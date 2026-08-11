"""부서·직책·조직 목록이 행 개수에 비례해 질의를 늘리지 않는다 (UA-16).

## 왜 이 파일이 있는가

`GET /api/admin/departments`·`/job-titles`·`/organizations`는 관리 콘솔을 열 때마다
도는 목록이다. 그런데 응답을 만들 때 행마다 `usage_count()`(부서·직책, 질의 1개) 또는
조직이면 부서 수·인원 수를 각각(질의 2개) 따로 물었다 — 행이 늘면 질의도 그만큼 늘고,
SQLite는 writer가 하나라 사람이 늘수록 이 경로가 먼저 막힌다. 같은 파일의 `_org_names`·
`tree.py`는 이미 그룹 질의로 고쳐져 있던 것과 대조적이었다.

## 어떻게 판정하는가

행 개수를 바꿔 가며 실행한 SELECT 개수를 세고 그 차이를 본다 — 절대 개수를 못 박지
않는 이유는 `test_team_chat_rooms_query_count.py`와 같다(세션·감사 같은 곁가지 질의가
붙었다 떨어졌다 한다).
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

pytestmark = pytest.mark.regression


class QueryCounter:
    """엔진에 붙여 실행된 SELECT 문을 센다."""

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.statements.append(statement)

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)
        return False

    @property
    def count(self) -> int:
        return len(self.statements)


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def test_department_list_query_count_does_not_grow_with_rows(app, client, admin_csrf):
    for i in range(2):
        client.post(
            "/api/admin/departments", json={"name": f"부서{i}"},
            headers={"X-CSRF-Token": admin_csrf},
        )
    with QueryCounter(app.state.engine) as small:
        assert client.get("/api/admin/departments").status_code == 200
    small_count = small.count

    for i in range(2, 10):
        client.post(
            "/api/admin/departments", json={"name": f"부서{i}"},
            headers={"X-CSRF-Token": admin_csrf},
        )
    with QueryCounter(app.state.engine) as big:
        body = client.get("/api/admin/departments").json()
    big_count = big.count

    assert len(body["items"]) == 10, body["items"]
    grew = big_count - small_count
    assert grew <= 2, (
        f"부서 2개일 때 {small_count}질의, 10개일 때 {big_count}질의 — 8개가 늘 때 "
        f"{grew}질의가 늘었다. 행 하나당 질의가 붙는 구조다(UA-16)."
    )


def test_job_title_list_query_count_does_not_grow_with_rows(app, client, admin_csrf):
    for i in range(2):
        client.post(
            "/api/admin/job-titles", json={"name": f"직책{i}"},
            headers={"X-CSRF-Token": admin_csrf},
        )
    with QueryCounter(app.state.engine) as small:
        assert client.get("/api/admin/job-titles").status_code == 200
    small_count = small.count

    for i in range(2, 10):
        client.post(
            "/api/admin/job-titles", json={"name": f"직책{i}"},
            headers={"X-CSRF-Token": admin_csrf},
        )
    with QueryCounter(app.state.engine) as big:
        body = client.get("/api/admin/job-titles").json()
    big_count = big.count

    assert len(body["items"]) == 10, body["items"]
    grew = big_count - small_count
    assert grew <= 2, (
        f"직책 2개일 때 {small_count}질의, 10개일 때 {big_count}질의 — 8개가 늘 때 "
        f"{grew}질의가 늘었다. 행 하나당 질의가 붙는 구조다(UA-16)."
    )


def test_organization_list_query_count_does_not_grow_with_rows(app, client, login_as, db):
    from app.org.models import Organization

    csrf = login_as("system_admin")

    for i in range(2):
        db.add(Organization(slug=f"qc-small-{i}", name=f"작은조직{i}", status="active"))
    db.commit()
    with QueryCounter(app.state.engine) as small:
        assert client.get("/api/admin/organizations").status_code == 200
    small_count = small.count

    for i in range(8):
        db.add(Organization(slug=f"qc-big-{i}", name=f"큰조직{i}", status="active"))
    db.commit()
    with QueryCounter(app.state.engine) as big:
        body = client.get("/api/admin/organizations").json()
    big_count = big.count

    assert body["total"] >= 10, body
    grew = big_count - small_count
    assert grew <= 2, (
        f"조직 소수일 때 {small_count}질의, 다수일 때 {big_count}질의 — 8개가 늘 때 "
        f"{grew}질의가 늘었다. 조직 하나당 COUNT 2번이 붙는 구조다(UA-16)."
    )


def test_lists_still_report_correct_counts(app, client, admin_csrf, db):
    """질의를 줄이면서 값이 달라지지 않았는지 — 실제로 그 부서/직책을 쓰는 사용자 수가
    응답에 맞게 나오는지 본다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.users.models import User

    dept = client.post(
        "/api/admin/departments", json={"name": "인원확인팀"},
        headers={"X-CSRF-Token": admin_csrf},
    ).json()["department"]

    from app.users.service import create_user

    create_user(
        db, email="qc-member@goodmit.co.kr", display_name="구성원",
        password="Str0ng-Passw0rd!", settings=app.state.settings, actor_role="system_admin",
        department_id=dept["id"],
    )
    db.commit()

    body = client.get("/api/admin/departments").json()
    row = next(r for r in body["items"] if r["id"] == dept["id"])
    assert row["user_count"] == 1
