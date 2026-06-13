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


def get_nominee(gs: GameState) -> Optional[int]:
    """
    지목 투표 집계 → 최종변론 대상(피고인) user_id.
    반환: 최다 득표자 user_id, 또는 None (득표 없음/동점).
    ※ 정치인·마술사·판사 보호는 여기서 적용하지 않고, 찬반 통과 후 resolve_execution 에서 처리.
    """
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
    if len(top) > 1:
        return None  # 동점 → 지목 무산
    return top[0]


def resolve_execution(gs: GameState, target_id: int) -> Optional[int]:
    """
    찬반 투표가 '처형'으로 가결된 뒤, 실제 처형 대상을 결정.
    반환: 실제 처형할 user_id, 또는 None (정치인 면책·판사 무죄로 면제).
    """
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


def count_judgment(gs: GameState) -> tuple[int, int]:
    """찬반 투표 가중치 집계 → (찬성, 반대)."""
    approve = reject = 0
    for voter_id, vote in gs.judgment_votes.items():
        voter = gs.players.get(voter_id)
        if not voter or not voter.is_alive:
            continue
        if voter.is_frogged or voter.vote_weight <= 0:
            continue
        if vote:
            approve += voter.vote_weight
        else:
            reject += voter.vote_weight
    return approve, reject


def tally_judgment(gs: GameState) -> bool:
    """찬반 투표 결과 → True(처형) / False(생존). 찬성이 반대보다 많아야 처형."""
    approve, reject = count_judgment(gs)
    return approve > reject


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
