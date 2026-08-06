"""0045(프로젝트 Notion 동기화 컬럼) — 왕복 리허설과 **0044 를 깨지 않았다**는 보증.

## 왜 이 왕복을 따로 보는가

0045 는 `projects` 에 컬럼 일곱 개를 더한다. SQLite 에서 `drop_column` 은 **테이블 재생성**이라,
되돌리는 순간 그 표의 행과 인덱스가 통째로 새로 만들어진다. `scripts/migration_rehearsal.sh`
는 거의 빈 DB 로 돌기 때문에 "행을 잃지 않았다" 를 증명하지 못한다 - 잃을 행이 없으면 검사가
헛돈다(0044 테스트가 같은 이유를 적어 놨다).

그리고 `projects` 는 **미러가 아니라 앱 정본**이다(0044). 여기서 행 하나를 잃으면 그 행에
매달린 마일스톤·주간 리포트·헬스 이력이 CASCADE 로 함께 사라지고, 넷 다 Notion 에 없어서
재동기화로 돌아오지 않는다. 되돌릴 수 있어야 하는 이유가 그것이다.

## 유니크 제약은 이름이 아니라 동작으로 확인한다

`uq_projects_org_code` 는 0044 가 만든 것이고 0045 의 테이블 재생성이 조용히 날릴 수 있다.
인덱스 이름을 찾는 검사는 제약이 실제로 막는지 아무것도 말해 주지 않으므로 INSERT 를 두 번
해서 두 번째가 거부되는지 본다(0044 / 0025 테스트와 같은 관용).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TS = "2026-08-01 00:00:00.000000"

# 0045 가 `projects` 에 더하는 컬럼 전부. 하나라도 빠지면 그 컬럼을 읽는 동기화가 배포
# 당일 첫 tick 에서 죽는다.
NEW_PROJECT_COLUMNS = {
    "notion_progress_pct",
    "notion_status",
    "notion_owner_ids",
    "notion_missing_at",
    "notion_last_edited",
    "notion_synced_at",
    "notion_sync_error",
}

# 0044 가 만든 것 중 **되돌릴 때 함께 날아가면 안 되는** 것들.
COLUMNS_0044_MUST_SURVIVE = {
    "progress_pct", "health_score", "archived_at", "notion_page_id", "dept_id", "code",
}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"alembic {args} 실패:\n{result.stdout}\n{result.stderr}"


def _rows(db_path: Path, sql: str) -> list[tuple]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql))]
    finally:
        engine.dispose()


def _columns(db_path: Path, table: str) -> set[str]:
    return {c[1] for c in _rows(db_path, f"PRAGMA table_info({table})")}


def _tables(db_path: Path) -> set[str]:
    return {
        r[0] for r in _rows(
            db_path, "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Path:
    """0044 까지 올린 뒤 프로젝트 하나와 그 자식들(마일스톤·주간 리포트)을 넣는다.

    자식까지 넣는 이유: `projects` 를 재생성하다 행을 잃으면 CASCADE 로 이 둘이 함께
    사라지는데, 그건 재계산으로도 복구되지 않는 사람의 판단 기록이다.
    """
    db_path = tmp_path / "project-sync.sqlite3"
    _alembic(db_path, "upgrade", "0044")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        # 조직을 **반드시 채운다.** `uq_projects_org_code` 는 (org_id, code) 이고 SQLite 는
        # UNIQUE 에서 NULL 을 서로 다른 값으로 본다 - org_id 를 비워 두면 같은 코드를 두 번
        # 넣어도 통과해서, 제약이 살아 있는지 확인하려던 아래 검사가 조용히 헛돈다.
        org_id = conn.execute(text("SELECT id FROM organizations LIMIT 1")).scalar()
        assert org_id, "0038 이 넣는 기본 조직이 없다 - 이 테스트의 전제가 깨졌다"
        conn.execute(text(
            "INSERT INTO projects (id, name, code, status, org_id, notion_page_id,"
            " progress_pct, created_at, updated_at)"
            " VALUES ('p-1', '되돌려도 살아 있어야 하는 프로젝트', 'PRJ-1', 'active',"
            " :org, 'notion-page-1', 42.5, :ts, :ts)"
        ), {"ts": TS, "org": org_id})
        conn.execute(text(
            "INSERT INTO projects (id, name, status, org_id, created_at, updated_at)"
            " VALUES ('p-2', '포털 전용', 'planned', :org, :ts, :ts)"
        ), {"ts": TS, "org": org_id})
        conn.execute(text(
            "INSERT INTO project_milestones (id, project_id, name, status,"
            " sort_order, created_at, updated_at)"
            " VALUES ('m-1', 'p-1', '1차 납품', 'planned', 0, :ts, :ts)"
        ), {"ts": TS})
        conn.execute(text(
            "INSERT INTO project_weekly_reports (id, project_id, week_of, summary_md,"
            " source, generated_at, created_at, updated_at)"
            " VALUES ('w-1', 'p-1', '2026-07-27', '사람이 쓴 판단', 'rule', :ts, :ts, :ts)"
        ), {"ts": TS})
    engine.dispose()
    return db_path


def test_upgrade_adds_the_columns_and_the_sync_singleton(seeded_db):
    _alembic(seeded_db, "upgrade", "0045")

    cols = _columns(seeded_db, "projects")
    missing = sorted(NEW_PROJECT_COLUMNS - cols)
    assert not missing, f"0045 가 안 만든 컬럼이 있다: {missing}"
    assert COLUMNS_0044_MUST_SURVIVE <= cols, "0045 가 0044 의 컬럼을 건드렸다"

    assert "project_sync_state" in _tables(seeded_db)
    # 티켓 미러와 **같은 모양**이어야 운영 화면이 두 벌의 번역을 안 갖는다.
    assert {
        "id", "status", "last_run_at", "last_success_at",
        "project_count", "truncated", "pruned_count", "error", "updated_at",
    } <= _columns(seeded_db, "project_sync_state")

    # 새 컬럼은 전부 NULL 로 들어와야 한다. 0 이나 빈 문자열로 백필하면 기존 프로젝트가
    # 화면에서 'Notion 진행률 0%' 로 보이는데, 그건 확인한 적 없는 숫자다.
    assert _rows(seeded_db, "SELECT notion_progress_pct, notion_status FROM projects") == [
        (None, None), (None, None),
    ]


def test_the_round_trip_keeps_every_row_and_the_unique_index(seeded_db):
    _alembic(seeded_db, "upgrade", "0045")
    _alembic(seeded_db, "downgrade", "-1")

    cols = _columns(seeded_db, "projects")
    assert not (NEW_PROJECT_COLUMNS & cols), "downgrade 가 컬럼을 안 지웠다"
    assert "project_sync_state" not in _tables(seeded_db)
    assert COLUMNS_0044_MUST_SURVIVE <= cols, (
        "downgrade 가 0044 의 컬럼까지 지웠다 - 되돌리면 프로젝트 정본이 망가진다"
    )
    assert _rows(seeded_db, "SELECT COUNT(*) FROM projects") == [(2,)]
    assert _rows(seeded_db, "SELECT COUNT(*) FROM project_milestones") == [(1,)]
    assert _rows(seeded_db, "SELECT COUNT(*) FROM project_weekly_reports") == [(1,)]
    assert _rows(seeded_db, "SELECT progress_pct FROM projects WHERE id='p-1'") == [(42.5,)]

    _alembic(seeded_db, "upgrade", "head")

    assert NEW_PROJECT_COLUMNS <= _columns(seeded_db, "projects")
    assert _rows(seeded_db, "SELECT COUNT(*) FROM projects") == [(2,)], (
        "왕복이 프로젝트 행을 잃었다"
    )
    assert _rows(seeded_db, "SELECT COUNT(*) FROM project_weekly_reports") == [(1,)], (
        "왕복이 주간 리포트를 잃었다 - 재계산으로 돌아오지 않는 기록이다"
    )
    assert _rows(seeded_db, "PRAGMA integrity_check") == [("ok",)]

    # 제약이 살아 있는지는 **동작으로** 본다. 이름만 찾으면 막는지 아닌지 알 수 없다.
    org_id = _rows(seeded_db, "SELECT org_id FROM projects WHERE id='p-1'")[0][0]
    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO projects (id, name, code, status, org_id,"
                    " created_at, updated_at)"
                    " VALUES ('p-dup', '같은 코드', 'PRJ-1', 'active', :org, :ts, :ts)"
                ), {"ts": TS, "org": org_id})
    finally:
        engine.dispose()


def test_the_soft_prune_mark_is_indexed(seeded_db):
    """동기화가 매 회차 "표시되지 않은 행" 만 후보로 뽑는다. 인덱스가 없으면 그 질의가
    프로젝트가 늘수록 풀스캔이 된다 - 느려지기만 하고 아무 오류도 안 난다."""
    _alembic(seeded_db, "upgrade", "0045")
    names = {
        r[0] for r in _rows(
            seeded_db,
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='projects'",
        )
    }
    assert "ix_projects_notion_missing_at" in names
