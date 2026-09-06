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
    """부분 수정. `None` 은 「안 보냈다」가 아니라 **「null 을 보냈다」일 수도 있다.**

    라우터가 `model_dump(exclude_unset=True)` 로 그 둘을 가르고, 「비울 수 없는 칸에 온
    null」은 서비스가 422 로 거절한다(`service._REQUIRED_SPACE_FIELDS`). 여기서 타입을
    `str`(필수)로 좁히지 못하는 이유가 그것이다 — 그러면 「안 보냈다」를 표현할 길이 없다.

    그래서 **비울 수 있는 칸과 없는 칸이 이 스키마의 모양으로는 구별되지 않는다.** 갈라
    적어 둔다: `owner_dept_id`·`owner_project_id` 는 null 이 「소유 대상을 뗀다」는 뜻이고,
    `name`·`description`·`confidential`·`archived`·`owner_kind` 는 null 이 거절이다.
    소유를 없앤다는 뜻은 `owner_kind: "unset"` 이라는 값으로 말한다.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    # 값 목록에 `unset` 이 들어 있다 — 「소유 없음」은 null 이 아니라 이 값이다.
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
    # 화면은 보통 `project_id` 만 안다(§14.4) — "공간"은 관리 화면에서만 쓰는 말이다.
    # 서비스 계층이 "둘 중 하나는 있어야 한다"를 검사한다(`ValidationAppError`).
    space_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)
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
    category_id: str | None = Field(default=None, max_length=36)
    confidential: bool = False
    # 시작할 틀 (지시 22.5). 본문을 직접 보내면 그쪽이 이긴다 — 「제안을 문서로」처럼
    # 이미 내용을 들고 오는 경로가 틀 때문에 그 내용을 잃으면 안 된다.
    #
    # 값 목록을 여기 문자열로 다시 적지 않는다. 틀 하나를 없앤 날 스키마만 옛 이름을
    # 받아 주면, 서버는 200 을 내면서 빈 문서를 만든다.
    #
    # 🔴 상한이 32 였다. 틀이 표가 되면서 id 가 **36자 UUID** 가 됐고, 그대로 두면 화면이
    # 고른 틀이 전부 422 로 거절된다 — 그런데 거절되는 것은 문서 생성 자체라 사용자는
    # 자기가 쓴 제목까지 잃는다. 「빈 문서」(`blank`)만 상수라 짧다.
    template: str | None = Field(default=None, max_length=64)


class DocumentSave(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: dict[str, Any] | None = None
    change_reason: str | None = Field(default=None, max_length=500)
    ai_used: bool = False
    tag_names: list[str] | None = Field(default=None, max_length=20)
    # `None` 이 두 뜻을 갖는 필드다 — 「안 보냈다」와 「분류를 해제한다」. 라우터가
    # `model_fields_set` 으로 가른다(`FolderUpdate.reparent` 가 같은 문제를 푸는 자리).
    # 안 가르면 카테고리를 모르는 호출자가 저장할 때마다 분류가 조용히 지워진다.
    category_id: str | None = Field(default=None, max_length=36)
    base_version: int | None = Field(default=None, ge=1)


class DocumentMove(BaseModel):
    folder_id: str | None = Field(default=None, max_length=36)
    # 오면 소속(공간) 이동으로 해석한다(§11.4·§14.4) — 그 프로젝트의 공간을 찾거나 만든다.
    project_id: str | None = Field(default=None, max_length=36)
    base_version: int | None = Field(default=None, ge=1)


class VersionRestore(BaseModel):
    base_version: int | None = Field(default=None, ge=1)


class TagCreate(BaseModel):
    """태그 추가와 이름 고치기가 같은 모양을 쓴다 — 둘 다 받는 것이 이름 하나뿐이다.

    상한은 `app/knowledge/tags.py::TAG_NAME_MAX` 와 같은 값이어야 한다. 여기서 숫자를 다시
    정하면 한쪽만 고치는 날 화면이 받아 주는 길이와 서버가 받아 주는 길이가 어긋난다.
    """

    name: str = Field(min_length=1, max_length=80)


class TemplateCreate(BaseModel):
    """새 문서가 시작할 틀.

    `body` 는 검사하지 않고 받는다 — 모양 판정은 `app/knowledge/blocks.py::normalize`
    한 곳이다(문서 본문과 같은 함수). pydantic 에 두 번째 판정을 두면 두 벌이 되고,
    갈라지는 날 「저장은 됐는데 열면 빈 화면」이 된다(`DocumentCreate.body` 와 같은 근거).

    상한은 `app/knowledge/templates.py` 의 `TEMPLATE_NAME_MAX`·`TEMPLATE_HELP_MAX` 와
    같은 값이어야 한다.
    """

    name: str = Field(min_length=1, max_length=80)
    help: str = Field(default="", max_length=500)
    body: dict[str, Any] | None = None


class TemplateUpdate(BaseModel):
    """부분 수정. **안 보낸 칸은 안 건드린다** — `model_fields_set` 으로 가른다.

    `help` 의 `None` 과 「안 보냈다」가 다른 뜻이라(전자는 「설명을 지운다」) 라우터가
    보낸 칸 목록을 본다. `DocumentSave.category_id` 가 쓰는 규약과 같다.
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    help: str = Field(default="", max_length=500)
    body: dict[str, Any] | None = None


class CategoryCreate(BaseModel):
    """카테고리 추가와 이름 고치기가 같은 모양을 쓴다 — `TagCreate` 와 같은 근거.

    상한은 `app/knowledge/categories.py::CATEGORY_NAME_MAX` 와 같은 값이어야 한다.
    """

    name: str = Field(min_length=1, max_length=80)


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
