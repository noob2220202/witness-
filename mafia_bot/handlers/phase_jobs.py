"""
게임 페이즈 전이 엔진.
advance_phase() 가 유일한 상태 머신 진입점.
타이머 만료와 조기 진행(행동 전원 제출) 모두 이 함수를 호출한다.
"""
import logging
import os
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

# 페이즈 전환 영상 경로 (봇 실행 위치 기준)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIGHT_GIF = os.path.join(_BASE_DIR, "data", "night_transition.mp4")  # 낮→밤
DAY_GIF   = os.path.join(_BASE_DIR, "data", "day_transition.mp4")    # 밤→아침

from game.state import GameState, Phase, Faction, WinCondition
from game.roles import ROLES
from game.night_engine import resolve_night, reset_night_state
from game.vote_engine import (
    get_nominee, resolve_execution, tally_judgment, count_judgment,
    get_vote_summary,
)
from game.win_checker import check_win, check_jester_win
from messages.templates import (
    esc,
    night_start_msg, night_action_prompt, no_night_action_msg,
    day_announce_msg, day_discuss_msg, morning_status_msg,
    vote_start_msg, vote_result_msg,
    final_defense_msg, judgment_start_msg, judgment_progress_msg, judgment_result_msg,
    politician_immune_msg, magician_swap_msg,
    win_announce_msg, investigate_result_dm,
    mafia_team_msg, mafia_kill_submitted_msg,
    player_dead_dm, lover_dead_dm, reporter_announce_msg,
)
import config

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 타이머 스케줄링
# ─────────────────────────────────────────────────────────────────────────────

def schedule_phase(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    delay: int,
    tag: str,
) -> None:
    """지정된 딜레이 후 advance_phase 를 호출하는 one-shot job을 예약."""
    if context.job_queue is None:
        # JobQueue 미설치(apscheduler 누락) 시 페이즈 타이머가 동작하지 않아
        # 낮이 끝나지 않고 게임이 멈춘다. 원인을 즉시 드러낸다.
        log.error(
            "JobQueue 가 None 입니다! 페이즈 타이머(%s)를 예약할 수 없습니다. "
            "'pip install python-telegram-bot[job-queue]' (apscheduler) 설치가 필요합니다.",
            tag,
        )
        return

    job_name = f"phase_{group_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    gs = context.bot_data.get("games", {}).get(group_id)
    if gs:
        gs.phase_job = job_name

    context.job_queue.run_once(
        _phase_timeout_callback,
        when=delay,
        name=job_name,
        data={"group_id": group_id, "tag": tag},
        chat_id=group_id,
    )


def cancel_phase_job(context: ContextTypes.DEFAULT_TYPE, gs: GameState) -> None:
    """현재 등록된 페이즈 타이머 취소."""
    if gs.phase_job and context.job_queue is not None:
        for job in context.job_queue.get_jobs_by_name(gs.phase_job):
            job.schedule_removal()
    gs.phase_job = None


async def _phase_timeout_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """타이머 만료 → advance_phase 호출. 이미 진행된 경우 무시."""
    data = context.job.data
    group_id = data["group_id"]
    tag = data["tag"]

    gs = context.bot_data.get("games", {}).get(group_id)
    if gs is None or gs.phase == Phase.ENDED:
        return

    # 타이머가 예약된 페이즈와 현재 페이즈가 다르면 이미 조기 진행된 것
    expected = {
        "lobby":    Phase.LOBBY,
        "night":    Phase.NIGHT,
        "discuss":  Phase.DAY_DISCUSS,
        "vote":     Phase.VOTE,
        "defense":  Phase.FINAL_DEFENSE,
        "judgment": Phase.JUDGMENT,
        "result":   Phase.DAY_ANNOUNCE,
    }
    if tag in expected and gs.phase != expected[tag]:
        return

    await advance_phase(context, gs)


# ─────────────────────────────────────────────────────────────────────────────
# 메인 상태 머신
# ─────────────────────────────────────────────────────────────────────────────

