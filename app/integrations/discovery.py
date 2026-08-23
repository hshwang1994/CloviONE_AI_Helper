"""Initial discovery import of known integrations (spec §14.3, §15.1).

Seeds the registry with the services known from the spec/precheck. Idempotent
by name — existing rows are never modified. The install script runs:
    python -m app.integrations.discovery

S11 이 n8n 과 러너 셋을 걷어내면서 그 넷의 시드가 빠졌다. 남은 것은 Notion 하나이고
그것도 S14 에서 Notion Runtime 과 함께 사라진다.
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
        "name": "notion",
        "provider_type": "notion",
        "description": "Notion 작업 공간. 미러 동기화가 쓰며 S14 에서 사라집니다.",
        "base_url": "https://api.notion.com",
        "health_url": "https://api.notion.com/v1/users/me",
        "capabilities": {"mirror": True},
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
        db.commit()
    if created:
        print(f"Integration 등록됨: {', '.join(created)}")
    else:
        print("Integration 신규 등록 없음 (모두 존재)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
