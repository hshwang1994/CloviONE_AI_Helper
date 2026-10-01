"""AI 도우미 도구 열두 개의 읽기 — 화면이 쓰는 권한 범위 함수를 그대로 부른다 (D-535).

규칙은 넷이다.

  * 대화 주인(`ctx.user`)의 권한으로만 읽는다. 사람 · id · 이메일을 인자로 받는 도구는 없다 - 모델이 다른 사람을
    지목할 수 없다
  * 범위 밖 대상은 없는 대상과 **같은** `not_found` 다(같은 문장). 존재를 흘리지 않는다
  * 결과에 이메일 · 역할 · 내부 사용자 id 를 싣지 않는다. 사람은 이름(과 부서 · 직책)으로만 나간다
  * 경로는 서버가 만든다 - 화면이 쓰는 경로와 같은 모양이다(`/tickets/…` · `/knowledge/…` · `/projects/…` ·
    `/my-approvals?id=…` · `/board/…`)

함수는 모두 `(ctx, args) -> results.Execution` 이다. 트랜잭션은 부른 쪽(`catalog.execute`)이 READ ONLY 로 연다 - 여기서
쓰기를 하면 그 도구는 `unavailable` 로 끝나고 아무것도 남지 않는다.
"""

from __future__ import annotations

import re
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

#: 티켓 상태 낱말(`app/work/workflow.py`). 도구 스키마의 선택지와 같다.
TICKET_STATUSES = ("계획", "진행", "검증", "완료", "보류", "취소")
PROJECT_STATUS_KO = {"planned": "계획", "active": "진행", "on_hold": "보류", "done": "완료"}
PROJECT_ROLE_KO = {"owner": "담당", "member": "구성원", "viewer": "보기"}

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


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


def ticket_route(page_id: str) -> str:
    return f"/tickets/{page_id}"


