"""사용자 셀프서비스 티켓 API (내 티켓 / 미할당 / 팀 / 생성·편집).

조회 전용(GET)이라 CSRF 불필요(상태 미변경). 역할 게이트 없이 인증만 — 일반 사용자도 '본인 것'은
봐야 하고, 대상 소스 user id 는 세션 사용자에서만 도출되므로 자동으로 본인 것만 보장된다(IDOR 차단).
소스 토큰이 없으면 오류 대신 configured=false 로 돌려줘 화면이 '연동 필요'를 그리게 한다(리포트와 동일).

목록이 로컬 미러에서 나온 경우에만 `sync` 블록(신선도)을 함께 싣는다 — 실시간으로 답한 응답에
미러 상태를 실으면 거짓말이고, 실시간 경로의 기존 응답 계약도 그대로 유지된다.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.org import context as org_context
from app.core.audit import audit_failure_on_exception, record_audit_from_request
from app.observability.service import EVENT_TICKET_CREATE, record_usage
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    NotionNotConfiguredError,
    NotionQueryError,
)
from app.core.pagination import PageParams
from app.core.uploads import content_disposition, MAX_UPLOAD_BYTES
from app.tickets import attachments as ticket_attachments
from app.tickets import service
from app.tickets.repository import PageSpec
from app.tickets.sync import sync_tickets
from app.tickets.schemas import (
    BulkPageIds,
    TicketBodyUpdate,
    TicketCommentCreate,
    TicketCommentUpdate,
    TicketCreate,
    TicketListQuery,
    TicketUpdate,
)
from app.users.models import User
from app.settings.gate import block_if_maintenance

router = APIRouter(
    prefix="/api/tickets",
    tags=["tickets"],
    dependencies=[Depends(block_if_maintenance)],
)

# 수동 재동기화(C7)를 **한 번에 하나만** 진행한다. `app/tickets/claim_lock.py` 의
# `claim_guard` 와 같은 이유(웹이 `--workers 1` 로 고정돼 있어 프로세스 안 잠금으로 충분,
# 워커를 늘리려면 공유 저장소로 바꿔야 한다)로 여기서도 기다리지 않는 논블로킹 잠금을 쓴다.
#
# **못 막는 것**: 워커 프로세스(app/worker_main.py)가 따로 도는 정기 동기화 틱은 이 잠금과
# 다른 프로세스라 못 막는다. 그 경합은 `sync_tickets` 자신의 예외 격리(전부 가둬서 상태에만
# error 로 남긴다)가 이미 다루므로 크래시로 번지지 않는다 — 여기서 막는 것은 운영자가 이
# 버튼을 신경질적으로 여러 번 누르는 경우다.
_ticket_sync_lock = threading.Lock()


def _sync_view(state) -> dict:
    """`team_docs.router._sync_view` 와 같은 모양(§17 신선도 블록과 응답 계약을 맞춘다)."""
    return {
        "status": state.status,
        "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
        "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
        "ticket_count": state.ticket_count,
        "truncated": state.truncated,
        "error": state.error,
    }


def _repo(request: Request):
    """앱 기동 때 배선된 저장소(app.state.repositories.tickets)."""
    return request.app.state.repositories.tickets


def _with_sync(db: Session, repo, body: dict) -> dict:
    """미러로 답했으면 신선도 블록을 덧붙인다(실시간이면 키 자체가 없다)."""
    sync = service.sync_indicator(db, repo=repo)
    return {**body, "sync": sync} if sync else body


def _paged(tickets: list[dict], total: int, page: PageParams) -> dict:
    """목록 응답의 페이지 봉투.

    `items` 는 저장소 관용(`{items,total,page,page_size}`)이고 `tickets` 는 **이미 나가 있는
    화면과의 호환용 별칭**이다. 같은 목록을 두 이름으로 싣는 이유는 하나뿐이다: 이 변경은
    백엔드 범위라 화면을 같이 못 고친다. 화면이 `items` 로 옮겨 가면 `tickets` 를 뺀다.

    total 은 **필터를 다 건 뒤, 자르기 전** 건수다 — 화면이 "N건 중 1-20" 을 쓸 수 있어야
    하고, 그 N 이 필터 앞의 수라면 사용자가 세는 것과 다른 말을 하게 된다.
    """
    return {
        "items": tickets,
        "tickets": tickets,
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


def _page_spec(page: PageParams) -> PageSpec:
    return PageSpec(offset=page.offset, limit=page.page_size)


@router.get("/mine")
def my_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: PageParams = Depends(),
    query: TicketListQuery = Depends(),
):
    """내가 담당한 티켓 한 페이지. 필터는 **서버가** 건다.

    `assignee_user_id` 는 이 경로에서 뜻이 없다 — 이 목록의 담당자는 언제나 세션 사용자다
    (그래야 IDOR 이 원천적으로 불가능하다). 나머지 조건은 다른 목록과 똑같이 걸린다.
    """
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    repo = _repo(request)
    try:
        result = service.list_my_tickets(
            db, outbound, settings, user, repo=repo,
            filters=service.build_filters(
                db, query, now=request.app.state.clock.now(),
                allow_assignee_filter=False,
            ),
            page=_page_spec(page),
        )
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "mapped": True, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "mapped": True, "tickets": []}
    return _with_sync(db, repo, {
        "configured": True, "ok": True, "mapped": result["mapped"],
        **_paged(result["tickets"], result["total"], page),
    })


@router.get("/unassigned")
def unassigned_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: PageParams = Depends(),
    query: TicketListQuery = Depends(),
):
    """미할당 트리아지 한 페이지 — **담당자가 아무도 없는** 티켓.

    `assignee_user_id` 는 여기서 뜻이 없다(정의상 담당자가 없다). 범위는 팀 티켓과 같은
    방식으로 질의에서 걸린다(`viewer` → 볼 수 있는 프로젝트).
    """
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    repo = _repo(request)
    try:
        result = service.list_unassigned_page(
            db, outbound, settings, repo=repo, viewer=user,
            filters=service.build_filters(
                db, query, now=request.app.state.clock.now(), active_only=True,
                allow_assignee_filter=False, viewer=user,
            ),
            page=_page_spec(page),
        )
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "tickets": []}
    return _with_sync(db, repo, {
        "configured": True, "ok": True,
        **_paged(result["tickets"], result["total"], page),
    })


@router.get("/assignees")
def assignees(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
):
    """담당자 배정 드롭다운용 후보 목록(active + verified 매핑 사용자).

    `project_id`(Portal 프로젝트 id)를 주면 **그 프로젝트에 닿을 수 있는 사람만** 나온다 —
    담당자와 프로젝트 ACL 이 어긋나 "내가 담당인데 내 티켓이 안 보인다" 가 되지 않게 한다.
    """
    return {
        "assignees": service.list_assignees(
            db, org_id=getattr(user, "org_id", None), project_id=project_id
        )
    }


@router.get("/meta")
def meta(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """편집 드롭다운용 허용 옵션(진행상태·우선순위·난이도). 로컬 메타 캐시 우선."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        return {"configured": True, "ok": True,
                **service.ticket_meta(outbound, settings, db, repo=_repo(request))}
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message,
                "statuses": [], "priorities": [], "difficulties": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message,
                "statuses": [], "priorities": [], "difficulties": []}


