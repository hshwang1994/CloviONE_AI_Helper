"""조직 스코프가 **실제로 거른다**는 성질 (옛 0024).

qa-contract-change: 옛 파일은 SQLite alembic 체인의 upgrade→downgrade→upgrade 왕복을 돌려 이 성질을 확인했다. 그 체인은 은퇴했으므로(D-189) 그 형태의 시험은 성립하지 않는다 — 못박는 성질은 그대로 두고, 체인이 만들어 내던 것을 0001_pg_baseline 이 빠짐없이 갖고 있는가로 대상만 옮겼다.

옛 파일이 특히 공들여 못박던 것 하나는 그대로 살렸다 — **인덱스가 있다는 것과 실제로
막는다는 것은 다르다.** SQLite 는 UNIQUE 인덱스에서 NULL 을 서로 다른 값으로 봐서, 인덱스가
멀쩡히 존재하는데 중복이 그냥 들어갔다. 그래서 존재를 보지 않고 **INSERT 를 쳐서** 본다.
PG 도 같은 NULL 규칙이라 이 검사는 여기서도 그대로 의미가 있다.

데이터 이관 자체의 무결성은 S13 Migration Tool 의 Dry Run 이 본다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.regression


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


@pytest.mark.parametrize(
    "table",
    ["departments", "board_posts", "chat_rooms", "trash_items", "search_documents"],
)
def test_org_scoped_tables_all_carry_org_id(db, table):
    """`org_id` 가 없는 표는 스코프 필터가 아예 닿지 못한다."""
    assert "org_id" in _cols(db, table)


def test_a_new_row_gets_a_real_org_not_null(db):
    """**이것이 이 파일에서 가장 중요한 성질이다.**

    `org_id` 가 NULL 이면 두 가지가 조용히 깨진다: `(org_id, name)` 복합 유니크가 아무것도
    막지 않고(NULL 은 서로 다른 값이다), `WHERE org_id = :org` 가 그 행을 통째로 못 고른다.
    마이그레이션이 백필만 하고 신규 행이 NULL 로 들어가면 다음 날부터 구멍이 다시 열린다 —
    그래서 **기본값**이 그 자리를 지킨다(`OrgScopedMixin`).
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    row = Department(name="기본 조직 확인용")
    db.add(row)
    db.flush()
    assert row.org_id == DEFAULT_ORG_ID


def test_duplicate_department_name_in_the_same_org_is_actually_rejected(db):
    """인덱스가 있다는 것과 막는다는 것은 다르다 — **INSERT 를 쳐서** 본다."""
    from sqlalchemy.exc import IntegrityError

    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    db.add(Department(name="중복팀", org_id=DEFAULT_ORG_ID))
    db.flush()
    db.add(Department(name="중복팀", org_id=DEFAULT_ORG_ID))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_same_name_in_a_different_org_is_allowed(db, two_orgs):
    """유니크는 조직 안에서만이다 — 전역이면 두 회사가 같은 팀 이름을 못 쓴다.

    이 시험이 있어야 위 시험이 «전역 유니크» 로 조용히 강해지는 것을 잡을 수 있다.
    """
    from app.org.models import Department

    db.add(Department(name="공통팀", org_id=two_orgs.org_a_id))
    db.add(Department(name="공통팀", org_id=two_orgs.org_b_id))
    db.flush()  # 예외가 나면 실패다.


def test_departments_form_a_tree(db):
    """`parent_id` 가 있어야 부서 계층이 표현된다."""
    assert "parent_id" in _cols(db, "departments")


def test_admin_scope_defaults_to_global(db, make_user):
    """기존 관리자가 계속 일하려면 기본이 global 이어야 한다."""
    user = make_user("scope-default@goodmit.co.kr", role="admin")
    assert user.admin_scope == "global"
