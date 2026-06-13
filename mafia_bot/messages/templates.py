"""
모든 유저 대면 메시지 템플릿 (MarkdownV2 포맷).
parse_mode=ParseMode.MARKDOWN_V2 로 전송 필수.
"""
from game.state import GameState, PlayerState, Faction, WinCondition
from game.roles import ROLES, RoleDefinition


# ── 공통 이스케이프 ─────────────────────────────────────────────────────────

def esc(text: str) -> str:
    """MarkdownV2 특수문자 이스케이프"""
    special = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special else c for c in str(text))


# ── 로비 ────────────────────────────────────────────────────────────────────

def lobby_msg(gs: GameState) -> str:
    player_lines = []
    for i, p in enumerate(gs.players.values(), 1):
        player_lines.append(f"  {i}\\. {esc(p.display)}")

    players_str = "\n".join(player_lines) if player_lines else "  _아직 아무도 없습니다_"
    count = len(gs.players)

    return (
        "🎭 *마피아 게임 로비*\n\n"
        f"👥 참가자 \\({esc(str(count))}명\\):\n"
        f"{players_str}\n\n"
        "📌 게임에 참가하려면 아래 버튼을 누르세요\\.\n"
        "> 먼저 봇 DM을 열어두어야 역할을 받을 수 있습니다\\!"
    )


def status_msg(gs: GameState) -> str:
    phase_names = {
        "lobby":        "🏠 로비",
        "night":        "🌙 밤",
        "night_resolve":"⚙️ 밤 결산 중",
        "day_announce": "🔔 사망자 공지",
        "day_discuss":  "☀️ 낮 토론",
        "vote":         "🗳️ 투표",
        "final_defense":"🎤 최종변론",
        "judgment":     "⚖️ 찬반 투표",
        "vote_resolve": "⚖️ 투표 결산",
        "ended":        "🏁 게임 종료",
    }
    phase_str = esc(phase_names.get(gs.phase.value, gs.phase.value))
    alive_cnt = gs.alive_count()
    dead_cnt = len(gs.dead_players)

    alive_names = "\n".join(
        f"  • {esc(p.display)}" for p in gs.alive_players()
    )

    return (
        f"📋 *게임 현황 — {esc(str(gs.day_number))}일차*\n\n"
        f"현재 페이즈: *{phase_str}*\n"
        f"생존자: *{esc(str(alive_cnt))}명* \\| 사망자: *{esc(str(dead_cnt))}명*\n\n"
        f"🟢 *생존자 목록:*\n{alive_names}"
    )


# ── 역할 배정 DM ────────────────────────────────────────────────────────────

def role_assignment_msg(
    p: PlayerState,
    role_def: RoleDefinition,
    mafia_team: list[str] | None = None,
    lover_name: str | None = None,
) -> str:
    faction_emoji = {
        Faction.MAFIA:   "🔴 마피아",
        Faction.CITIZEN: "🔵 시민",
        Faction.CULT:    "🟣 교주",
        Faction.NEUTRAL: "⚪ 중립",
    }
    faction_str = esc(faction_emoji.get(role_def.faction, "❓"))

    msg = (
        f"🎭 *직업이 배정되었습니다\\!*\n\n"
        f"{role_def.description}\n\n"
        f"진영: {faction_str}"
    )

    if mafia_team:
        team_str = "\n".join(f"  • {esc(name)}" for name in mafia_team)
        msg += f"\n\n🔪 *마피아 팀원:*\n{team_str}"

    if lover_name:
        msg += f"\n\n💕 *연인 파트너:* {esc(lover_name)}"

    msg += "\n\n> 게임이 시작되면 DM으로 행동 버튼이 전송됩니다\\."
    return msg


# ── 밤 시작 ─────────────────────────────────────────────────────────────────

