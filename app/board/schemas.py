"""자유게시판 입력 스키마 (경계 검증, 불변 규칙: 외부 데이터 불신).

extra='forbid'로 예상 못한 필드를 거절하고, 길이·카테고리·이모지·정렬 값을 화이트리스트로
제한한다. 본문은 서버에 그대로 저장하되 프런트가 textContent로만 렌더한다(§6 XSS 방지).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.board.models import (
    ALL_CATEGORIES,
    CATEGORIES_BY_KIND,
    IDEA_STATUSES,
    KIND_FREE,
    POST_CATEGORIES,
    POST_KINDS,
    REACTION_EMOJIS,
    REACTION_TARGETS,
)

MAX_TITLE = 200
MAX_BODY = 20000
MAX_COMMENT = 5000
# 'likes' 는 공감(👍) 많은 순 — 제안 게시판의 기본 정렬이다.
SORT_VALUES = frozenset({"recent", "views", "likes"})
MAX_PROJECT_ID = 64


def _stripped(value: str) -> str:
    return value.strip() if isinstance(value, str) else value


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 종류를 안 주면 자유게시글이다. 기존 클라이언트(그리고 이 필드를 모르는 옛 화면)가
    # 그대로 동작해야 하므로 필수로 만들지 않는다.
    kind: str = KIND_FREE
    category: str
    title: str
    body: str = ""

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        v = _stripped(v)
        if v not in POST_KINDS:
            raise ValueError("허용되지 않은 게시판 종류입니다.")
        return v

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = _stripped(v)
        # 여기서는 '아는 카테고리인가'만 본다. 종류와의 짝은 아래 model_validator 가 본다 —
        # 필드 검증은 다른 필드(kind)를 볼 수 없기 때문이다.
        if v not in ALL_CATEGORIES:
            raise ValueError("허용되지 않은 카테고리입니다.")
        return v

    @model_validator(mode="after")
    def _category_fits_kind(self):
        """자유게시판의 '맛집'을 제안으로 올리거나 그 반대를 막는다.

        종류마다 카테고리 목록이 다르므로 짝이 맞아야 한다. 안 막으면 목록의 카테고리
        칩이 자기 게시판에 없는 값을 그리게 되고, 그 글은 어느 칩으로도 걸러지지 않는다.
        """
        allowed = CATEGORIES_BY_KIND.get(self.kind, POST_CATEGORIES)
        if self.category not in allowed:
            raise ValueError("이 게시판에서 쓸 수 없는 카테고리입니다.")
        return self

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = _stripped(v)
        if not v:
            raise ValueError("제목을 입력하세요.")
        if len(v) > MAX_TITLE:
            raise ValueError(f"제목은 {MAX_TITLE}자 이하여야 합니다.")
        return v

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        if v is None:
            return ""
        if len(v) > MAX_BODY:
            raise ValueError(f"본문은 {MAX_BODY}자 이하여야 합니다.")
        return v


class PostUpdate(BaseModel):
    """부분 수정 — 준 필드만 바꾼다. 카테고리/제목/본문."""

    model_config = ConfigDict(extra="forbid")

    category: str | None = None
    title: str | None = None
    body: str | None = None

    @field_validator("category")
    @classmethod
    def _category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _stripped(v)
        # 종류는 받지 않는다 — 글의 종류는 이미 행에 있고 바꾸는 일이 없다(바꿀 수 있게
        # 하면 상태가 붙은 제안이 자유글이 되어 배지가 유령처럼 남는다). 그래서 여기서는
        # 아는 값인지만 보고, 그 글의 종류에 맞는지는 service.update_post 가 판정한다.
        if v not in ALL_CATEGORIES:
            raise ValueError("허용되지 않은 카테고리입니다.")
        return v

    @field_validator("title")
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _stripped(v)
        if not v:
            raise ValueError("제목을 입력하세요.")
        if len(v) > MAX_TITLE:
            raise ValueError(f"제목은 {MAX_TITLE}자 이하여야 합니다.")
        return v

    @field_validator("body")
    @classmethod
    def _body(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) > MAX_BODY:
            raise ValueError(f"본문은 {MAX_BODY}자 이하여야 합니다.")
        return v


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    parent_comment_id: str | None = None

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = _stripped(v)
        if not v:
            raise ValueError("댓글 내용을 입력하세요.")
        if len(v) > MAX_COMMENT:
            raise ValueError(f"댓글은 {MAX_COMMENT}자 이하여야 합니다.")
        return v


class CommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = _stripped(v)
        if not v:
            raise ValueError("댓글 내용을 입력하세요.")
        if len(v) > MAX_COMMENT:
            raise ValueError(f"댓글은 {MAX_COMMENT}자 이하여야 합니다.")
        return v


class ReactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str
    target_id: str
    emoji: str

    @field_validator("target_type")
    @classmethod
    def _target(cls, v: str) -> str:
        if v not in REACTION_TARGETS:
            raise ValueError("허용되지 않은 반응 대상입니다.")
        return v

    @field_validator("emoji")
    @classmethod
    def _emoji(cls, v: str) -> str:
        if v not in REACTION_EMOJIS:
            raise ValueError("허용되지 않은 이모지입니다.")
        return v


class IdeaStatusUpdate(BaseModel):
    """제안 상태 변경. `project_id` 는 '진행' 으로 넘어갈 때 만들 티켓이 붙을 프로젝트다.

    티켓 스키마가 프로젝트를 요구하므로(app/tickets/notion_write.py) 운영자가 어느 일감
    묶음에 넣을지 골라야 한다. 여기서 받지 않으면 게시판이 프로젝트를 임의로 정하게 되고,
    그건 화면에 안 보이는 결정이라 나중에 아무도 이유를 설명하지 못한다.
    """

    model_config = ConfigDict(extra="forbid")

    status: str
    project_id: str | None = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = _stripped(v)
        if v not in IDEA_STATUSES:
            raise ValueError("허용되지 않은 진행 상태입니다.")
        return v

    @field_validator("project_id")
    @classmethod
    def _project(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _stripped(v)
        if len(v) > MAX_PROJECT_ID:
            raise ValueError("프로젝트 식별자가 너무 깁니다.")
        return v or None
