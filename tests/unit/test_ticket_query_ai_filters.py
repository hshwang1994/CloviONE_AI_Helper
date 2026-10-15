"""티켓 목록 질의의 AI 도우미 전용 조건 (D-567).

AI 도우미의 티켓 도구는 화면에 없는 조건 넷을 쓴다: 본문까지 찾기(`body_search`), 바뀐 시각 · 끝난 시각의 범위, 「최근에 끝낸 순」.
이 조건들은 `TicketFilters` 의 칸이고 `build_filters` 가 질의에서 `getattr` 로 읽는다 — 화면 질의(`TicketListQuery`)에는 그 이름이
없으므로 화면 목록은 그대로다. 여기서 보는 것:

* 조건을 안 주면 조립된 SQL 이 예전과 같다(본문 · 시각 범위 절이 없다)
* 본문 찾기는 제목 · 티켓 이름 절과 **OR** 이다 — 범위 절은 따로 AND 로 걸린다
* 시각 범위는 반개구간이고 끝난 시각이 없는 티켓은 끝난 시각 조건에서 빠진다
* 실시간 폴백 경로(`TicketFilters.matches`)도 같은 뜻이다
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.dialects import postgresql

from app.tickets.query import SORT_KEYS, filter_clauses, sort_order
from app.tickets.repository import TicketDTO, TicketFilters, instant_of


def _sql(filters: TicketFilters) -> tuple[str, dict]:
    clauses = filter_clauses(filters)
    if not clauses:
        return "", {}
    compiled = and_(*clauses).compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


def test_without_the_new_conditions_the_sql_is_unchanged():
    sql, _ = _sql(TicketFilters(search="장비"))
    assert "body_markdown" not in sql and "updated_at" not in sql and "completed_at" not in sql
    assert _sql(TicketFilters()) == ("", {})


def test_body_search_is_an_or_with_title_and_key():
    sql, params = _sql(TicketFilters(search="교체 계획", body_search=True))
    assert "search_fold(tickets.body_markdown)" in sql
    assert sql.count(" OR ") >= 2, sql
    assert "%교체계획%" in params.values()
    # 검색어가 없으면 본문 찾기는 아무 조건도 아니다(빈 바늘은 전 행에 걸린다).
    assert "body_markdown" not in _sql(TicketFilters(search="  ", body_search=True))[0]


def test_time_ranges_are_half_open_on_the_stored_utc_axis():
    since = datetime(2026, 10, 8, 3, 0)
    sql, params = _sql(TicketFilters(updated_from=since, completed_from="2026-10-01", completed_to="2026-10-15"))
    assert "tickets.updated_at >= " in sql
    assert "tickets.completed_at >= " in sql and "tickets.completed_at < " in sql
    assert since in params.values()
    assert datetime(2026, 10, 1) in params.values() and datetime(2026, 10, 15) in params.values()
    assert instant_of("나쁜 값") is None and instant_of(None) is None and instant_of("") is None


def test_recently_completed_is_a_sort_key_with_nulls_last():
    assert "completed_at" in SORT_KEYS
    clause = sort_order("completed_at", descending=True)
    rendered = " ".join(str(c.compile(dialect=postgresql.dialect())) for c in clause)
    assert "tickets.completed_at DESC NULLS LAST" in rendered and "tickets.id DESC" in rendered


def test_the_live_fallback_path_reads_the_same_conditions():
    now = datetime(2026, 10, 15, 0, 0)
    done = TicketDTO(page_id="p1", title="장비 점검", body_markdown="교체 계획을 적습니다.", completed_at=now - timedelta(days=2))
    open_ = TicketDTO(page_id="p2", title="회의", body_markdown="교체 계획은 다음 주입니다.")
    by_body = TicketFilters(search="교체 계획", body_search=True)
    assert by_body.matches(done) and by_body.matches(open_)
    assert not TicketFilters(search="교체 계획").matches(done), "본문 찾기를 켜지 않았는데 본문이 걸렸다"
    recent = TicketFilters(completed_from=now - timedelta(days=7))
    assert recent.matches(done) and not recent.matches(open_)
    assert not TicketFilters(completed_from=now - timedelta(days=1)).matches(done)
