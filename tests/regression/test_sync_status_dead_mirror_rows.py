"""없어진 미러의 `sync_status` 행만 지우고 **살아 있는 둘은 남긴다** (S14 · C3).

이 시험이 못 박는 성질은 둘이고, 둘을 함께 봐야 뜻이 있다.

1. `tickets`·`documents`·`projects` 행이 사라진다. 쓰는 코드가 없어서 그 값은 굳어 있고,
   운영에 굳어 있던 세 줄은 전부 지금은 없는 노션 장애를 말한다.
2. 🔴 **반례**: `search`·`project_health` 행은 그대로 남는다. 이 단언이 없으면
   `DELETE FROM sync_status` 로 표를 통째로 비우는 회차도 1번을 만족하며 통과한다.
   그 회차는 살아 있는 잡 둘의 마지막 성공 시각을 지우고, 그러면 "몇 주째 안 돌았다" 가
   화면에서 "한 번도 안 쟀다" 와 같아진다.

마이그레이션이 실제로 실행하는 문장을 그대로 부른다. 시험이 SQL 을 다시 적으면 회차가
무엇을 지우는지가 아니라 시험이 무엇을 지우는지를 재게 된다.
"""

from __future__ import annotations

import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.regression

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0015_drop_dead_mirror_sync_rows.py"
)


def _migration():
    """alembic 회차 파일은 패키지가 아니라 경로로 읽는다(파일 이름이 식별자가 아니다)."""
    spec = importlib.util.spec_from_file_location("mig_0015_dead_mirror", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_every_component(db, fake_clock):
    """죽은 셋과 살아 있는 둘을 **함께** 심는다. 살아 있는 쪽을 안 심으면 반례가 빈다."""
    from app.observability.models import SYNC_ERROR, SYNC_OK
    from app.observability.service import upsert_sync_status

    now = fake_clock.now()
    module = _migration()
    for name in module.DEAD_MIRROR_COMPONENTS:
        upsert_sync_status(
            db,
            name,
            status=SYNC_ERROR,
            now=now - timedelta(days=4),
            item_count=110,
            error="Notion 응답 오류: HTTP 400 - This API is deprecated.",
        )
    for name in module.LIVE_COMPONENTS:
        upsert_sync_status(db, name, status=SYNC_OK, now=now, item_count=7)
    db.flush()
    return module


def _components(db) -> set[str]:
    from app.observability.models import SyncStatus

    return set(db.execute(select(SyncStatus.component)).scalars().all())


def test_the_dead_mirror_rows_are_gone(db, fake_clock):
    module = _seed_every_component(db, fake_clock)
    assert set(module.DEAD_MIRROR_COMPONENTS) <= _components(db), "심는 것부터 실패했다"

    removed = module.delete_dead_mirror_rows(db.get_bind())
    db.expire_all()

    assert removed == len(module.DEAD_MIRROR_COMPONENTS)
    left = _components(db) & set(module.DEAD_MIRROR_COMPONENTS)
    assert not left, f"쓰는 코드가 없는데 남아 있는 상태 행: {sorted(left)}"


def test_the_live_rows_survive_with_their_last_success_intact(db, fake_clock):
    """🔴 반례. 통째로 지우는 회차는 여기서 빨개진다."""
    from app.observability.models import SyncStatus

    module = _seed_every_component(db, fake_clock)
    module.delete_dead_mirror_rows(db.get_bind())
    db.expire_all()

    for name in module.LIVE_COMPONENTS:
        row = db.get(SyncStatus, name)
        assert row is not None, (
            f"{name} 행이 사라졌다. 이 컴포넌트에는 지금도 쓰는 코드가 있고, "
            "행이 없으면 잡이 몇 주째 안 돌아도 화면이 아무 말을 못 한다"
        )
        assert row.last_success_at is not None, (
            f"{name} 의 마지막 성공 시각이 지워졌다"
        )
        assert row.item_count == 7


def test_running_it_twice_lands_in_the_same_place(db, fake_clock):
    """두 번 돌려도 살아 있는 둘이 그대로다. 되감기가 없으니 재실행이 유일한 안전망이다."""
    module = _seed_every_component(db, fake_clock)

    first = module.delete_dead_mirror_rows(db.get_bind())
    second = module.delete_dead_mirror_rows(db.get_bind())
    db.expire_all()

    assert first == len(module.DEAD_MIRROR_COMPONENTS)
    assert second == 0, "두 번째 실행이 뭔가를 더 지웠다"
    assert _components(db) == set(module.LIVE_COMPONENTS)


def test_the_named_lists_do_not_overlap_and_match_the_source_constants():
    """이름을 두 곳에 적었으니 두 곳이 어긋나면 여기서 잡는다.

    `LIVE_COMPONENTS` 에 실수로 죽은 이름을 적으면 그 행이 영원히 남고, 반대로
    `DEAD_MIRROR_COMPONENTS` 에 살아 있는 이름이 들어가면 쓰는 코드가 있는 행을 지운다.
    """
    from app.observability.models import COMPONENT_PROJECT_HEALTH, COMPONENT_SEARCH

    module = _migration()
    assert not set(module.DEAD_MIRROR_COMPONENTS) & set(module.LIVE_COMPONENTS)
    assert set(module.LIVE_COMPONENTS) == {COMPONENT_SEARCH, COMPONENT_PROJECT_HEALTH}
