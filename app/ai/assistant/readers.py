"""AI 도우미 도구 열일곱 개의 읽기 — 화면이 쓰는 권한 범위 함수를 그대로 부른다 (D-535 · D-567).

규칙은 다섯이다.

  * 대화 주인(`ctx.user`)의 권한으로만 읽는다. 사람 · id · 이메일을 인자로 받는 도구는 없다 - 모델이 다른 사람을
    지목할 수 없다. 「내 문서」 · 「내 알림」 · 「내 활동」의 「나」는 서버가 정한다(`ctx.user`)
  * 범위 밖 대상은 없는 대상과 **같은** `not_found` 다(같은 문장). 존재를 흘리지 않는다
  * 결과에 이메일 · 역할 · 내부 사용자 id 를 싣지 않는다. 사람은 이름(과 부서 · 직책)으로만 나간다
  * 경로는 서버가 만든다 - 화면이 쓰는 경로와 같은 모양이다(`/tickets/…` · `/knowledge/…` · `/projects/…` ·
    `/my-approvals?id=…` · `/board/…` · `/sprint?team=…&sprint=…`)
  * 목록의 `total` 은 권한 안의 **정확한 전체 수**이고 `items` 는 그중 한 쪽(`offset` 부터)이다(`results.py` 의 세기 계약).
    모델은 개수를 물으면 `total` 을 말한다(`app/llm/prompt.py::ASSISTANT_COUNT_RULE`)

함수는 모두 `(ctx, args) -> results.Execution` 이다. 트랜잭션은 부른 쪽(`catalog.execute`)이 READ ONLY 로 연다 - 여기서
쓰기를 하면 그 도구는 `unavailable` 로 끝나고 아무것도 남지 않는다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.ai.assistant import results

#: 결과 하나에 싣는 글자 상한(런타임의 칸 상한 8천 자 안).
DOC_EXCERPT_CHARS = 900
DOC_TEXT_CHARS = 6000
TICKET_BODY_CHARS = 1500
COMMENT_CHARS = 300
LIST_LIMIT = 10
#: 목록 한 줄의 미리보기 글자 수(내 문서 · 프로젝트 문서).
LIST_EXCERPT_CHARS = 240
#: 문서 검색 한 쪽의 문서 수.
SEARCH_TOP_K = 8
#: 결과 한 칸의 글자 예산 — 런타임의 칸 상한(`app/ai/runtime.py::TOOL_RESULT_CHARS`, 8천 자)보다 작게 둔다. 넘으면 런타임이 JSON 을
#: 중간에서 자르고, 모델은 깨진 결과를 읽는다. 문서 검색은 이 안에 들도록 발췌를 줄인다(`_fit_texts`).
RESULT_BUDGET_CHARS = 7200
#: 티켓 댓글 한 쪽.
COMMENT_PAGE = 5
#: 알림 본문 · 회의 결정 · 주간 리포트의 글자 상한.
NOTIFICATION_BODY_CHARS = 200
DECISION_BODY_CHARS = 300
DECISIONS_LIMIT = 20
REPORT_CHARS = 1200
#: 프로젝트 진행 현황에 싣는 줄 수.
ACTIVITY_ROWS = 8
PROJECT_DOCUMENTS = 6

#: 티켓 상태 낱말(`app/work/workflow.py`). 도구 스키마의 선택지와 같다.
TICKET_STATUSES = ("계획", "진행", "검증", "완료", "보류", "취소")
TERMINAL_STATUSES = frozenset({"완료", "취소"})
PROJECT_STATUS_KO = {"planned": "계획", "active": "진행", "on_hold": "보류", "done": "완료"}
PROJECT_ROLE_KO = {"owner": "담당", "member": "구성원", "viewer": "보기 전용"}
MILESTONE_STATUS_KO = {"planned": "계획", "done": "완료", "missed": "놓침"}
DECISION_KIND_KO = {"decision": "결정", "action": "할 일"}

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class ToolContext:
    """도구 한 번이 받는 것. ``db`` 는 READ ONLY 트랜잭션의 세션이고 ``user`` 는 그 세션에서 다시 읽은 대화 주인이다."""

    db: Session
    user: object
    principal: object
    settings: object
    outbound: object
    gateway: object | None
    #: DB 소유 기능 플래그의 지금 값(`app/core/feature_flags.py::db_flag`).
    flag: Callable[[str], bool]
    #: 권한 키를 가졌는가(`app/authz/service.py::has_permission`).
    can: Callable[[str], bool]
    #: naive UTC(서버 시계).
    now: datetime

    @property
    def today(self) -> date:
        """KST 달력일(불변 §9). 마감 구간은 이 날로 잰다."""
        from app.home import service as home_service

        return home_service.local_today(self.settings, self.now)

    def day_now(self) -> datetime:
        """`build_filters` 가 `now.date()` 로 오늘을 읽으므로 KST 날짜의 자정을 준다."""
        return datetime.combine(self.today, time())


# ── 모양 ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _mask_emails(text: str | None) -> str | None:
    """사람이 쓴 글(알림 제목 · 본문)에 섞인 이메일 주소를 가린다 — 결과에는 이메일이 실리지 않는다."""
    if not text:
        return text
    return _EMAIL.sub("(이메일 가림)", text)


def _offset(args) -> int:
    return max(0, int(getattr(args, "offset", None) or 0))


def _since(ctx: ToolContext, days: int | None) -> datetime | None:
    """「최근 N일」의 시작 — naive UTC 순간(저장 축과 같다)."""
    return ctx.now - timedelta(days=int(days)) if days else None


def _completed_from(ctx: ToolContext, completed: str | None, days: int | None) -> datetime | None:
    """「끝낸 날」 조건의 시작 — naive UTC 순간. `this_week` 는 이번 주 월요일 0시(KST 달력, 마감의 「이번 주」와 같은 주)다.
    둘 다 오면 더 늦은 쪽(더 좁은 쪽)이다."""
    from app.home import service as home_service

    starts: list[datetime] = []
    if completed == "this_week":
        monday = ctx.today - timedelta(days=ctx.today.weekday())
        start, _end = home_service.window_utc_bounds(ctx.settings, monday.isoformat(),
                                                     (monday + timedelta(days=7)).isoformat())
        starts.append(start)
    since = _since(ctx, days)
    if since is not None:
        starts.append(since)
    return max(starts) if starts else None


def _created_from(ctx: ToolContext, days: int | None) -> str | None:
    """「N일 안에 만든」의 시작 날짜 — 티켓 목록의 생성일 조건과 같은 꼴(KST 달력일, 오늘을 첫날로 센다)."""
    return (ctx.today - timedelta(days=int(days) - 1)).isoformat() if days else None


def ticket_route(page_id: str) -> str:
    return f"/tickets/{page_id}"


def document_route(document_id: str) -> str:
    return f"/knowledge/{document_id}"


def project_route(project_id: str) -> str:
    return f"/projects/{project_id}"


def _ticket_row(view: dict) -> dict:
    """티켓 한 줄 - 화면의 목록 칸과 같은 값만. 담당자는 이름 셋까지."""
    page_id = view.get("id")
    row = {
        "ref": page_id,
        "key": view.get("key") or None,
        "title": view.get("title") or "(제목 없음)",
        "status": view.get("status") or None,
        "priority": view.get("priority") or None,
        "due": view.get("due") or None,
        "project": view.get("project") or None,
        "assignees": [name for name in (view.get("assignee_names") or []) if name][:3],
        "blocked": bool(view.get("blocked")),
        "route": ticket_route(page_id) if page_id else None,
    }
    if view.get("completed_at"):
        row["completed_at"] = view.get("completed_at")
    return row


def _ticket_source(view: dict) -> dict:
    page_id = view.get("id")
    return {"type": "ticket", "id": page_id, "title": view.get("title") or "(제목 없음)",
            "route": ticket_route(page_id), "key": view.get("key") or None, "status": view.get("status") or None}


def _ticket_list(tool: str, found: dict, *, note_empty: str, query: str | None = None,
                 offset: int = 0) -> results.Execution:
    views = list(found.get("tickets") or [])[:LIST_LIMIT]
    raw_total = found.get("total")
    total = int(raw_total) if raw_total is not None else offset + len(views)
    return results.ok(
        tool, [_ticket_row(v) for v in views], total=total, offset=offset,
        note=None if views else note_empty, query=query,
        sources=tuple(_ticket_source(v) for v in views if v.get("id")),
    )


def _cut_text(text: str, limit: int) -> tuple[str, bool]:
    """앞에서부터 구획(빈 줄) 단위로 자른다. 첫 구획이 상한보다 길면 글자로 자른다."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    out: list[str] = []
    size = 0
    for block in re.split(r"\n\s*\n", text):
        need = len(block) + (2 if out else 0)
        if size + need > limit:
            break
        out.append(block)
        size += need
    if not out:
        return text[:limit], True
    return "\n\n".join(out), True


