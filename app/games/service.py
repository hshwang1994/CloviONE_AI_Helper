"""놀이 비즈니스 규칙 — 방 생명주기 + 이벤트 스트림 + 서버 확정 게임 로직.

결과는 언제나 서버가 확정한다(§13.1) — 랜덤 추첨 당첨자는 secrets.SystemRandom 으로 뽑는다
(클라이언트가 정하지 않음). 이벤트는 append-only 로그(GameEvent)에 방별 순번(event_seq)으로
쌓이고, 폴링이 그 커서로 따라온다. 유니크(room_id, seq) 위반은 SAVEPOINT로 흡수해 재시도한다.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, ValidationAppError
from app.games import repository
from app.games.models import (
    EV_CHAT,
    EV_JOIN,
    EV_LEAVE,
    EV_READY,
    EV_RESET,
    EV_RESULT,
    EV_START,
    EV_VOTE,
    EV_PICK,
    EV_SYSTEM,
    GAME_LADDER,
    GAME_NUMBER,
    GAME_QUICK_VOTE,
    GAME_QUIZ,
    GAME_RANDOM_DRAW,
    GAME_RPS,
    GAME_TEAM_SPLIT,
    GAME_TYPES,
    ROLE_HOST,
    ROLE_PLAYER,
    ROLE_SPECTATOR,
    ROOM_FINISHED,
    ROOM_PLAYING,
    ROOM_WAITING,
    GameEvent,
    GameRoom,
    GameRoomMember,
)
from app.users.models import User

MAX_ROOM_TITLE = 120
MAX_CHAT = 500


def _append_event(db: Session, room: GameRoom, kind: str, *, actor_id, payload: dict, now: datetime) -> GameEvent:
    """방 이벤트를 순번을 붙여 추가한다(동시 추가 시 유니크 충돌을 흡수하고 재시도)."""
    for _ in range(5):
        seq = room.event_seq + 1
        ev = GameEvent(
            room_id=room.id, seq=seq, kind=kind, actor_user_id=actor_id,
            payload_json=json.dumps(payload, ensure_ascii=False), created_at=now,
        )
        try:
            with db.begin_nested():
                db.add(ev)
                db.flush()
            room.event_seq = seq
            db.flush()
            return ev
        except IntegrityError:
            db.refresh(room)  # 다른 요청이 먼저 붙였다 — 순번 다시 계산
    raise ConflictError("이벤트를 기록하지 못했습니다. 잠시 후 다시 시도해 주세요.")


# ── 방 생명주기 ─────────────────────────────────────────────────────────────
def create_room(db: Session, *, host: User, title: str, game_type: str, max_players: int,
                allow_spectators: bool, config: dict, now: datetime) -> GameRoom:
    title = (title or "").strip()
    if not title:
        raise ValidationAppError("방 제목을 입력하세요.")
    if game_type not in GAME_TYPES:
        raise ValidationAppError("지원하지 않는 게임입니다.")
    max_players = max(2, min(int(max_players or 8), 50))
    room = GameRoom(
        title=title[:MAX_ROOM_TITLE], game_type=game_type, host_user_id=host.id,
        status=ROOM_WAITING, max_players=max_players, allow_spectators=bool(allow_spectators),
        config_json=json.dumps(config or {}, ensure_ascii=False), state_json="{}",
        event_seq=0, created_at=now, updated_at=now,
    )
    db.add(room)
    db.flush()
    db.add(GameRoomMember(
        room_id=room.id, user_id=host.id, display_name=host.display_name,
        role=ROLE_HOST, active=True, last_seen=now, joined_at=now,
    ))
    db.flush()
    _append_event(db, room, EV_JOIN, actor_id=host.id, payload={"name": host.display_name, "role": ROLE_HOST}, now=now)
    return room


def join_room(db: Session, room: GameRoom, user: User, *, spectate: bool, now: datetime) -> GameRoomMember:
    existing = repository.get_member(db, room.id, user.id)
    if existing is not None:
        # 재접속 — 다시 활성화(§14).
        was_inactive = not existing.active
        existing.active = True
        existing.last_seen = now
        existing.display_name = user.display_name
        db.flush()
        if was_inactive:
            _append_event(db, room, EV_JOIN, actor_id=user.id, payload={"name": user.display_name, "role": existing.role, "reconnect": True}, now=now)
        return existing

    role = ROLE_SPECTATOR
    if not spectate and room.status == ROOM_WAITING:
        if repository.player_count(db, room.id) < room.max_players:
            role = ROLE_PLAYER
        elif not room.allow_spectators:
            raise ConflictError("방이 가득 찼습니다.")
    elif spectate and not room.allow_spectators:
        raise ConflictError("이 방은 관전을 허용하지 않습니다.")
    member = GameRoomMember(
        room_id=room.id, user_id=user.id, display_name=user.display_name,
        role=role, active=True, last_seen=now, joined_at=now,
    )
    db.add(member)
    db.flush()
    _append_event(db, room, EV_JOIN, actor_id=user.id, payload={"name": user.display_name, "role": role}, now=now)
    return member


def leave_room(db: Session, room: GameRoom, user: User, *, now: datetime) -> None:
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        return
    db.delete(member)
    db.flush()
    _append_event(db, room, EV_LEAVE, actor_id=user.id, payload={"name": user.display_name}, now=now)
    # 방장이 나가면 다른 활성 참여자에게 위임, 없으면 방을 닫는다.
    if room.host_user_id == user.id:
        others = [m for m in repository.members(db, room.id) if m.active and m.user_id != user.id]
        if others:
            new_host = others[0]
            new_host.role = ROLE_HOST
            room.host_user_id = new_host.user_id
            db.flush()
            _append_event(db, room, "system", actor_id=None, payload={"text": f"{new_host.display_name}님이 방장이 되었습니다."}, now=now)
        else:
            room.closed_at = now
            db.flush()


def set_ready(db: Session, room: GameRoom, user: User, *, ready: bool, now: datetime) -> None:
    member = repository.get_member(db, room.id, user.id)
    if member is None or member.role == ROLE_SPECTATOR:
        raise ForbiddenError("참여자만 준비 상태를 바꿀 수 있습니다.")
    member.ready = bool(ready)
    member.last_seen = now
    db.flush()
    _append_event(db, room, EV_READY, actor_id=user.id, payload={"name": user.display_name, "ready": bool(ready)}, now=now)


def chat(db: Session, room: GameRoom, user: User, *, text: str, now: datetime) -> None:
    text = (text or "").strip()
    if not text:
        raise ValidationAppError("메시지를 입력하세요.")
    _append_event(db, room, EV_CHAT, actor_id=user.id, payload={"name": user.display_name, "text": text[:MAX_CHAT]}, now=now)


def _ensure_host(room: GameRoom, user: User) -> None:
    if room.host_user_id != user.id:
        raise ForbiddenError("방장만 할 수 있습니다.")


# ── 게임 로직 (서버 확정) ────────────────────────────────────────────────────
def start_game(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    _ensure_host(room, user)
    if room.status == ROOM_PLAYING:
        raise ConflictError("이미 진행 중입니다.")
    if room.game_type == GAME_RANDOM_DRAW:
        return _run_random_draw(db, room, user, now=now)
    if room.game_type == GAME_TEAM_SPLIT:
        return _run_team_split(db, room, user, now=now)
    if room.game_type == GAME_LADDER:
        return _run_ladder(db, room, user, now=now)
    if room.game_type == GAME_QUICK_VOTE:
        return _open_vote(db, room, user, now=now)
    if room.game_type == GAME_NUMBER:
        return _open_number(db, room, user, now=now)
    if room.game_type == GAME_RPS:
        return _open_rps(db, room, user, now=now)
    if room.game_type == GAME_QUIZ:
        return _open_quiz(db, room, user, now=now)
    raise ValidationAppError("지원하지 않는 게임입니다.")


def _run_random_draw(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    players = [m for m in repository.members(db, room.id) if m.active and m.role != ROLE_SPECTATOR]
    if not players:
        raise ConflictError("추첨할 참여자가 없습니다.")
    config = json.loads(room.config_json or "{}")
    winners_n = max(1, min(int(config.get("winners", 1) or 1), len(players)))
    rng = secrets.SystemRandom()
    winners = rng.sample(players, winners_n)  # 서버가 공정하게 확정(§13.1)
    result = [{"user_id": m.user_id, "name": m.display_name} for m in winners]
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={}, now=now)
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload={"winners": result}, now=now)
    return room


def _run_team_split(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    players = [m for m in repository.members(db, room.id) if m.active and m.role != ROLE_SPECTATOR]
    if len(players) < 2:
        raise ConflictError("팀을 나눌 참여자가 2명 이상이어야 합니다.")
    config = json.loads(room.config_json or "{}")
    n_teams = max(2, min(int(config.get("teams", 2) or 2), len(players)))  # 팀 수는 참여자 수 이하
    shuffled = list(players)
    secrets.SystemRandom().shuffle(shuffled)  # 서버가 공정하게 섞는다(§13.1)
    teams: list[list[dict]] = [[] for _ in range(n_teams)]
    for i, m in enumerate(shuffled):
        teams[i % n_teams].append({"user_id": m.user_id, "name": m.display_name})  # 라운드로빈=균등 분배
    result = {"teams": teams}
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={}, now=now)
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload=result, now=now)
    return room


def _run_ladder(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    players = [m for m in repository.members(db, room.id) if m.active and m.role != ROLE_SPECTATOR]
    if len(players) < 2:
        raise ConflictError("사다리를 탈 참여자가 2명 이상이어야 합니다.")
    config = json.loads(room.config_json or "{}")
    outcomes = [str(o) for o in (config.get("options") or [])]
    if not outcomes:
        raise ConflictError("사다리 결과(도착지)를 1개 이상 넣어 주세요.")
    pool = list(outcomes)
    while len(pool) < len(players):
        pool.append("꽝")  # 결과가 참여자보다 적으면 꽝으로 채운다(각자 하나씩 배정)
    pool = pool[: len(players)]
    secrets.SystemRandom().shuffle(pool)  # 서버가 공정하게 섞어 1:1 배정(§13.1)
    assignments = [
        {"user_id": m.user_id, "name": m.display_name, "outcome": pool[i]}
        for i, m in enumerate(players)
    ]
    result = {"assignments": assignments}
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={}, now=now)
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload=result, now=now)
    return room


# ── 빠른 투표 ────────────────────────────────────────────────────────────────
# 방장이 선택지를 열고(_open_vote → playing), 참여자가 투표하고(submit_vote), 방장이 종료하면
# (finish_game) 서버가 집계·확정한다(§13.1). 개표 결과(당첨 선택지)는 서버가 정한다.
def _open_vote(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    config = json.loads(room.config_json or "{}")
    question = str(config.get("question", "") or "")
    options = [str(o) for o in (config.get("options") or [])]
    if len(options) < 2:
        raise ConflictError("선택지가 2개 이상이어야 합니다.")
    room.status = ROOM_PLAYING
    room.state_json = json.dumps({"question": question, "options": options, "votes": {}}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={"question": question, "options": options}, now=now)
    return room


def submit_vote(db: Session, room: GameRoom, user: User, *, option_index: int, now: datetime) -> None:
    if room.game_type != GAME_QUICK_VOTE:
        raise ValidationAppError("투표할 수 있는 게임이 아닙니다.")
    if room.status != ROOM_PLAYING:
        raise ConflictError("투표가 열려 있지 않습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None or not member.active or member.role == ROLE_SPECTATOR:
        raise ForbiddenError("참여자만 투표할 수 있습니다.")
    state = json.loads(room.state_json or "{}")
    options = state.get("options", [])
    if not (0 <= option_index < len(options)):
        raise ValidationAppError("잘못된 선택지입니다.")
    votes = dict(state.get("votes", {}))
    votes[user.id] = option_index  # 재투표 시 마지막 선택으로 덮어쓴다.
    state["votes"] = votes
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_VOTE, actor_id=user.id,
                  payload={"name": user.display_name, "option": option_index, "label": options[option_index]}, now=now)


def finish_game(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    """방장이 진행 중인 게임(투표/숫자 눈치)을 종료 → 서버가 결과 확정."""
    _ensure_host(room, user)
    if room.status != ROOM_PLAYING:
        raise ConflictError("진행 중인 게임이 없습니다.")
    if room.game_type == GAME_QUICK_VOTE:
        return _finish_vote(db, room, user, now=now)
    if room.game_type == GAME_NUMBER:
        return _finish_number(db, room, user, now=now)
    if room.game_type == GAME_RPS:
        return _finish_rps(db, room, user, now=now)
    raise ValidationAppError("종료할 게임이 없습니다.")


def _finish_vote(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    state = json.loads(room.state_json or "{}")
    options = state.get("options", [])
    votes = state.get("votes", {})
    counts = [0] * len(options)
    for idx in votes.values():
        if isinstance(idx, int) and 0 <= idx < len(options):
            counts[idx] += 1
    top = max(counts) if counts else 0
    winners = [options[i] for i, c in enumerate(counts) if c == top and top > 0]  # 서버가 확정(동점이면 공동)
    result = {"question": state.get("question", ""), "options": options,
              "counts": counts, "winners": winners, "total": sum(counts)}
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload=result, now=now)
    return room


# ── 숫자 눈치 ────────────────────────────────────────────────────────────────
# 방장이 범위를 열고(_open_number), 참여자가 몰래 숫자를 제출(submit_number)한다. 진행 중엔
# 남의 선택을 감춘다(public_state). 종료하면 서버가 공개해 '가장 낮은 유일 숫자'를 확정한다.
def _open_number(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    config = json.loads(room.config_json or "{}")
    lo = int(config.get("min", 1) or 1)
    hi = int(config.get("max", 10) or 10)
    if hi <= lo:
        hi = lo + 1
    room.status = ROOM_PLAYING
    room.state_json = json.dumps({"min": lo, "max": hi, "picks": {}}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={"min": lo, "max": hi}, now=now)
    return room


def submit_number(db: Session, room: GameRoom, user: User, *, value: int, now: datetime) -> None:
    if room.game_type != GAME_NUMBER:
        raise ValidationAppError("숫자를 낼 수 있는 게임이 아닙니다.")
    if room.status != ROOM_PLAYING:
        raise ConflictError("숫자 제출이 열려 있지 않습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None or not member.active or member.role == ROLE_SPECTATOR:
        raise ForbiddenError("참여자만 숫자를 낼 수 있습니다.")
    state = json.loads(room.state_json or "{}")
    lo, hi = int(state.get("min", 1)), int(state.get("max", 10))
    if not (lo <= value <= hi):
        raise ValidationAppError(f"{lo}~{hi} 사이의 숫자를 내세요.")
    picks = dict(state.get("picks", {}))
    picks[user.id] = value  # 재제출 시 마지막 값으로 덮어쓴다.
    state["picks"] = picks
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)


def _finish_number(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    state = json.loads(room.state_json or "{}")
    picks = state.get("picks", {})
    names = {m.user_id: m.display_name for m in repository.members(db, room.id)}
    # 숫자별 제출자 목록.
    by_number: dict[int, list[str]] = {}
    for uid, val in picks.items():
        if isinstance(val, int):
            by_number.setdefault(val, []).append(uid)
    # '가장 낮은 유일 숫자'(정확히 한 명이 낸 숫자 중 최소)를 낸 사람이 승리.
    winner = None
    for num in sorted(by_number):
        if len(by_number[num]) == 1:
            uid = by_number[num][0]
            winner = {"user_id": uid, "name": names.get(uid, ""), "number": num}
            break
    picks_view = sorted(
        [{"user_id": uid, "name": names.get(uid, ""), "number": val} for uid, val in picks.items() if isinstance(val, int)],
        key=lambda p: p["number"],
    )
    result = {"picks": picks_view, "winner": winner, "min": state.get("min"), "max": state.get("max")}
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload=result, now=now)
    return room


# ── 가위바위보 ───────────────────────────────────────────────────────────────
# 0=가위, 1=바위, 2=보. BEATS[a]=b 는 'a가 b를 이긴다'. 정확히 두 종류만 나오면 이기는 쪽 승리,
# 아니면(전원 같음/세 종류 다 나옴) 무승부. 진행 중엔 남의 선택을 감춘다(public_state).
_RPS_LABELS = ["가위", "바위", "보"]
_RPS_BEATS = {0: 2, 2: 1, 1: 0}


def _open_rps(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    room.status = ROOM_PLAYING
    room.state_json = json.dumps({"choices": {}}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={}, now=now)
    return room


def submit_rps(db: Session, room: GameRoom, user: User, *, choice: int, now: datetime) -> None:
    if room.game_type != GAME_RPS:
        raise ValidationAppError("가위바위보 게임이 아닙니다.")
    if room.status != ROOM_PLAYING:
        raise ConflictError("아직 낼 수 없습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None or not member.active or member.role == ROLE_SPECTATOR:
        raise ForbiddenError("참여자만 낼 수 있습니다.")
    if choice not in (0, 1, 2):
        raise ValidationAppError("가위/바위/보 중에서 내세요.")
    state = json.loads(room.state_json or "{}")
    choices = dict(state.get("choices", {}))
    choices[user.id] = choice  # 재제출 시 마지막 선택으로 덮어쓴다.
    state["choices"] = choices
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)


def _finish_rps(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    state = json.loads(room.state_json or "{}")
    choices = {uid: c for uid, c in state.get("choices", {}).items() if isinstance(c, int) and c in (0, 1, 2)}
    names = {m.user_id: m.display_name for m in repository.members(db, room.id)}
    present = set(choices.values())
    winners: list[dict] = []
    win_label = None
    outcome = "draw"
    if len(present) == 2:
        a, b = list(present)
        win_choice = a if _RPS_BEATS[a] == b else b
        win_label = _RPS_LABELS[win_choice]
        outcome = "win"
        winners = [{"user_id": uid, "name": names.get(uid, "")} for uid, c in choices.items() if c == win_choice]
    reveal = sorted(
        [{"user_id": uid, "name": names.get(uid, ""), "choice": _RPS_LABELS[c]} for uid, c in choices.items()],
        key=lambda x: x["name"],
    )
    result = {"outcome": outcome, "winners": winners, "win_choice": win_label, "reveal": reveal}
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload=result, now=now)
    return room


# ── 실시간 퀴즈 ──────────────────────────────────────────────────────────────
# 방장이 문제를 미리 넣고 라운드를 진행한다. phase: answering(참여자 응답, 남의 답·정답 비공개)
# → revealed(방장이 정답 공개·채점) → 다음 라운드 or 종료(누적 점수판 확정). 정답/채점은 서버만.
QUIZ_ANSWERING = "answering"
QUIZ_REVEALED = "revealed"


def _open_quiz(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    config = json.loads(room.config_json or "{}")
    questions = config.get("questions") or []
    if not questions:
        raise ConflictError("문제를 1개 이상 넣어 주세요.")
    room.status = ROOM_PLAYING
    room.state_json = json.dumps(
        {"questions": questions, "round": 0, "phase": QUIZ_ANSWERING, "answers": {}, "scores": {}},
        ensure_ascii=False,
    )
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={"rounds": len(questions)}, now=now)
    return room


def submit_quiz_answer(db: Session, room: GameRoom, user: User, *, option_index: int, now: datetime) -> None:
    if room.game_type != GAME_QUIZ:
        raise ValidationAppError("퀴즈 게임이 아닙니다.")
    if room.status != ROOM_PLAYING:
        raise ConflictError("진행 중인 퀴즈가 없습니다.")
    state = json.loads(room.state_json or "{}")
    if state.get("phase") != QUIZ_ANSWERING:
        raise ConflictError("지금은 답을 낼 수 없습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None or not member.active or member.role == ROLE_SPECTATOR:
        raise ForbiddenError("참여자만 답할 수 있습니다.")
    questions = state.get("questions", [])
    rnd = int(state.get("round", 0))
    if not (0 <= rnd < len(questions)):
        raise ConflictError("진행 중인 문제가 없습니다.")
    n_opts = len(questions[rnd].get("options", []))
    if not (0 <= option_index < n_opts):
        raise ValidationAppError("보기 범위를 벗어났습니다.")
    answers = dict(state.get("answers", {}))
    answers[user.id] = option_index  # 재응답 시 마지막 답으로 덮어쓴다.
    state["answers"] = answers
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)


def reveal_quiz(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    _ensure_host(room, user)
    if room.game_type != GAME_QUIZ or room.status != ROOM_PLAYING:
        raise ConflictError("공개할 퀴즈가 없습니다.")
    state = json.loads(room.state_json or "{}")
    if state.get("phase") != QUIZ_ANSWERING:
        raise ConflictError("이미 공개된 문제입니다.")
    questions = state.get("questions", [])
    rnd = int(state.get("round", 0))
    correct = int(questions[rnd].get("answer", 0)) if 0 <= rnd < len(questions) else 0
    answers = state.get("answers", {})
    scores = dict(state.get("scores", {}))
    for uid, ans in answers.items():
        if isinstance(ans, int) and ans == correct:
            scores[uid] = int(scores.get(uid, 0)) + 1  # 서버가 채점(§13.1)
    state["scores"] = scores
    state["phase"] = QUIZ_REVEALED
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_SYSTEM, actor_id=user.id, payload={"quiz": "revealed", "round": rnd}, now=now)
    return room


def next_quiz(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    _ensure_host(room, user)
    if room.game_type != GAME_QUIZ or room.status != ROOM_PLAYING:
        raise ConflictError("진행 중인 퀴즈가 없습니다.")
    state = json.loads(room.state_json or "{}")
    if state.get("phase") != QUIZ_REVEALED:
        raise ConflictError("먼저 정답을 공개하세요.")
    questions = state.get("questions", [])
    rnd = int(state.get("round", 0))
    if rnd + 1 >= len(questions):
        # 마지막 문제 → 종료. 누적 점수판 확정.
        scores = state.get("scores", {})
        names = {m.user_id: m.display_name for m in repository.members(db, room.id)}
        board = sorted(
            ({"user_id": uid, "name": names.get(uid, ""), "score": int(sc)} for uid, sc in scores.items()),
            key=lambda x: (-x["score"], x["name"]),
        )
        top = board[0]["score"] if board else 0
        result = {"scoreboard": board, "total_rounds": len(questions),
                  "winners": [b["name"] for b in board if b["score"] == top and top > 0]}
        room.status = ROOM_FINISHED
        room.state_json = json.dumps({"result": result}, ensure_ascii=False)
        db.flush()
        _append_event(db, room, EV_RESULT, actor_id=user.id, payload=result, now=now)
        return room
    state["round"] = rnd + 1
    state["phase"] = QUIZ_ANSWERING
    state["answers"] = {}
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_SYSTEM, actor_id=user.id, payload={"quiz": "next", "round": rnd + 1}, now=now)
    return room


def _quiz_public(state: dict, user_id: str) -> dict:
    """퀴즈 진행 중 클라이언트에 안전한 뷰. answering: 남의 답·정답 비공개. revealed: 정답·채점 공개."""
    questions = state.get("questions", [])
    rnd = int(state.get("round", 0))
    phase = state.get("phase", QUIZ_ANSWERING)
    q = questions[rnd] if 0 <= rnd < len(questions) else {"q": "", "options": []}
    answers = state.get("answers", {})
    scores = state.get("scores", {})
    view = {
        "round": rnd,
        "total": len(questions),
        "phase": phase,
        "question": q.get("q", ""),
        "options": q.get("options", []),
        "submitted_count": len(answers),
        "your_answer": answers.get(user_id),
        "scores": _score_view(scores, state),
    }
    if phase == QUIZ_REVEALED:
        view["answer"] = int(q.get("answer", 0))  # 정답 보기 index
        view["your_correct"] = answers.get(user_id) == int(q.get("answer", 0))
    return view


def _score_view(scores: dict, state: dict) -> list[dict]:
    # 점수판(이름은 state에 없으니 uid→점수만; 이름 매핑은 finish 시 result에 담는다). 진행 중엔
    # 이름 없이 내 점수만 유의미하므로 uid 그대로 두되 정렬만 한다.
    return sorted(({"user_id": uid, "score": int(sc)} for uid, sc in scores.items()), key=lambda x: -x["score"])


def public_state(room: GameRoom, user_id: str) -> dict:
    """클라이언트에 내려줄 안전한 상태. 숫자 눈치는 진행 중 남의 선택을 감추고 제출 여부/수만
    노출한다(반전의 재미 + 눈치 게임 본질). 그 외 게임/상태는 state_json 그대로."""
    state = json.loads(room.state_json or "{}")
    if room.game_type == GAME_NUMBER and room.status == ROOM_PLAYING:
        picks = state.get("picks", {})
        return {
            "min": state.get("min"),
            "max": state.get("max"),
            "submitted_count": len(picks),
            "you_submitted": user_id in picks,
            "your_pick": picks.get(user_id),
        }
    if room.game_type == GAME_RPS and room.status == ROOM_PLAYING:
        choices = state.get("choices", {})
        return {
            "submitted_count": len(choices),
            "you_submitted": user_id in choices,
            "your_choice": choices.get(user_id),  # 0/1/2 (본인 것만)
        }
    if room.game_type == GAME_QUIZ and room.status == ROOM_PLAYING:
        return _quiz_public(state, user_id)
    return state


def reset_room(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    _ensure_host(room, user)
    room.status = ROOM_WAITING
    room.state_json = "{}"
    for m in repository.members(db, room.id):
        m.ready = False
    db.flush()
    _append_event(db, room, EV_RESET, actor_id=user.id, payload={}, now=now)
    return room


def touch_presence(db: Session, room: GameRoom, user: User, *, now: datetime) -> None:
    """폴링마다 호출 — 재접속 감지용 last_seen/active 갱신."""
    member = repository.get_member(db, room.id, user.id)
    if member is not None and (not member.active or (now - member.last_seen).total_seconds() > 2):
        member.active = True
        member.last_seen = now
        db.flush()
