"""자유게시판 입력 스키마 (경계 검증, 불변 규칙: 외부 데이터 불신).

extra='forbid'로 예상 못한 필드를 거절하고, 길이·카테고리·이모지·정렬 값을 화이트리스트로
제한한다. 본문은 서버에 그대로 저장하되 프런트가 textContent로만 렌더한다(§6 XSS 방지).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from app.board.models import POST_CATEGORIES, REACTION_EMOJIS, REACTION_TARGETS

MAX_TITLE = 200
MAX_BODY = 20000
MAX_COMMENT = 5000
SORT_VALUES = frozenset({"recent", "views"})


def _stripped(value: str) -> str:
    return value.strip() if isinstance(value, str) else value


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    title: str
    body: str = ""

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = _stripped(v)
        if v not in POST_CATEGORIES:
            raise ValueError("허용되지 않은 카테고리입니다.")
        return v

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
        if v not in POST_CATEGORIES:
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