def _fit_texts(items: list[dict], key: str, budget: int, *, floor: int = 120) -> None:
    """items 를 JSON 으로 적었을 때 `budget` 안에 들도록 `key` 칸의 글을 고르게 줄인다(제자리). 바닥(`floor`)까지만 줄인다."""
    def size() -> int:
        return len(json.dumps(items, ensure_ascii=False, default=str))

    longest = max((len(item.get(key) or "") for item in items), default=0)
    while items and size() > budget and longest > floor:
        longest = max(floor, int(longest * 0.8))
        for item in items:
            text = item.get(key) or ""
            if len(text) > longest:
                item[key] = text[:longest].rstrip() + "…"


def _short(text: str | None, limit: int) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _names_of(ctx: ToolContext, user_ids) -> dict[str, str]:
    """{user id: 표시 이름} — 한 질의. id 는 결과에 싣지 않고 이름만 쓴다."""
    from sqlalchemy import select

    from app.users.models import User

    ids = sorted({uid for uid in user_ids if uid})
    if not ids:
        return {}
    return {uid: (name or "") for uid, name in ctx.db.execute(
        select(User.id, User.display_name).where(User.id.in_(ids))
    ).all()}


# ── 프로젝트 고르기 (D-567) ────────────────────────────────────────────────────────────────────────────────────


def _resolve_project(ctx: ToolContext, raw: str | None):
    """코드 · id · 이름 → (범위 안 프로젝트 하나, 후보 목록).

    하나로 정해지면 `(프로젝트, [])`, 못 찾으면 `(None, [])`, 이름이 여럿에 걸리면 `(None, 후보들)` 이다. 여럿일 때 예전에는
    `None` 을 돌려 「찾지 못함」이 됐다 — 「SK하이닉스 프로젝트」처럼 같은 고객의 프로젝트가 둘이면 둘 다 있는데 없다고 답했다.
    후보는 `list_in_scope` 의 결과뿐이다 — 보이지 않는 프로젝트는 후보에도 서지 않는다.
    """
    from app.authz.visibility import context_for_user
    from app.projects import repository as projects_repo

    text = (raw or "").strip()
    if not text:
        return None, []
    if _UUID.fullmatch(text):
        from app.core.errors import NotFoundError
        from app.projects.service import get_scoped_project_or_404

        try:
            return get_scoped_project_or_404(ctx.db, text, ctx.principal), []
        except NotFoundError:
            return None, []
    visible = context_for_user(ctx.db, ctx.user)
    rows, _ = projects_repo.list_in_scope(ctx.db, visible, q=text, limit=10)
    if len(rows) == 1:
        return rows[0], []
    exact = [p for p in rows if (p.code or "").lower() == text.lower() or (p.name or "").strip() == text]
    if len(exact) == 1:
        return exact[0], []
    return None, list(rows)


def _project_failure(tool: str, candidates) -> results.Execution:
    """못 찾음은 범위 밖과 같은 문장이다. 여럿이면 후보를 싣고 사용자에게 고르게 한다."""
    if not candidates:
        return results.error(tool, results.ERROR_NOT_FOUND)
    shown = list(candidates)[:5]
    names = ", ".join(f"{p.name}({p.code})" if p.code else p.name for p in shown)
    return results.error(
        tool, results.ERROR_AMBIGUOUS,
        f"같은 이름의 프로젝트가 여럿입니다: {names}. 어느 것인지 사용자에게 물어보세요.",
        extra={"candidates": [
            {"ref": p.id, "code": p.code or None, "name": p.name,
             "status": PROJECT_STATUS_KO.get(p.status, p.status), "route": project_route(p.id)}
            for p in shown
        ]},
        sources=tuple(_project_source(p) for p in shown),
    )


# ── 문서 ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _document_rows(ctx: ToolContext, documents) -> list[dict]:
    """문서 목록 한 쪽 → 결과 줄. 화면 목록과 같은 모음(`list_page_extras`)을 쓴다 — 질의 수는 문서 수와 무관하다."""
    from app.knowledge import service as knowledge

    extras = knowledge.list_page_extras(ctx.db, ctx.user, documents)
    people = extras.get("people") or {}
    out = []
    for document in documents:
        author = (people.get(document.created_by) or {}).get("display_name") if document.created_by else None
        project = (extras.get("projects") or {}).get(document.space_id)
        out.append({
            "ref": document.id,
            "title": document.title or "(제목 없음)",
            "author": author or None,
            "legacy_author": None if document.created_by else (document.legacy_author_name or None),
            "updated_at": _iso(document.updated_at),
            "created_at": _iso(document.created_at),
            "space": (extras.get("spaces") or {}).get(document.space_id) or None,
            "project": {"code": project.get("code"), "name": project.get("name")} if project else None,
            "excerpt": _short((extras.get("excerpts") or {}).get(document.id), LIST_EXCERPT_CHARS),
            "comments": int(((extras.get("counts") or {}).get("comments") or {}).get(document.id, 0)),
            "route": document_route(document.id),
        })
    return out


def _document_source(row: dict) -> dict:
    return {"type": "document", "id": row["ref"], "title": row["title"], "route": row["route"],
            "where": row.get("space") or None}


def _find_space(ctx: ToolContext, raw: str):
    """공간 이름(또는 id) → 범위 안 공간 하나. 못 찾거나 여럿이면 None."""
    from app.core.search_text import matches_folded
    from app.knowledge import service as knowledge

    text = (raw or "").strip()
    spaces = knowledge.list_spaces(ctx.db, ctx.user)
    if _UUID.fullmatch(text):
        return next((s for s in spaces if s.id == text), None)
    found = [s for s in spaces if matches_folded(s.name, text)]
    if len(found) == 1:
        return found[0]
    exact = [s for s in found if (s.name or "").strip() == text]
    return exact[0] if len(exact) == 1 else None


MY_DOCUMENT_VIEWS = ("authored", "edited")


def my_documents(ctx: ToolContext, args) -> results.Execution:
    """묻는 사람의 문서 — 문서 화면(`/api/knowledge/documents?mine=true`)과 같은 함수 · 같은 기준이다.

    「내가 작성한」(`authored`)은 `created_by == 나` 만 센다(D-567). 이관 문서는 작성자를 계정으로 잇지 못해 `created_by` 가
    비어 있고 원본 작성자 이름만 있다 — 이름이 같다고 같은 사람이라고 단정하지 않는다. 그 수는 따로 세어 note 로 말한다.
    「내가 고친」(`edited`)은 판을 하나라도 남긴 문서다(`document_versions.author_id`).
    """
    from app.knowledge import service as knowledge

    project_id = None
    if args.project:
        project, candidates = _resolve_project(ctx, args.project)
        if project is None:
            return _project_failure("my_documents", candidates)
        project_id = project.id
    space_id = None
    if args.space:
        space = _find_space(ctx, args.space)
        if space is None:
            return results.error("my_documents", results.ERROR_NOT_FOUND, "그 공간을 찾지 못했습니다.")
        space_id = space.id
    view = args.view or "authored"
    offset = _offset(args)
    hours = int(args.updated_within_days) * 24 if args.updated_within_days else None
    rows, total = knowledge.list_documents(
        ctx.db, ctx.user, space_id=space_id, project_id=project_id, q=args.query or None,
        created_by=ctx.user.id if view == "authored" else None,
        edited_by=ctx.user.id if view == "edited" else None,
        sort=args.sort or "recent", updated_within_hours=hours, now=ctx.now,
        limit=LIST_LIMIT, offset=offset,
    )
    items = _document_rows(ctx, rows)
    notes: list[str] = []
    if view == "authored":
        legacy = knowledge.count_documents_by_legacy_author(ctx.db, ctx.user, getattr(ctx.user, "display_name", None))
        if legacy:
            notes.append(f"원본 작성자 이름이 묻는 사람과 같은 이관 문서 {legacy}건은 이 수에 넣지 않았습니다.")
    if not items:
        notes.append("조건에 맞는 문서가 없습니다." if offset == 0 else "이 쪽에는 더 보일 문서가 없습니다.")
    return results.ok(
        "my_documents", items, total=int(total), offset=offset, note=" ".join(notes) or None,
        query=args.query or None, sources=tuple(_document_source(row) for row in items),
        extra={"view": view},
    )


