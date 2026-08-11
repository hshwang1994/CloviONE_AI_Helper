"""Automation Template API (spec §17.3)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.prompts.models import STATUS_ARCHIVED, Policy, Prompt
from app.runners.models import Runner
from app.templates.models import TARGET_RUNNER, TARGET_WORKFLOW, AutomationTemplate
from app.workflows.models import Workflow

router = APIRouter(
    prefix="/api/admin/templates",
    tags=["admin-templates"],
    dependencies=[Depends(require_csrf)],
)



class TemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    input_schema: dict = Field(default_factory=dict)
    target_type: str
    target_ref: str = Field(min_length=1, max_length=64)
    prompt_id: str | None = None
    policy_id: str | None = None
    approval_policy: dict = Field(default_factory=dict)

    @field_validator("target_type")
    @classmethod
    def _target_known(cls, v: str) -> str:
        if v not in {TARGET_WORKFLOW, TARGET_RUNNER}:
            raise ValueError("target_type은 workflow 또는 runner여야 합니다.")
        return v

    @field_validator("input_schema", "approval_policy", mode="before")
    @classmethod
    def _serializable(cls, v):
        # 관리자 콘솔의 JSON 입력 필드는 비워 두면 null을 보낸다. 선택 필드이므로 빈 객체로 본다 —
        # 안 그러면 기본값만으로 저장하려는 템플릿 생성이 dict 검증 422로 막힌다(round16 스윕 B2).
        if v is None:
            return {}
        if isinstance(v, dict):
            json.dumps(v)
        return v

    @field_validator("approval_policy")
    @classmethod
    def _approval_policy_shape(cls, v: dict) -> dict:
        # 발행 승인 정책은 {"required": bool} 한 가지 형태만 발효된다
        # (publish_approval_required가 required만 읽는다). 그 외 키를 조용히 저장하면
        # 발효되지 않는데도 발효되는 것처럼 보여 잘못된 확신을 준다 — 지원하지 않는 키를
        # 아예 거부해, UI가 무시될 정책을 담지 못하게 한다.
        extra = set(v) - {"required"}
        if extra:
            raise ValueError(
                'approval_policy는 {"required": true/false} 형태만 지원합니다. '
                f"허용되지 않는 키: {sorted(extra)}"
            )
        if "required" in v and not isinstance(v["required"], bool):
            raise ValueError("approval_policy.required는 true 또는 false여야 합니다.")
        return v


def _view(row: AutomationTemplate, names: dict | None = None) -> dict:
    names = names or {}
    creator = names.get(row.created_by or "")
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "input_schema": json.loads(row.input_schema_json),
        "target_type": row.target_type,
        "target_ref": row.target_ref,
        "prompt_id": row.prompt_id,
        "policy_id": row.policy_id,
        "approval_policy": json.loads(row.approval_policy_json),
        "enabled": row.enabled,
        # prompts/policies both expose created_by (registry.js:323,:358) — templates
        # captures it on create (router.py create() below) but never serialized it,
        # so provenance ("who made this template") was silently unavailable here.
        "created_by": row.created_by,
        # UB-29: 원시 UUID만 있으면 관리자가 "누가 만들었나"를 알 방법이 없다 — prompts/
        # policies가 이미 하는 대로(app/approvals/service.py::resolve_names 재사용) 이름·
        # 이메일을 함께 내려준다.
        "created_by_name": creator.get("display_name") if creator else None,
        "created_by_email": creator.get("email") if creator else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _get_or_404(db: Session, template_id: str) -> AutomationTemplate:
    row = db.get(AutomationTemplate, template_id)
    if row is None:
        raise NotFoundError("Template을 찾을 수 없습니다.")
    return row


def _validate_references(db: Session, payload: TemplateRequest) -> None:
    if payload.target_type == TARGET_WORKFLOW:
        if db.get(Workflow, payload.target_ref) is None:
            raise ValidationAppError("target_ref에 해당하는 Workflow가 없습니다.")
    else:
        if db.get(Runner, payload.target_ref) is None:
            raise ValidationAppError("target_ref에 해당하는 Runner가 없습니다.")
    if payload.prompt_id:
        prompt = db.get(Prompt, payload.prompt_id)
        if prompt is None:
            raise ValidationAppError("prompt_id에 해당하는 Prompt가 없습니다.")
        # UB-29: archived는 "다시는 안 쓴다"는 의도적 퇴역 표시다(prompts/policies 상태
        # 전이표, models.py — archived에서는 어디로도 못 나간다). 그런데 템플릿 생성/수정은
        # 그 표시를 무시하고 새로 바인딩할 수 있었다 — draft/test/review는 여전히 허용한다
        # (documents/service.py::_resolve_published_binding이 발행본이 없으면 그 pinned
        # 값으로 폴백하는 의도적 fail-safe라, 여기서 더 엄격하게 막으면 그 설계와 충돌한다).
        if prompt.status == STATUS_ARCHIVED:
            raise ValidationAppError("보관(archived)된 Prompt는 템플릿에 새로 연결할 수 없습니다.")
    if payload.policy_id:
        policy = db.get(Policy, payload.policy_id)
        if policy is None:
            raise ValidationAppError("policy_id에 해당하는 Policy가 없습니다.")
        if policy.status == STATUS_ARCHIVED:
            raise ValidationAppError("보관(archived)된 Policy는 템플릿에 새로 연결할 수 없습니다.")


def _validate_enable_target(db: Session, row: AutomationTemplate) -> None:
    """UB-14: 활성화 시점에 대상이 여전히 살아 있는지 확인한다.

    `_validate_references`는 생성·수정 시 "존재하는가"만 본다 — 활성화 이후 대상
    Workflow/Runner가 **비활성화**돼도(삭제 경로는 이 저장소에 아예 없다 — Workflow/
    Runner 둘 다 hard-delete route가 없다, "삭제된 뒤"라는 원 서술은 재확인 결과
    재현 불가로 판정, `docs/BACKLOG.md` 참고) 템플릿은 계속 `enabled=True`로 남아 있었다.
    그 어긋남은 관리자가 활성화를 누르는 순간이 아니라, 한참 뒤 다른 사용자가 문서 생성을
    누르는 순간에야(`app/documents/service.py::request_generation`) 터졌다 — 활성화
    시점에 미리 막아 그 지연을 없앤다.
    """
    if row.target_type == TARGET_WORKFLOW:
        target = db.get(Workflow, row.target_ref)
        label = "Workflow"
    else:
        target = db.get(Runner, row.target_ref)
        label = "Runner"
    if target is None:
        raise ValidationAppError(f"대상 {label}을(를) 찾을 수 없어 활성화할 수 없습니다.")
    if not target.enabled:
        raise ConflictError(f"대상 {label}이(가) 비활성화 상태라 템플릿을 활성화할 수 없습니다.")


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_templates(
    db: Session = Depends(get_db),
    target_type: str | None = Query(default=None, max_length=16),
    enabled: bool | None = Query(default=None),
    prompt_id: str | None = Query(default=None, max_length=64),
    policy_id: str | None = Query(default=None, max_length=64),
):
    # UB-29: 예전엔 파라미터가 전혀 없어, "이 정책을 쓰는 템플릿" 같은 소비처가 전체
    # 테이블을 끌어와 프런트에서 filterRows로 걸렀다(authoring.js). target_type/enabled는
    # 화면 자체 필터가 이미 clientFilter:true로 하던 것을 서버로 옮긴 것뿐 — 목록 전체
    # 크기 자체를 줄이지는 않는다(무제한 목록 자체의 페이지네이션은 이번 범위 밖으로
    # 남긴다, BACKLOG 참고 — 지금은 무한정 안 자란다는 전제가 실측상 안전하다).
    stmt = select(AutomationTemplate)
    if target_type:
        stmt = stmt.where(AutomationTemplate.target_type == target_type)
    if enabled is not None:
        stmt = stmt.where(AutomationTemplate.enabled == enabled)
    if prompt_id:
        stmt = stmt.where(AutomationTemplate.prompt_id == prompt_id)
    if policy_id:
        stmt = stmt.where(AutomationTemplate.policy_id == policy_id)
    rows = db.execute(stmt.order_by(AutomationTemplate.name)).scalars().all()
    from app.approvals.service import resolve_names

    names = resolve_names(db, {r.created_by for r in rows})
    return {"items": [_view(r, names) for r in rows]}


@router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def create_template(request: Request, payload: TemplateRequest, db: Session = Depends(get_db)):
    if db.execute(
        select(AutomationTemplate).where(AutomationTemplate.name == payload.name)
    ).scalar_one_or_none() is not None:
        raise ConflictError(f"이미 존재하는 Template 이름입니다: {payload.name}")
    _validate_references(db, payload)
    row = AutomationTemplate(
        name=payload.name,
        description=payload.description,
        input_schema_json=json.dumps(payload.input_schema, ensure_ascii=False),
        target_type=payload.target_type,
        target_ref=payload.target_ref,
        prompt_id=payload.prompt_id,
        policy_id=payload.policy_id,
        approval_policy_json=json.dumps(payload.approval_policy, ensure_ascii=False),
        enabled=False,
        created_by=request.state.user.id,
    )
    db.add(row)
    db.flush()
    record_audit_from_request(
        request, db, action="template.create", object_type="template",
        object_id=row.id, after={"name": row.name},
    )
    creator = request.state.user
    names = {creator.id: {"display_name": creator.display_name, "email": creator.email}}
    return {"template": _view(row, names)}


@router.get("/{template_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_template(template_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, template_id)
    from app.approvals.service import resolve_names

    names = resolve_names(db, {row.created_by})
    return {"template": _view(row, names)}


@router.put("/{template_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def update_template(
    request: Request,
    template_id: str,
    payload: TemplateRequest,
    db: Session = Depends(get_db),
):
    row = _get_or_404(db, template_id)
    _validate_references(db, payload)
    # 다른 템플릿과 이름이 겹치면 flush에서 IntegrityError → 500이 났다. 생성 경로는 같은 상황에
    # 409(ConflictError)를 준다. 동종 자원과 일관되게 사전 검사로 409를 돌려준다(round16 스윕).
    if payload.name != row.name:
        clash = db.execute(
            select(AutomationTemplate).where(
                AutomationTemplate.name == payload.name, AutomationTemplate.id != template_id
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError(f"이미 존재하는 Template 이름입니다: {payload.name}")
    before = _view(row)
    row.name = payload.name
    row.description = payload.description
    row.input_schema_json = json.dumps(payload.input_schema, ensure_ascii=False)
    row.target_type = payload.target_type
    row.target_ref = payload.target_ref
    row.prompt_id = payload.prompt_id
    row.policy_id = payload.policy_id
    row.approval_policy_json = json.dumps(payload.approval_policy, ensure_ascii=False)
    db.flush()
    record_audit_from_request(
        request, db, action="template.update", object_type="template",
        object_id=row.id, before=before, after=_view(row),
    )
    from app.approvals.service import resolve_names

    names = resolve_names(db, {row.created_by})
    return {"template": _view(row, names)}


def _set_enabled(request: Request, db: Session, template_id: str, enabled: bool):
    row = _get_or_404(db, template_id)
    row.enabled = enabled
    db.flush()
    record_audit_from_request(
        request, db,
        action="template.enable" if enabled else "template.disable",
        object_type="template", object_id=row.id,
    )
    return {"ok": True, "enabled": enabled}


@router.post("/{template_id}/enable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def enable_template(request: Request, template_id: str, db: Session = Depends(get_db)):
    row = _get_or_404(db, template_id)
    _validate_enable_target(db, row)
    return _set_enabled(request, db, template_id, True)


@router.post("/{template_id}/disable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def disable_template(request: Request, template_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, template_id, False)


@router.delete("/{template_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def delete_template(request: Request, template_id: str, db: Session = Depends(get_db)):
    """UB-29: 템플릿에는 create/read/update/enable/disable만 있고 퇴역 경로가 없었다.

    `enabled`일 때는 지울 수 없다(먼저 끄게 강제 — 활성 템플릿이 문서 생성에서 계속
    쓰이는 도중 사라지는 것을 막는다, `_validate_enable_target`이 활성화 시점에 대상
    생존을 강제하는 것과 같은 방향). `DocumentGeneration.template_id`는 FK 없는 bare
    문자열 컬럼이라(app/documents/models.py) 지워도 과거 생성 이력이 깨지지 않는다 —
    `generation_view`는 그 값을 그대로 echo만 한다.
    """
    row = _get_or_404(db, template_id)
    if row.enabled:
        raise ConflictError("활성 상태인 템플릿은 지울 수 없습니다. 먼저 비활성화하세요.")
    before = _view(row)
    db.delete(row)
    db.flush()
    record_audit_from_request(
        request, db, action="template.delete", object_type="template",
        object_id=template_id, before=before,
    )
    return {"ok": True}
