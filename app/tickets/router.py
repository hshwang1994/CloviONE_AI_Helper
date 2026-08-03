"""사용자 셀프서비스 티켓 API (내 티켓 / 미할당 / 팀 / 생성·편집).

조회 전용(GET)이라 CSRF 불필요(상태 미변경). 역할 게이트 없이 인증만 — 일반 사용자도 '본인 것'은
봐야 하고, 대상 소스 user id 는 세션 사용자에서만 도출되므로 자동으로 본인 것만 보장된다(IDOR 차단).
소스 토큰이 없으면 오류 대신 configured=false 로 돌려줘 화면이 '연동 필요'를 그리게 한다(리포트와 동일).

목록이 로컬 미러에서 나온 경우에만 `sync` 블록(신선도)을 함께 싣는다 — 실시간으로 답한 응답에
미러 상태를 실으면 거짓말이고, 실시간 경로의 기존 응답 계약도 그대로 유지된다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.observability.service import EVENT_TICKET_CREATE, record_usage
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import NotionNotConfiguredError, NotionQueryError
from app.tickets import service
from app.tickets.schemas import (
    BulkPageIds,
    TicketBodyUpdate,
    TicketCommentCreate,
    TicketCommentUpdate,
    TicketCreate,
    TicketUpdate,
)
from app.users.models import User

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _repo(request: Request):
    """앱 기동 때 배선된 저장소(app.state.repositories.tickets)."""
    return request.app.state.repositories.tickets


def _with_sync(db: Session, repo, body: dict) -> dict:
    """미러로 답했으면 신선도 블록을 덧붙인다(실시간이면 키 자체가 없다)."""
    sync = service.sync_indicator(db, repo=repo)
    return {**body, "sync": sync} if sync else body


@router.get("/mine")
def my_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    repo = _repo(request)
    try:
        result = service.list_my_tickets(db, outbound, settings, user, repo=repo)
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "mapped": True, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "mapped": True, "tickets": []}
    return _with_sync(db, repo, {"configured": True, "ok": True, **result})


@router.get("/unassigned")
def unassigned_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    repo = _repo(request)
    try:
        tickets = service.list_unassigned_tickets(db, outbound, settings, repo=repo)
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "tickets": []}
    return _with_sync(db, repo, {"configured": True, "ok": True, "tickets": tickets})


@router.get("/assignees")
def assignees(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """담당자 배정 드롭다운용 후보 목록(active + verified 매핑 사용자)."""
    return {"assignees": service.list_assignees(db)}


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
    """새 티켓 폼의 프로젝트 드롭다운 후보 [{id, name}]. 로컬 메타 캐시 우선."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        return {"configured": True, "ok": True,
                "projects": service.list_projects(outbound, settings, db, repo=_repo(request))}
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "projects": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "projects": []}


@router.get("/team")
def team_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    active: bool = Query(default=True),
):
    """팀 전체 티켓(다른 사람 것 포함) — 조회 전용. 리터럴 경로라 GET /{page_id} 보다 먼저 선언."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    repo = _repo(request)
    try:
        tickets = service.list_team_tickets(db, outbound, settings, active_only=active, repo=repo)
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "tickets": []}
    return _with_sync(db, repo, {"configured": True, "ok": True, "tickets": tickets})


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
    )
    record_audit_from_request(
        request, db, action="ticket.body.update", object_type="notion_task",
        object_id=page_id, after={"synced": result["synced"]},
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