def search_documents(ctx: ToolContext, args) -> results.Execution:
    """사내 문서 검색 — **문서 단위**다(D-567). AI 검색과 같은 함수(`retrieval.retrieve`, 가시성은 LIMIT 앞)를 부르되
    문서마다 가장 맞는 조각 하나만 남기고, 같은 조건 · 같은 권한 절로 전체 문서 수를 따로 센다.

    예전에는 조각 여섯을 돌려주고 `total` 이 그 여섯이었다 — 한 문서의 조각 셋이 섞이면 「문서 6개」라는 틀린 수가 나왔다.
    """
    from app.ai.gateway import contract
    from app.ai.retrieval import service as retrieval

    project_id = None
    if args.project:
        project, candidates = _resolve_project(ctx, args.project)
        if project is None:
            return _project_failure("search_documents", candidates)
        project_id = project.id
    offset = max(0, min(_offset(args), retrieval.MAX_OFFSET))
    gateway = ctx.gateway if ctx.gateway is not None else contract.Gateway(enabled=False)
    # 「내 문서 중 …」 — 묻는 사람이 만든 문서로 목록과 수를 같은 절로 좁힌다. 사람은 서버가 정한다(인자는 켜고 끄기뿐이다).
    author_id = ctx.user.id if getattr(args, "mine", None) else None
    found = retrieval.retrieve(
        ctx.db, ctx.user, raw_query=args.query, gateway=gateway, top_k=SEARCH_TOP_K,
        distinct_documents=True, offset=offset, project_id=project_id, author_id=author_id,
    )
    counted = retrieval.count_matching_documents(
        ctx.db, ctx.user, text=args.query, words=found.keywords, expanded=found.expanded, project_id=project_id,
        also_documents=found.semantic_only_documents, author_id=author_id,
    )
    facts = _document_facts(ctx, [cite.document_id for cite in found.citations])
    items, sources = [], []
    for cite in found.citations:
        fact = facts.get(cite.document_id) or {}
        items.append({
            "ref": cite.document_id,
            "title": cite.document_title,
            "author": fact.get("author"),
            "legacy_author": fact.get("legacy_author"),
            "updated_at": fact.get("updated_at"),
            "where": cite.where or None,
            "text": (cite.text_for_context or "")[:DOC_EXCERPT_CHARS],
            "route": cite.route,
        })
        sources.append({"type": "document", "id": cite.document_id, "title": cite.document_title,
                        "route": cite.route, "where": cite.where or None})
    # 결과 한 칸이 런타임의 칸 상한 안에 들게 발췌를 줄인다 — 봉투(수 · 낱말 · 안내)의 몫을 남긴다.
    _fit_texts(items, "text", RESULT_BUDGET_CHARS - 800)
    words = ", ".join(found.keywords) or args.query
    expanded = ", ".join(found.expanded)
    searched = f"찾아본 낱말: {words}" + (f", 함께 찾은 낱말: {expanded}" if expanded else "")
    total = counted.total if counted is not None else None
    notes: list[str] = []
    if not items:
        notes.append(f"맞는 사내 문서를 찾지 못했습니다. {searched}" if offset == 0
                     else f"이 쪽에는 더 보일 문서가 없습니다. {searched}")
    else:
        notes.append(searched)
        if counted is not None:
            notes.append(
                f"total 은 찾아본 낱말이 하나라도 들어 있는 문서 수입니다. 낱말이 모두 들어 있는 문서는 "
                f"{counted.with_every_word}건입니다."
            )
            if counted.semantic_only:
                notes.append(f"뜻이 가까워 찾은 문서 {counted.semantic_only}건이 total 에 들어 있습니다.")
    if counted is None:
        notes.append(results.TOTAL_UNKNOWN_NOTE)
    truncated = None
    if counted is None and found.distinct_total is not None:
        truncated = found.distinct_total > offset + len(items)
    return results.ok(
        "search_documents", items, total=total, truncated=truncated, offset=offset, note=" ".join(notes),
        query=args.query, sources=tuple(sources),
        extra={
            "total_documents": total,
            "documents_with_every_word": counted.with_every_word if counted is not None else None,
            "keywords": list(found.keywords),
            "expanded_keywords": list(found.expanded),
            "semantic": found.semantic,
        },
    )


def _document_facts(ctx: ToolContext, document_ids) -> dict[str, dict]:
    """문서 id → 작성자 이름 · 원본 작성자 · 수정일. 검색 결과 한 쪽에 붙인다(한 질의 + 이름 한 질의)."""
    from sqlalchemy import select

    from app.knowledge.models import Document

    ids = sorted({d for d in document_ids if d})
    if not ids:
        return {}
    rows = ctx.db.execute(
        select(Document.id, Document.created_by, Document.legacy_author_name, Document.updated_at)
        .where(Document.id.in_(ids))
    ).all()
    names = _names_of(ctx, [row[1] for row in rows])
    return {
        document_id: {
            "author": names.get(created_by) or None if created_by else None,
            "legacy_author": None if created_by else (legacy or None),
            "updated_at": _iso(updated_at),
        }
        for document_id, created_by, legacy, updated_at in rows
    }


def get_document(ctx: ToolContext, args) -> results.Execution:
    """문서 하나의 최신 본문(앞에서부터)과 작성자 · 자리 · 꼬리표 · 최근 댓글. 범위 밖 · 휴지통 · 없는 문서는 같은 `not_found` 다."""
    from sqlalchemy import func, select

    from app.core.errors import NotFoundError
    from app.knowledge import categories as categories_mod
    from app.knowledge import service as knowledge
    from app.knowledge import tags as tags_mod
    from app.knowledge import versions
    from app.knowledge.models import DocumentComment

    match = _UUID.search(args.ref or "")
    if match is None:
        return results.error("get_document", results.ERROR_NOT_FOUND)
    try:
        document = knowledge.get_scoped_document_or_404(ctx.db, ctx.user, match.group(0))
    except NotFoundError:
        return results.error("get_document", results.ERROR_NOT_FOUND)
    if document.archived:
        return results.error("get_document", results.ERROR_NOT_FOUND)
    version = versions.current(ctx.db, document)
    extras = knowledge.list_page_extras(ctx.db, ctx.user, [document])
    project = (extras.get("projects") or {}).get(document.space_id)
    category = categories_mod.of_documents(ctx.db, [document.id]).get(document.id)
    tags = [t.name for t in tags_mod.of_documents(ctx.db, [document.id]).get(document.id, [])]
    live = (DocumentComment.document_id == document.id) & DocumentComment.deleted_at.is_(None)
    comments_total = int(ctx.db.execute(select(func.count()).select_from(DocumentComment).where(live)).scalar_one())
    recent = list(ctx.db.execute(
        select(DocumentComment).where(live)
        .order_by(DocumentComment.created_at.desc(), DocumentComment.seq.desc()).limit(3)
    ).scalars().all())
    names = _names_of(ctx, [document.created_by, *[c.author_user_id for c in recent]])
    route = document_route(document.id)
    item = {
        "ref": document.id,
        "title": document.title or "(제목 없음)",
        "author": names.get(document.created_by) or None if document.created_by else None,
        "legacy_author": None if document.created_by else (document.legacy_author_name or None),
        "where": (extras.get("spaces") or {}).get(document.space_id) or None,
        "space": (extras.get("spaces") or {}).get(document.space_id) or None,
        "project": {"code": project.get("code"), "name": project.get("name")} if project else None,
        "category": getattr(category, "name", None) or None,
        "tags": tags,
        "created_at": _iso(document.created_at),
        "updated_at": _iso(document.updated_at),
        "legacy_updated_at": _iso(document.legacy_updated_at),
        "text": "",
        "truncated": False,
        "comments_total": comments_total,
        "recent_comments": [
            {"author": names.get(c.author_user_id) or "알 수 없는 사용자", "at": _iso(c.created_at),
             "text": (c.body or "")[:COMMENT_CHARS]}
            for c in recent
        ],
        "route": route,
    }
    # 본문은 남은 예산만큼 싣는다 — 작성자 · 꼬리표 · 댓글을 먼저 담고 나머지를 본문에 준다(칸 상한, `RESULT_BUDGET_CHARS`).
    room = RESULT_BUDGET_CHARS - len(json.dumps(item, ensure_ascii=False, default=str)) - 300
    text, truncated = _cut_text(version.body_text if version is not None else "", max(500, min(DOC_TEXT_CHARS, room)))
    item["text"], item["truncated"] = text, truncated
    note = "본문이 길어 앞부분만 실었습니다." if truncated else (None if text else "본문이 비어 있습니다.")
    return results.ok("get_document", [item], truncated=truncated, note=note, sources=(
        {"type": "document", "id": document.id, "title": item["title"], "route": route, "where": item["where"]},
    ))


