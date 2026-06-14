"""
모든 InlineKeyboard CallbackQuery 라우터.

callback_data 형식:
  join:<group_id>
  night_target:<group_id>:<target_id>
  disguise:<group_id>:<role_name>
  vote:<group_id>:<target_id>        (0 = 기권)
  judge:<group_id>:<action>:<target_id>
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game.state import Phase, Faction, WinCondition, PlayerState
from game.roles import ROLES
from handlers.phase_jobs import (
    advance_phase, cancel_phase_job,
    all_night_actions_submitted, all_votes_submitted, all_judgment_voted,
    _safe_dm, _safe_send,
    _build_vote_keyboard, _build_judgment_keyboard,
    _build_night_target2_keyboard,
)
from messages.templates import (
    esc, lobby_msg,
    mafia_kill_submitted_msg, judgment_progress_msg,
)
from game.vote_engine import get_vote_summary, count_judgment
import config

log = logging.getLogger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")

    if not parts:
        return

    action = parts[0]

    try:
        if action == "join" and len(parts) >= 2:
            await handle_join(query, context, int(parts[1]))

        elif action == "night_target" and len(parts) >= 3:
            await handle_night_target(query, context, int(parts[1]), int(parts[2]))

        elif action == "night_target2" and len(parts) >= 3:
            await handle_night_target2(query, context, int(parts[1]), int(parts[2]))

        elif action == "disguise" and len(parts) >= 3:
            await handle_disguise(query, context, int(parts[1]), parts[2])

        elif action == "vote" and len(parts) >= 3:
            await handle_vote(query, context, int(parts[1]), int(parts[2]))

        elif action == "trial" and len(parts) >= 3:
            await handle_trial_vote(query, context, int(parts[1]), parts[2])

        elif action == "judge" and len(parts) >= 4:
            await handle_judge(query, context, int(parts[1]), parts[2], int(parts[3]))

    except (ValueError, IndexError) as e:
        log.warning("callback 파싱 오류: %s — %s", data, e)


# ─────────────────────────────────────────────────────────────────────────────
# 참가
# ─────────────────────────────────────────────────────────────────────────────

async def handle_join(query, context: ContextTypes.DEFAULT_TYPE, group_id: int) -> None:
    user = query.from_user
    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None:
        await query.answer("❌ 진행 중인 게임이 없습니다.", show_alert=True)
        return
    if gs.phase != Phase.LOBBY:
        await query.answer("❌ 게임이 이미 시작되었습니다.", show_alert=True)
        return
    if user.id in gs.players:
        await query.answer("ℹ️ 이미 참가 중입니다.", show_alert=True)
        return
    if len(gs.players) >= config.MAX_PLAYERS:
        await query.answer(f"❌ 게임이 가득 찼습니다 (최대 {config.MAX_PLAYERS}명).",
                           show_alert=True)
        return

    # DM 개통 확인
    dm_capable: set = context.bot_data.get("dm_capable", set())
    if user.id not in dm_capable:
        from handlers.dm_cmd import make_dm_link
        dm_link = make_dm_link(group_id)
        await query.answer(
            f"먼저 봇에게 DM을 보내주세요!\n{dm_link}",
            show_alert=True,
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

    await query.answer(f"✅ 참가 완료! ({len(gs.players)}/{config.MAX_PLAYERS}명)")

    # 로비 메시지 갱신
    from handlers.dm_cmd import _build_lobby_keyboard
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
# 밤 행동
# ─────────────────────────────────────────────────────────────────────────────

async def handle_night_target(
    query, context: ContextTypes.DEFAULT_TYPE,
    group_id: int, target_id: int,
) -> None:
    actor_id = query.from_user.id
    games: dict = context.bot_data.get("games", {})
    gs = games.get(group_id)

    if gs is None or gs.phase != Phase.NIGHT:
        cur = gs.phase.value if gs else "no-game"
        log.info("밤행동 거부: actor=%s phase=%s(기대 night) target=%s", actor_id, cur, target_id)
        await query.answer("❌ 밤 행동 단계가 아닙니다.", show_alert=True)
        return

    actor = gs.players.get(actor_id)
    if not actor or not actor.is_alive:
        log.info("밤행동 거부: actor=%s 참가자아님/사망", actor_id)
        await query.answer("❌ 게임 참가자가 아니거나 이미 사망했습니다.", show_alert=True)
        return
    if actor.night_action_submitted:
        log.info("밤행동 거부: actor=%s 이미제출(submitted=True) role=%s", actor_id, actor.role_key)
        await query.answer("ℹ️ 이미 행동을 제출했습니다.", show_alert=True)
        return

    role = ROLES.get(actor.role_key)
    if not role or not role.night_action:
        await query.answer("❌ 밤 행동이 없는 직업입니다.", show_alert=True)
        return

    # ── 심리학자 2단계 처리 ──────────────────────────────────────
    if role.night_action == "COMPARE":
        if actor.night_target is None:
            # 1단계: 첫 번째 대상 저장 후 2단계 키보드 전송
            target_p = gs.players.get(target_id)
            if not target_p or not target_p.is_alive:
                await query.answer("❌ 올바른 대상이 아닙니다.", show_alert=True)
                return
            actor.night_target = target_id
            keyboard2 = _build_night_target2_keyboard(gs, actor, target_id)
            if keyboard2:
                await _safe_dm(
                    context.bot, actor_id,
                    f"🧠 *1번째 대상:* _{esc(target_p.display)}_\n\n두 번째 비교 대상을 선택하세요\\:",
                    reply_markup=keyboard2,
                )
            else:
                # 비교 가능한 두 번째 대상 없음 — 스킵
                actor.compare_target = None
                actor.night_action_submitted = True
                gs.night_actions[actor_id] = target_id
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await query.answer("첫 번째 대상을 선택했습니다.")
            if all_night_actions_submitted(gs):
                cancel_phase_job(context, gs)
                await advance_phase(context, gs)
        else:
            await query.answer("ℹ️ 두 번째 대상을 DM에서 선택해주세요.", show_alert=True)
        return

    # 마피아 기본 공격 (마피오소/대부만 팀 협조, 짐승인간/청부업자는 독립 행동)
    if actor.faction == Faction.MAFIA and role.night_action == "KILL":
        if gs.mafia_kill_submitted_by is not None:
            await query.answer("ℹ️ 이미 팀원이 목표를 선택했습니다.", show_alert=True)
            return
        target_p = gs.players.get(target_id)
        if not target_p:
            await query.answer("❌ 올바른 대상이 아닙니다.", show_alert=True)
            return
        gs.mafia_kill_submitted_by = actor_id
        # 모든 마피아 제출 처리
        for uid, p in gs.players.items():
            if p.faction == Faction.MAFIA and p.is_alive:
                gs.night_actions[uid] = target_id
                p.night_action_submitted = True

        # 마피아 팀 전체에 선택 알림
        for uid, p in gs.players.items():
            if p.faction == Faction.MAFIA and p.is_alive:
                await _safe_dm(
                    context.bot, uid,
                    mafia_kill_submitted_msg(actor.display, target_p.display)
                )
    else:
        gs.night_actions[actor_id] = target_id
        actor.night_action_submitted = True
        actor.night_target = target_id

    # 키보드 제거
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await query.answer("✅ 행동이 기록되었습니다.")

    # 전원 제출 시 조기 진행
    if all_night_actions_submitted(gs):
        cancel_phase_job(context, gs)
        await advance_phase(context, gs)


async def handle_night_target2(
    query, context: ContextTypes.DEFAULT_TYPE,
    group_id: int, target_id: int,
) -> None:
    """심리학자 두 번째 비교 대상 처리."""
    actor_id = query.from_user.id
    gs = context.bot_data.get("games", {}).get(group_id)

    if gs is None or gs.phase != Phase.NIGHT:
        await query.answer("❌ 밤 행동 단계가 아닙니다.", show_alert=True)
        return

    actor = gs.players.get(actor_id)
    if not actor or not actor.is_alive:
        await query.answer("❌ 게임 참가자가 아닙니다.", show_alert=True)
        return
    if actor.night_action_submitted:
        await query.answer("ℹ️ 이미 행동을 제출했습니다.", show_alert=True)
        return

    role = ROLES.get(actor.role_key)
    if not role or role.night_action != "COMPARE":
        await query.answer("❌ 심리학자 전용입니다.", show_alert=True)
        return

    target_p = gs.players.get(target_id)
    if not target_p or not target_p.is_alive:
        await query.answer("❌ 올바른 대상이 아닙니다.", show_alert=True)
        return

    actor.compare_target = target_id
    actor.night_action_submitted = True
    gs.night_actions[actor_id] = actor.night_target  # 첫 번째 대상을 메인 타겟으로

    first_p = gs.players.get(actor.night_target)
    first_name = first_p.display if first_p else "???"

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await query.answer("✅ 두 번째 대상 선택 완료.")
    await _safe_dm(
        context.bot, actor_id,
        f"🧠 비교 중\\: *{esc(first_name)}* vs *{esc(target_p.display)}*\n결과는 밤이 끝나면 알려드립니다\\.",
    )

    if all_night_actions_submitted(gs):
        cancel_phase_job(context, gs)
        await advance_phase(context, gs)


async def handle_disguise(
    query, context: ContextTypes.DEFAULT_TYPE,
    group_id: int, role_name: str,
) -> None:
    """사기꾼 위장 직업 선택."""
    actor_id = query.from_user.id
    gs = context.bot_data.get("games", {}).get(group_id)
    if gs is None or gs.phase != Phase.NIGHT:
        await query.answer("❌ 밤 행동 단계가 아닙니다.", show_alert=True)
        return

    actor = gs.players.get(actor_id)
    if not actor or actor.role_key != "fraud":
        await query.answer("❌ 권한이 없습니다.", show_alert=True)
        return
    if actor.night_action_submitted:
        await query.answer("ℹ️ 이미 위장 직업을 선택했습니다.", show_alert=True)
        return

    actor.disguise_role = role_name.replace("_", " ")
    actor.night_action_submitted = True
    gs.night_actions[actor_id] = actor_id  # 자기 자신 대상 (위장은 패시브)

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    await query.answer(f"✅ '{actor.disguise_role}' 으로 위장합니다.")

    if all_night_actions_submitted(gs):
        cancel_phase_job(context, gs)
        await advance_phase(context, gs)


# ─────────────────────────────────────────────────────────────────────────────
# 투표
# ─────────────────────────────────────────────────────────────────────────────

async def handle_vote(
    query, context: ContextTypes.DEFAULT_TYPE,
    group_id: int, target_id: int,
) -> None:
    voter_id = query.from_user.id
    gs = context.bot_data.get("games", {}).get(group_id)

    if gs is None or gs.phase != Phase.VOTE:
        await query.answer("❌ 투표 단계가 아닙니다.", show_alert=True)
        return

    voter = gs.players.get(voter_id)
    if not voter or not voter.is_alive:
        await query.answer("❌ 투표 자격이 없습니다.", show_alert=True)
        return
    if voter.is_frogged or voter.vote_weight <= 0:
        await query.answer("❌ 투표권이 없는 상태입니다.", show_alert=True)
        return
    if voter.has_voted:
        await query.answer("ℹ️ 이미 투표했습니다.", show_alert=True)
        return

    voter.has_voted = True
    if target_id == 0:
        # 기권
        voter.vote_target = None
        await query.answer("🚫 기권했습니다.")
    else:
        target = gs.players.get(target_id)
        if not target or not target.is_alive:
            await query.answer("❌ 올바른 투표 대상이 아닙니다.", show_alert=True)
            voter.has_voted = False
            return
        voter.vote_target = target_id
        gs.votes[voter_id] = target_id
        await query.answer(f"✅ {target.display} 에게 투표했습니다.")

    # 투표 현황 메시지 갱신
    alive_cnt = gs.alive_count()
    voted_cnt = sum(1 for p in gs.alive_players() if p.has_voted)

    try:
        summary = get_vote_summary(gs)
        new_text = (
            f"🗳️ *낮 {esc(str(gs.day_number))} 투표 중\\.\\.\\.*\n\n"
            f"{summary}\n\n"
            f"*{esc(str(voted_cnt))}/{esc(str(alive_cnt))}명* 투표 완료"
        )
        await context.bot.edit_message_text(
            chat_id=group_id,
            message_id=gs.vote_msg_id,
            text=new_text,
            reply_markup=_build_vote_keyboard(gs),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        pass

    # 전원 투표 시 조기 진행
    if all_votes_submitted(gs):
        cancel_phase_job(context, gs)
        await advance_phase(context, gs)


# ─────────────────────────────────────────────────────────────────────────────
# 찬반(업다운) 투표 — 최종변론 후 처형 여부 결정
# ─────────────────────────────────────────────────────────────────────────────

async def handle_trial_vote(
    query, context: ContextTypes.DEFAULT_TYPE,
    group_id: int, vote_str: str,
) -> None:
    voter_id = query.from_user.id
    gs = context.bot_data.get("games", {}).get(group_id)

    if gs is None or gs.phase != Phase.JUDGMENT:
        await query.answer("❌ 찬반 투표 단계가 아닙니다.", show_alert=True)
        return

    voter = gs.players.get(voter_id)
    if not voter or not voter.is_alive:
        await query.answer("❌ 투표 자격이 없습니다.", show_alert=True)
        return
    if voter_id == gs.accused_id:
        await query.answer("❌ 피고인은 찬반 투표에 참여할 수 없습니다.", show_alert=True)
        return
    if voter.is_frogged or voter.vote_weight <= 0:
        await query.answer("❌ 투표권이 없는 상태입니다.", show_alert=True)
        return
    if voter_id in gs.judgment_votes:
        await query.answer("ℹ️ 이미 투표했습니다.", show_alert=True)
        return

    approve_vote = (vote_str == "up")
    gs.judgment_votes[voter_id] = approve_vote
    await query.answer("👍 찬성 (처형)" if approve_vote else "👎 반대 (생존)")

    # 진행 현황 갱신
    accused = gs.players.get(gs.accused_id)
    accused_name = accused.display if accused else "???"
    approve, reject = count_judgment(gs)
    total = len([
        p for p in gs.alive_players()
        if p.user_id != gs.accused_id and not p.is_frogged and p.vote_weight > 0
    ])
    voted = len(gs.judgment_votes)
    try:
        await context.bot.edit_message_text(
            chat_id=group_id,
            message_id=gs.vote_msg_id,
            text=judgment_progress_msg(accused_name, approve, reject, voted, total),
            reply_markup=_build_judgment_keyboard(gs),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        pass

    # 전원 투표 시 조기 진행
    if all_judgment_voted(gs):
        cancel_phase_job(context, gs)
        await advance_phase(context, gs)


# ─────────────────────────────────────────────────────────────────────────────
# 판사 특수 행동
# ─────────────────────────────────────────────────────────────────────────────

async def handle_judge(
    query, context: ContextTypes.DEFAULT_TYPE,
    group_id: int, action: str, target_id: int,
) -> None:
    judge_id = query.from_user.id
    gs = context.bot_data.get("games", {}).get(group_id)
    if gs is None:
        return

    judge = gs.players.get(judge_id)
    if not judge or judge.role_key != "judge" or not judge.is_alive:
        await query.answer("❌ 판사 권한이 없습니다.", show_alert=True)
        return
    if judge.shots_remaining == 0:
        await query.answer("❌ 이미 권한을 사용했습니다.", show_alert=True)
        return

    # 사용 안 함
    if action == "skip":
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.answer("이번 낮 사용하지 않습니다.")
        return

    # 낮 단계 확인 (토론 or 투표 중에만)
    if gs.phase not in (Phase.DAY_DISCUSS, Phase.VOTE):
        await query.answer("❌ 낮 토론/투표 단계에서만 사용 가능합니다.", show_alert=True)
        return

    target = gs.players.get(target_id)
    if not target or not target.is_alive:
        await query.answer("❌ 올바른 대상이 아닙니다.", show_alert=True)
        return

    judge.is_revealed = True
    judge.shots_remaining = 0

    if action == "execute":
        role = ROLES.get(target.role_key)
        role_name = role.name if role else "???"
        target.is_alive = False
        if target_id not in gs.dead_players:
            gs.dead_players.append(target_id)
        gs.last_vote_dead = target_id
        # 과학자 부활 예약 (판사 처형 시)
        if target.role_key == "scientist" and target.shots_remaining == 1:
            target.shots_remaining = 0
            target.scientist_revival = True
        await _safe_send(
            context.bot, group_id,
            f"⚖️ *판사의 직권 처형\\!*\n\n"
            f"*{esc(judge.display)}* 이\\(가\\) 정체를 공개하고 직권 처형을 선언했습니다\\.\n\n"
            f"💀 *{esc(target.display)}* — 직업: __{esc(role_name)}__",
            message_thread_id=gs.topic_id,
        )
        await _safe_dm(context.bot, target_id,
            f"⚖️ 판사의 직권 처형으로 사망했습니다\\.\n직업: __{esc(role_name)}__")
        await query.answer("✅ 직권 처형 완료.")
    elif action == "spare":
        target.spared_this_round = True
        await _safe_send(
            context.bot, group_id,
            f"⚖️ *판사의 무죄 선언\\!*\n\n"
            f"*{esc(judge.display)}* 이\\(가\\) 정체를 공개하고 무죄를 선언했습니다\\.\n\n"
            f"🛡️ *{esc(target.display)}* 은\\(는\\) 이번 낮 투표 처형에서 면제됩니다\\.",
            message_thread_id=gs.topic_id,
        )
        await query.answer("✅ 무죄 선언 완료.")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
