"""사용자 셀프서비스 티켓 편집 요청 스키마.

PATCH 의미: **보낸 필드만** 바꾼다(model_dump(exclude_unset=True)). 필드를 null/""/[] 로 명시하면
'지움'(마감·난이도·우선순위·담당자)을 뜻한다. 진행상태는 비울 수 없다(서비스에서 거절).
담당자는 내부 user_id 로만 받는다 — 브라우저는 Notion user id 를 절대 주지 않는다(스펙 §12.3).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.notion_blocks import MAX_BLOCKS as BODY_MAX_LINES
from app.core.notion_blocks import MAX_LINE_CHARS as BODY_MAX_LINE_CHARS
from app.tickets.comments import MAX_COMMENT_CHARS

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BulkPageIds(BaseModel):
    """일괄 삭제(휴지통 이동) 요청 — Notion page id 목록. 티켓·문서 공용."""

    model_config = ConfigDict(extra="forbid")
    page_ids: list[str]

    @field_validator("page_ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for x in v or []:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        if not out:
            raise ValueError("삭제할 항목을 선택하세요.")
        return out[:100]  # 한 번에 최대 100건


class TicketBodyUpdate(BaseModel):
    """티켓 본문(마크다운 정본) 저장.

    상한을 **거절**로 두고 잘라내지 않는 이유: 우리 DB에는 다 들어가는데 Notion 에는 앞
    100줄만 올라가면 두 곳이 조용히 달라진다. 사용자에게 어긋난 이유를 말하지 않고 어긋나게
    두느니, 저장을 거절하고 무엇을 줄여야 하는지 알려주는 편이 낫다.
    (상한값은 app/core/notion_blocks.py 의 MAX_BLOCKS / MAX_LINE_CHARS 와 같은 값이다.)
    """

    model_config = ConfigDict(extra="forbid")

    body_markdown: str

    @field_validator("body_markdown")
    @classmethod
    def _check_body(cls, v: str) -> str:
        v = (v or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = v.split("\n")
        if len(lines) > BODY_MAX_LINES:
            raise ValueError(
                f"본문은 최대 {BODY_MAX_LINES}줄까지 저장할 수 있습니다"
                f"(현재 {len(lines)}줄). 줄 수를 줄이거나 원본에서 편집해 주세요."
            )
        if any(len(ln) > BODY_MAX_LINE_CHARS for ln in lines):
            raise ValueError(f"한 줄은 {BODY_MAX_LINE_CHARS}자 이하여야 합니다.")
        return v


class TicketCommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body")
    @classmethod
    def _check(cls, v: str) -> str:
        return _comment_body(v)


class TicketCommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body")
    @classmethod
    def _check(cls, v: str) -> str:
        return _comment_body(v)


def _comment_body(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("댓글 내용을 입력하세요.")
    if len(v) > MAX_COMMENT_CHARS:
        raise ValueError(f"댓글은 {MAX_COMMENT_CHARS}자 이하여야 합니다.")
    return v


class TicketUpdate(BaseModel):
    """티켓 속성 수정.

    **작업 DB 의 편집 가능한 속성을 전부 받는다**(2026-08-04 제품화 지시 — "티켓 수정, 본문
    수정 등 모두 이 포털에서 제공돼야 함"). 예전에는 제목·프로젝트·실제 WD·시작일·대분류가
    빠져 있어서, 그중 하나만 고치려 해도 노션을 열어야 했다.

    아직 여기 없는 것은 관계형 속성 넷(상위/하위 작업, 선행/후속 작업)뿐이다. 티켓 1,000건을
    검색해 고르는 별도 UI 가 필요해 이번 범위 밖이고, 실제 사용률도 8%/1%/1%/1% 다.
    """

    # 계약에 없는 키는 거절한다 — 프런트 오타/오용이 조용히 무시되지 않게(fail fast).
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    assignee_user_ids: list[str] | None = None
    project_id: str | None = None
    est_wd: float | None = None
    act_wd: float | None = None
    difficulty: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: str | None = None
    start_date: str | None = None
    category: str | None = None

    @field_validator("title")
    @classmethod
    def _check_title_u(cls, v):
        if v is None:
            return None
        v = v.strip()
        # 제목을 비우면 목록에서 그 티켓이 '(제목 없음)'이 된다 — 실수로 지운 것이지 뜻이 아니다.
        if not v:
            raise ValueError("제목은 비울 수 없습니다.")
        if len(v) > 200:
            raise ValueError("제목은 200자 이하여야 합니다.")
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v):
        if v is None:
            return None
        v = v.strip()
        if len(v) > 200:
            raise ValueError("대분류는 200자 이하여야 합니다.")
        return v   # 빈 문자열 = 지움

    @field_validator("start_date")
    @classmethod
    def _check_start(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not v:
            return ""  # 빈 문자열 = 시작일 지움
        if not _DATE_RE.match(v):
            raise ValueError("시작일은 YYYY-MM-DD 형식이어야 합니다.")
        return v

    @field_validator("act_wd")
    @classmethod
    def _check_act_wd(cls, v):
        if v is None:
            return v
        if v < 0 or v > 1000:
            raise ValueError("실제 WD는 0 이상 1000 이하여야 합니다.")
        return v

    @field_validator("est_wd")
    @classmethod
    def _check_wd(cls, v):
        if v is None:
            return v
        if v < 0 or v > 1000:
            raise ValueError("예상 WD는 0 이상 1000 이하여야 합니다.")
        return v

    @field_validator("due_date")
    @classmethod
    def _check_due(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not v:
            return ""  # 빈 문자열 = 마감일 지움(서비스가 date:null 로 반영)
        if not _DATE_RE.match(v):
            raise ValueError("마감일은 YYYY-MM-DD 형식이어야 합니다.")
        return v

    @field_validator("assignee_user_ids")
    @classmethod
    def _check_assignees(cls, v):
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("담당자는 최대 20명까지 지정할 수 있습니다.")
        return [s for s in v if isinstance(s, str) and s.strip()]


class TicketCreate(BaseModel):
    """새 티켓 수동 생성(채팅 없이 폼으로). 제목은 필수, 나머지는 선택. 담당자는 user_id 로만."""

    model_config = ConfigDict(extra="forbid")

    title: str
    project_id: str | None = None
    status: str | None = None
    priority: str | None = None
    difficulty: str | None = None
    est_wd: float | None = None
    due_date: str | None = None
    assignee_user_ids: list[str] | None = None
    description: str | None = None

    @field_validator("title")
    @classmethod
    def _check_title(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("제목을 입력하세요.")
        if len(v) > 200:
            raise ValueError("제목은 200자 이하여야 합니다.")
        return v

    @field_validator("description")
    @classmethod
    def _check_desc(cls, v):
        if v is None:
            return None
        v = v.strip()
        if len(v) > 4000:
            raise ValueError("설명은 4000자 이하여야 합니다.")
        return v or None

    @field_validator("est_wd")
    @classmethod
    def _check_wd_c(cls, v):
        if v is None:
            return v
        if v < 0 or v > 1000:
            raise ValueError("예상 WD는 0 이상 1000 이하여야 합니다.")
        return v

    @field_validator("due_date")
    @classmethod
    def _check_due_c(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not _DATE_RE.match(v):
            raise ValueError("마감일은 YYYY-MM-DD 형식이어야 합니다.")
        return v

    @field_validator("assignee_user_ids")
    @classmethod
    def _check_assignees_c(cls, v):
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("담당자는 최대 20명까지 지정할 수 있습니다.")
        return [s for s in v if isinstance(s, str) and s.strip()]
