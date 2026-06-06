from dataclasses import dataclass, field
from typing import Optional
from game.state import Faction, WinCondition


@dataclass(frozen=True)
class RoleDefinition:
    key:          str
    name:         str           # 한국어 직업명
    faction:      Faction
    win_cond:     WinCondition
    night_action: Optional[str] # 행동 타입 (None=없음)
    priority:     int
    description:  str
    max_shots:    int  = -1     # -1 무한
    can_self:     bool = False  # 자신 대상 허용


ROLES: dict[str, RoleDefinition] = {

    # ══════════════════════════════════════════════════
    # 마피아 진영 (10종)
    # ══════════════════════════════════════════════════

    "mafioso": RoleDefinition(
        key="mafioso", name="마피아",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="KILL", priority=4,
        description=(
            "🔪 *당신은 마피아입니다\\.*\n\n"
            "밤마다 생존자 중 1명을 살해합니다\\.\n"
            "팀원들과 협력해 시민들을 제거하세요\\."
        ),
    ),
    "godfather": RoleDefinition(
        key="godfather", name="대부",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="KILL", priority=4,
        description=(
            "👑 *당신은 대부입니다\\.*\n\n"
            "경찰 조사 시 __'시민'__ 으로 위장됩니다\\.\n"
            "밤 살해를 지휘하는 마피아의 수장입니다\\."
        ),
    ),
    "spy": RoleDefinition(
        key="spy", name="스파이",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="INVESTIGATE_ROLE", priority=0,
        description=(
            "🕵️ *당신은 스파이입니다\\.*\n\n"
            "밤마다 1명의 __정확한 직업__을 확인합니다\\.\n"
            "확인 결과는 마피아 팀 전체에 공유됩니다\\."
        ),
    ),
    "madam": RoleDefinition(
        key="madam", name="마담",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="ROLEBLOCK", priority=8,
        description=(
            "💃 *당신은 마담입니다\\.*\n\n"
            "밤마다 1명의 능력 사용을 __차단__합니다\\.\n"
            "차단된 대상의 밤 행동이 무효화됩니다\\."
        ),
    ),
    "beast": RoleDefinition(
        key="beast", name="짐승인간",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="KILL_UNSTOPPABLE", priority=4,
        description=(
            "🐺 *당신은 짐승인간입니다\\.*\n\n"
            "살해 시 __의사·군인 보호를 무시__합니다\\.\n"
            "마피아팀 공격으로는 사망하지 않습니다\\."
        ),
    ),
    "hitman": RoleDefinition(
        key="hitman", name="청부업자",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="KILL_TARGETED", priority=4,
        description=(
            "🎯 *당신은 청부업자입니다\\.*\n\n"
            "직업을 파악한 대상을 __보호·치료 무시__하고 즉시 처형합니다\\.\n"
            "직업 정보는 스파이·조사 결과로 수집하세요\\."
        ),
    ),
    "witch": RoleDefinition(
        key="witch", name="마녀",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="FROG_TRANSFORM", priority=8,
        description=(
            "🐸 *당신은 마녀입니다\\.*\n\n"
            "밤마다 1명을 __개구리로 변환__합니다\\.\n"
            "개구리 상태에서는 능력 사용·투표권이 다음날까지 무효화됩니다\\.\n"
            "다음 밤 자동으로 원래 직업으로 복귀합니다\\."
        ),
    ),
    "fraud": RoleDefinition(
        key="fraud", name="사기꾼",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="DISGUISE", priority=0,
        description=(
            "🎭 *당신은 사기꾼입니다\\.*\n\n"
            "조사당할 때 __다른 직업으로 위장__됩니다\\.\n"
            "매 밤 위장할 직업을 선택하세요\\."
        ),
    ),
    "scientist": RoleDefinition(
        key="scientist", name="과학자",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action=None, priority=0,
        max_shots=1,
        description=(
            "🧪 *당신은 과학자입니다\\.*\n\n"
            "투표 처형 또는 마피아에게 사망하면 __다음 밤 부활__합니다\\. \\(1회\\)\n"
            "밤 행동은 없지만 위기 탈출 능력이 있습니다\\."
        ),
    ),
    "thief": RoleDefinition(
        key="thief", name="도둑",
        faction=Faction.MAFIA, win_cond=WinCondition.MAFIA,
        night_action="STEAL_ABILITY", priority=2,
        description=(
            "🃏 *당신은 도둑입니다\\.*\n\n"
            "밤마다 시민 1명의 __능력을 복사__해 1회 사용합니다\\.\n"
            "복사된 능력은 다음 밤에 사용됩니다\\."
        ),
    ),

    # ══════════════════════════════════════════════════
    # 시민 진영 — 중직
    # ══════════════════════════════════════════════════

    "police": RoleDefinition(
        key="police", name="경찰",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="INVESTIGATE_MAFIA", priority=0,
        description=(
            "👮 *당신은 경찰입니다\\.*\n\n"
            "밤마다 1명을 조사해 __마피아 진영 여부__를 확인합니다\\.\n"
            "> ⚠️ 대부는 '시민'으로 위장됩니다\\."
        ),
    ),
    "doctor": RoleDefinition(
        key="doctor", name="의사",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="PROTECT", priority=6,
        can_self=True, max_shots=1,
        description=(
            "💉 *당신은 의사입니다\\.*\n\n"
            "밤마다 1명을 치료해 마피아 공격으로부터 __보호__합니다\\.\n"
            "> ⚠️ 자가치료는 1회만 가능합니다\\."
        ),
    ),
    "vigilante": RoleDefinition(
        key="vigilante", name="자경단원",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="INVESTIGATE_ROLE", priority=0,
        max_shots=1,
        description=(
            "🔫 *당신은 자경단원입니다\\.*\n\n"
            "밤마다 1명의 __직업을 확인__합니다\\.\n"
            "마피아로 확인되면 즉시 처형\\(1회\\)하거나 정보만 수집할 수 있습니다\\."
        ),
    ),
    "agent": RoleDefinition(
        key="agent", name="요원",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="INVESTIGATE_ROLE", priority=0,
        description=(
            "🕶️ *당신은 요원입니다\\.*\n\n"
            "매 밤 생존자 중 1명의 __정확한 직업__을 확인합니다\\.\n"
            "정보를 팀원과 공유해 마피아를 색출하세요\\."
        ),
    ),

    # ══════════════════════════════════════════════════
    # 시민 진영 — 특직
    # ══════════════════════════════════════════════════

    "soldier": RoleDefinition(
        key="soldier", name="군인",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action=None, priority=0,
        description=(
            "🪖 *당신은 군인입니다\\.*\n\n"
            "마피아의 첫 번째 살해 공격을 __자동으로 방어__합니다\\.\n"
            "> ⚠️ 방탄은 1회만 발동하며 이후 일반 시민이 됩니다\\."
        ),
    ),
    "politician": RoleDefinition(
        key="politician", name="정치인",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action=None, priority=0,
        description=(
            "🎩 *당신은 정치인입니다\\.*\n\n"
            "투표로 __처형당하지 않습니다__ \\(1회\\)\\.\n"
            "투표권이 __2개__로 집계됩니다\\."
        ),
    ),
    "medium": RoleDefinition(
        key="medium", name="영매",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="SEANCE", priority=0,
        description=(
            "🔮 *당신은 영매입니다\\.*\n\n"
            "죽은 자 1명의 __직업을 확인__하거나 그들의 메시지를 전달받을 수 있습니다\\.\n"
            "밤에 사망한 플레이어의 DM이 당신에게 전달됩니다\\."
        ),
    ),
    "lover": RoleDefinition(
        key="lover", name="연인",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action=None, priority=0,
        description=(
            "💕 *당신은 연인입니다\\.*\n\n"
            "__파트너가 사망하면 당신도 함께 사망__합니다\\.\n"
            "서로의 정체를 알고 있지만 진영은 다를 수 있습니다\\."
        ),
    ),
    "gangster": RoleDefinition(
        key="gangster", name="건달",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="DISARM", priority=4,
        description=(
            "🦹 *당신은 건달입니다\\.*\n\n"
            "밤마다 1명의 __다음날 투표권을 박탈__합니다\\.\n"
            "투표권이 0이 된 플레이어는 다음 낮 투표에서 제외됩니다\\."
        ),
    ),
    "reporter": RoleDefinition(
        key="reporter", name="기자",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="INVESTIGATE_ROLE", priority=0,
        description=(
            "📰 *당신은 기자입니다\\.*\n\n"
            "밤에 1명의 직업을 조사합니다\\.\n"
            "다음날 낮에 생존 시 그 직업이 __전체 그룹에 자동 공개__됩니다\\."
        ),
    ),
    "detective": RoleDefinition(
        key="detective", name="사립탐정",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="TRACK", priority=0,
        description=(
            "🔎 *당신은 사립탐정입니다\\.*\n\n"
            "밤에 대상이 어떤 행동을 했는지 __이동 경로를 추적__합니다\\.\n"
            "행동 타입과 대상을 알 수 있습니다\\."
        ),
    ),
    "grave_robber": RoleDefinition(
        key="grave_robber", name="도굴꾼",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="STEAL_ROLE", priority=2,
        description=(
            "⚰️ *당신은 도굴꾼입니다\\.*\n\n"
            "오늘 밤 사망한 플레이어 중 1명의 __직업을 획득__합니다\\.\n"
            "> ⚠️ 죽은 자가 없는 밤에는 사용할 수 없습니다\\."
        ),
    ),
    "terrorist": RoleDefinition(
        key="terrorist", name="테러리스트",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action=None, priority=0,
        description=(
            "💣 *당신은 테러리스트입니다\\.*\n\n"
            "마피아의 살해 대상이 되면 __공격한 마피아와 함께 사망__합니다\\.\n"
            "> ⚠️ 의사 치료로 유폭을 막을 수 없습니다\\."
        ),
    ),
    "priest": RoleDefinition(
        key="priest", name="성직자",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="REVIVE", priority=7,
        max_shots=1,
        description=(
            "✝️ *당신은 성직자입니다\\.*\n\n"
            "이미 사망한 플레이어 1명을 __부활__시킵니다\\. \\(1회\\)\n"
            "부활한 플레이어는 원래 직업으로 돌아옵니다\\."
        ),
    ),
    "prophet": RoleDefinition(
        key="prophet", name="예언자",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action=None, priority=0,
        description=(
            "🌟 *당신은 예언자입니다\\.*\n\n"
            "시민팀에서 __마지막으로 살아남은 자__가 되는 순간 계시가 발동합니다\\.\n"
            "즉시 시민팀 전체가 승리합니다\\."
        ),
    ),
    "judge": RoleDefinition(
        key="judge", name="판사",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action=None, priority=0,
        max_shots=1,
        description=(
            "⚖️ *당신은 판사입니다\\.*\n\n"
            "정체를 공개하면 이번 낮 투표에서 1회에 한해:\n"
            "• 특정인을 __직권 처형__ \\(투표 없이\\)\n"
            "• 또는 특정인을 __무죄 선언__ \\(처형 면제\\)"
        ),
    ),
    "magician": RoleDefinition(
        key="magician", name="마술사",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="SWAP_PREPARE", priority=2,
        max_shots=1,
        description=(
            "🪄 *당신은 마술사입니다\\.*\n\n"
            "밤에 대상을 예약해 두면 당신이 투표 처형될 때 그 대상과 __몸을 바꿉니다__\\. \\(1회\\)\n"
            "바뀐 대상이 처형되고 당신은 살아남습니다\\."
        ),
    ),
    "psychologist": RoleDefinition(
        key="psychologist", name="심리학자",
        faction=Faction.CITIZEN, win_cond=WinCondition.CITIZEN,
        night_action="COMPARE", priority=0,
        description=(
            "🧠 *당신은 심리학자입니다\\.*\n\n"
            "두 명을 선택해 __같은 진영\\(faction\\)인지__ 확인합니다\\.\n"
            "결과: 같은 팀 / 다른 팀 \\(구체적 진영은 공개 안 됨\\)"
        ),
    ),

    # ══════════════════════════════════════════════════
    # 교주 진영 (2종)
    # ══════════════════════════════════════════════════

    "cult_leader": RoleDefinition(
        key="cult_leader", name="교주",
        faction=Faction.CULT, win_cond=WinCondition.CULT,
        night_action="CULT_CONVERT", priority=5,
        description=(
            "🛐 *당신은 교주입니다\\.*\n\n"
            "매 밤 1명을 포교해 __교주팀으로 전환__합니다\\.\n"
            "> ⚠️ 마피아팀 포교는 불가합니다\\.\n"
            "사망 시 가장 먼저 포교된 멤버가 능력 계승\\."
        ),
    ),
    "fanatic": RoleDefinition(
        key="fanatic", name="광신도",
        faction=Faction.CULT, win_cond=WinCondition.CULT,
        night_action="INVESTIGATE_CULT", priority=0,
        description=(
            "🙏 *당신은 광신도입니다\\.*\n\n"
            "매 밤 1명이 __교주팀인지__ 확인합니다\\.\n"
            "교주 사망 시 포교 능력을 계승합니다\\."
        ),
    ),

    # ══════════════════════════════════════════════════
    # 중립 (3종)
    # ══════════════════════════════════════════════════

    "serial_killer": RoleDefinition(
        key="serial_killer", name="연쇄살인마",
        faction=Faction.NEUTRAL, win_cond=WinCondition.SERIAL_KILLER,
        night_action="KILL", priority=4,
        description=(
            "🗡️ *당신은 연쇄살인마입니다\\.*\n\n"
            "매 밤 1명을 살해합니다\\. __마피아와 시민 모두가 적__입니다\\.\n"
            "마지막까지 혼자 살아남으면 승리합니다\\."
        ),
    ),
    "jester": RoleDefinition(
        key="jester", name="어릿광대",
        faction=Faction.NEUTRAL, win_cond=WinCondition.JESTER,
        night_action=None, priority=0,
        description=(
            "🃏 *당신은 어릿광대입니다\\.*\n\n"
            "__낮 투표로 처형당하는 것__이 목표입니다\\.\n"
            "처형당하는 순간 즉시 혼자 승리합니다\\."
        ),
    ),
    "survivor": RoleDefinition(
        key="survivor", name="생존자",
        faction=Faction.NEUTRAL, win_cond=WinCondition.SURVIVOR,
        night_action=None, priority=0,
        description=(
            "🛡️ *당신은 생존자입니다\\.*\n\n"
            "어느 진영이 이기든 관계없이 __게임 종료 시 살아있으면 승리__합니다\\.\n"
            "자신을 드러내지 않고 끝까지 살아남으세요\\."
        ),
    ),
}
