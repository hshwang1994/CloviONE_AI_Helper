"""사용자 셀프서비스 티켓 API (내 티켓 / 미할당 / 배정 후보).

조회 전용(GET)이라 CSRF 불필요(상태 미변경). 역할 게이트 없이 인증만 — 일반 사용자도 '본인 것'은
봐야 하고, notion_user_id 는 세션 사용자에서만 도출되므로 자동으로 본인 것만 보장된다(IDOR 차단).
Notion 토큰이 없으면 오류 대신 configured=false 로 돌려줘 화면이 '연동 필요'를 그리게 한다(리포트와 동일).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_current_user, get_db, require_csrf
from app.reports.notion_source import NotionNotConfiguredError, NotionQueryError
from app.tickets import service
from app.tickets.schemas import TicketCreate, TicketUpdate
from app.users.models import User

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("/mine")
def my_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        result = service.list_my_tickets(db, outbound, settings, user)
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "mapped": True, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "mapped": True, "tickets": []}
    return {"configured": True, "ok": True, **result}


@router.get("/unassigned")
def unassigned_tickets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        tickets = service.list_unassigned_tickets(db, outbound, settings)
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "tickets": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "tickets": []}
    return {"configured": True, "ok": True, "tickets": tickets}


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
    user: User = Depends(get_current_user),
):
    """편집 드롭다운용 허용 옵션(진행상태·우선순위·난이도). 작업 DB 스키마에서 읽는다."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        return {"configured": True, "ok": True, **service.ticket_meta(outbound, settings)}
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message,
                "statuses": [], "priorities": [], "difficulties": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message,
                "statuses": [], "priorities": [], "difficulties": []}


@router.get("/projects")
def projects(
    request: Request,
    user: User = Depends(get_current_user),
):
    """새 티켓 폼의 프로젝트 드롭다운 후보 [{id, name}]. 작업 DB 스키마에서 자동 발견."""
    settings = request.app.state.settings
    outbound = request.app.state.outbound_client
    try:
        return {"configured": True, "ok": True, "projects": service.list_projects(outbound, settings)}
    except NotionNotConfiguredError as exc:
        return {"configured": False, "ok": False, "message": exc.message, "projects": []}
    except NotionQueryError as exc:
        return {"configured": True, "ok": False, "error": exc.message, "projects": []}


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
    result = service.create_ticket(db, outbound, settings, user, payload=payload)
    record_audit_from_request(
        request, db, action="ticket.create", object_type="notion_task",
        object_id=result["ticket"].get("id"), after=result["after"],
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
    result = service.update_ticket(db, outbound, settings, user, page_id=page_id, changes=changes)
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
    result = service.claim_ticket(db, outbound, settings, user, page_id=page_id)
    record_audit_from_request(
        request, db, action="ticket.claim", object_type="notion_task",
        object_id=page_id, before=result["before"], after=result["after"],
    )
    return {"configured": True, "ok": True, "ticket": result["ticket"]}
