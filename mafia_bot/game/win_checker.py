from typing import Optional
from game.state import GameState, Faction, WinCondition


def check_win(gs: GameState) -> WinCondition:
    """
    승리 진영 반환. NONE이면 게임 계속.
    우선순위: SERIAL_KILLER > MAFIA >= CULT > CITIZEN
    """
    alive = gs.alive_players()

    if not alive:
        return WinCondition.CITIZEN

    # ── 연쇄살인마: 혼자 남으면 승리 ────────────────────────
    sk_alive = [p for p in alive if p.win_cond == WinCondition.SERIAL_KILLER]
    if sk_alive and len(alive) == 1:
        return WinCondition.SERIAL_KILLER

    # ── 마피아 승리: 마피아 투표권 >= 비마피아 투표권 ─────────
    mafia_votes = gs.total_vote_weight(Faction.MAFIA)
    non_mafia_votes = sum(
        p.vote_weight for p in alive if p.faction != Faction.MAFIA
    )
    if mafia_votes >= non_mafia_votes and mafia_votes > 0:
        return WinCondition.MAFIA

    mafia_alive = gs.faction_alive(Faction.MAFIA)
    cult_alive = gs.faction_alive(Faction.CULT)

    # ── 교주 승리: 마피아 전멸 + 교주팀 투표권 >= 시민 투표권 ──
    if not mafia_alive and cult_alive:
        cult_votes = gs.total_vote_weight(Faction.CULT)
        citizen_votes = gs.total_vote_weight(Faction.CITIZEN)
        if cult_votes >= citizen_votes:
            return WinCondition.CULT

    # ── 시민 승리: 마피아 전멸 + 교주팀 전멸(또는 없음) ─────
    if not mafia_alive and not cult_alive:
        # 생존자만 남은 경우 생존자 승리
        citizen_alive_now = [p for p in alive if p.faction == Faction.CITIZEN]
        if not citizen_alive_now:
            survivor_alive = [p for p in alive if p.win_cond == WinCondition.SURVIVOR]
            if survivor_alive:
                return WinCondition.SURVIVOR
        return WinCondition.CITIZEN

    # ── 예언자: 시민팀 마지막 생존자 ────────────────────────
    citizen_alive = [p for p in alive if p.faction == Faction.CITIZEN]
    if len(citizen_alive) == 1 and citizen_alive[0].role_key == "prophet":
        return WinCondition.CITIZEN

    return WinCondition.NONE


def check_jester_win(gs: GameState, executed_id: int) -> bool:
    """투표 처형된 플레이어가 어릿광대인지 확인"""
    p = gs.players.get(executed_id)
    return p is not None and p.win_cond == WinCondition.JESTER
