"""AI 도우미의 도구 등록과 실행 (D-535).

## 등록

도구마다 이름 · 화면 이름(「확인한 내용」) · 진행 문구 · 모델에게 주는 설명 · 인자 모델 · 바깥 스키마 · 권한 문이 있다. 바깥
스키마는 두 제공자의 공용 모양이다(`app/ai/providers/base.py` 의 대화 계약): `type · enum · description · properties ·
required · additionalProperties:false · items` 만 쓰고 모든 속성을 required 로 두며 선택은 `["T", "null"]` 이다. 길이 ·
범위 · 패턴은 서버의 pydantic 인자 모델이 본다(`extra="forbid"` - 모르는 인자는 `invalid_arguments`).

**어떤 도구에도 사용자 · id · 이메일 인자가 없다.** 모델이 다른 사람을 지목할 수 없다.

## 실행

호출 하나마다 새 세션을 열고 `SET TRANSACTION READ ONLY` 와 `statement_timeout` 3초를 건 뒤 대화 주인을 그 세션에서
다시 읽는다(보관 · 비활성이면 `unavailable`). 도구가 쓰려고 하면 DB 가 거절하고 그 도구는 `unavailable` 로 끝난다 -
아무것도 남지 않는다. 끝나면 언제나 되감는다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from app.ai.assistant import readers, results
from app.ai.providers import base

logger = logging.getLogger("app.ai.assistant")

#: 도구 하나의 DB 문 시간 상한(밀리초).
STATEMENT_TIMEOUT_MS = 3000


# ── 인자 모델 ────────────────────────────────────────────────────────────────────────────────────────────────


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ShowArgs(_Args):
    """목록 · 현황 도구의 공통 인자 — 모델이 「사용자에게 보여 줄 목록」을 고른다(결과 블록, `blocks.py`)."""

    show: bool | None = None


#: 목록 도구가 넘길 수 있는 쪽의 상한(offset). 그 뒤는 화면에서 본다.
MAX_LIST_OFFSET = 200

TicketStatus = Literal["계획", "진행", "검증", "완료", "보류", "취소"]
TicketSort = Literal["due", "created", "updated", "completed"]


class DocumentQueryArgs(_ShowArgs):
    query: str = Field(min_length=2, max_length=200)
    project: str | None = Field(default=None, max_length=100)
    mine: bool | None = None
    offset: int | None = Field(default=None, ge=0, le=40)


class MyDocumentsArgs(_ShowArgs):
    view: Literal["authored", "edited"] | None = None
    query: str | None = Field(default=None, max_length=100)
    project: str | None = Field(default=None, max_length=100)
    space: str | None = Field(default=None, max_length=100)
    updated_within_days: int | None = Field(default=None, ge=1, le=365)
    sort: Literal["recent", "created", "title"] | None = None
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class DocumentArgs(_Args):
    ref: str = Field(min_length=1, max_length=200)


class WorkspaceArgs(_Args):
    query: str = Field(min_length=1, max_length=100)
    kinds: list[Literal["ticket", "document", "board"]] | None = Field(default=None, max_length=3)


class MyWorkArgs(_ShowArgs):
    view: Literal["assigned", "requested", "watching", "due_this_week", "overdue"]
    include_done: bool | None = None
    query: str | None = Field(default=None, max_length=100)
    project: str | None = Field(default=None, max_length=100)
    statuses: list[TicketStatus] | None = Field(default=None, max_length=6)
    updated_within_days: int | None = Field(default=None, ge=1, le=365)
    completed: Literal["this_week"] | None = None
    completed_within_days: int | None = Field(default=None, ge=1, le=365)
    sort: TicketSort | None = None
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class TicketArgs(_Args):
    key: str = Field(min_length=1, max_length=64)
    comments_offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class SearchTicketsArgs(_ShowArgs):
    scope: Literal["team", "unassigned"]
    query: str | None = Field(default=None, max_length=100)
    match_body: bool | None = None
    statuses: list[TicketStatus] | None = Field(default=None, max_length=6)
    include_done: bool | None = None
    due: Literal["overdue", "this_week", "next_week"] | None = None
    project: str | None = Field(default=None, max_length=100)
    assignee_name: str | None = Field(default=None, max_length=40)
    created_within_days: int | None = Field(default=None, ge=1, le=365)
    updated_within_days: int | None = Field(default=None, ge=1, le=365)
    completed_within_days: int | None = Field(default=None, ge=1, le=365)
    sort: TicketSort | None = None
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class SearchProjectsArgs(_ShowArgs):
    scope: Literal["mine", "all"]
    query: str | None = Field(default=None, max_length=100)
    status: Literal["planned", "active", "on_hold", "done"] | None = None
    trouble_only: bool | None = None
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class ProjectArgs(_ShowArgs):
    project: str = Field(min_length=1, max_length=100)


class ProjectActivityArgs(_ShowArgs):
    project: str = Field(min_length=1, max_length=100)
    days: int | None = Field(default=None, ge=1, le=180)


class ApprovalsArgs(_ShowArgs):
    box: Literal["todo", "requested", "done"]
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class PeopleArgs(_Args):
    query: str = Field(min_length=1, max_length=40)


class RecentArgs(_Args):
    days: int | None = Field(default=None, ge=1, le=14)
    kinds: list[Literal["documents", "board"]] | None = Field(default=None, max_length=2)


class SummaryArgs(_Args):
    period: Literal["today", "standup", "this_week"]


class NotificationsArgs(_ShowArgs):
    unread_only: bool | None = None
    days: int | None = Field(default=None, ge=1, le=60)
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class ActivityArgs(_ShowArgs):
    days: int | None = Field(default=None, ge=1, le=90)
    kinds: list[Literal["tickets", "documents", "comments"]] | None = Field(default=None, max_length=3)
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


class SprintMeetingArgs(_Args):
    sprint: str | None = Field(default=None, max_length=100)
    team: str | None = Field(default=None, max_length=100)
    offset: int | None = Field(default=None, ge=0, le=MAX_LIST_OFFSET)


# ── 바깥 스키마 조각 ─────────────────────────────────────────────────────────────────────────────────────────


def _text(description: str, *, nullable: bool = False) -> dict:
    return {"type": ["string", "null"] if nullable else "string", "description": description}


def _choice(values, description: str, *, nullable: bool = False) -> dict:
    return {"type": ["string", "null"] if nullable else "string",
            "enum": [*values, None] if nullable else list(values), "description": description}


def _flag(description: str) -> dict:
    return {"type": ["boolean", "null"], "description": description}


def _number(description: str) -> dict:
    return {"type": ["integer", "null"], "description": description}


#: 목록 · 현황 도구의 `show` 설명 — 모델이 보여 줄 목록을 고르고, 그 목록을 답에서 다시 나열하지 않게 한다.
_SHOW_TEXT = ("사용자에게 이 결과를 목록이나 카드로 보여 줄지. 사용자가 목록이나 현황을 보여 달라고 했으면 true 로 둡니다. "
              "화면이 그 목록을 그리므로 답에서 항목을 다시 나열하지 않습니다.")


def _choices(values, description: str) -> dict:
    return {"type": ["array", "null"], "items": {"type": "string", "enum": list(values)}, "description": description}


# ── 등록 ─────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tool:
    name: str
    #: 화면의 「확인한 내용」에 보일 이름(명사구).
    label: str
    #: 도구가 도는 동안 화면에 보일 문장.
    progress: str
    #: 모델에게 주는 설명 - 언제 쓰는가.
    description: str
    args: type[_Args]
    properties: dict
    run: Callable
    #: 이 권한이 없으면 목록에서 뺀다(`app/authz/permissions.py`).
    permission: str | None = None
    #: 이 기능 플래그가 꺼져 있으면 목록에서 뺀다.
    flag: str | None = None
    #: 모든 도구는 읽기 전용이다. 쓰기 도구는 승인 정책과 확인 창을 붙여 따로 설계한다(BACKLOG).
    read_only: bool = True

    def spec(self) -> base.ToolSpec:
        return base.ToolSpec(
            name=self.name, description=self.description,
            parameters={"type": "object", "properties": self.properties, "required": list(self.properties),
                        "additionalProperties": False},
        )


_OFFSET = "몇 번째 항목부터 볼지(0부터 셉니다). 비우면 처음부터 봅니다."
_STATUSES = "볼 상태들. 비우면 끝나지 않은 티켓만 봅니다."
_TICKET_SORT = "정렬. due 는 마감이 이른 순, created 는 최근에 만든 순, updated 는 최근에 바뀐 순, completed 는 최근에 끝낸 순입니다."

REGISTRY: tuple[Tool, ...] = (
    Tool(
        "my_documents", "내 문서", "내 문서를 확인하고 있습니다.",
        "묻는 사람이 만든 사내 문서를 세고 나열합니다. 「내가 작성한 문서」 「내 문서가 몇 개」 같은 질문에 씁니다. "
        "total 이 정확한 건수이고 items 는 한 쪽 분량입니다. 문서 화면의 내 문서와 같은 기준이며, edited 는 묻는 사람이 "
        "고친 적이 있는 문서입니다. query 는 제목과 본문에 그 글자가 그대로 있는 문서만 거릅니다. 주제로 찾을 때는 "
        "search_documents 에 mine 을 켭니다.",
        MyDocumentsArgs, {
            "view": _choice(("authored", "edited"), "authored 는 만든 문서, edited 는 고친 적이 있는 문서입니다. "
                            "비우면 만든 문서입니다.", nullable=True),
            "query": _text("제목이나 본문에서 찾을 글.", nullable=True),
            "project": _text("프로젝트 코드나 이름.", nullable=True),
            "space": _text("문서 공간 이름.", nullable=True),
            "updated_within_days": _number("최근 며칠 안에 바뀐 문서만 볼지(1에서 365)."),
            "sort": _choice(("recent", "created", "title"), "정렬. 비우면 최근에 바뀐 순입니다.", nullable=True),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.my_documents, permission="DOCUMENT_READ",
    ),
    Tool(
        "search_documents", "사내 문서 검색", "사내 문서를 찾고 있습니다.",
        "사내 문서(지식 공간)를 낱말로 찾습니다. 규정, 절차, 안내처럼 문서에 적힌 내용을 묻는 질문에 먼저 씁니다. "
        "질문에서 핵심 낱말만 넘기세요. 결과는 문서 하나에 한 줄이고, total 은 낱말이 하나라도 들어 있는 문서 수, "
        "documents_with_every_word 는 낱말이 모두 들어 있는 문서 수입니다. 묻는 사람이 쓴 문서를 세거나 나열할 때는 "
        "my_documents 를 쓰고, 묻는 사람이 만든 문서에서 주제로 찾을 때는 mine 을 켭니다.",
        DocumentQueryArgs, {
            "query": _text("찾을 낱말. 두 글자 이상입니다."),
            "project": _text("이 프로젝트의 문서로 좁힐 때 프로젝트 코드나 이름.", nullable=True),
            "mine": _flag("묻는 사람이 만든 문서에서만 찾을지."),
            "offset": _number("몇 번째 문서부터 볼지(0에서 40). 비우면 처음부터 봅니다."),
            "show": _flag(_SHOW_TEXT),
        }, readers.search_documents, permission="DOCUMENT_READ",
    ),
    Tool(
        "get_document", "문서 읽기", "문서를 읽고 있습니다.",
        "문서 하나의 본문을 앞에서부터 읽습니다. 작성자, 공간, 프로젝트, 태그, 최근 댓글도 함께 봅니다. "
        "search_documents 나 my_documents 결과의 ref 를 넘깁니다.",
        DocumentArgs, {"ref": _text("search_documents 나 다른 결과가 준 문서 ref.")}, readers.get_document,
        permission="DOCUMENT_READ",
    ),
    Tool(
        "search_workspace", "통합 검색", "티켓과 문서를 함께 찾고 있습니다.",
        "티켓, 문서, 게시글의 제목과 본문을 함께 찾습니다. 무엇이 어디에 있는지 모를 때 씁니다. totals 에 종류별 전체 "
        "수가 있습니다. 문서에 적힌 내용을 물으면 search_documents 를 먼저 씁니다.",
        WorkspaceArgs, {
            "query": _text("찾을 낱말."),
            "kinds": _choices(("ticket", "document", "board"), "찾을 종류. 비우면 셋 다 찾습니다."),
        }, readers.search_workspace,
    ),
    Tool(
        "my_work", "내 업무", "내 업무를 확인하고 있습니다.",
        "묻는 사람 자신의 티켓을 봅니다. assigned 는 맡은 것, requested 는 요청한 것, watching 은 지켜보는 것, "
        "due_this_week 는 이번 주 마감, overdue 는 마감이 지난 것입니다. 「내가 담당하는」 「내 티켓」 같은 질문에 씁니다. "
        "상태, 프로젝트, 검색어로 좁힐 수 있고 total 이 전체 건수입니다. 「이번 주에 끝낸」 「최근 며칠 안에 끝낸」 티켓은 "
        "completed 나 completed_within_days 로 봅니다.",
        MyWorkArgs, {
            "view": _choice(("assigned", "requested", "watching", "due_this_week", "overdue"), "볼 목록."),
            "include_done": _flag("끝난 티켓도 넣을지. 비우면 진행 중인 것만 봅니다."),
            "query": _text("제목이나 티켓 이름에서 찾을 글.", nullable=True),
            "project": _text("프로젝트 코드나 이름.", nullable=True),
            "statuses": _choices(readers.TICKET_STATUSES, _STATUSES),
            "updated_within_days": _number("최근 며칠 안에 바뀐 티켓만 볼지(1에서 365)."),
            "completed": _choice(("this_week",), "this_week 면 이번 주(월요일부터)에 끝낸 티켓만 봅니다. 끝난 티켓도 봅니다.",
                                 nullable=True),
            "completed_within_days": _number("최근 며칠 안에 끝낸 티켓만 볼지(1에서 365). 주면 끝난 티켓도 봅니다."),
            "sort": _choice(readers.TICKET_SORTS, _TICKET_SORT, nullable=True),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.my_work,
    ),
    Tool(
        "get_ticket", "티켓 보기", "티켓을 확인하고 있습니다.",
        "티켓 하나의 상태, 담당자, 마감, 본문 일부, 댓글을 봅니다. ABCDEF-12 같은 키나 결과의 ref 를 넘깁니다. "
        "댓글은 최근 것부터 다섯 개씩 보이고 comments_offset 으로 더 봅니다.",
        TicketArgs, {
            "key": _text("티켓 키(예: ABCDEF-12)나 결과의 ref."),
            "comments_offset": _number("몇 번째 댓글부터 볼지(최근 것이 0입니다). 비우면 최근 다섯 개입니다."),
        }, readers.get_ticket,
    ),
    Tool(
        "search_tickets", "티켓 찾기", "티켓을 찾고 있습니다.",
        "묻는 사람이 볼 수 있는 팀 티켓이나 담당자가 없는 티켓을 조건으로 찾습니다. 상태를 비우면 끝나지 않은 티켓만 보고 "
        "include_done 이면 끝난 것까지 봅니다. 본문까지 찾으려면 match_body 를 켭니다. 자기 티켓은 my_work 를 씁니다.",
        SearchTicketsArgs, {
            "scope": _choice(("team", "unassigned"), "team 은 팀 티켓, unassigned 는 담당자가 없는 티켓입니다."),
            "query": _text("제목이나 키에서 찾을 글.", nullable=True),
            "match_body": _flag("검색어를 티켓 본문에서도 찾을지."),
            "statuses": _choices(readers.TICKET_STATUSES, _STATUSES),
            "include_done": _flag("끝난 티켓도 넣을지. 비우면 진행 중인 것만 봅니다."),
            "due": _choice(("overdue", "this_week", "next_week"), "마감 구간.", nullable=True),
            "project": _text("프로젝트 코드나 이름.", nullable=True),
            "assignee_name": _text("담당자 이름. 팀 티켓에서만 씁니다.", nullable=True),
            "created_within_days": _number("최근 며칠 안에 만든 티켓만 볼지(1에서 365)."),
            "updated_within_days": _number("최근 며칠 안에 바뀐 티켓만 볼지(1에서 365)."),
            "completed_within_days": _number("최근 며칠 안에 끝낸 티켓만 볼지(1에서 365). 주면 끝난 티켓도 봅니다."),
            "sort": _choice(readers.TICKET_SORTS, _TICKET_SORT, nullable=True),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.search_tickets,
    ),
    Tool(
        "search_projects", "프로젝트 찾기", "프로젝트를 찾고 있습니다.",
        "프로젝트를 찾습니다. mine 은 묻는 사람이 구성원이거나 담당인 프로젝트, all 은 볼 수 있는 전체입니다. "
        "한 프로젝트의 진행 현황은 project_activity 를 씁니다.",
        SearchProjectsArgs, {
            "scope": _choice(("mine", "all"), "찾을 범위."),
            "query": _text("이름이나 코드에서 찾을 글.", nullable=True),
            "status": _choice(("planned", "active", "on_hold", "done"), "상태.", nullable=True),
            "trouble_only": _flag("건강도가 낮은 프로젝트만 볼지."),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.search_projects,
    ),
    Tool(
        "get_project_summary", "프로젝트 요약", "프로젝트 진행 상황을 확인하고 있습니다.",
        "프로젝트 하나의 진행률과 그 기준, 건강도와 그 이유를 봅니다. 코드, 이름, 결과의 ref 를 넘깁니다. "
        "이름이 여럿에 걸리면 후보 목록을 돌려주니 사용자에게 고르게 하세요.",
        ProjectArgs, {"project": _text("프로젝트 코드, 이름, 결과의 ref."), "show": _flag(_SHOW_TEXT)},
        readers.get_project_summary,
    ),
    Tool(
        "project_activity", "프로젝트 진행 현황", "프로젝트 진행 기록을 모으고 있습니다.",
        "프로젝트 하나의 진행 현황을 기록으로 봅니다. 상태별 티켓 수, 최근 끝낸 일과 바뀐 일, 마일스톤, 주간 리포트, "
        "연결된 문서를 함께 돌려줍니다. 이름이 여럿에 걸리면 후보 목록을 돌려주니 사용자에게 고르게 하세요.",
        ProjectActivityArgs, {
            "project": _text("프로젝트 코드, 이름, 결과의 ref."),
            "days": _number("최근 며칠의 기록을 볼지(1에서 180). 비우면 30일입니다."),
            "show": _flag(_SHOW_TEXT),
        }, readers.project_activity,
    ),
    Tool(
        "my_approvals", "내 결재함", "결재함을 확인하고 있습니다.",
        "묻는 사람의 결재함을 봅니다. todo 는 지금 결재할 것, requested 는 올린 것, done 은 결재한 것입니다.",
        ApprovalsArgs, {
            "box": _choice(("todo", "requested", "done"), "볼 칸."),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.my_approvals,
    ),
    Tool(
        "my_notifications", "내 알림", "알림을 확인하고 있습니다.",
        "묻는 사람이 받은 알림을 최근 것부터 봅니다. unread_total 이 안 읽은 알림 수이고 total 은 조건에 맞는 "
        "전체 수입니다.",
        NotificationsArgs, {
            "unread_only": _flag("안 읽은 알림만 볼지."),
            "days": _number("최근 며칠의 알림을 볼지(1에서 60). 비우면 기간 제한이 없습니다."),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.my_notifications,
    ),
    Tool(
        "my_activity", "내 최근 활동", "최근 활동을 모으고 있습니다.",
        "묻는 사람이 최근에 한 일을 시간 순으로 봅니다. 티켓에서 바꾼 것, 문서에 남긴 판, 단 댓글을 함께 돌려줍니다. "
        "「내가 최근에 한 일」 같은 질문에 씁니다.",
        ActivityArgs, {
            "days": _number("최근 며칠을 볼지(1에서 90). 비우면 14일입니다."),
            "kinds": _choices(("tickets", "documents", "comments"), "볼 종류. 비우면 셋 다 봅니다."),
            "offset": _number(_OFFSET),
            "show": _flag(_SHOW_TEXT),
        }, readers.my_activity,
    ),
    Tool(
        "sprint_meetings", "스프린트 회의록", "회의록을 확인하고 있습니다.",
        "스프린트 회차의 회의에서 정한 것과 할 일을 봅니다. 회차 이름을 비우면 묻는 사람 팀의 진행 중인 회차를 봅니다.",
        SprintMeetingArgs, {
            "sprint": _text("회차 이름.", nullable=True),
            "team": _text("팀 이름.", nullable=True),
            "offset": _number(_OFFSET),
        }, readers.sprint_meetings,
    ),
    Tool(
        "find_people", "사람 찾기", "사람을 찾고 있습니다.",
        "같은 조직의 사람을 이름이나 부서 이름으로 찾습니다. 이름, 부서, 직책만 돌려줍니다.",
        PeopleArgs, {"query": _text("이름이나 부서 이름.")}, readers.find_people, flag="team_chat_enabled",
    ),
    Tool(
        "recent_changes", "최근 바뀐 자료", "최근 바뀐 자료를 확인하고 있습니다.",
        "최근 바뀐 문서와 새 게시글을 봅니다.",
        RecentArgs, {
            "days": _number("며칠 전부터 볼지(1에서 14). 비우면 7일입니다."),
            "kinds": _choices(("documents", "board"), "볼 종류. 비우면 둘 다 봅니다."),
        }, readers.recent_changes,
    ),
    Tool(
        "work_summary", "업무 요약", "업무 현황을 모으고 있습니다.",
        "묻는 사람의 업무 현황을 모읍니다. today 는 오늘, standup 은 스탠드업(최근 끝낸 것, 오늘 할 것, 막힌 것), "
        "this_week 는 이번 주 스프린트 창의 요약입니다. 그 요약의 완료 수는 이번 주가 마감인 일 중 끝낸 것이라, 이번 주에 "
        "끝낸 티켓의 수와 목록은 my_work 의 completed 로 봅니다.",
        SummaryArgs, {"period": _choice(("today", "standup", "this_week"), "모을 기간.")}, readers.work_summary,
    ),
)

TOOLS: dict[str, Tool] = {tool.name: tool for tool in REGISTRY}


def available_tools(*, can: Callable[[str], bool], flag: Callable[[str], bool]) -> tuple[Tool, ...]:
    """대화 주인이 지금 쓸 수 있는 도구. 권한과 기능 플래그로 거른다 - 제공자 요청의 `tools` 가 이것이다."""
    out = []
    for tool in REGISTRY:
        if tool.permission and not can(tool.permission):
            continue
        if tool.flag and not flag(tool.flag):
            continue
        out.append(tool)
    return tuple(out)


# ── 실행 ─────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolEnv:
    """도구 실행에 필요한 바깥 것. DB 세션은 호출마다 새로 연다."""

    session_factory: Callable
    user_id: str
    settings: object
    outbound: object
    gateway: object | None
    settings_cache: object | None
    now: datetime

    def flag(self, key: str) -> bool:
        """기능 플래그의 지금 값(정본이 DB 든 파일이든, `app/core/feature_flags.py::flag_value`)."""
        from app.core.feature_flags import flag_value

        return flag_value(key, settings_cache=self.settings_cache, config_dir=self.settings.config_dir)


@contextmanager
def read_only_session(session_factory, *, statement_timeout_ms: int = STATEMENT_TIMEOUT_MS):
    """READ ONLY 트랜잭션 하나. 끝나면 언제나 되감는다."""
    db = session_factory()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}"))
        yield db
    finally:
        try:
            db.rollback()
        finally:
            db.close()


def _context(db, env: ToolEnv):
    """대화 주인을 이 세션에서 다시 읽는다. 보관 · 비활성이면 None."""
    from app.authz.service import has_permission
    from app.core.scope import principal_from_user
    from app.users.models import User

    user = db.get(User, env.user_id)
    if user is None or not user.active or user.archived_at is not None:
        return None
    return readers.ToolContext(
        db=db, user=user, principal=principal_from_user(db, user), settings=env.settings, outbound=env.outbound,
        gateway=env.gateway, flag=env.flag, can=lambda key: has_permission(db, user, key), now=env.now,
    )


def run(tool: Tool, args: _Args, env: ToolEnv) -> results.Execution:
    """검증한 인자로 도구 하나를 READ ONLY 트랜잭션에서 돌린다. 예외를 올리지 않는다."""
    from app.core.errors import NotFoundError, TicketNotFoundError, ValidationAppError

    try:
        with read_only_session(env.session_factory) as db:
            ctx = _context(db, env)
            if ctx is None:
                return results.error(tool.name, results.ERROR_UNAVAILABLE)
            try:
                found = tool.run(ctx, args)
            except (NotFoundError, TicketNotFoundError):
                return results.error(tool.name, results.ERROR_NOT_FOUND)
            except ValidationAppError:
                return results.error(tool.name, results.ERROR_INVALID_ARGUMENTS)
            return found if isinstance(found, results.Execution) else results.error(tool.name,
                                                                                   results.ERROR_UNAVAILABLE)
    except Exception:  # noqa: BLE001 - 도구 하나가 터져도(쓰기 시도, 시간 초과 포함) 차례는 이어진다
        logger.exception("도우미 도구 %s 가 실패했다", tool.name)
        return results.error(tool.name, results.ERROR_UNAVAILABLE)


def execute(call: base.ToolCall, *, allowed: dict[str, Tool], env: ToolEnv,
            progress: Callable[[str], None] | None = None) -> results.Execution:
    """모델이 부른 도구 하나. 등록에 없거나 이 사람에게 허락되지 않은 이름, 읽지 못한 인자는 실행하지 않는다."""
    name = call.name if isinstance(call.name, str) and call.name else "unknown"
    tool = allowed.get(name)
    if tool is None:
        return results.error(name, results.ERROR_UNAVAILABLE, "쓸 수 없는 도구입니다.")
    if call.arguments is None:
        return results.error(tool.name, results.ERROR_INVALID_ARGUMENTS)
    try:
        args = tool.args.model_validate(call.arguments)
    except ValidationError:
        return results.error(tool.name, results.ERROR_INVALID_ARGUMENTS)
    if progress is not None:
        progress(tool.progress)
    from dataclasses import replace

    return replace(run(tool, args, env), args=args.model_dump(exclude_none=True))


def fallback_search(question: str, *, allowed: dict[str, Tool], env: ToolEnv) -> results.Execution | None:
    """대체 모드(도구를 거절하는 제공자): 서버가 문서 검색과 통합 검색을 먼저 돌려 한 묶음으로 준다."""
    found: dict[str, dict] = {}
    sources: list = []
    queries: list[str] = []
    plan = (
        ("search_documents", DocumentQueryArgs, {"query": question[:200]}),
        ("search_workspace", WorkspaceArgs, {"query": question[:100]}),
    )
    for name, model, raw in plan:
        tool = allowed.get(name)
        if tool is None:
            continue
        try:
            args = model.model_validate(raw)
        except ValidationError:
            continue
        execution = run(tool, args, env)
        found[name] = json.loads(execution.content)
        sources.extend(execution.sources)
        if execution.query:
            queries.append(execution.query)
    if not found:
        return None
    return results.Execution(tool="search", content=json.dumps(found, ensure_ascii=False, default=str), ok=True,
                             count=sum(len(v.get("items") or []) for v in found.values()),
                             query=queries[0] if queries else None, sources=tuple(sources))
