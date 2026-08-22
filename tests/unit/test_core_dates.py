"""날짜 경계 — 바깥 문자열과 안쪽 `date`/`datetime` 사이 (S7 · P-14a).

## 여기서 확인하는 것 셋

1. **달력일에는 시간대를 적용하지 않는다.** 적용하면 자정 근처의 날짜가 하루 밀리고,
   그 하루가 「이번 주 마감」에서 통째로 빠진다.
2. **타임스탬프에는 적용한다.** 오프셋이 붙은 값을 그대로 저장하면 KST 오전 9시 이전의
   일이 UTC 로는 어제가 된다 — 주간 다이제스트가 실제로 그 상태였다(M4).
3. **못 읽는 값에 예외를 던지지 않는다.** 이 함수를 부르는 자리 대부분이 동기화 루프
   안이고, 거기서 예외가 나면 값 하나 때문에 미러 한 회차가 통째로 멈춘다.

양방향으로 본다 — 「거절한다」만 확인하면 전부 `None` 을 내는 구현도 통과하고,
그 구현에서는 어떤 날짜도 저장되지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.dates import iso_date, iso_dt, parse_date, parse_dt

pytestmark = pytest.mark.unit


# ── 달력일 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value,expected", [
    ("2026-08-22", date(2026, 8, 22)),
    ("  2026-08-22  ", date(2026, 8, 22)),
    # 소스(Notion)의 date 속성은 시각을 포함할 수 있다. 앞 10자가 달력일이다.
    ("2026-08-22T10:00:00.000Z", date(2026, 8, 22)),
    (date(2026, 8, 22), date(2026, 8, 22)),
    (datetime(2026, 8, 22, 23, 30), date(2026, 8, 22)),
])
def test_parse_date_reads_what_the_sources_actually_send(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("value", [
    None, "", "   ", "TBD", "2026-02-31", "2026-13-01", "언젠가", 0, False, True,
])
def test_parse_date_returns_none_instead_of_raising(value):
    """예외를 던지면 값 하나 때문에 동기화 한 회차가 통째로 멈춘다."""
    assert parse_date(value) is None


def test_a_calendar_day_never_shifts_with_a_timezone():
    """달력일은 시각이 아니다. 옮기면 자정 근처가 하루 밀린다.

    KST 로 8월 23일 오전 0시는 UTC 로 8월 22일 15시다. 그런데 소스가 'YYYY-MM-DD' 로
    준 값에 그 변환을 적용하면 「23일 마감」이 22일이 된다 — 그리고 그 하루가
    「이번 주 마감」 목록에서 빠진다.
    """
    assert parse_date("2026-08-23T00:00:00+09:00") == date(2026, 8, 23)
    assert parse_date("2026-08-23T00:00:00.000Z") == date(2026, 8, 23)


# ── 타임스탬프 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value,expected", [
    ("2026-08-22T10:00:00.000Z", datetime(2026, 8, 22, 10, 0)),
    ("2026-08-22T10:00:00Z", datetime(2026, 8, 22, 10, 0)),
    # 오프셋이 붙으면 UTC 로 옮기고 tzinfo 를 뗀다(저장 규약: naive UTC).
    ("2026-08-22T10:00:00+09:00", datetime(2026, 8, 22, 1, 0)),
    ("2026-08-22T10:00:00", datetime(2026, 8, 22, 10, 0)),
    # 소스가 date 속성을 timestamp 자리에 넣는 일이 있다.
    ("2026-08-22", datetime(2026, 8, 22, 0, 0)),
])
def test_parse_dt_normalises_to_naive_utc(value, expected):
    parsed = parse_dt(value)
    assert parsed == expected
    assert parsed.tzinfo is None, "저장 규약은 naive UTC 다 (app/core/db.py)"


@pytest.mark.parametrize("value", [None, "", "nope", "2026-13-01T00:00:00Z"])
def test_parse_dt_returns_none_instead_of_raising(value):
    assert parse_dt(value) is None


def test_an_offset_actually_moves_the_clock():
    """반대편 — 위 표가 「전부 그대로 둔다」로 통과하면 M4 가 되살아난다."""
    assert parse_dt("2026-08-03T06:00:00+09:00") == datetime(2026, 8, 2, 21, 0)


# ── 되돌리기 ─────────────────────────────────────────────────────────────────


def test_iso_helpers_round_trip():
    assert iso_date(date(2026, 8, 22)) == "2026-08-22"
    assert iso_date("2026-08-22T10:00:00Z") == "2026-08-22"
    assert iso_date(None) is None
    assert iso_dt(datetime(2026, 8, 22, 10, 0)) == "2026-08-22T10:00:00"
    assert iso_dt(None) is None


def test_iso_date_keeps_lexicographic_order_equal_to_date_order():
    """옛 문자열 규약이 기대던 성질이다. 화면과 정렬 키가 아직 이 위에 서 있다."""
    days = [date(2026, 1, 5), date(2026, 1, 20), date(2026, 2, 1), date(2026, 12, 31)]
    assert [iso_date(d) for d in sorted(days)] == sorted(iso_date(d) for d in days)
