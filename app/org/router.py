"""부서·직책 관리 API (admin+, CSRF, 감사).

⚠ 이 파일에는 `from __future__ import annotations`를 넣지 않는다(CLAUDE.md §8).
아래는 라우터 '팩토리'다 — 지연 평가된 문자열 애노테이션은 팩토리 지역 이름
(model 등)을 모듈 전역에서 찾지 못해 FastAPI의 의존성 해석이 깨진다.

부서와 직책은 규칙이 같으므로 라우터를 한 번 만들어 두 번 쓴다. 두 벌로 적으면
한쪽에만 CSRF나 감사가 빠지는 식으로 갈라진다.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.org.models import Department, JobTitle
from app.org.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
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
    usage_count,
)
from app.org.tree import tree_rows



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
