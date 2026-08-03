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
from app.core.presence import should_touch
from app.notifications.service import notify_user
from app.team_chat import repository
from app.team_chat.models import (
    MSG_IMAGE,
    MSG_SYSTEM,
    MSG_TEXT,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROOM_DIRECT,
    ROOM_GROUP,
    ChatMessage,
    ChatMessageImage,
    ChatReadCursor,
    ChatRoom,
    ChatRoomMember,
)
from app.users.models import User

MAX_BODY = 2000
_SEQ_RETRIES = 12  # 전체 채팅은 seq 경쟁이 잦다 — 놀이(5)보다 넉넉히

# 초대 알림 유형 — 프런트 TYPE_KO / RELATED_DESTINATIONS 와 짝이다.
NOTI_CHAT_INVITED = "chat_invited"
RELATED_CHAT_ROOM = "chat_room"


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
    _notify_invited(db, user, room, [uid for uid in ids if uid != user.id and uid in valid], now=now)
    return room


def _notify_invited(db: Session, inviter: User, room: ChatRoom, user_ids: list[str], *, now: datetime) -> None:
    """초대된 사람에게만 알림 — 초대한 본인은 제외한다(자기가 만든 방을 알림으로 다시 알릴 이유가 없다).

    related=("chat_room", room_id) 는 알림 벨의 딥링크 표(app/notifications/destinations.py)가
    `#/chat-rooms/<id>` 로 푸는 좌표다.
    """
    label = room.title.strip() if room.title else ""
    for uid in user_ids:
        notify_user(
            db,
            uid,
            type_=NOTI_CHAT_INVITED,
            title=f"{inviter.display_name}님이 대화에 초대했습니다.",
            body=(f"채팅방: {label}" if label else None),
            related=(RELATED_CHAT_ROOM, room.id),
            now=now,
        )


def create_or_get_direct(db: Session, user: User, *, other_user_id: str, now: datetime) -> ChatRoom:
    if not other_user_id or other_user_id == user.id:
        raise ValidationAppError("대화 상대를 선택하세요.")
    umap = repository.users_by_ids(db, [other_user_id])
    if other_user_id not in umap:
        raise ValidationAppError("대화 상대를 찾을 수 없습니다.")
    key = dm_key(user.id, other_user_id)
    existing = repository.get_direct_by_key(db, key)
    if existing is not None:
        # 내가 숨겨 뒀던 대화를 다시 열면 숨김을 푼다 — 그렇지 않으면 "1:1 대화 시작"이
        # 200을 돌려주는데 목록에는 아무것도 안 나타나는 유령 상태가 된다.
        unhide_room(db, existing, user)
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
            unhide_room(db, won, user)
            return won
        raise
    for uid in (user.id, other_user_id):
        db.add(ChatRoomMember(room_id=room.id, user_id=uid, role=ROLE_MEMBER,
                              last_read_seq=0, joined_at=now, last_seen=now))
    db.flush()
    _notify_invited(db, user, room, [other_user_id], now=now)
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


def send_image_message(db: Session, room: ChatRoom, user: User, *, filename: str,
                       stored_name: str, media_type: str, size_bytes: int,
                       client_message_id: str | None, now: datetime) -> tuple[ChatMessage, ChatMessageImage]:
    """붙여넣은 이미지 한 장 = 메시지 한 개(kind='image') + 이미지 행 한 개.

    본문(body)에는 새니타이즈된 표시용 파일명을 남긴다 — 그림을 못 그리는 자리(스크린리더
    alt, 감사, 나중의 검색)에서 무엇이 왔는지 남는 유일한 흔적이다. 목록 미리보기는 이 값을
    쓰지 않는다(붙여넣기 파일명은 'paste.png' 라 목록이 파일 탐색기처럼 읽힌다 —
    router._last_preview 가 '사진'으로 바꾼다).
    """
    if client_message_id:
        dup = repository.find_by_client_id(db, room.id, client_message_id[:64])
        if dup is not None:
            existing = repository.images_for_messages(db, [dup.id]).get(dup.id) or []
            if existing:
                return dup, existing[0]  # 낙관적 전송 재시도 중복 제거
    msg = _append_message(db, room, kind=MSG_IMAGE, sender_id=user.id,
                          body=filename[:MAX_BODY], client_message_id=(client_message_id or None), now=now)
    image = ChatMessageImage(
        message_id=msg.id, room_id=room.id, filename=filename, stored_name=stored_name,
        media_type=media_type, size_bytes=size_bytes, created_at=now,
    )
    db.add(image)
    db.flush()
    return msg, image


def unread_for(room: ChatRoom, member: ChatRoomMember | None, cursor: ChatReadCursor | None) -> int:
    """방 하나의 안읽음 — 멤버 방은 멤버 행이, 전체 채팅 방은 읽음 커서가 기준이다.

    커서가 아예 없으면(그 사용자가 전체 채팅을 한 번도 읽지 않았다) event_seq 전부가 안읽음이다.
    0으로 뭉개면 '새 메시지가 와도 영영 배지가 안 뜨는' 상태가 되므로 그렇게 하지 않는다.
    """
    base = member.last_read_seq if member is not None else (cursor.last_read_seq if cursor else 0)
    return max(0, room.event_seq - base)


