import random
from game.state import GameState, PlayerState, Faction, WinCondition
from game.roles import ROLES, RoleDefinition

# 인원별 배정 테이블
ASSIGNMENT_TABLE = {
    4:  {"mafia_base": 1, "mafia_support": 0, "citizen_special": 1, "cult": 0, "neutral": 0},
    5:  {"mafia_base": 1, "mafia_support": 0, "citizen_special": 2, "cult": 0, "neutral": 0},
    6:  {"mafia_base": 2, "mafia_support": 0, "citizen_special": 2, "cult": 0, "neutral": 0},
    7:  {"mafia_base": 2, "mafia_support": 0, "citizen_special": 3, "cult": 0, "neutral": 0},
    8:  {"mafia_base": 2, "mafia_support": 1, "citizen_special": 3, "cult": 0, "neutral": 0},
    9:  {"mafia_base": 2, "mafia_support": 1, "citizen_special": 3, "cult": 1, "neutral": 0},
    10: {"mafia_base": 3, "mafia_support": 1, "citizen_special": 3, "cult": 1, "neutral": 0},
    11: {"mafia_base": 3, "mafia_support": 1, "citizen_special": 3, "cult": 1, "neutral": 1},
    12: {"mafia_base": 3, "mafia_support": 1, "citizen_special": 5, "cult": 1, "neutral": 0},
    13: {"mafia_base": 3, "mafia_support": 2, "citizen_special": 5, "cult": 1, "neutral": 0},
    14: {"mafia_base": 3, "mafia_support": 2, "citizen_special": 5, "cult": 1, "neutral": 1},
    15: {"mafia_base": 4, "mafia_support": 2, "citizen_special": 5, "cult": 1, "neutral": 1},
    16: {"mafia_base": 4, "mafia_support": 2, "citizen_special": 6, "cult": 1, "neutral": 1},
}

MAFIA_SUPPORT_POOL = ["spy", "madam", "beast", "hitman", "witch", "fraud", "scientist", "thief"]

CITIZEN_SPECIAL_POOL = [
    "vigilante", "agent", "soldier", "politician", "medium", "gangster",
    "reporter", "detective", "grave_robber", "terrorist", "priest",
    "prophet", "judge", "magician", "psychologist",
]

NEUTRAL_POOL = ["serial_killer", "jester", "survivor"]


def assign_roles(player_ids: list[int]) -> dict[int, RoleDefinition]:
    """player_ids 목록에 직업을 배정해 {user_id: RoleDefinition} 반환"""
    n = len(player_ids)
    if n not in ASSIGNMENT_TABLE:
        raise ValueError(f"지원하지 않는 인원수: {n}")

    table = ASSIGNMENT_TABLE[n]
    shuffled = player_ids[:]
    random.shuffle(shuffled)
    idx = 0
    assignment = {}

    # 1. 마피아 기본 (12인+ 면 첫 번째를 대부로)
    for i in range(table["mafia_base"]):
        role_key = "godfather" if (i == 0 and n >= 12) else "mafioso"
        assignment[shuffled[idx]] = ROLES[role_key]
        idx += 1

    # 2. 마피아 보조
    support_picks = random.sample(MAFIA_SUPPORT_POOL, table["mafia_support"])
    for rk in support_picks:
        assignment[shuffled[idx]] = ROLES[rk]
        idx += 1

    # 3. 경찰 고정
    assignment[shuffled[idx]] = ROLES["police"]
    idx += 1

    # 4. 의사 고정
    assignment[shuffled[idx]] = ROLES["doctor"]
    idx += 1

    # 5. 교주
    if table["cult"] > 0:
        assignment[shuffled[idx]] = ROLES["cult_leader"]
        idx += 1

    # 6. 중립
    if table["neutral"] > 0:
        nk = random.choice(NEUTRAL_POOL)
        assignment[shuffled[idx]] = ROLES[nk]
        idx += 1

    # 7. 시민 특직 (남은 슬롯)
    remaining = n - idx
    picks = _pick_special(CITIZEN_SPECIAL_POOL[:], remaining)
    for rk in picks:
        assignment[shuffled[idx]] = ROLES[rk]
        idx += 1

    return assignment


def _pick_special(pool: list[str], count: int) -> list[str]:
    """
    연인(lover)은 2슬롯 소모 특직 선택.
    여기서는 연인을 일반 특직 풀에서 제외하고 40% 확률로 2칸 소모로 추가.
    """
    result = []
    remaining = count
    available = pool[:]

    # 40% 확률로 lover 쌍 추가 (슬롯 2칸)
    if remaining >= 2 and random.random() < 0.4:
        result.extend(["lover", "lover"])
        remaining -= 2

    random.shuffle(available)
    for rk in available:
        if remaining <= 0:
            break
        result.append(rk)
        remaining -= 1

    return result


def build_player_states(
    assignment: dict[int, RoleDefinition],
    names: dict[int, str],
    displays: dict[int, str],
) -> dict[int, PlayerState]:
    """assignment + names → {user_id: PlayerState} 생성, 연인 연결 포함"""
    players: dict[int, PlayerState] = {}
    for user_id, role_def in assignment.items():
        p = PlayerState(
            user_id=user_id,
            username=names.get(user_id, str(user_id)),
            display=displays.get(user_id, names.get(user_id, str(user_id))),
            role_key=role_def.key,
            faction=role_def.faction,
            win_cond=role_def.win_cond,
        )
        # shots_remaining 초기화
        if role_def.max_shots >= 0:
            p.shots_remaining = role_def.max_shots
        # 정치인 투표 가중치
        if role_def.key == "politician":
            p.vote_weight = 2
        players[user_id] = p

    # 연인 연결 (lover 직업 보유자 2명을 서로 연결)
    lover_ids = [uid for uid, p in players.items() if p.role_key == "lover"]
    if len(lover_ids) == 2:
        players[lover_ids[0]].lover_id = lover_ids[1]
        players[lover_ids[1]].lover_id = lover_ids[0]

    return players
