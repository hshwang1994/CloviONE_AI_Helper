"""Prompt and Policy version-management API (spec §17, §23.5).

NOTE: no ``from __future__ import annotations`` here — the router factory
annotates endpoint params with closure variables (``payload: create_schema``),
which must stay real class objects for FastAPI to see them as request bodies.
"""

import json as _json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator


def _json_object_to_str(value: object) -> object:
    """관리자 콘솔의 JSON 입력 필드는 파싱된 객체(dict/list)를 보낸다. 백엔드는 JSON 문자열을
    저장(content_json)하므로 여기서 직렬화해 둘 다(콘솔=객체, 외부 API=문자열)를 받는다.
    빈 값(None)은 빈 객체로 본다. 문자열은 그대로 둔다 — 프롬프트 본문(자유 텍스트)은 영향 없다."""
    if isinstance(value, (dict, list)):
        return _json.dumps(value, ensure_ascii=False)
    if value is None:
        return "{}"
    return value
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.db import is_insert_race
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.core.errors import ConflictError, ValidationAppError
from app.core.scope import Principal, require_global_management
from app.prompts.models import STATUS_DRAFT, STATUS_PUBLISHED, Policy, Prompt
from app.prompts.service import (
    diff_versions,
    get_or_404,
    new_version_from,
    rollback_to_version,
    transition,
    update_draft,
    validate_policy_content,
)


# 화면에 그대로 나가는 주어다 — `require_global_management` 가 받침을 보고 조사를 붙인다
# ("프롬프트는 전체 범위 관리자만 바꿀 수 있습니다.").
_GLOBAL_SUBJECT = {"prompts": "프롬프트", "policies": "정책"}


