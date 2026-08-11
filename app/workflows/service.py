"""Workflow Registry service (spec §16)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.allowlist import AllowlistRegistry
from app.core.db import is_write_conflict
from app.core.errors import ConflictError, NotFoundError
from app.core.versioning import get_version, load_snapshot, snapshot_config
from app.workflows.models import Workflow
from app.workflows.schemas import WorkflowConfig

OBJECT_TYPE = "workflow"
ALLOWLIST = "workflows"


def workflow_snapshot(row: Workflow) -> dict:
    return {
        "name": row.name,
        "purpose": row.purpose,
        "webhook_url": row.webhook_url,
        "http_method": row.http_method,
        "payload_schema": (
            json.loads(row.payload_schema_json) if row.payload_schema_json else None
        ),
        "response_schema": (
            json.loads(row.response_schema_json) if row.response_schema_json else None
        ),
        "operation_mode": row.operation_mode,
        "approval_required": row.approval_required,
        "enabled": row.enabled,
        "owner": row.owner,
        "tags": json.loads(row.tags_json),
    }


def workflow_view(row: Workflow) -> dict:
    view = workflow_snapshot(row)
    view.update(
        {
            "id": row.id,
            "last_test_status": row.last_test_status,
            "last_test_at": row.last_test_at.isoformat() if row.last_test_at else None,
            "config_version": row.config_version,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
    )
    return view


def get_workflow_or_404(db: Session, workflow_id: str) -> Workflow:
    row = db.get(Workflow, workflow_id)
    if row is None:
        raise NotFoundError("Workflow를 찾을 수 없습니다.")
    return row


def _check_name_clash(db: Session, name: str, *, exclude_id: str | None = None) -> None:
    stmt = select(Workflow).where(Workflow.name == name)
    if exclude_id:
        stmt = stmt.where(Workflow.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise ConflictError(f"이미 등록된 Workflow 이름입니다: {name}")


def _apply_fields(row: Workflow, config: WorkflowConfig) -> None:
    row.name = config.name
    row.purpose = config.purpose
    row.webhook_url = config.webhook_url
    row.http_method = config.http_method
    row.payload_schema_json = (
        json.dumps(config.payload_schema, ensure_ascii=False)
        if config.payload_schema is not None
        else None
    )
    row.response_schema_json = (
        json.dumps(config.response_schema, ensure_ascii=False)
        if config.response_schema is not None
        else None
    )
    row.operation_mode = config.operation_mode
    row.approval_required = config.approval_required
    row.enabled = config.enabled
    row.owner = config.owner
    row.tags_json = json.dumps(config.tags, ensure_ascii=False)


def create_workflow(
    db: Session,
    config: WorkflowConfig,
    *,
    allowlists: AllowlistRegistry,
    created_by: str | None,
) -> Workflow:
    allowlists.get(ALLOWLIST).check(config.webhook_url)
    _check_name_clash(db, config.name)
    row = Workflow(config_version=1)
    _apply_fields(row, config)
    try:
        # _check_name_clash 위의 SELECT는 UX용 조기 안내일 뿐이다 — 동시에 같은 이름으로
        # 두 요청이 그 SELECT를 통과하면 진짜 경계는 DB의 unique 제약이다. SAVEPOINT로
        # 감싸 그 제약 위반(IntegrityError)을 흡수하고 409로 답한다 — 레포 관례
        # (jobs/repository.enqueue, board/service._add_reaction 등)와 동일.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_write_conflict(exc):
            raise
        raise ConflictError(f"이미 등록된 Workflow 이름입니다: {config.name}") from exc
    snapshot_config(
        db, object_type=OBJECT_TYPE, object_id=row.id,
        snapshot=workflow_snapshot(row), created_by=created_by,
    )
    return row


def apply_workflow_config(
    db: Session,
    row: Workflow,
    config: WorkflowConfig,
    *,
    allowlists: AllowlistRegistry,
    updated_by: str | None,
) -> Workflow:
    allowlists.get(ALLOWLIST).check(config.webhook_url)
    if config.name != row.name:
        _check_name_clash(db, config.name, exclude_id=row.id)
    _apply_fields(row, config)
    row.config_version += 1
    try:
        with db.begin_nested():
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_write_conflict(exc):
            raise
        raise ConflictError(f"이미 등록된 Workflow 이름입니다: {config.name}") from exc
    snapshot_config(
        db, object_type=OBJECT_TYPE, object_id=row.id,
        snapshot=workflow_snapshot(row), created_by=updated_by,
    )
    return row


def rollback_workflow(
    db: Session,
    row: Workflow,
    version: int,
    *,
    allowlists: AllowlistRegistry,
    updated_by: str | None,
) -> Workflow:
    snapshot_row = get_version(db, OBJECT_TYPE, row.id, version)
    config = WorkflowConfig.model_validate(load_snapshot(snapshot_row))
    return apply_workflow_config(
        db, row, config, allowlists=allowlists, updated_by=updated_by
    )


def seed_known_workflows(db: Session, *, allowlists: AllowlistRegistry) -> list[str]:
    """Initial registration (spec §16.3). Idempotent by name."""
    known = [
        {
            "name": "ClovirONE AI 업무 도우미",
            "purpose": "티켓, 프로젝트 조회와 생성, 도움말: 사용자 채팅의 백엔드 workflow",
            "webhook_url": "http://127.0.0.1:5678/webhook/clovirone-work-assistant",
            "http_method": "POST",
            "operation_mode": "write",
            "approval_required": False,
            "enabled": True,
        },
        {
            # 이름이 계약이다 — notion_mapping/service.py의 MAPPING_WORKFLOW_NAME이 이 값으로
            # 찾는다. 이 워크플로가 없으면 get_mapping_workflow()가 None을 돌려주고 매핑이
            # "Workflow가 구성/활성화되지 않았습니다"로 끝난다. 실제로 그 상태였다 —
            # 플랫폼 코드는 완성돼 있는데 n8n 쪽 워크플로가 없어서 Notion ID를 못 가져왔다.
            "name": "notion-user-mapping",
            "purpose": (
                "사용자 이메일로 Notion user id를 찾는다. 사람은 워크스페이스 멤버 목록"
                "(/v1/users)이 아니라 작업 데이터의 담당자에서 나온다. 그 API는 이 통합에"
                " 2명만 노출한다(실측). 티켓의 '티켓 담당자'와 프로젝트의 '담당자 정/부'에"
                " 진짜 Notion user id가 들어 있고, 러너도 같은 우물을 쓴다."
            ),
            "webhook_url": "http://127.0.0.1:5678/webhook/clovirone-notion-user-mapping",
            "http_method": "POST",
            # 읽기 전용이다. Notion에 아무것도 쓰지 않는다.
            "operation_mode": "read",
            "approval_required": False,
            "enabled": True,
        },
    ]
    created: list[str] = []
    for entry in known:
        if db.execute(
            select(Workflow).where(Workflow.name == entry["name"])
        ).scalar_one_or_none() is None:
            create_workflow(
                db, WorkflowConfig.model_validate(entry),
                allowlists=allowlists, created_by=None,
            )
            created.append(entry["name"])
    return created
