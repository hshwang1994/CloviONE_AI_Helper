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
from app.core.errors import NotFoundError
from app.settings.gate import block_if_maintenance
from app.users.models import User
from app.work import keys as keys_mod
from app.work import relations as relations_mod
from app.work import service, triage, workflow
from app.work.models import MigrationException, ProjectKeyRegistry, TicketStatus
from app.work.resolve import resolve
from app.work.schemas import (
    BoardMove,
    ExceptionAssign,
    ProjectKeyAssign,
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
            }
            for r in rows
        ],
        "categories": list(workflow.CATEGORIES),
        "default": next((r.key for r in rows if r.is_default), workflow.DEFAULT_STATUS),
    }


# ── 판과 백로그 ──────────────────────────────────────────────────────────────


@router.get("/board")
def get_board(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
    sprint_id: str | None = Query(default=None, max_length=36),
) -> dict:
    return service.board(db, user, project_id=project_id, sprint_id=sprint_id)


@router.get("/backlog")
def get_backlog(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
) -> dict:
    return service.backlog(db, user, project_id=project_id)


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
    return service.move(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        ticket_id=ticket_id,
        to_status=payload.to_status,
        sprint_id=payload.sprint_id,
        set_sprint=payload.set_sprint,
        before_id=payload.before_id,
        after_id=payload.after_id,
        reorder=payload.reorder,
        base_version=payload.base_version,
        repo=_repo(request),
        request=request,
    )


# ── 스프린트 ─────────────────────────────────────────────────────────────────


@router.get("/sprints")
def list_sprints(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = Query(default=None, max_length=36),
) -> dict:
    return {"sprints": service.list_sprints(db, user, project_id=project_id)}


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


# ── 이름 (3층 식별자) ────────────────────────────────────────────────────────


@router.get("/resolve/{token}")
def resolve_key(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """`GIT-142` 든 `SKH-37` 이든 uuid 든 **같은 티켓**으로 간다 (D-195).

    범위 판정은 티켓 서비스가 한다 — 여기서 함께 하면 「없는 티켓」과 「안 보이는
    티켓」이 같은 답이 되고, 그 둘을 구별하지 못하면 관리자가 예외 티켓을 못 찾는다.
    """
    found = resolve(db, token)
    if found is None:
        raise NotFoundError("티켓을 찾을 수 없습니다.")
    from app.tickets import service as tickets_service

    tickets_service.ensure_ticket_visible(db, found.ticket.notion_page_id, user)
    return {
        "ticket_id": found.ticket.id,
        "page_id": found.ticket.notion_page_id,
        "matched_by": found.matched_by,
        "is_current_name": found.is_current_name,
        "key": found.ticket.canonical_key or found.ticket.legacy_key,
    }


@router.get("/keys")
def list_keys(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_READ")),
) -> dict:
    """Key 대장 전체. **`retired` 도 보인다** — 왜 그 이름을 못 쓰는지 알아야 한다."""
    rows = db.execute(
        ProjectKeyRegistry.__table__.select().order_by(ProjectKeyRegistry.key)
    ).all()
    return {
        "keys": [
            {
                "key": r.key, "project_id": r.project_id, "state": r.state,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.put("/projects/{project_id}/key", dependencies=[Depends(require_csrf)])
def set_project_key(
    project_id: str,
    payload: ProjectKeyAssign,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_ADMIN")),
) -> dict:
    """Key 를 정하거나 바꾼다. **바꾸는 쪽은 옛 이름을 별칭으로 남긴다** (D-195).

    처음 주는 것과 바꾸는 것을 한 입구로 받는 이유: 화면에서 그 둘은 같은 동작이다
    ("이 프로젝트의 키"를 채운다). 다른 것은 서버가 하는 일이고, 그 차이를 사용자에게
    묻게 하면 잘못 고르는 사람이 생긴다.
    """
    project = service.get_scoped_project_or_404(db, project_id, user)
    before = project.code
    if before:
        result = keys_mod.change(db, project_id=project_id, key=payload.key)
    else:
        row = keys_mod.claim(db, project_id=project_id, key=payload.key)
        result = {"changed": True, "old_key": None, "new_key": row.key, "aliased": 0}
    record_audit_from_request(
        request, db, action="project.key_change", object_type="project",
        object_id=project_id, before={"code": before}, after=result,
    )
    return result


@router.get("/projects/{project_id}/key/suggest")
def suggest_project_key(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("PROJECT_ADMIN")),
) -> dict:
    """이름에서 뽑은 초안. **확정이 아니다** (D-197) — 사람이 보고 고친다."""
    project = service.get_scoped_project_or_404(db, project_id, user)
    taken = {
        r.key for r in db.execute(ProjectKeyRegistry.__table__.select()).all()
    }
    return {
        "project_id": project_id,
        "name": project.name,
        "current": project.code,
        "suggestion": keys_mod.suggest(project.name, taken=taken),
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