async def advance_phase(
    context: ContextTypes.DEFAULT_TYPE,
    gs: GameState,
) -> None:
    """페이즈를 다음 단계로 전진."""
    bot: Bot = context.bot
    gid = gs.group_chat_id
    log.info("advance_phase: group=%s phase=%s day=%s", gid, gs.phase.value, gs.day_number)

    # ── LOBBY → NIGHT ──────────────────────────────────────────
    if gs.phase == Phase.LOBBY:
        await _start_night(bot, context, gs)
        return

    # ── NIGHT → DAY_ANNOUNCE ───────────────────────────────────
    if gs.phase == Phase.NIGHT:
        gs.phase = Phase.NIGHT_RESOLVE
        # resolve_night 는 '사망자 user_id 목록(list[int])'을 반환한다.
        # (사망 공지는 아래 dead_pairs / day_announce_msg 에서 처리)
        resolve_night(gs)

        # 조사 결과 DM 발송 (스파이는 마피아 팀 전체에 공유)
        for actor_id, result in gs.investigate_results.items():
            await _safe_dm(bot, actor_id, investigate_result_dm(result))
            actor = gs.players.get(actor_id)
            if actor and actor.role_key == "spy":
                spy_report = f"🕵️ *스파이 보고:*\n{result}"
                for uid, p in gs.players.items():
                    if p.is_alive and p.faction == Faction.MAFIA and uid != actor_id:
                        await _safe_dm(bot, uid, spy_report)

        # 기자 결과 공개
        for p in gs.players.values():
            if p.role_key == "reporter" and p.reporter_result and p.is_alive:
                await _send_group(gs, bot,
                    reporter_announce_msg(p.display, p.reporter_result))
                p.reporter_result = None

        # 사망자 DM
        for dead_id in gs.last_night_dead:
            dead_p = gs.players.get(dead_id)
            if dead_p:
                role = ROLES.get(dead_p.role_key)
                role_name = role.name if role else "알 수 없음"
                await _safe_dm(bot, dead_id, player_dead_dm(role_name))
                # 연인 알림
                if dead_p.lover_id and dead_p.lover_id in gs.last_night_dead:
                    partner = gs.players.get(dead_p.lover_id)
                    if partner:
                        await _safe_dm(bot, dead_p.lover_id,
                            lover_dead_dm(dead_p.display))

        # day_number 는 밤 시작 시 증가시킨다(_start_night). 여기서는 증가 X.
        # 밤 N → 낮 N 로 같은 일차를 유지해야 함.
        gs.phase = Phase.DAY_ANNOUNCE

        # 사망자 공지 빌드
        dead_pairs = []
        for uid in gs.last_night_dead:
            p = gs.players.get(uid)
            if p:
                role = ROLES.get(p.role_key)
                dead_pairs.append((p.display, role.name if role else "???"))

        await _send_transition_gif(bot, gid, DAY_GIF, gs.topic_id)
        await _send_group(gs, bot, day_announce_msg(gs, dead_pairs))

        # 승리 판정 (밤 결산 후)
        win = check_win(gs)
        if win != WinCondition.NONE:
            await _end_game(bot, context, gs, win)
            return

        schedule_phase(context, gid, config.RESULT_DELAY, "result")
        return

    # ── DAY_ANNOUNCE → DAY_DISCUSS ─────────────────────────────
    if gs.phase == Phase.DAY_ANNOUNCE:
        gs.phase = Phase.DAY_DISCUSS
        await _send_group(gs, bot, morning_status_msg(gs))
        await _send_judge_dm(bot, gs)
        schedule_phase(context, gid, gs.timers["discuss"], "discuss")
        return

    # ── DAY_DISCUSS → VOTE ─────────────────────────────────────
    if gs.phase == Phase.DAY_DISCUSS:
        gs.phase = Phase.VOTE
        alive_pairs = [(p.user_id, p.display) for p in gs.alive_players()]
        keyboard = _build_vote_keyboard(gs)
        msg = vote_start_msg(gs.day_number, gs.alive_count(), gs.timers["vote"])
        sent = await _send_group(gs, bot, msg, reply_markup=keyboard)
        if sent:
            gs.vote_msg_id = sent.message_id
        schedule_phase(context, gid, gs.timers["vote"], "vote")
        return

    # ── VOTE → FINAL_DEFENSE (지목) or 다음 밤 (지목 무산) ──────
    if gs.phase == Phase.VOTE:
        nominee_id = get_nominee(gs)
        if nominee_id is None:
            # 동점·기권 등으로 지목 무산 → 밤으로
            gs.phase = Phase.VOTE_RESOLVE
            await _send_group(gs, bot, vote_result_msg(None, None))
            await _to_next_night_or_end(bot, context, gs)
            return

        gs.accused_id = nominee_id
        gs.phase = Phase.FINAL_DEFENSE
        accused = gs.players.get(nominee_id)
        accused_name = accused.display if accused else "???"
        await _send_group(gs, bot,
            final_defense_msg(accused_name, config.FINAL_DEFENSE_TIMEOUT))
        schedule_phase(context, gid, config.FINAL_DEFENSE_TIMEOUT, "defense")
        return

    # ── FINAL_DEFENSE → JUDGMENT (찬반 투표) ───────────────────
    if gs.phase == Phase.FINAL_DEFENSE:
        accused = gs.players.get(gs.accused_id)
        if accused is None or not accused.is_alive:
            # 피고인이 사라진 예외 상황 → 밤으로
            gs.phase = Phase.VOTE_RESOLVE
            await _to_next_night_or_end(bot, context, gs)
            return
        gs.phase = Phase.JUDGMENT
        gs.judgment_votes = {}
        keyboard = _build_judgment_keyboard(gs)
        sent = await _send_group(gs, bot,
            judgment_start_msg(accused.display, config.JUDGMENT_TIMEOUT),
            reply_markup=keyboard)
        if sent:
            gs.vote_msg_id = sent.message_id
        schedule_phase(context, gid, config.JUDGMENT_TIMEOUT, "judgment")
        return

    # ── JUDGMENT → VOTE_RESOLVE → 다음 밤 or 종료 ──────────────
    if gs.phase == Phase.JUDGMENT:
        gs.phase = Phase.VOTE_RESOLVE
        accused_id = gs.accused_id
        gs.accused_id = None
        accused_p = gs.players.get(accused_id)
        accused_name = accused_p.display if accused_p else "???"
        approve, reject = count_judgment(gs)
        execute = tally_judgment(gs)

        if not execute:
            # 처형 부결 → 생존
            await _send_group(gs, bot,
                judgment_result_msg(accused_name, False, approve, reject))
            await _to_next_night_or_end(bot, context, gs)
            return

        # 처형 가결 → 보호(정치인·판사무죄·마술사) 적용
        actual_id = resolve_execution(gs, accused_id)
        if actual_id is None:
            await _send_group(gs, bot,
                judgment_result_msg(accused_name, True, approve, reject))
            if accused_p and accused_p.role_key == "politician":
                await _send_group(gs, bot, politician_immune_msg(accused_name))
            else:
                await _send_group(gs, bot,
                    f"🛡️ *{esc(accused_name)}* 은\\(는\\) 보호 효과로 처형을 면했습니다\\.")
            await _to_next_night_or_end(bot, context, gs)
            return

        await _send_group(gs, bot,
            judgment_result_msg(accused_name, True, approve, reject))
        if actual_id != accused_id:
            await _send_group(gs, bot, magician_swap_msg())
        await _execute_player(bot, context, gs, actual_id)
        return


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

