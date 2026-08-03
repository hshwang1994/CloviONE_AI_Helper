"""팀 채팅 모델 — 놀이(games)와 같은 폴링/이벤트-시퀀스 구조. 순수 내부(외부 호출 없음).

app/chat 는 AI 도우미 대화(러너/잡 기반)이고, 이 모듈은 사람 사이의 실시간 채팅이다(전혀 다름).
방마다 append-only 메시지 로그 + 정수 커서(event_seq)를 두고, GET .../messages?since=<seq> 폴링으로
따라온다(WebSocket 없이, 불변 §1 sync 유지). 1:1 방은 dm_key(정렬된 두 uid)로 유일하게 만든다.
홈 위젯용 '전체 채팅' 방 하나는 마이그레이션에서 시드하며 멤버십 없이 누구나 읽고 쓴다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)

ROOM_GROUP = "group"
ROOM_DIRECT = "direct"
ROLE_OWNER = "owner"
ROLE_MEMBER = "member"
MSG_TEXT = "text"
MSG_SYSTEM = "system"
MSG_IMAGE = "image"

# 홈 위젯이 붙는 팀 전체 방(마이그레이션에서 고정 id로 시드). 멤버십 행 없이 누구나 접근.
GLOBAL_ROOM_ID = "00000000-0000-0000-0000-0000cha70001"


class ChatRoom(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_rooms"

    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=ROOM_GROUP, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by_user_id: Mapped[str | None] = mapped_column(String(36))
    is_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 1:1 유일성: 정렬된 두 user_id 를 콜론으로 이은 키. 그룹 방은 NULL(SQLite는 NULL 중복 허용).
    dm_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class ChatRoomMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_room_members"

    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_rooms.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_MEMBER)
    last_read_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    # NULL = **아직 이 방을 한 번도 열어 보지 않았다**(0029). joined_at 을 넣어 두면
    # 방금 초대된 사람이 초대된 줄도 모르는 채로 온라인 점이 켜진다 — 없는 사람을 있다고
    # 말하는 표시가 된다. NULL 이면 service.is_online 은 꺼진 점을 주고,
    # core.presence.should_touch 는 첫 폴링에서 즉시 한 번 쓴다(그 뒤로는 30초 스로틀).
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_member"),
    )


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_messages"

    room_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_rooms.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sender_user_id: Mapped[str | None] = mapped_column(String(36))  # system 메시지는 NULL
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=MSG_TEXT)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    client_message_id: Mapped[str | None] = mapped_column(String(64))  # 낙관적 전송 중복 제거
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("room_id", "seq", name="uq_chat_message_seq"),
    )


class ChatMessageImage(UUIDPrimaryKeyMixin, Base):
    """말풍선에 인라인으로 그려지는 이미지(Ctrl+V 붙여넣기).

    파일은 `data_dir/uploads/team_chat/<room_id>/<stored_name>` 에 있고, 서빙은 반드시
    `GET /api/team-chat/messages/{message_id}/images/{image_id}` 를 거친다 —
    그 라우트가 방 접근 검사(ensure_access)를 하기 때문이다. 게시판 첨부 서빙 라우트를
    재사용하면 1:1 DM 이미지가 전사 공개가 된다(게시판은 조직 전체 공개).
    """

    __tablename__ = "chat_message_images"

    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_messages.id"), nullable=False, index=True
    )
    # 저장 경로의 owner_id — 메시지를 거치지 않고도 파일 위치를 알 수 있게 비정규화해 둔다.
    room_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 원본 표시명
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 디스크 저장명
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ChatReadCursor(UUIDPrimaryKeyMixin, Base):
    """개인별 읽음 커서 — 멤버십 행이 없는 방(전체 채팅)의 안읽음과 1:1 '나에게만 숨김'.

    **읽을 때만 쓴다.** 폴링(GET messages)은 이 표에 절대 쓰지 않는다 — 모든 화면에서
    도는 위젯이 매 조회마다 UPDATE를 만들면 SQLite 쓰기 경합이 이 앱에서 가장 뜨거워진다.
    전체 채팅 방에 대해 ChatRoomMember 행을 게으르게 만들지 않는 이유도 같다: 그러면
    `_room_summary.member_count` 의 뜻이 '멤버 수'에서 '한 번이라도 연 사람 수'로 조용히
    바뀐다.

    ``hidden_at`` 은 1:1 방 '나에게만 숨김'이다(방 파하기는 dm_key unique 때문에 금지 —
    service.disband_room 주석 참고). 숨길 때 ``last_read_seq`` 에 그 시점 event_seq 를
    박아 두고, 새 메시지로 event_seq 가 그보다 커지면 목록에 다시 나타난다.
    """

    __tablename__ = "chat_read_cursors"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_rooms.id"), nullable=False, index=True
    )
    last_read_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "room_id", name="uq_chat_read_cursor"),
    )
