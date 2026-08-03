"""팀 채팅 API — 방 목록/생성(그룹·1:1)/메시지 폴링/전송/읽음/나가기 + 사용자 디렉터리.

순수 내부 기능(외부 호출 없음). 조회는 인증만, 상태변경은 CSRF. IDOR 차단: 1:1·그룹 방은 멤버만
접근(전체 채팅 방만 예외로 누구나). 폴링은 GET .../messages?since=<seq> 로 놀이와 같은 커서를 쓴다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import NotFoundError, RateLimitedError
from app.core.feature_flags import load_feature_flags
from app.team_chat import repository, service
from app.team_chat.models import ROOM_DIRECT
from app.team_chat.schemas import DirectCreate, GroupCreate, MessageCreate, ReadInput
from app.users.models import User


def require_team_chat_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("team_chat_enabled", True):
        raise NotFoundError("팀 채팅 기능이 비활성화되어 있습니다.")


router = APIRouter(prefix="/api/team-chat", tags=["team-chat"], dependencies=[Depends(require_team_chat_enabled)])


def _room_title(room, members, names, me_id) -> str:
    if room.is_global:
        return room.title or "전체 채팅"
    if room.kind == ROOM_DIRECT:
        other = next((m.user_id for m in members if m.user_id != me_id), None)
        u = names.get(other)
        return (u.display_name if u else "대화") if other else "대화"
    return room.title or "채팅방"


def _room_summary(db: Session, room, me_id, names) -> dict:
    mem = repository.members(db, room.id)
    my = next((m for m in mem if m.user_id == me_id), None)
    last = repository.last_message(db, room.id)
    return {
        "id": room.id,
        "kind": room.kind,
        "is_global": room.is_global,
        "title": _room_title(room, mem, names, me_id),
        "member_count": len(mem),
        "last_preview": (last.body[:80] if last and last.kind == "text" else (last.body[:80] if last else "")),
        "last_at": last.created_at.isoformat() if last else None,
        "seq": room.event_seq,
        "unread": max(0, room.event_seq - (my.last_read_seq if my else 0)) if not room.is_global else 0,
    }


@router.get("/rooms")
def list_rooms(request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    rooms = repository.rooms_for_user(db, me.id)
    glob = repository.get_global_room(db)
    # 상대 이름 해석을 위해 모든 방의 멤버 user_id 를 한 번에 읽는다.
    all_uids: set[str] = set()
    for r in rooms:
        for m in repository.members(db, r.id):
            all_uids.add(m.user_id)
    names = repository.users_by_ids(db, list(all_uids))
    items = [_room_summary(db, r, me.id, names) for r in rooms]
    result = {"items": items}
    if glob is not None:
        result["global"] = _room_summary(db, glob, me.id, names)
    return result


@router.post("/rooms", dependencies=[Depends(require_csrf)])
def create_group(request: Request, payload: GroupCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = service.create_group(db, me, title=payload.title, member_user_ids=payload.member_user_ids,
                                now=request.app.state.clock.now())
    record_audit_from_request(request, db, action="team_chat.create_group", object_type="chat_room",
                              object_id=room.id, after={"title": room.title})
    return {"room": {"id": room.id, "kind": room.kind, "title": room.title}}


@router.post("/rooms/direct", dependencies=[Depends(require_csrf)])
def create_direct(request: Request, payload: DirectCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = service.create_or_get_direct(db, me, other_user_id=payload.user_id, now=request.app.state.clock.now())
    return {"room": {"id": room.id, "kind": room.kind}}


def _get_room_or_404(db, room_id):
    room = repository.get_room(db, room_id)
    if room is None:
        raise NotFoundError("채팅방을 찾을 수 없습니다.")
    return room


def _msg_view(m, names) -> dict:
    u = names.get(m.sender_user_id) if m.sender_user_id else None
    return {
        "seq": m.seq, "kind": m.kind, "sender_user_id": m.sender_user_id,
        "sender_name": u.display_name if u else "",
        "body": m.body, "created_at": m.created_at.isoformat(),
    }


@router.get("/rooms/{room_id}/messages")
def room_messages(request: Request, room_id: str, since: int = Query(default=0, ge=0),
                  db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    member = service.ensure_access(db, room, me)  # 멤버 아니면 403(전체 채팅만 예외)
    now = request.app.state.clock.now()
    service.touch_presence(db, room, me, now=now)
    msgs = repository.messages_since(db, room.id, since)
    mem = repository.members(db, room.id)
    names = repository.users_by_ids(db, list({m.sender_user_id for m in msgs if m.sender_user_id} | {m.user_id for m in mem}))
    return {
        "room": {"id": room.id, "kind": room.kind, "is_global": room.is_global,
                 "title": _room_title(room, mem, names, me.id)},
        "members": [{"user_id": m.user_id, "name": (names.get(m.user_id).display_name if names.get(m.user_id) else ""), "role": m.role} for m in mem],
        "messages": [_msg_view(m, names) for m in msgs],
        "seq": room.event_seq,
        "you": {"user_id": me.id, "role": member.role if member else None,
                "last_read_seq": member.last_read_seq if member else 0, "is_member": member is not None},
    }


@router.post("/rooms/{room_id}/messages", dependencies=[Depends(require_csrf)])
def send_message(request: Request, room_id: str, payload: MessageCreate,
                 db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    key = f"team-chat:{me.id}"
    if not request.app.state.chat_ratelimiter.allow(key):
        raise RateLimitedError("메시지를 너무 빨리 보냈습니다. 잠시 후 다시 시도하세요.",
                               retry_after_seconds=request.app.state.chat_ratelimiter.retry_after_seconds(key))
    msg = service.send_message(db, room, me, body=payload.body,
                               client_message_id=payload.client_message_id, now=request.app.state.clock.now())
    return {"ok": True, "seq": msg.seq}


@router.post("/rooms/{room_id}/read", dependencies=[Depends(require_csrf)])
def mark_read(request: Request, room_id: str, payload: ReadInput,
              db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    service.mark_read(db, room, me, seq=payload.seq)
    return {"ok": True}


@router.post("/rooms/{room_id}/leave", dependencies=[Depends(require_csrf)])
def leave(request: Request, room_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    room = _get_room_or_404(db, room_id)
    service.ensure_access(db, room, me)
    service.leave_room(db, room, me, now=request.app.state.clock.now())
    return {"ok": True}


@router.get("/directory")
def directory(request: Request, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """1:1 상대 고르기용 사용자 목록 — 이름·부서·직책만(이메일·역할·비밀은 절대 안 나감)."""
    users = repository.directory(db, me.id)
    return {"users": [{"user_id": u.id, "display_name": u.display_name,
                       "dept": u.department or "", "title": u.title or ""} for u in users]}
