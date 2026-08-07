"""설정 스냅샷 버전 번호 - 동시 쓰기 경쟁 (round7 감사).

`snapshot_config` 는 (object_type, object_id) 별 다음 version 을 "현재 최댓값 + 1" 로
읽어서 계산한다. 두 요청이 같은 대상을 동시에 스냅샷하면(예: 두 관리자가 같은 설정을
거의 동시에 저장) 둘 다 같은 최댓값을 읽고 같은 version 번호로 insert 를 시도할 수 있다.
유니크 인덱스(`uq_config_versions_object_version`)가 데이터 손상은 막지만, 그것만으로는
진 쪽에게 처리되지 않은 IntegrityError 가 그대로 500 으로 샌다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.versioning import ConfigVersion, get_version, list_versions, snapshot_config

pytestmark = pytest.mark.unit


def test_snapshots_get_increasing_version_numbers(db):
    first = snapshot_config(
        db, object_type="test_object", object_id="obj-1", snapshot={"a": 1}
    )
    second = snapshot_config(
        db, object_type="test_object", object_id="obj-1", snapshot={"a": 2}
    )
    db.commit()

    assert first.version == 1
    assert second.version == 2
    assert [v.version for v in list_versions(db, "test_object", "obj-1")] == [2, 1]
    assert get_version(db, "test_object", "obj-1", 1).version == 1


def test_a_concurrent_writer_does_not_crash_the_loser_with_an_integrity_error(app, db):
    """두 세션이 같은 (object_type, object_id) 를 거의 동시에 스냅샷하는 상황을 흉내낸다.

    `db` 세션이 현재 최댓값을 읽고 나서, 정작 그 값으로 insert 하기 **전에** 다른 세션이
    같은 version 번호로 먼저 커밋해 버리면(경쟁에서 진 쪽), `db` 쪽 insert 는 유니크
    인덱스에 걸린다. 처리되지 않은 IntegrityError 로 죽는 대신, 최댓값을 다시 읽어 한
    번 재시도해서 다음 번호로 저장해야 한다.
    """
    object_type, object_id = "test_object", "obj-race"
    calls = {"n": 0}
    orig_flush = db.flush

    def racing_flush(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # 다른 커넥션이 같은 대상에 먼저 version=1 을 커밋한 상황.
            with app.state.session_factory() as other:
                other.add(
                    ConfigVersion(
                        object_type=object_type,
                        object_id=object_id,
                        version=1,
                        snapshot_json="{}",
                    )
                )
                other.commit()
        return orig_flush(*args, **kwargs)

    db.flush = racing_flush
    try:
        row = snapshot_config(
            db, object_type=object_type, object_id=object_id, snapshot={"a": 1}
        )
    finally:
        db.flush = orig_flush

    assert row.version == 2, "먼저 커밋된 version=1 과 충돌했으면 재시도해서 2를 써야 한다"
    db.commit()

    versions = sorted(
        v
        for v, in db.execute(
            select(ConfigVersion.version).where(
                ConfigVersion.object_type == object_type,
                ConfigVersion.object_id == object_id,
            )
        ).all()
    )
    assert versions == [1, 2], "경쟁에서 진 쪽의 시도가 사라지거나 둘 다 안 남으면 안 된다"


def test_a_lost_race_does_not_roll_back_other_pending_changes_in_the_same_session(db):
    """이 함수를 부르기 **전에** 같은 세션에 이미 올라와 있는 다른 변경(예: 방금 만든
    부서 행)까지 재시도 과정에서 날아가면 안 된다 - 실제 호출부(app/settings/service.py
    등)는 snapshot_config 앞뒤로 다른 mutation 을 같은 세션에 쌓아 둔다.

    이 세션이 이미 쓰기 트랜잭션을 쥔 채로(부서 flush) 다른 커넥션이 동시에 같은
    (object_type, object_id) 에 commit 하는 상황은 SQLite 의 단일 writer 제약 때문에
    실제로 재현할 수 없다(두 커넥션이 동시에 쓰기 잠금을 쥘 수 없다). 그래서 경쟁의
    **결과**(첫 flush 가 IntegrityError 로 죽는 상황)만 흉내 내고, 재시도가 같은 세션의
    다른 변경까지 되돌리지 않는지를 본다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    pending = Department(name="충돌 테스트 부서", org_id=DEFAULT_ORG_ID)
    db.add(pending)
    db.flush()  # 이 세션에 이미 올라와 있는, 아직 커밋 전인 변경.

    calls = {"n": 0}
    orig_flush = db.flush

    def failing_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError(
                "INSERT INTO config_versions ...", {}, Exception("UNIQUE constraint failed")
            )
        return orig_flush(*args, **kwargs)

    db.flush = failing_once
    try:
        row = snapshot_config(
            db, object_type="test_object", object_id="obj-race-2", snapshot={"a": 1}
        )
    finally:
        db.flush = orig_flush

    assert row.version == 1

    db.commit()

    assert (
        db.execute(
            select(Department.id).where(Department.id == pending.id)
        ).scalar_one_or_none()
        is not None
    ), "버전 충돌 재시도가 같은 세션의 다른 변경(부서 생성)까지 되돌렸다"
