"""UA-08 (M4 trap, again): dev_monthly's default period/today used to be computed from
request.app.state.clock.now() directly (UTC). During KST month-boundary 00:00-09:00, the
UTC month is still last month, so the default period landed on the wrong month — and
`DevReport.jsx` computes its own default from the browser's local (KST) clock, so the
screen's default and the API's default default disagreed for those 9 hours every month.
Same shape as tests/regression/test_sprint_default_window_m4.py (UA-07).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.regression

# UTC 2026-07-31 18:00 == KST 2026-08-01 03:00. UTC still says July, KST already August.
JULY_UTC_AUGUST_KST = datetime(2026, 7, 31, 18, 0, 0)


@pytest.fixture()
def fake_clock():
    return FakeClock(JULY_UTC_AUGUST_KST)


def test_default_dev_monthly_period_uses_kst_month_not_utc_month(client, login_as):
    login_as("admin")
    body = client.get("/api/admin/reports/dev-monthly").json()
    assert body["period"] == "2026-08", (
        "UTC 월(7월)로 계산돼 지난달 리포트가 기본값이 됐다 — M4"
    )
