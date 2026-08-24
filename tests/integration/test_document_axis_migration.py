"""사용자 데이터의 조회 키가 옛 미러에서 정본 문서로 실제로 옮겨지는가 (S14 · C2).

이 revision(`0016_document_axis_to_documents`)의 위험은 스키마가 아니라 **데이터**다. 새
DB 에 그냥 돌리면 표가 비어 있어서 옮기는 절이 한 줄도 안 돈다 — 그 상태로 초록이면 이
migration 은 아무것도 증명하지 못한 채 운영에 나간다.

그래서 여기서는 자기 DB 를 받아 **0015 로 되감고, 옛 모양으로 행을 심고, 다시 올린다.**
보는 것 셋:

  1. 옛 page id 로 다리를 건널 수 있는 행은 **정본 문서 id 를 갖고 살아남는다.**
  2. 건널 다리가 없는 행은 **지워진다.** 그 행은 어느 화면에도 안 나오면서 유일 제약만
     갉아먹고, `document_id` 가 NOT NULL 이 되는 순간 스키마와도 모순이다.
  3. 옛 `document_id` 컬럼의 값은 **안 믿는다.** 운영에서 그 값은 이미 거의 전부 죽어
     있었다(최근 열람 54행 중 `documents.id` 에 맞는 것 0행) — 그것을 그대로 이어받으면
     사람이 남긴 것이 엉뚱한 문서에 붙는다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BEFORE = "0015_drop_dead_mirror_sync_rows"
AFTER = "0016_document_axis_to_documents"


def _alembic(url: str, target: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        if target == AFTER:
            command.upgrade(cfg, target)
        else:
            command.downgrade(cfg, target)
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior


def _insert_user(conn) -> None:
    from app.users.models import User

    from datetime import datetime

    now = datetime(2026, 8, 24, 0, 0, 0)
    values = {"id": "u-1", "email": "axis@goodmit.co.kr", "display_name": "축 시험",
              "role": "user", "password_hash": "x",
              "created_at": now, "updated_at": now}
    for column in User.__table__.columns:
        if column.name in values or column.nullable or column.server_default is not None:
            continue
        default = column.default
        arg = getattr(default, "arg", None) if default is not None else None
        values[column.name] = arg(None) if callable(arg) else arg
    conn.execute(User.__table__.insert().values(**values))


def _seed_old_shape(conn) -> None:
    """옛 모양 그대로 심는다: 조회 키는 page id 이고 `document_id` 는 못 믿을 값이다."""
    conn.execute(text(
        "INSERT INTO knowledge_spaces (id, name, slug, owner_kind, confidential, archived,"
        " version, created_at, updated_at)"
        " VALUES ('sp-1', '이관 공간', 'migrated', 'organization', false, false, 1,"
        " now(), now())"
    ))
    conn.execute(text(
        "INSERT INTO documents (id, space_id, title, source_type, confidential, archived,"
        " version, legacy_page_id, created_at, updated_at)"
        " VALUES ('doc-live', 'sp-1', '옮겨 온 문서', 'USER', false, false, 1,"
        " 'page-live', now(), now())"
    ))
    # 사용자 한 명. NOT NULL 컬럼을 손으로 나열하지 않는다 — `users` 는 컬럼이 스무 개
    # 넘고, 하나 빠질 때마다 이 시험이 자기 주제(축 이전)와 상관없는 이유로 빨개진다.
    # 서버 기본값이 없는 칸만 골라서 채운다.
    _insert_user(conn)
    # 다리를 건널 수 있는 행. `document_id` 에는 **일부러 엉뚱한 값**을 넣는다 — migration 이
    # 그 값을 그대로 믿으면 여기서 드러난다.
    conn.execute(text(
        "INSERT INTO document_favorites (id, user_id, notion_page_id, document_id, created_at)"
        " VALUES ('fav-live', 'u-1', 'page-live', 'stale-cache-uuid', now())"
    ))
    conn.execute(text(
        "INSERT INTO document_recent_views (id, user_id, notion_page_id, document_id, viewed_at)"
        " VALUES ('view-live', 'u-1', 'page-live', NULL, now())"
    ))
    conn.execute(text(
        "INSERT INTO document_comments (id, notion_page_id, document_id, author_user_id,"
        " body, created_at, updated_at)"
        " VALUES ('cm-live', 'page-live', NULL, 'u-1', '살아남아야 하는 댓글', now(), now())"
    ))
    # 건널 다리가 없는 행 — 그 page id 를 가진 문서가 이관되지 않았다.
    conn.execute(text(
        "INSERT INTO document_favorites (id, user_id, notion_page_id, document_id, created_at)"
        " VALUES ('fav-orphan', 'u-1', 'page-gone', NULL, now())"
    ))
    conn.execute(text(
        "INSERT INTO document_recent_views (id, user_id, notion_page_id, document_id, viewed_at)"
        " VALUES ('view-orphan', 'u-1', 'page-gone', NULL, now())"
    ))


def test_the_axis_moves_to_the_canonical_document(db_url):
    from app.core.db import normalize_database_url

    engine = create_engine(normalize_database_url(db_url))
    try:
        _alembic(db_url, BEFORE)
        with engine.begin() as conn:
            _seed_old_shape(conn)
        _alembic(db_url, AFTER)

        with engine.connect() as conn:
            # 1. 다리를 건넌 행은 정본 문서를 가리킨다.
            assert conn.execute(text(
                "SELECT document_id FROM document_favorites WHERE id = 'fav-live'"
            )).scalar_one() == "doc-live", "즐겨찾기가 정본 문서를 안 가리킨다"
            assert conn.execute(text(
                "SELECT document_id FROM document_recent_views WHERE id = 'view-live'"
            )).scalar_one() == "doc-live"
            assert conn.execute(text(
                "SELECT document_id FROM document_comments WHERE id = 'cm-live'"
            )).scalar_one() == "doc-live", "댓글이 정본 문서를 안 가리킨다"

            # 2. 건널 다리가 없던 행은 남지 않는다.
            for table, row_id in (
                ("document_favorites", "fav-orphan"),
                ("document_recent_views", "view-orphan"),
            ):
                left = conn.execute(text(
                    f"SELECT count(*) FROM {table} WHERE id = :i"), {"i": row_id}
                ).scalar_one()
                assert left == 0, f"{table}: 가리킬 데 없는 행이 남았다"

            # 3. 옛 조회 키는 컬럼째 사라졌다 — 다리가 둘이면 언젠가 다른 답을 낸다.
            for table in ("document_favorites", "document_recent_views", "document_comments"):
                cols = {r[0] for r in conn.execute(text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = :t"), {"t": table})}
                assert "notion_page_id" not in cols, f"{table}: 옛 조회 키가 남아 있다"
                assert "document_id" in cols
    finally:
        engine.dispose()


def test_rolling_back_refuses_to_invent_a_page_id(db_url):
    """되감기는 **거짓말을 만들지 않는다.**

    이 서버에서 새로 만든 문서에는 옛 page id 가 없다. 그런 문서에 달린 댓글을 되감으려면
    적을 값이 없는데, 아무 값이나 채우면 되감은 뒤 그 댓글이 엉뚱한 문서에 붙거나 사라진다.
    그래서 세어서 말하고 멈춘다.
    """
    from app.core.db import normalize_database_url

    engine = create_engine(normalize_database_url(db_url))
    try:
        _alembic(db_url, BEFORE)
        with engine.begin() as conn:
            _seed_old_shape(conn)
            # 옛 page id 가 없는 문서(이 서버에서 새로 만든 것)와 그 댓글.
            conn.execute(text(
                "INSERT INTO documents (id, space_id, title, source_type, confidential,"
                " archived, version, created_at, updated_at)"
                " VALUES ('doc-native', 'sp-1', '여기서 만든 문서', 'USER', false, false, 1,"
                " now(), now())"
            ))
        _alembic(db_url, AFTER)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO document_comments (id, document_id, author_user_id, body,"
                " created_at, updated_at)"
                " VALUES ('cm-native', 'doc-native', 'u-1', '여기서 쓴 댓글', now(), now())"
            ))

        with pytest.raises(RuntimeError, match="되감을 수 없습니다"):
            _alembic(db_url, BEFORE)
    finally:
        engine.dispose()
