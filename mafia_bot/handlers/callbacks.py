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
    all_night_actions_submitted, all_votes_submitted,
    _safe_dm, _safe_send,
    _build_vote_keyboard,
)
from messages.templates import (
    esc, lobby_msg,
    mafia_kill_submitted_msg,
)
from game.vote_engine import get_vote_summary
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

        elif action == "disguise" and len(parts) >= 3:
            await handle_disguise(query, context, int(parts[1]), parts[2])

        elif action == "vote" and len(parts) >= 3:
            await handle_vote(query, context, int(parts[1]), int(parts[2]))

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
        await query.answer("❌ 밤 행동 단계가 아닙니다.", show_alert=True)
        return

    actor = gs.players.get(actor_id)
    if not actor or not actor.is_alive:
        await query.answer("❌ 게임 참가자가 아니거나 이미 사망했습니다.", show_alert=True)
        return
    if actor.night_action_submitted:
        await query.answer("ℹ️ 이미 행동을 제출했습니다.", show_alert=True)
        return

    role = ROLES.get(actor.role_key)
    if not role or not role.night_action:
        await query.answer("❌ 밤 행동이 없는 직업입니다.", show_alert=True)
        return

    # 마피아: 첫 번째 제출이 팀 전체 행동
    if actor.faction == Faction.MAFIA and role.night_action in ("KILL", "KILL_UNSTOPPABLE", "KILL_TARGETED"):
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
        await _safe_send(
            context.bot, group_id,
            f"⚖️ *판사의 직권 처형\\!*\n\n"
            f"*{esc(target.display)}* 이\\(가\\) 판사에 의해 처형되었습니다\\.\n"
            f"직업: __{esc(role_name)}__"
        )
        await query.answer("처형 완료.")
    elif action == "spare":
        target.politician_immune = True
        await _safe_send(
            context.bot, group_id,
            f"⚖️ *판사의 무죄 선언\\!*\n\n"
            f"*{esc(target.display)}* 이\\(가\\) 이번 낮 처형에서 면제됩니다\\."
        )
        await query.answer("무죄 선언 완료.")

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
