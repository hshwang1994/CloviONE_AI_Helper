r"""날짜는 **모양이 아니라 실재**로 검증한다 (Z12).

정규식 `^\d{4}-\d{2}-\d{2}$` 만으로는 `2026-02-31` 이 통과한다. 그리고 `due_date` 는
문자열로 저장돼 **사전순으로 비교**되므로(`repository_notion`) 잘못된 값 하나가 모든 기간
필터와 공수 집계를 조용히 왜곡한다.

더 나쁜 것: 번다운이 `ValueError` 를 잡아 `[]` 를 돌려주는 바람에 **HTTP 200 에 합계는
채워지고 그래프만 빈** 화면이 나온다 — 숫자와 그래프가 서로 다른 말을 하는데 이유를 안 알려 준다.

참고: `est_wd`/`act_wd` 는 0~1000 으로 제대로 막혀 있었다 —
**숫자에는 물어본 질문을 날짜에는 안 물었다.**
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("bad", ["2026-02-31", "2026-13-01", "2026-00-10", "2025-02-29"])
def test_impossible_dates_are_refused(bad):
    from pydantic import ValidationError

    from app.tickets.schemas import TicketCreate

    with pytest.raises(ValidationError):
        TicketCreate(title="t", project_id="p1", due_date=bad)


@pytest.mark.parametrize("good", ["2026-02-28", "2024-02-29", "2026-12-31"])
def test_real_dates_still_pass(good):
    from app.tickets.schemas import TicketCreate

    assert TicketCreate(title="t", project_id="p1", due_date=good).due_date == good


def test_the_shape_check_still_runs_first():
    """모양이 틀린 것은 '없는 날짜' 가 아니라 '형식' 으로 말한다 — 고치는 방법이 다르다."""
    from pydantic import ValidationError

    from app.tickets.schemas import TicketCreate

    with pytest.raises(ValidationError) as e:
        TicketCreate(title="t", project_id="p1", due_date="2026/01/01")
    assert "형식" in str(e.value)
