from typing import Optional
from game.state import GameState, PlayerState, Faction, WinCondition
from game.roles import ROLES


def resolve_night(gs: GameState) -> list[int]:
    """
    밤 행동 결산.
    반환: 이번 밤 사망자 user_id 목록
    """
    actions = {k: v for k, v in gs.night_actions.items()}

    def get_priority(actor_id: int) -> int:
        p = gs.players.get(actor_id)
        if not p or not p.is_alive:
            return -1
        return ROLES.get(p.role_key, ROLES["mafioso"]).priority

    sorted_actors = sorted(
        [aid for aid in actions if gs.players.get(aid) and gs.players[aid].is_alive],
        key=get_priority,
        reverse=True,
    )

    to_kill: dict[int, int] = {}
    unstoppable_kills: set[int] = set()

    # ── 10: FROG_TRANSFORM (마녀) ─────────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        role = ROLES.get(p.role_key)
        if not role or role.night_action != "FROG_TRANSFORM":
            continue
        tid = actions.get(actor_id)
        if tid and tid in gs.players and gs.players[tid].is_alive:
            gs.players[tid].is_frogged = True

    # ── 8: ROLEBLOCK (마담) ───────────────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        role = ROLES.get(p.role_key)
        if not role or role.night_action != "ROLEBLOCK":
            continue
        if p.is_roleblocked or p.is_frogged:
            continue
        tid = actions.get(actor_id)
        if tid and tid in gs.players:
            gs.players[tid].is_roleblocked = True

    # ── 개구리/roleblock 행동 취소 ────────────────────────────
    for actor_id in list(actions.keys()):
        p = gs.players.get(actor_id)
        if p and (p.is_roleblocked or p.is_frogged):
            actions[actor_id] = None

    # ── 7: REVIVE (성직자) ────────────────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        if p.is_roleblocked or p.is_frogged:
            continue
        role = ROLES.get(p.role_key)
        if not role or role.night_action != "REVIVE":
            continue
        if p.shots_remaining == 0:
            continue
        tid = actions.get(actor_id)
        if tid and tid in gs.dead_players:
            gs.dead_players.remove(tid)
            gs.players[tid].is_alive = True
            gs.players[tid].revived = True
            p.shots_remaining = 0

    # ── 6: PROTECT (의사) ─────────────────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        if p.is_roleblocked or p.is_frogged:
            continue
        role = ROLES.get(p.role_key)
        if not role or role.night_action != "PROTECT":
            continue
        tid = actions.get(actor_id)
        if tid is None:
            continue
        if tid == actor_id:
            if p.self_heal_used:
                continue
            p.self_heal_used = True
        if tid in gs.players and gs.players[tid].is_alive:
            gs.players[tid].is_protected = True

    # 군인 방탄 (passive)
    for p in gs.players.values():
        if p.is_alive and p.role_key == "soldier" and not p.armor_used:
            p.is_protected = True

    # ── 5: CULT_CONVERT (교주/광신도) ─────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        if p.is_roleblocked or p.is_frogged:
            continue
        role = ROLES.get(p.role_key)
        if not role or role.night_action != "CULT_CONVERT":
            continue
        tid = actions.get(actor_id)
        if not tid or tid not in gs.players:
            continue
        target = gs.players[tid]
        if target.is_alive and target.faction != Faction.MAFIA and not target.cult_converted:
            target.faction = Faction.CULT
            target.win_cond = WinCondition.CULT
            target.cult_converted = True

    # ── 4: KILL / DISARM ─────────────────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        if p.is_roleblocked or p.is_frogged:
            continue
        role = ROLES.get(p.role_key)
        if not role:
            continue
        if role.night_action == "DISARM":
            tid = actions.get(actor_id)
            if tid and tid in gs.players and gs.players[tid].is_alive:
                gs.players[tid].vote_weight = 0
            continue
        if role.night_action in ("KILL", "KILL_UNSTOPPABLE", "KILL_TARGETED"):
            tid = actions.get(actor_id)
            if tid and tid in gs.players and gs.players[tid].is_alive:
                to_kill[tid] = actor_id
                if role.night_action == "KILL_UNSTOPPABLE":
                    unstoppable_kills.add(tid)

    dead_this_night: list[int] = []

    for victim_id, killer_id in list(to_kill.items()):
        victim = gs.players[victim_id]
        killer = gs.players.get(killer_id)
        killer_role = ROLES.get(killer.role_key) if killer else None
        bypasses = (
            victim_id in unstoppable_kills
            or (killer_role and killer_role.night_action == "KILL_UNSTOPPABLE")
        )

        if victim.is_protected and not bypasses:
            if victim.role_key == "soldier":
                victim.armor_used = True
                victim.is_protected = False
            continue

        # 테러리스트 유폭
        if victim.role_key == "terrorist":
            _kill_player(gs, victim_id, dead_this_night)
            if killer_id and killer_id in gs.players:
                _kill_player(gs, killer_id, dead_this_night)
            continue

        _kill_player(gs, victim_id, dead_this_night)

    # 연인 동반 사망
    _process_lovers(gs, dead_this_night)

    # ── 과학자 부활 예약 ──────────────────────────────────────
    for dead_id in dead_this_night:
        dp = gs.players.get(dead_id)
        if dp and dp.role_key == "scientist" and dp.shots_remaining == 1:
            dp.shots_remaining = 0
            dp.scientist_revival = True  # 다음 밤 부활

    # ── 2: STEAL / SWAP_PREPARE ──────────────────────────────
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        if p.is_roleblocked or p.is_frogged or not p.is_alive:
            continue
        role = ROLES.get(p.role_key)
        if not role:
            continue
        if role.night_action == "STEAL_ROLE":
            tid = actions.get(actor_id)
            if tid and tid in dead_this_night and tid in gs.players:
                stolen = ROLES.get(gs.players[tid].role_key)
                if stolen:
                    p.role_key = stolen.key
                    p.shots_remaining = stolen.max_shots
        elif role.night_action == "SWAP_PREPARE":
            tid = actions.get(actor_id)
            if tid and p.shots_remaining != 0:
                p.swap_target = tid

    # ── 0: INVESTIGATE ───────────────────────────────────────
    investigate_results: dict[int, str] = {}
    for actor_id in sorted_actors:
        p = gs.players[actor_id]
        if p.is_roleblocked or p.is_frogged or not p.is_alive:
            continue
        role = ROLES.get(p.role_key)
        if not role:
            continue
        tid = actions.get(actor_id)
        if not tid or tid not in gs.players:
            continue
        target = gs.players[tid]

        if role.night_action == "INVESTIGATE_MAFIA":
            if target.role_key == "godfather":
                investigate_results[actor_id] = f"🔍 *{target.display}* — 시민"
            elif target.faction == Faction.MAFIA:
                investigate_results[actor_id] = f"🔍 *{target.display}* — ⚠️ *마피아*"
            else:
                investigate_results[actor_id] = f"🔍 *{target.display}* — 시민"

        elif role.night_action == "INVESTIGATE_ROLE":
            role_name = ROLES[target.role_key].name if target.role_key in ROLES else "???"
            if target.role_key == "fraud" and target.disguise_role:
                role_name = target.disguise_role
            investigate_results[actor_id] = f"🔍 *{target.display}* — {role_name}"

        elif role.night_action == "COMPARE":
            # 심리학자: night_target(1번째) + compare_target(2번째)
            second_id = p.compare_target
            if second_id and second_id in gs.players:
                second = gs.players[second_id]
                same = target.faction == second.faction
                result = "같은 팀입니다 ✅" if same else "다른 팀입니다 ❌"
                investigate_results[actor_id] = (
                    f"🧠 *{target.display}* 과 *{second.display}* — {result}"
                )
            else:
                investigate_results[actor_id] = "🧠 대상 선택이 완료되지 않았습니다\\."

        elif role.night_action == "TRACK":
            tracked_action = actions.get(tid)
            if tracked_action and tracked_action in gs.players:
                dest = gs.players[tracked_action]
                investigate_results[actor_id] = (
                    f"🔎 *{target.display}* 은 *{dest.display}* 에게 행동했습니다\\."
                )
            else:
                investigate_results[actor_id] = (
                    f"🔎 *{target.display}* 은 오늘 밤 아무것도 하지 않았습니다\\."
                )

        elif role.night_action == "INVESTIGATE_CULT":
            is_cult = target.faction == Faction.CULT
            investigate_results[actor_id] = (
                f"🙏 *{target.display}* — "
                + ("교주팀입니다 ⚠️" if is_cult else "교주팀이 아닙니다")
            )

        elif role.night_action == "SEANCE":
            if not target.is_alive:
                dead_role = ROLES.get(target.role_key)
                investigate_results[actor_id] = (
                    f"👻 *{target.display}* 의 직업: "
                    + (dead_role.name if dead_role else "???")
                )

    # 기자 결과 저장 (다음 낮에 공개)
    for actor_id in sorted_actors:
        p = gs.players.get(actor_id)
        if p and p.role_key == "reporter" and actor_id in investigate_results:
            p.reporter_result = investigate_results[actor_id]

    # 교주 사망 시 광신도 계승
    for dead_id in dead_this_night:
        dp = gs.players.get(dead_id)
        if dp and dp.role_key == "cult_leader":
            for uid, p in gs.players.items():
                if p.is_alive and p.cult_converted and p.role_key == "fanatic":
                    p.role_key = "cult_leader"
                    break

    gs.investigate_results = investigate_results
    gs.last_night_dead = dead_this_night
    return dead_this_night


