"""Automation Template API (spec §17.3)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.prompts.models import Policy, Prompt
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


def _view(row: AutomationTemplate) -> dict:
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
    if payload.prompt_id and db.get(Prompt, payload.prompt_id) is None:
        raise ValidationAppError("prompt_id에 해당하는 Prompt가 없습니다.")
    if payload.policy_id and db.get(Policy, payload.policy_id) is None:
        raise ValidationAppError("policy_id에 해당하는 Policy가 없습니다.")


@router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def list_templates(db: Session = Depends(get_db)):
    rows = db.execute(
        select(AutomationTemplate).order_by(AutomationTemplate.name)
    ).scalars().all()
    return {"items": [_view(r) for r in rows]}


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
    return {"template": _view(row)}


@router.get("/{template_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def get_template(template_id: str, db: Session = Depends(get_db)):
    return {"template": _view(_get_or_404(db, template_id))}


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
    return {"template": _view(row)}


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
    return _set_enabled(request, db, template_id, True)


@router.post("/{template_id}/disable", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def disable_template(request: Request, template_id: str, db: Session = Depends(get_db)):
    return _set_enabled(request, db, template_id, False)