async def _start_night(
    bot: Bot,
    context: ContextTypes.DEFAULT_TYPE,
    gs: GameState,
) -> None:
    """밤 페이즈 시작: 일차 증가 → 과학자 부활 → 영상 → 메시지 → 행동 DM 전송 → 타이머 예약."""
    gs.phase = Phase.NIGHT
    gs.day_number += 1   # 첫 밤은 begin_handler 에서 day=1 로 직접 설정하므로 _start_night 미경유
    gid = gs.group_chat_id

    # 과학자 부활 처리
    for uid, p in list(gs.players.items()):
        if p.scientist_revival:
            p.is_alive = True
            p.scientist_revival = False
            if uid in gs.dead_players:
                gs.dead_players.remove(uid)
            await _send_group(gs, bot,
                f"🧪 *과학자 부활\\!* *{esc(p.display)}* 이\\(가\\) 기적적으로 되살아났습니다\\!")
            await _safe_dm(bot, uid,
                "🧪 당신은 *과학자의 기술*로 __부활__했습니다\\! 게임에 복귀합니다\\.")

    await _send_transition_gif(bot, gid, NIGHT_GIF, gs.topic_id)
    await _send_group(gs, bot,
        night_start_msg(gs.day_number, gs.alive_count()))

    # 역할 배정 DM 은 게임 시작(begin) 시 1회만 전송한다.
    # 매 밤 재전송하면 사망자에게도 "직업이 배정되었습니다" 가 날아가므로 호출하지 않는다.
    await send_night_action_dms(bot, gs)

    schedule_phase(context, gid, gs.timers["night"], "night")