def search_workspace(ctx: ToolContext, args) -> results.Execution:
    """통합 검색 색인에서 티켓 · 문서 · 게시글을 찾는다(낱말 OR, D-536). 사람 종류는 열지 않는다. 팀 채팅은 색인에 없다."""
    from app.search import service as search_service

    kinds = [kind for kind in (args.kinds or ("ticket", "document", "board"))]
    if "board" in kinds and not ctx.flag("board_enabled"):
        kinds.remove("board")
    if "document" in kinds and not ctx.can("DOCUMENT_READ"):
        kinds.remove("document")
    if not kinds:
        return results.error("search_workspace", results.ERROR_UNAVAILABLE)
    found = search_service.search(ctx.db, raw_query=args.query, principal=ctx.principal, per_kind=5,
                                  match=search_service.MATCH_ANY, only_kinds=tuple(kinds))
    items, sources = [], []
    totals: dict[str, int] = {}
    for group in found.get("groups") or []:
        totals[group["kind"]] = int(group.get("total") or 0)
        for hit in group.get("items") or []:
            if len(items) >= LIST_LIMIT:
                break
            items.append({"kind": hit["kind"], "ref": hit["id"], "title": hit["title"],
                          "subtitle": hit.get("subtitle") or None, "route": hit.get("route") or None})
            if hit.get("route"):
                sources.append({"type": hit["kind"], "id": hit["id"], "title": hit["title"], "route": hit["route"]})
    total = int(found.get("total") or 0)
    return results.ok("search_workspace", items, total=total, truncated=bool(found.get("truncated")) or total > len(items),
                      note=None if items else "맞는 항목을 찾지 못했습니다.", query=args.query, sources=tuple(sources),
                      extra={"totals": totals})


# ── 티켓 ──────────────────────────────────────────────────────────────────────────────────────────────────────

MY_VIEWS = ("assigned", "requested", "watching", "due_this_week", "overdue")
TICKET_SORTS = ("due", "created", "updated", "completed")


def _ticket_sort(sort: str | None, due: str | None) -> tuple[str | None, str | None]:
    """도구의 정렬 낱말 → 목록 정렬 키(`app/tickets/query.py::SORT_KEYS`)와 방향. 비우면 화면 기본값이다."""
    if sort == "due" or (sort is None and due):
        return "due_date", "asc"
    if sort == "updated":
        return "updated_at", "desc"
    if sort == "completed":
        return "completed_at", "desc"
    if sort == "created":
        return "created_at", "desc"
    return None, None


def my_work(ctx: ToolContext, args) -> results.Execution:
    """내 업무. 「맡은 것」은 「내 티켓」 화면과 같은 함수(`/api/tickets/mine`), 「요청한 것」 · 「지켜보는 것」은 범위를 건
    목록이다. 프로젝트 조건은 화면의 `project_id` 와 같은 축이다 — 「내 티켓」을 그 프로젝트로 좁힌 수와 `total` 이 같다."""
    from app.tickets import service as tickets
    from app.tickets.repository import PageSpec

    view = args.view
    due = {"due_this_week": "this_week", "overdue": "overdue"}.get(view)
    statuses = list(args.statuses or [])
    completed_from = _completed_from(ctx, getattr(args, "completed", None), getattr(args, "completed_within_days", None))
    if statuses or completed_from is not None:
        active = False
    else:
        active = True if due else not bool(args.include_done)
    project_id = None
    if args.project:
        project, candidates = _resolve_project(ctx, args.project)
        if project is None:
            return _project_failure("my_work", candidates)
        project_id = project.id
    sort_key, order = _ticket_sort(args.sort, due)
    query = SimpleNamespace(
        q=args.query or None, status=statuses or None, due=due, project_id=[project_id] if project_id else None,
        sort=sort_key, order=order, updated_from=_since(ctx, args.updated_within_days), completed_from=completed_from,
    )
    offset = _offset(args)
    page = PageSpec(offset=offset, limit=LIST_LIMIT)
    if view in ("assigned", "due_this_week", "overdue"):
        filters = tickets.build_filters(ctx.db, query, now=ctx.day_now(), active_only=active)
        found = tickets.list_my_tickets(ctx.db, ctx.outbound, ctx.settings, ctx.user, filters=filters, page=page)
    else:
        filters = tickets.build_filters(ctx.db, query, now=ctx.day_now(), active_only=active, viewer=ctx.user)
        reader = tickets.list_requested_tickets if view == "requested" else tickets.list_watching_tickets
        found = reader(ctx.db, ctx.outbound, ctx.settings, ctx.user, filters=filters, page=page)
    return _ticket_list("my_work", found, note_empty="조건에 맞는 티켓이 없습니다.", query=args.query or None,
                        offset=offset)


def get_ticket(ctx: ToolContext, args) -> results.Execution:
    """티켓 하나. 키나 id 를 풀고 → 범위를 확인하고 → 상세를 읽는다. 못 풀거나 범위 밖이면 같은 `not_found` 다.

    `ensure_in_scope` 에는 「행이 없으면 통과」 갈래가 있어(`app/tickets/service.py`) 못 푼 키는 그 앞에서 끝낸다.
    댓글은 최근 것부터 다섯 개씩이다(`comments_offset`, `comments_total`).
    """
    from app.core.errors import NotFoundError, TicketNotFoundError
    from app.tickets import service as tickets
    from app.tickets.models import api_page_id
    from app.work.resolve import resolve

    found = resolve(ctx.db, (args.key or "").strip())
    if found is None:
        return results.error("get_ticket", results.ERROR_NOT_FOUND)
    page_id = api_page_id(found.ticket)
    try:
        tickets.ensure_ticket_visible(ctx.db, page_id, ctx.user)
        detail = tickets.ticket_detail(ctx.db, ctx.outbound, ctx.settings, ctx.user, page_id=page_id)
    except (NotFoundError, TicketNotFoundError):
        return results.error("get_ticket", results.ERROR_NOT_FOUND)
    view = detail.get("ticket") or {}
    comments_offset = max(0, int(getattr(args, "comments_offset", None) or 0))
    comments: list[dict] = []
    comments_total: int | None = None
    try:
        with ctx.db.begin_nested():
            listed = tickets.list_ticket_comments(ctx.db, ctx.outbound, ctx.settings, ctx.user, page_id=page_id)
        live = [c for c in (listed.get("comments") or []) if not c.get("deleted")]
        live.reverse()
        comments_total = len(live)
        comments = [{"author": c.get("author_name") or "알 수 없는 사용자", "at": c.get("created_at"),
                     "text": (c.get("body") or "")[:COMMENT_CHARS]}
                    for c in live[comments_offset:comments_offset + COMMENT_PAGE]]
    except Exception:  # noqa: BLE001 - 댓글을 못 읽어도 티켓은 답한다
        comments = []
    body, cut = _cut_text(detail.get("body_markdown") or "", TICKET_BODY_CHARS)
    item = {
        **_ticket_row(view),
        "start": view.get("start") or None,
        "category": view.get("category") or None,
        "difficulty": view.get("difficulty") or None,
        "issue": bool(view.get("issue")),
        "blocked_reason": view.get("blocked_reason") or None,
        "completed_at": view.get("completed_at"),
        "body": body or None,
        "body_truncated": cut,
        "comments_total": comments_total,
        "comments_offset": comments_offset,
        "recent_comments": comments,
    }
    return results.ok("get_ticket", [item], query=args.key, sources=(_ticket_source(view),))


def _people_in_reach(ctx: ToolContext, name: str) -> list:
    """이름이 맞는 사람 - 보는 사람의 조회 범위 안, 활성 · 비보관만."""
    from sqlalchemy import select

    from app.core.scope import visibility_scope, visible_user_ids
    from app.core.search_text import matches_folded
    from app.users.models import User

    reach = visible_user_ids(ctx.db, visibility_scope(ctx.db, ctx.user))
    stmt = select(User).where(User.active.is_(True), User.archived_at.is_(None))
    if reach is not None:
        if not reach:
            return []
        stmt = stmt.where(User.id.in_(list(reach)))
    people = [u for u in ctx.db.execute(stmt).scalars().all() if matches_folded(u.display_name, name)]
    exact = [u for u in people if (u.display_name or "").strip() == name.strip()]
    return exact if len(exact) == 1 else people


