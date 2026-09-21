"""0030 — 검색 대조의 대상 쪽 짝이 DB 안에 제대로 섰는가 (D-495).

여기서 못박는 성질 다섯:

1. **함수가 생성 열을 받을 수 있는 모양이다** — IMMUTABLE · PARALLEL SAFE 이고, STRICT 도
   SET 절도 없어서 플래너가 질의 안에 펼친다(inline). 펼쳐지지 않으면 작은 표 검색이 행마다
   함수 호출이 된다.
2. **생성 열 셋이 STORED 로 서 있다** — `attgenerated='s'`, 식이 `search_fold(원문)`.
3. **인덱스가 새 자리로 옮겨 갔다** — 접힌 열 위 GIN 셋이 있고 원문 위 트라이그램 셋은 없다.
   FTS 인덱스는 그대로다.
4. **플래너가 새 인덱스를 쓸 수 있다** — seq scan 을 끄고 물었을 때 통합 검색 · AI 레인의
   질의가 그 인덱스를 고른다. 식이 어긋나면 강제해도 못 쓴다(D-209 과 같은 관용).
5. **되돌리기가 정확하다** — 0029 로 내리면 함수·열·새 인덱스가 사라지고 옛 원문 인덱스가
   `0001`·`0008` 의 모양 그대로 돌아오며, 행은 한 줄도 안 잃는다. 다시 올리면 이미 있던 행도
   접힌 값을 얻는다. 되돌리기는 `test_migration_0023_0024_reaudit.py` 도 실제로 지나간다.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import literal, select, text

from app.ai.models import DocumentChunk
from app.ai.retrieval import query as ai_query
from app.core.search_text import fold, like_folded, pattern_for
from app.search import query as search_query
from app.search.models import SearchDocument
from app.users.models import User
from tests.fakes.explain import plan_for

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0029_sprint_team_owner"
NOW = datetime(2026, 9, 21, 9, 0, 0)

FOLDED = (
    ("search_documents", "title_fold", "search_fold(title)"),
    ("search_documents", "body_fold", "search_fold(body)"),
    ("document_chunks", "text_fold", "search_fold(text)"),
)
NEW_INDEXES = {
    "ix_search_documents_title_fold_trgm": ("search_documents", "(title_fold gin_trgm_ops)"),
    "ix_search_documents_body_fold_trgm": ("search_documents", "(body_fold gin_trgm_ops)"),
    "ix_chunk_text_fold_trgm": ("document_chunks", "(text_fold gin_trgm_ops)"),
}
RAW_INDEXES = {
    "ix_search_documents_title_trgm": ("search_documents", "USING gin (title gin_trgm_ops)"),
    "ix_search_documents_body_trgm": ("search_documents", "USING gin (body gin_trgm_ops)"),
    "ix_chunk_text_trgm": ("document_chunks", "USING gin (text gin_trgm_ops)"),
}


def _indexdefs(conn) -> dict[str, str]:
    rows = conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE tablename IN ('search_documents', 'document_chunks')"
    )).all()
    return {name: definition for name, definition in rows}


def _generated(conn) -> dict[tuple[str, str], tuple[str, str, bool]]:
    rows = conn.execute(text(
        "SELECT c.relname, a.attname, a.attgenerated, pg_get_expr(d.adbin, d.adrelid), a.attnotnull "
        "FROM pg_attribute a "
        "JOIN pg_class c ON c.oid = a.attrelid "
        "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
        "WHERE c.relname IN ('search_documents', 'document_chunks') "
        "AND a.attname IN ('title_fold', 'body_fold', 'text_fold') AND NOT a.attisdropped"
    )).all()
    return {(table, column): (kind, expr, notnull) for table, column, kind, expr, notnull in rows}


# ── 1 · 함수 ─────────────────────────────────────────────────────────────────


def test_the_fold_function_can_back_a_generated_column_and_be_inlined(db):
    row = db.execute(text(
        "SELECT p.provolatile, p.proparallel, p.proisstrict, p.proconfig, l.lanname "
        "FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang "
        "WHERE p.proname = 'search_fold'"
    )).one()
    volatility, parallel, strict, config, language = row
    assert volatility == "i", "IMMUTABLE 이 아니면 생성 열·인덱스 식에 쓸 수 없다"
    assert parallel == "s", "PARALLEL SAFE 가 아니면 병렬 스캔에서 빠진다"
    assert strict is False, "STRICT 가 붙으면 플래너가 함수를 펼치지 못한다"
    assert config is None, "SET 절이 붙으면 플래너가 함수를 펼치지 못한다"
    assert language == "sql"


def test_the_planner_inlines_the_function_into_small_table_searches(db):
    """작은 표는 질의 때 접는다 — 그때 행마다 함수 호출이 아니라 식 그대로 들어가야 한다."""
    stmt = select(literal(1)).select_from(User).where(
        like_folded(User.display_name, pattern_for("김 지혜"))
    )
    plan = plan_for(db, stmt)
    assert "regexp_replace" in plan, f"접기 식이 계획에 안 보인다: {plan}"
    assert "search_fold(" not in plan, f"함수가 펼쳐지지 않고 호출로 남았다: {plan}"


# ── 2 · 생성 열 ───────────────────────────────────────────────────────────────


def test_the_three_folded_copies_are_stored_generated_columns(db):
    found = _generated(db)
    assert len(found) == len(FOLDED), f"접힌 열이 {len(found)}개다: {found}"
    for table, column, expression in FOLDED:
        kind, expr, notnull = found[(table, column)]
        assert kind == "s", f"{table}.{column} 이 STORED 생성 열이 아니다"
        assert expr == expression, f"{table}.{column} 의 식이 다르다: {expr}"
        assert notnull is True, f"{table}.{column} 이 NULL 을 받는다"


# ── 3 · 인덱스 ───────────────────────────────────────────────────────────────


def test_the_trigram_indexes_moved_to_the_folded_columns(db):
    defs = _indexdefs(db)
    for name, (table, body) in NEW_INDEXES.items():
        assert name in defs, f"{name} 이 없다"
        assert f"ON public.{table} USING gin {body}" in defs[name], defs[name]
    for name in RAW_INDEXES:
        assert name not in defs, f"원문 위 트라이그램 인덱스 {name} 가 남았다 — 받을 조건이 없다"
    assert "ix_chunk_text_fts" in defs, "FTS 인덱스는 원문 위에 남아야 한다"


# ── 4 · 플래너가 쓸 수 있는가 ────────────────────────────────────────────────


def test_unified_search_can_use_both_folded_indexes(db):
    normalized = search_query.normalize("현황 제외")
    stmt = select(SearchDocument.id).where(search_query.trgm_clause(normalized))
    plan = plan_for(db, stmt, force_index=True)
    assert "ix_search_documents_title_fold_trgm" in plan, plan
    assert "ix_search_documents_body_fold_trgm" in plan, plan


def test_the_ai_trigram_lane_can_use_its_folded_index(db):
    plan = plan_for(db, ai_query.trgm_lane("현황 제외", limit=5), force_index=True)
    assert "ix_chunk_text_fold_trgm" in plan, plan


def test_the_search_conditions_read_the_stored_copy(db):
    """큰 표는 저장된 사본을 읽는다. 질의 때 다시 접으면 인덱스를 못 탄다."""
    sql = str(search_query.trgm_clause("현황 제외").compile())
    assert "title_fold" in sql and "body_fold" in sql
    assert "search_fold(" not in sql
    lane = str(ai_query.trgm_lane("현황 제외").compile())
    assert "text_fold" in lane and "search_fold(" not in lane


# ── 5 · 되돌리기 왕복 ─────────────────────────────────────────────────────────


def _alembic(url: str, action: str, target: str) -> None:
    """`conftest.py::migrated_db_template` 과 같은 방법 — 이 시험 전용 DB 로 잠깐 바꿔 돌린다."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        getattr(command, action)(cfg, target)
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior


