"""구슬 레이스 (`marble_race`) — 서버는 seed 를 주고 결과를 상호 대조로 확정한다 (기능 개선 회차 P5, D-564).

서버는 물리를 돌리지 않는다(Python 과 브라우저의 부동소수가 다르고 좌표 중계는 부하가 크다). 대신:

  1. 시작: 방장이 누르면 서버가 `race_id` · `seed` · `started_at` · `speed` · 참가자 묶음을 발급한다(상태 `running`). 모든 브라우저가
     같은 seed 로 같은 결정적 경주를 계산한다(워커의 고정 스텝 + 결정적 수학).
  2. 제출: 경주가 끝나면 브라우저마다 **전체 결과** `{race_id, ranking, finish_steps, digest}` 를 올린다 — 방장은 `finish`, 나머지는
     `attest`. 검증은 같다: 순열 · 같은 race_id · 최소 경과 · 한 사람 한 번 · digest 가 ranking · finish_steps 의 해시와 같다.
  3. 확정 시점은 하나다. 첫 제출에 `verifying` 이 되고 **확인 창**(방장 제출 뒤 10초, 방장 없이 첫 attest 뒤 30초, 또는 지금 있는
     구성원이 모두 제출하면 즉시)이 닫힐 때 한 번 판정해 `finalized_at` 을 찍는다. 확정 뒤 도착한 제출은 기록만 하고 결과를 바꾸지 않는다.
  4. 일치와 신뢰를 구분한다 — `confirmed` 는 서로 다른 브라우저의 결과가 **일치했다**는 뜻이지 계산이 조작되지 않았다는 증명이 아니다.
     `host_only`(대조할 제출 없음) · `host_absent`(방장 미제출, 참가자 다수 결과 승격) · `disputed`(불일치 하나라도 — 발표하지 않는다).
  5. 10분 안에 아무 제출도 없으면 `abandoned`.

참가자는 방 구성원 이름이 기본이고 방장이 자유 이름을 더한다(2 ~ 100명, 1 ~ 24자, NFC · 공백 접기, 중복은 거절 + 「(2)」 제안).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, ValidationAppError
from app.games.models import EV_RESULT, EV_START, ROLE_SPECTATOR, ROOM_FINISHED, ROOM_PLAYING, ROOM_WAITING, GameRoom

MIN_PARTICIPANTS = 2
MAX_PARTICIPANTS = 100
NAME_MAX = 24
MAX_WINNERS = 10
SPEEDS = (1, 2, 4)
MAPS = ("wheel", "pot", "bubble", "yoru")  # 경주 판(D-578) — 100개 1배속 경주가 상한(240초) 안에 끝나는 판만(`engine.test.js` 가 잰다)
#: 서버 시계로 잰 최소 경과(배속 1 기준). 이보다 빨리 온 결과는 경주를 돌리지 않은 것이다.
MIN_RACE_SECONDS = 8
VERIFY_WINDOW_HOST_SECONDS = 10
VERIFY_WINDOW_ATTEST_SECONDS = 30
ABANDON_SECONDS = 600

PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_VERIFYING = "verifying"
PHASE_FINISHED = "finished"
PHASE_ABANDONED = "abandoned"

INTEGRITY_CONFIRMED = "confirmed"
INTEGRITY_HOST_ONLY = "host_only"
INTEGRITY_HOST_ABSENT = "host_absent"
INTEGRITY_DISPUTED = "disputed"
#: 발표해도 되는 확정 상태 — `disputed` 는 발표 · 축포가 없다.
ANNOUNCEABLE = frozenset({INTEGRITY_CONFIRMED, INTEGRITY_HOST_ONLY, INTEGRITY_HOST_ABSENT})

ROLE_FINISH = "host"
ROLE_ATTEST = "attest"


# ── 참가자 ───────────────────────────────────────────────────────────────────


def normalize_name(raw) -> str:
    """NFC 로 맞추고 제어 문자를 걷고 공백을 접는다. 빈 글이면 빈 문자열."""
    text = unicodedata.normalize("NFC", str(raw or ""))
    text = "".join(ch for ch in text if ch.isprintable())
    return " ".join(text.split())


def _suggest(name: str, taken: set[str]) -> str:
    n = 2
    while f"{name} ({n})" in taken:
        n += 1
    return f"{name} ({n})"


def validate_participants(items) -> list[dict]:
    """`[{key?, name, user_id?}]` → 정규화된 목록. 2 ~ 100명, 이름 1 ~ 24자, 중복은 422 와 함께 「(2)」 제안."""
    if not isinstance(items, list):
        raise ValidationAppError("참가자 목록이 올바르지 않습니다.")
    out: list[dict] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    suggestions: dict[str, str] = {}
    for raw in items[: MAX_PARTICIPANTS + 1]:
        if not isinstance(raw, dict):
            raise ValidationAppError("참가자 항목이 올바르지 않습니다.")
        name = normalize_name(raw.get("name"))
        if not name:
            raise ValidationAppError("빈 이름은 참가자가 될 수 없습니다.")
        if len(name) > NAME_MAX:
            raise ValidationAppError(f"참가자 이름은 {NAME_MAX}자까지 넣을 수 있습니다.")
        user_id = raw.get("user_id")
        user_id = str(user_id) if isinstance(user_id, str) and user_id else None
        key = raw.get("key")
        if not isinstance(key, str) or not key or len(key) > 48:
            key = f"u:{user_id}" if user_id else f"n:{uuid.uuid4().hex[:10]}"
        if name in seen:
            duplicates.append(name)
            suggestions[name] = _suggest(name, seen | set(suggestions.values()))
            continue
        seen.add(name)
        out.append({"key": key, "name": name, "user_id": user_id})
    if duplicates:
        raise ValidationAppError(
            "같은 이름이 둘 이상 있습니다. 구별할 수 있게 고쳐 주세요.",
            details={"duplicates": sorted(set(duplicates)), "suggestions": suggestions},
        )
    if len(out) < MIN_PARTICIPANTS:
        raise ValidationAppError(f"참가자는 {MIN_PARTICIPANTS}명 이상이어야 합니다.")
    if len(out) > MAX_PARTICIPANTS:
        raise ValidationAppError(f"참가자는 {MAX_PARTICIPANTS}명까지 넣을 수 있습니다.")
    if len({p["key"] for p in out}) != len(out):
        raise ValidationAppError("참가자 구분 값이 겹칩니다.")
    return out


def participants_from_members(db: Session, room: GameRoom, now: datetime) -> list[dict]:
    """방 구성원(관전자 제외, 지금 있는 사람)이 기본 참가자다. 이름이 겹치면 「(2)」를 붙인다."""
    from app.games import service as _service

    out: list[dict] = []
    seen: set[str] = set()
    for m in _service._present_players(db, room, now):  # noqa: SLF001 - 같은 꾸러미의 판정 하나를 쓴다
        name = normalize_name(m.display_name) or "참가자"
        if name in seen:
            name = _suggest(name, seen)
        seen.add(name)
        out.append({"key": f"u:{m.user_id}", "name": name, "user_id": m.user_id})
    return out


# ── 설정 ─────────────────────────────────────────────────────────────────────


def config_view(config: dict | None) -> dict:
    """저장된 설정을 기본값으로 채운 한 벌. 참가자는 저장된 목록(없으면 빈 목록 — 시작 때 구성원으로 채운다)."""
    raw = config or {}
    try:
        winners = int(raw.get("winners", 1) or 1)
    except (TypeError, ValueError):
        winners = 1
    try:
        speed = int(raw.get("speed", 1) or 1)
    except (TypeError, ValueError):
        speed = 1
    participants = raw.get("participants") if isinstance(raw.get("participants"), list) else []
    return {
        "participants": [p for p in participants if isinstance(p, dict) and p.get("name")],
        "winners": max(1, min(winners, MAX_WINNERS)),
        "pick_last": bool(raw.get("pick_last", False)),
        "map": raw.get("map") if raw.get("map") in MAPS else MAPS[0],
        "speed": speed if speed in SPEEDS else 1,
    }


def _save_config(room: GameRoom, config: dict) -> None:
    stored = json.loads(room.config_json or "{}")
    stored.update(config)
    room.config_json = json.dumps(stored, ensure_ascii=False)


def _ensure_host(room: GameRoom, user) -> None:
    if room.host_user_id != user.id:
        raise ForbiddenError("방장만 할 수 있습니다.")


def set_participants(db: Session, room: GameRoom, user, items, *, now: datetime) -> list[dict]:
    _ensure_host(room, user)
    if room.status != ROOM_WAITING:
        raise ConflictError("경주가 진행 중이거나 끝난 방입니다. '다시 하기'를 누른 뒤 변경할 수 있습니다.")
    if not list(items or []):
        # 빈 목록은 「시작할 때의 방 구성원」이다(`config_view` · `start`). 예전에는 2명 미만이라며 422 를 줘, 구성원을 참가자로 쓰는 방은
        # 설정 창이 참가자를 먼저 보내는 순서 때문에 맵조차 저장하지 못했다(r23 D-593).
        _save_config(room, {"participants": []})
        db.flush()
        return []
    participants = validate_participants(items)
    _save_config(room, {"participants": participants})
    db.flush()
    return participants


def set_config(db: Session, room: GameRoom, user, changes: dict, *, now: datetime) -> dict:
    _ensure_host(room, user)
    if room.status != ROOM_WAITING:
        raise ConflictError("경주가 진행 중이거나 끝난 방입니다. '다시 하기'를 누른 뒤 변경할 수 있습니다.")
    current = config_view(json.loads(room.config_json or "{}"))
    merged = {**current, **{k: v for k, v in (changes or {}).items() if k in ("winners", "pick_last", "map", "speed")}}
    try:
        winners = int(merged["winners"])
    except (TypeError, ValueError):
        raise ValidationAppError("당첨 인원은 숫자여야 합니다.") from None
    if not (1 <= winners <= MAX_WINNERS):
        raise ValidationAppError(f"당첨 인원은 1명부터 {MAX_WINNERS}명까지입니다.")
    if merged["map"] not in MAPS:
        raise ValidationAppError("지원하지 않는 맵입니다.")
    try:
        speed = int(merged["speed"])
    except (TypeError, ValueError):
        raise ValidationAppError("배속은 1, 2, 4 중 하나입니다.") from None
    if speed not in SPEEDS:
        raise ValidationAppError("배속은 1, 2, 4 중 하나입니다.")
    saved = {"winners": winners, "pick_last": bool(merged["pick_last"]), "map": merged["map"], "speed": speed}
    _save_config(room, saved)
    db.flush()
    return {**current, **saved}


# ── 시작 ─────────────────────────────────────────────────────────────────────


def start(db: Session, room: GameRoom, user, *, now: datetime) -> GameRoom:
    """방장이 시작한다. 서버가 race_id · seed · started_at 을 발급하고 참가자 묶음을 상태에 박는다(그 뒤의 편집은 이 경주에 닿지 않는다)."""
    from app.games import service as _service

    _ensure_host(room, user)
    if room.status != ROOM_WAITING:
        raise ConflictError("이미 시작했거나 끝난 방입니다. '다시 하기'를 누른 뒤 다시 시작할 수 있습니다.")
    config = config_view(json.loads(room.config_json or "{}"))
    participants = config["participants"] or participants_from_members(db, room, now)
    if len(participants) < MIN_PARTICIPANTS:
        raise ConflictError(f"참가자가 {MIN_PARTICIPANTS}명 이상이어야 합니다. 방장이 설정에서 참가자를 추가할 수 있습니다.")
    participants = validate_participants(participants)
    state = {
        "phase": PHASE_RUNNING,
        "race_id": uuid.uuid4().hex,
        "seed": secrets.token_hex(8),
        "started_at": now.isoformat(),
        "speed": config["speed"],
        "map": config["map"],
        "winners_n": min(config["winners"], len(participants)),
        "pick_last": config["pick_last"],
        "host_user_id": room.host_user_id,
        "participants": participants,
        "submissions": [],
        "verify_until": None,
        "result": None,
        "finalized_at": None,
    }
    room.status = ROOM_PLAYING
    room.state_json = json.dumps(state, ensure_ascii=False)
    db.flush()
    _service._append_event(db, room, EV_START, actor_id=user.id, payload={  # noqa: SLF001
        "race_id": state["race_id"], "seed": state["seed"], "started_at": state["started_at"], "speed": state["speed"],
        "map": state["map"], "participants": len(participants), "winners": state["winners_n"], "pick_last": state["pick_last"],
    }, now=now)
    return room


# ── 결과 제출과 확정 ─────────────────────────────────────────────────────────


def digest_of(race_id: str, ranking: list[str], finish_steps: list[int]) -> str:
    """결과 지문 — 브라우저(`engine/race.js`)와 같은 글을 같은 해시로. 순위 열쇠와 완주 스텝만 든다."""
    material = f"{race_id}|{','.join(ranking)}|{','.join(str(int(s)) for s in finish_steps)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _parse_dt(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _present_member_ids(db: Session, room: GameRoom, now: datetime) -> set[str]:
    """지금 방에 있는 구성원 전부(관전자 포함) — 「모두 제출했는가」의 분모."""
    from app.games import repository, service as _service

    return {m.user_id for m in repository.members(db, room.id) if _service.is_present(m, now)}


def _winners_of(ranking: list[str], n: int, pick_last: bool) -> list[str]:
    n = max(1, min(int(n), len(ranking)))
    return list(ranking[-n:][::-1]) if pick_last else list(ranking[:n])


def _judge(state: dict) -> tuple[dict | None, dict]:
    """제출들을 대조해 (결과, 무결성) 을 낸다. 결과가 None 이면 발표하지 않는다(`disputed`)."""
    subs = state.get("submissions") or []
    host = next((s for s in subs if s.get("role") == ROLE_FINISH), None)
    others = [s for s in subs if s.get("role") != ROLE_FINISH]
    if host is not None:
        agree = [s for s in others if s.get("digest") == host.get("digest")]
        disagree = [s for s in others if s.get("digest") != host.get("digest")]
        if disagree:
            status = INTEGRITY_DISPUTED
        elif agree:
            status = INTEGRITY_CONFIRMED
        else:
            status = INTEGRITY_HOST_ONLY
        integrity = {"status": status, "agree": len(agree), "disagree": len(disagree), "source": "host",
                     "submissions": len(subs)}
        chosen = host
    else:
        digests = {s.get("digest") for s in others}
        if len(digests) != 1:
            integrity = {"status": INTEGRITY_DISPUTED, "agree": 0, "disagree": len(others), "source": "attest",
                         "submissions": len(subs)}
            return None, integrity
        integrity = {"status": INTEGRITY_HOST_ABSENT, "agree": len(others), "disagree": 0, "source": "attest",
                     "submissions": len(subs)}
        chosen = others[0]
    if integrity["status"] == INTEGRITY_DISPUTED:
        return None, integrity
    ranking = list(chosen["ranking"])
    result = {
        "ranking": ranking,
        "finish_steps": list(chosen["finish_steps"]),
        "digest": chosen["digest"],
        "winners": _winners_of(ranking, state.get("winners_n", 1), bool(state.get("pick_last"))),
    }
    return result, integrity


def _validate_submission(state: dict, body: dict, *, now: datetime) -> dict:
    """한 제출의 모양 · 시점 검사(순열 · race_id · 최소 경과 · digest). 통과하면 저장할 모양을 돌려준다."""
    race_id = str(body.get("race_id") or "")
    if race_id != state.get("race_id"):
        raise ValidationAppError("이번 경주의 결과가 아닙니다.")
    keys = [p["key"] for p in state.get("participants") or []]
    ranking = body.get("ranking")
    steps = body.get("finish_steps")
    if not isinstance(ranking, list) or not isinstance(steps, list):
        raise ValidationAppError("결과 모양이 올바르지 않습니다.")
    if sorted(str(k) for k in ranking) != sorted(keys) or len(ranking) != len(keys):
        raise ValidationAppError("순위가 참가자 전체의 순열이 아닙니다.")
    if len(steps) != len(ranking):
        raise ValidationAppError("완주 스텝 수가 순위 수와 다릅니다.")
    clean_steps: list[int] = []
    for s in steps:
        if isinstance(s, bool) or not isinstance(s, int) or s < 0:
            raise ValidationAppError("완주 스텝이 올바르지 않습니다.")
        clean_steps.append(int(s))
    started = _parse_dt(state.get("started_at"))
    speed = int(state.get("speed") or 1)
    if started is None or (now - started).total_seconds() < MIN_RACE_SECONDS / max(1, speed):
        raise ValidationAppError("경주가 끝났다기에는 너무 이릅니다. 경주를 끝까지 돌린 뒤 결과를 올리세요.")
    ranking = [str(k) for k in ranking]
    digest = str(body.get("digest") or "")
    if digest != digest_of(race_id, ranking, clean_steps):
        raise ValidationAppError("결과 지문이 순위와 맞지 않습니다.")
    return {"ranking": ranking, "finish_steps": clean_steps, "digest": digest}


def submit(db: Session, room: GameRoom, user, body: dict, *, now: datetime, as_host: bool) -> dict:
    """결과 하나를 받는다. 방장의 `finish` 와 구성원의 `attest` 는 검증이 같다. 확정 뒤에 온 제출은 기록만 한다."""
    from app.games import repository, service as _service

    if as_host:
        _ensure_host(room, user)
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("방 안의 사람만 결과를 올릴 수 있습니다.")
    if room.status not in (ROOM_PLAYING, ROOM_FINISHED):
        raise ConflictError("진행 중인 경주가 없습니다.")
    role = ROLE_FINISH if as_host else ROLE_ATTEST
    outcome = {"recorded": False, "late": False}

    def _apply(state: dict) -> dict:
        phase = state.get("phase")
        if phase not in (PHASE_RUNNING, PHASE_VERIFYING, PHASE_FINISHED):
            raise ConflictError("결과를 받을 수 있는 경주가 아닙니다.")
        clean = _validate_submission(state, body, now=now)
        subs = list(state.get("submissions") or [])
        if any(s.get("user_id") == user.id for s in subs):
            raise ConflictError("이미 이번 경주의 결과를 올렸습니다.")
        if len(subs) >= MAX_PARTICIPANTS + 10:
            raise ConflictError("이번 경주의 제출이 너무 많습니다.")
        subs.append({"user_id": user.id, "role": role, "at": now.isoformat(), **clean})
        state["submissions"] = subs
        outcome["recorded"] = True
        if phase == PHASE_FINISHED or state.get("finalized_at"):
            outcome["late"] = True  # 확정 뒤 — 결과 · 상태 불변
            return state
        window = VERIFY_WINDOW_HOST_SECONDS if as_host else VERIFY_WINDOW_ATTEST_SECONDS
        until = now + timedelta(seconds=window)
        current = _parse_dt(state.get("verify_until"))
        if phase == PHASE_RUNNING or current is None:
            state["verify_until"] = until.isoformat()
        elif as_host and until < current:
            state["verify_until"] = until.isoformat()  # 방장이 늦게 왔으면 10초로 줄인다
        state["phase"] = PHASE_VERIFYING
        return state

    new_state = _service._cas_update_state(db, room, _apply)  # noqa: SLF001
    if not outcome["late"]:
        everyone = _present_member_ids(db, room, now)
        submitted = {s.get("user_id") for s in new_state.get("submissions") or []}
        if everyone and everyone <= submitted:
            new_state = _finalize(db, room, now=now)
    view = public_view(new_state, user.id)
    return {"recorded": outcome["recorded"], "late": outcome["late"], "state": view}


def _finalize(db: Session, room: GameRoom, *, now: datetime) -> dict:
    """확인 창을 닫고 한 번 판정한다(CAS — 겹친 폴링이 두 번 판정하지 않는다). 이미 확정됐으면 그대로."""
    from app.games import service as _service

    def _apply(state: dict) -> dict:
        if state.get("finalized_at") or state.get("phase") not in (PHASE_VERIFYING,):
            return state
        result, integrity = _judge(state)
        state["result"] = result
        state["integrity"] = integrity
        state["finalized_at"] = now.isoformat()
        state["phase"] = PHASE_FINISHED
        return state

    new_state = _service._cas_update_state(db, room, _apply)  # noqa: SLF001
    if room.status != ROOM_FINISHED and new_state.get("phase") == PHASE_FINISHED:
        room.status = ROOM_FINISHED
        db.flush()
        integrity = new_state.get("integrity") or {}
        result = new_state.get("result")
        payload = {"race_id": new_state.get("race_id"), "integrity": integrity,
                   "winners": (result or {}).get("winners") if result else None,
                   "disputed": integrity.get("status") == INTEGRITY_DISPUTED}
        _service._append_event(db, room, EV_RESULT, actor_id=None, payload=payload, now=now)  # noqa: SLF001
    return new_state


def maybe_finalize(db: Session, room: GameRoom, *, now: datetime) -> None:
    """폴링마다(`service.maybe_autoresolve`) — 확인 창이 닫혔으면 판정하고, 제출 없이 10분이 지났으면 버린다."""
    from app.games import service as _service

    if room.status != ROOM_PLAYING:
        return
    state = json.loads(room.state_json or "{}")
    phase = state.get("phase")
    if phase == PHASE_VERIFYING:
        until = _parse_dt(state.get("verify_until"))
        if until is not None and now >= until:
            _finalize(db, room, now=now)
        return
    if phase == PHASE_RUNNING:
        started = _parse_dt(state.get("started_at"))
        if started is not None and (now - started).total_seconds() >= ABANDON_SECONDS and not state.get("submissions"):
            def _abandon(current: dict) -> dict:
                if current.get("phase") == PHASE_RUNNING:
                    current["phase"] = PHASE_ABANDONED
                    current["finalized_at"] = now.isoformat()
                return current

            new_state = _service._cas_update_state(db, room, _abandon)  # noqa: SLF001
            if new_state.get("phase") == PHASE_ABANDONED and room.status != ROOM_FINISHED:
                room.status = ROOM_FINISHED
                db.flush()
                _service._append_event(db, room, EV_RESULT, actor_id=None,  # noqa: SLF001
                                       payload={"race_id": state.get("race_id"), "abandoned": True}, now=now)


# ── 화면에 내려줄 모양 ───────────────────────────────────────────────────────


def public_view(state: dict, user_id: str, config: dict | None = None) -> dict:
    """저장된 상태 그대로에 「내가 올렸는가」와 방 설정(대기 중 미리 보기 · 방장 설정 창의 현재 값)을 더한다.
    비밀이 없다(seed · digest 는 모두가 알아야 하는 값이다)."""
    if not state:
        return {"phase": PHASE_IDLE, "config": config_view(config)}
    subs = state.get("submissions") or []
    return {
        **state,
        "config": config_view(config),
        "phase": state.get("phase") or PHASE_IDLE,
        "submissions": [{"user_id": s.get("user_id"), "role": s.get("role"), "digest": s.get("digest"), "at": s.get("at")}
                        for s in subs],
        "you_submitted": any(s.get("user_id") == user_id for s in subs),
        "announceable": bool(state.get("finalized_at")) and (state.get("integrity") or {}).get("status") in ANNOUNCEABLE,
        # 결과를 받기 시작하는 최소 경과(배속 1 기준) — 짧게 끝난 경주의 브라우저가 이만큼 기다렸다 올린다(D-580).
        "min_race_seconds": MIN_RACE_SECONDS,
    }