def search_tickets(ctx: ToolContext, args) -> results.Execution:
    """팀 티켓 · 미할당 티켓. 화면과 같은 두 그물(`build_filters(viewer)` + `_drop_out_of_scope`)을 건다.

    상태를 비우면 끝나지 않은 티켓만(예전과 같다), `include_done` 이면 전 상태, `statuses` 를 주면 그 상태만이다. 「최근 N일에
    끝낸」을 물으면(`completed_within_days`) 끝난 티켓을 봐야 하므로 상태를 비워도 전 상태다. `match_body` 는 검색어를 본문에서도
    찾는다(제목 · 티켓 이름과 OR).
    """
    from app.tickets import service as tickets
    from app.tickets.repository import PageSpec, ProjectVisibility

    statuses = list(args.statuses or [])
    active = not statuses and not bool(args.include_done) and not args.completed_within_days
    sort_key, order = _ticket_sort(args.sort, args.due)
    query = SimpleNamespace(
        q=args.query or None, status=statuses or None, due=args.due, sort=sort_key, order=order,
        assignee_user_id=None, body_search=bool(args.match_body and args.query),
        created_from=_created_from(ctx, args.created_within_days),
        updated_from=_since(ctx, args.updated_within_days),
        completed_from=_since(ctx, args.completed_within_days),
    )
    if args.assignee_name:
        if args.scope == "unassigned":
            return results.error("search_tickets", results.ERROR_INVALID_ARGUMENTS,
                                 "미할당 티켓에는 담당자 이름을 줄 수 없습니다.")
        people = _people_in_reach(ctx, args.assignee_name)
        if not people:
            return results.error("search_tickets", results.ERROR_NOT_FOUND, "그 이름의 사람을 찾지 못했습니다.")
        if len(people) > 1:
            names = ", ".join(f"{u.display_name}({u.department or '부서 없음'})" for u in people[:5])
            return results.error("search_tickets", results.ERROR_AMBIGUOUS,
                                 f"같은 이름이 여럿입니다: {names}. 부서를 함께 알려 달라고 사용자에게 물어보세요.")
        query.assignee_user_id = [people[0].id]
    filters = tickets.build_filters(ctx.db, query, now=ctx.day_now(), active_only=active, viewer=ctx.user,
                                    allow_assignee_filter=args.scope == "team")
    if args.project:
        project, candidates = _resolve_project(ctx, args.project)
        if project is None:
            return _project_failure("search_tickets", candidates)
        # 이미 범위 안에서 찾은 프로젝트로 더 좁힌다. 파이썬 그물(`_drop_out_of_scope`)은 그대로 보는 사람 기준이다.
        filters = replace(filters, project_any_of=ProjectVisibility(uids=frozenset({project.id}),
                                                                    page_ids=frozenset()))
    offset = _offset(args)
    page = PageSpec(offset=offset, limit=LIST_LIMIT)
    reader = tickets.list_team_page if args.scope == "team" else tickets.list_unassigned_page
    found = reader(ctx.db, ctx.outbound, ctx.settings, active_only=active, viewer=ctx.user, filters=filters, page=page)
    return _ticket_list("search_tickets", found, note_empty="조건에 맞는 티켓이 없습니다.", query=args.query,
                        offset=offset)


# ── 프로젝트 ──────────────────────────────────────────────────────────────────────────────────────────────────


def _project_row(project, role: str | None = None) -> dict:
    return {
        "ref": project.id,
        "code": project.code or None,
        "name": project.name,
        "status": PROJECT_STATUS_KO.get(project.status, project.status),
        "progress_pct": project.progress_pct,
        "health_score": project.health_score,
        "my_role": PROJECT_ROLE_KO.get(role, role) if role else None,
        "route": project_route(project.id),
    }


def _project_source(project) -> dict:
    return {"type": "project", "id": project.id, "title": project.name, "route": project_route(project.id),
            "status": PROJECT_STATUS_KO.get(project.status, project.status)}


def search_projects(ctx: ToolContext, args) -> results.Execution:
    """프로젝트 목록 - 화면과 같은 범위 함수(`list_in_scope`). 「내 것」은 구성원이거나 담당인 프로젝트로 좁힌다
    (`/api/projects?mine=true` 와 같은 조건)."""
    from sqlalchemy import select

    from app.authz.visibility import context_for_user
    from app.projects import repository as projects_repo
    from app.projects.models import ProjectMember

    visible = context_for_user(ctx.db, ctx.user)
    offset = _offset(args)
    rows, total = projects_repo.list_in_scope(
        ctx.db, visible, q=args.query or None, status=args.status or None, trouble=bool(args.trouble_only),
        offset=offset, limit=LIST_LIMIT, member_user_id=ctx.user.id if args.scope == "mine" else None,
    )
    roles = {}
    if rows:
        roles = dict(ctx.db.execute(
            select(ProjectMember.project_id, ProjectMember.role).where(
                ProjectMember.user_id == ctx.user.id, ProjectMember.project_id.in_([p.id for p in rows]),
            )
        ).all())
    items = []
    for project in rows:
        role = "owner" if project.owner_user_id == ctx.user.id else roles.get(project.id)
        items.append(_project_row(project, role))
    return results.ok(
        "search_projects", items, total=int(total), offset=offset,
        note=None if items else "조건에 맞는 프로젝트가 없습니다.", query=args.query,
        sources=tuple(_project_source(p) for p in rows),
    )


def _scoped_project(ctx: ToolContext, tool: str, raw: str):
    """(프로젝트, 실패) — 후보 해석 뒤 단건 게이트(`get_scoped_project_or_404`)를 한 번 더 지난다."""
    from app.core.errors import NotFoundError
    from app.projects.service import get_scoped_project_or_404

    project, candidates = _resolve_project(ctx, raw)
    if project is None:
        return None, _project_failure(tool, candidates)
    try:
        return get_scoped_project_or_404(ctx.db, project.id, ctx.principal), None
    except NotFoundError:
        return None, results.error(tool, results.ERROR_NOT_FOUND)


def get_project_summary(ctx: ToolContext, args) -> results.Execution:
    """프로젝트 하나의 진행률(과 기준) · 건강도(와 이유). 단건 게이트(`get_scoped_project_or_404`)를 먼저 지난다."""
    from app.projects.service import project_health, project_progress

    project, failure = _scoped_project(ctx, "get_project_summary", args.project)
    if failure is not None:
        return failure
    progress = project_progress(ctx.db, project).as_dict()
    health = project_health(ctx.db, project, today=ctx.today.isoformat()).as_dict()
    basis = progress.get("basis") or {}
    item = {
        **_project_row(project),
        "starts_on": project.starts_on.isoformat() if project.starts_on else None,
        "ends_on": project.ends_on.isoformat() if project.ends_on else None,
        "progress": {
            "percent": progress.get("percent"),
            "counted_tasks": basis.get("counted_tasks"),
            "done_tasks": basis.get("done_tasks"),
        },
        "health": {
            "score": health.get("score"),
            "reasons": [{"label": r.get("label"), "detail": r.get("detail")} for r in (health.get("reasons") or [])[:5]],
        },
    }
    return results.ok("get_project_summary", [item], query=args.project, sources=(_project_source(project),))


def _ticket_brief(row, *, at_field: str) -> dict:
    """진행 현황의 티켓 한 줄 — 행(`Ticket`)에서 바로 만든다."""
    from app.tickets.models import api_page_id

    page_id = api_page_id(row)
    return {
        "ref": page_id,
        "key": row.canonical_key or None,
        "title": row.title or "(제목 없음)",
        "status": row.status or None,
        "due": row.due_date or None,
        at_field: _iso(getattr(row, at_field)),
        "route": ticket_route(page_id),
    }