def night_start_msg(day: int, alive_cnt: int) -> str:
    return (
        f"🌙 *밤 {esc(str(day))}이 되었습니다\\.*\n\n"
        f"마피아가 움직이기 시작합니다\\.\\.\\.\n"
        f"생존자 {esc(str(alive_cnt))}명 중 누군가가 오늘 밤 사라질 수도 있습니다\\.\n\n"
        "> 특수 직업 보유자는 DM으로 이동해 행동을 선택하세요\\!"
    )


def night_action_prompt(role_def: RoleDefinition) -> str:
    action_descs = {
        "KILL":              "🔪 *오늘 밤 처치할 대상을 선택하세요\\.*",
        "KILL_UNSTOPPABLE":  "🐺 *오늘 밤 처치할 대상을 선택하세요\\.*\n_\\(보호·치료 무시\\)_",
        "KILL_TARGETED":     "🎯 *오늘 밤 처치할 대상을 선택하세요\\.*\n_\\(파악된 직업에 한해 보호 무시\\)_",
        "PROTECT":           "💉 *오늘 밤 보호할 대상을 선택하세요\\.*",
        "ROLEBLOCK":         "💃 *오늘 밤 차단할 대상을 선택하세요\\.*",
        "FROG_TRANSFORM":    "🐸 *오늘 밤 개구리로 변환할 대상을 선택하세요\\.*",
        "INVESTIGATE_MAFIA": "👮 *오늘 밤 조사할 대상을 선택하세요\\.*\n_\\(마피아 여부 확인\\)_",
        "INVESTIGATE_ROLE":  "🔍 *오늘 밤 조사할 대상을 선택하세요\\.*\n_\\(직업 확인\\)_",
        "INVESTIGATE_CULT":  "🙏 *오늘 밤 조사할 대상을 선택하세요\\.*\n_\\(교주팀 여부 확인\\)_",
        "CULT_CONVERT":      "🛐 *오늘 밤 포교할 대상을 선택하세요\\.*",
        "SEANCE":            "🔮 *대화할 죽은 자를 선택하세요\\.*",
        "TRACK":             "🔎 *오늘 밤 추적할 대상을 선택하세요\\.*",
        "STEAL_ROLE":        "⚰️ *직업을 훔칠 사망자를 선택하세요\\.*",
        "STEAL_ABILITY":     "🃏 *능력을 복사할 시민을 선택하세요\\.*",
        "SWAP_PREPARE":      "🪄 *처형 시 몸을 바꿀 대상을 예약하세요\\.*",
        "COMPARE":           "🧠 *진영을 비교할 대상을 선택하세요\\.*",
        "DISARM":            "🦹 *투표권을 박탈할 대상을 선택하세요\\.*",
        "DISGUISE":          "🎭 *오늘 밤 위장할 직업을 선택하세요\\.*",
        "REVIVE":            "✝️ *부활시킬 사망자를 선택하세요\\.*",
    }
    return action_descs.get(role_def.night_action or "", "🌙 *오늘 밤 행동을 선택하세요\\.*")


def no_night_action_msg(role_def: RoleDefinition) -> str:
    return (
        f"🌙 *{esc(role_def.name)}* — 밤 행동이 없습니다\\.\n\n"
        "> 날이 밝을 때까지 기다려주세요\\."
    )


# ── 낮 공지 ─────────────────────────────────────────────────────────────────

def day_announce_msg(gs: GameState, dead_names_roles: list[tuple[str, str]]) -> str:
    if not dead_names_roles:
        return (
            f"☀️ *{esc(str(gs.day_number))}일째 아침\\.*\n\n"
            "오늘 밤은 __아무도 죽지 않았습니다__\\.\n\n"
            "> 신중히 토론하고 마피아를 색출하세요\\!"
        )

    dead_lines = "\n".join(
        f"  ☠️ *{esc(name)}* \\— __{esc(role)}__"
        for name, role in dead_names_roles
    )
    return (
        f"☀️ *{esc(str(gs.day_number))}일째 아침\\.*\n\n"
        f"오늘 아침 발견된 시신:\n{dead_lines}\n\n"
        "> 신중히 토론하고 마피아를 색출하세요\\!"
    )


