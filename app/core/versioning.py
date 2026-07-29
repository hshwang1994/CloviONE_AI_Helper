"""Config version snapshots for registries and settings (spec §21.18).

Every mutation writes a full post-change JSON snapshot with a per-object
monotonic version. Rollback (implemented per module) loads a snapshot,
re-validates it against the current schema, and applies it through the normal
update path — so rollback itself is an audited, versioned change and history
stays append-only. Snapshots are NOT masked (they must be restorable); they
contain secret reference NAMES only, never secret values.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.errors import NotFoundError
from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow


class ConfigVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "config_versions"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


def snapshot_config(
    db: Session,
    *,
    object_type: str,
    object_id: str,
    snapshot: dict,
    created_by: str | None = None,
) -> ConfigVersion:
    current_max = db.execute(
        select(func.max(ConfigVersion.version)).where(
            ConfigVersion.object_type == object_type,
            ConfigVersion.object_id == object_id,
        )
    ).scalar_one()
    row = ConfigVersion(
        object_type=object_type,
        object_id=object_id,
        version=(current_max or 0) + 1,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=str),
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def list_versions(db: Session, object_type: str, object_id: str) -> list[ConfigVersion]:
    return list(
        db.execute(
            select(ConfigVersion)
            .where(
                ConfigVersion.object_type == object_type,
                ConfigVersion.object_id == object_id,
            )
            .order_by(ConfigVersion.version.desc())
        )
        .scalars()
        .all()
    )


def get_version(
    db: Session, object_type: str, object_id: str, version: int
) -> ConfigVersion:
    row = db.execute(
        select(ConfigVersion).where(
            ConfigVersion.object_type == object_type,
            ConfigVersion.object_id == object_id,
            ConfigVersion.version == version,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"버전 {version}을 찾을 수 없습니다.")
    return row


def load_snapshot(row: ConfigVersion) -> dict:
    return json.loads(row.snapshot_json)
