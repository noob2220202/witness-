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
    topic_set_handler,
)
from handlers.dm_cmd import start_handler
from handlers.callbacks import callback_router
from handlers.setting_cmd import setting_handler, setting_callback_router
from handlers.role_lookup import role_lookup_handler

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

    # JobQueue 점검: 없으면 낮/밤 타이머가 동작하지 않아 게임이 멈춘다.
    if application.job_queue is None:
        log.error(
            "⚠️ JobQueue 가 설정되지 않았습니다! 페이즈 타이머가 동작하지 않아 "
            "낮이 끝나지 않고 게임이 진행되지 않습니다. "
            "다음을 설치하세요: pip install \"python-telegram-bot[job-queue]==21.9\""
        )
    else:
        log.info("JobQueue 정상 작동 — 페이즈 타이머 사용 가능")

    # 재시작 복구: 진행 중인 게임을 '같은 페이즈에서' 이어가도록 타이머만 재예약.
    # (기존엔 advance_phase 로 강제 진행해 밤/낮이 통째로 스킵되던 문제)
    from game.state import Phase
    from handlers.phase_jobs import advance_phase, schedule_phase
    import config as cfg

    games: dict = application.bot_data.get("games", {})

    # 구버전 pickle 호환: 새로 추가된 필드가 없는 옛 게임에 기본값 보강
    for gs in games.values():
        if not hasattr(gs, "topic_id"):
            gs.topic_id = None
        if not hasattr(gs, "accused_id"):
            gs.accused_id = None
        if not hasattr(gs, "judgment_votes"):
            gs.judgment_votes = {}

    # 페이즈별 재개 타이머 (고정 시간이면 값, None 이면 gs.timers[tag] 사용)
    resume_timer = {
        Phase.NIGHT:         ("night",    None),
        Phase.DAY_ANNOUNCE:  ("result",   cfg.RESULT_DELAY),
        Phase.DAY_DISCUSS:   ("discuss",  None),
        Phase.VOTE:          ("vote",     None),
        Phase.FINAL_DEFENSE: ("defense",  cfg.FINAL_DEFENSE_TIMEOUT),
        Phase.JUDGMENT:      ("judgment", cfg.JUDGMENT_TIMEOUT),
    }

    for group_id, gs in list(games.items()):
        if gs.phase in (Phase.LOBBY, Phase.ENDED):
            continue
        try:
            if gs.phase in resume_timer:
                tag, fixed = resume_timer[gs.phase]
                delay = fixed if fixed is not None else gs.timers.get(tag, 60)
                log.info("재시작 복구: group=%s phase=%s → 타이머 재예약(%ss)",
                         group_id, gs.phase.value, delay)
                schedule_phase(application, group_id, delay, tag)
            else:
                # 전환 중(resolve) 페이즈는 마저 진행
                log.info("재시작 복구: group=%s phase=%s → 진행", group_id, gs.phase.value)
                await advance_phase(application, gs)
        except Exception as e:
            log.warning("복구 실패 group=%s: %s", group_id, e)


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
    app.add_handler(CommandHandler(
        "setting", setting_handler, filters=filters.ChatType.GROUPS
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
    app.add_handler(CallbackQueryHandler(setting_callback_router, pattern=r"^set:"))
    app.add_handler(CallbackQueryHandler(callback_router))

    # ── 마피아 토픽 설정 (/마피아토픽설정, /토픽설정, /토픽) ────
    # role_lookup 보다 먼저 등록해 한국어 명령으로 가로채이지 않게 함
    _topic_cmd = filters.ChatType.GROUPS & filters.Regex(
        r'^/(마피아토픽설정|토픽설정|마피아토픽|토픽)(@[\w]+)?($|\s)'
    )
    app.add_handler(MessageHandler(_topic_cmd, topic_set_handler), group=-1)

    # ── 역할 도감 (/도감, /마피아, /경찰 등 한국어 명령) ────────
    # 그룹 + DM 모두에서 동작 / chat_guard 보다 먼저 등록(group=-1)
    _korean_cmd = filters.Regex(r'^/[가-힣a-zA-Z0-9_]')
    app.add_handler(MessageHandler(_korean_cmd, role_lookup_handler), group=-1)

    # ── 채팅 감시 (사망자·미참여자 메시지 삭제) ──────────────
    # 한국어 명령(/마피아 등)은 삭제 대상에서 제외
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL
        & ~filters.COMMAND & ~filters.Regex(r'^/[가-힣]'),
        chat_guard_handler,
    ))

    log.info("폴링 시작...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
