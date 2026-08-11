"""Config version snapshots for registries and settings (spec §21.18).

Every mutation writes a full JSON snapshot with a per-object monotonic
version, but call sites differ on which side of the mutation they snapshot:
registries (integrations/runners/workflows) snapshot the row AFTER applying
the change (post-change — see the respective service.py create_*/update_*),
while app/settings/service.py::apply_setting snapshots the value BEFORE
applying the new one (pre-change — it saves "before" so rollback_setting has
something to restore to). Rollback (implemented per module) loads a snapshot,
re-validates it against the current schema, and applies it through the normal
update path — so rollback itself is an audited, versioned change and history
stays append-only. Snapshots are NOT masked (they must be restorable); they
contain secret reference NAMES only, never secret values.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import is_write_conflict
from app.core.errors import NotFoundError
from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow


class ConfigVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "config_versions"
    # alembic/versions/0004_integrations_config_versions.py 가 DB 단에 만드는 것과 같은
    # 제약을 ORM 메타데이터에도 선언한다 - 안 하면 Base.metadata.create_all() 로 테이블을
    # 만드는 경로(alembic 을 안 거치는 일부 테스트/스크립트)는 이 유니크 제약이 빠진 채
    # 테이블이 만들어져, snapshot_config 의 재시도 로직과 get_version 의
    # scalar_one_or_none() 이 기대는 "동시 삽입은 IntegrityError 로 걸린다" 전제가 조용히
    # 깨진다.
    __table_args__ = (
        Index(
            "uq_config_versions_object_version",
            "object_type",
            "object_id",
            "version",
            unique=True,
        ),
    )

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

    정확한 트랜잭션 격리(``app/core/db.py``)에서는 재시도가 한 가지를 더 요구한다:
    이 세션이 attempt 0 의 첫 SELECT 에서 이미 스냅샷을 확정했으므로, ``begin_nested()``
    실패 뒤 **같은 트랜잭션 안에서** ``current_max`` 를 다시 읽어도 여전히 낡은 값을
    본다(SAVEPOINT 롤백은 SAVEPOINT 만 되돌리지 바깥 트랜잭션의 스냅샷은 안 바꾼다) —
    두 번째 시도도 같은 버전 번호를 계산해 같은 충돌을 반복한다(실측 확인함). 그래서
    재시도 전에 ``db.commit()`` 으로 스냅샷을 새로 뜬다 — ``rollback()`` 이 아니라
    ``commit()`` 인 이유가 바로 위 문단이다: 이 함수 호출 전에 이미 flush 된 다른 변경을
    "되돌리지 않는다"는 약속을 지키려면 **잃지 않고 커밋해 보존**해야 한다(잃는 쪽인
    rollback 은 그 약속과 반대다).
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
        except (IntegrityError, OperationalError) as exc:
            if not is_write_conflict(exc):
                raise
            if attempt == 1:
                raise
            db.commit()  # 스냅샷을 새로 뜬다 — 다른 이미 flush 된 변경은 보존(커밋)한다.
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
