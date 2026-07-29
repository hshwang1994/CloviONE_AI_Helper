"""사용자 셀프서비스 티켓 편집 요청 스키마.

PATCH 의미: **보낸 필드만** 바꾼다(model_dump(exclude_unset=True)). 필드를 null/""/[] 로 명시하면
'지움'(마감·난이도·우선순위·담당자)을 뜻한다. 진행상태는 비울 수 없다(서비스에서 거절).
담당자는 내부 user_id 로만 받는다 — 브라우저는 Notion user id 를 절대 주지 않는다(스펙 §12.3).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TicketUpdate(BaseModel):
    # 계약에 없는 키는 거절한다 — 프런트 오타/오용이 조용히 무시되지 않게(fail fast).
    model_config = ConfigDict(extra="forbid")

    assignee_user_ids: list[str] | None = None
    est_wd: float | None = None
    difficulty: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: str | None = None

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
