"""팀 채팅 비즈니스 규칙 — 방 생성(그룹/1:1) + append-only 메시지 로그 + 폴링 커서.

놀이(games)의 seq 할당기를 그대로 옮겼다: begin_nested 안에서 seq=event_seq+1 로 넣고, 유니크
(room_id, seq) 충돌은 SAVEPOINT로 흡수하고 재시도한다. 전체 채팅 방은 동시 전송이 몰려 seq 경쟁이
심하므로 재시도 횟수를 넉넉히 둔다. 1:1 방은 dm_key(정렬된 두 uid)로 유일하게 만들고, 동시 생성
경쟁은 유니크 위반을 잡아 승자를 다시 읽어 돌려준다. 외부 호출 없음(순수 내부 DB).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, ValidationAppError
from app.team_chat import repository
from app.team_chat.models import (
    MSG_SYSTEM,
    MSG_TEXT,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROOM_DIRECT,
    ROOM_GROUP,
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
)
from app.users.models import User

MAX_BODY = 2000
_SEQ_RETRIES = 12  # 전체 채팅은 seq 경쟁이 잦다 — 놀이(5)보다 넉넉히


def dm_key(a: str, b: str) -> str:
    return ":".join(sorted([a, b]))


def _append_message(db: Session, room: ChatRoom, *, kind: str, sender_id: str | None, body: str,
                    client_message_id: str | None, now: datetime) -> ChatMessage:
    for _ in range(_SEQ_RETRIES):
        seq = room.event_seq + 1
        msg = ChatMessage(
            room_id=room.id, seq=seq, sender_user_id=sender_id, kind=kind,
            body=body, client_message_id=client_message_id, created_at=now,
        )
        try:
            with db.begin_nested():
                db.add(msg)
                db.flush()
            room.event_seq = seq
            room.updated_at = now
            db.flush()
            return msg
        except IntegrityError:
            db.refresh(room)  # 다른 요청이 먼저 seq를 붙였다 — 다시 계산
    raise ConflictError("메시지를 보내지 못했습니다. 잠시 후 다시 시도해 주세요.")


def create_group(db: Session, user: User, *, title: str, member_user_ids: list[str], now: datetime) -> ChatRoom:
    title = (title or "").strip()
    if not title:
        raise ValidationAppError("방 이름을 입력하세요.")
    room = ChatRoom(kind=ROOM_GROUP, title=title[:200], created_by_user_id=user.id,
                    is_global=False, event_seq=0, created_at=now, updated_at=now)
    db.add(room)
    db.flush()
    # 만든 사람 = 방장, 지정한 사람들 = 멤버(중복·본인 제거).
    ids = {user.id, *[m for m in (member_user_ids or []) if m]}
    valid = set(repository.users_by_ids(db, list(ids)).keys())
    for uid in ids:
        if uid not in valid:
            continue
        db.add(ChatRoomMember(room_id=room.id, user_id=uid,
                              role=ROLE_OWNER if uid == user.id else ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=now))
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 채팅방을 만들었습니다.", client_message_id=None, now=now)
    return room


def create_or_get_direct(db: Session, user: User, *, other_user_id: str, now: datetime) -> ChatRoom:
    if not other_user_id or other_user_id == user.id:
        raise ValidationAppError("대화 상대를 선택하세요.")
    umap = repository.users_by_ids(db, [other_user_id])
    if other_user_id not in umap:
        raise ValidationAppError("대화 상대를 찾을 수 없습니다.")
    key = dm_key(user.id, other_user_id)
    existing = repository.get_direct_by_key(db, key)
    if existing is not None:
        return existing
    room = ChatRoom(kind=ROOM_DIRECT, title="", created_by_user_id=user.id, is_global=False,
                    dm_key=key, event_seq=0, created_at=now, updated_at=now)
    try:
        with db.begin_nested():
            db.add(room)
            db.flush()
    except IntegrityError:
        # 동시 생성 경쟁에서 졌다 — 먼저 만들어진 방을 돌려준다.
        won = repository.get_direct_by_key(db, key)
        if won is not None:
            return won
        raise
    for uid in (user.id, other_user_id):
        db.add(ChatRoomMember(room_id=room.id, user_id=uid, role=ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=now))
    db.flush()
    return room


def ensure_access(db: Session, room: ChatRoom, user: User) -> ChatRoomMember | None:
    """방을 볼/쓸 수 있는지. 전체 채팅 방은 멤버십 없이 누구나(멤버 None 반환). 그 외는 멤버여야 한다."""
    if room.is_global:
        return None
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("이 채팅방에 접근할 수 없습니다.")
    return member


def send_message(db: Session, room: ChatRoom, user: User, *, body: str,
                 client_message_id: str | None, now: datetime) -> ChatMessage:
    body = (body or "").strip()
    if not body:
        raise ValidationAppError("메시지를 입력하세요.")
    if client_message_id:
        dup = repository.find_by_client_id(db, room.id, client_message_id[:64])
        if dup is not None:
            return dup  # 낙관적 전송 재시도 중복 제거
    return _append_message(db, room, kind=MSG_TEXT, sender_id=user.id, body=body[:MAX_BODY],
                           client_message_id=(client_message_id or None), now=now)


def mark_read(db: Session, room: ChatRoom, user: User, *, seq: int) -> None:
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        return  # 전체 채팅 방은 멤버십이 없어 읽음 상태를 저장하지 않는다
    if seq > member.last_read_seq:
        member.last_read_seq = min(seq, room.event_seq)
        db.flush()


def leave_room(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    if room.is_global:
        raise ConflictError("전체 채팅방은 나갈 수 없습니다.")
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        return
    db.delete(member)
    db.flush()
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 나갔습니다.", client_message_id=None, now=now)


def touch_presence(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """실제 멤버만 last_seen 갱신(2초 스로틀). 전체 채팅 방은 멤버십이 없어 아무 것도 쓰지 않는다
    (모든 페이지에서 폴링하는 위젯이 매 조회마다 쓰기를 만들지 않게)."""
    if room.is_global:
        return
    member = repository.get_member(db, room.id, user.id)
    if member is not None and (now - member.last_seen).total_seconds() > 2:
        member.last_seen = now
        db.flush()
