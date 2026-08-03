"""0025(self_id_refs) — 자체 id 백필과, **레거시 컬럼을 지우지 않았다**는 보증.

두 가지를 확인한다.

1. **백필이 실제로 값을 채웠는가.** 컬럼만 생기고 전부 NULL 이면 소스 전환 때 이어질 다리가
   없는 것과 같다(그런데 스키마만 보면 멀쩡해 보인다).

2. **`notion_page_id` 가 남아 있는가.** 휴지통의 중복 방지 키가 거기 걸려 있다
   (`uq_trash_item(item_type, notion_page_id)`). 떼면 같은 페이지를 두 번 버릴 수 있게 되고
   복원 시 목록에 중복 행이 생긴다. "자체 id 가 생겼으니 옛 컬럼은 지워도 되겠지"가 정확히
   이 사고를 만드는 판단이라, 여기서 명시적으로 못박는다.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TS = "2026-08-01 00:00:00.000000"


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic {args} 실패:\n{result.stdout}\n{result.stderr}"


def _rows(db_path: Path, sql: str) -> list[tuple]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql))]
    finally:
        engine.dispose()


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Path:
    """0028(=0025 직전) 까지 올린 뒤, 미러와 참조 행을 넣는다.

    일부러 **미러에 없는 페이지**도 하나 섞는다 — 그 행의 자체 id 는 NULL 로 남아야 하고,
    그것이 정상 상태다(방금 만들어져 아직 동기화 안 된 문서를 즐겨찾기할 수 있다).
    """
    db_path = tmp_path / "self_ids.sqlite3"
    _alembic(db_path, "upgrade", "0028")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO document_cache (id, notion_page_id, title, type_names,"
            " category_names, project_names, author_names, owner, memo, has_files,"
            " notion_favorite, archived, synced_at, tech_tags, classification_manual)"
            " VALUES ('doc-uid-1', 'page-doc-1', '문서 하나', '', '', '', '', '', '',"
            " 0, 0, 0, :ts, '', 0)"
        ), {"ts": TS})
        conn.execute(text(
            "INSERT INTO ticket_cache (id, notion_page_id, title, project_ids,"
            " project_names, assignee_notion_ids, source, synced_at, created_at, updated_at)"
            " VALUES ('tkt-uid-1', 'page-tkt-1', '티켓 하나', '', '', '', 'notion',"
            " :ts, :ts, :ts)"
        ), {"ts": TS})

        conn.execute(text(
            "INSERT INTO document_favorites (id, user_id, notion_page_id, created_at)"
            " VALUES ('fav-1', 'u-1', 'page-doc-1', :ts)"
        ), {"ts": TS})
        conn.execute(text(  # 미러에 없는 페이지 — NULL 로 남아야 한다
            "INSERT INTO document_favorites (id, user_id, notion_page_id, created_at)"
            " VALUES ('fav-2', 'u-1', 'page-not-synced', :ts)"
        ), {"ts": TS})
        conn.execute(text(
            "INSERT INTO document_recent_views (id, user_id, notion_page_id, viewed_at)"
            " VALUES ('rec-1', 'u-1', 'page-doc-1', :ts)"
        ), {"ts": TS})
        conn.execute(text(
            "INSERT INTO trash_items (id, item_type, notion_page_id, title,"
            " deleted_by_user_id, deleted_by_name, deleted_at)"
            " VALUES ('trash-1', 'document', 'page-doc-1', '문서 하나', 'u-1', '김', :ts)"
        ), {"ts": TS})
        conn.execute(text(
            "INSERT INTO trash_items (id, item_type, notion_page_id, title,"
            " deleted_by_user_id, deleted_by_name, deleted_at)"
            " VALUES ('trash-2', 'ticket', 'page-tkt-1', '티켓 하나', 'u-1', '김', :ts)"
        ), {"ts": TS})
    engine.dispose()
    return db_path


def test_backfill_fills_real_ids_where_the_mirror_has_the_row(seeded_db):
    _alembic(seeded_db, "upgrade", "0025")

    assert _rows(seeded_db, "SELECT document_id FROM document_favorites WHERE id='fav-1'") == [
        ("doc-uid-1",)
    ]
    assert _rows(seeded_db, "SELECT document_id FROM document_recent_views WHERE id='rec-1'") == [
        ("doc-uid-1",)
    ]
    assert _rows(seeded_db, "SELECT target_uid FROM trash_items WHERE id='trash-1'") == [
        ("doc-uid-1",)
    ]
    assert _rows(seeded_db, "SELECT target_uid FROM trash_items WHERE id='trash-2'") == [
        ("tkt-uid-1",)
    ]


def test_rows_without_a_mirror_row_stay_null(seeded_db):
    """NULL 이 정상이다 — 아직 동기화되지 않은 페이지를 가리키는 참조가 있을 수 있다."""
    _alembic(seeded_db, "upgrade", "0025")
    assert _rows(seeded_db, "SELECT document_id FROM document_favorites WHERE id='fav-2'") == [
        (None,)
    ]


def test_the_legacy_notion_page_id_columns_are_kept(seeded_db):
    """휴지통 중복 방지 키가 여기 걸려 있다 — 지우면 중복 복원이 생긴다."""
    _alembic(seeded_db, "upgrade", "0025")
    for table in ("document_favorites", "document_recent_views", "trash_items"):
        cols = {c[1] for c in _rows(seeded_db, f"PRAGMA table_info({table})")}
        assert "notion_page_id" in cols, f"{table}.notion_page_id 가 사라졌다"


def test_the_trash_dedupe_key_still_rejects_a_second_delete(seeded_db):
    """제약이 '있다'가 아니라 두 번째 삭제가 '거부된다'를 본다."""
    import sqlalchemy as sa

    _alembic(seeded_db, "upgrade", "0025")
    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO trash_items (id, item_type, notion_page_id, title,"
                    " deleted_by_user_id, deleted_by_name, deleted_at)"
                    " VALUES ('trash-dup', 'document', 'page-doc-1', '문서 하나',"
                    " 'u-2', '이', :ts)"
                ), {"ts": TS})
    finally:
        engine.dispose()


def test_roundtrip_keeps_rows_and_the_dedupe_constraint(seeded_db):
    """downgrade 는 SQLite 에서 테이블 재생성이다 — 유니크 제약이 조용히 사라질 수 있다."""
    _alembic(seeded_db, "upgrade", "0025")
    _alembic(seeded_db, "downgrade", "0028")

    cols = {c[1] for c in _rows(seeded_db, "PRAGMA table_info(trash_items)")}
    assert "target_uid" not in cols
    assert _rows(seeded_db, "SELECT COUNT(*) FROM trash_items") == [(2,)]

    _alembic(seeded_db, "upgrade", "0025")
    assert _rows(seeded_db, "SELECT COUNT(*) FROM trash_items") == [(2,)]
    assert _rows(seeded_db, "SELECT target_uid FROM trash_items WHERE id='trash-2'") == [
        ("tkt-uid-1",)
    ]

    # 왕복 뒤에도 중복 방지가 **실제로** 살아 있어야 한다.
    #
    # 인덱스 이름으로 확인하지 않는 이유: `uq_trash_item` 은 테이블 레벨 UNIQUE 제약이라
    # SQLite 가 이름 없는 `sqlite_autoindex_trash_items_2` 로 구현한다. 이름을 찾는 검사는
    # 배치 재생성 전에도 통과하지 못한다(= 헛도는 검사다). 제약이 있는지는 INSERT 로 본다.
    import sqlalchemy as sa

    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO trash_items (id, item_type, notion_page_id, title,"
                    " deleted_by_user_id, deleted_by_name, deleted_at)"
                    " VALUES ('trash-dup2', 'ticket', 'page-tkt-1', '티켓 하나',"
                    " 'u-2', '이', :ts)"
                ), {"ts": TS})
    finally:
        engine.dispose()


def test_new_favorites_get_the_self_id_at_write_time(db, make_user):
    """마이그레이션이 백필한 뒤에도, **새 행**이 NULL 로 들어가면 구멍이 다시 열린다."""
    from datetime import datetime

    from app.team_docs.models import DocumentCache
    from app.team_docs.service import toggle_favorite

    now = datetime(2026, 8, 3, 9, 0, 0)
    db.add(DocumentCache(id="dc-1", notion_page_id="page-x", title="문서", synced_at=now))
    db.flush()

    user = make_user(email="fav@goodmit.co.kr")
    toggle_favorite(db, user_id=user.id, page_id="page-x", on=True, now=now)
    db.flush()

    from sqlalchemy import select

    from app.team_docs.models import DocumentFavorite

    row = db.execute(
        select(DocumentFavorite).where(DocumentFavorite.notion_page_id == "page-x")
    ).scalar_one()
    assert row.document_id == "dc-1"
