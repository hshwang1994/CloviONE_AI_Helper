"""Work Domain API — 판 · 백로그 · 스프린트 · 관계 · 이름 · 예외.

## 권한은 역할이 아니라 권한으로 묻는다

S5 가 `require_permission` 을 만든 이유가 여기서 그대로 쓰인다. 상태를 옮기는 것은
`TICKET_TRANSITION`, 프로젝트 Key 를 정하는 것은 `PROJECT_ADMIN` 이다 — 새 역할이
생겨도 이 파일은 안 고친다.

**다만 권한만으로는 부족하다.** 「무엇을 할 수 있는가」와 「어느 것에 할 수 있는가」는
다른 질문이고, 뒤쪽은 서비스가 `effective_visibility_clause` 로 답한다(D-194).
게이트만 걸고 범위를 안 걸면 권한 있는 사람이 남의 부서 티켓을 옮길 수 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.deps import get_current_user, get_db, require_csrf, require_permission
from app.core.dates import parse_date
from app.core.errors import NotFoundError, ValidationAppError
from app.home.service import local_today
from app.settings.gate import block_if_maintenance
from app.tickets import service as tickets_service
from app.users.models import User
from app.work import relations as relations_mod
from app.work import meeting, service, triage, workflow
from app.work.models import MigrationException, TicketStatus
from app.work.resolve import resolve
from app.work.schemas import (
    BoardMove,
    DecisionCreate,
    DecisionUpdate,
    ExceptionAssign,
    RelationCreate,
    SprintClose,
    SprintCreate,
    SprintState,
    WatchToggle,
)

router = APIRouter(
    prefix="/api/work",
    tags=["work"],
    dependencies=[Depends(block_if_maintenance)],
)


def _repo(request: Request):
    return request.app.state.repositories.tickets


# ── 상태 어휘 ────────────────────────────────────────────────────────────────


@router.get("/statuses")
def list_statuses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """상태 어휘. **앱이 소유한다** — 예전에는 외부 스키마 조회에서 왔다.

    폼 드롭다운과 칸반 열이 **같은 표**를 본다(`ticket_statuses`). 두 화면이 서로 다른
    곳에서 어휘를 받으면 언젠가 한쪽에만 있는 상태가 생기고, 그 상태의 티켓은 판에
    안 나타난다.

    어휘의 정본은 코드(`app/work/workflow.py::STATUSES`)이고 이 표는 그 결과다 —
    런타임이 표를 읽는 것은 S5 의 `effective_permissions` 와 같은 배치다.
    """
    rows = db.execute(
        select(TicketStatus).order_by(TicketStatus.sort_order, TicketStatus.key)
    ).scalars().all()
    return {
        "statuses": [
            {
                "key": r.key, "label": r.label, "category": r.category,
                "sort_order": r.sort_order, "is_default": bool(r.is_default),
                "terminal": workflow.is_terminal(r.key),
                # 판에서 어디에 서는가 — 열인가, 접힌 칸인가, 숨는가 (D-349). 화면이
                # 상태 이름을 적어 자리를 고르면 어휘가 바뀐 날 그 화면만 옛 목록으로
                # 남는다. 폼 드롭다운은 이 값을 안 본다 — 여섯 전부를 고를 수 있다.
                "board": workflow.board_placement(r.key),
            }
            for r in rows
        ],
        "categories": list(workflow.CATEGORIES),
        "default": next((r.key for r in rows if r.is_default), workflow.DEFAULT_STATUS),
    }


# ── 판과 백로그 ──────────────────────────────────────────────────────────────


def _resolve_assignee_token(
    db: Session, user: User, *, mine: bool, assignee_user_id: str | None
) -> str | None:
    """담당자는 **앱 user_id** 로 받는다. 브라우저는 원본 소스 토큰을 절대 모른다
    (§12.3) — 해석은 서버가 한다. 판·백로그·이동 위치 계산 셋이 같은 규칙을 쓴다."""
    if mine:
        return tickets_service.assignee_token(db, user)
    if assignee_user_id:
        return tickets_service.assignee_token_for_user(db, assignee_user_id)
    return None


@router.get("/board")
def get_board(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
    sprint_id: str | None = Query(default=None, max_length=36),
    # 담당자는 **앱 user_id** 로 받는다. 브라우저는 원본 소스 토큰을 절대 모른다(§12.3) —
    # 해석은 서버가 한다.
    assignee_user_id: str | None = Query(default=None, max_length=36),
    mine: bool = Query(default=False),
    blocked_only: bool = Query(default=False),
    # §8.1 — 회차 미선택 기본은 execution(종료 상태 제외). all 은 명시할 때만.
    scope: str | None = Query(default=None, pattern="^(sprint|execution|all)$"),
    # §8.5 — 열 하나가 첫 쪽에 싣는 카드 수. 나머지는 /board/columns/{status_key} 가 잇는다.
    column_page_size: int = Query(default=service.DEFAULT_COLUMN_PAGE_SIZE, ge=1, le=service.MAX_COLUMN_PAGE_SIZE),
) -> dict:
    """칸반 한 판. 「내 티켓만」은 담당자 필터의 특수한 경우라 같은 축으로 접는다.

    「지연」의 기준일은 서버가 정한다(§불변 9) — 화면이 브라우저에서 오늘을 구하면
    KST 09:00 이전에 하루 밀린 건수를 요약 줄에 그린다.
    """
    token = _resolve_assignee_token(db, user, mine=mine, assignee_user_id=assignee_user_id)
    return service.board(
        db, user,
        project_id=project_id, sprint_id=sprint_id, scope=scope,
        assignee_token=token, blocked_only=blocked_only,
        column_page_size=column_page_size,
        today=local_today(request.app.state.settings, request.app.state.clock.now()),
    )


@router.get("/board/columns/{status_key}")
def get_board_column(
    status_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
    sprint_id: str | None = Query(default=None, max_length=36),
    assignee_user_id: str | None = Query(default=None, max_length=36),
    mine: bool = Query(default=False),
    blocked_only: bool = Query(default=False),
    scope: str | None = Query(default=None, pattern="^(sprint|execution|all)$"),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=service.DEFAULT_COLUMN_PAGE_SIZE, ge=1, le=service.MAX_COLUMN_PAGE_SIZE),
) -> dict:
    """판의 열 하나 — **다음 쪽**(§8.5). `GET /board` 와 같은 조건을 받는다 — 조건이
    어긋나면 이 쪽에서 다른 카드가 새거나 겹친다.

    🔴 「N건 중 앞 200건만 보여 줍니다」로 끝내지 않는다 — 커서를 끝까지 따라가면
    `total` 과 정확히 같은 수의 카드를 받는다(중복 0 · 누락 0).
    """
    token = _resolve_assignee_token(db, user, mine=mine, assignee_user_id=assignee_user_id)
    return service.board_column(
        db, user,
        status_key=status_key,
        project_id=project_id, sprint_id=sprint_id, scope=scope,
        assignee_token=token, blocked_only=blocked_only,
        cursor=cursor, limit=limit,
    )


@router.get("/backlog")
def get_backlog(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
    q: str | None = Query(default=None, max_length=200),
    assignee_user_id: str | None = Query(default=None, max_length=36),
    mine: bool = Query(default=False),
    priority: str | None = Query(default=None, max_length=64),
    difficulty: str | None = Query(default=None, max_length=64),
    # §8.5 — 181행을 한 번에 받던 것을 커서로 잇는다.
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=service.DEFAULT_COLUMN_PAGE_SIZE, ge=1, le=service.MAX_COLUMN_PAGE_SIZE),
) -> dict:
    """백로그 — 아직 어느 회차에도 안 담긴 일. 조건은 판과 **같은 이름**을 쓴다."""
    token = _resolve_assignee_token(db, user, mine=mine, assignee_user_id=assignee_user_id)
    return service.backlog(
        db, user,
        project_id=project_id, q=q, assignee_token=token,
        priority=priority, difficulty=difficulty,
        cursor=cursor, limit=limit,
    )


@router.post("/board/{ticket_id}/move", dependencies=[Depends(require_csrf)])
def move_card(
    ticket_id: str,
    payload: BoardMove,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("TICKET_TRANSITION", "TICKET_UPDATE")),
) -> dict:
    """카드 한 장을 옮긴다 — 상태·활동·감사·`updated_at`·알림이 **한 트랜잭션**이다.

    감사는 서비스가 남긴다(`request` 를 넘긴다) — 라우터에서 따로 남기면 서비스가
    거절한 요청에도 기록이 생긴다.
    """
    position_token = _resolve_assignee_token(
        db, user, mine=payload.position_mine, assignee_user_id=payload.position_assignee_user_id,
    )
    return service.move(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        ticket_id=ticket_id,
        to_status=payload.to_status,
        sprint_id=payload.sprint_id,
        set_sprint=payload.set_sprint,
        before_id=payload.before_id,
        after_id=payload.after_id,
        reorder=payload.reorder,
        on_board=payload.on_board,
        to_position=payload.to_position,
        position_project_id=payload.position_project_id,
        position_q=payload.position_q,
        position_assignee_token=position_token,
        position_priority=payload.position_priority,
        position_difficulty=payload.position_difficulty,
        base_version=payload.base_version,
        repo=_repo(request),
        request=request,
    )


# ── 스프린트 ─────────────────────────────────────────────────────────────────


@router.get("/sprints")
def list_sprints(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
) -> dict:
    """스프린트 목록 — 각 회차가 **오늘 활성인가**(`active`)를 함께 낸다(§8.3).

    화면(작업 보드)이 진입 시 이 값으로 자동 선택할 회차를 고른다. 「오늘」의 정본은
    서버다(§불변 9) — 브라우저가 자기 시계로 판정하면 자정 앞뒤 몇 분 사용자마다
    다른 회차가 활성으로 보인다.
    """
    today = local_today(request.app.state.settings, request.app.state.clock.now())
    return {"sprints": service.list_sprints(db, user, project_id=project_id, today=today)}


@router.post("/sprints", dependencies=[Depends(require_csrf)])
def create_sprint(
    payload: SprintCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_WRITE")),
) -> dict:
    sprint = service.create_sprint(
        db, user, name=payload.name, starts_on=payload.starts_on,
        ends_on=payload.ends_on, project_id=payload.project_id, goal=payload.goal,
    )
    record_audit_from_request(
        request, db, action="sprint.create", object_type="sprint",
        object_id=sprint["id"], after=sprint,
    )
    return sprint


@router.post("/sprints/{sprint_id}/state", dependencies=[Depends(require_csrf)])
def set_sprint_state(
    sprint_id: str,
    payload: SprintState,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_WRITE")),
) -> dict:
    sprint = service.set_sprint_state(db, user, sprint_id=sprint_id, state=payload.state)
    record_audit_from_request(
        request, db, action="sprint.state", object_type="sprint",
        object_id=sprint_id, after={"state": payload.state},
    )
    return sprint


@router.post("/sprints/{sprint_id}/close", dependencies=[Depends(require_csrf)])
def close_sprint(
    sprint_id: str,
    payload: SprintClose,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_WRITE")),
) -> dict:
    result = service.close_sprint_and_carry_over(
        db, user, sprint_id=sprint_id, target_sprint_id=payload.target_sprint_id
    )
    record_audit_from_request(
        request, db, action="sprint.close", object_type="sprint",
        object_id=sprint_id, after=result,
    )
    return result


@router.get("/sprints/{sprint_id}/scope")
def sprint_scope(
    sprint_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return service.sprint_scope(db, sprint_id, user)


# ── 회의 (지시 4) ────────────────────────────────────────────────────────────


@router.get("/sprints/{sprint_id}/meeting")
def sprint_meeting(
    sprint_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """회의 한 판. 여섯 질문의 답이 한 응답에 있다(`app/work/meeting.py`).

    「오늘」은 **서버가 정한다**(§불변 9). 화면이 브라우저에서 오늘을 구하면 KST 09:00
    이전에 접속한 사람과 이후에 접속한 사람이 서로 다른 「지연 목록」을 보고, 같은
    회의에서 두 사람이 다른 화면을 읽게 된다.
    """
    return meeting.meeting(
        db, user, sprint_id=sprint_id,
        today=local_today(request.app.state.settings, request.app.state.clock.now()),
    )


@router.post("/sprints/{sprint_id}/decisions", dependencies=[Depends(require_csrf)])
def add_decision(
    sprint_id: str,
    payload: DecisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """회의록을 적는다. **역할로 막지 않는다.**

    회의에 앉은 사람이 곧 적는 사람이다. 「기록은 관리자만」이면 회의가 끝난 뒤 아무도
    안 적고, 그러면 이 표는 빈 채로 남는다. 대신 회차가 보여야 하고(`get_scoped_...`)
    고칠 수 있는 사람은 좁다(적은 사람 · 걸린 담당자 · 운영군).
    """
    row = meeting.add_decision(
        db, user, sprint_id=sprint_id, kind=payload.kind, body=payload.body,
        ticket_id=payload.ticket_id, assignee_user_id=payload.assignee_user_id,
        due_date=parse_date(payload.due_date),
    )
    record_audit_from_request(
        request, db, action="sprint.decision.add", object_type="sprint_decision",
        object_id=row["id"], after={"sprint_id": sprint_id, "kind": payload.kind},
    )
    return row


@router.patch("/decisions/{decision_id}", dependencies=[Depends(require_csrf)])
def edit_decision(
    decision_id: str,
    payload: DecisionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "due_date" in changes:
        changes["due_date"] = parse_date(changes["due_date"])
    if not changes:
        raise ValidationAppError("변경할 내용이 없습니다.")
    row = meeting.update_decision(db, user, decision_id=decision_id, changes=changes)
    record_audit_from_request(
        request, db, action="sprint.decision.edit", object_type="sprint_decision",
        object_id=decision_id, after={k: v for k, v in changes.items() if k != "body"},
    )
    return row


@router.delete("/decisions/{decision_id}", dependencies=[Depends(require_csrf)])
def remove_decision(
    decision_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    meeting.delete_decision(db, user, decision_id=decision_id)
    record_audit_from_request(
        request, db, action="sprint.decision.delete", object_type="sprint_decision",
        object_id=decision_id,
    )
    return {"ok": True}


# ── 이름 (3층 식별자) ────────────────────────────────────────────────────────


@router.get("/resolve/{token}")
def resolve_key(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """`ABCDEF-37` 이든 uuid 든 **같은 티켓**으로 간다 (D-282).

    범위 판정은 티켓 서비스가 한다 — 여기서 함께 하면 「없는 티켓」과 「안 보이는
    티켓」이 같은 답이 되고, 그 둘을 구별하지 못하면 관리자가 예외 티켓을 못 찾는다.
    """
    found = resolve(db, token)
    if found is None:
        raise NotFoundError("티켓을 찾을 수 없습니다.")
    from app.tickets import service as tickets_service
    from app.tickets.models import api_page_id

    tickets_service.ensure_ticket_visible(db, api_page_id(found.ticket), user)
    return {
        "ticket_id": found.ticket.id,
        "page_id": api_page_id(found.ticket),
        "matched_by": found.matched_by,
        "is_current_name": found.is_current_name,
        "key": found.ticket.canonical_key,
    }


# ── 관계 · 관찰 ──────────────────────────────────────────────────────────────


@router.get("/tickets/{ticket_id}/detail")
def ticket_extras(
    ticket_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ticket = service.load_ticket_in_scope_or_404(db, ticket_id, user)
    return service.ticket_detail_extras(db, ticket)


@router.post("/tickets/{ticket_id}/relations", dependencies=[Depends(require_csrf)])
def add_relation(
    ticket_id: str,
    payload: RelationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("TICKET_UPDATE")),
) -> dict:
    """관계를 잇는다. **양쪽 티켓이 다 보여야 한다.**

    한쪽만 확인하면 안 보이는 티켓의 존재를 관계로 알아낼 수 있다 — 상세를 못 열어도
    "그 id 는 있다" 가 새 나간다.
    """
    _ensure_both_visible(db, user, ticket_id, payload.to_ticket_id)
    relations_mod.add(
        db, from_ticket_id=ticket_id, to_ticket_id=payload.to_ticket_id,
        kind=payload.kind, actor_id=user.id,
    )
    record_audit_from_request(
        request, db, action="ticket.relation_add", object_type="ticket",
        object_id=ticket_id, after={"to": payload.to_ticket_id, "kind": payload.kind},
    )
    return {"relations": relations_mod.for_ticket(db, ticket_id)}


@router.delete("/tickets/{ticket_id}/relations", dependencies=[Depends(require_csrf)])
def drop_relation(
    ticket_id: str,
    payload: RelationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("TICKET_UPDATE")),
) -> dict:
    _ensure_both_visible(db, user, ticket_id, payload.to_ticket_id)
    removed = relations_mod.remove(
        db, from_ticket_id=ticket_id, to_ticket_id=payload.to_ticket_id, kind=payload.kind
    )
    if removed:
        record_audit_from_request(
            request, db, action="ticket.relation_remove", object_type="ticket",
            object_id=ticket_id,
            before={"to": payload.to_ticket_id, "kind": payload.kind},
        )
    return {"relations": relations_mod.for_ticket(db, ticket_id)}


@router.post("/tickets/{ticket_id}/watch", dependencies=[Depends(require_csrf)])
def toggle_watch(
    ticket_id: str,
    payload: WatchToggle,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    service.load_ticket_in_scope_or_404(db, ticket_id, user)
    changed = service.watch(
        db, ticket_id=ticket_id, user_id=user.id, watching=payload.watching
    )
    return {"watching": payload.watching, "changed": changed}


def _ensure_both_visible(db: Session, user: User, *ticket_ids: str) -> None:
    for tid in ticket_ids:
        service.load_ticket_in_scope_or_404(db, tid, user)


# ── Migration Exception ──────────────────────────────────────────────────────


@router.get("/exceptions")
def list_exceptions(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_ADMIN")),
) -> dict:
    """소속을 못 정한 티켓들. **여기 있는 동안은 번호가 없다** (D-197)."""
    rows = db.execute(
        MigrationException.__table__.select()
        .where(MigrationException.resolved_at.is_(None))
        .order_by(MigrationException.created_at)
    ).all()
    return {
        "exceptions": [
            {
                "id": r.id, "ticket_id": r.ticket_id, "reason": r.reason,
                "evidence": r.source_evidence,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/exceptions/{ticket_id}/assign", dependencies=[Depends(require_csrf)])
def assign_exception(
    ticket_id: str,
    payload: ExceptionAssign,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_ADMIN")),
) -> dict:
    """사람이 소속을 정한다 — **자동으로 하지 않는 일을 하는 자리다.**"""
    # 한쪽만 보면 남의 티켓을 내 프로젝트로 끌어오거나(소속 탈취) 내 티켓을 남의
    # 프로젝트로 밀어 넣을 수 있다. 뒤쪽은 되돌릴 수도 없다 — 그 순간 내 범위에서 사라진다.
    service.load_ticket_in_scope_or_404(db, ticket_id, user)
    service.get_scoped_project_or_404(db, payload.project_id, user)
    result = triage.assign(
        db, ticket_id=ticket_id, project_id=payload.project_id, actor_id=user.id
    )
    record_audit_from_request(
        request, db, action="ticket.exception_assign", object_type="ticket",
        object_id=ticket_id, after=result,
    )
    return result
