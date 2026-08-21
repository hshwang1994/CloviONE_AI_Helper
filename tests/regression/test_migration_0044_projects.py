"""프로젝트 표들과 **소프트 프룬을 깨지 않았다**는 보증 (옛 0044).

qa-contract-change: 옛 파일은 SQLite alembic 체인의 upgrade→downgrade→upgrade 왕복을 돌려 이 성질을 확인했다. 그 체인은 은퇴했으므로(D-189) 그 형태의 시험은 성립하지 않는다 — 못박는 성질은 그대로 두고, 체인이 만들어 내던 것을 0001_pg_baseline 이 빠짐없이 갖고 있는가로 대상만 옮겼다.

왕복(되돌리기)을 보던 이유는 SQLite 의 `downgrade` 가 대개 **테이블 재생성**이라 컬럼·기본값·
인덱스가 조용히 달라졌기 때문이다. 기준선 하나로 접은 지금은 되돌릴 체인이 없고, 대신
**한 파일이 61회차분을 빠짐없이 담았는가**가 그 자리를 대신한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.regression

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


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def _indexes(db, table: str) -> set[str]:
    return {i["name"] for i in inspect(db.get_bind()).get_indexes(table)}


def test_every_project_table_exists(db):
    missing = set(NEW_TABLES) - set(inspect(db.get_bind()).get_table_names())
    assert not missing, f"기준선이 안 만든 표가 있다: {missing}"


def test_projects_keeps_its_full_column_set(db):
    missing = PROJECT_COLUMNS - _cols(db, "projects")
    assert not missing, f"projects 에서 빠진 컬럼: {missing}"


def test_the_child_tables_keep_the_columns_the_screens_read(db):
    assert "sort_order" in _cols(db, "project_milestones")
    assert "reasons_json" in _cols(db, "project_health_snapshots")
    assert {"summary_md", "source", "week_of"} <= _cols(db, "project_weekly_reports")


def test_the_ticket_mirror_keeps_parent_page_id_and_soft_prune(db):
    """`notion_missing_at` 은 **지우는 대신 표시한다**는 계약이다.

    이 컬럼이 없으면 티켓이 소스 응답에서 한 회차 깜빡일 때 행이 지워지고, 붙어 있던
    댓글·첨부·미push 본문이 CASCADE 로 함께 사라진다 — 셋 다 Notion 에 없어서 재동기화로
    돌아오지 않는다(`tests/regression/test_comment_survives_resync.py` 가 그 사고를 재현한다).
    """
    cols = _cols(db, "ticket_cache")
    assert "parent_page_id" in cols, "상위 작업 미러 컬럼이 없다 - 리프 판정을 할 수 없다"
    assert "notion_missing_at" in cols, "소프트 프룬 컬럼이 없다 - 깜빡임이 곧 데이터 손실이다"


def test_the_soft_prune_indexes_are_there(db):
    """보존 정리와 리프 집계가 매번 전수 스캔이 되지 않게 하는 인덱스들이다."""
    indexes = _indexes(db, "ticket_cache")
    assert "ix_ticket_cache_notion_missing_at" in indexes
    assert "ix_ticket_cache_parent_page_id" in indexes


def test_deleting_a_project_takes_its_children_with_it(db):
    """프로젝트는 **앱 정본**이다(미러가 아니다). 자식이 고아로 남으면 되살릴 소스가 없다."""
    fks = inspect(db.get_bind()).get_foreign_keys("project_milestones")
    project_fk = [fk for fk in fks if fk["referred_table"] == "projects"]
    assert project_fk, "project_milestones 가 projects 를 안 가리킨다"
