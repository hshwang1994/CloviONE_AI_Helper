"""UA-07 (M4 trap, again): sprint_summary's default window used to be computed from
request.app.state.clock.now().date() directly — that clock is UTC (invariant §9: UTC
storage, Asia/Seoul only at display/cron time). During KST Monday 00:00-09:00, the UTC
date is still Sunday, so the default window landed on *last* week instead of this one.
Same M4 shape as home/service.py's local_today() docstring describes; this endpoint just
hadn't been fixed yet. A real browser hitting GET /api/sprint/summary with no query
params during that 9-hour gap would see last week's sprint by default.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.regression

# UTC 2026-08-02 18:00 (Sunday) == KST 2026-08-03 03:00 (Monday). Squarely in the gap.
SUNDAY_UTC_MONDAY_KST = datetime(2026, 8, 2, 18, 0, 0)


@pytest.fixture()
def fake_clock():
    return FakeClock(SUNDAY_UTC_MONDAY_KST)


def test_default_sprint_window_uses_kst_date_not_utc_date(client, login_as):
    login_as("user")
    body = client.get("/api/sprint/summary").json()
    assert body["window"]["start"] == "2026-08-03", (
        "UTC 날짜(일요일)로 계산돼 지난주(2026-07-27) 창이 잡혔다 — M4"
    )
    assert body["window"]["end_exclusive"] == "2026-08-10"
