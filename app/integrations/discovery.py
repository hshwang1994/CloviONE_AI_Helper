"""Initial discovery import of known integrations (spec §14.3, §15.1).

Seeds the registry with the services known from the spec/precheck. Idempotent
by name — existing rows are never modified. The install script runs:
    python -m app.integrations.discovery
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.allowlist import AllowlistRegistry
from app.core.config import Settings
from app.core.versioning import snapshot_config
from app.integrations.models import Integration
from app.integrations.schemas import IntegrationConfig
from app.integrations.service import OBJECT_TYPE, create_integration

KNOWN_INTEGRATIONS: list[dict] = [
    {
        "name": "n8n",
        "provider_type": "n8n",
        "description": "n8n 워크플로 엔진 (기존 서비스 — 무접촉, webhook 호출만)",
        "base_url": "http://127.0.0.1:5678",
        "health_url": "http://127.0.0.1:5678/healthz",
        "capabilities": {"webhooks": True},
        "enabled": True,
    },
    {
        "name": "clovirone-work-assistant",
        "provider_type": "http_service",
        "description": "ClovirONE AI 업무 도우미 (기존 서비스)",
        "base_url": "http://127.0.0.1:8789",
        "health_url": "http://127.0.0.1:8789/healthz",
        "capabilities": {"chat": True},
        "enabled": True,
    },
    {
        "name": "claude-ticket-runner",
        "provider_type": "http_service",
        "description": "Claude Ticket Runner (기존 서비스)",
        "base_url": "http://127.0.0.1:8787",
        "health_url": "http://127.0.0.1:8787/healthz",
        "capabilities": {"tickets": True},
        "enabled": True,
    },
    {
        "name": "claude-request-interpreter",
        "provider_type": "http_service",
        "description": "Claude Request Interpreter (기존 서비스 — 존재 여부 사전조사로 확인)",
        "base_url": "http://127.0.0.1:8788",
        "health_url": "http://127.0.0.1:8788/healthz",
        "capabilities": {"interpretation": True},
        "enabled": True,
    },
]


def seed_known_integrations(
    db: Session, *, allowlists: AllowlistRegistry, created_by: str | None = None
) -> list[str]:
    """Returns names of newly created integrations (existing ones skipped)."""
    created: list[str] = []
    for entry in KNOWN_INTEGRATIONS:
        exists = db.execute(
            select(Integration).where(Integration.name == entry["name"])
        ).scalar_one_or_none()
        if exists is not None:
            continue
        config = IntegrationConfig.model_validate(entry)
        create_integration(db, config, allowlists=allowlists, created_by=created_by)
        created.append(entry["name"])
    return created


def main() -> int:
    from app.core.db import make_engine, make_session_factory

    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    allowlists = AllowlistRegistry(settings.config_dir)
    with factory() as db:
        created = seed_known_integrations(db, allowlists=allowlists)
        # Also seed the known n8n workflow (spec §16.3) so the registry is
        # populated on a fresh install, not only the integrations.
        from app.workflows.service import seed_known_workflows

        created_wf = seed_known_workflows(db, allowlists=allowlists)
        db.commit()
    if created:
        print(f"Integration 등록됨: {', '.join(created)}")
    else:
        print("Integration 신규 등록 없음 (모두 존재)")
    if created_wf:
        print(f"Workflow 등록됨: {', '.join(created_wf)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
