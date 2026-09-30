"""0033 — 조직이 없는 프로젝트를 근거 있는 조직으로만 채운다 (계획 3.2).

못박는 성질:
1. 부서가 있으면 그 부서의 조직을 쓴다(기본 조직보다 먼저).
2. 부서가 없으면 기본 조직을 쓴다.
3. 이미 조직이 있는 프로젝트는 건드리지 않는다.
4. 정합성 검사가 마이그레이션 뒤 0건을 센다(검사는 감시로 남는다).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "0032_ticket_completed_backfill"


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
def test_backfill_fills_only_from_a_reason(db, db_url, make_project):
    from app.core.db import normalize_database_url
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department, Organization

    other = Organization(id=str(uuid.uuid4()), slug=f"other-{uuid.uuid4().hex[:8]}", name="다른 조직")
    db.add(other)
    db.flush()
    dept = Department(name="다른 조직 부서", org_id=other.id)
    db.add(dept)
    db.flush()

    with_dept = make_project(name="부서가 조직을 말한다")
    no_dept = make_project(name="부서 없음")
    kept = make_project(name="이미 조직 있음")
    db.flush()
    with_dept.dept_id = dept.id
    kept.org_id = other.id
    db.commit()
    ids = {"with_dept": with_dept.id, "no_dept": no_dept.id, "kept": kept.id}
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        with engine.begin() as conn:
            # 믹스인 기본값이 생기기 전의 옛 행을 흉내 낸다 - 앱 경로로는 이 상태를 만들 수 없다.
            conn.execute(text("UPDATE projects SET org_id = NULL WHERE id = ANY(:ids)"),
                         {"ids": [ids["with_dept"], ids["no_dept"]]})
        _alembic(db_url, "downgrade", BEFORE)
        _alembic(db_url, "upgrade", "head")
        with engine.connect() as conn:
            got = dict(conn.execute(text(
                "SELECT id, org_id FROM projects WHERE id = ANY(:ids)"
            ), {"ids": list(ids.values())}).all())
    finally:
        engine.dispose()

    assert got[ids["with_dept"]] == other.id, "부서가 말하는 조직보다 기본 조직을 먼저 썼다"
    assert got[ids["no_dept"]] == DEFAULT_ORG_ID, "부서 없는 옛 프로젝트를 기본 조직으로 채우지 않았다"
    assert got[ids["kept"]] == other.id, "이미 있던 조직을 덮었다"


@pytest.mark.real_db
def test_the_integrity_check_counts_none_after_the_backfill(db, db_url, make_project):
    from app.core.db import normalize_database_url
    from app.integrity import service

    stray = make_project(name="옛 행")
    db.commit()
    stray_id = stray.id
    db.close()
    db.get_bind().dispose()

    engine = sa.create_engine(normalize_database_url(db_url), future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE projects SET org_id = NULL WHERE id = :id"), {"id": stray_id})
        _alembic(db_url, "downgrade", BEFORE)
        _alembic(db_url, "upgrade", "head")
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            finding = next(
                f for f in service.report(session)["findings"] if f["key"] == "projects_without_scope"
            )
    finally:
        engine.dispose()
    assert finding["count"] == 0, finding
