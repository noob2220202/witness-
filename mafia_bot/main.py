"""
마피아 봇 — 진입점
python-telegram-bot v21 + PicklePersistence
"""
import logging
import os
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PicklePersistence,
    filters,
)
import config
from handlers.group_cmd import (
    startgame_handler,
    join_handler,
    begin_handler,
    status_handler,
    skip_handler,
    endgame_handler,
    migrate_handler,
    chat_guard_handler,
)
from handlers.dm_cmd import start_handler
from handlers.callbacks import callback_router

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """봇 연결 후 초기화."""
    me = await application.bot.get_me()
    config.BOT_USERNAME = me.username
    log.info("봇 준비: @%s", me.username)

    # 재시작 복구: 진행 중인 게임이 있으면 해당 페이즈에서 재개
    from game.state import Phase
    from handlers.phase_jobs import advance_phase, schedule_phase
    import config as cfg

    games: dict = application.bot_data.get("games", {})
    for group_id, gs in list(games.items()):
        if gs.phase in (Phase.LOBBY, Phase.ENDED):
            continue
        # 진행 중 게임: 현재 페이즈를 즉시 advance (타임아웃 처리)
        log.info("재시작 복구: group_id=%s phase=%s", group_id, gs.phase)
        try:
            await advance_phase(application, gs)
        except Exception as e:
            log.warning("복구 실패 group_id=%s: %s", group_id, e)


def main() -> None:
    os.makedirs("mafia_bot/data", exist_ok=True)

    persistence = PicklePersistence(filepath=config.PERSISTENCE_PATH)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .persistence(persistence)
        .concurrent_updates(False)   # race condition 방지
        .post_init(post_init)
        .build()
    )

    # ── 그룹 명령어 ──────────────────────────────────────────
    app.add_handler(CommandHandler(
        "startgame", startgame_handler, filters=filters.ChatType.GROUPS
    ))
    app.add_handler(CommandHandler(
        "join", join_handler, filters=filters.ChatType.GROUPS
    ))
    app.add_handler(CommandHandler(
        "begin", begin_handler, filters=filters.ChatType.GROUPS
    ))
    app.add_handler(CommandHandler(
        "status", status_handler, filters=filters.ChatType.GROUPS
    ))
    app.add_handler(CommandHandler(
        "skip", skip_handler, filters=filters.ChatType.GROUPS
    ))
    app.add_handler(CommandHandler(
        "endgame", endgame_handler, filters=filters.ChatType.GROUPS
    ))

    # ── DM 명령어 ────────────────────────────────────────────
    app.add_handler(CommandHandler(
        "start", start_handler, filters=filters.ChatType.PRIVATE
    ))

    # ── 그룹 마이그레이션 ────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.StatusUpdate.MIGRATE, migrate_handler
    ))

    # ── InlineKeyboard 콜백 ──────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_router))

    # ── 채팅 감시 (사망자·미참여자 메시지 삭제) ──────────────
    # 텍스트·스티커·사진·동영상 등 모든 그룹 메시지 감시
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL & ~filters.COMMAND,
        chat_guard_handler,
    ))

    log.info("폴링 시작...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
