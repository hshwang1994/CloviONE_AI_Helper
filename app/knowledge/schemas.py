"""Knowledge Domain 요청 스키마 (S7).

길이 상한을 전부 적는다 — 상한이 없는 문자열 필드는 그대로 DB 컬럼 길이 초과가 되고,
그 실패는 422 가 아니라 500 이다.

**본문(`body`)에는 길이 상한이 없다.** 옛 코드가 100줄·1900자에서 저장을 거절하던 것을
S7 이 없앴다(D-198) — 그 두 수는 Notion API 의 한 번 요청 상한이지 이 제품의 규칙이
아니었다. 본문이 통과해야 하는 것은 길이가 아니라 **모양**이고, 그 검사는
`app/knowledge/blocks.py` 가 한다(모르는 노드 · 위험한 링크 · 과도한 중첩).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.ownership import (
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
    OWNER_UNSET,
)
from app.knowledge.models import DREL_KINDS, SOURCE_TYPES

_OWNER_KINDS = (OWNER_PROJECT, OWNER_DEPARTMENT, OWNER_ORGANIZATION, OWNER_UNSET)
_SLUG = r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$"


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # 주소에 나가는 이름이라 글자를 제한한다. 대문자·공백·한글을 허용하면 같은 공간이
    # 여러 주소로 불리고, 그중 하나만 링크로 돌아다닌다.
    slug: str = Field(pattern=_SLUG, max_length=64)
    description: str = Field(default="", max_length=2000)
    owner_kind: str = Field(pattern="^(" + "|".join(_OWNER_KINDS) + ")$")
    owner_dept_id: str | None = Field(default=None, max_length=36)
    owner_project_id: str | None = Field(default=None, max_length=36)
    confidential: bool = False


class SpaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    owner_kind: str | None = Field(
        default=None, pattern="^(" + "|".join(_OWNER_KINDS) + ")$"
    )
    owner_dept_id: str | None = Field(default=None, max_length=36)
    owner_project_id: str | None = Field(default=None, max_length=36)
    confidential: bool | None = None
    archived: bool | None = None
    base_version: int | None = Field(default=None, ge=1)


class FolderCreate(BaseModel):
    space_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = Field(default=None, max_length=36)
    before_id: str | None = Field(default=None, max_length=36)
    after_id: str | None = Field(default=None, max_length=36)


class FolderUpdate(BaseModel):
    """이름 · 부모 · 자리를 한 번에.

    `reparent` 가 따로 있는 이유: `parent_id=null` 은 「뿌리로 옮긴다」이고 「부모를 안
    건드린다」가 아니다. 한 값으로 두 뜻을 표현하면 뿌리로 옮기는 요청이 조용히 무시된다.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = Field(default=None, max_length=36)
    reparent: bool = False
    before_id: str | None = Field(default=None, max_length=36)
    after_id: str | None = Field(default=None, max_length=36)


class DocumentCreate(BaseModel):
    space_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=500)
    folder_id: str | None = Field(default=None, max_length=36)
    # ProseMirror 노드 트리. 모양 검사는 `blocks.normalize` 가 한다 — pydantic 으로
    # 재귀 스키마를 적으면 검사가 두 벌이 되고, 한쪽만 고쳐지는 날이 온다.
    body: dict[str, Any] | None = None
    doc_type: str | None = Field(default=None, max_length=32)
    source_type: str = Field(
        default="USER", pattern="^(" + "|".join(SOURCE_TYPES) + ")$"
    )
    tag_names: list[str] | None = Field(default=None, max_length=20)
    confidential: bool = False


class DocumentSave(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: dict[str, Any] | None = None
    change_reason: str | None = Field(default=None, max_length=500)
    ai_used: bool = False
    tag_names: list[str] | None = Field(default=None, max_length=20)
    base_version: int | None = Field(default=None, ge=1)


class DocumentMove(BaseModel):
    folder_id: str | None = Field(default=None, max_length=36)
    base_version: int | None = Field(default=None, ge=1)


class VersionRestore(BaseModel):
    base_version: int | None = Field(default=None, ge=1)


class DocumentRelationCreate(BaseModel):
    to_document_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(pattern="^(" + "|".join(DREL_KINDS) + ")$")


# ── 댓글 (S14 · C2) ──────────────────────────────────────────────────────────
#
# 상한값의 출처는 `app/knowledge/comments.py::MAX_COMMENT_CHARS` 한 곳이다. 여기서 숫자를
# 다시 정하면 한쪽만 고치는 날 화면이 받아 주는 길이와 서버가 받아 주는 길이가 어긋난다.


def _comment_body(v: str) -> str:
    from app.knowledge.comments import MAX_COMMENT_CHARS

    v = (v or "").strip()
    if not v:
        raise ValueError("댓글 내용을 입력하세요.")
    if len(v) > MAX_COMMENT_CHARS:
        raise ValueError(f"댓글은 {MAX_COMMENT_CHARS}자 이하여야 합니다.")
    return v


class CommentCreate(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def _check(cls, v: str) -> str:
        return _comment_body(v)


class CommentUpdate(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def _check(cls, v: str) -> str:
        return _comment_body(v)
