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
    username:  str
    display:   str

    role_key:  str
    faction:   Faction
    win_cond:  WinCondition

    is_alive:    bool = True
    vote_weight: int  = 1

    # ── 밤 행동 (매 밤 reset) ─────────────────────────────────
    night_target:            Optional[int] = None
    compare_target:          Optional[int] = None  # 심리학자 두 번째 대상
    is_roleblocked:          bool = False
    is_protected:            bool = False
    is_frogged:              bool = False
    night_action_submitted:  bool = False

    # ── 직업별 특수 카운터 ────────────────────────────────────
    armor_used:              bool = False
    politician_immune:       bool = False
    shots_remaining:         int  = -1      # -1=무한, 0=소진
    is_revealed:             bool = False
    self_heal_used:          bool = False
    revived:                 bool = False
    scientist_revival:       bool = False   # 다음 밤 부활 예약
    cult_converted:          bool = False
    lover_id:                Optional[int] = None
    swap_target:             Optional[int] = None   # 마술사 예약 대상
    reporter_result:         Optional[str] = None
    disguise_role:           Optional[str] = None
    confirmed_targets:       set = field(default_factory=set)
    spared_this_round:       bool = False  # 판사 무죄 선언 보호

    has_voted:    bool = False
    vote_target:  Optional[int] = None


@dataclass
class GameState:
    group_chat_id: int
    creator_id:    int

    # 마피아 전용 토픽(포럼 스레드) ID. None이면 일반 그룹/General 토픽.
    topic_id:   Optional[int] = None

    phase:      Phase = Phase.LOBBY
    day_number: int   = 0

    players:      dict = field(default_factory=dict)
    dead_players: list = field(default_factory=list)

    night_actions:           dict = field(default_factory=dict)
    mafia_kill_submitted_by: Optional[int] = None

    votes: dict = field(default_factory=dict)

    lobby_msg_id:      Optional[int] = None
    vote_msg_id:       Optional[int] = None
    last_group_msg_id: Optional[int] = None

    phase_job: Optional[str] = None

    investigate_results: dict = field(default_factory=dict)

    last_night_dead:  list = field(default_factory=list)
    prev_night_dead:  list = field(default_factory=list)  # 지난 밤 사망자 (도굴꾼용)
    last_vote_dead:   Optional[int] = None

    # 커스텀 타이머 (설정에서 덮어씀)
    timers: dict = field(default_factory=lambda: {
        "lobby": 300, "night": 90, "discuss": 180, "vote": 60,
    })

    def belongs_to_topic(self, message_thread_id: Optional[int]) -> bool:
        """주어진 메시지의 스레드(토픽) ID가 이 게임의 토픽과 일치하는지."""
        return (self.topic_id or None) == (message_thread_id or None)

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