async def send_role_dms(bot: Bot, gs: GameState) -> None:
    """역할 배정 직후 각 플레이어에게 역할 DM 전송 (게임 시작 시 1회)."""
    from messages.templates import role_assignment_msg

    mafia_names = [p.display for p in gs.players.values()
                   if p.faction == Faction.MAFIA and p.is_alive]

    for uid, player in gs.players.items():
        if not player.is_alive:
            continue
        role = ROLES.get(player.role_key)
        if not role:
            continue
        allies = mafia_names if player.faction == Faction.MAFIA else None
        lover_name = None
        if player.lover_id:
            partner = gs.players.get(player.lover_id)
            lover_name = partner.display if partner else None

        msg = role_assignment_msg(player, role, allies, lover_name)
        await _safe_dm(bot, uid, msg)

    # 마피아 팀 채팅 (팀 구성 알림)
    mafia_ids = [uid for uid, p in gs.players.items()
                 if p.faction == Faction.MAFIA and p.is_alive]
    if mafia_ids:
        team_msg = mafia_team_msg(mafia_names)
        for uid in mafia_ids:
            await _safe_dm(bot, uid, team_msg)


async def send_night_action_dms(bot: Bot, gs: GameState) -> None:
    """각 생존 플레이어에게 밤 행동 버튼 DM 전송."""
    for uid, player in gs.players.items():
        if not player.is_alive:
            continue
        role = ROLES.get(player.role_key)
        if not role:
            continue

        if not role.night_action:
            # 밤 행동 없는 직업: 매 밤 DM 보내지 않음(직업 카드 도배 방지).
            # 진행을 위해 제출 완료 처리만 한다.
            player.night_action_submitted = True
            continue

        prompt = night_action_prompt(role)
        keyboard = _build_night_keyboard(gs, player, role)

        if keyboard is None:
            # 도굴꾼: 죽은 자가 없으면 행동 불가
            await _safe_dm(bot, uid,
                f"⚰️ 오늘 밤 사용할 수 있는 대상이 없습니다\\.\n"
                f"_밤 행동이 건너뜁니다\\._")
            player.night_action_submitted = True
            continue

        await _safe_dm(bot, uid, prompt, reply_markup=keyboard)