def _ticket_row(view: dict) -> dict:
    """티켓 한 줄 - 화면의 목록 칸과 같은 값만. 담당자는 이름 셋까지."""
    page_id = view.get("id")
    return {
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


def _ticket_source(view: dict) -> dict:
    page_id = view.get("id")
    return {"type": "ticket", "id": page_id, "title": view.get("title") or "(제목 없음)",
            "route": ticket_route(page_id), "key": view.get("key") or None, "status": view.get("status") or None}


def _ticket_list(tool: str, found: dict, *, note_empty: str, query: str | None = None) -> results.Execution:
    views = list(found.get("tickets") or [])[:LIST_LIMIT]
    total = int(found.get("total") or len(views))
    return results.ok(
        tool, [_ticket_row(v) for v in views], total=total, truncated=total > len(views),
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


# ── 문서 ──────────────────────────────────────────────────────────────────────────────────────────────────────


def search_documents(ctx: ToolContext, args) -> results.Execution:
    """사내 문서 검색 - AI 검색과 같은 함수(`retrieval.retrieve`, 가시성은 LIMIT 앞)."""
    from app.ai.retrieval import service as retrieval

    found = retrieval.retrieve(ctx.db, ctx.user, raw_query=args.query, gateway=ctx.gateway, top_k=6)
    items, sources = [], []
    for cite in found.citations:
        items.append({
            "ref": cite.document_id,
            "title": cite.document_title,
            "where": cite.where or None,
            "text": (cite.text_for_context or "")[:DOC_EXCERPT_CHARS],
            "route": cite.route,
        })
        sources.append({"type": "document", "id": cite.document_id, "title": cite.document_title,
                        "route": cite.route, "where": cite.where or None})
    words = ", ".join(found.keywords) or args.query
    note = None if items else f"맞는 사내 문서를 찾지 못했습니다. 찾아본 낱말: {words}"
    return results.ok("search_documents", items, note=note, query=args.query, sources=tuple(sources))


def get_document(ctx: ToolContext, args) -> results.Execution:
    """문서 하나의 최신 본문(앞에서부터). 범위 밖 · 휴지통 · 없는 문서는 같은 `not_found` 다."""
    from app.core.errors import NotFoundError
    from app.knowledge import versions
    from app.knowledge.models import KnowledgeSpace
    from app.knowledge.service import get_scoped_document_or_404

    match = _UUID.search(args.ref or "")
    if match is None:
        return results.error("get_document", results.ERROR_NOT_FOUND)
    try:
        document = get_scoped_document_or_404(ctx.db, ctx.user, match.group(0))
    except NotFoundError:
        return results.error("get_document", results.ERROR_NOT_FOUND)
    if document.archived:
        return results.error("get_document", results.ERROR_NOT_FOUND)
    version = versions.current(ctx.db, document)
    text, truncated = _cut_text(version.body_text if version is not None else "", DOC_TEXT_CHARS)
    space = ctx.db.get(KnowledgeSpace, document.space_id) if document.space_id else None
    route = f"/knowledge/{document.id}"
    item = {
        "ref": document.id,
        "title": document.title or "(제목 없음)",
        "where": getattr(space, "name", None),
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "text": text,
        "truncated": truncated,
        "route": route,
    }
    note = "본문이 길어 앞부분만 실었습니다." if truncated else (None if text else "본문이 비어 있습니다.")
    return results.ok("get_document", [item], truncated=truncated, note=note, sources=(
        {"type": "document", "id": document.id, "title": item["title"], "route": route, "where": item["where"]},
    ))


def search_workspace(ctx: ToolContext, args) -> results.Execution:
    """통합 검색 색인에서 티켓 · 문서 · 게시글을 찾는다(낱말 OR, D-536). 사람 종류는 열지 않는다."""
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
    for group in found.get("groups") or []:
        for hit in group.get("items") or []:
            if len(items) >= LIST_LIMIT:
                break
            items.append({"kind": hit["kind"], "ref": hit["id"], "title": hit["title"],
                          "subtitle": hit.get("subtitle") or None, "route": hit.get("route") or None})
            if hit.get("route"):
                sources.append({"type": hit["kind"], "id": hit["id"], "title": hit["title"], "route": hit["route"]})
    total = int(found.get("total") or len(items))
    return results.ok("search_workspace", items, total=total, truncated=total > len(items),
                      note=None if items else "맞는 항목을 찾지 못했습니다.", query=args.query, sources=tuple(sources))


# ── 티켓 ──────────────────────────────────────────────────────────────────────────────────────────────────────

MY_VIEWS = ("assigned", "requested", "watching", "due_this_week", "overdue")


def my_work(ctx: ToolContext, args) -> results.Execution:
    """내 업무. 「맡은 것」은 「내 티켓」 화면과 같은 함수, 「요청한 것」 · 「지켜보는 것」은 범위를 건 새 목록이다."""
    from app.tickets import service as tickets
    from app.tickets.repository import PageSpec

    view = args.view
    due = {"due_this_week": "this_week", "overdue": "overdue"}.get(view)
    active = True if due else not bool(args.include_done)
    query = SimpleNamespace(due=due, sort="due_date" if due else None, order="asc" if due else None)
    page = PageSpec(offset=0, limit=LIST_LIMIT)
    if view in ("assigned", "due_this_week", "overdue"):
        filters = tickets.build_filters(ctx.db, query, now=ctx.day_now(), active_only=active)
        found = tickets.list_my_tickets(ctx.db, ctx.outbound, ctx.settings, ctx.user, filters=filters, page=page)
    else:
        filters = tickets.build_filters(ctx.db, query, now=ctx.day_now(), active_only=active, viewer=ctx.user)
        reader = tickets.list_requested_tickets if view == "requested" else tickets.list_watching_tickets
        found = reader(ctx.db, ctx.outbound, ctx.settings, ctx.user, filters=filters, page=page)
    return _ticket_list("my_work", found, note_empty="조건에 맞는 티켓이 없습니다.")


def get_ticket(ctx: ToolContext, args) -> results.Execution:
    """티켓 하나. 키나 id 를 풀고 → 범위를 확인하고 → 상세를 읽는다. 못 풀거나 범위 밖이면 같은 `not_found` 다.

    `ensure_in_scope` 에는 「행이 없으면 통과」 갈래가 있어(`app/tickets/service.py`) 못 푼 키는 그 앞에서 끝낸다.
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
    comments: list[dict] = []
    try:
        with ctx.db.begin_nested():
            listed = tickets.list_ticket_comments(ctx.db, ctx.outbound, ctx.settings, ctx.user, page_id=page_id)
        live = [c for c in (listed.get("comments") or []) if not c.get("deleted")]
        comments = [{"author": c.get("author_name") or "알 수 없는 사용자", "at": c.get("created_at"),
                     "text": (c.get("body") or "")[:COMMENT_CHARS]} for c in live[-3:]]
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
    """팀 티켓 · 미할당 티켓. 화면과 같은 두 그물(`build_filters(viewer)` + `_drop_out_of_scope`)을 건다."""
    from app.tickets import service as tickets
    from app.tickets.repository import PageSpec, ProjectVisibility

    query = SimpleNamespace(q=args.query or None, status=[args.status] if args.status else None, due=args.due,
                            sort="due_date" if args.due else None, order="asc" if args.due else None,
                            assignee_user_id=None)
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
    active = not args.status
    filters = tickets.build_filters(ctx.db, query, now=ctx.day_now(), active_only=active, viewer=ctx.user,
                                    allow_assignee_filter=args.scope == "team")
    if args.project:
        project = _find_project(ctx, args.project)
        if project is None:
            return results.error("search_tickets", results.ERROR_NOT_FOUND, "그 프로젝트를 찾지 못했습니다.")
        # 이미 범위 안에서 찾은 프로젝트로 더 좁힌다. 파이썬 그물(`_drop_out_of_scope`)은 그대로 보는 사람 기준이다.
        filters = replace(filters, project_any_of=ProjectVisibility(uids=frozenset({project.id}),
                                                                    page_ids=frozenset()))
    page = PageSpec(offset=0, limit=LIST_LIMIT)
    reader = tickets.list_team_page if args.scope == "team" else tickets.list_unassigned_page
    found = reader(ctx.db, ctx.outbound, ctx.settings, active_only=active, viewer=ctx.user, filters=filters, page=page)
    return _ticket_list("search_tickets", found, note_empty="조건에 맞는 티켓이 없습니다.", query=args.query)


# ── 프로젝트 ──────────────────────────────────────────────────────────────────────────────────────────────────


def _find_project(ctx: ToolContext, raw: str):
    """코드 · id · 이름으로 범위 안 프로젝트 하나. 여럿이면 코드나 이름이 정확히 같은 것, 그래도 여럿이면 None."""
    from app.authz.visibility import context_for_user
    from app.projects import repository as projects_repo

    text = (raw or "").strip()
    if not text:
        return None
    visible = context_for_user(ctx.db, ctx.user)
    match = _UUID.fullmatch(text)
    if match:
        from app.core.errors import NotFoundError
        from app.projects.service import get_scoped_project_or_404

        try:
            return get_scoped_project_or_404(ctx.db, text, ctx.principal)
        except NotFoundError:
            return None
    rows, _ = projects_repo.list_in_scope(ctx.db, visible, q=text, limit=5)
    if len(rows) == 1:
        return rows[0]
    exact = [p for p in rows if (p.code or "").lower() == text.lower() or (p.name or "") == text]
    return exact[0] if len(exact) == 1 else None


def _project_row(project, role: str | None = None) -> dict:
    return {
        "ref": project.id,
        "code": project.code or None,
        "name": project.name,
        "status": PROJECT_STATUS_KO.get(project.status, project.status),
        "progress_pct": project.progress_pct,
        "health_score": project.health_score,
        "my_role": PROJECT_ROLE_KO.get(role, role) if role else None,
        "route": f"/projects/{project.id}",
    }


def search_projects(ctx: ToolContext, args) -> results.Execution:
    """프로젝트 목록 - 화면과 같은 범위 함수(`list_in_scope`). 「내 것」은 구성원이거나 담당인 프로젝트로 좁힌다."""
    from sqlalchemy import select

    from app.authz.visibility import context_for_user
    from app.projects import repository as projects_repo
    from app.projects.models import ProjectMember

    visible = context_for_user(ctx.db, ctx.user)
    rows, total = projects_repo.list_in_scope(
        ctx.db, visible, q=args.query or None, status=args.status or None, trouble=bool(args.trouble_only),
        limit=LIST_LIMIT, member_user_id=ctx.user.id if args.scope == "mine" else None,
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
        "search_projects", items, total=int(total), truncated=int(total) > len(items),
        note=None if items else "조건에 맞는 프로젝트가 없습니다.", query=args.query,
        sources=tuple({"type": "project", "id": p.id, "title": p.name, "route": f"/projects/{p.id}",
                       "status": PROJECT_STATUS_KO.get(p.status, p.status)} for p in rows),
    )


def get_project_summary(ctx: ToolContext, args) -> results.Execution:
    """프로젝트 하나의 진행률(과 기준) · 건강도(와 이유). 단건 게이트(`get_scoped_project_or_404`)를 먼저 지난다."""
    from app.core.errors import NotFoundError
    from app.projects.service import get_scoped_project_or_404, project_health, project_progress

    project = _find_project(ctx, args.project)
    if project is None:
        return results.error("get_project_summary", results.ERROR_NOT_FOUND)
    try:
        project = get_scoped_project_or_404(ctx.db, project.id, ctx.principal)
    except NotFoundError:
        return results.error("get_project_summary", results.ERROR_NOT_FOUND)
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
    return results.ok("get_project_summary", [item], query=args.project, sources=(
        {"type": "project", "id": project.id, "title": project.name, "route": f"/projects/{project.id}",
         "status": item["status"]},
    ))


# ── 결재 · 사람 · 최근 변경 · 요약 ──────────────────────────────────────────────────────────────────────────────


def my_approvals(ctx: ToolContext, args) -> results.Execution:
    """내 결재함 - 화면(`/api/approvals/mine`)과 같은 함수다(`approvals.service.list_my_approvals`)."""
    from app.approvals import service as approvals
    from app.core.feature_flags import load_feature_flags

    found = approvals.list_my_approvals(
        ctx.db, ctx.user, ctx.principal, box=args.box, now=ctx.now,
        self_approval_allowed=bool(load_feature_flags(ctx.settings.config_dir).get("self_approval_allowed")),
        offset=0, limit=LIST_LIMIT,
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
        note = "해당하는 결재가 없습니다."
    return results.ok("my_approvals", items, total=found["total"], truncated=found["total"] > len(items),
                      note=note, sources=tuple(sources))


def find_people(ctx: ToolContext, args) -> results.Execution:
    """사람 찾기 - 팀 채팅 디렉터리와 같은 칸(같은 조직, 활성, 비보관). 이름 · 부서 · 직책만 나간다."""
    from app.team_chat.repository import directory_search

    people, total = directory_search(ctx.db, ctx.user, args.query, limit=LIST_LIMIT)
    items = [{"name": u.display_name, "department": u.department, "title": u.title} for u in people]
    return results.ok("find_people", items, total=total, truncated=total > len(items),
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
            route = f"/knowledge/{row['id']}"
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
