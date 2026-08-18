"""사용자 셀프서비스 티켓 편집 요청 스키마.

PATCH 의미: **보낸 필드만** 바꾼다(model_dump(exclude_unset=True)). 필드를 null/""/[] 로 명시하면
'지움'(마감·난이도·우선순위·담당자)을 뜻한다. 진행상태는 비울 수 없다(서비스에서 거절).
담당자는 내부 user_id 로만 받는다 — 브라우저는 Notion user id 를 절대 주지 않는다(스펙 §12.3).
"""

from __future__ import annotations

import re

from fastapi import Query
from pydantic import BaseModel, ConfigDict, field_validator, Field

from app.core.notion_blocks import MAX_BLOCKS as BODY_MAX_LINES
from app.core.notion_blocks import MAX_LINE_CHARS as BODY_MAX_LINE_CHARS
from app.tickets.comments import MAX_COMMENT_CHARS
from app.tickets.repository import DUE_BUCKETS

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 기한 버킷 쿼리값 검증용. 값 자체는 도메인(repository.DUE_BUCKETS)이 정한다 — 여기서 다시
# 적으면 한쪽만 늘어나고, 그때 증상은 "이 버튼만 422" 라서 원인이 안 보인다.
_DUE_PATTERN = "^(" + "|".join(DUE_BUCKETS) + ")$"


def _clean(value: str | None) -> str | None:
    """빈 문자열은 '조건 없음'이다. 프런트가 select 를 비우면 `?status=` 로 오기 때문에,
    그것을 '상태가 빈 문자열인 티켓' 으로 읽으면 목록이 통째로 빈다."""
    if value is None:
        return None
    value = value.strip()
    return value or None


class TicketListQuery:
    """티켓 목록 서버 필터 (FastAPI 의존성).

    `app/core/pagination.py::PageParams` 와 **같은 관용**이다: pydantic 모델이 아니라 Query
    기본값을 가진 평범한 클래스라 `Depends()` 하나로 붙고, 라우터 시그니처가 짧게 남는다.

    담당자는 **앱 user_id 로만** 받는다(§12.3). 브라우저는 소스(Notion) user id 를 주지도
    받지도 않으므로, 해석은 서비스가 한 번만 한다(`service._notion_id_for_user`).

    `due` 는 정해진 세 값만 받는다 — 모르는 값을 조용히 무시하면 "기한 필터를 눌렀는데
    전체가 나온다" 가 되고, 그건 사용자가 필터가 안 걸렸다는 사실을 알아챌 수 없는 모양이다.
    """

    def __init__(
        self,
        status: str | None = Query(default=None, max_length=64),
        priority: str | None = Query(default=None, max_length=64),
        difficulty: str | None = Query(default=None, max_length=64),
        project_id: str | None = Query(default=None, max_length=64),
        assignee_user_id: str | None = Query(default=None, max_length=36),
        category: str | None = Query(default=None, max_length=200),
        due: str | None = Query(default=None, pattern=_DUE_PATTERN),
        q: str | None = Query(default=None, max_length=100),
    ) -> None:
        self.status = _clean(status)
        self.priority = _clean(priority)
        self.difficulty = _clean(difficulty)
        self.project_id = _clean(project_id)
        self.assignee_user_id = _clean(assignee_user_id)
        self.category = _clean(category)
        self.due = _clean(due)
        self.q = _clean(q)


