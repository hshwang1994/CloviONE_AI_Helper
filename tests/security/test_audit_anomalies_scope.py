"""이상 징후 화면도 감사 목록과 **같은 범위**를 지킨다 (§0-A 2순위).

`GET /api/admin/audit` 와 `GET /api/admin/audit/export.csv` 는 둘 다 행위자 기준으로
범위를 걸었는데 `GET /api/admin/audit/anomalies` 만 안 걸려 있었다. 핸들러에 `principal`
파라미터조차 없었고 `anomalies.detect` 는 창 안의 `audit_log` 전량을 행위자별로 묶었다.

**목록보다 이쪽이 더 나쁘다.** 소견 한 줄은 그 사람이 무엇을 몇 건 했는지의 요약이고,
근거(`evidence`)에 수행한 action 목록이 그대로 들어간다. 거기에 라우터가 표시 이름과
**이메일**까지 얹는다. 즉 목록에서 가려 둔 사람의 활동 요약과 연락처가 이 화면 하나로
통째로 샜다.

## 시스템 행위는 가리지 않는다

행위자가 없는 자동 처리(보존 정리, 동기화 실패)는 누구의 것도 아니다. 그것까지 없애면
부서 관리자가 자기 범위에서 일어난 자동 처리 실패를 못 본다 — 감사 목록이 이미 남기기로
정해 놨고(`app/audit/repository.py::scope_clause`), 이 화면도 같은 규칙이어야 한다.

## 이 테스트가 헛것이 되지 않게

"범위 밖 소견이 안 보인다" 는 **창을 잘못 잡아도, 임계값을 못 넘겨도, 응답이 500 이어도**
통과한다. 그래서 모든 부정 단언은 **같은 응답 안에서** 자기 범위 소견이 실제로 나오는 것을
함께 확인한다. 막을 수 있는 것이 범위 판정 하나뿐이 되게 만든다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.security

# fake_clock 은 2026-07-14 00:00 UTC 에서 시작하고 기본 창은 24시간이다.
# 이 시각은 창 안(since = 07-13 00:00)이면서 KST 로는 정오라 심야 규칙에 걸리지 않는다.
AT = datetime(2026, 7, 13, 3, 0, 0)

MATE_EMAIL = "anom-mate@goodmit.co.kr"
VICTIM_EMAIL = "anom-victim@goodmit.co.kr"
VICTIM_NAME = "남의팀사람"
BOSS_EMAIL = "anom-boss@goodmit.co.kr"

# FAILURE_BURST_THRESHOLD 는 5 다. 6건이면 확실히 넘는다.
BURST = 6


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리 팀만 관리하는 관리자 + 세 갈래의 실패 기록."""
    from app.audit.models import AuditLog
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user(MATE_EMAIL, role="user", display_name="우리팀사람")
    victim = make_user(VICTIM_EMAIL, role="user", display_name=VICTIM_NAME)
    boss = make_user(BOSS_EMAIL, role="admin", display_name="팀관리자")
    mate.department_id = mine.id
    victim.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    rows = []
    for actor_id, prefix in ((victim.id, "theirs"), (mate.id, "mine"), (None, "system")):
        for i in range(BURST):
            rows.append(
                AuditLog(
                    user_id=actor_id,
                    # 심야 규칙, 중대 동작 규칙에 걸리지 않는 평범한 동작이라
                    # 소견이 실패 폭주 하나로만 나온다.
                    action="auth.login",
                    object_type="session",
                    object_id=f"{prefix}-{i}",
                    result="failure",
                    created_at=AT,
                )
            )
    db.add_all(rows)
    db.commit()

    return {"mate_id": mate.id, "victim_id": victim.id, "boss_id": boss.id}


def _boss(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def _findings(client, headers):
    response = client.get("/api/admin/audit/anomalies", headers=headers)
    assert response.status_code == 200, f"이상 징후 화면이 안 열린다: {response.text}"
    return response, response.json()["findings"]


def test_a_scoped_admin_does_not_see_another_teams_finding(client, login_as, world):
    """범위 밖 행위자의 소견은 나오지 않는다.

    같은 응답에서 자기 팀 소견이 나오는지도 함께 본다 — 그게 없으면 창을 잘못 잡아
    아무 소견도 없는 응답을 놓고 "안전하다" 고 읽게 된다.
    """
    response, findings = _findings(client, _boss(login_as))
    actors = {f["actor_id"] for f in findings}

    assert world["mate_id"] in actors, (
        "자기 팀 소견조차 없다 — 이 응답으로는 아무것도 증명하지 못한다 "
        f"(scanned={response.json()['scanned']})"
    )
    assert world["victim_id"] not in actors, (
        f"남의 팀 행위자의 소견이 그대로 나온다: {findings}"
    )


def test_the_out_of_scope_actors_email_never_reaches_the_response(
    client, login_as, world
):
    """소견에는 이메일이 붙는다 — 가려야 할 사람의 연락처가 응답 본문에 남으면 안 된다."""
    response, _ = _findings(client, _boss(login_as))

    assert MATE_EMAIL in response.text, (
        "자기 팀 소견의 이메일조차 없다 — 필드가 통째로 사라진 것을 '가려졌다' 로 "
        "잘못 읽을 뻔했다"
    )
    assert VICTIM_EMAIL not in response.text, "남의 팀 행위자의 이메일이 응답에 있다"
    assert VICTIM_NAME not in response.text, "남의 팀 행위자의 표시 이름이 응답에 있다"


def test_my_own_scope_findings_still_appear(client, login_as, world):
    """오탐 방지 — 자기 범위 소견이 안 나오면 그건 화면이 고장 난 것이다."""
    _, findings = _findings(client, _boss(login_as))
    mine = [
        f for f in findings
        if f["actor_id"] == world["mate_id"] and f["kind"] == "failure_burst"
    ]
    assert mine, f"자기 팀의 실패 폭주 소견이 사라졌다: {findings}"
    assert mine[0]["count"] >= BURST
    assert mine[0]["evidence"], "근거 없이 경보만 내면 아무도 안 믿는다"
    assert mine[0]["actor_email"] == MATE_EMAIL, "자기 팀 행위자의 이메일이 안 붙었다"


def test_system_findings_stay_visible(client, login_as, world):
    """행위자 없는 자동 처리는 목록과 같은 규칙으로 남는다.

    여기서 가리면 부서 관리자가 자기 범위의 자동 처리 실패를 아예 못 본다.
    """
    _, findings = _findings(client, _boss(login_as))
    system = [f for f in findings if f["actor_id"] is None]
    assert system, (
        "소유자 없는 자동 처리의 소견까지 사라졌다 — 감사 목록은 남기기로 돼 있다"
    )
    assert system[0]["actor_email"] is None


def test_a_global_admin_still_sees_everyone(client, login_as, world):
    """전역 관리자까지 좁히면 이상 탐지 자체가 무의미해진다."""
    _, findings = _findings(client, {"X-CSRF-Token": login_as("system_admin")})
    actors = {f["actor_id"] for f in findings}
    assert world["victim_id"] in actors, "전역 관리자가 남의 팀 소견을 못 본다"
    assert world["mate_id"] in actors
