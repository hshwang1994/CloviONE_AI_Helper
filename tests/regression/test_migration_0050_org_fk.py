"""`org_id` 가 **진짜 외래키**라는 성질 (옛 0050).

qa-contract-change: 옛 파일은 SQLite alembic 체인의 upgrade→downgrade→upgrade 왕복을 돌려 이 성질을 확인했다. 그 체인은 은퇴했으므로(D-189) 그 형태의 시험은 성립하지 않는다 — 못박는 성질은 그대로 두고, 체인이 만들어 내던 것을 0001_pg_baseline 이 빠짐없이 갖고 있는가로 대상만 옮겼다.

옛 파일의 핵심 통찰은 그대로 살렸다 — **FK 가 선언돼 있다는 것과 실제로 거부한다는 것은
다르다.** SQLite 에서는 `PRAGMA foreign_keys` 가 꺼져 있으면 선언만 남고 아무것도 안 막혔다.
PG 는 끌 수 없지만, 그 사실을 믿고 검사를 없애면 **다음에 이 표를 만드는 코드가 FK 를 빠뜨려도
아무도 모른다.** 그래서 여기서도 실제로 넣어 보고 지워 본다.

한 가지는 여기서 볼 수 없다: 옛 파일이 확인하던 **고아 행을 기본 조직으로 옮긴다**는 백필은
새 설치에 옮길 고아가 없다. 그건 S13 Migration Tool 이 운영 데이터를 옮길 때 보는 일이다.

qa-contract-change: S5 가 조직도 마디 표의 이름을 `departments` 에서 `org_units` 로 옮겼다(app/org/models.py::OrgUnit · 0002_identity_access). 단언의 뜻과 수는 그대로이고 가리키는 표 이름만 새 이름으로 맞춘다 — 옛 이름을 그대로 두면 이 시험이 없는 표를 찾는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

pytestmark = pytest.mark.regression

# 0050 이 FK 를 건 표들. 스코프 판정이 이 컬럼 하나에 매달려 있다.
TABLES = (
    "org_units",
    "board_posts",
    "document_cache",
    "chat_rooms",
    "game_rooms",
    "trash_items",
    "usage_events",
    "search_documents",
)


@pytest.mark.parametrize("table", TABLES)
def test_org_id_is_a_declared_foreign_key(db, table):
    """컬럼만 있고 FK 가 없으면 없는 조직을 가리키는 행이 조용히 쌓인다."""
    fks = inspect(db.get_bind()).get_foreign_keys(table)
    org_fks = [fk for fk in fks if fk["constrained_columns"] == ["org_id"]]
    assert org_fks, f"{table}.org_id 에 외래키가 없다 (있는 것: {fks})"
    assert org_fks[0]["referred_table"] == "organizations"


def test_a_bogus_org_id_is_actually_rejected(db):
    """선언을 읽는 대신 **실제 행에 넣어 본다.** 선언과 강제는 다른 일이다.

    빈 표에 `UPDATE` 를 치면 0행이 바뀌고 FK 는 발동하지 않는다 — 그렇게 쓴 검사는 FK 가
    아예 없어도 통과한다. 그래서 행을 먼저 만들고 그 행의 소속을 없는 조직으로 바꾼다.
    """
    from sqlalchemy.exc import IntegrityError

    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    row = Department(name="FK확인팀", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.flush()

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE org_units SET org_id = :bogus WHERE id = :id"),
            {"bogus": "no-such-org", "id": row.id},
        )
        db.flush()
    db.rollback()


def test_the_search_index_rejects_a_bogus_org_too(db):
    """검색 색인은 **유출 경로**라 따로 본다 — 소속을 못 믿으면 스코프 필터도 못 믿는다."""
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    from app.search.models import SearchDocument

    row = SearchDocument(
        kind="ticket", ref_id="fk-check", title="소속 확인", body="",
        owner_user_ids="", route="/x", indexed_at=datetime(2026, 8, 21, 9, 0, 0),
    )
    db.add(row)
    db.flush()

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE search_documents SET org_id = :bogus WHERE id = :id"),
            {"bogus": "no-such-org", "id": row.id},
        )
        db.flush()
    db.rollback()


def test_deleting_an_organization_that_still_owns_rows_is_refused(db):
    """FK 가 참조 무결성을 실제로 강제하는가. 지워지면 그 행들이 통째로 고아가 된다."""
    from sqlalchemy.exc import IntegrityError

    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    db.add(Department(name="조직삭제확인팀", org_id=DEFAULT_ORG_ID))
    db.flush()
    with pytest.raises(IntegrityError):
        db.execute(
            text("DELETE FROM organizations WHERE id = :org"), {"org": DEFAULT_ORG_ID}
        )
        db.flush()
    db.rollback()


def test_the_search_index_is_scoped_too(db):
    """검색 색인이 스코프 밖이면 목록에서 막은 것을 검색이 보여 준다 — 유출 경로 하나다."""
    assert "org_id" in {c["name"] for c in inspect(db.get_bind()).get_columns("search_documents")}