@pytest.mark.real_db
def test_the_round_trip_restores_the_raw_indexes_and_refolds_existing_rows(
    db, db_url, make_space, make_knowledge_document
):
    from app.core.db import normalize_database_url

    title = "현황 제외 ＣｌｏｖｉｒＯＮＥ"
    chunk_text = "현황\u3000제외 목록을 정리합니다"
    db.add(SearchDocument(
        kind="ticket", ref_id="fold-roundtrip", title=title, body="본문",
        owner_user_ids="", route="/x", indexed_at=NOW,
    ))
    space = make_space(name="접기 공간", org_wide=True)
    document = make_knowledge_document(space=space, title="접기 문서", text=chunk_text)
    db.add(DocumentChunk(
        source_kind="document", document_id=document.id, ordinal=0,
        anchor_kind="text", anchor_ref="0", anchor_label="",
        text_body=chunk_text, text_sha256="0" * 64, parser_version="t", indexed_at=NOW,
    ))
    db.commit()
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        # ── 내린다 ──
        _alembic(db_url, "downgrade", BEFORE)
        with engine.connect() as conn:
            assert conn.execute(text(
                "SELECT count(*) FROM pg_proc WHERE proname = 'search_fold'"
            )).scalar() == 0, "되돌리기가 함수를 안 지웠다"
            assert _generated(conn) == {}, "되돌리기가 접힌 열을 안 지웠다"
            defs = _indexdefs(conn)
            for name in NEW_INDEXES:
                assert name not in defs, f"되돌리기가 {name} 을 안 지웠다"
            for name, (table, body) in RAW_INDEXES.items():
                assert name in defs, f"되돌리기가 {name} 을 복원하지 않았다"
                assert f"ON public.{table} {body}" in defs[name], defs[name]
            # 행은 한 줄도 안 잃는다 — 지운 것은 파생 값뿐이다.
            assert conn.execute(text(
                "SELECT title FROM search_documents WHERE ref_id = 'fold-roundtrip'"
            )).scalar() == title
            assert conn.execute(text(
                "SELECT text FROM document_chunks WHERE document_id = :d"
            ), {"d": document.id}).scalar() == chunk_text

        # ── 다시 올린다 ──
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            folded_title = conn.execute(text(
                "SELECT title_fold FROM search_documents WHERE ref_id = 'fold-roundtrip'"
            )).scalar()
            folded_chunk = conn.execute(text(
                "SELECT text_fold FROM document_chunks WHERE document_id = :d"
            ), {"d": document.id}).scalar()
            assert folded_title == fold(title) == "현황제외clovirone"
            assert folded_chunk == fold(chunk_text) == "현황제외목록을정리합니다"
            defs = _indexdefs(conn)
            assert set(NEW_INDEXES) <= set(defs)
            assert not set(RAW_INDEXES) & set(defs)
    finally:
        engine.dispose()
