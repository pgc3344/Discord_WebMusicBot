# 웹 제어 패널이 있는 디스코드 음악 봇

디스코드 서버에서 음악을 재생할 수 있는 다양한 기능을 갖춘 음악 봇으로, 채팅 명령어와 편리한 웹 기반 제어 패널을 모두 제공합니다.

## 기능

- 🎵 YouTube 이름또는 링크로 음악 재생
- 🌐 쉬운 관리를 위한 웹 제어 패널
- 📋 대기열 관리 (추가, 제거, 비우기, 섞기)
- 🔊 볼륨 조절
- 🔁 반복 재생 모드
- ⏭️ 곡 건너뛰기
- 📱 반응형 웹 인터페이스

## 요구 사항

- Python 3.12.9 권장
- ffmpeg
- 디스코드 봇 토큰
- 웹 서버 (제어 패널 호스팅용)

## 설치 방법

1. 이 저장소를 클론합니다:
```bash
git clone https://github.com/pgc3344/Discord_WebMusicBot.git
cd Discord_WebMusicBot
```

2. 의존성 패키지를 설치합니다:
```bash
pip install -r requirements.txt
```

3. ffmpeg 설치 (아직 설치되지 않은 경우):
   - **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
   - **Windows**: [ffmpeg.org](https://ffmpeg.org/download.html)에서 다운로드 후 PATH에 추가
   - **macOS**: `brew install ffmpeg`

4. 루트 디렉토리에 다음 내용으로 `.env` 파일을 생성합니다:
```
DISCORD_TOKEN=your_discord_bot_token
BOT_PREFIX=!
WEB_HOST=0.0.0.0
WEB_PORT=8080
FFMPEG_VOLUME=0.5
AUDIO_BITRATE=384
```

## 사용 방법

### 봇 시작하기

```bash
python main.py
```

이렇게 하면 디스코드 봇과 제어 패널용 웹 서버가 모두 시작됩니다.

### 디스코드 명령어

- `!join` - 사용자의 음성 채널에 참가
- `!leave` - 음성 채널에서 나가기
- `!play <노래 이름 또는 URL>` - 노래 재생 또는 대기열에 추가
- `!skip` - 현재 노래 건너뛰기
- `!queue` - 현재 대기열 표시
- `!clear` - 대기열 비우기
- `!shuffle` - 대기열 섞기
- `!volume [0-100]` - 볼륨 설정 (인수 없이 사용하면 현재 볼륨 표시)
- `!loop` - 현재 곡 반복 모드 켜기/끄기
- `!np` 또는 `!now` - 현재 재생 중인 곡 표시
- `!remove <번호>` - 대기열에서 특정 곡 제거
- `!panel` - 웹 제어 패널 링크 받기

### 웹 제어 패널

웹 제어 패널은 `http://your_server_ip:8080`에서 접속할 수 있습니다.

웹 패널에서는 다음과 같은 작업을 할 수 있습니다:
- 봇이 참가한 모든 서버 보기
- 음악 대기열 관리
- 재생 제어
- 볼륨 조절
- 반복 모드 설정

## 디스코드 봇 생성 방법

1. [디스코드 개발자 포털](https://discord.com/developers/applications)로 이동
2. 새 애플리케이션 생성
3. "Bot" 탭으로 이동하여 "Add Bot" 클릭
4. "Privileged Gateway Intents" 아래에서 "Message Content Intent" 활성화
5. 토큰을 복사하여 `.env` 파일에 추가
6. OAuth2 > URL Generator로 이동, "bot" 스코프와 다음 권한을 선택:
   - Send Messages
   - Connect
   - Speak
   - Use Voice Activity
7. 생성된 URL을 사용하여 봇을 서버에 초대

## 디렉토리 구조

```
discord-music-bot/
├── main.py            # 메인 봇 코드
├── .env               # 환경 변수
├── requirements.txt   # 의존성 패키지
├── templates/         # 웹 인터페이스 템플릿
│   ├── index.html     # 메인 페이지
│   └── guild.html     # 서버별 페이지
└── static/            # 웹 인터페이스 정적 에셋
    ├── css/
    └── js/
```

## 의존성 패키지

- discord.py
- yt-dlp
- Flask
- Flask-SocketIO
- python-dotenv
- requests

## 라이선스

[MIT](LICENSE)

## Thank you for

- [discord.py](https://github.com/Rapptz/discord.py)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [Flask](https://flask.palletsprojects.com/)