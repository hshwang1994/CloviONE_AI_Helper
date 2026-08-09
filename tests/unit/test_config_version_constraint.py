"""ConfigVersion 유니크 제약이 ORM 메타데이터에도 선언돼 있는지 (round8 감사).

alembic 마이그레이션 0004(alembic/versions/0004_integrations_config_versions.py)는
config_versions 테이블에 (object_type, object_id, version) 유니크 인덱스
(`uq_config_versions_object_version`)를 DB 단에서 만든다. 하지만 ORM 모델
(app.core.versioning.ConfigVersion)에 같은 제약이 __table_args__ 로 선언돼
있지 않으면, alembic 을 거치지 않고 Base.metadata.create_all() 로 테이블을
만드는 경로는 이 제약이 빠진 채 테이블이 만들어진다 - snapshot_config 의 동시
쓰기 재시도 로직(IntegrityError 를 잡아 재시도)과 get_version 의
scalar_one_or_none()(중복이 없다는 전제로 "정확히 하나"를 기대)이 기대는
전제가 조용히 깨진다. 이 테스트는 alembic 없이 create_all() 만으로 만든 테이블
에서도 같은 제약이 살아 있는지를 본다(이 레포의 tests/conftest.py 는 실제로는
alembic 경로만 쓰지만, ORM 메타데이터 자체가 스키마의 정본이어야 한다).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.models_base import Base
from app.core.versioning import ConfigVersion

pytestmark = pytest.mark.unit


def test_unique_constraint_survives_create_all_without_alembic(tmp_path):
    db_path = tmp_path / "create_all_only.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    # alembic upgrade 를 전혀 거치지 않는다 - ORM 메타데이터만으로 테이블을 만든다.
    Base.metadata.create_all(engine, tables=[ConfigVersion.__table__])

    with Session(engine) as session:
        session.add(
            ConfigVersion(
                object_type="test_object", object_id="obj-1", version=1,
                snapshot_json="{}",
            )
        )
        session.commit()

        session.add(
            ConfigVersion(
                object_type="test_object", object_id="obj-1", version=1,
                snapshot_json="{}",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
