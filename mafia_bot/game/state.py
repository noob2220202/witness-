from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Phase(Enum):
    LOBBY         = "lobby"
    NIGHT         = "night"
    NIGHT_RESOLVE = "night_resolve"
    DAY_ANNOUNCE  = "day_announce"
    DAY_DISCUSS   = "day_discuss"
    VOTE          = "vote"
    VOTE_RESOLVE  = "vote_resolve"
    ENDED         = "ended"


class Faction(Enum):
    MAFIA   = "mafia"
    CITIZEN = "citizen"
    CULT    = "cult"
    NEUTRAL = "neutral"


class WinCondition(Enum):
    MAFIA         = "마피아"
    CITIZEN       = "시민"
    CULT          = "교주"
    SERIAL_KILLER = "연쇄살인마"
    JESTER        = "어릿광대"
    SURVIVOR      = "생존자"
    NONE          = "none"


@dataclass
class PlayerState:
    user_id:   int
    username:  str   # @username 또는 first_name
    display:   str   # 표시용 이름

    role_key:  str   # ROLES dict 키
    faction:   Faction
    win_cond:  WinCondition

    # 생사
    is_alive:  bool = True

    # 투표 가중치
    vote_weight: int = 1  # 정치인=2, 건달 피해=0

    # 밤 행동 (매 밤 reset)
    night_target:       Optional[int] = None
    is_roleblocked:     bool = False
    is_protected:       bool = False
    is_frogged:         bool = False
    night_action_submitted: bool = False

    # 직업별 특수 카운터
    armor_used:         bool = False   # 군인 방탄 소진
    politician_immune:  bool = False   # 처형 면제 소진
    shots_remaining:    int  = -1      # -1 무한, 0 소진
    is_revealed:        bool = False   # 판사 정체 공개
    self_heal_used:     bool = False   # 의사 자힐 소진
    revived:            bool = False   # 부활 플래그
    cult_converted:     bool = False   # 교주 포교됨
    lover_id:           Optional[int] = None
    swap_target:        Optional[int] = None
    reporter_result:    Optional[str] = None   # 기자 조사 결과

    # 사기꾼 위장 직업
    disguise_role:      Optional[str] = None

    # 청부업자 확인 대상 목록
    confirmed_targets:  set = field(default_factory=set)

    # 투표
    has_voted:    bool = False
    vote_target:  Optional[int] = None


@dataclass
class GameState:
    group_chat_id: int
    creator_id:    int

    phase:      Phase = Phase.LOBBY
    day_number: int   = 0

    players:      dict = field(default_factory=dict)   # {user_id: PlayerState}
    dead_players: list = field(default_factory=list)   # [user_id]

    # 밤 행동: actor_id -> target_id
    night_actions:   dict = field(default_factory=dict)
    mafia_kill_submitted_by: Optional[int] = None

    # 투표: voter_id -> target_id
    votes: dict = field(default_factory=dict)

    # 메시지 ID (edit용)
    lobby_msg_id:      Optional[int] = None
    vote_msg_id:       Optional[int] = None
    last_group_msg_id: Optional[int] = None

    # 페이즈 타이머 job name
    phase_job: Optional[str] = None

    # 조사 결과 {actor_id: result_str}
    investigate_results: dict = field(default_factory=dict)

    # 이번 밤 사망자 / 이번 낮 처형자
    last_night_dead: list = field(default_factory=list)
    last_vote_dead:  Optional[int] = None

    def alive_players(self) -> list:
        return [p for p in self.players.values() if p.is_alive]

    def alive_ids(self) -> list:
        return [p.user_id for p in self.alive_players()]

    def faction_alive(self, faction: Faction) -> list:
        return [p for p in self.alive_players() if p.faction == faction]

    def alive_count(self) -> int:
        return sum(1 for p in self.players.values() if p.is_alive)

    def total_vote_weight(self, faction: Faction) -> int:
        return sum(p.vote_weight for p in self.faction_alive(faction))
