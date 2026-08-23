"""복구 리허설의 **검사 질의 자체**를 먼저 검증한다 (S12 · CLAUDE.md §7).

## 왜 이 파일이 있는가

리허설 4단계는 「복원본의 스키마 성질이 원본과 같은가」를 센다. 그 질의가 **아무것도
못 세는 질의**여도 원본과 복원본이 똑같이 0 을 돌려주므로 비교는 통과한다 — 검사가
켜져 있는데 아무것도 안 보는 상태이고, 그것이 이 종류의 하네스에서 가장 흔한 실패다.

그래서 Product 판정 전에 셋을 확인한다:

  * **Known Good** — 실제 스키마에서 넷이 전부 0 보다 크다(정말 세고 있다).
  * **Known Bad** — 인덱스를 하나 지우면 그 수가 **줄어든다**(차이를 실제로 본다).
  * **반례** — 부분 유니크의 `WHERE` 절 원문이 다르면 잡힌다. 개수만 세면 「인덱스는
    왔는데 `WHERE` 가 빠졌다」를 못 잡는데, 그때 그 인덱스는 **전체 유니크**가 되어
    정상 재요청을 막는다(D-189 가 경고한 자리).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.db import make_engine
from scripts.restore_rehearsal import (
    SHAPE_QUERIES,
    _partial_unique_predicates,
    _row_counts,
    _shape,
    _table_names,
)

# 전용 DB 가 필요하다(D-190) — 인덱스를 실제로 지웠다 되살리기 때문이다.
pytestmark = [pytest.mark.regression, pytest.mark.real_db]


@pytest.fixture()
def conn(db_url):
    engine = make_engine(db_url)
    with engine.connect() as c:
        yield c


# ── Known Good ───────────────────────────────────────────────────────────────


def test_every_shape_query_actually_counts_something(conn):
    """넷 다 0 보다 커야 한다. 0 이면 그 축은 **검사되지 않는 축**이다."""
    shape = _shape(conn)
    assert set(shape) == set(SHAPE_QUERIES)
    for key in ("partial_unique_indexes", "trgm_gin_indexes", "jsonb_columns", "foreign_keys"):
        assert shape[key] > 0, f"{key} 가 0 이다 — 이 축은 아무것도 비교하지 못한다"


def test_table_and_row_probes_see_the_real_schema(conn):
    tables = _table_names(conn)
    assert "backups" in tables and "documents" in tables
    counts = _row_counts(conn, ["backups"])
    assert counts["backups"] >= 0


def test_a_missing_table_is_reported_not_skipped(conn):
    """세지 못한 표를 0 으로 보고하면 「비었다」와 「못 읽었다」가 같아진다."""
    assert _row_counts(conn, ["표가_없어요"])["표가_없어요"] == -1


# ── Known Bad — 차이를 실제로 보는가 ─────────────────────────────────────────


def test_dropping_a_partial_unique_index_is_visible(conn):
    """🔴 인덱스를 하나 지우면 그 수가 줄어야 한다.

    이 검사가 없으면 「언제나 같은 수를 돌려주는 질의」도 4단계를 통과시킨다.
    """
    before = _shape(conn)["partial_unique_indexes"]
    conn.execute(
        text(
            "create unique index ux_probe_partial on backups (checksum) "
            "where status = 'verified'"
        )
    )
    conn.commit()
    try:
        assert _shape(conn)["partial_unique_indexes"] == before + 1
    finally:
        conn.execute(text("drop index ux_probe_partial"))
        conn.commit()
    assert _shape(conn)["partial_unique_indexes"] == before


def test_the_where_clause_itself_is_compared_not_just_the_count(conn):
    """개수가 같아도 **조건이 다르면** 다른 인덱스다.

    두 인덱스를 차례로 만들되 `WHERE` 만 다르게 둔다. 개수는 둘 다 `before + 1` 이지만
    술어 집합은 달라야 한다 — 그것을 못 보면 「부분 유니크가 전체 유니크가 됐다」를
    놓친다.
    """
    conn.execute(
        text(
            "create unique index ux_probe_a on backups (checksum) where status = 'verified'"
        )
    )
    conn.commit()
    with_a = _partial_unique_predicates(conn)
    conn.execute(text("drop index ux_probe_a"))
    conn.execute(
        text(
            "create unique index ux_probe_a on backups (checksum) where status = 'succeeded'"
        )
    )
    conn.commit()
    try:
        with_b = _partial_unique_predicates(conn)
        assert len(with_a) == len(with_b), "개수는 같아야 이 시험이 뜻을 갖는다"
        assert with_a != with_b, "WHERE 절이 달라졌는데 같은 것으로 읽었다"
    finally:
        conn.execute(text("drop index ux_probe_a"))
        conn.commit()


def test_the_policy_excluded_tables_all_exist_in_the_schema(conn):
    """제외 목록에 **오타가 있으면 `pg_dump` 가 조용히 무시한다.**

    `--exclude-table-data=오타` 는 아무것도 안 빼고 오류도 안 낸다. 그러면 매니페스트는
    「제외했습니다」라고 적는데 덤프에는 그 행이 그대로 들어 있다.
    """
    from app.backups.policy import excluded_tables

    tables = set(_table_names(conn))
    missing = [name for name in excluded_tables() if name not in tables]
    assert missing == [], f"제외 목록에 스키마에 없는 표가 있다: {missing}"