def _kill_player(gs: GameState, user_id: int, dead_list: list[int]):
    p = gs.players.get(user_id)
    if not p or not p.is_alive:
        return
    p.is_alive = False
    if user_id not in gs.dead_players:
        gs.dead_players.append(user_id)
    if user_id not in dead_list:
        dead_list.append(user_id)


def _process_lovers(gs: GameState, dead_list: list[int]):
    """연인 중 한 명 사망 시 파트너도 사망"""
    extra = []
    for uid in list(dead_list):
        p = gs.players.get(uid)
        if p and p.lover_id:
            partner = gs.players.get(p.lover_id)
            if partner and partner.is_alive:
                partner.is_alive = False
                if partner.user_id not in gs.dead_players:
                    gs.dead_players.append(partner.user_id)
                if partner.user_id not in dead_list:
                    extra.append(partner.user_id)
    dead_list.extend(extra)


def reset_night_state(gs: GameState):
    """밤 시작 전 상태 초기화 (prev_night_dead는 도굴꾼을 위해 보존)"""
    gs.prev_night_dead = list(gs.last_night_dead)  # 도굴꾼용으로 보존
    for p in gs.players.values():
        p.night_target = None
        p.compare_target = None
        p.is_roleblocked = False
        p.is_protected = False
        p.is_frogged = False
        p.night_action_submitted = False
        p.has_voted = False
        p.vote_target = None
        # swap_target은 마술사가 처형될 때까지 유지 (처형 시 vote_engine에서 소비)
    gs.night_actions.clear()
    gs.mafia_kill_submitted_by = None
    gs.votes.clear()
    gs.investigate_results.clear()
    gs.last_night_dead.clear()
    gs.last_vote_dead = None