def _build_night_keyboard(gs: GameState, player, role) -> InlineKeyboardMarkup | None:
    """역할에 맞는 밤 행동 InlineKeyboard 생성."""
    gid = gs.group_chat_id
    action = role.night_action
    alive = gs.alive_players()
    dead = [gs.players[uid] for uid in gs.dead_players if uid in gs.players]

    candidates = []

    if action in ("KILL", "KILL_UNSTOPPABLE", "KILL_TARGETED"):
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "PROTECT":
        if role.can_self:
            candidates = alive[:]
        else:
            candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "ROLEBLOCK":
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "FROG_TRANSFORM":
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action in ("INVESTIGATE_MAFIA", "INVESTIGATE_ROLE", "INVESTIGATE_CULT"):
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "CULT_CONVERT":
        candidates = [p for p in alive
                      if p.user_id != player.user_id
                      and p.faction != Faction.MAFIA]
    elif action == "REVIVE":
        candidates = dead
        if not candidates:
            return None
    elif action == "SEANCE":
        candidates = dead
    elif action == "TRACK":
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "STEAL_ROLE":
        # 도굴꾼: 이번 밤 사망할 가능성이 있는 생존자 선택 (밤 결산 시 실제 사망자만 적용)
        candidates = [p for p in alive if p.user_id != player.user_id]
        if not candidates:
            return None
    elif action == "STEAL_ABILITY":
        candidates = [p for p in alive
                      if p.faction == Faction.CITIZEN
                      and p.user_id != player.user_id]
    elif action == "SWAP_PREPARE":
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "COMPARE":
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "DISARM":
        candidates = [p for p in alive if p.user_id != player.user_id]
    elif action == "DISGUISE":
        # 사기꾼: 직업명 선택 (다른 플레이어 직업 목록)
        role_names = list({ROLES[p.role_key].name for p in alive
                           if p.user_id != player.user_id and p.role_key in ROLES})
        buttons = [
            [InlineKeyboardButton(
                name,
                callback_data=f"disguise:{gid}:{esc_cb(name)}"
            )]
            for name in role_names[:20]
        ]
        return InlineKeyboardMarkup(buttons) if buttons else None
    else:
        return None

    if not candidates:
        return None

    buttons = []
    for c in candidates:
        cb = f"night_target:{gid}:{c.user_id}"
        buttons.append([InlineKeyboardButton(c.display, callback_data=cb)])

    return InlineKeyboardMarkup(buttons)


async def _send_judge_dm(bot: Bot, gs: GameState) -> None:
    """낮 토론 시작 시 판사에게 능력 사용 키보드 DM 전송."""
    gid = gs.group_chat_id
    for uid, p in gs.players.items():
        if not p.is_alive or p.role_key != "judge":
            continue
        if p.shots_remaining == 0:
            continue  # 이미 사용함
        targets = [t for t in gs.alive_players() if t.user_id != uid]
        if not targets:
            continue
        rows = []
        for t in targets:
            rows.append([
                InlineKeyboardButton(
                    f"⚖️ 처형: {t.display}",
                    callback_data=f"judge:{gid}:execute:{t.user_id}",
                ),
                InlineKeyboardButton(
                    f"🛡️ 무죄: {t.display}",
                    callback_data=f"judge:{gid}:spare:{t.user_id}",
                ),
            ])
        rows.append([
            InlineKeyboardButton("❌ 이번 낮 사용 안 함", callback_data=f"judge:{gid}:skip:0")
        ])
        keyboard = InlineKeyboardMarkup(rows)
        await _safe_dm(
            bot, uid,
            "⚖️ *판사 능력*\n\n"
            "정체를 공개하고 능력을 사용할 수 있습니다\\. \\(1회\\)\n\n"
            "• *처형* — 즉시 대상을 처형합니다\n"
            "• *무죄* — 이번 낮 투표 처형에서 대상을 면제합니다\n\n"
            "> ⚠️ 사용 즉시 그룹에 정체가 공개됩니다\\.",
            reply_markup=keyboard,
        )


def _build_night_target2_keyboard(
    gs: GameState, player, first_target_id: int
) -> InlineKeyboardMarkup | None:
    """심리학자 두 번째 대상 선택 키보드. 자기 자신·첫 번째 대상 제외."""
    gid = gs.group_chat_id
    candidates = [
        p for p in gs.alive_players()
        if p.user_id != player.user_id and p.user_id != first_target_id
    ]
    if not candidates:
        return None
    buttons = [
        [InlineKeyboardButton(c.display, callback_data=f"night_target2:{gid}:{c.user_id}")]
        for c in candidates
    ]
    return InlineKeyboardMarkup(buttons)


def _build_vote_keyboard(gs: GameState) -> InlineKeyboardMarkup:
    gid = gs.group_chat_id
    buttons = []
    for p in gs.alive_players():
        cb = f"vote:{gid}:{p.user_id}"
        buttons.append([InlineKeyboardButton(p.display, callback_data=cb)])
    buttons.append([InlineKeyboardButton("🚫 기권", callback_data=f"vote:{gid}:0")])
    return InlineKeyboardMarkup(buttons)