def _ensure_real_date(value: str, label: str) -> str:
    """모양뿐 아니라 **실제로 있는 날짜인지** 본다 (Z12).

    정규식만으로는 `2026-02-31` 이 통과한다. 그리고 `due_date` 는 문자열로 저장돼
    **사전순으로 비교**되므로(`repository_notion`) 잘못된 값 하나가 모든 기간 필터와 공수
    집계를 조용히 왜곡한다. 더 나쁜 것은 번다운이 `ValueError` 를 잡아 `[]` 를 돌려주는
    바람에 **HTTP 200 에 합계는 채워지고 그래프만 빈** 화면이 나온다는 점이다 —
    숫자와 그래프가 서로 다른 말을 하는데 이유를 안 알려 준다.

    (참고: `est_wd`/`act_wd` 는 0~1000 으로 제대로 막혀 있었다 — **숫자에는 물어본 질문을
    날짜에는 안 물었다.**)
    """
    from datetime import date as _date

    if not _DATE_RE.match(value):
        raise ValueError(f"{label}은 YYYY-MM-DD 형식이어야 합니다.")
    try:
        _date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label}에 없는 날짜입니다: {value}") from None
    return value


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
    # 낙관적 잠금 (Z2). 편집을 시작할 때 받은 본문의 지문을 그대로 돌려보낸다.
    # **선택 사항**이다 — 안 보내면 예전처럼 그냥 덮어쓴다(기존 클라이언트·CLI 호환).
    # 보내면 그 사이 누가 먼저 저장한 경우 409 로 막는다.
    base_version: str | None = Field(default=None, max_length=64)

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
        return _ensure_real_date(v, "시작일")

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
        return _ensure_real_date(v, "마감일")

    @field_validator("assignee_user_ids")
    @classmethod
    def _check_assignees(cls, v):
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("담당자는 최대 20명까지 지정할 수 있습니다.")
        return [s for s in v if isinstance(s, str) and s.strip()]


class TicketCreate(BaseModel):
    """새 티켓 수동 생성(채팅 없이 폼으로). 제목과 **프로젝트**가 필수, 나머지는 선택.

    ## 프로젝트가 필수인 이유 (0060)

    티켓의 조직 소속은 프로젝트가 정한다(`app/core/ownership.py`). 프로젝트 없는 티켓은
    **어느 범위에도 안 잡히는 유령**이 되어 전역 관리자 말고는 아무도 못 보고, 그 상태는
    화면상 "목록이 비었다" 로만 보여 원인을 찾을 수 없다. 그래서 만들 때 막는다.

    `project_id` 는 **Portal 프로젝트 id** 다(외부 소스의 relation id 가 아니다). 외부
    id 로의 번역은 서버가 한다 — 브라우저가 외부 시스템의 키를 알 이유가 없고, Portal id 로
    받아야 그 프로젝트에 대한 권한을 검증할 수 있다.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    project_id: str = Field(min_length=1)
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

    @field_validator("project_id")
    @classmethod
    def _check_project(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("프로젝트를 선택하세요.")
        return v

    @field_validator("description")
    @classmethod
    def _check_desc(cls, v):
        if v is None:
            return None
        v = v.strip()
        if len(v) > 4000:
            raise ValueError("설명은 4000자 이하여야 합니다.")
        if not v:
            return None
        # 이 설명은 그대로 노션 블록으로 변환된다(service.create_ticket → markdown_to_blocks).
        # 그 변환기는 100줄/줄당 1900자를 넘으면 **조용히 잘라낸다** — 총 글자 수(4000자)만
        # 봐서는 이 함정을 못 막는다(짧은 줄 150개는 4000자 밑이어도 뒤 50줄이 사라진다).
        # 본문 수정(TicketBodyUpdate._check_body)과 같은 규칙으로 여기서도 자르지 않고 거절한다.
        lines = v.split("\n")
        if len(lines) > BODY_MAX_LINES:
            raise ValueError(
                f"설명은 최대 {BODY_MAX_LINES}줄까지 저장할 수 있습니다"
                f"(현재 {len(lines)}줄). 줄 수를 줄여 주세요."
            )
        if any(len(ln) > BODY_MAX_LINE_CHARS for ln in lines):
            raise ValueError(f"설명의 한 줄은 {BODY_MAX_LINE_CHARS}자 이하여야 합니다.")
        return v

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
        return _ensure_real_date(v, "마감일")

    @field_validator("assignee_user_ids")
    @classmethod
    def _check_assignees_c(cls, v):
        if v is None:
            return None
        if len(v) > 20:
            raise ValueError("담당자는 최대 20명까지 지정할 수 있습니다.")
        return [s for s in v if isinstance(s, str) and s.strip()]
