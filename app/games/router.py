"""팀 공간 > 놀이 API (§5·§6·§13·§14).

거의 순수 내부 기능(게임방 채팅도 n8n 안 거침, §13.2). 예외로 AI 퀴즈 생성(POST /quiz/generate,
§7-9)만 러너를 통해 Claude를 호출하며, 그 유일한 외부 호출은 app/games/ai.py에 격리돼 있다
(service.py는 외부 호출 없음). 이 엔드포인트는 game_ai_enabled 플래그(기본 OFF)로 fail-closed.
조회는 인증만, 상태변경은 CSRF. 결과는 서버가 확정(§13.1). 폴링(GET .../state?since=<seq>)으로 흐른다.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_auth, get_current_user, get_db, require_csrf
from app.core.etag import etag_json_response
from app.core.errors import NotFoundError, RateLimitedError
from app.core.feature_flags import load_feature_flags
from app.games import ai, repository, service
from app.games.models import EV_CHAT, ROLE_SPECTATOR
from app.games.schemas import ChatInput, NumberInput, QuizGenerateInput, ReadyInput, RoomCreate, VoteInput
from app.users.models import User
from app.settings.gate import block_if_maintenance


def require_games_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("games_enabled", True):
        raise NotFoundError("놀이 기능이 비활성화되어 있습니다.")


def require_game_ai_enabled(request: Request) -> None:
    # fail-closed: 기본값 False. 켜지 않으면 AI 생성 엔드포인트는 404(나머지 놀이는 그대로 동작).
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("game_ai_enabled", False):
        raise NotFoundError("AI 퀴즈 생성 기능이 비활성화되어 있습니다.")


router = APIRouter(
    prefix="/api/games",
    tags=["games"],
    dependencies=[Depends(require_games_enabled), Depends(block_if_maintenance)],
)


def _room_summary(db: Session, room) -> dict:
    return {
        "id": room.id,
        "title": room.title,
        "game_type": room.game_type,
        "host_user_id": room.host_user_id,
        "status": room.status,
        "player_count": repository.player_count(db, room.id),
        "member_count": repository.member_count(db, room.id),
        "max_players": room.max_players,
        "allow_spectators": room.allow_spectators,
        "closed": room.closed_at is not None,
        "created_at": room.created_at.isoformat(),
    }


def _member_view(m, user=None, *, now=None) -> dict:
    # 참여자 카드에 이름과 함께 직책·부서를 보여준다(사람을 알아보게). 명부에 없으면 빈칸.
    return {
        "user_id": m.user_id, "name": m.display_name, "role": m.role,
        "ready": m.ready, "active": m.active,
        # 명단에는 남아 있어도 추첨·팀나누기·사다리·투표 대상 풀(service._present_players)
        # 에서는 빠질 수 있다(90초 넘게 폴링이 없으면) - 그 어긋남을 화면이 미리 말해야
        # "5명이 보이는데 4명 중에서 뽑힌다"는 게 나중에야 결과로 드러나지 않는다.
        "present": now is None or service.is_present(m, now),
        "title": (user.title if user else None) or "",
        "dept": (user.department if user else None) or "",
    }


def _event_view(e) -> dict:
    try:
        payload = json.loads(e.payload_json or "{}")
    except (json.JSONDecodeError, ValueError):
        payload = {}
    return {"seq": e.seq, "kind": e.kind, "actor_user_id": e.actor_user_id, "payload": payload,
            "created_at": e.created_at.isoformat()}


def _viewer_org_id(db: Session, me: User) -> str | None:
    """이 사람에게 걸 조직 경계. 전역 범위면 `None`(제한 없음).

    `app/board/router.py::_viewer_org_id` 와 같은 판정이다 — 게시판·놀이 둘 다 조직 공용
    공간이고, `User.org_id` 를 그냥 쓰면 전역 관리자조차 자기 기본 조직으로 좁혀진다
    (기본값이 항상 채워져 있기 때문이다, SEC-34 와 같은 자리).
    """
    from app.core.scope import visibility_scope

    if visibility_scope(db, me).is_global:
        return None
    return getattr(me, "org_id", None)


def _get_room_or_404(db: Session, room_id: str, me: User):
    """모든 `/{room_id}` 경로의 단 하나의 문. 범위 밖은 **404** — 존재를 알려 주지 않는다.

    방 안의 실제 참여는 멤버십이 정한다(그건 각 동작이 따로 본다). 여기서 거는 것은
    **조직 경계**뿐이다: 다른 회사의 방이 id 하나로 열리면 안 된다.
    """
    room = repository.get_room(db, room_id, org_id=_viewer_org_id(db, me))
    if room is None:
        raise NotFoundError("방을 찾을 수 없습니다.")
    return room


@router.get("/rooms")
def list_rooms(request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    # 목록을 볼 때마다 버려진(폴링 끊긴) 방을 먼저 정리해 유령 방이 남지 않게 한다.
    service.cleanup_idle_rooms(db, now=request.app.state.clock.now())
    rooms = repository.list_open_rooms(db, org_id=_viewer_org_id(db, me))
    flags = load_feature_flags(request.app.state.settings.config_dir)
    # 프런트가 AI 퀴즈 생성 버튼 노출 여부를 알도록 플래그를 함께 내려준다(기본 OFF → 버튼 숨김).
    # 놀이 목록은 3초마다 폴링된다 — 방이 하나도 안 바뀐 동안은 304 로 끝낸다.
    # (위의 cleanup_idle_rooms 는 그대로 돈다: 유령 방 정리를 건너뛰면 목록이 썩는다.)
    return etag_json_response(request, {
        "items": [_room_summary(db, r) for r in rooms],
        "game_ai_enabled": bool(flags.get("game_ai_enabled", False)),
    })


@router.post("/rooms", dependencies=[Depends(require_csrf)])
def create_room(request: Request, payload: RoomCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = service.create_room(
        db, host=me, title=payload.title, game_type=payload.game_type,
        max_players=payload.max_players, allow_spectators=payload.allow_spectators,
        config=payload.config, now=request.app.state.clock.now(),
    )
    return {"room": _room_summary(db, room)}


@router.get("/rooms/{room_id}/state")
def room_state(
    request: Request, room_id: str, since: int = Query(default=0, ge=0),
    db: Session = Depends(get_db), me: User = Depends(get_current_user),
    auth: AuthContext = Depends(get_current_auth),
):
    room = _get_room_or_404(db, room_id, me)
    now = request.app.state.clock.now()
    # GET 이라 공용 임퍼소네이션 쓰기 차단을 안 지난다 — 여기서 안 막으면 관리자의 폴링이
    # 대상 사용자를 '접속 중'으로 켜고, 실제 접속 여부와 무관하게 추첨 대상 풀에도 들어간다
    # (app/core/presence.py 의 놀이 전용 경고 — last_seen 이 표시가 아니라 추첨 풀을 가른다).
    if not auth.impersonating:
        service.touch_presence(db, room, me, now=now)
    service.maybe_autoresolve(db, room, now=now)  # 마감 지난 타이머 게임을 서버가 자동 확정(방장 비의존)
    mem = repository.get_member(db, room.id, me.id)
    active_members = [m for m in repository.members(db, room.id) if m.active]
    umap = repository.users_by_ids(db, [m.user_id for m in active_members])
    return {
        "room": _room_summary(db, room),
        "state": service.public_state(room, me.id),
        "members": [_member_view(m, umap.get(m.user_id), now=now) for m in active_members],
        # 대화는 **방 안 사람에게만** (1순위 유출 #10). 로비 미리보기(방·멤버·진행 상태)는
        # 설계다 — `you.in_room` 과 `join(spectate=…)` 이 그걸 전제로 있다. 하지만 "무슨
        # 게임이 몇 명으로 돌아가는지" 를 보는 것과 "그 사람들이 무슨 말을 했는지" 를 읽는
        # 것은 다른 일이다. 방 밖에서는 대화 이벤트만 뺀다.
        "events": [
            _event_view(e)
            for e in repository.events_since(db, room.id, since)
            if mem is not None or e.kind != EV_CHAT
        ],
        "seq": room.event_seq,
        "you": {
            "user_id": me.id,
            "in_room": mem is not None,
            "role": mem.role if mem else None,
            "ready": mem.ready if mem else False,
            "is_host": room.host_user_id == me.id,
        },
    }


@router.post("/rooms/{room_id}/join", dependencies=[Depends(require_csrf)])
def join(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user),
         spectate: bool = Query(default=False)):
    room = _get_room_or_404(db, room_id, me)
    m = service.join_room(db, room, me, spectate=spectate, now=request.app.state.clock.now())
    return {"ok": True, "role": m.role}


@router.post("/rooms/{room_id}/leave", dependencies=[Depends(require_csrf)])
def leave(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.leave_room(db, room, me, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/disband", dependencies=[Depends(require_csrf)])
def disband(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    # 방장만 방을 파할 수 있다(service._ensure_host). 파하면 방이 목록·조회에서 사라진다.
    room = _get_room_or_404(db, room_id, me)
    service.disband_room(db, room, me, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/ready", dependencies=[Depends(require_csrf)])
def ready(request: Request, room_id: str, payload: ReadyInput, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.set_ready(db, room, me, ready=payload.ready, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/start", dependencies=[Depends(require_csrf)])
def start(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.start_game(db, room, me, now=request.app.state.clock.now())
    return {"room": _room_summary(db, room)}


@router.post("/rooms/{room_id}/vote", dependencies=[Depends(require_csrf)])
def vote(request: Request, room_id: str, payload: VoteInput, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.submit_vote(db, room, me, option_index=payload.option, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/pick", dependencies=[Depends(require_csrf)])
def pick(request: Request, room_id: str, payload: NumberInput, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.submit_number(db, room, me, value=payload.value, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/rps", dependencies=[Depends(require_csrf)])
def rps(request: Request, room_id: str, payload: VoteInput, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    # option: 0=가위, 1=바위, 2=보 (VoteInput 재사용).
    room = _get_room_or_404(db, room_id, me)
    service.submit_rps(db, room, me, choice=payload.option, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/quiz-answer", dependencies=[Depends(require_csrf)])
def quiz_answer(request: Request, room_id: str, payload: VoteInput, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.submit_quiz_answer(db, room, me, option_index=payload.option, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/reveal", dependencies=[Depends(require_csrf)])
def quiz_reveal(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.reveal_quiz(db, room, me, now=request.app.state.clock.now())
    return {"ok": True}


@router.post("/rooms/{room_id}/next", dependencies=[Depends(require_csrf)])
def quiz_next(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.next_quiz(db, room, me, now=request.app.state.clock.now())
    return {"room": _room_summary(db, room)}


@router.post("/quiz/generate", dependencies=[Depends(require_csrf), Depends(require_game_ai_enabled)])
def quiz_generate(
    request: Request,
    payload: QuizGenerateInput,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """주제로 AI가 퀴즈 문제를 생성한다(방 생성 전 단계 — 방/DB를 만들지 않는다). 반환한 문제는
    프런트 QuizEditor에서 사람이 검토·수정한 뒤 방을 만든다. game_ai_enabled OFF면 404."""
    limit_key = f"game-ai:{me.id}"
    if not request.app.state.game_ai_ratelimiter.allow(limit_key):
        raise RateLimitedError(
            "AI 생성을 너무 자주 요청했습니다. 잠시 후 다시 시도하세요.",
            retry_after_seconds=request.app.state.game_ai_ratelimiter.retry_after_seconds(limit_key),
        )
    questions = ai.generate_quiz(
        request.app.state.outbound_client,
        request.app.state.settings,
        topic=payload.topic,
        count=payload.count,
        num_options=payload.num_options,
    )
    return {"questions": questions}


@router.post("/rooms/{room_id}/finish", dependencies=[Depends(require_csrf)])
def finish(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.finish_game(db, room, me, now=request.app.state.clock.now())
    return {"room": _room_summary(db, room)}


@router.post("/rooms/{room_id}/reset", dependencies=[Depends(require_csrf)])
def reset(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.reset_room(db, room, me, now=request.app.state.clock.now())
    return {"room": _room_summary(db, room)}


@router.post("/rooms/{room_id}/chat", dependencies=[Depends(require_csrf)])
def chat(request: Request, room_id: str, payload: ChatInput, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id, me)
    service.chat(db, room, me, text=payload.text, now=request.app.state.clock.now())
    return {"ok": True}