def _build_judgment_keyboard(gs: GameState) -> InlineKeyboardMarkup:
    """찬반(업다운) 투표 키보드. 👍 찬성(처형) / 👎 반대(생존)."""
    gid = gs.group_chat_id
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👍 찬성 (처형)", callback_data=f"trial:{gid}:up"),
        InlineKeyboardButton("👎 반대 (생존)", callback_data=f"trial:{gid}:down"),
    ]])


async def _to_next_night_or_end(
    bot: Bot,
    context: ContextTypes.DEFAULT_TYPE,
    gs: GameState,
) -> None:
    """낮 결산 후 승리 판정 → 게임 종료 또는 다음 밤으로."""
    win = check_win(gs)
    if win != WinCondition.NONE:
        await _end_game(bot, context, gs, win)
        return
    reset_night_state(gs)
    await _start_night(bot, context, gs)


async def _execute_player(
    bot: Bot,
    context: ContextTypes.DEFAULT_TYPE,
    gs: GameState,
    executed_id: int,
) -> None:
    """투표 처형 확정 대상 처리: 어릿광대 승리·과학자 부활·연인 동반사망 포함."""
    executed_p = gs.players.get(executed_id)
    if executed_p is None:
        await _to_next_night_or_end(bot, context, gs)
        return

    role = ROLES.get(executed_p.role_key)
    role_name = role.name if role else "???"

    # 어릿광대 처형 승리 체크
    if check_jester_win(gs, executed_id):
        executed_p.is_alive = False
        if executed_id not in gs.dead_players:
            gs.dead_players.append(executed_id)
        await _send_group(gs, bot, vote_result_msg(executed_p.display, role_name))
        await _end_game(bot, context, gs, WinCondition.JESTER)
        return

    executed_p.is_alive = False
    if executed_id not in gs.dead_players:
        gs.dead_players.append(executed_id)
    gs.last_vote_dead = executed_id

    # 과학자 부활 예약 (투표 처형 시)
    if executed_p.role_key == "scientist" and executed_p.shots_remaining == 1:
        executed_p.shots_remaining = 0
        executed_p.scientist_revival = True

    await _send_group(gs, bot, vote_result_msg(executed_p.display, role_name))
    await _safe_dm(bot, executed_id, player_dead_dm(role_name))

    # 연인 동반 사망
    if executed_p.lover_id:
        partner = gs.players.get(executed_p.lover_id)
        if partner and partner.is_alive:
            partner.is_alive = False
            if partner.user_id not in gs.dead_players:
                gs.dead_players.append(partner.user_id)
            partner_role = ROLES.get(partner.role_key)
            await _send_group(gs, bot,
                f"💔 *{esc(partner.display)}* 도 연인을 잃고 함께 사망했습니다\\.\n"
                f"직업: __{esc(partner_role.name if partner_role else '???')}__")
            await _safe_dm(bot, partner.user_id, lover_dead_dm(executed_p.display))

    await _to_next_night_or_end(bot, context, gs)


async def _end_game(
    bot: Bot,
    context: ContextTypes.DEFAULT_TYPE,
    gs: GameState,
    win_cond: WinCondition,
) -> None:
    """게임 종료: 승리 공지 + 상태 정리."""
    cancel_phase_job(context, gs)
    gs.phase = Phase.ENDED
    await _send_group(gs, bot, win_announce_msg(win_cond, gs))

    games: dict = context.bot_data.get("games", {})
    games.pop(gs.group_chat_id, None)


def all_night_actions_submitted(gs: GameState) -> bool:
    """살아있는 행동 가능 플레이어 전원이 행동을 제출했는지 확인."""
    for player in gs.alive_players():
        role = ROLES.get(player.role_key)
        if role and role.night_action and not player.night_action_submitted:
            return False
    return True


def all_votes_submitted(gs: GameState) -> bool:
    """살아있는 전원이 투표했는지 확인."""
    return all(p.has_voted for p in gs.alive_players())