def mark_read(db: Session, room: ChatRoom, user: User, *, seq: int, now: datetime) -> None:
    """**읽을 때만** 쓴다. 폴링(GET messages)은 이 경로를 부르지 않는다.

    이미 그 seq 까지 읽은 상태면 아무것도 쓰지 않는다 — 프런트가 방을 열어 둔 채로 같은
    seq 로 반복 호출해도 UPDATE 가 나가지 않아야 한다(SQLite 쓰기 경합).
    """
    seq = min(max(0, seq), room.event_seq)
    member = repository.get_member(db, room.id, user.id)
    if member is not None:
        if seq > member.last_read_seq:
            member.last_read_seq = seq
            db.flush()
        return
    # 멤버십 행이 없는 방(전체 채팅) — 여기서 ChatRoomMember 를 게으르게 만들면
    # member_count 의 뜻이 '멤버 수'에서 '한 번이라도 연 사람 수'로 바뀐다. 커서만 쓴다.
    cursor = repository.get_cursor(db, room.id, user.id)
    if cursor is None:
        if seq <= 0:
            return  # 읽을 게 없었다 — 빈 행을 만들지 않는다
        db.add(ChatReadCursor(room_id=room.id, user_id=user.id, last_read_seq=seq,
                              hidden_at=None, updated_at=now))
        db.flush()
        return
    if seq > cursor.last_read_seq:
        cursor.last_read_seq = seq
        cursor.updated_at = now
        db.flush()


def hide_room(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """1:1 '나에게만 숨김' — 방을 지우지 않고 내 목록에서만 감춘다.

    1:1 은 파할 수 없다(disband_room 주석 참고). 대신 지금 event_seq 를 커서에 박아 두고
    숨긴다 — 상대가 새 메시지를 보내면 event_seq 가 그보다 커져 목록에 다시 나타난다.
    """
    if room.is_global:
        raise ConflictError("전체 채팅방은 숨길 수 없습니다.")
    ensure_access(db, room, user)
    cursor = repository.get_cursor(db, room.id, user.id)
    if cursor is None:
        cursor = ChatReadCursor(room_id=room.id, user_id=user.id, last_read_seq=room.event_seq,
                                hidden_at=now, updated_at=now)
        db.add(cursor)
    else:
        cursor.last_read_seq = room.event_seq
        cursor.hidden_at = now
        cursor.updated_at = now
    db.flush()


def unhide_room(db: Session, room: ChatRoom, user: User) -> None:
    cursor = repository.get_cursor(db, room.id, user.id)
    if cursor is not None and cursor.hidden_at is not None:
        cursor.hidden_at = None
        db.flush()


def is_hidden_for(room: ChatRoom, cursor: ChatReadCursor | None) -> bool:
    """숨김은 '그때까지의 대화'에만 걸린다 — 새 메시지가 오면 방이 다시 보인다."""
    return cursor is not None and cursor.hidden_at is not None and room.event_seq <= cursor.last_read_seq


def disband_room(db: Session, room: ChatRoom, user: User, *, now: datetime) -> None:
    """방 파하기(soft delete) — 방장만. 전체 채팅과 1:1 은 409.

    1:1 을 파하면 안 되는 이유(실제로 500을 만든다): `chat_rooms.dm_key` 는 unique 이고
    모든 조회가 `deleted_at IS NULL` 로 거른다. soft-delete 한 DM 은 조회에서 사라지지만
    유니크 인덱스에는 그대로 남는다 → 같은 상대와 다시 대화를 시작하면
    `create_or_get_direct` 가 방을 못 찾아 INSERT 하고, dm_key 충돌로 IntegrityError,
    except 절이 다시 읽어도 여전히 None → raise → **다음 1:1 이 500**.
    그래서 1:1 은 hide_room('나에게만 숨김')으로 보낸다. 정말 파하기를 지원하려면
    같은 트랜잭션에서 dm_key 를 NULL 로 만들어야 한다.
    """
    if room.is_global:
        raise ConflictError("전체 채팅방은 파할 수 없습니다.")
    if room.kind == ROOM_DIRECT:
        raise ConflictError("1:1 대화는 파할 수 없습니다. 내 목록에서 숨기기를 사용하세요.")
    member = repository.get_member(db, room.id, user.id)
    if member is None:
        raise ForbiddenError("이 채팅방에 접근할 수 없습니다.")
    if member.role != ROLE_OWNER:
        raise ForbiddenError("방장만 채팅방을 파할 수 있습니다.")
    _append_message(db, room, kind=MSG_SYSTEM, sender_id=None,
                    body=f"{user.display_name}님이 채팅방을 파했습니다.", client_message_id=None, now=now)
    room.deleted_at = now
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
    """실제 멤버만 last_seen 갱신. 전체 채팅 방은 멤버십이 없어 아무 것도 쓰지 않는다
    (모든 페이지에서 폴링하는 위젯이 매 조회마다 쓰기를 만들지 않게).

    스로틀은 2초에서 **30초**로 올렸다(app/core/presence.py). 2초는 폴링 주기와 거의 같아
    사실상 스로틀이 아니었고, 읽기 폴링이 그대로 쓰기 부하가 됐다 — SQLite writer 는 하나라
    사람이 늘수록 아무도 아무것도 안 하는 동안에도 쓰기 큐가 찬다.
    온라인 점의 임계값(계획 F)은 2분 이상으로 잡는다 — 30초면 그 창 안에 네 번은 찍혀서
    실제로 붙어 있는 사람이 깜빡이지 않는다."""
    if room.is_global:
        return
    member = repository.get_member(db, room.id, user.id)
    if member is not None and should_touch(member.last_seen, now):
        member.last_seen = now
        db.flush()
