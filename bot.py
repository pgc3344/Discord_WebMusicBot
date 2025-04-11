import os
import json
import asyncio
import threading
from urllib.parse import urlparse

import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import yt_dlp
from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
from flask_socketio import SocketIO
from dotenv import load_dotenv

load_dotenv()

# 봇 설정
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('BOT_PREFIX', '!')
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': f'-vn -filter:a "volume={os.getenv("FFMPEG_VOLUME", "0.5")}" -b:a {os.getenv("AUDIO_BITRATE", "384")}k'
}

# YouTube DL 옵션
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': os.getenv('WEB_HOST', '0.0.0.0'),
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': os.getenv('AUDIO_BITRATE', '384'),
    }]
}

# 봇 인스턴스 생성
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# 음악 재생을 위한 클래스
class MusicPlayer:
    def __init__(self):
        self.queue = {}
        self.current_song = {}
        self.ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
        self.guild_states = {}

    def get_guild_state(self, guild_id):
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {
                'queue': [],
                'current': None,
                'volume': 0.5,
                'is_playing': False,
                'loop': False
            }
        return self.guild_states[guild_id]

    def extract_info(self, url, download=False):
        try:
            return self.ytdl.extract_info(url, download=download)
        except Exception as e:
            print(f"Error extracting info: {e}")
            return None

    async def add_to_queue(self, guild_id, url):
        state = self.get_guild_state(guild_id)
        
        info = self.extract_info(url, download=False)
        
        if 'entries' in info:
            # 플레이리스트인 경우
            for entry in info['entries']:
                url = entry['webpage_url']
                title = entry['title']
                thumbnail = entry.get('thumbnail', '')
                duration = entry.get('duration', 0)
                
                state['queue'].append({
                    'url': url,
                    'title': title,
                    'thumbnail': thumbnail,
                    'duration': duration
                })
            return len(info['entries'])
        else:
            # 단일 곡인 경우
            title = info['title']
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            
            state['queue'].append({
                'url': url,
                'title': title,
                'thumbnail': thumbnail,
                'duration': duration
            })
            return 1

    async def play_next(self, guild_id, voice_client):
        state = self.get_guild_state(guild_id)
        
        if not state['queue'] and not state['loop']:
            state['is_playing'] = False
            state['current'] = None
            return
        
        if state['loop'] and state['current']:
            song = state['current']
        else:
            if not state['queue']:
                state['is_playing'] = False
                state['current'] = None
                return
            
            song = state['queue'].pop(0)
            state['current'] = song
        
        state['is_playing'] = True
        
        try:
            info = self.extract_info(song['url'], download=False)
            stream_url = info['url']
            
            source = FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            voice_client.play(
                source,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.play_next(guild_id, voice_client), bot.loop
                )
            )
            
            voice_client.source = discord.PCMVolumeTransformer(voice_client.source)
            voice_client.source.volume = state['volume']
        except Exception as e:
            print(f"Error playing song: {e}")
            await self.play_next(guild_id, voice_client)

    def get_queue(self, guild_id):
        state = self.get_guild_state(guild_id)
        return state['queue']

    def get_current(self, guild_id):
        state = self.get_guild_state(guild_id)
        return state['current']

    def clear_queue(self, guild_id):
        state = self.get_guild_state(guild_id)
        state['queue'] = []

    def shuffle_queue(self, guild_id):
        import random
        state = self.get_guild_state(guild_id)
        random.shuffle(state['queue'])

    def set_volume(self, guild_id, volume):
        state = self.get_guild_state(guild_id)
        state['volume'] = volume / 100
        
        guild = bot.get_guild(guild_id)
        if guild and guild.voice_client and guild.voice_client.source:
            guild.voice_client.source.volume = state['volume']

    def toggle_loop(self, guild_id):
        state = self.get_guild_state(guild_id)
        state['loop'] = not state['loop']
        return state['loop']

    def skip_song(self, guild_id, voice_client):
        if voice_client and voice_client.is_playing():
            voice_client.stop()
        
    def remove_song(self, guild_id, index):
        state = self.get_guild_state(guild_id)
        if 0 <= index < len(state['queue']):
            return state['queue'].pop(index)
        return None

    def get_guild_states_data(self):
        data = {}
        for guild_id, state in self.guild_states.items():
            guild = bot.get_guild(int(guild_id))
            if guild:
                data[guild_id] = {
                    'guild_name': guild.name,
                    'guild_id': guild_id,
                    'queue': state['queue'],
                    'current': state['current'],
                    'is_playing': state['is_playing'],
                    'volume': int(state['volume'] * 100),
                    'loop': state['loop']
                }
        return data

