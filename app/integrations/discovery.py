"""Initial discovery import of known integrations (spec §14.3, §15.1).

Seeds the registry with the services known from the spec/precheck. Idempotent
by name — existing rows are never modified. The install script runs:
    python -m app.integrations.discovery

S11 이 n8n 과 러너 셋을 걷어내면서 그 넷의 시드가 빠졌고, 마지막 하나였던 Notion 은
Notion Runtime 과 함께 사라졌다. 그래서 지금 이 시드는 비어 있다.

**비었다고 이 모듈을 지우지는 않는다.** 설치 스크립트가 부르는 진입점이고, 다음 연동이
생기면 그 시드가 여기 온다. 비어 있는 목록은 「아직 아무 연동도 기본으로 넣지 않는다」는
사실을 그대로 말한다.
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

# 새 항목의 `base_url`·`health_url` 호스트는 런타임 허용 목록(config/allowed-services.json)
# 에 먼저 있어야 한다. 없으면 `create_integration` 이 저장 시점에 거절한다.
KNOWN_INTEGRATIONS: list[dict] = []


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
