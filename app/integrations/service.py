"""Integration Registry service (spec §14.3)."""

from __future__ import annotations

import json
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.allowlist import AllowlistRegistry
from app.core.errors import ConflictError, NotFoundError
from app.core.http_client import OutboundClient, is_timeout_error, is_transport_error
from app.core.secret_refs import FileSecretReferenceProvider
from app.core.versioning import get_version, load_snapshot, snapshot_config
from app.integrations.models import HEALTH_DOWN, HEALTH_UP, Integration
from app.integrations.schemas import IntegrationConfig

OBJECT_TYPE = "integration"
ALLOWLIST = "services"


def integration_snapshot(row: Integration) -> dict:
    """Restorable full config. Contains secret reference NAMES, never values."""
    return {
        "name": row.name,
        "provider_type": row.provider_type,
        "description": row.description,
        "base_url": row.base_url,
        "health_url": row.health_url,
        "auth_type": row.auth_type,
        "secret_ref": row.secret_ref,
        "capabilities": json.loads(row.capabilities_json),
        "enabled": row.enabled,
    }


def integration_view(row: Integration, secrets: FileSecretReferenceProvider) -> dict:
    """Response shape — secret status only, never a value (spec §0.2)."""
    view = integration_snapshot(row)
    view.update(
        {
            "id": row.id,
            "secret_status": (
                secrets.status(row.secret_ref) if row.secret_ref else None
            ),
            "last_health_status": row.last_health_status,
            "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
            "config_version": row.config_version,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
    )
    return view


def get_integration_or_404(db: Session, integration_id: str) -> Integration:
    row = db.get(Integration, integration_id)
    if row is None:
        raise NotFoundError("Integration을 찾을 수 없습니다.")
    return row


def _validate_urls(config: IntegrationConfig, allowlists: AllowlistRegistry) -> None:
    allowlist = allowlists.get(ALLOWLIST)
    allowlist.check(config.base_url)
    if config.health_url:
        allowlist.check(config.health_url)


def create_integration(
    db: Session,
    config: IntegrationConfig,
    *,
    allowlists: AllowlistRegistry,
    created_by: str | None,
) -> Integration:
    _validate_urls(config, allowlists)
    existing = db.execute(
        select(Integration).where(Integration.name == config.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"이미 등록된 Integration 이름입니다: {config.name}")

    row = Integration(
        name=config.name,
        provider_type=config.provider_type,
        description=config.description,
        base_url=config.base_url,
        health_url=config.health_url,
        auth_type=config.auth_type,
        secret_ref=config.secret_ref,
        capabilities_json=json.dumps(config.capabilities, ensure_ascii=False),
        enabled=config.enabled,
        config_version=1,
    )
    try:
        # 위의 SELECT 사전 검사는 UX용 조기 안내일 뿐이다 — 동시에 같은 이름으로 두 요청이
        # 그 SELECT를 통과하면 진짜 경계는 DB의 unique 제약이다. SAVEPOINT로 감싸 그 제약
        # 위반(IntegrityError)을 흡수하고 409로 답한다 — 레포 관례
        # (jobs/repository.enqueue, board/service._add_reaction 등)와 동일.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        raise ConflictError(f"이미 등록된 Integration 이름입니다: {config.name}")
    snapshot_config(
        db,
        object_type=OBJECT_TYPE,
        object_id=row.id,
        snapshot=integration_snapshot(row),
        created_by=created_by,
    )
    return row


def apply_integration_config(
    db: Session,
    row: Integration,
    config: IntegrationConfig,
    *,
    allowlists: AllowlistRegistry,
    updated_by: str | None,
) -> Integration:
    """The single write path for updates AND rollbacks — always validated,
    always versioned."""
    _validate_urls(config, allowlists)
    if config.name != row.name:
        clash = db.execute(
            select(Integration).where(
                Integration.name == config.name, Integration.id != row.id
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError(f"이미 등록된 Integration 이름입니다: {config.name}")

    row.name = config.name
    row.provider_type = config.provider_type
    row.description = config.description
    row.base_url = config.base_url
    row.health_url = config.health_url
    row.auth_type = config.auth_type
    row.secret_ref = config.secret_ref
    row.capabilities_json = json.dumps(config.capabilities, ensure_ascii=False)
    row.enabled = config.enabled
    row.config_version += 1
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ConflictError(f"이미 등록된 Integration 이름입니다: {config.name}")
    snapshot_config(
        db,
        object_type=OBJECT_TYPE,
        object_id=row.id,
        snapshot=integration_snapshot(row),
        created_by=updated_by,
    )
    return row


def rollback_integration(
    db: Session,
    row: Integration,
    version: int,
    *,
    allowlists: AllowlistRegistry,
    updated_by: str | None,
) -> Integration:
    snapshot_row = get_version(db, OBJECT_TYPE, row.id, version)
    config = IntegrationConfig.model_validate(load_snapshot(snapshot_row))
    return apply_integration_config(
        db, row, config, allowlists=allowlists, updated_by=updated_by
    )


def run_health_check(
    db: Session,
    row: Integration,
    *,
    outbound: OutboundClient,
    now,
) -> dict:
    url = row.health_url or row.base_url
    started = time.perf_counter()
    detail: str | None = None
    try:
        response = outbound.get(
            url,
            allowlist=ALLOWLIST,
            timeout=10.0,
            auth_type=row.auth_type,
            secret_ref=row.secret_ref,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        # OutboundClient는 follow_redirects=False로 만들어진다(SSRF 방지) — 3xx가 오면
        # 그건 실제 대상이 아니라 리다이렉트 응답 자체다. status_code < 400은 3xx를 '정상'으로
        # 세서, 붙지도 않은 대상을 대시보드(app/health/service.py)에 up으로 보여줬다.
        healthy = 200 <= response.status_code < 300
        status = HEALTH_UP if healthy else HEALTH_DOWN
        detail = f"HTTP {response.status_code}"
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        status = HEALTH_DOWN
        if is_timeout_error(exc):
            detail = "timeout"
        elif is_transport_error(exc):
            detail = "connection_error"
        else:
            raise

    row.last_health_status = status
    row.last_health_at = now
    db.flush()
    return {
        "status": status,
        "latency_ms": round(latency_ms, 1),
        "detail": detail,
        "checked_url": url,
    }
