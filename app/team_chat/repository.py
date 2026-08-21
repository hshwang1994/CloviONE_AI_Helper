"""팀 채팅 데이터 접근 (쿼리 전용)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.team_chat.models import (
    ChatMessage,
    ChatMessageImage,
    ChatReadCursor,
    ChatRoom,
    ChatRoomMember,
)
from app.users.models import User


def get_room(db: Session, room_id: str) -> ChatRoom | None:
    return db.execute(
        select(ChatRoom).where(ChatRoom.id == room_id, ChatRoom.deleted_at.is_(None))
    ).scalar_one_or_none()


def get_global_room(db: Session) -> ChatRoom | None:
    return db.execute(
        select(ChatRoom).where(ChatRoom.is_global.is_(True), ChatRoom.deleted_at.is_(None))
    ).scalar_one_or_none()


def get_team_room(db: Session, department_id: str) -> ChatRoom | None:
    """그 부서의 팀 방(0039). 삭제된 방은 없는 것으로 본다 — 다시 만들어 준다."""
    return db.execute(
        select(ChatRoom).where(
            ChatRoom.department_id == department_id, ChatRoom.deleted_at.is_(None)
        )
    ).scalars().first()


def get_direct_by_key(db: Session, dm_key: str) -> ChatRoom | None:
    return db.execute(
        select(ChatRoom).where(ChatRoom.dm_key == dm_key, ChatRoom.deleted_at.is_(None))
    ).scalar_one_or_none()


def get_member(db: Session, room_id: str, user_id: str) -> ChatRoomMember | None:
    return db.execute(
        select(ChatRoomMember).where(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
    ).scalar_one_or_none()


def members(db: Session, room_id: str) -> list[ChatRoomMember]:
    return list(
        db.execute(select(ChatRoomMember).where(ChatRoomMember.room_id == room_id)).scalars().all()
    )


def members_for_rooms(db: Session, room_ids: list[str]) -> dict[str, list[ChatRoomMember]]:
    """room_id → 참여자들. 목록 화면이 방마다 한 번씩 묻지 않게 한 번에 읽는다 (H4).

    참여자가 없는 방은 키 자체가 없다 — 호출자가 빈 목록으로 읽으면 된다. 미리 채워 두면
    '요청한 방'과 '실제로 참여자가 있는 방'의 구분이 흐려진다.
    """
    if not room_ids:
        return {}
    rows = (
        db.execute(select(ChatRoomMember).where(ChatRoomMember.room_id.in_(list(room_ids))))
        .scalars()
        .all()
    )
    out: dict[str, list[ChatRoomMember]] = {}
    for row in rows:
        out.setdefault(row.room_id, []).append(row)
    return out


def members_for_rooms_and_user(
    db: Session, room_ids: list[str], user_id: str
) -> dict[str, ChatRoomMember]:
    """room_id → 그 사용자 한 명의 멤버 행. 안읽음 합계처럼 '나'만 필요한 호출자용(M2).

    `members_for_rooms` 는 방마다 참여자 전원을 실어 목록 화면(이름 해석)에 맞지만, 안읽음
    합계처럼 내 멤버 행 하나만 필요한 호출자가 그걸 쓰면 남의 멤버 행까지 긁어 온다. 이
    함수는 `user_id` 로 한 번 더 좁혀 필요한 행만 읽는다. 방 하나씩 `get_member` 를 부르면
    방 개수만큼 질의가 늘어난다 — `app/home/readers.chat_unread` 가 그 함정이었다.
    """
    if not room_ids:
        return {}
    rows = (
        db.execute(
            select(ChatRoomMember).where(
                ChatRoomMember.room_id.in_(list(room_ids)), ChatRoomMember.user_id == user_id
            )
        )
        .scalars()
        .all()
    )
    return {row.room_id: row for row in rows}


def last_messages_for_rooms(db: Session, room_ids: list[str]) -> dict[str, ChatMessage]:
    """room_id → 마지막(삭제 안 된) 메시지. 방 개수와 무관하게 **질의 두 번**이다 (H4).

    왜 두 번인가: 방마다 `ORDER BY seq DESC LIMIT 1` 을 돌리면 그게 곧 N+1 이다. 먼저
    방별 최대 seq 를 한 번에 구하고(집계), 그 seq 에 해당하는 행만 한 번 더 읽는다.
    윈도 함수(`row_number() OVER (PARTITION BY room_id ORDER BY seq DESC)`) 한 방으로도
    된다 — 그것을 피하던 이유(설치처 sqlite3 버전 의존)는 **더 이상 없다**. 지금 이
    모양인 것은 단지 바꿀 이유가 없어서다: 질의 두 번은 이미 방 개수와 무관하고,
    아래 「같은 seq 다른 방」 걸러내기가 시험으로 고정돼 있다.

    두 번째 질의의 `seq IN (...)` 는 **다른 방의 같은 seq** 도 걸린다(seq 는 방 안에서만
    유일하다). 그래서 방별 최대값과 맞는 행만 남긴다 — 이 한 줄을 빼면 엉뚱한 방의
    메시지가 미리보기로 나간다.
    """
    if not room_ids:
        return {}
    ids = list(room_ids)
    max_rows = db.execute(
        select(ChatMessage.room_id, func.max(ChatMessage.seq))
        .where(ChatMessage.room_id.in_(ids), ChatMessage.deleted_at.is_(None))
        .group_by(ChatMessage.room_id)
    ).all()
    top: dict[str, int] = {room_id: seq for room_id, seq in max_rows if seq is not None}
    if not top:
        return {}
    rows = (
        db.execute(
            select(ChatMessage).where(
                ChatMessage.room_id.in_(list(top.keys())),
                ChatMessage.seq.in_(sorted(set(top.values()))),
                ChatMessage.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return {row.room_id: row for row in rows if top.get(row.room_id) == row.seq}


def rooms_for_user(db: Session, user_id: str) -> list[ChatRoom]:
    """사용자가 속한(삭제 안 된) 방들 — 그룹·1:1. 전체 채팅 방은 서비스가 따로 붙인다."""
    return list(
        db.execute(
            select(ChatRoom)
            .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
            .where(ChatRoomMember.user_id == user_id, ChatRoom.deleted_at.is_(None))
            .order_by(ChatRoom.updated_at.desc())
        ).scalars().all()
    )


def messages_since(db: Session, room_id: str, since: int, *, limit: int = 200) -> list[ChatMessage]:
    """seq > since 인 메시지(삭제 제외)를 seq 오름차순으로. since=0 이면 처음부터(최근 limit개)."""
    rows = list(
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.room_id == room_id, ChatMessage.seq > since, ChatMessage.deleted_at.is_(None))
            .order_by(ChatMessage.seq.desc())
            .limit(limit)
        ).scalars().all()
    )
    rows.reverse()  # 최근 limit개를 시간순(오름차순)으로
    return rows


def last_message(db: Session, room_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id, ChatMessage.deleted_at.is_(None))
        .order_by(ChatMessage.seq.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_message_by_seq(db: Session, room_id: str, seq: int) -> ChatMessage | None:
    """방 안의 seq 하나를 집는다(삭제된 것도 포함).

    삭제된 행까지 돌려주는 이유: 삭제 요청이 두 번 오면(느린 네트워크의 재시도) '이미 삭제됨'과
    '그런 메시지 없음'을 구분해서 답해야 한다. 없는 것으로 답하면 404 가 뜨고 사용자는
    자기 메시지가 사라졌는지 실패했는지 알 수 없다.
    """
    return db.execute(
        select(ChatMessage).where(ChatMessage.room_id == room_id, ChatMessage.seq == seq)
    ).scalar_one_or_none()


def find_by_client_id(db: Session, room_id: str, client_message_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage).where(
            ChatMessage.room_id == room_id, ChatMessage.client_message_id == client_message_id
        )
    ).scalar_one_or_none()


def get_message(db: Session, message_id: str) -> ChatMessage | None:
    return db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id, ChatMessage.deleted_at.is_(None)
        )
    ).scalar_one_or_none()


def get_image(db: Session, message_id: str, image_id: str) -> ChatMessageImage | None:
    """이미지는 항상 자기 메시지와 짝지어 조회한다 — image_id만으로 찾으면 다른 방의
    이미지를 자기 방 메시지 id에 붙여 부르는 경로가 열린다."""
    return db.execute(
        select(ChatMessageImage).where(
            ChatMessageImage.id == image_id, ChatMessageImage.message_id == message_id
        )
    ).scalar_one_or_none()


def images_for_messages(db: Session, message_ids: list[str]) -> dict[str, list[ChatMessageImage]]:
    """메시지 목록 한 번에 이미지 붙이기(N+1 회피). 이미지 없는 방은 쿼리 자체를 건너뛴다."""
    if not message_ids:
        return {}
    rows = (
        db.execute(
            select(ChatMessageImage)
            .where(ChatMessageImage.message_id.in_(list(message_ids)))
            .order_by(ChatMessageImage.created_at)
        )
        .scalars()
        .all()
    )
    out: dict[str, list[ChatMessageImage]] = {}
    for row in rows:
        out.setdefault(row.message_id, []).append(row)
    return out


def get_cursor(db: Session, room_id: str, user_id: str) -> ChatReadCursor | None:
    return db.execute(
        select(ChatReadCursor).where(
            ChatReadCursor.room_id == room_id, ChatReadCursor.user_id == user_id
        )
    ).scalar_one_or_none()


def cursors_for_user(db: Session, user_id: str) -> dict[str, ChatReadCursor]:
    """room_id → 커서. 목록 화면이 방마다 한 번씩 묻지 않게 한 번에 읽는다."""
    rows = (
        db.execute(select(ChatReadCursor).where(ChatReadCursor.user_id == user_id))
        .scalars()
        .all()
    )
    return {row.room_id: row for row in rows}


def cursors_for_room(db: Session, room_id: str) -> dict[str, ChatReadCursor]:
    """user_id → 커서(방 하나). 멤버 행이 없는 참여자의 읽음 위치를 한 번에 읽는다."""
    rows = (
        db.execute(select(ChatReadCursor).where(ChatReadCursor.room_id == room_id))
        .scalars()
        .all()
    )
    return {row.user_id: row for row in rows}


def users_by_ids(db: Session, ids: list[str]) -> dict[str, User]:
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(list(ids)))).scalars().all()
    return {u.id: u for u in rows}


def directory(db: Session, exclude_user_id: str, *, org_id: str | None = None) -> list[User]:
    """1:1 상대 고르기용 — 활성·비보관 사용자(본인 제외). 이름/부서/직책만 노출(라우터에서).

    `org_id` 를 주면 **그 조직 사람만** (1순위 유출 #7). 부서로는 좁히지 않는다 — 다른 팀에
    DM 을 못 보내게 되면 그건 기능 축소지 보안이 아니다. 맞는 축은 조직이고, 이 목록은
    이름·부서·직책을 그대로 주므로 **조직도 열거**가 된다.
    """
    stmt = (
        select(User)
        .where(User.active.is_(True), User.archived_at.is_(None), User.id != exclude_user_id)
    )
    if org_id:
        stmt = stmt.where(User.org_id == org_id)
    return list(db.execute(stmt.order_by(User.display_name)).scalars().all())