def project_activity(ctx: ToolContext, args) -> results.Execution:
    """프로젝트 하나의 진행 현황을 **기록으로** — 진행률 · WBS · 건강과 같은 정본 집합(`ticket_rows_for_project`)을 센다(D-567).

    상태별 수는 끝난 것 · 취소한 것까지 전 상태다(휴지통은 빠진다). 「최근」은 `days` 일(기본 30) 안이다. 제목을 나열하는 줄은
    티켓 화면의 범위 판정(`_project_visibility`)을 한 번 더 지난다 — 소속을 판정하지 못한 티켓은 수에만 들고 이름은 나오지 않는다.
    """
    from sqlalchemy import select

    from app.core.dates import parse_date
    from app.projects import repository as projects_repo
    from app.projects.models import ProjectMember, ProjectWeeklyReport
    from app.projects.service import project_health, project_progress
    from app.tickets.models import PROJECT_LINK_OK
    from app.tickets.service import _project_visibility
    from app.users.models import User
    from app.work import workflow

    project, failure = _scoped_project(ctx, "project_activity", args.project)
    if failure is not None:
        return failure
    days = int(args.days or 30)
    since = ctx.now - timedelta(days=days)
    today = ctx.today
    rows = projects_repo.ticket_rows_for_project(ctx.db, project)
    visible = _project_visibility(ctx.db, ctx.user)

    def nameable(row) -> bool:
        if visible is None:
            return True
        return row.project_link == PROJECT_LINK_OK and row.project_uid in visible.uids

    status_counts = Counter((row.status or "미정") for row in rows)
    open_rows = [row for row in rows if (row.status or "") not in TERMINAL_STATUSES]
    overdue_open = sum(
        1 for row in open_rows if workflow.is_overdue(parse_date(row.due_date), row.status, today=today)
    )
    blocked = sum(1 for row in open_rows if row.blocked_flag)
    completed = sorted(
        (row for row in rows if row.completed_at and row.completed_at >= since and nameable(row)),
        key=lambda row: (row.completed_at, row.id), reverse=True,
    )
    shown_done = {row.id for row in completed[:ACTIVITY_ROWS]}
    updated = sorted(
        (row for row in rows if row.updated_at and row.updated_at >= since and nameable(row) and row.id not in shown_done),
        key=lambda row: (row.updated_at, row.id), reverse=True,
    )
    milestones = projects_repo.milestones_for_project(ctx.db, project)
    reports = list(ctx.db.execute(
        select(ProjectWeeklyReport).where(ProjectWeeklyReport.project_id == project.id)
        .order_by(ProjectWeeklyReport.week_of.desc()).limit(2)
    ).scalars().all())
    members = list(ctx.db.execute(
        select(User.display_name, ProjectMember.role)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project.id, User.active.is_(True), User.archived_at.is_(None))
        .order_by(User.display_name)
    ).all())
    owner_name = _names_of(ctx, [project.owner_user_id]).get(project.owner_user_id) if project.owner_user_id else None
    progress = project_progress(ctx.db, project).as_dict()
    health = project_health(ctx.db, project, today=today.isoformat()).as_dict()
    basis = progress.get("basis") or {}

    documents = None
    document_rows: list[dict] = []
    if ctx.can("DOCUMENT_READ"):
        from app.knowledge import service as knowledge

        doc_rows, doc_total = knowledge.list_documents(
            ctx.db, ctx.user, project_id=project.id, sort="recent", limit=PROJECT_DOCUMENTS, offset=0,
        )
        document_rows = [
            {"ref": d.id, "title": d.title or "(제목 없음)", "updated_at": _iso(d.updated_at),
             "route": document_route(d.id)}
            for d in doc_rows
        ]
        documents = {"total": int(doc_total), "items": document_rows}

    item = {
        **_project_row(project),
        "owner": owner_name or None,
        "window_days": days,
        "tickets": {
            "total": len(rows),
            "open": len(open_rows),
            "overdue_open": overdue_open,
            "blocked": blocked,
            "status_counts": dict(sorted(status_counts.items())),
        },
        "recent_completed": [_ticket_brief(row, at_field="completed_at") for row in completed[:ACTIVITY_ROWS]],
        "recent_completed_total": len(completed),
        "recent_updated": [_ticket_brief(row, at_field="updated_at") for row in updated[:ACTIVITY_ROWS]],
        "recent_updated_total": len(updated),
        "milestones": [
            {"name": m.name, "due_on": _iso(m.due_on), "status": MILESTONE_STATUS_KO.get(m.status, m.status)}
            for m in milestones[:ACTIVITY_ROWS]
        ],
        "milestones_total": len(milestones),
        "weekly_reports": [
            {"week_of": _iso(r.week_of), "summary": _cut_text(r.summary_md or "", REPORT_CHARS)[0] or None}
            for r in reports
        ],
        "progress": {
            "percent": progress.get("percent"),
            "counted_tasks": basis.get("counted_tasks"),
            "done_tasks": basis.get("done_tasks"),
        },
        "health": {
            "score": health.get("score"),
            "reasons": [{"label": r.get("label"), "detail": r.get("detail")} for r in (health.get("reasons") or [])[:5]],
        },
        "members": [
            {"name": name, "role": PROJECT_ROLE_KO.get(role, role)} for name, role in members[:ACTIVITY_ROWS] if name
        ],
        "members_total": len(members),
        "documents": documents,
    }
    sources = [_project_source(project)]
    for row in [*completed[:ACTIVITY_ROWS], *updated[:ACTIVITY_ROWS]]:
        brief = _ticket_brief(row, at_field="updated_at")
        sources.append({"type": "ticket", "id": brief["ref"], "title": brief["title"], "route": brief["route"],
                        "key": brief["key"], "status": brief["status"]})
    for doc in document_rows:
        sources.append({"type": "document", "id": doc["ref"], "title": doc["title"], "route": doc["route"]})
    _fit_activity(item)
    return results.ok("project_activity", [item], query=args.project, sources=tuple(sources))


def _fit_activity(item: dict) -> None:
    """진행 현황 한 줄이 칸 예산을 넘으면 덜 중요한 것부터 줄인다 — 리포트 글 → 둘째 리포트 → 바뀐 일 → 마일스톤 · 구성원 · 문서.

    수(`*_total`)는 그대로 둔다 — 줄을 덜 보였을 뿐 센 값은 바뀌지 않는다.
    """
    def size() -> int:
        return len(json.dumps(item, ensure_ascii=False, default=str))

    steps = (
        lambda: [r.update(summary=_short(r.get("summary"), 500)) for r in item["weekly_reports"]],
        lambda: item.update(weekly_reports=item["weekly_reports"][:1]),
        lambda: item.update(recent_updated=item["recent_updated"][:4]),
        lambda: item.update(milestones=item["milestones"][:4], members=item["members"][:4]),
        lambda: item["documents"] and item["documents"].update(items=item["documents"]["items"][:3]),
        lambda: item.update(recent_completed=item["recent_completed"][:4], recent_updated=item["recent_updated"][:2]),
    )
    for step in steps:
        if size() <= RESULT_BUDGET_CHARS:
            return
        step()


# ── 결재 · 사람 · 최근 변경 · 요약 ──────────────────────────────────────────────────────────────────────────────


def my_approvals(ctx: ToolContext, args) -> results.Execution:
    """내 결재함 - 화면(`/api/approvals/mine`)과 같은 함수다(`approvals.service.list_my_approvals`)."""
    from app.approvals import service as approvals
    from app.core.feature_flags import load_feature_flags

    offset = _offset(args)
    found = approvals.list_my_approvals(
        ctx.db, ctx.user, ctx.principal, box=args.box, now=ctx.now,
        self_approval_allowed=bool(load_feature_flags(ctx.settings.config_dir).get("self_approval_allowed")),
        offset=offset, limit=LIST_LIMIT,
    )
    items, sources = [], []
    for row in found["rows"]:
        view = approvals.approval_view(row, ctx.now, names=found["names"], can_decide=found["can_decide"])
        label = approvals.request_type_label(view["request_type"])
        route = f"/my-approvals?id={view['id']}"
        items.append({
            "ref": view["id"],
            "title": label,
            "type": label,
            "requester": view.get("requester_name"),
            "status": approvals.status_label(view["status"]),
            "created_at": view.get("requested_at"),
            "expires_at": view.get("expires_at"),
            "overdue": bool(view.get("overdue")),
            "route": route,
        })
        sources.append({"type": "approval", "id": view["id"], "title": label, "route": route,
                        "status": approvals.status_label(view["status"])})
    note = None
    if args.box == "todo" and not found["can_decide"]:
        note = "이 사람은 결재 권한이 없어 결재할 건이 없습니다."
    elif not items:
        note = "조건에 맞는 결재가 없습니다."
    return results.ok("my_approvals", items, total=found["total"], offset=offset, note=note, sources=tuple(sources))


def find_people(ctx: ToolContext, args) -> results.Execution:
    """사람 찾기 - 팀 채팅 디렉터리와 같은 칸(같은 조직, 활성, 비보관). 이름 · 부서 · 직책만 나간다."""
    from app.team_chat.repository import directory_search

    people, total = directory_search(ctx.db, ctx.user, args.query, limit=LIST_LIMIT)
    items = [{"name": u.display_name, "department": u.department, "title": u.title} for u in people]
    return results.ok("find_people", items, total=total,
                      note=None if items else "맞는 사람을 찾지 못했습니다.", query=args.query)


def recent_changes(ctx: ToolContext, args) -> results.Execution:
    """최근 바뀐 문서 · 새 게시글 - 홈 화면과 같은 읽기(`home.readers`)."""
    from app.home import readers
    from app.home import service as home_service

    days = int(args.days or 7)
    kinds = list(args.kinds or ("documents", "board"))
    today = ctx.today
    start, end = (today - timedelta(days=days - 1)).isoformat(), (today + timedelta(days=1)).isoformat()
    items, sources = [], []
    total = 0
    if "documents" in kinds and ctx.can("DOCUMENT_READ"):
        since, until = home_service.utc_iso_bounds(ctx.settings, start, end)
        docs = readers.documents_changed_between(ctx.db, since, until, limit=8, viewer=ctx.user)
        total += int(docs.get("count") or 0)
        for row in docs.get("items") or []:
            route = document_route(row["id"])
            items.append({"kind": "document", "ref": row["id"], "title": row.get("title") or "(제목 없음)",
                          "changed_at": row.get("last_edited"), "route": route})
            sources.append({"type": "document", "id": row["id"], "title": row.get("title") or "(제목 없음)",
                            "route": route})
    if "board" in kinds and ctx.flag("board_enabled"):
        since_utc, until_utc = home_service.window_utc_bounds(ctx.settings, start, end)
        posts = readers.board_posts_between(ctx.db, since_utc, until_utc, limit=5, org_id=_board_org(ctx))
        total += int(posts.get("count") or 0)
        for row in posts.get("items") or []:
            route = f"/board/{row['id']}"
            items.append({"kind": "board", "ref": row["id"], "title": row.get("title") or "(제목 없음)",
                          "author": row.get("author_name"), "changed_at": row.get("created_at"), "route": route})
            sources.append({"type": "board", "id": row["id"], "title": row.get("title") or "(제목 없음)",
                            "route": route})
    return results.ok("recent_changes", items, total=total, truncated=total > len(items),
                      note=None if items else f"최근 {days}일 동안 바뀐 항목이 없습니다.", sources=tuple(sources))


