"""조직 정합성 진단 API.

읽기는 관리 콘솔 읽기 권한(감사자 포함 — 무엇이 어긋나 있는지는 감사가 봐야 한다),
**고치기는 전역 관리자만**이다. 소속을 지정하는 것은 "누가 무엇을 볼 수 있는가" 를 바꾸는
일이라, 범위가 좁혀진 관리자가 자기 범위 밖 계정의 소속을 정하게 두면 그 자체가
범위 탈출 경로가 된다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.errors import ForbiddenError
from app.core.scope import Principal
from app.integrity import service

router = APIRouter(
    prefix="/api/admin/integrity",
    tags=["admin-integrity"],
    dependencies=[Depends(require_csrf)],
)


class MembershipAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(min_length=1, max_length=500)
    department_id: str | None = Field(default=None, max_length=36)
    organization_direct: bool = False


def _require_global(principal: Principal) -> None:
    # 403 이지 404 가 아니다 — 이 화면의 존재는 이미 드러나 있고, 문제는 존재가 아니라 권한이다
    # (`app/org/router.py::create_organization` 과 같은 판단).
    if not principal.manages_everything:
        raise ForbiddenError("정합성 일괄 지정은 전체 범위 관리자만 할 수 있습니다.")


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def integrity_report(db: Session = Depends(get_db)):
    """읽기 전용 진단. **아무 데이터도 바꾸지 않는다.**"""
    return service.report(db)


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
    몇 시간짜리 일이 된다.
    """
    _require_global(principal)
    changed = service.assign_membership(
        db,
        user_ids=payload.user_ids,
        department_id=payload.department_id,
        organization_direct=payload.organization_direct,
    )
    record_audit_from_request(
        request, db, action="integrity.assign_membership", object_type="user",
        object_id=None,
        after={
            "count": changed,
            "department_id": payload.department_id,
            "organization_direct": payload.organization_direct,
        },
    )
    return {"ok": True, "changed": changed}