def judgment_eligible_ids(gs: GameState) -> list[int]:
    """찬반 투표 가능한 유권자 목록 (피고인·개구리·투표권 0 제외)."""
    return [
        p.user_id for p in gs.alive_players()
        if p.user_id != gs.accused_id and not p.is_frogged and p.vote_weight > 0
    ]


def all_judgment_voted(gs: GameState) -> bool:
    """찬반 투표 가능한 전원이 투표했는지 확인."""
    eligible = judgment_eligible_ids(gs)
    if not eligible:
        return True
    return all(uid in gs.judgment_votes for uid in eligible)


# ─────────────────────────────────────────────────────────────────────────────
# 전송 유틸
# ─────────────────────────────────────────────────────────────────────────────

async def _safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    """그룹/개인 메시지 전송. 실패해도 게임 진행.

    ``message_thread_id`` 를 kwargs 로 넘기면 해당 토픽(포럼 스레드)으로 전송한다.
    값이 None 이면 일반 그룹/General 토픽으로 전송된다.
    """
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            **kwargs,
        )
    except Exception as e:
        # MarkdownV2 파싱 오류 등으로 실패하면 메시지가 조용히 사라진다.
        # (예: 아침 직업 리스트가 안 뜨는 증상) → 일반 텍스트로 재시도.
        log.warning("MarkdownV2 전송 실패 chat_id=%s: %s — 일반 텍스트로 재시도", chat_id, e)
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=_strip_md(text),
                **kwargs,
            )
        except Exception as e2:
            log.warning("일반 텍스트 전송도 실패 chat_id=%s: %s", chat_id, e2)
            return None


def _strip_md(text: str) -> str:
    """MarkdownV2 전송 실패 시 사용할 일반 텍스트로 변환.
    이스케이프 백슬래시(\\x)를 풀고, 강조 기호(*, _, ~, `, |)를 제거한다."""
    import re
    # \x → x (이스케이프된 특수문자 복원)
    out = re.sub(r'\\([_*\[\]()~`>#+\-=|{}.!\\])', r'\1', text)
    # 남은 강조 기호 제거
    out = out.replace("*", "").replace("`", "").replace("|", "")
    out = out.replace("__", "").replace("~", "")
    return out


async def _send_group(gs: GameState, bot: Bot, text: str, **kwargs):
    """게임이 묶여 있는 그룹(+토픽)으로 메시지 전송."""
    return await _safe_send(
        bot, gs.group_chat_id, text,
        message_thread_id=gs.topic_id,
        **kwargs,
    )


async def _safe_dm(bot: Bot, user_id: int, text: str, **kwargs):
    """DM 전송. DM 미개통 시 무시. MarkdownV2 실패 시 일반 텍스트로 재시도."""
    try:
        return await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            **kwargs,
        )
    except Exception as e:
        # MarkdownV2 파싱 오류로 실패하면 reply_markup(밤 행동 버튼)까지 통째로 사라진다.
        # → 일반 텍스트로 재시도해서 버튼이라도 살린다.
        log.warning("DM MarkdownV2 실패 user_id=%s: %s — 일반 텍스트로 재시도", user_id, e)
        try:
            return await bot.send_message(
                chat_id=user_id,
                text=_strip_md(text),
                **kwargs,
            )
        except Exception as e2:
            log.warning("DM 전송 실패 user_id=%s: %s", user_id, e2)
            return None


def esc_cb(text: str) -> str:
    """callback_data 용 간단 이스케이프 (콜론 제거)."""
    return text.replace(":", "_").replace(" ", "_")


async def _send_transition_gif(
    bot: Bot, chat_id: int, path: str, message_thread_id=None
) -> None:
    """페이즈 전환 영상(mp4)을 GIF 애니메이션으로 전송. 파일 없으면 무시."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            await bot.send_animation(
                chat_id=chat_id,
                animation=f,
                message_thread_id=message_thread_id,
            )
    except Exception as e:
        log.warning("전환 영상 전송 실패 chat_id=%s: %s", chat_id, e)