def _board_org(ctx: ToolContext) -> str | None:
    """게시판의 축(`app/board/router.py::_viewer_org_id` 와 같은 판정) - 전역이면 None, 아니면 내 조직."""
    from app.core.scope import visibility_scope

    if visibility_scope(ctx.db, ctx.user).is_global:
        return None
    return getattr(ctx.user, "org_id", None)


_DROP_KEYS = frozenset({
    "id", "uid", "user_id", "assignee_user_ids", "assignee_people", "project_ids", "project_uid", "avatar_url",
    "avatar_default_key", "email", "sprint_id", "tid", "est_wd", "act_wd", "message", "error",
})


def _compact(value, depth: int = 0):
    """사실 묶음을 모델용으로 줄인다 - 티켓은 한 줄 모양, 목록은 다섯 개, 내부 id · 이메일은 뺀다."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        if value.get("id") and "key" in value and "title" in value:
            return _ticket_row(value)
        return {k: _compact(v, depth + 1) for k, v in value.items() if k not in _DROP_KEYS}
    if isinstance(value, list):
        return [_compact(v, depth + 1) for v in value[:5]]
    return value


def _ticket_sources(value, out: list) -> None:
    if isinstance(value, dict):
        if value.get("id") and "key" in value and "title" in value:
            out.append(_ticket_source(value))
            return
        for child in value.values():
            _ticket_sources(child, out)
    elif isinstance(value, list):
        for child in value[:5]:
            _ticket_sources(child, out)


def work_summary(ctx: ToolContext, args) -> results.Execution:
    """오늘 · 스탠드업 · 이번 주의 사실 묶음 - 홈과 비서 화면이 쓰는 같은 함수(`app/assistant/facts.py`)."""
    from app.assistant import facts
    from app.core.source_registry import build_ticket_repository

    reader = {"today": facts.briefing_facts, "standup": facts.standup_facts,
              "this_week": facts.weekly_digest_facts}[args.period]
    found = reader(ctx.db, ctx.outbound, ctx.settings, ctx.user,
                   repo=build_ticket_repository(ctx.settings, ctx.outbound), now=ctx.now)
    sources: list = []
    _ticket_sources(found, sources)
    seen, unique = set(), []
    for source in sources:
        if source["id"] not in seen:
            seen.add(source["id"])
            unique.append(source)
    return results.ok("work_summary", [_compact(found)], sources=tuple(unique[:12]))


# ── 알림 · 활동 · 회의 (D-567) ─────────────────────────────────────────────────────────────────────────────────

#: 알림의 관련 대상 → 출처 종류. 화면이 그리는 다섯 갈래만 출처가 된다(나머지는 경로만 싣는다).
_NOTIFICATION_SOURCE_TYPES = {"ticket": "ticket", "document": "document", "board_post": "board", "approval": "approval"}
#: 팀 채팅 알림 — 본문에 대화가 실려 있다. 팀 채팅은 AI 가 찾지 않는다(사용자 결정 2026-10-15)라 본문을 싣지 않는다.
_CHAT_RELATED = frozenset({"chat_room", "chat_mention"})


def my_notifications(ctx: ToolContext, args) -> results.Execution:
    """묻는 사람이 받은 알림 — 알림 화면(`/api/notifications`)과 같은 행(본인 것만), 최근 것부터.

    `unread_total` 은 알림 벨의 숫자(`/api/notifications/unread-count` 의 `unread`)와 같은 함수다. 경로는 알림 목록과 같은 표
    (`destinations.destination_for`)가 만든다. 사람을 가리키는 경로(`/users?id=`)와 팀 채팅 알림의 본문은 싣지 않는다.
    """
    from sqlalchemy import func, select

    from app.notifications.destinations import destination_for
    from app.notifications.models import Notification
    from app.notifications.service import unread_count

    stmt = select(Notification).where(Notification.user_id == ctx.user.id)
    if args.unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if args.days:
        stmt = stmt.where(Notification.created_at >= ctx.now - timedelta(days=int(args.days)))
    total = int(ctx.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    offset = _offset(args)
    rows = list(ctx.db.execute(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(offset).limit(LIST_LIMIT)
    ).scalars().all())
    items, sources = [], []
    for row in rows:
        related = row.related_object_type or ""
        route = None if related == "user" else destination_for(related, row.related_object_id, row.audience)
        chat = related in _CHAT_RELATED
        items.append({
            "ref": row.id,
            "title": _mask_emails(row.title) or "(제목 없음)",
            "body": None if chat else _short(_mask_emails(row.body), NOTIFICATION_BODY_CHARS),
            "read": row.read_at is not None,
            "created_at": _iso(row.created_at),
            "route": route,
        })
        source_type = _NOTIFICATION_SOURCE_TYPES.get(related)
        if source_type and route and row.related_object_id:
            sources.append({"type": source_type, "id": row.related_object_id, "title": _mask_emails(row.title) or "",
                            "route": route})
    unread_total = int(unread_count(ctx.db, ctx.user.id))
    note = None if items else ("조건에 맞는 알림이 없습니다." if offset == 0 else "이 쪽에는 더 보일 알림이 없습니다.")
    return results.ok("my_notifications", items, total=total, offset=offset, note=note, sources=tuple(sources),
                      extra={"unread_total": unread_total})


#: 티켓 활동 종류 → 문장 조각(`app/work/models.py::ACT_KINDS`). 담당자 · 회차의 앞뒤 값은 내부 값이라 싣지 않는다.
ACTIVITY_SENTENCES = {
    "created": "티켓을 추가했습니다.",
    "status": "상태를 바꿨습니다.",
    "assignee": "담당자를 바꿨습니다.",
    "sprint": "스프린트 회차를 바꿨습니다.",
    "rank": "순서를 바꿨습니다.",
    "relation": "연결된 티켓을 바꿨습니다.",
    "field": "티켓 값을 바꿨습니다.",
}
ACTIVITY_KINDS = ("tickets", "documents", "comments")


def _ro(word: str) -> str:
    """「~로」와 「~으로」 — 끝 글자에 받침이 없거나 ㄹ 받침이면 「로」다. 한글이 아니면 「(으)로」."""
    last = (word or "").strip()[-1:]
    if not last or not ("가" <= last <= "힣"):
        return "로"
    final = (ord(last) - 0xAC00) % 28
    return "로" if final in (0, 8) else "으로"


def _ticket_scope_clauses(ctx: ToolContext) -> list:
    """티켓 목록과 같은 범위 절 — 소속 프로젝트가 보이는 티켓만, 휴지통 제외(`query.filter_clauses` 와 같은 판정)."""
    from sqlalchemy import false

    from app.tickets.models import PROJECT_LINK_OK, Ticket
    from app.tickets.query import not_trashed_clause
    from app.tickets.service import _project_visibility

    clauses = [not_trashed_clause()]
    visible = _project_visibility(ctx.db, ctx.user)
    if visible is not None:
        if not visible.uids:
            clauses.append(false())
        else:
            clauses.append(Ticket.project_link == PROJECT_LINK_OK)
            clauses.append(Ticket.project_uid.in_(tuple(sorted(visible.uids))))
    return clauses


def my_activity(ctx: ToolContext, args) -> results.Execution:
    """묻는 사람이 최근에 한 일 — 티켓 활동(`ticket_activities.actor`) · 문서 판(`document_versions.author`) · 단 댓글(티켓 ·
    문서)을 시간 순으로 합친다. 셋 다 **지금 볼 수 있는 대상**만이다 — 다른 부서 프로젝트로 옮겨 간 티켓의 활동, 보관한
    문서의 판, 볼 수 없게 된 글의 댓글은 나오지 않는다. `total` 은 셋의 합이다.
    """
    from sqlalchemy import func, select

    from app.knowledge.models import Document, DocumentComment, DocumentVersion
    from app.knowledge.service import _document_scope
    from app.tickets.models import Ticket, TicketComment, api_page_id
    from app.work.models import TicketActivity

    days = int(args.days or 14)
    since = ctx.now - timedelta(days=days)
    kinds = set(args.kinds or ACTIVITY_KINDS)
    offset = _offset(args)
    need = offset + LIST_LIMIT
    me = ctx.user.id
    events: list[tuple[datetime, str, dict, dict | None]] = []
    totals: dict[str, int] = {}
    ticket_scope = _ticket_scope_clauses(ctx)
    doc_clause = _document_scope(ctx.db, ctx.user)[1]
    doc_scope = [Document.archived.is_(False)] + ([doc_clause] if doc_clause is not None else [])

    def counted(stmt) -> int:
        return int(ctx.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

    def ticket_event(at, sentence: str, ticket) -> tuple:
        page_id = api_page_id(ticket)
        row = {"kind": "ticket", "at": _iso(at), "action": sentence, "title": ticket.title or "(제목 없음)",
               "key": ticket.canonical_key or None, "route": ticket_route(page_id)}
        source = {"type": "ticket", "id": page_id, "title": row["title"], "route": row["route"], "key": row["key"],
                  "status": ticket.status or None}
        return (at, "t", row, source)

    if "tickets" in kinds:
        stmt = (select(TicketActivity, Ticket).join(Ticket, Ticket.id == TicketActivity.ticket_id)
                .where(TicketActivity.actor_user_id == me, TicketActivity.created_at >= since, *ticket_scope))
        totals["tickets"] = counted(stmt)
        for act, ticket in ctx.db.execute(
            stmt.order_by(TicketActivity.created_at.desc(), TicketActivity.seq.desc()).limit(need)
        ).all():
            sentence = ACTIVITY_SENTENCES.get(act.kind, ACTIVITY_SENTENCES["field"])
            if act.kind == "status" and act.from_value and act.to_value:
                sentence = f"상태를 {act.from_value}에서 {act.to_value}{_ro(act.to_value)} 바꿨습니다."
            events.append(ticket_event(act.created_at, sentence, ticket))
    if "documents" in kinds:
        stmt = (select(DocumentVersion, Document).join(Document, Document.id == DocumentVersion.document_id)
                .where(DocumentVersion.author_id == me, DocumentVersion.created_at >= since, *doc_scope))
        totals["documents"] = counted(stmt)
        for version, document in ctx.db.execute(
            stmt.order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc()).limit(need)
        ).all():
            sentence = "문서를 추가했습니다." if version.version_no == 1 else f"문서를 수정해 {version.version_no}판을 남겼습니다."
            row = {"kind": "document", "at": _iso(version.created_at), "action": sentence,
                   "title": document.title or "(제목 없음)", "route": document_route(document.id)}
            events.append((version.created_at, "d", row,
                           {"type": "document", "id": document.id, "title": row["title"], "route": row["route"]}))
    if "comments" in kinds:
        ticket_comments = (select(TicketComment, Ticket).join(Ticket, Ticket.id == TicketComment.ticket_uid)
                           .where(TicketComment.author_user_id == me, TicketComment.deleted_at.is_(None),
                                  TicketComment.created_at >= since, *ticket_scope))
        document_comments = (select(DocumentComment, Document).join(Document, Document.id == DocumentComment.document_id)
                             .where(DocumentComment.author_user_id == me, DocumentComment.deleted_at.is_(None),
                                    DocumentComment.created_at >= since, *doc_scope))
        totals["comments"] = counted(ticket_comments) + counted(document_comments)
        for comment, ticket in ctx.db.execute(
            ticket_comments.order_by(TicketComment.created_at.desc(), TicketComment.seq.desc()).limit(need)
        ).all():
            at, _tag, row, source = ticket_event(comment.created_at, "티켓에 댓글을 달았습니다.", ticket)
            row["kind"] = "comment"
            row["text"] = (comment.body or "")[:COMMENT_CHARS]
            events.append((at, "c", row, source))
        for comment, document in ctx.db.execute(
            document_comments.order_by(DocumentComment.created_at.desc(), DocumentComment.seq.desc()).limit(need)
        ).all():
            row = {"kind": "comment", "at": _iso(comment.created_at), "action": "문서에 댓글을 달았습니다.",
                   "title": document.title or "(제목 없음)", "text": (comment.body or "")[:COMMENT_CHARS],
                   "route": document_route(document.id)}
            events.append((comment.created_at, "c", row,
                           {"type": "document", "id": document.id, "title": row["title"], "route": row["route"]}))
    events.sort(key=lambda event: (event[0], event[1]), reverse=True)
    page = events[offset:offset + LIST_LIMIT]
    items = [row for _at, _tag, row, _source in page]
    sources = [source for _at, _tag, _row, source in page if source]
    total = sum(totals.values())
    note = None if items else (f"최근 {days}일 동안 한 일을 찾지 못했습니다." if offset == 0
                               else "이 쪽에는 더 보일 활동이 없습니다.")
    return results.ok("my_activity", items, total=total, offset=offset, note=note, sources=tuple(sources),
                      extra={"totals": totals, "window_days": days})


def sprint_route(sprint: dict) -> str:
    """스프린트 회의 화면의 주소 — 화면의 질의 상태 이름(`screens/Sprint.jsx::SPRINT_SPEC` 의 team · sprint)과 같다."""
    team = sprint.get("department_id") or "none"
    return f"/sprint?team={team}&sprint={sprint['id']}"


def sprint_meetings(ctx: ToolContext, args) -> results.Execution:
    """스프린트 회차 하나의 회의록 — 정한 것과 할 일(`meeting.list_decisions`). 회차는 볼 수 있는 목록(`list_sprints`)에서만 고른다.

    회차 이름을 비우면 묻는 사람 팀의 진행 중인 회차, 없으면 볼 수 있는 진행 중인 회차, 그것도 없으면 가장 최근 회차다.
    items 는 회의록 줄이고 `total` 이 그 회차의 전체 줄 수다. 결정에 걸린 티켓은 묻는 사람이 볼 수 있을 때만 이름과 경로를 싣는다.
    """
    from sqlalchemy import select

    from app.core.search_text import matches_folded
    from app.org.models import Department
    from app.tickets.models import Ticket, api_page_id
    from app.work import meeting as meeting_mod
    from app.work import service as work_service

    sprints = work_service.list_sprints(ctx.db, ctx.user, today=ctx.today)
    dept_ids = sorted({s["department_id"] for s in sprints if s.get("department_id")})
    teams = dict(ctx.db.execute(select(Department.id, Department.name).where(Department.id.in_(dept_ids))).all()) \
        if dept_ids else {}
    pool = sprints
    if args.team:
        pool = [s for s in pool if matches_folded(teams.get(s.get("department_id") or "", ""), args.team)]
    picked = None
    notes: list[str] = []
    if args.sprint:
        text = args.sprint.strip()
        matched = [s for s in pool if s["id"] == text] or [s for s in pool if matches_folded(s.get("name"), text)]
        if not matched:
            return results.error("sprint_meetings", results.ERROR_NOT_FOUND, "그 이름의 스프린트 회차를 찾지 못했습니다.")
        picked = matched[0]
        if len(matched) > 1:
            notes.append("이름이 맞는 회차가 여럿이라 가장 최근 회차를 보였습니다.")
    else:
        mine = getattr(ctx.user, "department_id", None)
        active = [s for s in pool if s.get("active")]
        own = [s for s in active if mine and s.get("department_id") == mine]
        picked = (own or active or pool or [None])[0]
    if picked is None:
        return results.ok("sprint_meetings", [], total=0, note="볼 수 있는 스프린트 회차가 없습니다.")
    decisions = meeting_mod.list_decisions(ctx.db, picked["id"])
    ticket_ids = sorted({d["ticket_id"] for d in decisions if d.get("ticket_id")})
    visible_tickets = {}
    if ticket_ids:
        visible_tickets = {
            t.id: t for t in ctx.db.execute(
                work_service._visible_tickets_stmt(ctx.db, ctx.user).where(Ticket.id.in_(ticket_ids))
            ).scalars().all()
        }
    offset = _offset(args)
    shown = decisions[offset:offset + DECISIONS_LIMIT]
    items = []
    for d in shown:
        ticket = visible_tickets.get(d.get("ticket_id") or "")
        items.append({
            "kind": DECISION_KIND_KO.get(d.get("kind"), d.get("kind")),
            "body": _short(d.get("body"), DECISION_BODY_CHARS),
            "assignee": (d.get("assignee") or {}).get("display_name") or None,
            "due_date": d.get("due_date"),
            "done": bool(d.get("done")),
            "ticket": {"key": d.get("ticket_key"), "route": ticket_route(api_page_id(ticket))} if ticket else None,
        })
    route = sprint_route(picked)
    sprint = {
        "name": picked.get("name"), "team": teams.get(picked.get("department_id") or "") or None,
        "starts_on": picked.get("starts_on"), "ends_on": picked.get("ends_on"), "state": picked.get("state"),
        "active": picked.get("active"), "goal": picked.get("goal") or None, "route": route,
    }
    if not items:
        notes.append("이 회차에는 아직 적힌 회의록이 없습니다." if offset == 0 else "이 쪽에는 더 보일 회의록이 없습니다.")
    sources = [{"type": "sprint", "id": picked["id"], "title": picked.get("name") or "스프린트 회차", "route": route}]
    for d in shown:
        ticket = visible_tickets.get(d.get("ticket_id") or "")
        if ticket is not None:
            page_id = api_page_id(ticket)
            sources.append({"type": "ticket", "id": page_id, "title": ticket.title or "(제목 없음)",
                            "route": ticket_route(page_id), "key": ticket.canonical_key or None,
                            "status": ticket.status or None})
    return results.ok("sprint_meetings", items, total=len(decisions), offset=offset, note=" ".join(notes) or None,
                      query=args.sprint or args.team or None, sources=tuple(sources),
                      extra={"sprint": sprint, "route": route})
