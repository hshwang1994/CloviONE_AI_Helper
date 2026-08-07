"""0050 — `org_id` 가 **DB 에서** 진짜 조직을 가리키게 만든다 (H1).

## 무엇이 잘못돼 있었나

`OrgScopedMixin` 은 `ForeignKey("organizations.id")` 를 선언한다. 그런데 마이그레이션은
그 제약을 만든 적이 없다(0024 가 "6개 테이블을 다시 만드는 위험이 크다"며 일부러 건너뛰었고,
그 뒤 0026/0030 도 같은 모양을 따라갔다). 그래서 **모델은 참조라고 말하는데 DB 는 아무것도
검사하지 않는** 상태였다.

증상은 오류가 아니라 **침묵**이다:
  * 조직 행을 지우면 그 조직 것이던 행들의 `org_id` 가 아무 데도 안 닿는 값이 된다.
  * 오타·복사 실수로 잘못된 `org_id` 가 들어가도 INSERT 가 성공한다.
  * 둘 다 화면에서는 "왜인지 목록이 비어 있다" 로만 보인다(`org_id = :org` 가 0건).

## 이 테스트가 보는 것

* **데이터를 잃지 않는다** — SQLite 는 기존 표에 FK 를 붙이려면 표를 다시 만들어야 한다.
  1,071건짜리 표를 복사하는 변경이므로 "제약이 생겼다" 만으로는 부족하고 행이 그대로
  살아 있는지를 본다.
* **고아를 어떻게 다뤘나** — 제약을 걸기 전에 고아가 있으면 마이그레이션이 멈추거나
  조용히 데이터를 버린다. 0050 은 **기본 조직으로 옮긴다**(지우지 않는다). 그 결정이
  실제로 그렇게 동작하는지 본다.
* **제약이 실제로 거부하는가** — 인덱스 존재 확인은 0024 에서 이미 헛돈 적이 있다
  (`PRAGMA` 에는 보이는데 아무것도 안 막았다). 그래서 INSERT/DELETE 를 쳐 본다.
* **FTS 인덱스가 살아 있는가** — `search_documents` 를 재생성하면 rowid 가 새로 매겨지고
  트리거도 함께 사라진다. 다시 만들고 `rebuild` 하지 않으면 검색이 **옛 내용을 돌려주거나
  0건**이 된다(가장 알아채기 어려운 종류의 고장이다).
* **왕복** — batch 다운그레이드는 표를 다시 만든다. up→down→up 뒤 데이터가 같아야 한다.
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

DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
GHOST_ORG_ID = "00000000-0000-0000-0000-0000000ghost"  # 어디에도 없는 조직
TS = "2026-08-01 00:00:00.000000"

# 0050 이 FK 를 붙이는 표들. 각 표에 '정상 행 1개 + 고아 행 1개'를 심는다.
SEED: dict[str, str] = {
    "job_titles": (
        "INSERT INTO job_titles (id, name, active, created_at, org_id)"
        " VALUES (:id, :tag, 1, :ts, :org)"
    ),
    "board_posts": (
        "INSERT INTO board_posts (id, author_user_id, category, title, body, is_pinned,"
        " view_count, created_at, updated_at, kind, org_id)"
        " VALUES (:id, 'u-1', 'free', :tag, '본문', 0, 0, :ts, :ts, 'free', :org)"
    ),
    "document_cache": (
        "INSERT INTO document_cache (id, notion_page_id, title, type_names, category_names,"
        " project_names, author_names, owner, memo, has_files, notion_favorite, archived,"
        " synced_at, tech_tags, classification_manual, author_notion_ids, org_id)"
        " VALUES (:id, :id, :tag, '', '', '', '', '', '', 0, 0, 0, :ts, '', 0, '', :org)"
    ),
    "chat_rooms": (
        "INSERT INTO chat_rooms (id, kind, title, is_global, event_seq, created_at,"
        " updated_at, org_id)"
        " VALUES (:id, 'group', :tag, 0, 0, :ts, :ts, :org)"
    ),
    "game_rooms": (
        "INSERT INTO game_rooms (id, title, game_type, host_user_id, status, max_players,"
        " allow_spectators, config_json, state_json, event_seq, created_at, updated_at, org_id)"
        " VALUES (:id, :tag, 'quiz', 'u-1', 'open', 4, 1, '{}', '{}', 0, :ts, :ts, :org)"
    ),
    "trash_items": (
        "INSERT INTO trash_items (id, item_type, notion_page_id, title, deleted_by_user_id,"
        " deleted_by_name, deleted_at, org_id)"
        " VALUES (:id, 'ticket', :id, :tag, 'u-1', '지운사람', :ts, :org)"
    ),
    "usage_events": (
        "INSERT INTO usage_events (id, event, created_at, org_id, object_id)"
        " VALUES (:id, 'test.event', :ts, :org, :tag)"
    ),
    "search_documents": (
        "INSERT INTO search_documents (id, kind, ref_id, owner_user_ids, title, body,"
        " route, indexed_at, org_id)"
        " VALUES (:id, 'ticket', :id, '', :tag, '검색 본문 스프린트', '/x', :ts, :org)"
    ),
}
TABLES = tuple(SEED)


def _alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"alembic {args} 실패:\n{result.stdout}\n{result.stderr}"
    return result


def _engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path.as_posix()}")


def _rows(db_path: Path, sql: str, params: dict | None = None) -> list[tuple]:
    engine = _engine(db_path)
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql), params or {})]
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def seeded_template(tmp_path_factory) -> Path:
    """0049(= FK 가 없던 마지막 상태)까지 올린 뒤 정상 행과 고아 행을 심는다.

    모듈에 한 번만 만든다 — 검사할 표가 8개라 표당 3~4개씩 테스트가 붙는데, 매번
    `alembic upgrade 0049` 를 subprocess 로 돌리면 이 파일 하나가 몇 분을 먹는다.
    실제 테스트는 이 파일의 **사본** 위에서 돈다(서로 오염되지 않는다).
    """
    db_path = tmp_path_factory.mktemp("org-fk") / "template.sqlite3"
    _alembic(db_path, "upgrade", "0049")

    engine = _engine(db_path)
    with engine.begin() as conn:
        for table, sql in SEED.items():
            conn.execute(
                text(sql),
                {"id": f"{table}-ok", "tag": f"{table} 정상", "ts": TS, "org": DEFAULT_ORG_ID},
            )
            conn.execute(
                text(sql),
                {"id": f"{table}-ghost", "tag": f"{table} 고아", "ts": TS, "org": GHOST_ORG_ID},
            )
    engine.dispose()
    return db_path


@pytest.fixture()
def seeded_db(seeded_template: Path, tmp_path: Path) -> Path:
    import shutil

    target = tmp_path / "org_fk.sqlite3"
    shutil.copy(seeded_template, target)
    return target


# ── 1) 데이터를 잃지 않는다 ───────────────────────────────────────────────────


@pytest.mark.parametrize("table", TABLES)
def test_no_row_is_lost_when_the_table_is_rebuilt(seeded_db, table):
    # 표에 따라 마이그레이션이 심어 둔 행이 이미 있다(예: 0039 의 전사 채팅방). 그래서
    # 숫자를 손으로 적지 않고 **왕복 전후를 비교**한다.
    before = _rows(seeded_db, f"SELECT id FROM {table} ORDER BY id")
    assert len(before) >= 2, f"{table}: 표본이 안 심겼다"
    _alembic(seeded_db, "upgrade", "0050")
    after = _rows(seeded_db, f"SELECT id FROM {table} ORDER BY id")
    assert after == before, f"{table}: 표를 다시 만들면서 행이 달라졌다"


# ── 2) 고아는 지우지 않고 기본 조직으로 옮긴다 ────────────────────────────────


@pytest.mark.parametrize("table", TABLES)
def test_orphan_rows_move_to_the_default_org_instead_of_being_deleted(seeded_db, table):
    """운영 데이터가 걸린 결정이다 — 지우는 쪽을 고르면 되돌릴 수 없다."""
    _alembic(seeded_db, "upgrade", "0050")
    rows = _rows(seeded_db, f"SELECT org_id FROM {table} WHERE id = :id",
                 {"id": f"{table}-ghost"})
    assert rows, f"{table}: 고아 행이 사라졌다(지워 버렸다)"
    assert rows[0][0] == DEFAULT_ORG_ID, (
        f"{table}: 고아 org_id 가 그대로 남아 제약을 걸어도 아무것도 못 막는다: {rows[0][0]}"
    )


# ── 3) 제약이 **실제로** 거부하는가 ───────────────────────────────────────────


@pytest.mark.parametrize("table", TABLES)
def test_the_constraint_exists_after_the_migration(seeded_db, table):
    _alembic(seeded_db, "upgrade", "0050")
    engine = _engine(seeded_db)
    try:
        fks = sa.inspect(engine).get_foreign_keys(table)
    finally:
        engine.dispose()
    org_fks = [fk for fk in fks if fk["constrained_columns"] == ["org_id"]]
    assert org_fks, f"{table}.org_id 에 외래키가 없다 (있는 것: {fks})"
    assert org_fks[0]["referred_table"] == "organizations"


@pytest.mark.parametrize("table", TABLES)
def test_a_bogus_org_id_is_rejected(seeded_db, table):
    """`PRAGMA index_list` 로는 못 잡는다 — INSERT 를 쳐서 거부되는지 본다."""
    _alembic(seeded_db, "upgrade", "0050")
    engine = _engine(seeded_db)
    try:
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.execute(
                    text(SEED[table]),
                    {"id": f"{table}-bad", "tag": "없는 조직", "ts": TS,
                     "org": "no-such-org-id"},
                )
    finally:
        engine.dispose()


def test_deleting_an_organization_that_still_owns_rows_is_refused(seeded_db):
    """조직 행을 지워 참조를 고아로 만드는 경로도 DB 가 막아야 한다."""
    _alembic(seeded_db, "upgrade", "0050")
    engine = _engine(seeded_db)
    try:
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.execute(
                    text("DELETE FROM organizations WHERE id = :org"),
                    {"org": DEFAULT_ORG_ID},
                )
    finally:
        engine.dispose()


# ── 4) 검색 인덱스가 표 재생성에서 살아남는가 ─────────────────────────────────


def test_the_fts_index_still_points_at_the_right_rows(seeded_db):
    """external content FTS5 는 rowid 로 원본을 가리킨다 — 표를 다시 만들면 어긋난다.

    트리거를 다시 만들고 인덱스를 rebuild 하지 않으면 검색이 조용히 0건이 되거나
    **다른 행의 제목**을 돌려준다. 둘 다 아무 오류를 내지 않는다.
    """
    _alembic(seeded_db, "upgrade", "0050")
    hits = _rows(
        seeded_db,
        "SELECT search_documents.title FROM search_index"
        " JOIN search_documents ON search_documents.rowid = search_index.rowid"
        " WHERE search_index MATCH :m",
        {"m": '"스프린트"'},
    )
    titles = {row[0] for row in hits}
    assert titles == {"search_documents 정상", "search_documents 고아"}, (
        f"FTS 인덱스가 원본과 어긋났다: {titles}"
    )


def test_the_fts_triggers_are_back_so_new_rows_are_indexed(seeded_db):
    """트리거가 없으면 앞으로 들어오는 글이 **영원히** 검색에 안 걸린다."""
    _alembic(seeded_db, "upgrade", "0050")
    engine = _engine(seeded_db)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(SEED["search_documents"]),
                {"id": "sd-new", "tag": "새로 들어온 회의록", "ts": TS,
                 "org": DEFAULT_ORG_ID},
            )
    finally:
        engine.dispose()
    hits = _rows(
        seeded_db,
        "SELECT search_documents.title FROM search_index"
        " JOIN search_documents ON search_documents.rowid = search_index.rowid"
        " WHERE search_index MATCH :m",
        {"m": '"회의록"'},
    )
    assert [row[0] for row in hits] == ["새로 들어온 회의록"], (
        f"새 행이 색인되지 않았다(트리거가 사라졌다): {hits}"
    )


# ── 5) 왕복 ──────────────────────────────────────────────────────────────────


def test_upgrade_downgrade_upgrade_keeps_the_data(seeded_db):
    _alembic(seeded_db, "upgrade", "0050")
    before = {
        table: _rows(seeded_db, f"SELECT id, org_id FROM {table} ORDER BY id")
        for table in TABLES
    }

    _alembic(seeded_db, "downgrade", "-1")
    _alembic(seeded_db, "upgrade", "head")

    after = {
        table: _rows(seeded_db, f"SELECT id, org_id FROM {table} ORDER BY id")
        for table in TABLES
    }
    assert after == before, "왕복이 데이터를 바꿨다"
