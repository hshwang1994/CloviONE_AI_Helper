"""회차 열기가 동시에 와도 팀에 열린 회차는 하나이고, 5xx 는 없다 (P4 · B-1 · B-2).

활성 회차는 팀당 하나다 — 부분 유일 인덱스 `uq_sprints_active (org_id, coalesce(department_id, '')) WHERE state =
'active'` 가 막는다. `set_sprint_state` 는 다른 활성 회차가 없는지 읽고(`_ensure_no_other_active`) 나서 연다.

두 갈래를 본다.

  * **같은 회차를 N 번 연다**(더블클릭). 재실행 안전이다 — 모두 200 이고 열린 회차는 그 하나다. 행 잠금이 요청을
    한 줄로 세우고, 같은 행을 다시 여는 것은 인덱스를 어기지 않는다.
  * **같은 팀의 서로 다른 회차 N 개를 동시에 연다.** 하나만 열리고 나머지는 사전 검사와 **같은 문장**(이긴 회차의
    이름을 댄다)의 409 다. 예전에는 늦은 쪽이 인덱스에 부딪혀 요청 경계의 안전망(일반 문장의 409)까지 갔다.

이 파일은 전용 DB 가 필요하다(D-190).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import DUPLICATE_WRITE_MESSAGE
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.work import service as work_service
from app.work.models import SPRINT_ACTIVE, SPRINT_PLANNED, Sprint
from tests.fixtures.race import Window, fire, hold_after, messages, statuses

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

N = 8
START = date(2026, 10, 1)


@pytest.fixture()
def team_sprints(db):
    team = Department(name="열기경합팀", org_id=DEFAULT_ORG_ID)
    db.add(team)
    db.flush()
    rows = []
    for i in range(N):
        row = Sprint(
            name=f"10-{i + 1}", department_id=team.id, org_id=DEFAULT_ORG_ID,
            starts_on=START + timedelta(days=7 * i), ends_on=START + timedelta(days=7 * i + 6),
            state=SPRINT_PLANNED,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return team, rows


def _active(db, team_id: str) -> list[Sprint]:
    db.rollback()   # 다른 연결이 커밋한 것을 새 트랜잭션에서 본다
    return db.execute(
        select(Sprint).where(Sprint.department_id == team_id, Sprint.state == SPRINT_ACTIVE)
    ).scalars().all()


def test_opening_the_same_sprint_n_times_is_a_rerun(client, login_as, db, team_sprints, monkeypatch):
    team, rows = team_sprints
    target = rows[0]
    csrf = login_as("system_admin")
    window = Window(N)
    hold_after(monkeypatch, work_service, "_ensure_no_other_active", window)

    responses = fire(N, lambda _i: client.post(
        f"/api/work/sprints/{target.id}/state", json={"state": "active"}, headers={"X-CSRF-Token": csrf},
    ))

    assert window.opened, "요청들이 사전 검사 뒤에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert codes == [200] * N, [(c, getattr(r, "text", r)) for c, r in zip(codes, responses)]
    assert all(r.json()["state"] == SPRINT_ACTIVE for r in responses)
    assert [s.id for s in _active(db, team.id)] == [target.id]


def test_opening_different_sprints_of_one_team_at_once_leaves_one_open(
    client, login_as, db, team_sprints, monkeypatch,
):
    team, rows = team_sprints
    csrf = login_as("system_admin")
    window = Window(N)
    hold_after(monkeypatch, work_service, "_ensure_no_other_active", window)

    responses = fire(N, lambda i: client.post(
        f"/api/work/sprints/{rows[i].id}/state", json={"state": "active"}, headers={"X-CSRF-Token": csrf},
    ))

    assert window.opened, "요청들이 사전 검사 뒤에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert all(code in (200, 201, 409) for code in codes), codes
    assert codes.count(200) == 1, codes
    active = _active(db, team.id)
    assert len(active) == 1, [s.name for s in active]
    winner = active[0]
    assert responses[codes.index(200)].json()["id"] == winner.id
    conflicts = messages(responses, 409)
    assert conflicts == [f"이미 «{winner.name}» 회차가 열려 있습니다. 먼저 닫아 주세요."] * (N - 1), conflicts
    assert DUPLICATE_WRITE_MESSAGE not in conflicts, "경합이 요청 경계의 안전망까지 갔다"
