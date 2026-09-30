"""조직 정합성 진단 API.

읽기는 관리 콘솔 읽기 권한(감사자 포함 — 무엇이 어긋나 있는지는 감사가 봐야 한다),
**고치기는 전역 관리자만**이다. 소속을 지정하는 것은 "누가 무엇을 볼 수 있는가" 를 바꾸는
일이라, 범위가 좁혀진 관리자가 자기 범위 밖 계정의 소속을 정하게 두면 그 자체가
범위 탈출 경로가 된다.

## 일괄 작업은 이미 있는 쓰기 경로를 부른다 (계획 3.2)

`POST /checks/{key}/fix` 는 새 쓰기 규칙을 만들지 않는다. 항목마다 그 자원의 원래 수정 함수를
부르고, 그 함수의 라우터가 남기는 것과 **같은 감사 행**을 남긴다(티켓 편집 `ticket.update`, 보드
이동은 서비스가 직접, 공간 `knowledge.space_update`, 프로젝트 `project.update`, 회차 `sprint.update`).
세 번째 쓰기 경로를 만들면 감사와 알림이 갈라진다.

항목 하나가 거절되면(열린 회차에 담긴 프로젝트의 부서 변경 등) 그 항목만 SAVEPOINT 로 되감고
사유와 함께 건너뛴다. 나머지는 그대로 반영한다 - 50건 중 1건 때문에 49건을 다시 고르게 하지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_current_user, get_db, get_principal, require_csrf, require_roles
from app.core.errors import AppError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.core.scope import Principal
from app.integrity import service
from app.users.models import User

router = APIRouter(
    prefix="/api/admin/integrity",
    tags=["admin-integrity"],
    dependencies=[Depends(require_csrf)],
)

# 한 번에 고칠 수 있는 항목 수. 항목마다 원래 수정 함수와 감사가 돌므로 상한이 없으면 요청 하나가
# 몇 분씩 걸린다. 목록은 50건씩 더 보기라 몇 번 나눠 고르면 된다.
MAX_FIX_IDS = 200


class MembershipAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(min_length=1, max_length=500)
    department_id: str | None = Field(default=None, max_length=36)
    organization_direct: bool = False


class FixRequest(BaseModel):
    """검사 하나의 일괄 작업. 대상 값은 작업마다 하나만 쓴다(나머지는 보내지 않는다)."""

    model_config = ConfigDict(extra="forbid")

    fix: str = Field(min_length=1, max_length=40)
    ids: list[str] = Field(min_length=1, max_length=MAX_FIX_IDS)
    department_id: str | None = Field(default=None, max_length=36)
    organization_direct: bool = False
    project_id: str | None = Field(default=None, max_length=36)


def _require_global(principal: Principal) -> None:
    # 403 이지 404 가 아니다 — 이 화면의 존재는 이미 드러나 있고, 문제는 존재가 아니라 권한이다
    # (`app/org/router.py::create_organization` 과 같은 판단).
    if not principal.manages_everything:
        raise ForbiddenError("정합성 일괄 지정은 전체 범위 관리자만 할 수 있습니다.")


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def integrity_report(db: Session = Depends(get_db)):
    """읽기 전용 요약. **아무 데이터도 바꾸지 않는다.**"""
    return service.report(db)


@router.get("/checks/{key}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def integrity_check_items(
    key: str,
    q: str | None = Query(default=None, max_length=200),
    sort: str | None = Query(default=None, max_length=20),
    order: str | None = Query(default=None, pattern="^(asc|desc)$"),
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    """검사 하나의 전량 목록 — 검색, 정렬, 페이지. 요약의 표본 50건에서 잘리지 않는다."""
    result = service.list_items(
        db, key, q=q, sort=sort, order=order, offset=page.offset, limit=page.page_size,
    )
    return {**result, "page": page.page, "page_size": page.page_size}


@router.get("/admins", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def integrity_admins(
    q: str | None = Query(default=None, max_length=200),
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
):
    """관리자 범위 현황(참고 목록). 할 일이 아니라서 일괄 작업이 없다."""
    result = service.list_admins(db, q=q, offset=page.offset, limit=page.page_size)
    return {**result, "page": page.page, "page_size": page.page_size}


def _assign_membership(request: Request, db: Session, *, user_ids, department_id, organization_direct):
    result = service.assign_membership(
        db, user_ids=user_ids, department_id=department_id, organization_direct=organization_direct,
    )
    record_audit_from_request(
        request, db, action="integrity.assign_membership", object_type="user",
        object_id=None,
        after={
            "count": result["changed"],
            # 건너뛴 건수도 남긴다 — 「50명을 보냈는데 2명만 바뀌었다」를 나중에 설명할 수
            # 있어야 한다(감사 로그는 무슨 일이 있었나의 기록이다).
            "skipped": len(result["skipped"]),
            "department_id": department_id,
            "organization_direct": organization_direct,
        },
    )
    return result


@router.post("/membership", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def assign_membership(
    request: Request,
    payload: MembershipAssignRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """소속 미지정 사용자에게 부서 또는 조직 직속을 **일괄 지정**한다.

    이것이 fail-closed 규칙과 같은 배포에 있어야 하는 이유: 규칙만 켜면 소속을 안 정한
    계정들이 그날부터 아무것도 못 보는데, 한 명씩 편집 화면을 열어 고치게 하면 복구가
    몇 시간짜리 일이 된다. 화면은 `POST /checks/{key}/fix` 를 쓰고, 이 경로는 먼저 있던
    호출자를 위해 같은 함수로 남긴다.
    """
    _require_global(principal)
    result = _assign_membership(
        request, db, user_ids=payload.user_ids, department_id=payload.department_id,
        organization_direct=payload.organization_direct,
    )
    # `skipped` 를 응답에 싣는다 — 화면이 「몇 명은 왜 안 바뀌었는가」를 그대로 말할 수 있다.
    return {"ok": True, "changed": result["changed"], "skipped": result["skipped"]}


# ── 항목별 작업 — 전부 원래 수정 함수를 부른다 ───────────────────────────────


def _ticket_project(
    request: Request, db: Session, user: User, principal: Principal, item: dict,
    payload: FixRequest,
) -> None:
    from app.tickets import service as tickets_service

    result = tickets_service.update_ticket(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        page_id=item["id"], changes={"project_id": payload.project_id},
        now=request.app.state.clock.now(), repo=request.app.state.repositories.tickets,
    )
    record_audit_from_request(
        request, db, action="ticket.update", object_type="notion_task",
        object_id=item["id"], before=result["before"], after=result["after"],
    )


def _remove_from_sprint(
    request: Request, db: Session, user: User, principal: Principal, item: dict,
    payload: FixRequest,
) -> None:
    from app.work import service as work_service

    # 감사는 보드 이동 서비스가 남긴다(`request` 를 넘긴다) - 보드에서 뺀 것과 같은 기록이다.
    work_service.move(
        db, request.app.state.outbound_client, request.app.state.settings, user,
        ticket_id=item["uid"], set_sprint=True, sprint_id=None,
        repo=request.app.state.repositories.tickets, request=request,
    )


def _space_owner(
    request: Request, db: Session, user: User, principal: Principal, item: dict,
    payload: FixRequest,
) -> None:
    from app.core import ownership
    from app.knowledge import service as knowledge_service

    before = knowledge_service.get_scoped_space_or_404(db, user, item["id"]).owner_kind
    fields = (
        {"owner_kind": ownership.OWNER_DEPARTMENT, "owner_dept_id": payload.department_id}
        if payload.department_id else {"owner_kind": ownership.OWNER_ORGANIZATION}
    )
    space = knowledge_service.update_space(db, user, item["id"], **fields)
    record_audit_from_request(
        request, db, action="knowledge.space_update", object_type="knowledge_space",
        object_id=item["id"],
        before={"owner_kind": before, "confidential": space.confidential},
        after={"owner_kind": space.owner_kind, "confidential": space.confidential},
    )


def _project_department(
    request: Request, db: Session, user: User, principal: Principal, item: dict,
    payload: FixRequest,
) -> None:
    from app.projects import service as projects_service
    from app.projects.schemas import ProjectUpdate

    project = projects_service.get_scoped_project_or_404(db, item["id"], principal)
    projects_service.ensure_project_manageable(project, principal)
    before = {"dept_id": project.dept_id, "org_id": project.org_id}
    projects_service.update_project(
        db, project, ProjectUpdate(dept_id=payload.department_id), principal,
        now=request.app.state.clock.now(),
    )
    after = {"dept_id": project.dept_id, "org_id": project.org_id}
    record_audit_from_request(
        request, db, action="project.update", object_type="project", object_id=project.id,
        before=before if before != after else None, after=after if before != after else None,
    )


def _sprint_team(
    request: Request, db: Session, user: User, principal: Principal, item: dict,
    payload: FixRequest,
) -> None:
    from app.work import service as work_service

    changes = {"department_id": payload.department_id}
    sprint = work_service.update_sprint(db, user, sprint_id=item["id"], changes=changes)
    record_audit_from_request(
        request, db, action="sprint.update", object_type="sprint",
        object_id=item["id"], after={"changed": sorted(changes), **sprint},
    )


FIXES = {
    service.FIX_TICKET_PROJECT: _ticket_project,
    service.FIX_REMOVE_FROM_SPRINT: _remove_from_sprint,
    service.FIX_SPACE_OWNER: _space_owner,
    service.FIX_PROJECT_DEPARTMENT: _project_department,
    service.FIX_SPRINT_TEAM: _sprint_team,
}


def _validate_target(db: Session, payload: FixRequest) -> None:
    """작업마다 필요한 대상 값 하나를 요청 머리에서 한 번 확인한다. 항목마다 같은 422 를 되풀이하지 않는다."""
    from app.org.models import Department
    from app.org.service import resolve_assignable

    fix = payload.fix
    if fix == service.FIX_TICKET_PROJECT:
        if not payload.project_id or payload.department_id or payload.organization_direct:
            raise ValidationAppError("옮길 프로젝트 하나를 고르세요.")
        return
    if fix == service.FIX_REMOVE_FROM_SPRINT:
        if payload.project_id or payload.department_id or payload.organization_direct:
            raise ValidationAppError("회차에서 빼기에는 대상 값이 필요하지 않습니다.")
        return
    if fix in (service.FIX_MEMBERSHIP, service.FIX_SPACE_OWNER):
        if payload.project_id or bool(payload.department_id) == bool(payload.organization_direct):
            raise ValidationAppError("부서 지정과 조직 직속 중 하나만 고르세요.")
    elif not payload.department_id or payload.project_id or payload.organization_direct:
        raise ValidationAppError("지정할 부서 하나를 고르세요.")
    if payload.department_id:
        # 사용자 편집과 같은 함수, 같은 문구다: 없는 부서와 비활성 부서는 422 다.
        resolve_assignable(db, Department, payload.department_id)


@router.post("/checks/{key}/fix", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def fix_check_items(
    key: str,
    payload: FixRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    user: User = Depends(get_current_user),
):
    """검사 하나의 항목들을 일괄로 고친다. `{"changed": n, "skipped": [{id, title, reason}]}`."""
    _require_global(principal)
    check = service.CHECK_BY_KEY.get(key)
    if check is None:
        raise NotFoundError("알 수 없는 정합성 검사입니다.")
    if payload.fix not in check.fixes:
        raise ValidationAppError("이 항목에는 그 작업을 할 수 없습니다.")
    _validate_target(db, payload)

    if payload.fix == service.FIX_MEMBERSHIP:
        result = _assign_membership(
            request, db, user_ids=payload.ids, department_id=payload.department_id,
            organization_direct=payload.organization_direct,
        )
        skipped = [
            {"id": s["user_id"], "title": s["display_name"], "reason": s["reason"]}
            for s in result["skipped"]
        ]
        return {"ok": True, "changed": result["changed"], "skipped": skipped}

    items, skipped = service.listed(db, key, payload.ids)
    apply = FIXES[payload.fix]
    changed = 0
    for item in items:
        try:
            with db.begin_nested():
                apply(request, db, user, principal, item, payload)
            changed += 1
        except AppError as exc:
            skipped.append({"id": item["id"], "title": item.get("title"), "reason": exc.message})
    record_audit_from_request(
        request, db, action="integrity.fix", object_type="integrity_check", object_id=key,
        after={
            "fix": payload.fix, "count": changed, "skipped": len(skipped),
            "department_id": payload.department_id, "project_id": payload.project_id,
            "organization_direct": payload.organization_direct,
        },
    )
    return {"ok": True, "changed": changed, "skipped": skipped}
