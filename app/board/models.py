"""자유게시판 모델 (팀 공간 §18, §20).

게시판은 순수 내부 기능이다 — 외부 호출(n8n/Notion/Claude) 없음. 게시글·댓글은
소프트 삭제(deleted_at)로 되돌릴 수 있게 남기고, 첨부는 파일시스템에 저장한 뒤
메타만 여기 둔다(실제 바이트는 data_dir/uploads, app/core/uploads.py 참조).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

# 카테고리는 고정 상수다(테이블 대신) — "카테고리는 페이지 내부 필터"(§18). '전체'는
# 저장값이 아니라 목록 필터의 전체 보기이므로 여기 없다.
CATEGORY_FREE = "자유"
CATEGORY_QUESTION = "질문"
CATEGORY_INFO = "정보 공유"
CATEGORY_FOOD = "맛집"
CATEGORY_NOTICE = "공지"
POST_CATEGORIES: frozenset[str] = frozenset(
    {CATEGORY_FREE, CATEGORY_QUESTION, CATEGORY_INFO, CATEGORY_FOOD, CATEGORY_NOTICE}
)

# 반응 이모지 화이트리스트 — 자유 입력이 아니라 고정 집합이라 UI가 일관되고 저장값이
# 예측 가능하다(§18 "이모지 반응"). 렌더는 textContent 전용이라 XSS 위험은 없지만,
# 임의 문자열을 반응으로 저장하지 않는다.
REACTION_EMOJIS: tuple[str, ...] = ("👍", "❤️", "😂", "🎉", "👀", "🙏")

# 반응 대상 종류.
TARGET_POST = "post"
TARGET_COMMENT = "comment"
REACTION_TARGETS: frozenset[str] = frozenset({TARGET_POST, TARGET_COMMENT})


class Post(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "board_posts"

    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 소프트 삭제 — NULL이면 살아 있는 글. 하드 삭제 대신 값을 채워 목록·검색에서 빼되
    # 행은 남긴다(되돌릴 수 있고 감사에 친화적, users.archived_at와 같은 규약).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "board_comments"

    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("board_posts.id"), nullable=False, index=True
    )
    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    # 한 단계 답글만(§18) — 부모가 있으면 그 부모는 최상위 댓글이어야 한다(서비스가 강제).
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("board_comments.id"), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class Reaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "board_reactions"

    target_type: Mapped[str] = mapped_column(String(16), nullable=False)  # post|comment
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    __table_args__ = (
        # 같은 사용자가 같은 대상에 같은 이모지를 두 번 못 남긴다(토글의 근거).
        UniqueConstraint(
            "target_type", "target_id", "user_id", "emoji", name="uq_board_reaction"
        ),
    )


class PostAttachment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "board_attachments"

    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("board_posts.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 원본 표시명
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 디스크 저장명
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