def reporter_announce_msg(reporter_name: str, result: str) -> str:
    return (
        f"📰 *기자 {esc(reporter_name)}의 특종\\!*\n\n"
        f"{result}"
    )


# ── 낮 토론 ─────────────────────────────────────────────────────────────────

def day_discuss_msg(day: int, timeout: int) -> str:
    return (
        f"🗣️ *낮 {esc(str(day))} 토론이 시작되었습니다\\.*\n\n"
        f"제한 시간: *{esc(str(timeout))}초*\n"
        "> 자유롭게 토론하고 마피아를 찾아내세요\\!"
    )


# 직업별 이모지
_ROLE_EMOJI: dict[str, str] = {
    "mafioso":       "🤵🏼",
    "godfather":     "👑",
    "spy":           "🕵️",
    "madam":         "💃",
    "beast":         "🐺",
    "hitman":        "🎯",
    "witch":         "🐸",
    "fraud":         "🎭",
    "scientist":     "🧪",
    "thief":         "🃏",
    "police":        "👮",
    "doctor":        "👨🏼‍⚕️",
    "vigilante":     "🔫",
    "agent":         "🕶️",
    "soldier":       "🪖",
    "politician":    "🎩",
    "medium":        "🔮",
    "lover":         "💕",
    "gangster":      "🦹",
    "reporter":      "📰",
    "detective":     "🔎",
    "grave_robber":  "⚰️",
    "terrorist":     "💣",
    "priest":        "✝️",
    "prophet":       "🌟",
    "judge":         "⚖️",
    "magician":      "🪄",
    "psychologist":  "🧠",
    "cult_leader":   "🛐",
    "fanatic":       "🙏",
    "serial_killer": "🗡️",
    "jester":        "🃏",
    "survivor":      "🛡️",
}


def morning_status_msg(gs: GameState) -> str:
    """
    아침 토론 시작 시 전송하는 풀 상태 메시지.
    생존자 목록 + 현재 살아있는 직업 목록(익명) + 총 인원
    """
    from game.roles import ROLES

    alive = gs.alive_players()

    # 생존자 목록 (참가 순서 번호 유지)
    all_ids = list(gs.players.keys())
    survivor_lines = []
    for p in alive:
        num = all_ids.index(p.user_id) + 1
        survivor_lines.append(f"  {num}\\. {esc(p.display)}")
    survivors_str = "\n".join(survivor_lines)

    # 직업 목록 (살아있는 플레이어 직업, 익명·중복 표시)
    role_counts: dict[str, int] = {}
    for p in alive:
        role_counts[p.role_key] = role_counts.get(p.role_key, 0) + 1

    role_parts = []
    for rk, cnt in role_counts.items():
        role = ROLES.get(rk)
        if not role:
            continue
        emoji = _ROLE_EMOJI.get(rk, "👤")
        name = esc(role.name)
        if cnt > 1:
            role_parts.append(f"{emoji} {name} \\- {cnt}")
        else:
            role_parts.append(f"{emoji} {name}")
    roles_str = ",  ".join(role_parts)

    total = len(alive)

    return (
        f"☀️ *{esc(str(gs.day_number))}일째 아침이 밝았습니다\\.*\n\n"
        f"*생존자 목록:*\n{survivors_str}\n\n"
        f"*직업 목록:*\n{roles_str}\n"
        f"총 인원 : *{esc(str(total))}명*\n\n"
        "> 아침이 밝았습니다\\. 지난 밤의 일을 자유롭게 토론하고 마피아를 찾아내세요\\."
    )


# ── 투표 ────────────────────────────────────────────────────────────────────

