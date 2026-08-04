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
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, ValidationAppError
from app.prompts.models import STATUS_DRAFT, STATUS_PUBLISHED, Policy, Prompt
from app.prompts.service import (
    diff_versions,
    get_or_404,
    new_version_from,
    rollback_to_version,
    transition,
    update_content,
    validate_policy_content,
)



class PromptCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="", max_length=100000)
    runner_id: str | None = None


class PolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(default="{}", max_length=100000)

    _coerce_content = field_validator("content", mode="before")(_json_object_to_str)


class ContentUpdateRequest(BaseModel):
    content: str = Field(max_length=100000)
    purpose: str | None = Field(default=None, max_length=2000)
    runner_id: str | None = None

    # Policy 수정은 JSON 객체를 보낸다(관리자 콘솔). Prompt 수정은 자유 텍스트(문자열)를 보낸다.
    # 아래 코어서는 객체만 문자열로 바꾸므로 프롬프트 본문에는 영향이 없다.
    _coerce_content = field_validator("content", mode="before")(_json_object_to_str)


class TransitionRequest(BaseModel):
    status: str


class RollbackRequest(BaseModel):
    name: str
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
        "runner_id": row.runner_id,
        **_creator_fields(row.created_by, names or {}),
        "created_at": row.created_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _policy_view(row: Policy, names: dict | None = None) -> dict:
    import json

    return {
        "id": row.id,
        "name": row.name,
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


def _build_router(kind: str, model, view, create_schema):
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
                stmt.order_by(model.name, model.version.desc())
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

    @router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def create(request: Request, payload: create_schema, db: Session = Depends(get_db)):
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
                name=payload.name, version=1, content_json=content,
                status=STATUS_DRAFT, created_by=request.state.user.id,
            )
        else:
            row = Prompt(
                name=payload.name, purpose=payload.purpose, version=1,
                content=content, status=STATUS_DRAFT,
                runner_id=payload.runner_id, created_by=request.state.user.id,
            )
        db.add(row)
        db.flush()
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
        payload: ContentUpdateRequest,
        db: Session = Depends(get_db),
    ):
        row = get_or_404(db, model, row_id)
        if model is Policy:
            validate_policy_content(payload.content)
        update_content(db, row, payload.content)
        if model is Prompt:
            if payload.purpose is not None:
                row.purpose = payload.purpose
            if payload.runner_id is not None:
                row.runner_id = payload.runner_id or None
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
    ):
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
    def new_version(request: Request, row_id: str, db: Session = Depends(get_db)):
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
        "실제로 쓰이는가"는 **그것을 가리키는 것**에서 나온다 — 템플릿·스케줄이 이 이름의
        어느 버전을 참조하는지, 그리고 그 버전으로 실제 문서 생성이 몇 번 돌았는지.

        추측하지 않는다: 참조가 0이면 0으로 보여 준다. "쓰이지 않는 프롬프트"를 알아보는
        것이 이 화면의 목적이므로, 애매하게 감추면 목적이 사라진다.
        """
        from sqlalchemy import or_ as _or

        from app.documents.models import DocumentGeneration
        from app.schedules.models import Schedule
        from app.templates.models import AutomationTemplate as Template

        rows = db.execute(select(model).order_by(model.name, model.version)).scalars().all()
        by_name: dict[str, list] = {}
        for row in rows:
            by_name.setdefault(row.name, []).append(row)

        id_field = "prompt_id" if kind == "prompts" else "policy_id"
        template_refs = db.execute(
            select(getattr(Template, id_field), Template.name).where(
                getattr(Template, id_field).is_not(None)
            )
        ).all()
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
            templates_using = sorted({n for vid, n in template_refs if vid in ids})
            schedules_using = sorted({n for vid, n in schedule_refs if vid in ids})
            # UUID 를 LIKE 로 찾는다 — config_json 안에 들어 있어 컬럼으로는 못 건다.
            # id 가 UUID 라 오탐이 사실상 불가능하고, 버전 수만큼만 절이 붙는다.
            capped = sorted(ids)[:50]
            doc_runs = 0
            if capped:
                doc_runs = int(
                    db.execute(
                        select(func.count())
                        .select_from(DocumentGeneration)
                        .where(_or(*[DocumentGeneration.config_json.like(f"%{i}%") for i in capped]))
                    ).scalar_one()
                )
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
                "template_refs": len(templates_using),
                "template_names": templates_using,
                "schedule_refs": len(schedules_using),
                "schedule_names": schedules_using,
                "document_runs": doc_runs,
                "unused": not templates_using and not schedules_using and doc_runs == 0,
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
    def rollback(request: Request, payload: RollbackRequest, db: Session = Depends(get_db)):
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


prompts_router = _build_router("prompts", Prompt, _prompt_view, PromptCreateRequest)
policies_router = _build_router("policies", Policy, _policy_view, PolicyCreateRequest)
