"""일정 생성이 **같은 이름으로 겹쳐도** 500 이 아니라 409 로 끝난다.

직렬 경로는 이미 정확한 답을 갖고 있었다 — 이름이 있으면 409 다. 그런데 그 판정이
「확인한 뒤 넣는다」 모양이라 확인과 INSERT 사이가 요청 하나만큼 넓었고(커밋은 요청 끝에
한 번뿐이다), 두 운영자가 같은 이름('야간 백업')으로 동시에 저장하면 뒤진 쪽의 flush 가
`schedules.name` 유니크를 때려 처리되지 않은 `IntegrityError` 가 그대로 500 이 됐다.
그 화면에는 'Internal server error' 만 뜨고 감사 로그에는 `schedule.create` 가 없어,
운영자는 일정이 만들어졌는지 목록을 뒤져야 했다.

같은 모양을 이 저장소는 prompts·policies·org 에서 이미 결함으로 규정하고 고쳤다
(`tests/integration/test_prompt_create_new_version_race.py`). 이 시험은 그 파일과 같은
방법을 쓴다 — 순수 타이밍 경주는 로그인 자체의 경합 때문에 스레드가 흩어져 위양성으로
초록불이 되기 쉬우므로, 「이름 존재 확인」 SELECT 두 개를 배리어에 세워 **둘 다 '없음'을
본 다음에야** 동시에 INSERT 로 넘어가게 강제한다.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from tests.conftest import DEFAULT_TEST_PASSWORD

# 스레드가 각자 세션을 열어야 하므로 **전용 DB** 가 필요하다(D-190).
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

ADMIN_EMAIL = "system-admin@goodmit.co.kr"
RACE_NAME = "race-create-schedule"


def _payload(name=RACE_NAME):
    return {
        "name": name,
        "schedule_type": "cron",
        "cron_expression": "0 3 * * *",
        "timezone": "Asia/Seoul",
        "target_type": "system",
        "target_ref": "noop",
    }


def _login(c):
    r = c.post("/login", json={"email": ADMIN_EMAIL, "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def test_concurrent_create_same_name_never_500s(app, login_as):
    login_as("system_admin")  # 관리자 계정을 미리 만든다 — 로그인 경합은 시험 대상이 아니다.
    engine = app.state.engine
    barrier = threading.Barrier(2)
    hits = 0
    hits_lock = threading.Lock()

    def _pause_before_insert_races(conn, cursor, statement, parameters, context, executemany):
        nonlocal hits
        if "FROM schedules" not in statement or RACE_NAME not in str(parameters):
            return
        with hits_lock:
            hits += 1
            should_wait = hits <= 2
        if should_wait:
            barrier.wait(timeout=5)

    def attempt(_i: int) -> int:
        with TestClient(app, raise_server_exceptions=False) as c:
            token = _login(c)
            return c.post(
                "/api/admin/schedules",
                json=_payload(),
                headers={"X-CSRF-Token": token},
            ).status_code

    event.listen(engine, "before_cursor_execute", _pause_before_insert_races)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(attempt, range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", _pause_before_insert_races)

    assert codes.count(201) == 1, f"정확히 하나만 성공해야 한다: {codes}"
    assert all(c in (201, 409) for c in codes), f"500이 섞였다(처리 안 된 경합): {codes}"


def test_serial_duplicate_name_still_answers_409(app, login_as):
    """반례 — 경합이 아닌 평범한 중복은 예전 그대로 409 다(사전 검사가 먼저 잡는다)."""
    login_as("system_admin")
    with TestClient(app, raise_server_exceptions=False) as c:
        token = _login(c)
        first = c.post(
            "/api/admin/schedules",
            json=_payload("serial-duplicate-schedule"),
            headers={"X-CSRF-Token": token},
        )
        assert first.status_code == 201, first.text
        second = c.post(
            "/api/admin/schedules",
            json=_payload("serial-duplicate-schedule"),
            headers={"X-CSRF-Token": token},
        )
        assert second.status_code == 409, second.text
