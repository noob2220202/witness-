from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import config


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start 또는 /start join_<group_id> DM 핸들러.
    그룹에서 deep-link 버튼 클릭 → DM에서 /start join_<group_id> 수신.
    """
    user = update.effective_user

    # DM 개통 가능 유저로 등록
    dm_capable: set = context.bot_data.setdefault("dm_capable", set())
    dm_capable.add(user.id)

    args = context.args
    if args:
        payload = args[0]
        if payload.startswith("join_"):
            try:
                group_id = int(payload[5:])
            except ValueError:
                await update.message.reply_text(
                    "❌ 잘못된 링크입니다\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
            await _handle_deep_link(update, context, group_id, user)
            return

    await update.message.reply_text(
        "👋 *마피아 봇에 오신 것을 환영합니다\\!*\n\n"
        "그룹 채팅에서 `/startgame` 을 입력해 게임을 시작하세요\\.\n\n"
        "> DM이 열려 있어야 역할과 행동 버튼을 받을 수 있습니다\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def _handle_deep_link(update, context, group_id: int, user):
    """deep-link로 진입한 유저를 게임 로비에 자동 추가 시도."""
    from game.state import Phase, Faction, WinCondition, PlayerState
    from game.roles import ROLES
    from messages.templates import lobby_msg, esc
    from telegram.constants import ParseMode
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    import config

    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await update.message.reply_text(
            "✅ *봇 DM이 열렸습니다\\!*\n\n"
            "게임이 시작되면 역할을 DM으로 전달해드립니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if gs.phase != Phase.LOBBY:
        await update.message.reply_text(
            "✅ *DM이 열렸습니다\\!*\n게임이 이미 진행 중입니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # 이미 참가 중
    if user.id in gs.players:
        await update.message.reply_text(
            "ℹ️ 이미 게임에 참가 중입니다\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if len(gs.players) >= config.MAX_PLAYERS:
        await update.message.reply_text(
            f"❌ 게임이 가득 찼습니다 \\(최대 {config.MAX_PLAYERS}명\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # 참가 처리
    display = user.first_name
    if user.username:
        display = f"@{user.username}"

    gs.players[user.id] = PlayerState(
        user_id=user.id,
        username=user.username or user.first_name,
        display=display,
        role_key="",
        faction=Faction.CITIZEN,
        win_cond=WinCondition.NONE,
    )

    await update.message.reply_text(
        f"✅ *게임에 참가했습니다\\!*\n\n"
        f"현재 참가자: *{len(gs.players)}명*\n"
        "> 게임이 시작될 때까지 기다려주세요\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # 그룹 로비 메시지 업데이트
    try:
        keyboard = _build_lobby_keyboard(group_id)
        await context.bot.edit_message_text(
            chat_id=group_id,
            message_id=gs.lobby_msg_id,
            text=lobby_msg(gs),
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        pass


def make_dm_link(group_id: int) -> str:
    """deep-link URL 생성"""
    return f"https://t.me/{config.BOT_USERNAME}?start=join_{group_id}"


def _build_lobby_keyboard(group_id: int):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🙋 참가하기", callback_data=f"join:{group_id}"),
            InlineKeyboardButton("📬 DM 열기", url=make_dm_link(group_id)),
        ]
    ])
