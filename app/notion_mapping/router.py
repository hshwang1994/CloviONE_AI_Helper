"""Notion mapping admin API (spec §12.2)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.scope import Principal
from app.core.pagination import PageParams
from app.jobs import repository as jobs_repo
from app.jobs.models import STATUS_QUEUED, STATUS_RUNNING, Job
from app.notion_mapping.models import STATUS_UNMAPPED, UserNotionMapping
from app.notion_mapping.service import (
    manual_map,
    mapping_view,
    mapping_view_for_user,
    resolve_conflict,
    unmap,
    verify_mapping,
)
from app.users.service import get_scoped_user_or_404

router = APIRouter(
    prefix="/api/admin/notion-mapping",
    tags=["admin-notion-mapping"],
    dependencies=[Depends(require_csrf)],
)



class ManualMapRequest(BaseModel):
    notion_user_id: str = Field(min_length=8, max_length=64)
    notion_email: str | None = Field(default=None, max_length=255)


class ResolveConflictRequest(BaseModel):
    notion_user_id: str = Field(min_length=8, max_length=64)


def _sync_idempotency_key(now: datetime) -> str:
    """초 단위로만 결정되는 키.

    이전에는 여기에 난수 조각(``uuid.uuid4().hex[:8]``)을 더 붙였는데, 그러면 호출마다
    키가 무조건 달라져 `jobs_repo.enqueue`의 유니크 제약(unique idempotency_key)이 절대
    걸리지 않는다 — 바로 위 '진행 중인 잡' 조회는 조회와 삽입 사이에 진짜 동시 요청이 끼면
    (둘 다 조회 시점엔 진행 중인 잡을 못 본다) 막지 못하는데, 그 틈을 막아 주는 것이 바로
    이 유니크 키였다. 초 단위 키로 두면 같은 초 안의 진짜 동시 요청은 같은 키로 부딪혀
    두 번째 삽입이 `IntegrityError`로 막히고 첫 번째 잡을 그대로 돌려받는다 — 그러면서도
    분 단위 키가 가졌던 "새 사용자 추가 직후 재동기화가 늦게 반영되는" 문제는 재현하지
    않는다(초 단위라 한 자리만 지나도 새 키를 받는다).
    """
    return f"notionsync:{now.strftime('%Y%m%d%H%M%S')}"


@router.post("/sync", status_code=202, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def sync_all(request: Request, db: Session = Depends(get_db)):
    """전원의 Notion 매핑을 한 번에 맞춘다. 잡을 만들고 바로 돌려준다(202).

    사용자당 '검증'을 누르는 방식은 n8n을 **동기로** 부른다. 그 워크플로는 Notion의 작업·
    프로젝트 DB를 통째로 읽어 9~13초가 걸리고(실측), 12명이면 브라우저를 2분 붙잡으면서
    같은 조회를 12번 반복한다. 한 번 읽어서 전원에게 나눠 주는 것이 맞다.

    화면은 이 잡이 끝나면 매핑 목록을 다시 불러 결과를 본다 — 매핑 행 자체가 결과다.
    """
    now = request.app.state.clock.now()
    # 이미 진행 중(대기·실행)인 동기화 잡이 있으면 그걸 돌려준다 — 신경질적 더블클릭이 같은
    # 조회를 두 번 돌리지 않는다. 진행 중인 게 없으면(예: 사용자를 막 추가한 뒤 다시 누름)
    # 새 조회를 돈다. 분 단위 시간창 키의 "새 사용자 매핑 지연" 문제와 더블클릭 중복을 동시에 해결.
    active = db.execute(
        select(Job)
        .where(Job.job_type == "notion_mapping_sync", Job.status.in_([STATUS_QUEUED, STATUS_RUNNING]))
        .order_by(Job.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if active is not None:
        # 이미 진행 중인 잡을 돌려줄 때 deduplicated 플래그를 명시한다 — 화면은 이 플래그로
        # '이미 진행 중입니다'와 '새로 시작했습니다'를 구분해 안내한다(이 신호가 없으면
        # 더블클릭이 항상 '새로 시작'으로 잘못 보고된다).
        return {"job_id": active.id, "status": active.status, "deduplicated": True}
    key = _sync_idempotency_key(now)
    job = jobs_repo.enqueue(
        db,
        job_type="notion_mapping_sync",
        payload={},
        now=now,
        user_id=request.state.user.id,
        idempotency_key=key,
    )
    if job.status not in (STATUS_QUEUED, STATUS_RUNNING):
        # `enqueue`'s idempotency lookup matches on key alone, regardless of status. The
        # `active` check above already established there is no in-progress job, so a
        # terminal job returned here means the key collided with one that finished within
        # the same second (fast/mocked worker) — that is a fresh sync request, not a
        # duplicate. Retry with a key that cannot collide with the finished job.
        job = jobs_repo.enqueue(
            db,
            job_type="notion_mapping_sync",
            payload={},
            now=now,
            user_id=request.state.user.id,
            idempotency_key=f"{key}:{job.id}",
        )
    record_audit_from_request(
        request, db, action="notion_mapping.sync", object_type="user_notion_mapping",
        object_id=None, after={"job_id": job.id},
    )
    return {"job_id": job.id, "status": job.status}


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_mappings(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    page: PageParams = Depends(),
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=16),
    source: str | None = Query(default=None, max_length=16),
    user_ids: str | None = Query(default=None, max_length=4000),
    archived: bool = Query(
        default=False,
        description="true면 보관된 계정'만' 보여준다. 기본(false)은 보관된 계정을 숨긴다.",
    ),
):
    """사용자를 기준으로 나열한다(매핑 행이 아니라).

    매핑 행은 연결을 시도해야 생기므로, 행만 나열하면 목록이 구조적으로 비어 있고
    행 액션에 도달할 수 없다. 사용자를 기준으로 좌측 조인하면 아직 연결하지 않은
    사람도 'unmapped'으로 보이고, 그 행에서 바로 연결을 시작할 수 있다.

    ``user_ids``는 콘솔이 감사 로그의 행위자, 승인 요청자, 설정 이력의 변경자
    UUID를 사람 이름으로 바꿔 보여줄 때 쓴다. 이 엔드포인트의 READ_ROLES가 그
    화면들의 조회 권한과 일치해서, 권한 없는 사람에게 명부가 새지 않는다.
    """
    from app.users.models import User

    from app.core.scope import apply_user_scope

    stmt = select(User, UserNotionMapping).outerjoin(
        UserNotionMapping, UserNotionMapping.user_id == User.id
    )
    # **같은 명부를 옆문으로 전부 보게 두지 않는다** (2순위 #2). `/api/admin/users` 는 범위를
    # 거는데 이 화면은 안 걸었다 — 같은 역할 게이트를 지나면서 같은 사람 목록(이메일 포함)을
    # 그대로 내줬다. `apply_user_scope` 는 users 화면이 쓰는 바로 그 함수다(규칙을 두 벌로
    # 만들지 않는다).
    stmt = apply_user_scope(stmt, principal.scope)
    # 보관된 계정은 목록·검색·로그인에서 뺀다(User.archived_at 규약, Users 화면과 동일).
    # 이 목록은 사용자를 기준으로 나열하므로 보관 계정이 활성 직원과 섞여 보이면 안 된다
    # (동기화 잡도 보관 계정을 건너뛴다). archived=true일 때만 '보관함'을 따로 연다.
    stmt = stmt.where(
        User.archived_at.is_not(None) if archived else User.archived_at.is_(None)
    )
    if user_ids:
        wanted = [s.strip() for s in user_ids.split(",") if s.strip()]
        stmt = stmt.where(User.id.in_(wanted))
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(User.email).like(needle), func.lower(User.display_name).like(needle))
        )
    if status:
        if status == STATUS_UNMAPPED:
            # 행이 없는 사용자도 '연결 안 됨'이다 — 둘을 같은 것으로 취급한다.
            stmt = stmt.where(
                or_(UserNotionMapping.id.is_(None), UserNotionMapping.status == STATUS_UNMAPPED)
            )
        else:
            stmt = stmt.where(UserNotionMapping.status == status)
    # 출처(수동/워크플로) 필터는 서버측에서 한다 — 예전엔 clientFilter라 서버 페이지네이션과
    # 겹쳐 현재 페이지만 걸러져 다른 페이지의 수동 매핑을 조용히 숨겼다(round30 감사 E).
    # 매핑 행이 있어야 source가 있으므로, source 필터는 자연히 연결된 사용자만 남긴다.
    if source:
        stmt = stmt.where(UserNotionMapping.source == source)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(User.email).offset(page.offset).limit(page.page_size)
    ).all()
    return {
        "items": [mapping_view_for_user(user, row) for user, row in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


@router.get("/{user_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_mapping(user_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    """단일 사용자의 Notion 매핑 조회.

    관리자 콘솔은 이 엔드포인트를 호출한다: notion-mapping 화면의 user_id 딥링크
    (registry.js onQuery `{open:'select', id: p.user_id}` → DataScreen이
    GET /api/admin/notion-mapping/{user_id} 호출)가 이 경로를 탄다. Users 화면의
    'Notion 연결 확인 → 화면에서 확인하기' 딥링크가 이 메커니즘을 쓴다. 따라서
    이 라우트 제거/동작 변경을 '안전한 정리'로 착각하면 안 된다.

    조회(GET)는 행을 만들지 않는다 — 예전엔 get_or_create_mapping을 불러 단순
    조회가 UserNotionMapping 행을 INSERT하는 부작용(감사 로그도 없는 GET-triggered
    write)을 냈다. 이제 list_mappings와 같은 방식으로, 행이 없으면 메모리상에서
    'unmapped' 뷰를 만들어 돌려준다(mapping_view_for_user).
    """
    # 범위 밖은 **404** (저장소 규칙 — 관리자 라우터의 모든 /{user_id} 경로가
    # `get_scoped_user_or_404` 하나를 통과해야 한다). 여기만 예외였다.
    user = get_scoped_user_or_404(db, user_id, principal.scope)
    row = db.execute(
        select(UserNotionMapping).where(UserNotionMapping.user_id == user_id)
    ).scalar_one_or_none()
    return {"mapping": mapping_view_for_user(user, row)}


@router.post("/{user_id}/verify", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def verify(request: Request, user_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    # 범위 밖은 **404** (저장소 규칙 — 관리자 라우터의 모든 /{user_id} 경로가
    # `get_scoped_user_or_404` 하나를 통과해야 한다). 여기만 예외였다.
    user = get_scoped_user_or_404(db, user_id, principal.scope)
    row = verify_mapping(
        db, user,
        outbound=request.app.state.outbound_client,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="notion_mapping.verify", object_type="user_notion_mapping",
        object_id=user_id, after={"status": row.status},
    )
    return {"mapping": mapping_view(row, user)}


@router.post("/{user_id}/map", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def map_manual(
    request: Request, user_id: str, payload: ManualMapRequest, db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 범위 밖은 **404** (저장소 규칙 — 관리자 라우터의 모든 /{user_id} 경로가
    # `get_scoped_user_or_404` 하나를 통과해야 한다). 여기만 예외였다.
    user = get_scoped_user_or_404(db, user_id, principal.scope)
    row = manual_map(
        db, user,
        notion_user_id=payload.notion_user_id,
        notion_email=payload.notion_email,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request, db, action="notion_mapping.manual_map", object_type="user_notion_mapping",
        object_id=user_id, after={"status": row.status},
    )
    return {"mapping": mapping_view(row, user)}


@router.post("/{user_id}/unmap", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def unmap_user(request: Request, user_id: str, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    # 범위 밖은 **404** (저장소 규칙 — 관리자 라우터의 모든 /{user_id} 경로가
    # `get_scoped_user_or_404` 하나를 통과해야 한다). 여기만 예외였다.
    user = get_scoped_user_or_404(db, user_id, principal.scope)
    row = unmap(db, user_id)
    record_audit_from_request(
        request, db, action="notion_mapping.unmap", object_type="user_notion_mapping",
        object_id=user_id,
    )
    return {"mapping": mapping_view(row, user)}


@router.post("/{user_id}/resolve-conflict", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def resolve(
    request: Request, user_id: str, payload: ResolveConflictRequest, db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    # 범위 밖은 **404** (저장소 규칙 — 관리자 라우터의 모든 /{user_id} 경로가
    # `get_scoped_user_or_404` 하나를 통과해야 한다). 여기만 예외였다.
    user = get_scoped_user_or_404(db, user_id, principal.scope)
    row = resolve_conflict(
        db, user, notion_user_id=payload.notion_user_id, now=request.app.state.clock.now()
    )
    record_audit_from_request(
        request, db, action="notion_mapping.resolve_conflict",
        object_type="user_notion_mapping", object_id=user_id, after={"status": row.status},
    )
    return {"mapping": mapping_view(row, user)}
