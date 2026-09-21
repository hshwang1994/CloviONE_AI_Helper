"""같은 회차 만들기가 동시에 N 번 와도 회차는 하나이고, 나머지는 사람의 문장이 든 409 다 (P4 · B-1).

`create_sprint` 는 이름이 팀 안에서 비었는지 읽고(`_ensure_name_free`) 나서 넣는다. 그 사이는 잠기지 않은 창이라
같은 요청 둘(「추가」 더블클릭 · 두 사람이 같은 이름을 동시에)이 둘 다 검사를 지나고, 늦은 삽입이 유일 인덱스
`uq_sprints_name (org_id, coalesce(department_id, ''), name)` 에 부딪힌다. 예전에는 그 위반이 요청 경계의 안전망
(`app/core/errors.py` — 「같은 항목이 이미 있어 저장하지 않았습니다」)까지 갔다. 지금은 삽입을 SAVEPOINT 로 감싸
사전 검사와 **같은 문장**으로 답한다 — 조금 늦게 온 요청과 동시에 온 요청이 같은 답을 받는다.

이 파일은 전용 DB 가 필요하다(D-190) — 요청마다 자기 연결로 진짜 커밋해야 경합이 일어난다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.errors import DUPLICATE_WRITE_MESSAGE
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.work import service as work_service
from app.work.models import Sprint
from tests.fixtures.race import Window, fire, hold_after, messages, statuses

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

N = 8


@pytest.fixture()
def team(db):
    row = Department(name="경합팀", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.commit()
    return row


def _count(db, team_id: str, name: str) -> int:
    db.rollback()   # 다른 연결이 커밋한 것을 새 트랜잭션에서 본다
    return db.execute(
        select(func.count()).select_from(Sprint).where(Sprint.department_id == team_id, Sprint.name == name)
    ).scalar_one()


def test_identical_creates_make_one_sprint_and_the_rest_hear_the_name_sentence(
    client, login_as, db, team, monkeypatch,
):
    csrf = login_as("system_admin")
    window = Window(N)
    hold_after(monkeypatch, work_service, "_ensure_name_free", window)
    body = {"name": "9-3", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": team.id}

    responses = fire(N, lambda _i: client.post(
        "/api/work/sprints", json=body, headers={"X-CSRF-Token": csrf},
    ))

    assert window.opened, "요청들이 사전 검사 뒤에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert all(code in (200, 201, 409) for code in codes), codes
    assert sum(code in (200, 201) for code in codes) == 1, codes
    conflicts = messages(responses, 409)
    assert conflicts == [work_service.SPRINT_NAME_TAKEN] * (N - 1), conflicts
    assert DUPLICATE_WRITE_MESSAGE not in conflicts, "경합이 요청 경계의 안전망까지 갔다"
    assert _count(db, team.id, "9-3") == 1


def test_a_create_that_arrives_after_the_winner_hears_the_same_sentence(client, login_as, team):
    """반례 — 경합이 아니라 순서대로 온 둘째 요청도 **같은 문장**의 409 다(사전 검사가 막는다)."""
    csrf = login_as("system_admin")
    body = {"name": "9-4", "starts_on": "2026-10-09", "ends_on": "2026-10-16", "department_id": team.id}
    first = client.post("/api/work/sprints", json=body, headers={"X-CSRF-Token": csrf})
    second = client.post("/api/work/sprints", json=body, headers={"X-CSRF-Token": csrf})
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["message"] == work_service.SPRINT_NAME_TAKEN
