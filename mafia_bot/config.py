import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]

# 인원 제한
MIN_PLAYERS: int = 4
MAX_PLAYERS: int = 16

# 페이즈 타이머 (초)
LOBBY_TIMEOUT: int = 300        # 로비 대기 5분
NIGHT_TIMEOUT: int = 90         # 밤 행동 90초
RESULT_DELAY: int = 8           # 결과 공지 후 딜레이
DAY_DISCUSS_TIMEOUT: int = 180  # 낮 토론 3분
VOTE_TIMEOUT: int = 60          # 투표 1분
FINAL_DEFENSE_TIMEOUT: int = 15  # 최종변론 (고정 15초)
JUDGMENT_TIMEOUT: int = 15       # 찬반(업다운) 투표 (고정 15초)

# 의사 자힐 횟수
DOCTOR_SELF_HEAL_SHOTS: int = 1

# 저장 경로
PERSISTENCE_PATH: str = "mafia_bot/data/bot_data.pickle"

# 봇 유저네임 (main.py post_init에서 설정)
BOT_USERNAME: str = ""