def vote_start_msg(day: int, alive_cnt: int, timeout: int) -> str:
    return (
        f"🗳️ *낮 {esc(str(day))} 투표 시작\\!*\n\n"
        f"생존자 {esc(str(alive_cnt))}명 중 처형할 플레이어를 선택하세요\\.\n"
        f"제한 시간: *{esc(str(timeout))}초*\n\n"
        "> 기권하려면 '기권' 버튼을 누르세요\\."
    )


def final_defense_msg(accused_name: str, seconds: int) -> str:
    return (
        f"🎤 *최종변론*\n\n"
        f"투표 결과 *{esc(accused_name)}* 님이 지목되었습니다\\.\n"
        f"제한 시간 *{esc(str(seconds))}초* 동안 최후 변론을 하세요\\.\n\n"
        "> 변론이 끝나면 찬반\\(처형/생존\\) 투표가 진행됩니다\\."
    )


def judgment_start_msg(accused_name: str, seconds: int) -> str:
    return (
        f"⚖️ *찬반 투표\\!*\n\n"
        f"*{esc(accused_name)}* 님을 처형할까요\\?\n"
        f"제한 시간: *{esc(str(seconds))}초*\n\n"
        "👍 *찬성* \\= 처형  \\|  👎 *반대* \\= 생존\n"
        "> 찬성이 더 많으면 처형됩니다\\. \\(피고인은 투표 불가\\)"
    )


def judgment_progress_msg(accused_name: str, approve: int, reject: int, voted: int, total: int) -> str:
    return (
        f"⚖️ *찬반 투표 진행 중\\.\\.\\.*\n\n"
        f"피고인: *{esc(accused_name)}*\n"
        f"👍 찬성 *{esc(str(approve))}*  \\|  👎 반대 *{esc(str(reject))}*\n\n"
        f"*{esc(str(voted))}/{esc(str(total))}명* 투표 완료"
    )


def judgment_result_msg(accused_name: str, executed: bool, approve: int, reject: int) -> str:
    verdict = "💀 *처형 가결*" if executed else "🕊️ *생존 \\(처형 부결\\)*"
    return (
        f"⚖️ *찬반 투표 결과*\n\n"
        f"피고인: *{esc(accused_name)}*\n"
        f"👍 찬성 *{esc(str(approve))}*  \\|  👎 반대 *{esc(str(reject))}*\n\n"
        f"{verdict}"
    )


def vote_result_msg(executed_name: str | None, executed_role: str | None, reason: str = "") -> str:
    if executed_name is None:
        _reason = esc(reason) if reason else "과반수 미달 또는 동점으로 처형이 보류되었습니다\\."
        return (
            "⚖️ *투표 결과: 처형 없음*\n\n"
            f"_{_reason}_"
        )
    return (
        f"⚖️ *처형\\!*\n\n"
        f"*{esc(executed_name)}* 이\\(가\\) 처형되었습니다\\.\n"
        f"직업: __{esc(executed_role or '???')}__"
    )


def politician_immune_msg(name: str) -> str:
    return (
        f"🎩 *{esc(name)}* 의 정치적 면책권이 발동되었습니다\\!\n"
        "_이번 처형에서 살아남았습니다\\._"
    )


def magician_swap_msg() -> str:
    return "🪄 *마술사의 몸바꿈이 발동되었습니다\\!* 진짜 처형 대상이 바뀌었습니다\\."


# ── 게임 종료 ────────────────────────────────────────────────────────────────

