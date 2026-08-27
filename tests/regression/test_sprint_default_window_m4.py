"""UA-07 (M4 trap, again): the default "this week" window must be a **KST** calendar
week, not a UTC one.

`request.app.state.clock.now()` is UTC (invariant §9: UTC storage, Asia/Seoul only at
display/cron time). During KST Monday 00:00-09:00 the UTC date is still Sunday, so a
window computed from `now().date()` lands on *last* week. Same M4 shape as
`app/home/service.py::local_today` describes.

## 이 파일이 보는 문이 바뀌었다

예전에는 `GET /api/sprint/summary` 를 눌렀다. 지시 4 회차에서 그 API 를 걷었다 —
「그 주에 마감인 티켓 묶음」을 스프린트라고 부르던 자리이고, 이제 회차는 실체다
(`sprints` 표 · `app/work/meeting.py`).

**계산 자체는 그대로 살아 있다**(`local_today` → `default_sprint_window`) — 홈·비서·
주간 리포트가 부른다. 그래서 살아 있는 소비자 가운데 창을 응답에 그대로 실어 주는
`/api/projects/weekly-report` 로 옮긴다. 함수를 직접 부르는 유닛 시험으로 바꾸지 않는
이유는 이 결함이 **라우트가 시계를 어떻게 읽는가**에서 났기 때문이다 — 함수만 부르면
그 자리를 안 지난다.
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


def test_default_week_window_uses_kst_date_not_utc_date(client, login_as):
    login_as("user")
    body = client.get("/api/projects/weekly-report").json()
    assert body["window"]["start"] == "2026-08-03", (
        "UTC 날짜(일요일)로 계산돼 지난주(2026-07-27) 창이 잡혔다 — M4"
    )
    assert body["window"]["end_exclusive"] == "2026-08-10"
