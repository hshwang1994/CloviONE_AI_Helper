"""관리 화면의 사람 자리가 UUID 가 아니라 **이름**을 받는다 (E-4 UUID 노출).

## 무엇이 틀렸었나

관리자 상세 패널이 사람 자리를 전부 UUID 로 채우고 있었다. "이 스케줄은 누구 것인가",
"이 백업은 누가 돌렸나" 를 알려면 운영자가 `9f2c…-…` 를 복사해 사용자 화면에서 검색해야
했다. 화면만 고칠 수는 없었다 — **응답에 이름 자체가 없었기 때문이다.**

## 이 검사가 지키는 것

1. 목록 응답이 표시 이름과 이메일을 함께 준다(화면이 그릴 것이 실제로 존재한다).
2. **id 도 그대로 남는다.** 이름은 더하는 것이지 감추는 것이 아니다 — 동명이인이면 id 가
   유일한 구분자이고, 감사 로그 필터에 붙여 넣는 값도 id 다.
3. 사람이 아닌 실행(예약 백업)은 이름이 없다는 사실이 그대로 드러난다 — 없는 것을 있는
   척 지어내지 않는다.
4. 목록이 **한 번의 질의로** 이름을 모은다(행마다 조회하면 이 화면이 N+1 이 된다).
"""

import pytest

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("system_admin")


# S11 이후 스케줄 대상은 `system` 하나다(D-267).
@pytest.fixture()
def workflow_id():
    return "noop"


def test_schedule_list_names_its_owner(client, admin_csrf, workflow_id):
    created = client.post(
        "/api/admin/schedules",
        json={
            "name": "매시 보고서",
            "schedule_type": "cron",
            "cron_expression": "0 * * * *",
            "timezone": "UTC",
            "target_type": "system",
            "target_ref": workflow_id,
            "payload_template": {},
        },
        headers=_headers(admin_csrf),
    )
    assert created.status_code == 201, created.text

    rows = client.get("/api/admin/schedules").json()["items"]
    row = next(r for r in rows if r["name"] == "매시 보고서")

    assert row["owner_name"], "소유자 이름이 없다 — 화면은 UUID 를 그릴 수밖에 없다"
    assert row["owner_email"] == "system-admin@goodmit.co.kr"
    # 이름을 더하는 것이지 id 를 감추는 것이 아니다.
    assert row["owner_user_id"], "id 가 사라졌다 — 감사 로그 대조와 동명이인 구분이 막힌다"
    assert row["owner_name"] != row["owner_user_id"]


def test_backup_list_names_who_ran_it(client, admin_csrf):
    created = client.post("/api/admin/backups", headers=_headers(admin_csrf))
    assert created.status_code == 201, created.text

    rows = client.get("/api/admin/backups").json()["items"]
    assert rows, "백업 행이 없다 — 이 검사가 아무것도 보지 않는다"
    row = rows[0]
    assert row["created_by_name"], "실행자 이름이 없다 — 화면은 UUID 를 그릴 수밖에 없다"
    assert row["created_by_email"] == "system-admin@goodmit.co.kr"
    assert row["created_by"], "id 가 사라졌다"


def test_scheduled_backup_has_no_person_and_says_so():
    """예약(자동) 백업은 실행한 사람이 없다. 그 사실이 그대로 나와야 한다 — 없는 사람을
    지어내면 감사 기록이 거짓이 된다(불변 6)."""
    from datetime import datetime

    from app.backups.service import backup_view

    class _Auto:
        id = "b-auto"
        backup_type = "sqlite"
        path = "/tmp/auto.sqlite3"
        status = "succeeded"
        size_bytes = 10
        checksum = "abc"
        created_by = None
        created_at = datetime(2026, 8, 7, 3, 0, 0)
        verified_at = None
        error_message = None

    view = backup_view(_Auto(), {})
    assert view["created_by"] is None
    assert view["created_by_name"] is None, "실행자가 없는데 이름을 지어냈다"


def test_owner_names_are_resolved_in_one_query(client, admin_csrf, workflow_id):
    """행마다 조회하면 목록 화면이 그대로 N+1 이 된다 — 여러 행이 있어도 질의는 한 번이다."""
    from sqlalchemy import event

    for i in range(3):
        r = client.post(
            "/api/admin/schedules",
            json={
                "name": f"스케줄 {i}",
                "schedule_type": "cron",
                "cron_expression": "0 * * * *",
                "timezone": "UTC",
                "target_type": "system",
                "target_ref": workflow_id,
                "payload_template": {},
            },
            headers=_headers(admin_csrf),
        )
        assert r.status_code == 201, r.text

    engine = client.app.state.engine
    user_selects = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        if "FROM users" in statement:
            user_selects.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        rows = client.get("/api/admin/schedules").json()["items"]
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert len(rows) >= 3
    # 이 요청에서 users 를 읽는 곳은 둘뿐이다: 세션 인증(요청당 1회) + 이름 배치 1회.
    # 행마다 조회하는 구현이면 3행에 대해 1 + 3 = 4회가 된다 — 값이 실제로 갈린다.
    assert len(user_selects) <= 2, (
        f"소유자 이름을 행마다 조회하고 있다(users 조회 {len(user_selects)}회) — 목록이 N+1 이다\n"
        + "\n".join(user_selects)
    )
