from typing import Optional
from game.state import GameState


def tally_votes(gs: GameState) -> Optional[int]:
    """
    투표 집계.
    반환: 처형 대상 user_id 또는 None (동점/과반 미달)
    """
    # 개구리·투표권 0인 유권자 제외
    weighted: dict[int, int] = {}
    for voter_id, target_id in gs.votes.items():
        voter = gs.players.get(voter_id)
        if not voter or not voter.is_alive:
            continue
        if voter.is_frogged or voter.vote_weight <= 0:
            continue
        weighted[target_id] = weighted.get(target_id, 0) + voter.vote_weight

    if not weighted:
        return None

    max_votes = max(weighted.values())
    top = [uid for uid, v in weighted.items() if v == max_votes]

    # 동점 → 처형 보류
    if len(top) > 1:
        return None

    target_id = top[0]
    p = gs.players.get(target_id)
    if not p:
        return None

    # 판사 무죄 선언 보호
    if p.spared_this_round:
        return None

    # 정치인 처형 면제 (1회)
    if p.role_key == "politician" and not p.politician_immune:
        p.politician_immune = True
        return None

    # 마술사 몸바꿈
    if p.role_key == "magician" and p.swap_target and p.shots_remaining != 0:
        actual_target = p.swap_target
        p.swap_target = None
        p.shots_remaining = 0
        return actual_target

    return target_id


def get_vote_summary(gs: GameState) -> str:
    """현재 투표 현황 문자열 (MarkdownV2)"""
    weighted: dict[int, int] = {}
    for voter_id, target_id in gs.votes.items():
        voter = gs.players.get(voter_id)
        if voter and voter.is_alive and voter.vote_weight > 0 and not voter.is_frogged:
            weighted[target_id] = weighted.get(target_id, 0) + voter.vote_weight

    if not weighted:
        return "아직 투표가 없습니다\\."

    lines = []
    for uid, cnt in sorted(weighted.items(), key=lambda x: -x[1]):
        p = gs.players.get(uid)
        name = _esc(p.display) if p else str(uid)
        lines.append(f"  • *{name}* \\— {cnt}표")

    alive_cnt = gs.alive_count()
    voted_cnt = sum(1 for p in gs.alive_players() if p.has_voted)
    lines.append(f"\n📊 투표 현황: {voted_cnt}/{alive_cnt}명 완료")
    return "\n".join(lines)


def _esc(text: str) -> str:
    special = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special else c for c in str(text))
