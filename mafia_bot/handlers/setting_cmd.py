"""
/setting 명령어 — 타이머·직업 설정 UI
그룹 관리자(또는 게임 진행자)만 수정 가능.
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game.roles import ROLES
from game.state import Faction
from messages.templates import esc

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 기본값 & 상수
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TIMERS = {"lobby": 300, "night": 90, "discuss": 180, "vote": 60}

TIMER_META = {
    "lobby":   {"label": "🏠 로비",  "min": 60,  "max": 600, "step": 30},
    "night":   {"label": "🌙 밤",    "min": 30,  "max": 300, "step": 30},
    "discuss": {"label": "💬 토론",  "min": 60,  "max": 600, "step": 30},
    "vote":    {"label": "🗳️ 투표",  "min": 30,  "max": 300, "step": 30},
}

# 진영별 토글 가능한 직업 (mafioso 제외 — 기본 마피아는 항상 필요)
FACTION_ROLES: dict[str, list[str]] = {
    "mafia":   ["godfather", "spy", "madam", "beast", "hitman", "witch", "fraud", "scientist", "thief"],
    "citizen": [
        "police", "doctor", "vigilante", "agent", "soldier", "politician",
        "medium", "gangster", "reporter", "detective", "grave_robber",
        "terrorist", "priest", "prophet", "judge", "magician", "psychologist", "lover",
    ],
    "cult":    ["cult_leader", "fanatic"],
    "neutral": ["serial_killer", "jester", "survivor"],
}

FACTION_LABEL = {
    "mafia":   "🔴 마피아",
    "citizen": "🔵 시민",
    "cult":    "🟣 교주",
    "neutral": "⚪ 중립",
}


# ─────────────────────────────────────────────────────────────────────────────
# 설정 조회 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def get_settings(bot_data: dict, group_id: int) -> dict:
    settings = bot_data.setdefault("settings", {})
    if group_id not in settings:
        settings[group_id] = {
            "timers": dict(DEFAULT_TIMERS),
            "disabled_roles": set(),
        }
    s = settings[group_id]
    # 누락된 키 보완
    s.setdefault("timers", dict(DEFAULT_TIMERS))
    s.setdefault("disabled_roles", set())
    for k, v in DEFAULT_TIMERS.items():
        s["timers"].setdefault(k, v)
    return s


async def _is_admin(context: ContextTypes.DEFAULT_TYPE, group_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(group_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def _is_creator(context: ContextTypes.DEFAULT_TYPE, group_id: int, user_id: int) -> bool:
    gs = context.bot_data.get("games", {}).get(group_id)
    return gs is not None and gs.creator_id == user_id


async def _check_permission(context, group_id, user_id) -> bool:
    return _is_creator(context, group_id, user_id) or await _is_admin(context, group_id, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# 메뉴 빌더
# ─────────────────────────────────────────────────────────────────────────────

def _main_menu_text(group_id: int, bot_data: dict) -> str:
    s = get_settings(bot_data, group_id)
    disabled = s["disabled_roles"]
    timers = s["timers"]
    total_roles = sum(len(v) for v in FACTION_ROLES.values())
    disabled_cnt = len(disabled & {r for roles in FACTION_ROLES.values() for r in roles})
    return (
        "⚙️ *게임 설정*\n\n"
        f"⏱ 타이머  🏠{timers['lobby']}s  🌙{timers['night']}s  "
        f"💬{timers['discuss']}s  🗳️{timers['vote']}s\n"
        f"🎭 직업  활성 *{total_roles - disabled_cnt}*/{total_roles}개\n\n"
        "_설정은 다음 게임부터 적용됩니다\\._"
    )


def _main_menu_keyboard(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ 타이머 설정", callback_data=f"set:t_menu:{group_id}"),
            InlineKeyboardButton("🎭 직업 설정", callback_data=f"set:r_menu:{group_id}"),
        ],
        [InlineKeyboardButton("❌ 닫기", callback_data=f"set:close:{group_id}")],
    ])


def _timer_menu_text(group_id: int, bot_data: dict) -> str:
    s = get_settings(bot_data, group_id)
    t = s["timers"]
    lines = ["⏱ *타이머 설정*\n"]
    for key, meta in TIMER_META.items():
        lines.append(f"{meta['label']}  *{t[key]}초*  \\(최소 {meta['min']}s / 최대 {meta['max']}s\\)")
    return "\n".join(lines)


def _timer_menu_keyboard(group_id: int, bot_data: dict) -> InlineKeyboardMarkup:
    s = get_settings(bot_data, group_id)
    t = s["timers"]
    rows = []
    for key, meta in TIMER_META.items():
        step = meta["step"]
        rows.append([
            InlineKeyboardButton(f"{meta['label']}  {t[key]}초", callback_data="set:noop"),
            InlineKeyboardButton(f"➖{step}s", callback_data=f"set:t_adj:{group_id}:{key}:-{step}"),
            InlineKeyboardButton(f"➕{step}s", callback_data=f"set:t_adj:{group_id}:{key}:{step}"),
        ])
    rows.append([InlineKeyboardButton("🔙 뒤로", callback_data=f"set:menu:{group_id}")])
    return InlineKeyboardMarkup(rows)


def _role_menu_text() -> str:
    return "🎭 *직업 설정* — 진영 선택\n\n비활성화한 직업은 해당 게임에 등장하지 않습니다\\."


def _role_menu_keyboard(group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(FACTION_LABEL["mafia"],   callback_data=f"set:r_fac:{group_id}:mafia"),
            InlineKeyboardButton(FACTION_LABEL["citizen"], callback_data=f"set:r_fac:{group_id}:citizen"),
        ],
        [
            InlineKeyboardButton(FACTION_LABEL["cult"],    callback_data=f"set:r_fac:{group_id}:cult"),
            InlineKeyboardButton(FACTION_LABEL["neutral"], callback_data=f"set:r_fac:{group_id}:neutral"),
        ],
        [InlineKeyboardButton("🔙 뒤로", callback_data=f"set:menu:{group_id}")],
    ]
    return InlineKeyboardMarkup(rows)


def _faction_roles_text(faction: str, group_id: int, bot_data: dict) -> str:
    s = get_settings(bot_data, group_id)
    disabled = s["disabled_roles"]
    role_keys = FACTION_ROLES.get(faction, [])
    active = sum(1 for r in role_keys if r not in disabled)
    label = FACTION_LABEL.get(faction, faction)
    return (
        f"{label} *직업 설정*\n\n"
        f"활성 직업: *{active}/{len(role_keys)}*\n"
        "_직업을 눌러 활성\\·비활성화하세요\\._"
    )


def _faction_roles_keyboard(faction: str, group_id: int, bot_data: dict) -> InlineKeyboardMarkup:
    s = get_settings(bot_data, group_id)
    disabled = s["disabled_roles"]
    role_keys = FACTION_ROLES.get(faction, [])
    buttons = []
    row = []
    for i, rk in enumerate(role_keys):
        role = ROLES.get(rk)
        name = role.name if role else rk
        mark = "❌" if rk in disabled else "✅"
        row.append(InlineKeyboardButton(
            f"{mark} {name}",
            callback_data=f"set:r_tog:{group_id}:{rk}",
        ))
        if len(row) == 3 or i == len(role_keys) - 1:
            buttons.append(row)
            row = []
    buttons.append([InlineKeyboardButton("🔙 직업 설정", callback_data=f"set:r_menu:{group_id}")])
    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# /setting 커맨드
# ─────────────────────────────────────────────────────────────────────────────

async def setting_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await _check_permission(context, group_id, user_id):
        await update.message.reply_text(
            "❌ 게임 진행자 또는 그룹 관리자만 설정을 변경할 수 있습니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    text = _main_menu_text(group_id, context.bot_data)
    keyboard = _main_menu_keyboard(group_id)
    await update.message.reply_text(
        text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
    )


# ─────────────────────────────────────────────────────────────────────────────
# 설정 콜백 라우터
# ─────────────────────────────────────────────────────────────────────────────

async def setting_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    # format: set:<action>:<group_id>[:<extra>...]
    parts = data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]
    try:
        group_id = int(parts[2])
    except ValueError:
        return

    user_id = query.from_user.id

    # 읽기 전용 noop
    if action == "noop":
        return

    # 닫기
    if action == "close":
        try:
            await query.delete_message()
        except Exception:
            pass
        return

    # 권한 확인
    if not await _check_permission(context, group_id, user_id):
        await query.answer("❌ 권한이 없습니다.", show_alert=True)
        return

    # ── 메인 메뉴 ──────────────────────────────────────────────
    if action == "menu":
        text = _main_menu_text(group_id, context.bot_data)
        keyboard = _main_menu_keyboard(group_id)
        try:
            await query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
        return

    # ── 타이머 메뉴 ────────────────────────────────────────────
    if action == "t_menu":
        text = _timer_menu_text(group_id, context.bot_data)
        keyboard = _timer_menu_keyboard(group_id, context.bot_data)
        try:
            await query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
        return

    # ── 타이머 조정 ────────────────────────────────────────────
    if action == "t_adj" and len(parts) >= 5:
        key = parts[3]
        try:
            delta = int(parts[4])
        except ValueError:
            return
        if key not in TIMER_META:
            return
        meta = TIMER_META[key]
        s = get_settings(context.bot_data, group_id)
        current = s["timers"].get(key, DEFAULT_TIMERS[key])
        new_val = max(meta["min"], min(meta["max"], current + delta))
        s["timers"][key] = new_val
        text = _timer_menu_text(group_id, context.bot_data)
        keyboard = _timer_menu_keyboard(group_id, context.bot_data)
        try:
            await query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
        return

    # ── 직업 설정 메뉴 ─────────────────────────────────────────
    if action == "r_menu":
        text = _role_menu_text()
        keyboard = _role_menu_keyboard(group_id)
        try:
            await query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
        return

    # ── 진영 직업 목록 ─────────────────────────────────────────
    if action == "r_fac" and len(parts) >= 4:
        faction = parts[3]
        if faction not in FACTION_ROLES:
            return
        text = _faction_roles_text(faction, group_id, context.bot_data)
        keyboard = _faction_roles_keyboard(faction, group_id, context.bot_data)
        try:
            await query.edit_message_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
        return

    # ── 직업 토글 ──────────────────────────────────────────────
    if action == "r_tog" and len(parts) >= 4:
        role_key = parts[3]
        if role_key not in ROLES:
            return
        # mafioso는 항상 활성 (기본 마피아)
        if role_key == "mafioso":
            await query.answer("⚠️ 기본 마피아는 비활성화할 수 없습니다.", show_alert=True)
            return
        s = get_settings(context.bot_data, group_id)
        disabled = s["disabled_roles"]
        if role_key in disabled:
            disabled.discard(role_key)
        else:
            disabled.add(role_key)
        # 현재 진영 찾아서 키보드 갱신
        faction = None
        for fac, keys in FACTION_ROLES.items():
            if role_key in keys:
                faction = fac
                break
        if faction:
            text = _faction_roles_text(faction, group_id, context.bot_data)
            keyboard = _faction_roles_keyboard(faction, group_id, context.bot_data)
            try:
                await query.edit_message_text(
                    text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception:
                pass
        return
