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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.errors import NotFoundError, ValidationAppError
from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.scope import Principal
from app.core.deps import get_db, get_principal, require_csrf, require_roles
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



def _org_names(db: Session, rows) -> dict[str, str]:
    """{org_id: 조직 이름}. 행이 참조하는 조직만 한 번에 읽는다.

    `Department` 에 `organization` 관계를 붙이지 않는 이유는 `service.item_view` 주석 참조
    (모델은 FK 를 선언하지만 마이그레이션이 그 제약을 만든 적이 없다). 관계 대신 여기서
    한 번 조회한다 — 행마다 조회하면 부서 목록이 N+1 이 된다.
    """
    ids = {oid for oid in (getattr(r, "org_id", None) for r in rows) if oid}
    if not ids:
        return {}
    return {
        o.id: o.name
        for o in db.execute(select(Organization).where(Organization.id.in_(ids)))
        .scalars()
        .all()
    }


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
        principal: Principal = Depends(get_principal),
        active: Optional[bool] = Query(
            default=None, description="true면 새로 고를 수 있는 항목만"
        ),
    ):
        # 범위 밖 조직도는 안 보인다 (2순위 #1). 부서 이름만으로도 그 회사가 무슨 일을
        # 어떤 단위로 하는지 드러난다.
        rows = list_items(db, model, active=active, scope=principal.scope)
        names = _org_names(db, rows)
        # 몇 명이 쓰는지 보이지 않으면 관리자는 지워도 되는지 판단할 수 없다.
        return {
            "items": [
                item_view(
                    row,
                    user_count=usage_count(db, model, row.id),
                    org_name=names.get(getattr(row, "org_id", None)),
                )
                for row in rows
            ]
        }

    if with_tree:
        # ⚠ 반드시 `/{item_id}` **위에** 있어야 한다. Starlette 는 선언 순서로 매칭하므로
        # 아래에 두면 이 경로는 영영 `/{item_id}` 에 먹혀 "'tree' 부서를 찾을 수 없습니다"만
        # 돌려준다(정적 경로가 경로 파라미터에 가려지는 전형적인 함정).
        @router.get("/tree")
        def get_org_tree(
            db: Session = Depends(get_db),
            principal: Principal = Depends(get_principal),
            active: Optional[bool] = Query(default=None),
        ):
            # 목록과 **같은 판정**을 지난다. 이 경로만 principal 을 안 받고 있었고, 트리는
            # 목록보다 더 많이 준다 - 조직 이름·인원수에 부서 계층 path 까지 한 번에 나갔다.
            return {"items": tree_rows(db, active=active, scope=principal.scope)}

    @router.get("/{item_id}")
    def get_org_item(item_id: str, db: Session = Depends(get_db),
                     principal: Principal = Depends(get_principal)):
        # 감사/알림이 job_title·department를 참조할 때 '관련 항목 보기'로 그 행 하나를
        # 열 수 있게 단건 조회를 연다(다른 CRUD 화면과 동일한 딥링크 패턴, round30 감사 E).
        row = get_or_404(db, model, item_id, principal.scope)
        names = _org_names(db, [row])
        return {body_key: item_view(
            row,
            user_count=usage_count(db, model, row.id),
            org_name=names.get(getattr(row, "org_id", None)),
        )}

    @router.post("", status_code=201)
    def create_org_item(
        request: Request,
        payload: create_schema,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        # 만드는 것도 범위 안에서만. 안 그러면 부서 범위 관리자가 남의 조직·남의 부서 밑에
        # 행을 만들어 놓고 **자기 화면에서는 그 행을 보지도 지우지도 못한다**(유령 행).
        row = create_item(
            db, model,
            name=payload.name,
            parent_id=getattr(payload, "parent_id", None),
            org_id=getattr(payload, "org_id", None),
            scope=principal.scope,
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
        principal: Principal = Depends(get_principal),
    ):
        row = get_or_404(db, model, item_id, principal.scope)
        before = item_view(row)
        fields = payload.model_dump(exclude_unset=True)
        # 상위 부서도 범위를 지난다 — 생성만 막으면 수정으로 같은 일을 한다.
        update_item(db, row, scope=principal.scope, **fields)
        record_audit_from_request(
            request, db, action=f"{audit_type}.update", object_type=audit_type,
            object_id=row.id, before=before, after=item_view(row),
        )
        return {body_key: item_view(row, user_count=usage_count(db, model, row.id))}

    @router.delete("/{item_id}")
    def delete_org_item(request: Request, item_id: str, db: Session = Depends(get_db),
                        principal: Principal = Depends(get_principal)):
        row = get_or_404(db, model, item_id, principal.scope)
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

def _revoke_org_sessions(request: Request, db: Session, org_id: str) -> int:
    """정지된 조직 구성원의 살아 있는 세션을 전부 끊는다 (X5).

    `system_admin` 은 건너뛴다 — 포탈 운영자까지 끊으면 **정지를 풀 사람이 없어진다**.
    판정 기준은 `is_blocked_by_org_suspension` 과 같아야 한다(두 벌이 되면 한쪽만 고쳐진다).
    """
    from app.users.models import User

    sessions = request.app.state.session_service
    users = db.execute(
        select(User.id).where(User.org_id == org_id, User.role != "system_admin")
    ).scalars().all()
    return sum(sessions.revoke_all_for_user(db, uid) for uid in users)


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


def _visible_org_or_404(db: Session, org_id: str, principal) -> Organization:
    """내 범위 안의 조직만. 밖은 **404** (존재를 알려 주지 않는다).

    부서·직책은 이미 범위를 지나는데 **조직 자체는 안 지나고 있었다** — 같은 파일 안에서
    규칙이 갈려 있었다. 멀티테넌트에서 조직 목록은 곧 **테넌트 명부**다(이름·식별자·부서
    수·인원수). 다른 고객사의 존재와 규모가 콘솔 쓰기 권한자 누구에게나 보이면 안 된다.
    """
    row = _get_org_or_404(db, org_id)
    scope = getattr(principal, "scope", None)
    if scope is None or getattr(scope, "is_global", True):
        return row
    if row.id != getattr(scope, "org_id", None):
        raise NotFoundError("조직을 찾을 수 없습니다.")
    return row


@organizations_router.get("")
def list_organizations(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    stmt = select(Organization).order_by(Organization.name)
    scope = getattr(principal, "scope", None)
    # 전역 범위가 아니면 자기 조직만. 부서 범위 관리자도 마찬가지다 — 부서는 조직 안에 있고,
    # 그 사람이 다른 조직의 존재를 알아야 할 이유가 없다.
    if scope is not None and not getattr(scope, "is_global", True):
        stmt = stmt.where(Organization.id == getattr(scope, "org_id", None))
    rows = list(db.execute(stmt).scalars())
    return {"items": [_org_view(db, r) for r in rows], "total": len(rows)}


@organizations_router.get("/{org_id}")
def get_organization(
    org_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    return {"organization": _org_view(db, _visible_org_or_404(db, org_id, principal))}


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
    principal: Principal = Depends(get_principal),
):
    # 목록·단건과 **같은 문**을 지난다 — 목록만 가려서는 id 로 뚫린다.
    row = _visible_org_or_404(db, org_id, principal)
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
        was = before["status"]
        row.status = status
        if status == ORG_SUSPENDED and was != ORG_SUSPENDED:
            # **즉시** 끊는다. 안 그러면 이미 로그인해 있는 사람은 세션이 만료될 때까지
            # (최대 8시간) 계속 쓴다 — 관리자는 정지했다고 믿는 동안이다.
            # 역할·범위 변경과 같은 급의 권한 변경이므로 같은 처리를 한다.
            revoked = _revoke_org_sessions(request, db, row.id)
            before["revoked_sessions"] = revoked
    db.flush()
    record_audit_from_request(
        request, db, action="organization.update", object_type="organization",
        object_id=row.id, before=before, after={"name": row.name, "status": row.status},
    )
    return {"organization": _org_view(db, row)}
