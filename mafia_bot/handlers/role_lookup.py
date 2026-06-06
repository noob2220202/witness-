"""
역할 도감 핸들러
/도감       — 전체 역할 목록
/[역할명]   — 상세 정보  (예: /마피아  /경찰  /교주  /mafioso)
"""
import re
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game.roles import ROLES, RoleDefinition
from game.state import Faction, WinCondition
from messages.templates import esc

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 이름 → role_key 매핑 (한국어 이름 + 영어 키 둘 다)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_NAME_MAP: dict[str, str] = {}
for _k, _r in ROLES.items():
    ROLE_NAME_MAP[_r.name] = _k   # 예: "마피아" → "mafioso"
    ROLE_NAME_MAP[_k] = _k        # 예: "mafioso" → "mafioso"

LOOKUP_RE = re.compile(r'^/([가-힣a-zA-Z0-9_]+)', re.UNICODE)

# ─────────────────────────────────────────────────────────────────────────────
# 표시용 레이블
# ─────────────────────────────────────────────────────────────────────────────

FACTION_LABEL = {
    Faction.MAFIA:   "🔴 마피아",
    Faction.CITIZEN: "🔵 시민",
    Faction.CULT:    "🟣 교주",
    Faction.NEUTRAL: "⚪ 중립",
}

WIN_LABEL = {
    WinCondition.MAFIA:         "마피아 팀 승리",
    WinCondition.CITIZEN:       "시민 팀 승리",
    WinCondition.CULT:          "교주 팀 승리",
    WinCondition.SERIAL_KILLER: "혼자 생존",
    WinCondition.JESTER:        "처형당하기",
    WinCondition.SURVIVOR:      "최후 생존",
    WinCondition.NONE:          "없음",
}

ACTION_LABEL = {
    "KILL":              "살인",
    "KILL_UNSTOPPABLE":  "관통 살인 \\(보호 무시\\)",
    "KILL_TARGETED":     "표적 처형",
    "PROTECT":           "치료",
    "INVESTIGATE_MAFIA": "마피아 여부 조사",
    "INVESTIGATE_ROLE":  "직업 조사",
    "INVESTIGATE_CULT":  "교주팀 조사",
    "ROLEBLOCK":         "능력 차단",
    "FROG_TRANSFORM":    "개구리 변환",
    "REVIVE":            "부활",
    "CULT_CONVERT":      "포교",
    "STEAL_ROLE":        "직업 도굴",
    "STEAL_ABILITY":     "능력 복사",
    "SWAP_PREPARE":      "교체 예약",
    "COMPARE":           "진영 비교",
    "DISARM":            "투표권 박탈",
    "DISGUISE":          "위장",
    "SEANCE":            "영혼 접촉",
    "TRACK":             "이동 추적",
}

FACTION_ORDER = [Faction.MAFIA, Faction.CITIZEN, Faction.CULT, Faction.NEUTRAL]


# ─────────────────────────────────────────────────────────────────────────────
# 메시지 빌더
# ─────────────────────────────────────────────────────────────────────────────

def _role_card(role: RoleDefinition) -> str:
    faction = FACTION_LABEL.get(role.faction, str(role.faction.value))
    win = WIN_LABEL.get(role.win_cond, str(role.win_cond.value))

    # 밤 행동
    if role.night_action:
        action_str = ACTION_LABEL.get(role.night_action, esc(role.night_action))
    else:
        action_str = "없음 \\(패시브\\)"

    # 사용 횟수
    if role.max_shots == -1:
        shots_str = "무한"
    elif role.max_shots == 0:
        shots_str = "\\-"
    else:
        shots_str = f"{role.max_shots}회"

    return (
        f"{faction}  ·  *{esc(role.name)}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{role.description}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌙 *밤 행동:* {action_str}\n"
        f"🔢 *사용 횟수:* {shots_str}\n"
        f"🏆 *승리 조건:* {esc(win)}"
    )


def _role_guide() -> str:
    lines = [
        "📖 *역할 도감*",
        "",
        "직업명을 입력하면 상세 정보를 볼 수 있습니다\\.",
        "_예: /마피아  /경찰  /교주  /연쇄살인마_",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for faction in FACTION_ORDER:
        roles_in = [r for r in ROLES.values() if r.faction == faction]
        label = FACTION_LABEL[faction]
        names = " · ".join(r.name for r in roles_in)
        lines.append(f"\n{label} *\\({len(roles_in)}종\\)*")
        lines.append(esc(names))

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 핸들러
# ─────────────────────────────────────────────────────────────────────────────

async def role_lookup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /[역할명] 메시지를 받아 역할 카드 또는 전체 도감을 응답.
    CommandHandler 대신 Regex MessageHandler 로 등록해 한국어 처리.
    """
    msg = update.effective_message
    if not msg or not msg.text:
        return

    m = LOOKUP_RE.match(msg.text)
    if not m:
        return

    query = m.group(1)

    if query == "도감":
        await msg.reply_text(_role_guide(), parse_mode=ParseMode.MARKDOWN_V2)
        return

    role_key = ROLE_NAME_MAP.get(query)
    if not role_key:
        return  # 알 수 없는 직업명 — 무시

    role = ROLES[role_key]
    try:
        await msg.reply_text(_role_card(role), parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        log.warning("역할 카드 전송 실패 role=%s: %s", role_key, e)
