# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""티켓 목록의 날짜 조건이 틀리면 **422** 다 — 서버 오류(500)가 아니다.

🔴 이 파일이 생긴 이유(2026-09-21): `GET /api/tickets/team?created_from=2026-02-31` 가 500 `internal_error` 였다.
날짜 검사(`_ensure_real_date`)는 `ValueError` 를 던지는데, 그 검사를 부르는 자리가 Pydantic 검사기가 아니라 FastAPI
의존성(`TicketListQuery.__init__`)이라 검증 오류로 바뀌지 않고 그대로 새어 나갔다. 주소를 손으로 고친 사람 · 옛 즐겨찾기가
서버 오류 화면을 봤다. 작업 보드 API 회차가 탐침으로 찾았다.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def admin(db, make_user, settings):
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    return make_user("bad-date-admin@goodmit.co.kr", role="system_admin", display_name="관리자")


@pytest.mark.parametrize(
    "query,needle",
    [
        ("created_from=2026-02-31", "날짜가 달력에 없습니다"),
        ("created_to=2026-13-01", "날짜가 달력에 없습니다"),
        ("created_from=2026/02/01", "YYYY-MM-DD"),
    ],
)
def test_a_bad_date_condition_is_422_with_a_sentence_not_500(client, login_as, admin, query, needle):
    login_as("system_admin", email="bad-date-admin@goodmit.co.kr")
    res = client.get(f"/api/tickets/team?active=false&{query}")
    assert res.status_code == 422, (res.status_code, res.text)
    error = res.json()["error"]
    assert error["code"] != "internal_error", error
    assert needle in error["message"], error
