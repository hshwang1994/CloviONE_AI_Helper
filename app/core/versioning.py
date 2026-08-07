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
from sqlalchemy.exc import IntegrityError
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
    """같은 (object_type, object_id) 를 두 요청이 동시에 스냅샷하면 둘 다 같은
    ``current_max`` 를 읽고 같은 version 번호로 insert 를 시도할 수 있다.
    ``uq_config_versions_object_version`` 유니크 인덱스가 데이터 손상은 막지만, 진 쪽은
    처리되지 않은 IntegrityError 로 그 호출자에게 500 이 그대로 샌다.

    그래서 진 쪽은 최신 max 를 다시 읽어 한 번만 재시도한다. 이 함수는 다른 변경(예:
    설정 행 갱신)이 이미 flush 된 뒤에 불리는 호출부가 있으므로(app/settings/service.py 등),
    실패한 insert 를 savepoint(``begin_nested``)로 감싸 그 세션에 이미 올라와 있는 다른
    변경까지 되돌리지 않는다.
    """
    for attempt in range(2):
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
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            if attempt == 1:
                raise
            continue
        return row
    raise AssertionError("unreachable")  # pragma: no cover


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
