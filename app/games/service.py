"""놀이 비즈니스 규칙 — 방 생명주기 + 이벤트 스트림 + 서버 확정 게임 로직.

결과는 언제나 서버가 확정한다(§13.1) — 랜덤 추첨 당첨자는 secrets.SystemRandom 으로 뽑는다
(클라이언트가 정하지 않음). 이벤트는 append-only 로그(GameEvent)에 방별 순번(event_seq)으로
쌓이고, 폴링이 그 커서로 따라온다. 유니크(room_id, seq) 위반은 SAVEPOINT로 흡수해 재시도한다.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.presence import should_touch
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

# 게임별 기본 제한 시간(초). 0=무제한. 방 만들 때 config.timer_seconds 로 덮어쓴다.
DEFAULT_TIMERS = {GAME_RPS: 15, GAME_QUIZ: 25, GAME_NUMBER: 0, GAME_QUICK_VOTE: 0}


def _timer_from_config(config: dict, game_type: str, now: datetime) -> tuple[int, str | None]:
    """방 설정에서 제한 시간을 읽어 (초, 마감 ISO)를 돌려준다. 0/미설정이면 (0, None)=무제한.
    마감(deadline)은 서버 시계 기준이라 모든 참여자가 같은 카운트다운을 본다."""
    default = DEFAULT_TIMERS.get(game_type, 0)
    timer = max(0, min(int(config.get("timer_seconds", default) or 0), 300))
    if timer <= 0:
        return 0, None
    return timer, (now + timedelta(seconds=timer)).isoformat()


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


def _cas_update_state(db: Session, room: GameRoom, mutate) -> dict:
    """room.state_json을 낙관적 동시성 제어(compare-and-swap)로 갱신한다.

    앱은 동기 핸들러를 스레드풀에서 돌린다(app/core/db.py) — 참여자 여럿이 거의 동시에
    제출하면 각자 독립된 DB 세션이 같은 옛 state_json을 읽어(WAL 리더는 쓰기 잠금과 무관하게
    커밋된 스냅샷을 읽는다) 자기 제출 하나만 반영한 새 state를 계산한다. 예전처럼
    `room.state_json = json.dumps(state); db.flush()`로 무조건 덮어쓰면, 나중에 자기 차례가
    된(SQLite는 단일 writer라 뒤 트랜잭션은 앞이 커밋할 때까지 대기했다가 쓴다) 쪽이 자기가
    읽었던(이미 낡은) state를 기준으로 써서 먼저 커밋된 제출을 통째로 지워버렸다 — 무승부
    판정과 무관하게 "동시 제출 유실" 그 자체가 버그였다.
    `UPDATE ... WHERE state_json = 내가 읽은 값`으로 "그 사이에 아무도 안 바꿨을 때만" 쓰고
    (0행이면 충돌 — 다른 요청이 먼저 썼다는 뜻), 그러면 room을 다시 읽어 mutate를 최신 state에
    다시 적용해 재시도한다(최대 5회, 유실 없이 §13.1 서버 확정 유지).

    mutate(state: dict) -> dict 는 현재 state를 받아 새 state를 돌려주는 순수 함수다. 검증 실패
    (ValidationAppError 등)는 그대로 위로 올라간다 — 재시도 대상은 '쓰기 충돌'뿐이다."""
    for _ in range(5):
        old_json = room.state_json or "{}"
        new_state = mutate(json.loads(old_json))
        new_json = json.dumps(new_state, ensure_ascii=False)
        result = db.execute(
            update(GameRoom)
            .where(GameRoom.id == room.id, GameRoom.state_json == old_json)
            .values(state_json=new_json)
        )
        # 성공/실패 모두 refresh — 성공했으면 커밋 전이라도 우리 세션엔 이미 반영된 값이고,
        # 실패했으면(0행) 다른 요청이 먼저 쓴 최신 값을 가져와야 다음 시도의 mutate가 그
        # 위에서 다시 계산된다. room.state_json을 직접 대입하지 않는 이유: 그러면 SQLAlchemy가
        # 이 속성을 '더티'로 표시해, 이후 이 요청 안의 다른 flush가 (이미 위 UPDATE로 반영된)
        # 같은 값을 조건 없이 다시 쓰려 든다 — refresh로 커밋된 값을 그대로 불러와 깨끗한
        # 상태로 유지한다.
        db.refresh(room)
        if result.rowcount == 1:
            return new_state
    raise ConflictError("다른 참여자의 제출과 겹쳤습니다. 다시 시도해 주세요.")


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
    # 진행 중/종료된 방에 그냥 입장하면 위 분기가 모두 거짓이라 role이 관전자로 남는다 —
    # 관전 불허 방에는 그 경로로도 못 들어가게 막는다(관전 불허 계약을 모든 경로에 적용).
    if role == ROLE_SPECTATOR and not room.allow_spectators:
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
    # 방장이 나가면 다른 활성 '참여자'에게 위임(관전자 제외), 없으면 방을 닫는다.
    if room.host_user_id == user.id:
        others = [m for m in repository.members(db, room.id)
                  if m.active and m.user_id != user.id and m.role != ROLE_SPECTATOR]
        if others:
            new_host = others[0]
            new_host.role = ROLE_HOST
            room.host_user_id = new_host.user_id
            db.flush()
            _append_event(db, room, "system", actor_id=None, payload={"text": f"{new_host.display_name}님이 방장이 되었습니다."}, now=now)
        else:
            room.closed_at = now
            db.flush()


# 아무도 이 시간(초) 동안 폴링하지 않은 열린 방은 버려진 것으로 보고 자동으로 닫는다. 진행 중인
# 방은 참여자가 1.2초마다 폴링하므로 절대 이 값에 안 걸린다 — 브라우저만 닫고 떠난 방만 정리된다.
IDLE_ROOM_SECONDS = 180

# 최근 이 시간(초) 안에 폴링한 참여자만 '현재 있는' 사람으로 본다. 탭만 닫고 떠난(나가기 안 누른)
# 유령이 추첨/팀나누기/사다리 대상이나 결과 승자로 잡히는 걸 막는다. 백그라운드 탭 폴링 스로틀을
# 견디도록 넉넉히 둔다(active 플래그를 영구히 내리지 않고, 액션 시점에만 걸러 재접속에 안전).
PRESENCE_SECONDS = 90


def _present_players(db: Session, room: GameRoom, now: datetime) -> list[GameRoomMember]:
    """지금 방에 실제로 있는 참여자(활성 + 최근 폴링 + 비관전)만. 서버 확정 게임의 대상 풀."""
    cutoff = now - timedelta(seconds=PRESENCE_SECONDS)
    return [
        m for m in repository.members(db, room.id)
        if m.active and m.role != ROLE_SPECTATOR and m.last_seen >= cutoff
    ]


def cleanup_idle_rooms(db: Session, *, now: datetime) -> int:
    """폴링이 끊긴 지 오래된 열린 방을 닫는다(목록에 유령 방이 남는 걸 막는다). 닫은 방 수 반환."""
    cutoff = now - timedelta(seconds=IDLE_ROOM_SECONDS)
    last_seen = repository.last_seen_by_room(db)
    closed = 0
    for room in repository.list_open_rooms(db):
        last = last_seen.get(room.id)
        if last is None or last < cutoff:
            room.closed_at = now
            closed += 1
    if closed:
        db.flush()
    return closed


def disband_room(db: Session, room: GameRoom, user: User, *, now: datetime) -> None:
    """방장이 방을 파한다 — 방을 닫아(closed_at) 목록에서 사라지게 하고, 남은 참여자는
    다음 폴링에서 방을 못 찾아(404) 목록으로 돌아간다. 히스토리를 남기지 않는다(§16.1)."""
    _ensure_host(room, user)
    _append_event(db, room, EV_SYSTEM, actor_id=user.id,
                  payload={"text": "방장이 방을 파했습니다.", "disbanded": True}, now=now)
    room.status = ROOM_FINISHED
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
    # WAITING 에서만 시작할 수 있다. 즉시 종료 게임(추첨/팀나누기/사다리)은 PLAYING을 거치지 않고
    # 바로 FINISHED가 되므로, 'PLAYING만 막는' 예전 가드로는 끝난 방에 /start를 다시 보내 결과를
    # 무한 재추첨할 수 있었다(§13.1 공정성 훼손). 다시 하려면 반드시 초기화(reset)를 거친다.
    if room.status != ROOM_WAITING:
        raise ConflictError("이미 시작했거나 끝난 방입니다. 다시 하려면 먼저 초기화하세요.")
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
    players = _present_players(db, room, now)  # 자리를 뜬 유령은 추첨 대상에서 제외
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
    players = _present_players(db, room, now)  # 자리를 뜬 유령은 팀 배정에서 제외
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


def _build_ladder(n: int, rng) -> tuple[int, list[dict]]:
    """참여자 n명짜리 사다리(아미다쿠지)의 가로줄을 만든다. 각 행에서 인접한 두 세로줄 사이에
    확률적으로 가로줄을 놓되, 한 점에 두 줄이 겹치지 않게 같은 행에서는 건너뛴다(c += 2).
    반환: (행 수, 가로줄 목록 [{"row","col"}] — 열 col과 col+1 사이의 가로줄)."""
    rows = max(6, n * 2)
    rungs: list[dict] = []
    for r in range(rows):
        c = 0
        while c < n - 1:
            if rng.random() < 0.45:
                rungs.append({"row": r, "col": c})
                c += 2
            else:
                c += 1
    return rows, rungs


def _walk_ladder(start_col: int, rows: int, rung_set: set[tuple[int, int]]) -> int:
    """시작 세로줄에서 사다리를 따라 내려가 도착 세로줄을 구한다(각 행에서 걸린 가로줄로 좌우 이동)."""
    col = start_col
    for r in range(rows):
        if (r, col) in rung_set:
            col += 1
        elif col > 0 and (r, col - 1) in rung_set:
            col -= 1
    return col


def _run_ladder(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    players = _present_players(db, room, now)  # 자리를 뜬 유령은 사다리에서 제외
    if len(players) < 2:
        raise ConflictError("사다리를 탈 참여자가 2명 이상이어야 합니다.")
    config = json.loads(room.config_json or "{}")
    outcomes = [str(o) for o in (config.get("options") or [])]
    if not outcomes:
        raise ConflictError("사다리 결과(도착지)를 1개 이상 넣어 주세요.")
    n = len(players)
    pool = list(outcomes)
    while len(pool) < n:
        pool.append("꽝")  # 결과가 참여자보다 적으면 꽝으로 채운다(각자 하나씩 배정)
    rng = secrets.SystemRandom()
    rng.shuffle(pool)  # 먼저 섞고
    pool = pool[:n]     # 그 다음 자른다 — 도착지가 참여자보다 많아도 뒤쪽이 공정하게 배정된다(truncate-after-shuffle)
    rows, rungs = _build_ladder(n, rng)  # 서버가 사다리 구조를 확정 → 프런트가 정직하게 그린다
    rung_set = {(g["row"], g["col"]) for g in rungs}
    assignments = []
    for i, m in enumerate(players):
        end = _walk_ladder(i, rows, rung_set)  # 사다리를 실제로 따라간 결과(구조와 일치)
        assignments.append({"user_id": m.user_id, "name": m.display_name, "outcome": pool[end], "end_col": end})
    result = {
        "columns": [{"user_id": m.user_id, "name": m.display_name} for m in players],
        "outcomes": pool,
        "rungs": rungs,
        "rows": rows,
        "assignments": assignments,
    }
    room.status = ROOM_FINISHED
    room.state_json = json.dumps({"result": result}, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={}, now=now)
    _append_event(db, room, EV_RESULT, actor_id=user.id, payload={"assignments": assignments}, now=now)
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
    timer, deadline = _timer_from_config(config, GAME_QUICK_VOTE, now)
    state = {"question": question, "options": options, "votes": {}}
    if deadline:
        state["timer_seconds"] = timer
        state["deadline"] = deadline
    room.status = ROOM_PLAYING
    room.state_json = json.dumps(state, ensure_ascii=False)
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

    def _apply(state: dict) -> dict:
        options = state.get("options", [])
        if not (0 <= option_index < len(options)):
            raise ValidationAppError("잘못된 선택지입니다.")
        votes = dict(state.get("votes", {}))
        votes[user.id] = option_index  # 재투표 시 마지막 선택으로 덮어쓴다.
        state["votes"] = votes
        return state

    new_state = _cas_update_state(db, room, _apply)  # 동시 투표가 서로 덮어쓰지 않게(CAS)
    _append_event(db, room, EV_VOTE, actor_id=user.id,
                  payload={"name": user.display_name, "option": option_index,
                           "label": new_state["options"][option_index]}, now=now)


# 타임아웃 자동 확정의 행위자(방장 없이 서버가 확정) — _finish_* 는 actor의 .id 만 쓰므로 None 이면 충분.
_SYSTEM_ACTOR = type("_SystemActor", (), {"id": None})()


def maybe_autoresolve(db: Session, room: GameRoom, *, now: datetime) -> None:
    """진행 중인 타이머 게임의 마감이 지났으면 서버가 방장 없이도 자동 확정한다. 폴링(room_state)
    진입마다 호출된다 — 방장이 자리를 비워도 카운트다운 0에서 멈추지 않는다(방장 브라우저 비의존)."""
    if room.status != ROOM_PLAYING:
        return
    state = json.loads(room.state_json or "{}")
    deadline = state.get("deadline")
    if not deadline:
        return
    try:
        dt = datetime.fromisoformat(str(deadline))
    except (ValueError, TypeError):
        return
    if now < dt:
        return
    gt = room.game_type
    if gt == GAME_QUICK_VOTE:
        _finish_vote(db, room, _SYSTEM_ACTOR, now=now)
    elif gt == GAME_NUMBER:
        _finish_number(db, room, _SYSTEM_ACTOR, now=now)
    elif gt == GAME_RPS:
        if state.get("mode") == "tournament":
            _finish_rps_tournament(db, room, _SYSTEM_ACTOR, state, now=now)
        else:
            _finish_rps(db, room, _SYSTEM_ACTOR, now=now)
    elif gt == GAME_QUIZ:
        if state.get("phase") == QUIZ_ANSWERING:
            _reveal_quiz(db, room, None, now=now)  # 답변 마감 → 채점 공개(다음 문제는 방장이 진행)


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
        state = json.loads(room.state_json or "{}")
        if state.get("mode") == "tournament":
            return _finish_rps_tournament(db, room, user, state, now=now)
        return _finish_rps(db, room, user, now=now)
    raise ValidationAppError("종료할 게임이 없습니다.")


def _finish_rps_tournament(db, room, user, state, *, now) -> GameRoom:
    """방장/타임아웃이 현재 라운드를 마감 → 미결 대진은 서버가 무작위로 채우고 다음 라운드/챔피언."""
    _tournament_advance(db, room, state, now=now, force=True)
    if room.status == ROOM_PLAYING:  # 챔피언이 아직 안 나옴 → 다음 라운드로 넘어감
        room.state_json = json.dumps(state, ensure_ascii=False)
        db.flush()
        _append_event(db, room, EV_SYSTEM, actor_id=user.id,
                      payload={"tournament": "round_advanced", "round": state.get("round_idx")}, now=now)
    return room


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
    timer, deadline = _timer_from_config(config, GAME_NUMBER, now)
    state = {"min": lo, "max": hi, "picks": {}}
    if deadline:
        state["timer_seconds"] = timer
        state["deadline"] = deadline
    room.status = ROOM_PLAYING
    room.state_json = json.dumps(state, ensure_ascii=False)
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

    def _apply(state: dict) -> dict:
        lo, hi = int(state.get("min", 1)), int(state.get("max", 10))
        if not (lo <= value <= hi):
            raise ValidationAppError(f"{lo}~{hi} 사이의 숫자를 내세요.")
        picks = dict(state.get("picks", {}))
        picks[user.id] = value  # 재제출 시 마지막 값으로 덮어쓴다.
        state["picks"] = picks
        return state

    _cas_update_state(db, room, _apply)  # 동시 제출이 서로 덮어쓰지 않게(CAS)
    _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)


def _finish_number(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    state = json.loads(room.state_json or "{}")
    # 지금 방에 있는 참여자만 집계 — 나갔거나 관전자로 재입장한 사람의 옛 숫자로 '유령'이 이기는 걸 막는다.
    members = _present_players(db, room, now)
    names = {m.user_id: m.display_name for m in members}
    picks = {uid: v for uid, v in state.get("picks", {}).items() if uid in names}
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
    config = json.loads(room.config_json or "{}")
    mode = "tournament" if str(config.get("mode", "single")) == "tournament" else "single"
    timer, deadline = _timer_from_config(config, GAME_RPS, now)
    if mode == "tournament":
        return _open_rps_tournament(db, room, user, timer=timer, deadline=deadline, now=now)
    state: dict = {"choices": {}, "mode": "single"}
    if deadline:
        state["timer_seconds"] = timer
        state["deadline"] = deadline  # 카운트다운 마감(서버 기준)
    room.status = ROOM_PLAYING
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={"timer_seconds": timer, "mode": "single"}, now=now)
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
    if state.get("mode") == "tournament":
        _tournament_submit(db, room, user, state, choice=choice, now=now)
        return

    def _apply(state: dict) -> dict:
        choices = dict(state.get("choices", {}))
        choices[user.id] = choice  # 재제출 시 마지막 선택으로 덮어쓴다.
        state["choices"] = choices
        return state

    _cas_update_state(db, room, _apply)  # 동시 제출이 서로 덮어쓰지 않게(CAS)
    _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)


# ── 가위바위보 토너먼트(단판 승자 진출) ──────────────────────────────────────────
# 참여자를 무작위로 짝지어 각 대진에서 가위바위보 1:1. 두 선택이 다르면 그 자리에서 승부가 나고,
# 같으면(비김) 그 대진만 다시 낸다. 라운드의 모든 대진이 끝나면 승자들로 다음 라운드를 짠다
# (홀수면 한 명 부전승). 마지막 한 명이 챔피언. 시간이 끝나면 서버가 안 낸 쪽을 무작위로 채우고,
# 강제 종료 시 비김은 동전던지기로 가른다(§13.1 서버 확정).
def _new_match(a: tuple[str, str], b: tuple[str, str] | None) -> dict:
    if b is None:  # 부전승
        return {"a": a[0], "b": None, "a_name": a[1], "b_name": None,
                "a_choice": None, "b_choice": None, "winner": a[0], "done": True, "bye": True, "replayed": 0}
    return {"a": a[0], "b": b[0], "a_name": a[1], "b_name": b[1],
            "a_choice": None, "b_choice": None, "winner": None, "done": False, "bye": False, "replayed": 0}


def _pair_round(entrants: list[tuple[str, str]]) -> list[dict]:
    """(uid, name) 목록을 두 명씩 대진으로 묶는다. 홀수면 마지막 한 명은 부전승."""
    matches: list[dict] = []
    i = 0
    while i < len(entrants):
        if i + 1 < len(entrants):
            matches.append(_new_match(entrants[i], entrants[i + 1]))
            i += 2
        else:
            matches.append(_new_match(entrants[i], None))
            i += 1
    return matches


def _open_rps_tournament(db, room, user, *, timer, deadline, now) -> GameRoom:
    players = [m for m in repository.members(db, room.id) if m.active and m.role != ROLE_SPECTATOR]
    if len(players) < 2:
        raise ConflictError("토너먼트는 참여자가 2명 이상이어야 합니다.")
    entrants = [(m.user_id, m.display_name) for m in players]
    secrets.SystemRandom().shuffle(entrants)
    state = {
        "mode": "tournament", "round_idx": 0, "champion": None,
        "matches": _pair_round(entrants), "rounds": [], "timer_seconds": timer,
    }
    if deadline:
        state["deadline"] = deadline
    room.status = ROOM_PLAYING
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id,
                  payload={"mode": "tournament", "players": len(players)}, now=now)
    return room


def _resolve_match(m: dict) -> None:
    """두 선택이 모두 있으면 승부를 낸다. 비기면 두 선택을 지워 다시 내게 한다(replay)."""
    ac, bc = m.get("a_choice"), m.get("b_choice")
    if ac is None or bc is None:
        return
    if ac == bc:  # 비김 → 그 대진만 다시
        m["a_choice"] = None
        m["b_choice"] = None
        m["replayed"] = int(m.get("replayed", 0)) + 1
        return
    m["winner"] = m["a"] if _RPS_BEATS[ac] == bc else m["b"]
    m["done"] = True


def _tournament_submit(db, room, user, state, *, choice, now) -> None:
    for m in state.get("matches", []):
        if m.get("done"):
            continue
        if m["a"] == user.id:
            m["a_choice"] = choice
        elif m.get("b") == user.id:
            m["b_choice"] = choice
        else:
            continue
        _resolve_match(m)
        _tournament_advance(db, room, state, now=now, force=False)
        # 챔피언이 나오면 advance가 이미 result를 room.state_json에 썼다 — 덮어쓰지 않는다.
        if room.status == ROOM_PLAYING:
            room.state_json = json.dumps(state, ensure_ascii=False)
        db.flush()
        _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)
        return
    raise ForbiddenError("이번 라운드 대진에 없습니다(이미 탈락했거나 관전 중).")


def _tournament_advance(db, room, state, *, now, force: bool) -> None:
    """라운드가 끝났으면 다음 라운드를 짜거나 챔피언을 확정한다. force면 미결 대진을 서버가 마감."""
    matches = state.get("matches", [])
    rng = secrets.SystemRandom()
    if force:
        for m in matches:
            if m.get("done"):
                continue
            # 대진 상대가 이미 방을 나갔으면(멤버 row가 사라짐) 무작위 채우기·코인플립을 타지
            # 않고 남아 있는 쪽이 곧바로 이긴다 — 안 그러면 나간 사람이 무작위로 챔피언까지
            # 올라갈 수 있었다(§13.1 공정성). 숫자 눈치·가위바위보 단판은 _present_players로
            # 종료 집계에서 나간 사람을 거르는데, 토너먼트 강제 마감엔 그 대응 필터가 없었다.
            a_present = repository.get_member(db, room.id, m["a"]) is not None
            b_present = m.get("b") is not None and repository.get_member(db, room.id, m["b"]) is not None
            if a_present != b_present:
                m["winner"] = m["a"] if a_present else m["b"]
                m["done"] = True
                continue
            if m.get("a_choice") is None:
                m["a_choice"] = rng.randint(0, 2)
            if m.get("b_choice") is None:
                m["b_choice"] = rng.randint(0, 2)
            ac, bc = m["a_choice"], m["b_choice"]
            m["winner"] = rng.choice([m["a"], m["b"]]) if ac == bc else (m["a"] if _RPS_BEATS[ac] == bc else m["b"])
            m["done"] = True
    if not matches or not all(m.get("done") for m in matches):
        return  # 아직 진행 중

    def _wname(m):  # 승자 이름은 대진에 저장된 이름에서 — 참여자가 중간에 나가도 이름이 남는다
        w = m.get("winner")
        if w == m.get("a"):
            return m.get("a_name") or ""
        if w == m.get("b"):
            return m.get("b_name") or ""
        return (m.get("a_name") or "") if m.get("bye") else ""

    # 끝난 라운드를 히스토리에 남긴다(대진표 표시용).
    state.setdefault("rounds", []).append([
        {"a_name": m.get("a_name"), "b_name": m.get("b_name"), "winner_name": _wname(m)}
        for m in matches
    ])
    winners = [m["winner"] for m in matches if m.get("winner")]
    if len(winners) <= 1:
        champ = winners[0] if winners else None
        champ_name = ""
        for m in matches:
            if champ and m.get("winner") == champ:
                champ_name = _wname(m)
                break
        state["champion"] = {"user_id": champ, "name": champ_name} if champ else None
        result = {"mode": "tournament", "champion": state["champion"], "rounds": state["rounds"]}
        room.status = ROOM_FINISHED
        room.state_json = json.dumps({"result": result}, ensure_ascii=False)
        db.flush()
        _append_event(db, room, EV_RESULT, actor_id=None, payload={"champion": state["champion"]}, now=now)
        return
    name_by_uid: dict[str, str] = {}
    for m in matches:
        if m.get("a"):
            name_by_uid[m["a"]] = m.get("a_name") or ""
        if m.get("b"):
            name_by_uid[m["b"]] = m.get("b_name") or ""
    entrants = [(uid, name_by_uid.get(uid, "")) for uid in winners]
    rng.shuffle(entrants)
    state["round_idx"] = int(state.get("round_idx", 0)) + 1
    state["matches"] = _pair_round(entrants)
    timer = int(state.get("timer_seconds", 0) or 0)
    if timer > 0:
        state["deadline"] = (now + timedelta(seconds=timer)).isoformat()
    else:
        state.pop("deadline", None)


def _rps_tournament_public(state: dict, user_id: str) -> dict:
    """토너먼트 진행 중 안전한 뷰. 상대가 무엇을 냈는지는 감추고(제출 여부만), 대진이 끝나면
    승자만 공개한다. your_match로 내 대진·내 선택·상대 이름을 준다."""
    matches = state.get("matches", [])
    view_matches = []
    your_match = None
    for idx, m in enumerate(matches):
        winner_name = None
        if m.get("done") and m.get("winner"):
            winner_name = m.get("a_name") if m.get("winner") == m.get("a") else m.get("b_name")
        view_matches.append({
            "a_name": m.get("a_name"), "b_name": m.get("b_name"),
            "a_submitted": m.get("a_choice") is not None,
            "b_submitted": m.get("b_choice") is not None,
            "done": bool(m.get("done")), "bye": bool(m.get("bye")),
            "winner_name": winner_name, "replayed": int(m.get("replayed", 0)),
        })
        if not m.get("done") and user_id in (m.get("a"), m.get("b")):
            slot = "a" if m.get("a") == user_id else "b"
            your_match = {
                "index": idx, "slot": slot,
                "opponent": m.get("b_name") if slot == "a" else m.get("a_name"),
                "your_choice": m.get(slot + "_choice"),
                "you_submitted": m.get(slot + "_choice") is not None,
            }
    return {
        "mode": "tournament",
        "round_idx": int(state.get("round_idx", 0)),
        "matches": view_matches,
        "your_match": your_match,
        "champion": state.get("champion"),
        "deadline": state.get("deadline"),
        "timer_seconds": state.get("timer_seconds"),
    }


def _finish_rps(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    state = json.loads(room.state_json or "{}")
    # 지금 방에 있는 참여자만 — 나갔거나 관전자로 재입장한 사람의 옛 선택(유령 승자·빈 이름)을 배제.
    members = _present_players(db, room, now)
    names = {m.user_id: m.display_name for m in members}
    raw = {uid: c for uid, c in state.get("choices", {}).items()
           if isinstance(c, int) and c in (0, 1, 2) and uid in names}
    # 시간 안에 안 낸 참여자는 서버가 무작위로 채운다 — 대기로 게임이 막히지 않게(§13.1 서버 확정).
    rng = secrets.SystemRandom()
    auto_ids: set[str] = set()
    for m in members:
        if m.user_id not in raw:
            raw[m.user_id] = rng.randint(0, 2)
            auto_ids.add(m.user_id)
    choices = raw
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
        [{"user_id": uid, "name": names.get(uid, ""), "choice": _RPS_LABELS[c], "auto": uid in auto_ids}
         for uid, c in choices.items()],
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
    timer, deadline = _timer_from_config(config, GAME_QUIZ, now)
    room.status = ROOM_PLAYING
    # 점수판을 참여자 전원 0점으로 시작한다 — 한 문제도 못 맞힌 사람도 최종 결과에 남게(누락 방지).
    scores = {m.user_id: 0 for m in _present_players(db, room, now)}
    state = {"questions": questions, "round": 0, "phase": QUIZ_ANSWERING, "answers": {}, "scores": scores,
             "timer_seconds": timer}
    if deadline:
        state["deadline"] = deadline  # 라운드마다 갱신(각 문제에 제한 시간)
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _append_event(db, room, EV_START, actor_id=user.id, payload={"rounds": len(questions)}, now=now)
    return room


def submit_quiz_answer(db: Session, room: GameRoom, user: User, *, option_index: int, now: datetime) -> None:
    if room.game_type != GAME_QUIZ:
        raise ValidationAppError("퀴즈 게임이 아닙니다.")
    if room.status != ROOM_PLAYING:
        raise ConflictError("진행 중인 퀴즈가 없습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None or not member.active or member.role == ROLE_SPECTATOR:
        raise ForbiddenError("참여자만 답할 수 있습니다.")

    def _apply(state: dict) -> dict:
        # 검증도 mutate 안에서 한다 — CAS가 충돌로 재시도할 때마다 최신 state(예: 그 사이
        # 방장이 정답을 공개해 phase가 바뀌었을 수도 있다) 기준으로 다시 확인한다.
        if state.get("phase") != QUIZ_ANSWERING:
            raise ConflictError("지금은 답을 낼 수 없습니다.")
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
        return state

    _cas_update_state(db, room, _apply)  # 동시 응답이 서로 덮어쓰지 않게(CAS)
    _append_event(db, room, EV_PICK, actor_id=user.id, payload={"name": user.display_name}, now=now)


def reveal_quiz(db: Session, room: GameRoom, user: User, *, now: datetime) -> GameRoom:
    _ensure_host(room, user)
    return _reveal_quiz(db, room, user.id, now=now)


def _reveal_quiz(db: Session, room: GameRoom, actor_id, *, now: datetime) -> GameRoom:
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
    _append_event(db, room, EV_SYSTEM, actor_id=actor_id, payload={"quiz": "revealed", "round": rnd}, now=now)
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
        # 지금 방에 있는 참여자만 — 나간 사람의 점수를 그대로 남겨두면(repository.members는
        # 지금 멤버만 주지만 나간 사람은 아예 없다) 빈 이름("")으로 점수판에 남고, 점수가
        # 가장 높으면 빈 이름이 '우승자'로도 뜬다(숫자 눈치·가위바위보 종료 집계가 이미
        # _present_players로 막는 유령 승자와 같은 문제).
        scores = state.get("scores", {})
        names = {m.user_id: m.display_name for m in _present_players(db, room, now)}
        board = sorted(
            ({"user_id": uid, "name": names[uid], "score": int(sc)}
             for uid, sc in scores.items() if uid in names),
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
    timer = int(state.get("timer_seconds", 0) or 0)
    if timer > 0:
        state["deadline"] = (now + timedelta(seconds=timer)).isoformat()  # 새 문제에 새 카운트다운
    else:
        state.pop("deadline", None)
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
        "submitted": list(answers.keys()),  # 누가 답했는지(무엇을 골랐는지는 감춤) — 대기자 표시
        "your_answer": answers.get(user_id),
        "scores": _score_view(scores, state),
        "deadline": state.get("deadline") if phase == QUIZ_ANSWERING else None,
        "timer_seconds": state.get("timer_seconds"),
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
            "submitted": list(picks.keys()),  # 누가 냈는지(값은 감춤) — 대기자 표시용
            "you_submitted": user_id in picks,
            "your_pick": picks.get(user_id),
            "deadline": state.get("deadline"),
            "timer_seconds": state.get("timer_seconds"),
        }
    if room.game_type == GAME_RPS and room.status == ROOM_PLAYING:
        if state.get("mode") == "tournament":
            return _rps_tournament_public(state, user_id)
        choices = state.get("choices", {})
        return {
            "submitted_count": len(choices),
            "submitted": list(choices.keys()),  # 누가 냈는지(무엇을 냈는지는 감춤)
            "you_submitted": user_id in choices,
            "your_choice": choices.get(user_id),  # 0/1/2 (본인 것만)
            "deadline": state.get("deadline"),
            "timer_seconds": state.get("timer_seconds"),
            "mode": "single",
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
    """폴링마다 호출 — 재접속 감지용 last_seen/active 갱신.

    방 화면은 1.2초마다 폴링한다. 예전 임계값 2초는 "두 번에 한 번은 쓴다"는 뜻이라 사실상
    스로틀이 아니었고, 읽기 폴링이 그대로 쓰기 부하가 됐다(SQLite writer 는 하나다).
    이제 `app/core/presence.py` 의 30초를 쓴다 — 접속자 판정 창(PRESENCE_SECONDS=90)의
    1/3 이라 실제로 붙어 있는 사람이 깜빡일 여지가 없다.

    **재접속(active=False → True)만은 스로틀에 걸지 않는다.** 그건 '아직 여기 있다'가 아니라
    '방금 돌아왔다'라서, 30초를 기다리면 돌아온 사람이 목록에 안 뜬다.
    """
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        return
    if member.active and not should_touch(member.last_seen, now):
        return
    member.active = True
    member.last_seen = now
    db.flush()