# 음악 플레이어 인스턴스 생성
music_player = MusicPlayer()

# Flask 웹 서버 설정
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# zfill 필터 추가
@app.template_filter('zfill')
def zfill_filter(s, width):
    return str(s).zfill(width)

@app.route('/')
def index():
    guild_data = music_player.get_guild_states_data()
    return render_template('index.html', guilds=guild_data)

@app.route('/guild/<guild_id>')
def guild_page(guild_id):
    state = music_player.get_guild_state(int(guild_id))
    guild = bot.get_guild(int(guild_id))
    
    guild_data = {
        'guild_name': guild.name if guild else "Unknown",
        'guild_id': guild_id,
        'queue': state['queue'],
        'current': state['current'],
        'is_playing': state['is_playing'],
        'volume': int(state['volume'] * 100),
        'loop': state['loop']
    }
    
    return render_template('guild.html', guild=guild_data)

@app.route('/api/queue/<guild_id>', methods=['GET'])
def get_queue(guild_id):
    queue = music_player.get_queue(int(guild_id))
    current = music_player.get_current(int(guild_id))
    state = music_player.get_guild_state(int(guild_id))
    
    return jsonify({
        'queue': queue,
        'current': current,
        'is_playing': state['is_playing'],
        'volume': int(state['volume'] * 100),
        'loop': state['loop']
    })

@app.route('/api/add/<guild_id>', methods=['POST'])
def add_song(guild_id):
    url = request.json.get('url', '')
    
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    guild_id = int(guild_id)
    guild = bot.get_guild(guild_id)
    
    if not guild:
        return jsonify({'success': False, 'error': 'Guild not found'})
    
    async def add_song_task():
        try:
            count = await music_player.add_to_queue(guild_id, url)
            
            voice_client = guild.voice_client
            if voice_client and not voice_client.is_playing():
                await music_player.play_next(guild_id, voice_client)
                
            socketio.emit('queue_updated', {'guild_id': guild_id})
            return count
        except Exception as e:
            print(f"Error adding song: {e}")
            return 0
    
    count = asyncio.run_coroutine_threadsafe(add_song_task(), bot.loop).result()
    
    return jsonify({'success': True, 'message': f"Added {count} songs to the queue"})

@app.route('/api/skip/<guild_id>', methods=['POST'])
def skip_song(guild_id):
    guild_id = int(guild_id)
    guild = bot.get_guild(guild_id)
    
    if not guild or not guild.voice_client:
        return jsonify({'success': False, 'error': 'Guild not connected to voice'})
    
    music_player.skip_song(guild_id, guild.voice_client)
    socketio.emit('queue_updated', {'guild_id': guild_id})
    
    return jsonify({'success': True})

@app.route('/api/remove/<guild_id>/<int:index>', methods=['POST'])
def remove_song(guild_id, index):
    guild_id = int(guild_id)
    
    removed_song = music_player.remove_song(guild_id, index)
    
    if removed_song:
        socketio.emit('queue_updated', {'guild_id': guild_id})
        return jsonify({'success': True, 'song': removed_song})
    
    return jsonify({'success': False, 'error': 'Invalid song index'})

@app.route('/api/clear/<guild_id>', methods=['POST'])
def clear_queue(guild_id):
    guild_id = int(guild_id)
    
    music_player.clear_queue(guild_id)
    socketio.emit('queue_updated', {'guild_id': guild_id})
    
    return jsonify({'success': True})

@app.route('/api/shuffle/<guild_id>', methods=['POST'])
def shuffle_queue(guild_id):
    guild_id = int(guild_id)
    
    music_player.shuffle_queue(guild_id)
    socketio.emit('queue_updated', {'guild_id': guild_id})
    
    return jsonify({'success': True})

@app.route('/api/volume/<guild_id>', methods=['POST'])
def set_volume(guild_id):
    guild_id = int(guild_id)
    volume = int(request.json.get('volume', 50))
    
    if volume < 0:
        volume = 0
    elif volume > 100:
        volume = 100
    
    music_player.set_volume(guild_id, volume)
    socketio.emit('queue_updated', {'guild_id': guild_id})
    
    return jsonify({'success': True, 'volume': volume})

