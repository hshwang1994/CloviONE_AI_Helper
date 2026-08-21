"""부서·직책이 **문자열이 아니라 표**라는 성질 (옛 0015).

qa-contract-change: 옛 파일은 SQLite alembic 체인의 upgrade→downgrade→upgrade 왕복을 돌려 이 성질을 확인했다. 그 체인은 은퇴했으므로(D-189) 그 형태의 시험은 성립하지 않는다 — 못박는 성질은 그대로 두고, 체인이 만들어 내던 것을 0001_pg_baseline 이 빠짐없이 갖고 있는가로 대상만 옮겼다.

이 방향 전환은 D-189 가 경고한 실패를 정면으로 겨눈다 — 61개 revision 을 한 파일로 접으면서
**조용히 빠지는 것**이 생기는 것. 옛 왕복 시험은 "되돌릴 수 있는가" 를 봤고, 여기서는
"빠뜨리지 않았는가" 를 본다. 지금 필요한 것은 후자다.

데이터 이관 자체(운영 SQLite → PG)의 무결성은 S13 Migration Tool 의 Dry Run 이 본다
(MASTER_PLAN §9.3 의 면제 불가 검증 목록).
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.regression


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def _tables(db) -> set[str]:
    return set(inspect(db.get_bind()).get_table_names())


def test_departments_and_job_titles_are_tables_not_strings(db):
    """이 둘이 표여야 "한 곳만 고치면 전원에 반영" 이 참이 된다.

    문자열 컬럼으로 두면 같은 부서가 표기만 다른 여러 값으로 갈라지고, 그걸 되돌릴 방법이
    없다. 0015 가 옮긴 것이 이것이고, 기준선이 그 결과를 그대로 갖고 있어야 한다.
    """
    assert {"departments", "job_titles"} <= _tables(db)


@pytest.mark.parametrize("table", ["departments", "job_titles"])
def test_the_lookup_tables_keep_their_shape(db, table):
    assert {"id", "name", "active", "created_at"} <= _cols(db, table)


def test_users_point_at_those_tables_by_id(db):
    """FK 컬럼이 있어야 이름을 고쳐도 사람 쪽이 따라온다."""
    cols = _cols(db, "users")
    assert "department_id" in cols
    assert "title_id" in cols


def test_the_foreign_keys_are_declared_not_just_the_columns(db):
    """컬럼만 있고 FK 가 없으면 지워진 부서를 가리키는 사람이 남는다."""
    fks = inspect(db.get_bind()).get_foreign_keys("users")
    referred = {tuple(fk["constrained_columns"]): fk["referred_table"] for fk in fks}
    assert referred.get(("department_id",)) == "departments"
    assert referred.get(("title_id",)) == "job_titles"


def test_a_new_lookup_row_is_active_by_default(db):
    """`active` 기본값이 없으면 새로 만든 부서가 아무 화면에도 안 보인다."""
    from app.org.models import Department

    row = Department(name="새로 만든 팀")
    db.add(row)
    db.flush()
    assert row.active is True