@router.get("/projects")
def projects(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """새 티켓 폼의 프로젝트 드롭다운 — **범위 안 Portal 프로젝트**(0060).

    외부 소스에 묻지 않으므로 그쪽 장애와 무관하다. 예전에는 Notion relation 목록을 그대로
    내려 줘서 ① 다른 부서 프로젝트 이름이 전부 보이고 ② 외부 키가 브라우저로 나갔다.
    """
    return {
        "configured": True, "ok": True,
        "projects": service.list_projects(db, user),
    }


@router.get("/team")
def team_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    active: bool = Query(default=True),
    page: PageParams = Depends(),
    query: TicketListQuery = Depends(),
    # 부서 필터 (0060 §32). 조회 범위 **안에서만** 좁힌다 — 범위 밖 id 는 404 다.
    department_id: str | None = Query(default=None, max_length=36),
):
    """팀 티켓 한 페이지(다른 사람 것 포함) — 조회 전용. 리터럴 경로라 GET /{page_id} 보다 먼저 선언.

    **범위는 질의에서 걸린다**: `build_filters(viewer=user)` 가 이 사람이 볼 수 있는
    프로젝트 집합을 `project_any_of` 로 옮겨 담고, `list_team_page` 가 파이썬 그물
    (`_drop_out_of_scope`)을 한 번 더 건다. 범위를 페이지 뒤에서만 걸면 남의 팀 티켓이
    자리만 차지하고 빠진, 20건을 달랬는데 3건이 오는 페이지가 나간다.
    """
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    repo = _repo(request)
    try:
        # `viewer` 를 넘겨 **보는 사람의 팀**으로 좁힌다. 예전에는 포탈 전체가 나갔다.
        picked = org_context.filter_scope(db, user, department_id)
        result = service.list_team_page(
            db, outbound, settings, active_only=active, repo=repo, viewer=user,
            filters=service.build_filters(
                db, query, now=request.app.state.clock.now(),
                active_only=active, viewer=user, scope=picked,
            ),
            page=_page_spec(page), scope=picked,
        )
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "tickets": []}
    return _with_sync(db, repo, {
        "configured": True, "ok": True,
        "can_sync": service.can_trigger_sync(user),
        # 고를 수 있는 부서는 서버가 계산한다 — 프런트가 만들면 서버 검증과 갈라진다.
        "departments": {
            "selected": department_id,
            "options": org_context.department_options(db, user),
        },
        **_paged(result["tickets"], result["total"], page),
    })


