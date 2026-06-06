"""
그룹 채팅 명령어 핸들러.
/startgame /join /begin /status /skip /endgame
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game.state import GameState, Phase, Faction, WinCondition, PlayerState
from game.roles import ROLES
from game.assignment import assign_roles, build_player_states
from handlers.dm_cmd import make_dm_link, _build_lobby_keyboard
from handlers.phase_jobs import (
    schedule_phase, cancel_phase_job, send_role_dms, send_night_action_dms,
    _safe_send, advance_phase,
)
from messages.templates import (
    esc,
    lobby_msg, status_msg,
    not_enough_players_msg, dm_required_players_msg,
    game_not_found_msg, already_in_game_msg, game_full_msg,
    night_start_msg,
)
import config

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# /startgame
# ─────────────────────────────────────────────────────────────────────────────

async def startgame_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    user = update.effective_user

    games: dict = context.bot_data.setdefault("games", {})

    if group_id in games:
        await update.message.reply_text(
            "⚠️ 이미 진행 중인 게임이 있습니다\\.\n"
            "`/endgame` 으로 현재 게임을 종료한 후 새 게임을 시작하세요\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    gs = GameState(group_chat_id=group_id, creator_id=user.id)
    games[group_id] = gs

    keyboard = _build_lobby_keyboard(group_id)
    sent = await update.message.reply_text(
        lobby_msg(gs),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    gs.lobby_msg_id = sent.message_id

    # 로비 타임아웃 예약
    schedule_phase(context, group_id, config.LOBBY_TIMEOUT, "lobby")

    log.info("게임 생성: group_id=%s, creator=%s", group_id, user.id)


# ─────────────────────────────────────────────────────────────────────────────
# /join (버튼 없이 텍스트로 참가)
# ─────────────────────────────────────────────────────────────────────────────

async def join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    user = update.effective_user

    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await update.message.reply_text(
            game_not_found_msg(), parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if gs.phase != Phase.LOBBY:
        await update.message.reply_text(
            "❌ 게임이 이미 시작되었습니다\\.", parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if user.id in gs.players:
        await update.message.reply_text(
            already_in_game_msg(), parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if len(gs.players) >= config.MAX_PLAYERS:
        await update.message.reply_text(
            game_full_msg(config.MAX_PLAYERS), parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # DM 개통 확인
    dm_capable: set = context.bot_data.get("dm_capable", set())
    if user.id not in dm_capable:
        dm_link = make_dm_link(group_id)
        await update.message.reply_text(
            f"📬 *봇 DM을 먼저 열어주세요\\!*\n\n"
            f"[여기를 눌러 DM 열기]({dm_link})\n\n"
            "> DM을 연 후 다시 `/join` 을 입력하세요\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )
        return

    display = f"@{user.username}" if user.username else user.first_name
    gs.players[user.id] = PlayerState(
        user_id=user.id,
        username=user.username or user.first_name,
        display=display,
        role_key="",
        faction=Faction.CITIZEN,
        win_cond=WinCondition.NONE,
    )

    await update.message.reply_text(
        f"✅ *{esc(display)}* 님이 게임에 참가했습니다\\! "
        f"\\({esc(str(len(gs.players)))}/{esc(str(config.MAX_PLAYERS))}명\\)",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # 로비 메시지 갱신
    try:
        await context.bot.edit_message_text(
            chat_id=group_id,
            message_id=gs.lobby_msg_id,
            text=lobby_msg(gs),
            reply_markup=_build_lobby_keyboard(group_id),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# /begin
# ─────────────────────────────────────────────────────────────────────────────

async def begin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    user = update.effective_user

    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await update.message.reply_text(
            game_not_found_msg(), parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if gs.creator_id != user.id:
        await update.message.reply_text(
            "❌ 게임 진행자만 게임을 시작할 수 있습니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    if gs.phase != Phase.LOBBY:
        await update.message.reply_text(
            "❌ 게임이 이미 시작되었습니다\\.", parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if len(gs.players) < config.MIN_PLAYERS:
        await update.message.reply_text(
            not_enough_players_msg(len(gs.players), config.MIN_PLAYERS),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # DM 미개통 플레이어 확인
    dm_capable: set = context.bot_data.get("dm_capable", set())
    missing_dm = [
        p.display for uid, p in gs.players.items() if uid not in dm_capable
    ]
    if missing_dm:
        await update.message.reply_text(
            dm_required_players_msg(missing_dm),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # 직업 배정
    player_ids = list(gs.players.keys())
    names = {uid: p.username for uid, p in gs.players.items()}
    displays = {uid: p.display for uid, p in gs.players.items()}

    assignment = assign_roles(player_ids)
    gs.players = build_player_states(assignment, names, displays)

    # 로비 타임아웃 취소
    cancel_phase_job(context, gs)

    # 밤 1 시작
    gs.phase = Phase.NIGHT
    gs.day_number = 1

    await update.message.reply_text(
        f"🎲 *게임 시작\\!* {esc(str(len(gs.players)))}명의 직업이 배정되었습니다\\.\n\n"
        "> DM에서 자신의 직업을 확인하세요\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # 역할 DM 전송 (1회성)
    await send_role_dms(context.bot, gs)

    # 그룹에 밤 시작 알림
    await _safe_send(
        context.bot, group_id,
        night_start_msg(gs.day_number, gs.alive_count())
    )

    # 밤 행동 버튼 DM 전송
    await send_night_action_dms(context.bot, gs)

    # 밤 타이머 예약
    schedule_phase(context, group_id, config.NIGHT_TIMEOUT, "night")

    log.info("게임 시작: group_id=%s, players=%s", group_id, len(gs.players))


# ─────────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────────

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await update.message.reply_text(
            game_not_found_msg(), parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    await update.message.reply_text(
        status_msg(gs), parse_mode=ParseMode.MARKDOWN_V2
    )


# ─────────────────────────────────────────────────────────────────────────────
# /skip
# ─────────────────────────────────────────────────────────────────────────────

async def skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    user = update.effective_user

    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await update.message.reply_text(
            game_not_found_msg(), parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if gs.creator_id != user.id:
        await update.message.reply_text(
            "❌ 게임 진행자만 페이즈를 건너뛸 수 있습니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    if gs.phase in (Phase.LOBBY, Phase.ENDED):
        await update.message.reply_text(
            "❌ 현재 건너뛸 수 있는 페이즈가 없습니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    cancel_phase_job(context, gs)
    await update.message.reply_text(
        "⏩ *페이즈를 강제로 진행합니다\\.*",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await advance_phase(context, gs)


# ─────────────────────────────────────────────────────────────────────────────
# /endgame
# ─────────────────────────────────────────────────────────────────────────────

async def endgame_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    group_id = update.effective_chat.id
    user = update.effective_user

    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await update.message.reply_text(
            game_not_found_msg(), parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    if gs.creator_id != user.id:
        await update.message.reply_text(
            "❌ 게임 진행자만 게임을 종료할 수 있습니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    cancel_phase_job(context, gs)
    gs.phase = Phase.ENDED
    del games[group_id]

    await update.message.reply_text(
        "🛑 *게임이 강제 종료되었습니다\\.*",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 그룹 마이그레이션 핸들러 (일반 그룹 → 슈퍼그룹)
# ─────────────────────────────────────────────────────────────────────────────

async def migrate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    old_id = update.message.migrate_from_chat_id
    new_id = update.effective_chat.id

    if old_id is None:
        return

    games: dict = context.bot_data.get("games", {})
    if old_id in games:
        gs = games.pop(old_id)
        gs.group_chat_id = new_id
        games[new_id] = gs
        log.info("그룹 마이그레이션: %s → %s", old_id, new_id)
