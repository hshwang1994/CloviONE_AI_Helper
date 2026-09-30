"""부서·직책 관리 API (admin+, CSRF, 감사).

⚠ 이 파일에는 `from __future__ import annotations`를 넣지 않는다(CLAUDE.md §8).
아래는 라우터 '팩토리'다 — 지연 평가된 문자열 애노테이션은 팩토리 지역 이름
(model 등)을 모듈 전역에서 찾지 못해 FastAPI의 의존성 해석이 깨진다.

부서와 직책은 규칙이 같으므로 라우터를 한 번 만들어 두 번 쓴다. 두 벌로 적으면
한쪽에만 CSRF나 감사가 빠지는 식으로 갈라진다.
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_insert_race, write_conflict_backoff
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.scope import Principal
from app.authz.permissions import ORG_MANAGE
from app.core.deps import get_db, get_principal, require_csrf, require_permission
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
from app.core.scope import require_global_management
from app.org.service import (
    bulk_child_department_count,
    bulk_usage_count,
    create_item,
    delete_item,
    delete_precheck,
    detached_message,
    ensure_may_suspend_org,
    get_or_404,
    item_view,
    list_items,
    scope_clause,
    update_item,
    normalize_name,
    usage_count,
)
from app.org.tree import tree_rows
from app.users.models import User



def _audit_if_changed(
    request: Request, db: Session, *, action: str, object_type: str, object_id: str,
    before: dict, after: dict,
) -> bool:
    """**바뀐 것이 있을 때만** 감사 행을 남긴다. 남겼으면 True.

    감사 로그는 「무엇이 언제 바뀌었나」를 읽는 곳이다. 값이 하나도 안 바뀐 '수정' 행이
    섞이면 조사자는 그 시각에 무언가 일어난 줄 알고 시간을 쓴다. 빈 본문 PATCH 도, 같은
    값을 다시 보낸 PATCH 도 200 은 그대로 돌려준다 — 응답이 아니라 기록의 문제다.

    화면은 이미 바뀐 것이 없으면 요청 자체를 안 보내지만(`orgModals.jsx::diffFields`),
    API·가져오기·연동은 그대로 보낸다. 그래서 판정은 서버에 있어야 한다.
    """
    if before == after:
        return False
    record_audit_from_request(
        request, db, action=action, object_type=object_type, object_id=object_id,
        before=before, after=after,
    )
    return True


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
        dependencies=[Depends(require_permission(ORG_MANAGE)), Depends(require_csrf)],
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
        rows = list_items(db, model, active=active, scope=principal.management)
        names = _org_names(db, rows)
        # UA-16: 행마다 usage_count()를 부르면 목록 N건에 질의 N번이었다(_org_names 바로
        # 위 두 줄은 이미 그룹 질의였는데 이쪽만 안 고쳐져 있었다) — 한 번에 센다.
        counts = bulk_usage_count(db, model, [row.id for row in rows])
        # UA-20R: 부서만 자식 수도 함께 준다(직책은 트리가 없다) — 목록 N건에 질의를 또
        # 하나 늘리지 않도록 model is Department일 때만 그룹 질의 한 번을 더 한다.
        child_counts = (
            bulk_child_department_count(db, [row.id for row in rows])
            if model is Department else {}
        )
        # 몇 명이 쓰는지 보이지 않으면 관리자는 지워도 되는지 판단할 수 없다.
        return {
            "items": [
                item_view(
                    row,
                    user_count=counts.get(row.id, 0),
                    org_name=names.get(getattr(row, "org_id", None)),
                    child_department_count=child_counts.get(row.id, 0) if model is Department else None,
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
            return {"items": tree_rows(db, active=active, scope=principal.management)}

    @router.get("/{item_id}")
    def get_org_item(item_id: str, db: Session = Depends(get_db),
                     principal: Principal = Depends(get_principal)):
        # 감사/알림이 job_title·department를 참조할 때 '관련 항목 보기'로 그 행 하나를
        # 열 수 있게 단건 조회를 연다(다른 CRUD 화면과 동일한 딥링크 패턴, round30 감사 E).
        row = get_or_404(db, model, item_id, principal.management)
        names = _org_names(db, [row])
        child_count = (
            bulk_child_department_count(db, [row.id]).get(row.id, 0)
            if model is Department else None
        )
        body = item_view(
            row,
            user_count=usage_count(db, model, row.id),
            org_name=names.get(getattr(row, "org_id", None)),
            child_department_count=child_count,
        )
        if model is Department:
            # **삭제 판정은 서버가 한 번만 내린다** (org-01). 상세 판이 자기 계산으로
            # 「지금 삭제할 수 있습니다」라고 말하던 시절에는 인원과 하위 부서 둘만 세어,
            # 프로젝트·지식 공간·팀 채팅방이 매달린 부서에서 눌러 보면 409 였다. 갈래·건수·
            # 라벨·이유 문장을 여기서 실어 화면이 그리기만 하게 한다.
            body["delete_precheck"] = delete_precheck(db, row.id)
        return {body_key: body}

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
            scope=principal.management,
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
        row = get_or_404(db, model, item_id, principal.management)
        before = item_view(row)
        fields = payload.model_dump(exclude_unset=True)
        # 상위 부서도 범위를 지난다 — 생성만 막으면 수정으로 같은 일을 한다.
        update_item(db, row, scope=principal.management, **fields)
        _audit_if_changed(
            request, db, action=f"{audit_type}.update", object_type=audit_type,
            object_id=row.id, before=before, after=item_view(row),
        )
        return {body_key: item_view(row, user_count=usage_count(db, model, row.id))}

    @router.delete("/{item_id}")
    def delete_org_item(request: Request, item_id: str, db: Session = Depends(get_db),
                        principal: Principal = Depends(get_principal)):
        row = get_or_404(db, model, item_id, principal.management)
        before = item_view(row)
        # 쓰는 사람이 있으면 여기서 409로 막힌다. 막지 않는 갈래(팀 채팅방·옛 문서 기록)는
        # 같은 트랜잭션에서 연결만 끊고 무엇을 끊었는지 돌려준다.
        detached = delete_item(db, row)
        record_audit_from_request(
            request, db, action=f"{audit_type}.delete", object_type=audit_type,
            object_id=item_id, before=before,
            # 끊은 것을 기록에 남긴다 — 나중에 「이 방이 왜 부서를 잃었나」를 물을 사람에게
            # 답이 있어야 한다.
            after={"detached": detached} if detached else None,
        )
        body = {"ok": True}
        if detached:
            body["detached"] = detached
            body["message"] = detached_message(detached)
        return body

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
    dependencies=[Depends(require_permission(ORG_MANAGE)), Depends(require_csrf)],
)


def _scope_departments(stmt, scope):
    """조직 안 부서를 세는 질의에 **관리 범위를 건다** (org-12).

    범위 관리자에게 보이는 숫자는 그가 볼 수 있는 것과 같은 모집단이어야 한다. 트리는
    범위를 지나는데(`app/org/tree.py`) 이 숫자는 안 지나서, 한 화면에서 요약 타일은
    「1 부서」, 조직 상세 판은 「3 부서」라고 말했다 — 관리자는 어느 쪽을 믿을지 알 수 없고
    「내가 못 보는 부서가 둘 더 있다」는 사실 자체가 범위 밖 정보다.

    판정은 목록·트리가 쓰는 `scope_clause` 그대로다 — 여기서 두 번째 규칙을 만들지 않는다.
    """
    clause = scope_clause(scope, Department)
    return stmt if clause is None else stmt.where(clause)


def _scope_users(stmt, scope):
    """인원을 세는 질의에 범위를 건다. 사람을 세는 규칙은 사용자 목록과 같아야 한다 —
    그래서 `app/org/tree.py::_org_user_counts` 와 **같은 함수**(`apply_user_scope`)를 쓴다."""
    from app.core.scope import apply_user_scope

    return stmt if scope is None else apply_user_scope(stmt, scope)


def _bulk_org_counts(
    db: Session, org_ids: list[str], scope=None
) -> tuple[dict[str, int], dict[str, int]]:
    """(부서 수, 인원 수) 그룹 질의 — UA-16: 목록에서 `_org_view`를 행마다 부르면 조직 하나당
    COUNT 두 번, 목록 N건에 질의 2N번이었다. 안 쓰는 id는 딕셔너리에 없다(호출부가 `.get`)."""
    ids = {i for i in org_ids if i}
    if not ids:
        return {}, {}
    dept_rows = db.execute(
        _scope_departments(select(Department.org_id, func.count()), scope)
        .where(Department.org_id.in_(ids)).group_by(Department.org_id)
    ).all()
    user_rows = db.execute(
        _scope_users(select(User.org_id, func.count()), scope)
        .where(User.org_id.in_(ids)).group_by(User.org_id)
    ).all()
    return {r[0]: r[1] for r in dept_rows}, {r[0]: r[1] for r in user_rows}


def _org_view(
    db: Session, row: Organization, *,
    dept_counts: dict[str, int] | None = None, user_counts: dict[str, int] | None = None,
    scope=None,
) -> dict:
    """조직 한 곳 + **그 안에 무엇이 들어 있는지**. 숫자가 곧 포함 관계의 요약이다.

    `dept_counts`/`user_counts`를 주면(목록에서 `_bulk_org_counts`로 미리 구한 것) 그
    딕셔너리를 쓴다 — 단건 조회(get/create/update)는 안 주므로 그때만 개별 COUNT를 한다.

    `scope` 는 목록·단건이 **같은 모집단**을 세게 한다(org-12). 안 주면 전체를 센다 —
    범위를 안 건 것이 코드에 드러나야 하므로 기본값으로 조용히 넓히지 않는다.

    ## `can_edit` 은 화면이 다시 계산하지 않게 하려고 싣는다

    조직 이름·상태를 바꾸는 PATCH 는 `require_global_management` 를 지난다(org-07). 그런데
    이 응답은 범위를 좁힌 관리자에게도 자기 조직 행을 준다 — 그 사람의 상세 판은 「수정」
    버튼을 그려 놓고, 저장할 때가 되어서야 403 을 받는다. 같은 판이 「비활성화」에 대해서는
    이미 판정을 재현하고 안내까지 붙이므로(`OrgDetailPanel.jsx`), 판정의 정본인 서버가
    (D-194) 답을 함께 실어 준다. 화면이 같은 규칙을 다시 적으면 반드시 갈라진다 —
    부서 삭제(`delete_precheck`)가 같은 이유로 이미 그렇게 한다.

    `scope` 를 안 받았으면 `False` 다. **모르면 좁게 답한다** — 넓게 틀리면 버튼이 서고,
    그 버튼은 눌러 봐야 403 이다.
    """
    dept_count = (
        dept_counts.get(row.id, 0) if dept_counts is not None
        else db.execute(
            _scope_departments(
                select(func.count()).select_from(Department), scope
            ).where(Department.org_id == row.id)
        ).scalar_one()
    )
    user_count = (
        user_counts.get(row.id, 0) if user_counts is not None
        else db.execute(
            _scope_users(select(func.count()).select_from(User), scope)
            .where(User.org_id == row.id)
        ).scalar_one()
    )
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "status": row.status,
        "department_count": dept_count,
        "user_count": user_count,
        # `update_organization` 의 `require_global_management` 와 **같은 술어**다
        # (`Principal.manages_everything` 이 곧 `management.is_global` 이다).
        "can_edit": bool(scope is not None and scope.is_global),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _get_org_or_404(db: Session, org_id: str) -> Organization:
    row = db.get(Organization, org_id)
    if row is None:
        raise NotFoundError("조직을 찾을 수 없습니다.")
    return row


def _ensure_org_name_is_free(db: Session, name: str, *, keep_id: str | None = None) -> None:
    """조직 이름 중복을 막는다 (org-11). 대소문자만 다른 이름도 같은 이름으로 본다.

    조직은 이 제품의 **테넌트 경계**다. 이름이 완전히 같은 조직이 둘이면 트리에 같은 줄이
    두 개 서고, 「부서 추가」의 조직 선택기도 라벨이 같아 어느 회사에 부서를 만드는지 화면만
    봐서는 끝내 알 수 없다. 같은 콘솔의 부서·직책 명부가 이미 이름 중복을 409 로 막는다
    (`service.create_item`) — 조직만 뚫려 있었다.

    유니크 제약은 `slug` 에만 있어 이 검사는 사전 검사다. 동시에 같은 이름 둘이 들어오면
    둘 다 통과할 수 있지만, 이 검사가 막으려는 것은 경합이 아니라 **사람의 실수**다.
    """
    stmt = select(Organization).where(func.lower(Organization.name) == name.lower())
    if keep_id is not None:
        stmt = stmt.where(Organization.id != keep_id)
    if db.execute(stmt).scalars().first() is not None:
        raise ConflictError(f"이미 있는 조직입니다: {name}")


def _visible_org_or_404(db: Session, org_id: str, principal) -> Organization:
    """내 범위 안의 조직만. 밖은 **404** (존재를 알려 주지 않는다).

    부서·직책은 이미 범위를 지나는데 **조직 자체는 안 지나고 있었다** — 같은 파일 안에서
    규칙이 갈려 있었다. 멀티테넌트에서 조직 목록은 곧 **테넌트 명부**다(이름·식별자·부서
    수·인원수). 다른 고객사의 존재와 규모가 콘솔 쓰기 권한자 누구에게나 보이면 안 된다.
    """
    row = _get_org_or_404(db, org_id)
    # ⚠️ `getattr(principal, "scope", ...)` 로 부드럽게 읽지 않는다. 예전에 그렇게 적혀
    # 있었는데, 0060 이 `Principal.scope` 를 `visibility`/`management` 둘로 쪼개자 그
    # getattr 이 조용히 `None` 을 돌려주고 **필터가 통째로 사라졌다**(다른 조직이 그대로
    # 열렸다). 없는 속성을 관대하게 넘기는 코드는 리팩터링 때 fail-open 으로 변한다.
    scope = principal.management
    if scope.is_global:
        return row
    if row.id != scope.org_id:
        raise NotFoundError("조직을 찾을 수 없습니다.")
    return row


@organizations_router.get("")
def list_organizations(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    stmt = select(Organization).order_by(Organization.name)
    # 전역 범위가 아니면 자기 조직만. 부서 범위 관리자도 마찬가지다 — 부서는 조직 안에 있고,
    # 그 사람이 다른 조직의 존재를 알아야 할 이유가 없다.
    # (getattr 로 읽지 않는 이유는 위 `_visible_org_or_404` 주석 참조.)
    scope = principal.management
    if not scope.is_global:
        stmt = stmt.where(Organization.id == scope.org_id)
    rows = list(db.execute(stmt).scalars())
    dept_counts, user_counts = _bulk_org_counts(db, [r.id for r in rows], scope)
    return {
        "items": [
            _org_view(db, r, dept_counts=dept_counts, user_counts=user_counts, scope=scope)
            for r in rows
        ],
        "total": len(rows),
    }


@organizations_router.get("/{org_id}")
def get_organization(
    org_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    return {"organization": _org_view(
        db, _visible_org_or_404(db, org_id, principal), scope=principal.management
    )}


# 후속 재감사(2026-08-15)에서 발견: 아래 slug 중복 사전 검사와 db.add/flush 사이에
# SAVEPOINT/재시도가 없었다 — Organization.slug가 실제 UNIQUE라, 동시에 같은 slug로
# 두 번 POST하면 사전 검사를 둘 다 통과하고 나중 flush()가 처리되지 않은
# IntegrityError/OperationalError("database is locked")로 500을 냈다 — PA-RC-0008이
# 승격한 패턴인데 이 호출부만 빠져 있었다(app/org/service.py::create_item과 같은 발견).
_CREATE_ORG_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES


@organizations_router.post("", status_code=201)
def create_organization(
    request: Request,
    payload: OrganizationCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # UA-11: 목록·단건·수정은 scope.org_id로 좁히는데(_visible_org_or_404) 생성만 무방비였다
    # — 조직 자체를 만드는 것은 테넌트를 새로 여는 일이라 전역 관리자만 할 수 있어야 한다.
    # dept/org 범위 admin도 CONSOLE_WRITE_ROLES(role="admin")는 통과하므로(role과 admin_scope는
    # 서로 다른 축이다) 라우터 데코레이터의 권한 게이트만으로는 못 막는다 — quotas/router.py
    # 의 _ensure_may_touch_global과 같은 이유로 403(그 행의 존재는 이미 화면에 드러나 있으니
    # 문제는 존재가 아니라 권한이다).
    if not principal.management.is_global:
        raise ForbiddenError("조직 생성은 전체 범위 관리자만 할 수 있습니다.")
    name = normalize_name(payload.name)
    slug = payload.slug.strip().lower()
    exists = db.execute(
        select(Organization).where(Organization.slug == slug)
    ).scalar_one_or_none()
    if exists is not None:
        # 이미 있는 자원과의 충돌은 409 다 (org-10). 같은 콘솔의 부서·직책 명부가 같은
        # 사건에 `ConflictError` 를 던지는데(`service.create_item`) 조직만 422 였다 —
        # 화면 문구는 같아 보여도 API 를 쓰는 쪽은 코드로 분기하므로 그 분기가 틀렸다.
        raise ConflictError(f"이미 있는 식별자입니다: {slug}")
    _ensure_org_name_is_free(db, name)
    row = Organization(slug=slug, name=name, status=ORG_ACTIVE)
    for attempt in range(_CREATE_ORG_RETRIES):
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            break
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            if attempt == _CREATE_ORG_RETRIES - 1:
                # 예산 소진 — 사전 검사가 잡았을 때와 같은 오류로 통일한다(둘 다 409).
                raise ConflictError(f"이미 있는 식별자입니다: {slug}") from None
            try:
                # app/org/service.py::create_item과 같은 이유 — 스냅샷을 새로 뜨는 이
                # commit 자체도 심한 경합에서 거부될 수 있다.
                db.commit()
            except (IntegrityError, OperationalError) as commit_exc:
                if not is_insert_race(commit_exc):
                    raise
                db.rollback()
            time.sleep(write_conflict_backoff(attempt))
    record_audit_from_request(
        request, db, action="organization.create", object_type="organization",
        object_id=row.id, after={"slug": slug, "name": name},
    )
    return {"organization": _org_view(db, row, scope=principal.management)}


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
    # 그리고 생성·정지와도 **같은 문**을 지난다 (org-07). 조직 이름은 테넌트의 정체라
    # 로그인 화면·머리·프로필·감사 로그에 그대로 나간다 — 부서 하나를 맡은 관리자가 회사
    # 이름을 바꿀 업무상 이유가 없고, 같은 라우터의 다른 두 동작은 이미 범위를 판정한다.
    # 범위 밖 단일 자원은 404 지만 이 행의 존재는 이미 화면에 있으므로 403 이다.
    require_global_management(principal, "조직 정보")
    changes = payload.model_dump(exclude_unset=True)
    before = {"name": row.name, "status": row.status}
    if "name" in changes:
        name = normalize_name(changes["name"] or "")
        _ensure_org_name_is_free(db, name, keep_id=row.id)
        row.name = name
    if "status" in changes:
        status = (changes["status"] or "").strip()
        if status not in (ORG_ACTIVE, ORG_SUSPENDED):
            raise ValidationAppError(
                f"상태는 {ORG_ACTIVE} 또는 {ORG_SUSPENDED} 여야 합니다."
            )
        was = before["status"]
        if status == ORG_SUSPENDED:
            # 자기 조직 정지는 포탈 운영자만 — 아래 `_revoke_org_sessions` 가 요청한 사람의
            # 세션까지 끊어 정지를 풀 사람이 조직 안에 남지 않기 때문이다. 상태를 바꾸기
            # **전에** 판정해야 403 이 아무것도 바꾸지 않은 채로 돌아간다.
            ensure_may_suspend_org(request.state.user, row.id)
        row.status = status
        if status == ORG_SUSPENDED and was != ORG_SUSPENDED:
            # **즉시** 끊는다. 안 그러면 이미 로그인해 있는 사람은 세션이 만료될 때까지
            # (최대 8시간) 계속 쓴다 — 관리자는 정지했다고 믿는 동안이다.
            # 역할·범위 변경과 같은 급의 권한 변경이므로 같은 처리를 한다.
            revoked = _revoke_org_sessions(request, db, row.id)
            before["revoked_sessions"] = revoked
    db.flush()
    # 바뀐 것이 없으면 감사 행도 없다 (org-13) — 부서·직책과 같은 판정을 함께 쓴다.
    # `revoked_sessions` 는 정지가 실제로 일어났을 때만 붙으므로 비교를 흐리지 않는다.
    _audit_if_changed(
        request, db, action="organization.update", object_type="organization",
        object_id=row.id, before=before, after={"name": row.name, "status": row.status},
    )
    return {"organization": _org_view(db, row, scope=principal.management)}
