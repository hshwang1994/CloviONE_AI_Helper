"""0044(projects) — 왕복 리허설과, **0043 을 깨지 않았다**는 보증.

## 왜 왕복을 테스트하는가

SQLite 에서 downgrade 는 종종 테이블 재생성이다. 컬럼 순서, 기본값, 유니크 제약이 조용히
달라질 수 있어서 "up 이 성공했다" 만으로는 되돌릴 수 있다는 증명이 안 된다
(`scripts/migration_rehearsal.sh` 가 같은 이유로 앞뒤 스키마를 비교한다).

## 왜 0043 을 함께 확인하는가

`notion_missing_at` 은 **0043 에서 막 들어왔다.** 티켓이 Notion 응답에서 한 회차 깜빡였을 때
행을 지우는 대신 표시만 해서 댓글, 첨부, 미push 본문이 CASCADE 로 사라지는 것을 막는
컬럼이다(`tests/regression/test_comment_survives_resync.py` 가 그 사고를 재현한다).
0044 는 같은 표에 컬럼 하나를 더할 뿐이고, 더하다가 그 컬럼이나 소프트 프룬 인덱스를
날리면 **되살릴 수 없는 사용자 데이터가 다시 위험해진다.** 그래서 여기서 못박는다.

## 유니크 제약은 이름이 아니라 동작으로 확인한다

인덱스 이름을 찾는 검사는 제약이 실제로 막는지 아무것도 말해 주지 않는다. INSERT 를 두 번
해서 두 번째가 거부되는지 본다(`test_migration_0025_self_id_refs.py` 와 같은 관용).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TS = "2026-08-01 00:00:00.000000"

# 0044 가 만드는 표 전부. 하나라도 빠지면 그 표를 쓰는 코드가 배포 당일에 처음 죽는다.
NEW_TABLES = (
    "projects",
    "project_members",
    "project_milestones",
    "project_health_snapshots",
    "project_weekly_reports",
)

PROJECT_COLUMNS = {
    "id", "name", "code", "status", "dept_id", "org_id", "owner_user_id",
    "starts_on", "ends_on", "goal", "biz_type", "product",
    "progress_pct", "health_score", "archived_at", "notion_page_id",
    "created_at", "updated_at",
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
    """0043 까지 올린 뒤 티켓 미러 행 둘을 넣는다(부모와 자식).

    왕복이 **기존 행을 보존하는지** 보려면 되돌리는 구간보다 먼저 있던 데이터가 필요하다.
    빈 DB 로 왕복하면 아무것도 잃을 것이 없어 검사가 헛돈다.
    """
    db_path = tmp_path / "projects.sqlite3"
    _alembic(db_path, "upgrade", "0043")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        for uid, page in (("tkt-parent", "page-parent"), ("tkt-child", "page-child")):
            conn.execute(text(
                "INSERT INTO ticket_cache (id, notion_page_id, title, project_ids,"
                " project_names, assignee_notion_ids, source, synced_at,"
                " created_at, updated_at)"
                " VALUES (:uid, :page, '티켓', '', '', '', 'notion', :ts, :ts, :ts)"
            ), {"uid": uid, "page": page, "ts": TS})
    engine.dispose()
    return db_path


def test_the_new_tables_and_columns_exist_after_upgrade(seeded_db):
    _alembic(seeded_db, "upgrade", "0044")

    present = _tables(seeded_db)
    missing = [t for t in NEW_TABLES if t not in present]
    assert not missing, f"0044 가 만들지 않은 표가 있다: {missing}"

    assert _columns(seeded_db, "projects") == PROJECT_COLUMNS, (
        "projects 컬럼이 계약과 다르다"
    )
    # `order` 는 SQL 예약어라 `sort_order` 로 둔다(0044 주석). 이름이 바뀌면 여기서 잡는다.
    assert "sort_order" in _columns(seeded_db, "project_milestones")
    assert "reasons_json" in _columns(seeded_db, "project_health_snapshots"), (
        "점수만 남기면 몇 주 뒤에 '왜 그 점수였나' 에 아무도 답할 수 없다"
    )
    assert {"summary_md", "source", "week_of"} <= _columns(
        seeded_db, "project_weekly_reports"
    )


def test_the_ticket_mirror_gains_parent_page_id_without_losing_0043(seeded_db):
    """0043 의 `notion_missing_at` 과 그 인덱스를 **깨뜨리지 않았다**."""
    _alembic(seeded_db, "upgrade", "0044")

    cols = _columns(seeded_db, "ticket_cache")
    assert "parent_page_id" in cols, "상위 작업 미러 컬럼이 없다 - 리프 판정을 할 수 없다"
    assert "notion_missing_at" in cols, (
        "0043 의 소프트 프룬 컬럼이 사라졌다 - 댓글, 첨부가 다시 CASCADE 로 지워진다"
    )

    indexes = {i["name"] for i in sa.inspect(
        create_engine(f"sqlite:///{seeded_db.as_posix()}")
    ).get_indexes("ticket_cache")}
    assert "ix_ticket_cache_notion_missing_at" in indexes, (
        "0043 의 인덱스가 사라졌다 - 모든 목록 질의가 이 컬럼을 건다"
    )
    assert "ix_ticket_cache_parent_page_id" in indexes

    # 기존 행은 그대로 있고 새 컬럼은 NULL 이다. 그게 사실이다(파서가 아직 안 채운다).
    assert _rows(seeded_db, "SELECT COUNT(*) FROM ticket_cache") == [(2,)]
    assert _rows(
        seeded_db, "SELECT parent_page_id FROM ticket_cache WHERE id='tkt-child'"
    ) == [(None,)]


def test_a_second_snapshot_for_the_same_week_is_rejected(seeded_db):
    """주간 이력은 **한 주에 한 행**이다. 쌓이면 '이력'이 아니라 '실행 로그'가 된다."""
    _alembic(seeded_db, "upgrade", "0044")

    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO projects (id, name, status, created_at, updated_at)"
                " VALUES ('p-1', '프로젝트', 'active', :ts, :ts)"
            ), {"ts": TS})
            conn.execute(text(
                "INSERT INTO project_health_snapshots"
                " (id, project_id, week_of, score, reasons_json, created_at)"
                " VALUES ('s-1', 'p-1', '2026-08-03', 70, '[]', :ts)"
            ), {"ts": TS})

        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO project_health_snapshots"
                    " (id, project_id, week_of, score, reasons_json, created_at)"
                    " VALUES ('s-2', 'p-1', '2026-08-03', 40, '[]', :ts)"
                ), {"ts": TS})
    finally:
        engine.dispose()


def test_deleting_a_project_takes_its_children_with_it(seeded_db):
    """CASCADE 가 **실제로 동작하는지**. FK 선언만 있고 PRAGMA 가 꺼져 있으면 고아가 남는다."""
    _alembic(seeded_db, "upgrade", "0044")

    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text(
                "INSERT INTO projects (id, name, status, created_at, updated_at)"
                " VALUES ('p-2', '프로젝트', 'active', :ts, :ts)"
            ), {"ts": TS})
            conn.execute(text(
                "INSERT INTO project_milestones"
                " (id, project_id, name, status, sort_order, created_at, updated_at)"
                " VALUES ('m-1', 'p-2', '1차 납품', 'planned', 0, :ts, :ts)"
            ), {"ts": TS})
            conn.execute(text("DELETE FROM projects WHERE id='p-2'"))
        assert _rows(seeded_db, "SELECT COUNT(*) FROM project_milestones") == [(0,)]
    finally:
        engine.dispose()


def test_the_roundtrip_keeps_the_ticket_mirror_intact(seeded_db):
    """올리고 되돌리고 다시 올린다 - `scripts/migration_rehearsal.sh` 의 pytest 판.

    되돌리면 0044 가 만든 표는 사라지는 것이 정상이다(그게 롤백의 대가다). **사라지면 안
    되는 것**은 그 구간보다 먼저 있던 `ticket_cache` 행과 0043 의 컬럼이다.
    """
    _alembic(seeded_db, "upgrade", "0044")
    _alembic(seeded_db, "downgrade", "0043")

    after_down = _tables(seeded_db)
    still_there = [t for t in NEW_TABLES if t in after_down]
    assert not still_there, f"downgrade 가 표를 안 지웠다: {still_there}"

    cols = _columns(seeded_db, "ticket_cache")
    assert "parent_page_id" not in cols, "downgrade 가 컬럼을 안 지웠다"
    assert "notion_missing_at" in cols, (
        "downgrade 가 0043 의 컬럼까지 지웠다 - 되돌리면 소프트 프룬이 사라진다"
    )
    assert _rows(seeded_db, "SELECT COUNT(*) FROM ticket_cache") == [(2,)]

    _alembic(seeded_db, "upgrade", "0044")

    assert set(NEW_TABLES) <= _tables(seeded_db)
    assert "parent_page_id" in _columns(seeded_db, "ticket_cache")
    assert _rows(seeded_db, "SELECT COUNT(*) FROM ticket_cache") == [(2,)], (
        "왕복이 티켓 미러 행을 잃었다"
    )
    assert _rows(seeded_db, "PRAGMA integrity_check") == [("ok",)]


def test_0044_survives_all_the_way_to_head(seeded_db):
    """마이그레이션 파일이 체인에 실제로 붙었는지. 붙지 않으면 `upgrade head` 가 조용히
    0043 에서 멈추고, 표가 없다는 사실은 첫 요청에서야 드러난다.

    **머리 번호를 못박지 않는다.** 예전에는 `head == "0044"` 를 봤는데, 그러면 뒤에 리비전이
    하나 붙을 때마다 이 테스트가 실패한다 - 0044 가 깨져서가 아니라 그 뒤에 뭔가 생겨서다
    (0045 에서 실제로 그랬다). 거짓 실패를 내는 테스트는 곧 아무도 안 보게 되고, 그때 진짜
    결함도 함께 묻힌다. 확인해야 하는 것은 번호가 아니라 **head 까지 올렸을 때 0044 가 만든
    것이 거기 그대로 있는가** 다. 뒤 리비전이 이 표를 지우거나 컬럼을 날려도 여기서 잡힌다.
    """
    _alembic(seeded_db, "upgrade", "head")

    head = _rows(seeded_db, "SELECT version_num FROM alembic_version")
    assert head and head[0][0] >= "0044", f"head 가 0044 앞에서 멈췄다: {head}"

    present = _tables(seeded_db)
    missing = [t for t in NEW_TABLES if t not in present]
    assert not missing, f"head 까지 올렸더니 0044 의 표가 사라졌다: {missing}"
    assert PROJECT_COLUMNS <= _columns(seeded_db, "projects"), (
        "뒤 리비전이 0044 의 projects 컬럼을 지웠다"
    )