@app.route('/api/loop/<guild_id>', methods=['POST'])
def toggle_loop(guild_id):
    guild_id = int(guild_id)
    
    loop_state = music_player.toggle_loop(guild_id)
    socketio.emit('queue_updated', {'guild_id': guild_id})
    
    return jsonify({'success': True, 'loop': loop_state})

# 디스코드 봇 명령어
@bot.event
async def on_ready():
    print(f'{bot.user.name} 준비 완료!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{PREFIX}help"))

@bot.command(name='join', help='음성 채널에 봇을 참가시킵니다.')
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("음성 채널에 먼저 참가해주세요!")
        return
    
    voice_channel = ctx.author.voice.channel
    
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(voice_channel)
    else:
        await voice_channel.connect()
    
    await ctx.send(f"'{voice_channel.name}' 채널에 참가했습니다!")

@bot.command(name='leave', help='음성 채널에서 봇을 나가게 합니다.')
async def leave(ctx):
    if ctx.voice_client is None:
        await ctx.send("봇이 음성 채널에 참가해있지 않습니다!")
        return
    
    state = music_player.get_guild_state(ctx.guild.id)
    state['is_playing'] = False
    state['current'] = None
    
    await ctx.voice_client.disconnect()
    await ctx.send("음성 채널에서 나갔습니다!")

@bot.command(name='play', help='음악을 재생합니다. URL이나 검색어를 입력하세요.')
async def play(ctx, *, query):
    if ctx.author.voice is None:
        await ctx.send("음성 채널에 먼저 참가해주세요!")
        return
    
    voice_channel = ctx.author.voice.channel
    
    if ctx.voice_client is None:
        await voice_channel.connect()
    
    await ctx.send(f"🔍 **검색 중**: `{query}`")
    
    # URL이 아닌 경우 YouTube 검색
    if not any(service in query for service in ['youtube.com', 'youtu.be', 'soundcloud.com', 'spotify.com']):
        query = f"ytsearch:{query}"
    
    try:
        count = await music_player.add_to_queue(ctx.guild.id, query)
        
        if count > 1:
            await ctx.send(f"✅ **{count}개의 곡이 대기열에 추가되었습니다!**")
        else:
            state = music_player.get_guild_state(ctx.guild.id)
            song = state['queue'][-1] if state['queue'] else None
            if song:
                await ctx.send(f"✅ **대기열에 추가됨**: `{song['title']}`")
        
        state = music_player.get_guild_state(ctx.guild.id)
        
        if not state['is_playing']:
            await music_player.play_next(ctx.guild.id, ctx.voice_client)
    except Exception as e:
        await ctx.send(f"❌ **오류 발생**: `{str(e)}`")

@bot.command(name='skip', help='현재 재생 중인 곡을 건너뜁니다.')
async def skip(ctx):
    if ctx.voice_client is None:
        await ctx.send("봇이 음성 채널에 참가해있지 않습니다!")
        return
    
    if not ctx.voice_client.is_playing():
        await ctx.send("현재 재생 중인 곡이 없습니다!")
        return
    
    ctx.voice_client.stop()
    await ctx.send("⏭️ **곡을 건너뛰었습니다!**")

@bot.command(name='queue', help='재생 대기열을 보여줍니다.')
async def queue(ctx):
    state = music_player.get_guild_state(ctx.guild.id)
    queue = state['queue']
    current = state['current']
    
    if not current and not queue:
        await ctx.send("재생 대기열이 비어 있습니다!")
        return
    
    embed = discord.Embed(title="🎵 재생 대기열", color=discord.Color.blue())
    
    if current:
        embed.add_field(
            name="🎧 현재 재생 중",
            value=f"[{current['title']}]({current['url']}) | `{format_duration(current['duration'])}`",
            inline=False
        )
    
    if queue:
        queue_text = ""
        for i, song in enumerate(queue):
            if i < 10:  # 최대 10개만 표시
                queue_text += f"`{i+1}.` [{song['title']}]({song['url']}) | `{format_duration(song['duration'])}`\n"
        
        if queue_text:
            embed.add_field(name=f"📑 대기열 ({len(queue)}곡)", value=queue_text, inline=False)
        
        if len(queue) > 10:
            embed.set_footer(text=f"외 {len(queue) - 10}곡이 더 있습니다.")
    
    await ctx.send(embed=embed)

@bot.command(name='clear', help='재생 대기열을 비웁니다.')
async def clear(ctx):
    music_player.clear_queue(ctx.guild.id)
    await ctx.send("🗑️ **대기열을 비웠습니다!**")

@bot.command(name='shuffle', help='재생 대기열을 섞습니다.')
async def shuffle(ctx):
    state = music_player.get_guild_state(ctx.guild.id)
    
    if not state['queue'] or len(state['queue']) < 2:
        await ctx.send("섞을 곡이 충분하지 않습니다!")
        return
    
    music_player.shuffle_queue(ctx.guild.id)
    await ctx.send("🔀 **대기열을 섞었습니다!**")

@bot.command(name='volume', help='볼륨을 설정합니다. (0-100)')
async def volume(ctx, volume: int = None):
    if volume is None:
        state = music_player.get_guild_state(ctx.guild.id)
        current_volume = int(state['volume'] * 100)
        await ctx.send(f"🔊 **현재 볼륨**: `{current_volume}%`")
        return
    
    if volume < 0 or volume > 100:
        await ctx.send("볼륨은 0에서 100 사이여야 합니다!")
        return
    
    music_player.set_volume(ctx.guild.id, volume)
    await ctx.send(f"🔊 **볼륨이 {volume}%로 설정되었습니다!**")

@bot.command(name='loop', help='현재 곡을 반복합니다.')
async def loop(ctx):
    loop_state = music_player.toggle_loop(ctx.guild.id)
    
    if loop_state:
        await ctx.send("🔁 **반복 재생이 활성화되었습니다!**")
    else:
        await ctx.send("➡️ **반복 재생이 비활성화되었습니다!**")

@bot.command(name='np', aliases=['now'], help='현재 재생 중인 곡을 보여줍니다.')
async def now_playing(ctx):
    state = music_player.get_guild_state(ctx.guild.id)
    current = state['current']
    
    if not current:
        await ctx.send("현재 재생 중인 곡이 없습니다!")
        return
    
    embed = discord.Embed(title="🎵 현재 재생 중", color=discord.Color.blue())
    embed.add_field(
        name=current['title'],
        value=f"[YouTube 링크]({current['url']}) | `{format_duration(current['duration'])}`",
        inline=False
    )
    
    if current['thumbnail']:
        embed.set_thumbnail(url=current['thumbnail'])
    
    embed.set_footer(text=f"볼륨: {int(state['volume'] * 100)}% | 반복: {'켬' if state['loop'] else '끔'}")
    
    await ctx.send(embed=embed)

@bot.command(name='remove', help='대기열에서 특정 곡을 제거합니다.')
async def remove(ctx, index: int):
    if index <= 0:
        await ctx.send("올바른 인덱스를 입력해주세요! (1부터 시작)")
        return
    
    removed_song = music_player.remove_song(ctx.guild.id, index - 1)
    
    if removed_song:
        await ctx.send(f"🗑️ **대기열에서 제거됨**: `{removed_song['title']}`")
    else:
        await ctx.send("해당 인덱스의 곡을 찾을 수 없습니다!")

@bot.command(name='panel', help='웹 제어 패널 URL을 보여줍니다.')
async def panel(ctx):
    # 서버의 IP 또는 도메인으로 수정
    panel_url = f"http://개아무거나.서버.한국:8080/guild/{ctx.guild.id}"
    
    embed = discord.Embed(
        title="🎛️ 웹 제어 패널",
        description=f"아래 링크를 클릭하여 음악 봇의 웹 제어 패널에 접속하세요:",
        color=discord.Color.blue()
    )
    embed.add_field(name="URL", value=f"[제어 패널 열기]({panel_url})", inline=False)
    embed.set_footer(text="웹 브라우저에서 위 링크를 열어주세요.")
    
    await ctx.send(embed=embed)

# 시간 포맷 유틸리티 함수
def format_duration(seconds):
    if not seconds:
        return "알 수 없음"
    
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

# 웹 서버 실행 함수
def run_flask():
    socketio.run(app, 
                host=os.getenv('WEB_HOST', '0.0.0.0'), 
                port=int(os.getenv('WEB_PORT', 8080)))

# 메인 함수
def main():
    # 웹 서버 스레드 시작
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 디스코드 봇 실행
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
    app.run(host='0.0.0.0',port=8080,debug=True)