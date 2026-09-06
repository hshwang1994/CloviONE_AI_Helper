"""개발자 월간 리포트의 `period` 는 **한 가지 모양으로** 거절한다 (app/reports/router.py).

## 무엇이 문제였나

같은 파라미터의 같은 오류(형식 위반)에 응답이 두 모양이었다. 일곱 자 이하면 핸들러 안에서
`200 {"ok": false, "error": …}` 이 나왔고, 여덟 자 이상이면 pydantic 의 길이 상한에 먼저
걸려 `422` 였다 — 경계가 뜻이 아니라 **글자 수**였다.

`ok: false` 는 「기능은 살아 있는데 답을 못 준다」(연동 미설정·조회 실패)를 위한 모양이다.
잘못 보낸 값은 그것과 다른 사건이고, 이 저장소의 다른 필터도 형식 위반에는 422 를 준다
(`app/audit/router.py::_parse_boundary`). 화면은 드롭다운만 주므로 사람이 이 경로를 밟지는
않지만, 이 API 를 부르는 스크립트는 오류 처리 분기를 두 벌 써야 했다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

BAD_PERIODS = ["2026-13", "abc", "", "2026-00", "2026-09-01", "20260901"]


@pytest.mark.parametrize("period", BAD_PERIODS)
def test_a_malformed_period_is_always_422(client, login_as, period):
    login_as("admin", email="devreport-period@goodmit.co.kr")

    response = client.get("/api/admin/reports/dev-monthly", params={"period": period})
    assert response.status_code == 422, (
        f"period={period!r} 이 다른 모양으로 거절됐다: {response.status_code} {response.text}"
    )
    assert response.json()["error"]["code"] == "validation_error"


def test_a_well_formed_period_still_answers(client, login_as):
    """반례 — 올바른 값은 그대로 200 이다. 위 시험이 「전부 422」로 통과하면 안 된다."""
    login_as("admin", email="devreport-period-ok@goodmit.co.kr")

    response = client.get("/api/admin/reports/dev-monthly", params={"period": "2026-09"})
    assert response.status_code == 200, response.text
    assert response.json()["period"] == "2026-09"