def _clean_name(value: str) -> str:
    """이름은 공백만으로 이뤄질 수 없고, 앞뒤 공백은 이름의 일부가 아니다.

    `app/org/service.py::normalize_name` 이 부서·직책에 쓰는 규칙과 같은 규칙이다. 여기만
    비어 있으면 두 가지가 깨진다. 첫째, 목록·사용 통계·이름 필터에 이름 칸이 빈 행이 남아
    관리자가 그 행을 가리킬 방법이 없다. 둘째, ' 티켓 요약' 과 '티켓 요약' 이 서로 다른
    이름이 되어 같은 이름을 막는 중복 검사(409)와 버전 묶음이 그대로 갈라진다.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("이름을 입력해야 합니다.")
    return cleaned


class PromptCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="", max_length=100000)

    _normalize_name = field_validator("name")(_clean_name)


class PolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # WF1 단독 결함 — Prompt와 대칭. app/prompts/models.py::Policy.purpose(0058) 참고.
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="{}", max_length=100000)

    _normalize_name = field_validator("name")(_clean_name)
    _coerce_content = field_validator("content", mode="before")(_json_object_to_str)


# UB-22: 예전엔 이 하나(ContentUpdateRequest)를 prompts/policies 둘 다에 썼다.
# `_json_object_to_str`의 `None → "{}"` 분기가 콘솔의 "빈 JSON 입력란"(Policy)을 위한
# 것인데 타입 게이트가 없어, `PATCH prompts/{id} {"content": null}`(자유 텍스트여야
# 하는 Prompt 본문)도 그대로 통과해 422 검증 오류 대신 **문자열 리터럴 "{}"가 본문에
# 저장**됐다 - create() 이 이미 kind별로 스키마를 나눠 두고 있던 것(PromptCreateRequest/
# PolicyCreateRequest)과 같은 모양으로 patch()도 나눈다.
#
# 🔴 PATCH 는 **부분 갱신**이다 — 아래 두 스키마의 기본값은 저장 경로에 절대 닿지 않는다.
# 콘솔(DataScreen)은 바뀐 필드만 보낸다. 예전에는 정책의 `content` 기본값 `"{}"` 가 그대로
# 저장돼, 「용도」한 줄만 고쳐도 규칙 전체가 빈 객체로 지워지고 응답은 200 이었다(같은 요청이
# 프롬프트에서는 `content` 가 필수라 422 였다 — 쌍둥이 화면의 답이 서로 달랐다). 그래서
# 보낸 칸은 `model_fields_set` 으로만 판정하고(`_sent_changes`), 안 보낸 칸은 손대지 않는다.
class PromptContentUpdateRequest(BaseModel):
    content: str = Field(default="", max_length=100000)
    purpose: str | None = Field(default=None, max_length=2000)


class PolicyContentUpdateRequest(BaseModel):
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="{}", max_length=100000)

    _coerce_content = field_validator("content", mode="before")(_json_object_to_str)


def _sent_changes(payload: BaseModel) -> dict:
    """요청 본문에 **실제로 실려 온 칸만** 뽑는다.

    `payload.content` 를 그냥 읽으면 「안 보냈다」와 「기본값」이 같은 값으로 보여 구별할 수
    없다. `model_fields_set` 은 그 둘을 가르는 유일한 근거다(`app/knowledge/schemas.py::
    DocumentSave.category_id` 가 같은 규약을 쓴다). `purpose` 의 `null` 은 「용도를 지운다」는
    뜻으로 받는다 — 안 보낸 것과 다른 사실이다.
    """
    sent = payload.model_fields_set
    return {field: getattr(payload, field) for field in ("content", "purpose") if field in sent}


class TransitionRequest(BaseModel):
    status: str


class RollbackRequest(BaseModel):
    # UB-30: 형제 엔드포인트 diff()의 name 쿼리 파라미터는 이미 max_length=120(Prompt/
    # Policy.name의 DB 컬럼 String(120)과 같은 값)을 걸어 두는데 여기만 무제한이었다.
    name: str = Field(max_length=120)
    version: int


# created_by is stored as a raw user id. Every view below also exposes
# created_by_name/created_by_email (resolved via _resolve_creator_names,
# same pattern as the audit log's actor_name) so the admin console can show
# a display name instead of a bare UUID — created_by itself is kept for API
# stability.
def _creator_fields(created_by: str | None, names: dict) -> dict:
    creator = names.get(created_by, {}) if created_by else {}
    return {
        "created_by": created_by,
        "created_by_name": creator.get("display_name"),
        "created_by_email": creator.get("email"),
    }


def _prompt_view(row: Prompt, names: dict | None = None) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "version": row.version,
        "content": row.content,
        "status": row.status,
        **_creator_fields(row.created_by, names or {}),
        "created_at": row.created_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _policy_view(row: Policy, names: dict | None = None) -> dict:
    import json

    return {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "version": row.version,
        "content": json.loads(row.content_json),
        "status": row.status,
        **_creator_fields(row.created_by, names or {}),
        "created_at": row.created_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _resolve_creator_names(db: Session, ids) -> dict:
    from app.users.models import User

    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    result: dict[str, dict[str, str]] = {}
    for u in db.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(wanted))
    ).all():
        result[u.id] = {"display_name": u.display_name, "email": u.email}
    return result


def _build_router(kind: str, model, view, create_schema, content_update_schema):
    router = APIRouter(
        prefix=f"/api/admin/{kind}",
        tags=[f"admin-{kind}"],
        dependencies=[Depends(require_csrf)],
    )

    def _view_single(db: Session, row) -> dict:
        names = _resolve_creator_names(db, {row.created_by} if row.created_by else set())
        return view(row, names)

    @router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def list_all(
        db: Session = Depends(get_db),
        name: str | None = Query(default=None, max_length=120),
        status: str | None = Query(default=None, max_length=16),
        page: int = Query(default=1, ge=1),
        # Default kept at the old hardcoded .limit(500) so existing callers
        # (registry.js does not yet set paginated:true / pass page params —
        # see finding) keep seeing everything they used to in one call. What
        # changes is that results are no longer SILENTLY truncated past 500:
        # `total` is now returned so a caller can detect truncation, and a
        # caller that needs more can page explicitly.
        page_size: int = Query(default=500, ge=1, le=500),
    ):
        stmt = select(model)
        if name:
            stmt = stmt.where(model.name == name)
        if status:
            stmt = stmt.where(model.status == status)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = (
            db.execute(
                # 🔴 마지막 절이 PK 다 — **전순서**여야 한다. `(name, version)` 은 실무상
                # 유일하지만 계약으로 보장되지 않고, 전순서가 아니면 OFFSET 페이징이 같은 행을
                # 두 묶음에 내거나 아예 빠뜨린다(그 어긋남은 오류를 안 낸다).
                # 같은 이유를 `app/knowledge/service.py::_order_by` 가 이미 적어 뒀다(Z9).
                stmt.order_by(model.name, model.version.desc(), model.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        names = _resolve_creator_names(db, {r.created_by for r in rows if r.created_by})
        return {
            "items": [view(r, names) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _require_global(principal: Principal) -> None:
        """프롬프트와 정책은 **포탈 전체**가 함께 쓰는 자원이라 전역 관리자만 바꾼다.

        부서로 나뉘는 자원이 아니다 — 같은 이름의 발행본 하나를 전 부서가 참조하고, 스케줄이
        그 이름을 가리킨다. 부서 범위 관리자가 발행본을 보관하면 다른 팀의 자동화가 근거를
        잃고, 롤백 한 번으로 전사 AI 지시문이 그 사람이 만든 버전으로 바뀐다. 같은 성격의
        공지(`app/announcements/router.py`)와 전역 쿼터(`app/quotas/router.py`)는 이미
        403 을 내고 있었고, 여기만 열려 있던 것은 설계가 아니라 누락이었다.

        읽기는 좁히지 않는다 — 부서 관리자도 지금 무엇이 쓰이는지 볼 수 있어야 한다.
        """
        require_global_management(principal, _GLOBAL_SUBJECT[kind])

    @router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def create(
        request: Request,
        payload: create_schema,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        # Existence check only — a name legitimately has many versions, so
        # limit(1) avoids MultipleResultsFound (which would surface as HTTP 500).
        existing = db.execute(
            select(model.id).where(model.name == payload.name).limit(1)
        ).first()
        if existing is not None:
            raise ConflictError(
                f"이미 존재하는 이름입니다: {payload.name}: new-version을 사용하세요."
            )
        content = payload.content
        if model is Policy:
            validate_policy_content(content)
            row = Policy(
                name=payload.name, purpose=payload.purpose, version=1, content_json=content,
                status=STATUS_DRAFT, created_by=request.state.user.id,
            )
        else:
            row = Prompt(
                name=payload.name, purpose=payload.purpose, version=1,
                content=content, status=STATUS_DRAFT,
                created_by=request.state.user.id,
            )
        # UB-21: 위 존재 확인~삽입 사이는 잠기지 않는다(커밋은 요청 끝에 한 번). 같은
        # 이름으로 두 생성 요청이 거의 동시에 오면(더블클릭) 둘 다 "기존 없음"을 보고
        # 각자 version=1 삽입을 시도할 수 있다 - uq_{prompts,policies}_name_version
        # 유일 제약이 진 쪽을 IntegrityError로 막는데, 여태 아무도 안 잡아서 그대로
        # 500으로 샜다. 재시도는 안 한다 - 이건 approvals/new_version_from의 "재시도로
        # 풀리는 경합"이 아니라 "이름이 이미 있다"는 실제 결론이 하나뿐인 경합이라,
        # 위와 같은 메시지로 깨끗한 409를 준다.
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            raise ConflictError(
                f"이미 존재하는 이름입니다: {payload.name}: new-version을 사용하세요."
            ) from exc
        record_audit_from_request(
            # 같은 기능 안에서 create만 단수화(kind[:-1])해 'policies'→'policie.create'로 어긋났고,
            # 나머지 액션은 'policies.update_content'처럼 복수였다. object_type과 동일한 kind로
            # 통일해 감사 액션 접두를 일관되게 한다(round16 제품 스윕).
            request, db, action=f"{kind}.create",
            object_type=kind, object_id=row.id, after={"name": row.name, "version": 1},
        )
        return {"item": _view_single(db, row)}

    @router.get("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def get_one(row_id: str, db: Session = Depends(get_db)):
        return {"item": _view_single(db, get_or_404(db, model, row_id))}

    @router.patch("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def patch(
        request: Request,
        row_id: str,
        payload: content_update_schema,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = get_or_404(db, model, row_id)
        # WF1 단독 결함 — purpose는 이제 Prompt/Policy 둘 다 있다.
        changes = _sent_changes(payload)
        if model is Policy and "content" in changes:
            validate_policy_content(changes["content"])
        update_draft(db, row, **changes)
        record_audit_from_request(
            request, db, action=f"{kind}.update_content", object_type=kind,
            object_id=row.id, after={"name": row.name, "version": row.version},
        )
        return {"item": _view_single(db, row)}

    @router.post("/{row_id}/transition", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def do_transition(
        request: Request,
        row_id: str,
        payload: TransitionRequest,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = get_or_404(db, model, row_id)
        before_status = row.status
        transition(db, row, payload.status, now=request.app.state.clock.now())
        record_audit_from_request(
            request, db, action=f"{kind}.transition", object_type=kind,
            object_id=row.id,
            before={"status": before_status},
            after={"status": row.status, "name": row.name, "version": row.version},
        )
        return {"item": _view_single(db, row)}

    @router.post("/{row_id}/new-version", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def new_version(
        request: Request,
        row_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = get_or_404(db, model, row_id)
        copy = new_version_from(db, row, created_by=request.state.user.id)
        record_audit_from_request(
            request, db, action=f"{kind}.new_version", object_type=kind,
            object_id=copy.id, after={"name": copy.name, "version": copy.version},
        )
        return {"item": _view_single(db, copy)}

    @router.get("/usage/stats", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def usage_stats(db: Session = Depends(get_db)):
        """이름별 사용 통계 (0033, PLAN Phase 6).

        **무엇을 세는가**: 버전 수·발행 버전·마지막 발행 시각은 이 표 자체에서 나오고,
        "실제로 쓰이는가"는 **그것을 가리키는 것**에서 나온다 — 스케줄이 이 이름의 어느
        버전을 참조하는지다. 템플릿과 문서 생성 회차는 S11 이 n8n 과 함께 걷어냈다.

        추측하지 않는다: 참조가 0이면 0으로 보여 준다. "쓰이지 않는 프롬프트"를 알아보는
        것이 이 화면의 목적이므로, 애매하게 감추면 목적이 사라진다.
        """
        from app.schedules.models import Schedule

        rows = db.execute(select(model).order_by(model.name, model.version)).scalars().all()
        by_name: dict[str, list] = {}
        for row in rows:
            by_name.setdefault(row.name, []).append(row)

        schedule_refs = (
            db.execute(
                select(Schedule.prompt_id, Schedule.name).where(Schedule.prompt_id.is_not(None))
            ).all()
            if kind == "prompts"
            else []
        )
        items = []
        for name, versions in by_name.items():
            ids = {v.id for v in versions}
            published = [v for v in versions if v.status == STATUS_PUBLISHED]
            schedules_using = sorted({n for vid, n in schedule_refs if vid in ids})
            items.append({
                "name": name,
                "versions": len(versions),
                "published_version": published[-1].version if published else None,
                "latest_version": versions[-1].version,
                "latest_status": versions[-1].status,
                "last_published_at": (
                    published[-1].published_at.isoformat()
                    if published and published[-1].published_at
                    else None
                ),
                "schedule_refs": len(schedules_using),
                "schedule_names": schedules_using,
                "unused": not schedules_using,
            })
        items.sort(key=lambda i: (i["unused"], i["name"]))
        return {"items": items, "kind": kind}

    @router.get("/diff/view", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def diff(
        name: str = Query(max_length=120),
        from_version: int = Query(alias="from", ge=1),
        to_version: int = Query(alias="to", ge=1),
        db: Session = Depends(get_db),
    ):
        return {"diff": diff_versions(db, model, name, from_version, to_version)}

    @router.post("/rollback", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def rollback(
        request: Request,
        payload: RollbackRequest,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = rollback_to_version(
            db, model, payload.name, payload.version,
            created_by=request.state.user.id,
            now=request.app.state.clock.now(),
        )
        record_audit_from_request(
            request, db, action=f"{kind}.rollback", object_type=kind,
            object_id=row.id,
            after={"name": row.name, "republished_from": payload.version,
                   "new_version": row.version},
        )
        return {"item": _view_single(db, row)}

    return router


prompts_router = _build_router(
    "prompts", Prompt, _prompt_view, PromptCreateRequest, PromptContentUpdateRequest
)
policies_router = _build_router(
    "policies", Policy, _policy_view, PolicyCreateRequest, PolicyContentUpdateRequest
)