@router.post("", dependencies=[Depends(require_csrf)])
def create(
    request: Request,
    payload: TicketCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """새 티켓을 폼으로 생성한다(채팅 없이). 제목 필수 + 스키마/옵션 검증 + 감사."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    result = service.create_ticket(
        db, outbound, settings, user, payload=payload,
        now=request.app.state.clock.now(), repo=_repo(request),
    )
    record_audit_from_request(
        request, db, action="ticket.create", object_type="notion_task",
        object_id=result["ticket"].get("id"), after=result["after"],
    )
    # 사용 통계(0026) — 저빈도 지점. 티켓 '조회'가 아니라 '생성'에만 건다.
    record_usage(
        db, event=EVENT_TICKET_CREATE, user_id=user.id,
        org_id=getattr(user, "org_id", None),
        object_type="notion_task", object_id=result["ticket"].get("id"),
        now=request.app.state.clock.now(),
    )
    return {"configured": True, "ok": True, "ticket": result["ticket"]}


@router.patch("/{page_id}", dependencies=[Depends(require_csrf)])
def update_ticket(
    request: Request,
    page_id: str,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """티켓 수동 편집(담당자·예상 WD·난이도·우선순위·진행상태·마감). 소유권·스키마 검증 + 감사.

    보낸 필드만 바꾼다(exclude_unset). 소유권/검증 실패는 표준 오류(403/422/404)로 던진다 —
    프런트가 메시지를 토스트로 보여준다. 성공한 쓰기만 감사에 남긴다(실패는 get_db 롤백으로
    같은 트랜잭션의 감사도 되돌려져 남지 않는다 — 다른 라우터와 동일하게 성공만 기록).
    """
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    changes = payload.model_dump(exclude_unset=True)
    result = service.update_ticket(
        db, outbound, settings, user, page_id=page_id, changes=changes,
        now=request.app.state.clock.now(), repo=_repo(request),
    )
    record_audit_from_request(
        request, db, action="ticket.update", object_type="notion_task",
        object_id=page_id, before=result["before"], after=result["after"],
    )
    return {"configured": True, "ok": True, "ticket": result["ticket"]}


@router.post("/{page_id}/claim", dependencies=[Depends(require_csrf)])
def claim_ticket(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """미할당(또는 본인 담당) 티켓의 담당자로 '나'를 배정한다."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    result = service.claim_ticket(
        db, outbound, settings, user, page_id=page_id,
        now=request.app.state.clock.now(), repo=_repo(request),
    )
    record_audit_from_request(
        request, db, action="ticket.claim", object_type="notion_task",
        object_id=page_id, before=result["before"], after=result["after"],
    )
    return {"configured": True, "ok": True, "ticket": result["ticket"]}


