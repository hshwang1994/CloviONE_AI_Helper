"""부서·직책 관리 API (admin+, CSRF, 감사).

⚠ 이 파일에는 `from __future__ import annotations`를 넣지 않는다(CLAUDE.md §8).
아래는 라우터 '팩토리'다 — 지연 평가된 문자열 애노테이션은 팩토리 지역 이름
(model 등)을 모듈 전역에서 찾지 못해 FastAPI의 의존성 해석이 깨진다.

부서와 직책은 규칙이 같으므로 라우터를 한 번 만들어 두 번 쓴다. 두 벌로 적으면
한쪽에만 CSRF나 감사가 빠지는 식으로 갈라진다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.errors import NotFoundError, ValidationAppError
from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.org.constants import ORG_ACTIVE, ORG_SUSPENDED
from app.org.models import Department, JobTitle, Organization
from app.org.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    OrgItemCreateRequest,
    OrgItemUpdateRequest,
)
from app.org.service import (
    create_item,
    delete_item,
    get_or_404,
    item_view,
    list_items,
    update_item,
    normalize_name,
    usage_count,
)
from app.org.tree import tree_rows
from app.users.models import User



def _make_org_router(
    *,
    model,
    prefix: str,
    tag: str,
    body_key: str,
    audit_type: str,
    create_schema=OrgItemCreateRequest,
    update_schema=OrgItemUpdateRequest,
    with_tree: bool = False,
):
    router = APIRouter(
        prefix=prefix,
        tags=[tag],
        dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES)), Depends(require_csrf)],
    )

    @router.get("")
    def list_org_items(
        db: Session = Depends(get_db),
        active: Optional[bool] = Query(
            default=None, description="true면 새로 고를 수 있는 항목만"
        ),
    ):
        rows = list_items(db, model, active=active)
        # 몇 명이 쓰는지 보이지 않으면 관리자는 지워도 되는지 판단할 수 없다.
        return {
            "items": [
                item_view(row, user_count=usage_count(db, model, row.id)) for row in rows
            ]
        }

    if with_tree:
        # ⚠ 반드시 `/{item_id}` **위에** 있어야 한다. Starlette 는 선언 순서로 매칭하므로
        # 아래에 두면 이 경로는 영영 `/{item_id}` 에 먹혀 "'tree' 부서를 찾을 수 없습니다"만
        # 돌려준다(정적 경로가 경로 파라미터에 가려지는 전형적인 함정).
        @router.get("/tree")
        def get_org_tree(
            db: Session = Depends(get_db),
            active: Optional[bool] = Query(default=None),
        ):
            return {"items": tree_rows(db, active=active)}

    @router.get("/{item_id}")
    def get_org_item(item_id: str, db: Session = Depends(get_db)):
        # 감사/알림이 job_title·department를 참조할 때 '관련 항목 보기'로 그 행 하나를
        # 열 수 있게 단건 조회를 연다(다른 CRUD 화면과 동일한 딥링크 패턴, round30 감사 E).
        row = get_or_404(db, model, item_id)
        return {body_key: item_view(row, user_count=usage_count(db, model, row.id))}

    @router.post("", status_code=201)
    def create_org_item(
        request: Request,
        payload: create_schema,
        db: Session = Depends(get_db),
    ):
        row = create_item(
            db, model, name=payload.name, parent_id=getattr(payload, "parent_id", None)
        )
        record_audit_from_request(
            request, db, action=f"{audit_type}.create", object_type=audit_type,
            object_id=row.id, after=item_view(row),
        )
        return {body_key: item_view(row, user_count=0)}

    @router.patch("/{item_id}")
    def update_org_item(
        request: Request,
        item_id: str,
        payload: update_schema,
        db: Session = Depends(get_db),
    ):
        row = get_or_404(db, model, item_id)
        before = item_view(row)
        fields = payload.model_dump(exclude_unset=True)
        update_item(db, row, **fields)
        record_audit_from_request(
            request, db, action=f"{audit_type}.update", object_type=audit_type,
            object_id=row.id, before=before, after=item_view(row),
        )
        return {body_key: item_view(row, user_count=usage_count(db, model, row.id))}

    @router.delete("/{item_id}")
    def delete_org_item(request: Request, item_id: str, db: Session = Depends(get_db)):
        row = get_or_404(db, model, item_id)
        before = item_view(row)
        delete_item(db, row)  # 쓰는 사람이 있으면 여기서 409로 막힌다
        record_audit_from_request(
            request, db, action=f"{audit_type}.delete", object_type=audit_type,
            object_id=item_id, before=before,
        )
        return {"ok": True}

    return router


departments_router = _make_org_router(
    model=Department,
    prefix="/api/admin/departments",
    tag="admin-departments",
    body_key="department",
    audit_type="department",
    create_schema=DepartmentCreateRequest,
    update_schema=DepartmentUpdateRequest,
    with_tree=True,
)

job_titles_router = _make_org_router(
    model=JobTitle,
    prefix="/api/admin/job-titles",
    tag="admin-job-titles",
    body_key="job_title",
    audit_type="job_title",
)


# ── 조직 ──────────────────────────────────────────────────────────────────────
#
# `organizations` 는 0022 부터 표만 있고 라우터도 화면도 없었다 — 시드 한 행이 전부였다.
# 사용자 지시 §3 이 "조직 > 부서 > 사용자" 를 한눈에 보여 달라고 했는데, 맨 위 층이
# 화면에 존재하지 않으면 그 관계를 보여 줄 수가 없다. 그래서 되살린다.
#
# 팩토리(_make_org_router)를 쓰지 않는 이유: 조직은 `active` 대신 `status` 를 쓰고 `slug`
# 를 가지며 **지울 수 없다**. 억지로 끼워 맞추면 팩토리에 조직 전용 분기가 세 개 생긴다.

organizations_router = APIRouter(
    prefix="/api/admin/organizations",
    tags=["admin-organizations"],
    dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES)), Depends(require_csrf)],
)


def _org_view(db: Session, row: Organization) -> dict:
    """조직 한 곳 + **그 안에 무엇이 들어 있는지**. 숫자가 곧 포함 관계의 요약이다."""
    dept_count = db.execute(
        select(func.count()).select_from(Department).where(Department.org_id == row.id)
    ).scalar_one()
    user_count = db.execute(
        select(func.count()).select_from(User).where(User.org_id == row.id)
    ).scalar_one()
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "status": row.status,
        "department_count": dept_count,
        "user_count": user_count,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _get_org_or_404(db: Session, org_id: str) -> Organization:
    row = db.get(Organization, org_id)
    if row is None:
        raise NotFoundError("조직을 찾을 수 없습니다.")
    return row


@organizations_router.get("")
def list_organizations(db: Session = Depends(get_db)):
    rows = list(db.execute(select(Organization).order_by(Organization.name)).scalars())
    return {"items": [_org_view(db, r) for r in rows], "total": len(rows)}


@organizations_router.get("/{org_id}")
def get_organization(org_id: str, db: Session = Depends(get_db)):
    return {"organization": _org_view(db, _get_org_or_404(db, org_id))}


@organizations_router.post("", status_code=201)
def create_organization(
    request: Request,
    payload: OrganizationCreateRequest,
    db: Session = Depends(get_db),
):
    name = normalize_name(payload.name)
    slug = payload.slug.strip().lower()
    exists = db.execute(
        select(Organization).where(Organization.slug == slug)
    ).scalar_one_or_none()
    if exists is not None:
        raise ValidationAppError(f"이미 있는 식별자입니다: {slug}")
    row = Organization(slug=slug, name=name, status=ORG_ACTIVE)
    db.add(row)
    db.flush()
    record_audit_from_request(
        request, db, action="organization.create", object_type="organization",
        object_id=row.id, after={"slug": slug, "name": name},
    )
    return {"organization": _org_view(db, row)}


@organizations_router.patch("/{org_id}")
def update_organization(
    request: Request,
    org_id: str,
    payload: OrganizationUpdateRequest,
    db: Session = Depends(get_db),
):
    row = _get_org_or_404(db, org_id)
    changes = payload.model_dump(exclude_unset=True)
    before = {"name": row.name, "status": row.status}
    if "name" in changes:
        row.name = normalize_name(changes["name"] or "")
    if "status" in changes:
        status = (changes["status"] or "").strip()
        if status not in (ORG_ACTIVE, ORG_SUSPENDED):
            raise ValidationAppError(
                f"상태는 {ORG_ACTIVE} 또는 {ORG_SUSPENDED} 여야 합니다."
            )
        row.status = status
    db.flush()
    record_audit_from_request(
        request, db, action="organization.update", object_type="organization",
        object_id=row.id, before=before, after={"name": row.name, "status": row.status},
    )
    return {"organization": _org_view(db, row)}
