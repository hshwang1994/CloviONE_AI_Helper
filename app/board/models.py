"""자유게시판 모델 (팀 공간 §18, §20).

게시판은 순수 내부 기능이다 — 외부 호출(Notion/모델) 없음. 게시글·댓글은
소프트 삭제(deleted_at)로 되돌릴 수 있게 남기고, 첨부는 파일시스템에 저장한 뒤
메타만 여기 둔다(실제 바이트는 data_dir/uploads, app/core/uploads.py 참조).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)

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

# ── 게시글 종류 ──────────────────────────────────────────────────────────────
#
# 기능 개선 제안 게시판(7단계 #1)은 **새 표도 새 모듈도 아니다** — 이 표의 종류가 하나 는
# 것뿐이다. 표를 나눴다면 첨부·댓글·반응·알림·검색·조직 범위가 전부 두 벌이 되고, 그중
# 한쪽만 고쳐지는 날이 반드시 온다(이 저장소가 목록만 좁히고 단건은 안 좁힌 실수를 네 번
# 했다 — scripts/check_scope_gates.py 서문). 종류 하나로 두면 그 길이 계속 하나다.
KIND_FREE = "free"
KIND_IDEA = "idea"
POST_KINDS: frozenset[str] = frozenset({KIND_FREE, KIND_IDEA})

# 아이디어 카테고리. 자유게시판의 '맛집'·'공지'는 제안에 뜻이 없고, 반대로 제안의 분류는
# 자유글에 뜻이 없다. 값 공간을 섞지 않고 종류별로 나눠 둔다.
IDEA_CATEGORY_FEATURE = "기능"
IDEA_CATEGORY_UX = "사용성"
IDEA_CATEGORY_PERF = "성능"
IDEA_CATEGORY_ETC = "기타"
IDEA_CATEGORIES: frozenset[str] = frozenset(
    {IDEA_CATEGORY_FEATURE, IDEA_CATEGORY_UX, IDEA_CATEGORY_PERF, IDEA_CATEGORY_ETC}
)

# 종류 → 그 종류가 쓸 수 있는 카테고리. **판정은 여기 한 곳**이라 화면·스키마·서비스가
# 각자 다른 목록을 들고 있다가 어긋나는 일이 없다.
CATEGORIES_BY_KIND: dict[str, frozenset[str]] = {
    KIND_FREE: POST_CATEGORIES,
    KIND_IDEA: IDEA_CATEGORIES,
}
# 스키마 경계에서 쓰는 합집합. 종류별 판정은 서비스가 한다(수정은 kind 를 안 받는다 —
# 글의 종류는 이미 행에 있고, 그것을 바꾸는 일은 없다).
ALL_CATEGORIES: frozenset[str] = POST_CATEGORIES | IDEA_CATEGORIES

# ── 제안 상태 ────────────────────────────────────────────────────────────────
#
# 저장값을 한국어로 둔다(카테고리와 같은 규약). 영문 코드로 두면 화면·감사·알림이 각자
# 라벨 표를 하나씩 들게 되고, 그 표들이 어긋나는 날이 온다.
IDEA_PROPOSED = "제안"
IDEA_REVIEWING = "검토중"
IDEA_IN_PROGRESS = "진행"
IDEA_DONE = "완료"
IDEA_ON_HOLD = "보류"
# 화면 노출 순서 = 일이 흘러가는 순서. 필터 칩도 이 순서로 그린다.
IDEA_STATUSES: tuple[str, ...] = (
    IDEA_PROPOSED, IDEA_REVIEWING, IDEA_IN_PROGRESS, IDEA_DONE, IDEA_ON_HOLD,
)

# 어디서 어디로 갈 수 있는가. 아무 데서나 아무 데로 갈 수 있으면 상태는 그냥 라벨이고,
# '검토를 건너뛰고 진행으로 갔다' 같은 일이 조용히 벌어진다(진행은 티켓을 만든다 —
# 되돌릴 수 없는 쪽이라 더 그렇다).
#
# 보류는 진행 전 어느 단계에서나 갈 수 있고, 보류에서는 제안·검토로 돌아온다.
# 완료에서 나가는 길은 '진행' 하나뿐이다(잘못 닫은 것을 되돌리는 재개). 완료에서 곧장
# 제안으로 돌아가는 길은 두지 않는다 — 그건 되돌리기가 아니라 이력을 지우는 것이다.
IDEA_TRANSITIONS: dict[str, frozenset[str]] = {
    IDEA_PROPOSED: frozenset({IDEA_REVIEWING, IDEA_ON_HOLD}),
    IDEA_REVIEWING: frozenset({IDEA_IN_PROGRESS, IDEA_ON_HOLD, IDEA_PROPOSED}),
    IDEA_IN_PROGRESS: frozenset({IDEA_DONE, IDEA_ON_HOLD}),
    IDEA_DONE: frozenset({IDEA_IN_PROGRESS}),
    IDEA_ON_HOLD: frozenset({IDEA_PROPOSED, IDEA_REVIEWING}),
}

# 반응 이모지 화이트리스트 — 자유 입력이 아니라 고정 집합이라 UI가 일관되고 저장값이
# 예측 가능하다(§18 "이모지 반응"). 렌더는 textContent 전용이라 XSS 위험은 없지만,
# 임의 문자열을 반응으로 저장하지 않는다.
REACTION_EMOJIS: tuple[str, ...] = ("👍", "❤️", "😂", "🎉", "👀", "🙏")

# 반응 대상 종류.
TARGET_POST = "post"
TARGET_COMMENT = "comment"
REACTION_TARGETS: frozenset[str] = frozenset({TARGET_POST, TARGET_COMMENT})

# '공감' 은 새 표가 아니라 **이미 있는 반응 중 👍** 하나다. 제안 게시판을 위해 공감 표를
# 따로 만들면 같은 사람의 같은 뜻이 두 군데 쌓이고, 자유게시판의 👍 와 뜻이 갈린다.
LIKE_EMOJI = REACTION_EMOJIS[0]


class Post(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "board_posts"
    __table_args__ = (
        Index("ix_board_posts_created_at", "created_at"),
    )

    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    # 종류. **NOT NULL + 서버 기본값**이라 컬럼이 생기기 전에 쓰인 행도, 이 컬럼을 모르는
    # 옛 경로가 넣는 행도 전부 '자유'로 떨어진다. nullable 로 두면 `kind = 'free'` 조건이
    # NULL 행을 못 골라 **사내 게시판이 하루아침에 통째로 빈다**(0048 이 같은 이유를 적어
    # 두었고, tests/integration/test_idea_board.py 가 컬럼을 뺀 INSERT 로 그걸 지킨다).
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=KIND_FREE, server_default=KIND_FREE, index=True
    )
    # 아래 둘은 **아이디어에만 뜻이 있다.** 자유글은 NULL 이고, 라우터가 종류를 보고 응답에
    # 실을지 정한다 — 값이 새 나가면 화면이 자유게시글에 상태 배지를 그린다.
    idea_status: Mapped[str | None] = mapped_column(String(16), index=True)
    # 진행으로 넘길 때 만든 티켓(Notion page id). 제안이 실제 일이 된 자리의 유일한 흔적이다.
    ticket_page_id: Mapped[str | None] = mapped_column(String(64), index=True)
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
