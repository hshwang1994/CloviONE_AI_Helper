"""0031 — `projects.stats_computed_at` 가 '계산 전' 과 '셀 것 없음' 을 가른다 (계획 3.1).

못박는 성질:
1. 값이 하나라도 있는 행은 되채우기로 계산 시각을 얻는다(이미 계산된 것이다).
2. 둘 다 비어 있는 행은 NULL 로 남는다 - 어느 뜻인지 모르므로 다음 스윕이 가장 먼저 채운다.
3. 되돌리면 칸과 인덱스만 사라지고 행은 그대로다. 다시 올리면 같은 규칙으로 채운다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0030_search_fold"


def _alembic(url: str, action: str, target: str) -> None:
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
def test_backfill_marks_only_rows_that_were_already_computed(db, db_url, make_project):
    from app.core.db import normalize_database_url

    scored = make_project(name="이미 계산된 프로젝트")
    empty = make_project(name="아무것도 모르는 프로젝트")
    scored.progress_pct = 40.0
    scored.health_score = 80
    db.commit()
    scored_id, empty_id = scored.id, empty.id
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        _alembic(db_url, "downgrade", BEFORE)
        with engine.connect() as conn:
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'projects'"
            ))}
            assert "stats_computed_at" not in cols, "되돌리기가 칸을 안 지웠다"
            assert conn.execute(text("SELECT count(*) FROM projects WHERE id IN (:a, :b)"),
                                {"a": scored_id, "b": empty_id}).scalar() == 2, "되돌리기가 행을 잃었다"

        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT id, stats_computed_at FROM projects WHERE id IN (:a, :b)"
            ), {"a": scored_id, "b": empty_id}).all())
            assert got[scored_id] is not None, "값이 있는 행이 계산 시각을 못 받았다"
            assert got[empty_id] is None, "뜻을 모르는 행에 계산 시각을 지어냈다"
            idx = conn.execute(text(
                "SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_projects_stats_computed_at'"
            )).scalar()
            assert idx == 1
    finally:
        engine.dispose()