def win_announce_msg(
    winner: WinCondition,
    gs: GameState,
) -> str:
    titles = {
        WinCondition.MAFIA:         "🔴 *마피아의 승리\\!*",
        WinCondition.CITIZEN:       "🔵 *시민팀의 승리\\!*",
        WinCondition.CULT:          "🟣 *교주팀의 승리\\!*",
        WinCondition.SERIAL_KILLER: "🗡️ *연쇄살인마의 승리\\!*",
        WinCondition.JESTER:        "🃏 *어릿광대의 승리\\!*",
        WinCondition.SURVIVOR:      "🛡️ *생존자의 승리\\!*",
    }
    title = titles.get(winner, "🏁 *게임 종료*")

    # 전체 플레이어 역할 공개
    reveal_lines = []
    for p in gs.players.values():
        role = ROLES.get(p.role_key)
        role_name = role.name if role else "알 수 없음"
        status = "🟢" if p.is_alive else "💀"
        reveal_lines.append(
            f"  {status} *{esc(p.display)}* — __{esc(role_name)}__"
        )
    reveal_str = "\n".join(reveal_lines)

    survivor_names = [esc(p.display) for p in gs.alive_players()]
    survivors_str = ", ".join(survivor_names) if survivor_names else "_없음_"

    return (
        f"🎮 {title}\n\n"
        f"🏆 생존자: {survivors_str}\n\n"
        f"📋 *최종 직업 공개:*\n{reveal_str}"
    )


# ── 기타 알림 ────────────────────────────────────────────────────────────────

def mafia_team_msg(mafia_names: list[str]) -> str:
    team_str = "\n".join(f"  • {esc(n)}" for n in mafia_names)
    return (
        "🔪 *마피아 팀 채팅*\n\n"
        f"팀원:\n{team_str}\n\n"
        "> 이 메시지는 팀원 전체에게 전달됩니다\\."
    )


def mafia_kill_submitted_msg(chooser_name: str, target_name: str) -> str:
    return (
        f"🔪 *{esc(chooser_name)}* 이\\(가\\) 오늘 밤 목표를 선택했습니다\\.\n"
        f"대상: *{esc(target_name)}*"
    )


def investigate_result_dm(result: str) -> str:
    return f"🔔 *조사 결과:*\n\n{result}"


def revive_success_dm(revived_name: str) -> str:
    return (
        f"✝️ *부활 성공\\!*\n\n"
        f"*{esc(revived_name)}* 이\\(가\\) 부활했습니다\\."
    )


def player_dead_dm(role_name: str) -> str:
    return (
        "💀 *당신은 사망했습니다\\.*\n\n"
        f"직업: __{esc(role_name)}__\n\n"
        "> 이제 관전자가 됩니다\\. 결과를 지켜봐 주세요\\."
    )


def lover_dead_dm(partner_name: str) -> str:
    return (
        f"💔 *연인 {esc(partner_name)}* 이\\(가\\) 사망했습니다\\.\n\n"
        "__당신도 함께 세상을 떠납니다\\.__"
    )


def dm_not_open_msg(bot_username: str, group_id: int) -> str:
    return (
        "📬 *봇 DM이 열려있지 않습니다\\!*\n\n"
        f"아래 링크를 눌러 봇에게 먼저 메시지를 보내주세요:\n"
        f"[봇 DM 열기](https://t\\.me/{esc(bot_username)}?start=join_{esc(str(group_id))})"
    )


def skip_not_allowed_msg() -> str:
    return "❌ 게임 진행자만 페이즈를 건너뛸 수 있습니다\\."


def game_not_found_msg() -> str:
    return "❌ 진행 중인 게임이 없습니다\\. `/startgame` 으로 게임을 시작하세요\\."


def already_in_game_msg() -> str:
    return "ℹ️ 이미 참가 중인 게임이 있습니다\\."


def game_full_msg(max_p: int) -> str:
    return f"❌ 게임이 가득 찼습니다 \\(최대 {esc(str(max_p))}명\\)\\."


def not_enough_players_msg(current: int, minimum: int) -> str:
    return (
        f"❌ 인원이 부족합니다\\.\n"
        f"현재: *{esc(str(current))}명* / 최소: *{esc(str(minimum))}명*"
    )


def dm_required_players_msg(names: list[str]) -> str:
    name_str = ", ".join(f"*{esc(n)}*" for n in names)
    return (
        f"❌ 다음 플레이어가 아직 봇 DM을 열지 않았습니다:\n"
        f"{name_str}\n\n"
        "> 위 플레이어들이 봇에게 `/start` 를 먼저 보내야 합니다\\."
    )