@router.post("/trash-bulk", dependencies=[Depends(require_csrf)])
def trash_tickets_bulk(
    request: Request,
    payload: BulkPageIds,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """티켓 여러 건을 한 번에 휴지통으로(목록 다중선택). 건별 권한 검사, 부분 성공.
    (리터럴 경로라 아래 GET /{page_id} 보다 먼저 선언 — id 로 잡히지 않게.)"""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    result = service.trash_tickets_bulk(db, outbound, settings, user,
                                        page_ids=payload.page_ids,
                                        now=request.app.state.clock.now(), repo=_repo(request))
    for it in result["trashed"]:
        record_audit_from_request(request, db, action="ticket.trash", object_type="notion_task",
                                  object_id=it["id"], before={"title": it.get("title")})
    return {"ok": True, **result}


# ── 강제 재동기화 (C7) ────────────────────────────────────────────────────────
# team_docs 의 POST /api/team-docs/sync 와 같은 패턴: 운영자 권한 확인(같은 기준,
# service.can_trigger_sync = MODERATOR_ROLES) → app/tickets/sync.py 의 동기화 함수 호출 →
# 감사 로그. 지금까지 이 버튼이 없어서 Notion 쪽 데이터가 깨졌다 복구돼도 다음 정기
# 동기화 주기(워커 틱)까지 기다리는 것 말고는 방법이 없었다.

@router.post("/sync", dependencies=[Depends(require_csrf)])
def trigger_sync(
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if not service.can_trigger_sync(me):
        raise ForbiddenError("티켓 동기화는 운영자만 실행할 수 있습니다.")
    if not _ticket_sync_lock.acquire(blocking=False):
        # 기다리지 않는다 — `claim_guard` 와 같은 이유. Notion 이 느린 날 요청이 쌓여
        # 요청 스레드가 잠기는 것보다 "지금은 안 된다" 를 바로 알려 주는 편이 낫다.
        raise ConflictError("이미 티켓 동기화가 진행 중입니다. 잠시 후 다시 시도해 주세요.")
    try:
        state = sync_tickets(
            db,
            outbound=request.app.state.outbound_client,
            settings=request.app.state.settings,
            now=request.app.state.clock.now(),
        )
    finally:
        _ticket_sync_lock.release()
    record_audit_from_request(
        request,
        db,
        action="ticket.sync",
        object_type="ticket_sync",
        object_id="tickets",
        after={"status": state.status, "ticket_count": state.ticket_count},
    )
    return {"sync": _sync_view(state)}


# ── 댓글 ──────────────────────────────────────────────────────────────────────
# 리터럴 세그먼트가 두 개라 아래 GET /{page_id} 와 겹치지 않는다(경로 파라미터는 '/' 를 먹지
# 않는다). 그래도 읽는 순서상 여기에 모아 둔다.

@router.patch("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def update_comment(
    request: Request,
    comment_id: str,
    payload: TicketCommentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """댓글 수정 — **작성자 본인만**(운영자 우회 없음). 남의 문장을 고쳐 쓸 수는 없다."""
    result = service.edit_ticket_comment(
        db, user, comment_id=comment_id, body=payload.body,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="ticket.comment.update", object_type="ticket_comment",
        object_id=comment_id,
    )
    return {"ok": True, **result}


@router.delete("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def delete_comment(
    request: Request,
    comment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """댓글 삭제 — 작성자 본인 또는 운영자군. soft-delete 이고, 목록에는 툼스톤으로 남는다."""
    result = service.delete_ticket_comment(
        db, user, comment_id=comment_id, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="ticket.comment.delete", object_type="ticket_comment",
        object_id=comment_id,
    )
    return {"ok": True, **result}


@router.get("/{page_id}/comments")
def list_comments(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """티켓 댓글 목록(삭제된 것은 본문 없는 툼스톤). 외부 왕복 없음 — 우리 표만 읽는다."""
    return {"ok": True, **service.list_ticket_comments(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        page_id=page_id, repo=_repo(request),
    )}


@router.post("/{page_id}/comments", dependencies=[Depends(require_csrf)])
def create_comment(
    request: Request,
    page_id: str,
    payload: TicketCommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """댓글 작성 — 로그인한 누구나(티켓 자체가 팀 전체 조회 대상이다)."""
    result = service.add_ticket_comment(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        page_id=page_id, body=payload.body,
        now=request.app.state.clock.now(), repo=_repo(request),
    )
    record_audit_from_request(
        request, db, action="ticket.comment.create", object_type="ticket_comment",
        object_id=result["comment_id"], after={"ticket_page_id": page_id},
    )
    return {"ok": True, **result}


# ── 본문 편집 ─────────────────────────────────────────────────────────────────

@router.put("/{page_id}/body", dependencies=[Depends(require_csrf)])
def save_body(
    request: Request,
    page_id: str,
    payload: TicketBodyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """티켓 본문 저장. 정본(우리 DB)을 먼저 쓰고 그다음 원본(Notion)에 밀어 넣는다.

    **원본 push 실패는 500 이 아니다.** 사용자가 친 글은 이미 저장돼 있으므로 오류로 던지면
    (요청 트랜잭션이 롤백돼) 오히려 그 글이 사라진다. 그래서 `ok: true` + `synced: false` +
    이유를 함께 돌려주고, 화면이 "저장됨 · 원본 동기화 실패 · 재시도"를 그린다.
    """
    result = service.save_ticket_body(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        page_id=page_id, body_markdown=payload.body_markdown,
        now=request.app.state.clock.now(), repo=_repo(request),
        base_version=payload.base_version,   # 낙관적 잠금 (Z2)
    )
    record_audit_from_request(
        request, db, action="ticket.body.update", object_type="notion_task",
        object_id=page_id, after={"synced": result["synced"]},
    )
    return {"ok": True, **result}


# ── 첨부 (지시서 §4: 티켓에 붙은 이미지를 이 화면에서 바로 본다) ─────────────────
# 리터럴 경로("/attachments/...")를 경로 파라미터("/{page_id}")보다 먼저 선언한다 —
# 순서가 뒤바뀌면 page_id="attachments" 로 잡혀 404 조차 아닌 이상한 오류가 난다.

def _ensure_attachment_ticket_visible(db: Session, att, user: User) -> None:
    """첨부가 붙은 **티켓**에 상세와 똑같은 판정을 건다.

    상세(`service.ticket_detail`)와 댓글 목록이 부르는 그 함수를 그대로 부른다. 조건을 여기서
    다시 쓰면 언젠가 한쪽만 고쳐져 "상세는 404 인데 첨부 원본은 그대로 나간다"가 되는데,
    이 라우트가 정확히 그 상태였다 — 판정은 한 곳에만 둔다.

    page id 해석은 `service._page_id_for_uid` 를 쓴다(삭제 경로가 이미 쓰는 그 함수다).
    같은 매핑을 라우터가 한 벌 더 갖고 있으면 source='native' 가 들어오는 날 한쪽만 고쳐진다.

    **page id 가 없는 티켓(source='native')은 통과시킨다.** 판정할 근거가 없는 것이지 범위
    밖인 것이 아니다 — `ensure_in_scope` 가 캐시 행이 없을 때 통과시키는 것과 같은 이유다.
    """
    page_id = service._page_id_for_uid(db, att.ticket_uid)
    if page_id is None:
        return
    service.ensure_not_trashed(db, page_id)   # H2 — 지운 티켓의 첨부는 없는 것으로 본다
    service.ensure_in_scope(db, page_id, user)   # 범위 밖은 404


@router.get("/attachments/{attachment_id}")
def serve_ticket_attachment(
    request: Request,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """첨부 원본. **상세와 같은 판정을 지난 사람에게만** 바이트를 준다.

    예전 주석은 "로그인한 사람이면 볼 수 있다"였고 근거는 "티켓 자체가 팀 전체 조회 대상"
    이라는 전제였다. **그 전제는 이제 거짓이다** — RBAC 작업으로 `ticket_detail` 과
    `list_ticket_comments` 에 `ensure_in_scope` 가 들어가 남의 부서 티켓은 404 가 됐는데,
    첨부 원본만 열려 있었다. 상세가 404 인 티켓의 이미지·규격서를 id 하나로 받아 갈 수
    있으면 상세를 막은 의미가 없다(첨부 URL 은 화면에 그대로 노출되는 값이다).

    **언제 통과시키나**: 담당자를 앱 사용자로 해석할 수 없는 티켓은 그대로 열린다. 그런
    티켓은 미할당 트리아지에 뜨므로, 첨부만 막으면 목록에는 보이는데 못 여는 화면이 된다 —
    그건 보안이 아니라 고장이다. 그 결합은 `ensure_in_scope` 가 갖고 있고 여기서 다시 쓰지
    않는다(→ `_ensure_attachment_ticket_visible`).

    없는 첨부·파일 없음·범위 밖·휴지통은 전부 404 다(403 은 "그런 첨부가 있긴 하다"를
    알려 준다)."""
    att = ticket_attachments.get_attachment(db, attachment_id)
    if att is None:
        raise NotFoundError("첨부를 찾을 수 없습니다.")
    # 바이트를 만들기 **전에** 판정한다 — 경로만 계산해도 새는 것은 없지만, 순서가 뒤집히면
    # 다음 사람이 그 사이에 응답을 만들어 넣는다.
    _ensure_attachment_ticket_visible(db, att, user)
    path = ticket_attachments.file_path(request.app.state.settings.data_dir, att)
    if path is None:
        raise NotFoundError("첨부 파일을 찾을 수 없습니다.")
    # nosniff + inline. 서버가 판정·저장한 media_type 만 신뢰한다. 실행 불가.
    return FileResponse(
        str(path),
        media_type=att.media_type,
        headers={
            "Content-Disposition": content_disposition(att.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete("/attachments/{attachment_id}", dependencies=[Depends(require_csrf)])
def delete_ticket_attachment(
    request: Request,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """첨부 제거 — 올린 사람 본인이거나 티켓을 편집할 수 있는 사람. 범위 밖은 404.

    범위 판정을 서비스에만 맡기면 구멍이 하나 남는다: `delete_ticket_attachment` 는
    **올린 사람 본인이면 티켓을 아예 보지 않고** 지운다(그 분기에 `ensure_in_scope` 가 없다).
    미할당일 때 붙인 첨부가 나중에 남의 부서로 배정되면, 읽기는 404 인데 삭제는 되는 상태가
    된다 — 못 보는 티켓을 고치는 셈이다. 그래서 읽기와 **같은 판정을 같은 자리에서** 먼저
    건다(→ `_ensure_attachment_ticket_visible`).
    """
    att = ticket_attachments.get_attachment(db, attachment_id)
    if att is None:
        raise NotFoundError("첨부를 찾을 수 없습니다.")
    _ensure_attachment_ticket_visible(db, att, user)
    result = service.delete_ticket_attachment(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        attachment_id=attachment_id, repo=_repo(request),
    )
    record_audit_from_request(
        request, db, action="ticket.attachment.delete", object_type="ticket_attachment",
        object_id=attachment_id,
    )
    return {"ok": True, **result}


@router.post("/{page_id}/attachments", dependencies=[Depends(require_csrf)])
def upload_ticket_attachment(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    """티켓에 이미지·PDF 를 붙인다(편집 권한 필요).

    sync 핸들러라 UploadFile 의 내부 파일 객체를 직접 읽는다(await 불필요, 불변 §1).
    상한보다 1바이트 더 읽는 이유: 정확히 상한인 파일과 넘는 파일을 구분해야 한다.
    """
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    with audit_failure_on_exception(
        request, db, action="ticket.attachment.upload", object_type="ticket_attachment",
        after={"ticket_page_id": page_id},
    ):
        result = service.add_ticket_attachment(
            db, request.app.state.outbound_client, request.app.state.settings, user,
            page_id=page_id, data_dir=request.app.state.settings.data_dir,
            filename=file.filename or "file", content=content,
            now=request.app.state.clock.now(), repo=_repo(request),
        )
    record_audit_from_request(
        request, db, action="ticket.attachment.upload", object_type="ticket_attachment",
        object_id=result["attachment_id"], after={"ticket_page_id": page_id},
    )
    return {"ok": True, **result}


@router.get("/{page_id}")
def ticket_detail(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """티켓 단건 상세(속성 + 본문 블록) — 우리 화면에서 읽고 '원본 열기'로 노션에 간다.
    (리터럴 GET 라우트들이 위에 먼저 선언돼 있어 이 경로 파라미터가 그것들을 가리지 않는다.)"""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        result = service.ticket_detail(db, outbound, settings, user, page_id=page_id,
                                       repo=_repo(request))
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message}
    return {"configured": True, "ok": True, **result}


@router.post("/{page_id}/trash", dependencies=[Depends(require_csrf)])
def trash_ticket(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """티켓을 휴지통으로 보낸다(노션 원본은 보관기간 뒤 삭제). 편집 권한 필요 + 감사."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    result = service.trash_ticket(db, outbound, settings, user, page_id=page_id,
                                  now=request.app.state.clock.now(), repo=_repo(request))
    record_audit_from_request(
        request, db, action="ticket.trash", object_type="notion_task",
        object_id=page_id, before={"title": result["title"]},
    )
    return {"ok": True}
