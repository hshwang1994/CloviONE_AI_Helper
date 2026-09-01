"""「기한 넘김」을 읽는 자리가 다섯인데 **규칙은 하나여야 한다**.

## 무엇이 문제였나

상태 축이 두 갈래였다. Health 규칙만 「완료가 아니면」으로 셌고, 나머지 넷 — 홈의 지연
목록, 프로젝트 목록의 `overdue_milestones` 필터, 대시보드 요약, 주간 리포트 — 은 「아직
예정이면」으로 셌다. `missed`(놓침)가 정확히 그 틈에 떨어진다.

그래서 마일스톤을 놓쳤다고 표시하는 순간 같은 화면이 서로 반대되는 말을 했다: 요약 칸은
「지연 마일스톤 0건」인데 바로 옆 Health 는 그 건으로 12점을 깎고 있었다. 게다가 그 상태로
빠져나갈 길이 없었다 — 놓쳤다고 인정하면 목록에서는 사라지는데 점수는 계속 깎였고,
점수를 되돌릴 방법은 없는 일을 「완료」로 거짓 표시하는 것뿐이었다.

**놓침도 기한 넘김이다.** 늦었다고 적는 것이 늦지 않은 것으로 만들어 주지 않는다.
판정의 정본은 `app/projects/models.py::milestone_unmet` 하나이고 다섯 자리가 그것을 본다.

## 왜 다섯을 한 파일에서 보는가

깨진 것은 어느 한 자리가 아니라 **자리들 사이**다. 파일을 나눠 각자 시험하면 다음에 또
한 곳만 고쳐도 전부 초록이 된다. 같은 표본 하나를 다섯 창구에 넣고 다섯이 같은 답을
내는지 본다 — 그것이 이 파일이 지키는 성질이다.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project, ProjectMilestone

pytestmark = pytest.mark.integration

BOSS_EMAIL = "ms-rule@goodmit.co.kr"
NOW = datetime(2026, 7, 14, 0, 0, 0)
# 기준일. 아래 기한 셋을 이 날짜로 가른다.
TODAY = "2026-07-14"
# 기준일의 정본은 conftest 의 `fake_clock`(2026-07-14 UTC)이다. KST 로 옮겨도
# 같은 날이라 아래 상수와 맞는다 — 여기서 시계를 새로 만들면 그 fixture 를 가린다.
PAST = "2026-07-01"      # 지났다
FUTURE = "2026-08-01"    # 아직 안 지났다


@pytest.fixture()
def world(db, make_user, fake_clock):
    """프로젝트 하나에 마일스톤 넷. **놓침 하나가 이 시험의 표본이다.**

    기한이 지난 것 셋(예정·놓침·완료)과 아직 안 지난 놓침 하나를 둔다. 마지막 하나가
    오탐 방지다 — 「놓침이면 무조건 지연」으로 고치면 그것도 함께 걸린다.
    """
    boss = make_user(BOSS_EMAIL, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    project = Project(
        name="놓침이 있는 프로젝트", org_id=DEFAULT_ORG_ID, status="active",
        created_at=NOW, updated_at=NOW,
    )
    db.add(project)
    db.commit()

    def milestone(name, due_on, status):
        row = ProjectMilestone(
            project_id=project.id, name=name, due_on=due_on, status=status,
            sort_order=0, created_at=NOW, updated_at=NOW,
        )
        db.add(row)
        return row

    milestone("지났고 예정", PAST, "planned")
    milestone("지났고 놓침", PAST, "missed")
    milestone("지났고 완료", PAST, "done")
    milestone("아직이고 놓침", FUTURE, "missed")
    db.commit()
    return {"project_id": project.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


# ── ① 공용 규칙 자체 ──────────────────────────────────────────────────────────

def test_the_rule_itself_counts_missed_as_unmet():
    from app.projects.models import (
        MILESTONE_DONE, MILESTONE_MISSED, MILESTONE_PLANNED, milestone_unmet,
    )

    assert milestone_unmet(MILESTONE_MISSED) is True, "놓침은 끝난 것이 아니다"
    assert milestone_unmet(MILESTONE_PLANNED) is True
    assert milestone_unmet(MILESTONE_DONE) is False, "완료만 지켜진 것이다"


# ── ② Health 규칙 ────────────────────────────────────────────────────────────

def test_health_counts_missed_as_overdue():
    """Health 는 **처음부터** 놓침을 셌다 — 이 시험은 고침 전에도 초록이다.

    회귀 시험이 아니라 **기준을 못 박는** 시험이다. 나머지 넷을 여기에 맞추기로 했으므로,
    이 자리가 나중에 「예정만」으로 좁아지면 다섯이 다시 갈린다.
    """
    from app.projects.health import RULE_MILESTONE_OVERDUE, HealthInput, MilestoneFact, compute_health

    result = compute_health(HealthInput(
        today=TODAY,
        milestones=(
            MilestoneFact(due_on=PAST, status="planned"),
            MilestoneFact(due_on=PAST, status="missed"),
            MilestoneFact(due_on=PAST, status="done"),
            MilestoneFact(due_on=FUTURE, status="missed"),
        ),
    ))
    reason = next(r for r in result.reasons if r.rule == RULE_MILESTONE_OVERDUE)
    # 기한이 지난 예정 1 + 놓침 1 = 2건. 완료와 아직 안 지난 놓침은 안 센다.
    assert "4건 중 2건" in reason.detail, reason.detail


# ── ③ 프로젝트 목록의 `overdue_milestones` 필터 ───────────────────────────────

def test_project_list_filter_keeps_a_project_whose_only_overdue_is_missed(
    client, login_as, db, make_user, fake_clock
):
    """놓침 **하나뿐인** 프로젝트가 필터에 걸려야 한다.

    표본을 따로 만든다 — 위 `world` 는 예정 지연도 함께 있어서, 놓침을 안 세는 구현도
    그 프로젝트를 걸러 내며 통과한다(가짜 초록).
    """
    boss = make_user(BOSS_EMAIL, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    project = Project(
        name="놓침만 있는 프로젝트", org_id=DEFAULT_ORG_ID, status="active",
        created_at=NOW, updated_at=NOW,
    )
    db.add(project)
    db.commit()
    db.add(ProjectMilestone(
        project_id=project.id, name="지났고 놓침", due_on=PAST, status="missed",
        sort_order=0, created_at=NOW, updated_at=NOW,
    ))
    db.commit()

    r = client.get("/api/projects?overdue_milestones=true", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json()["items"]]
    assert "놓침만 있는 프로젝트" in names, f"놓침을 지연으로 안 센다: {names}"


# ── ④ 대시보드 요약 ──────────────────────────────────────────────────────────

def test_dashboard_summary_counts_missed_as_overdue(client, login_as, world, fake_clock):
    r = client.get("/api/projects/dashboard", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    overdue = r.json()["milestones"]["overdue"]
    assert overdue["count"] == 2, f"요약이 놓침을 빼고 세고 있다: {overdue}"
    names = {m["name"] for m in overdue["items"]}
    assert names == {"지났고 예정", "지났고 놓침"}, names


# ── ⑤ 주간 리포트 ────────────────────────────────────────────────────────────

def test_weekly_report_counts_missed_as_overdue(client, login_as, world, fake_clock):
    r = client.get(
        f"/api/projects/{world['project_id']}/weekly-report", headers=_hdr(login_as)
    )
    assert r.status_code == 200, r.text
    overdue = r.json()["milestones"]["overdue"]
    assert overdue["count"] == 2, f"주간 리포트가 놓침을 빼고 세고 있다: {overdue}"
    assert {m["name"] for m in overdue["items"]} == {"지났고 예정", "지났고 놓침"}


# ── ⑥ 홈의 지연 마일스톤 ─────────────────────────────────────────────────────

def test_home_dashboard_counts_missed_as_overdue(client, login_as, world, fake_clock):
    r = client.get("/api/home/work-dashboard", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    overdue = r.json()["milestones"]["overdue"]
    assert overdue["count"] == 2, f"홈이 놓침을 빼고 세고 있다: {overdue}"
    assert {m["name"] for m in overdue["items"]} == {"지났고 예정", "지났고 놓침"}


# ── ⑦ 다섯이 같은 답을 낸다 ──────────────────────────────────────────────────

def test_all_five_readers_agree(client, login_as, world, fake_clock):
    """숫자 하나가 아니라 **일치**를 지킨다 — 다음에 또 한 곳만 고치면 여기가 빨개진다.

    🔴 **Health 를 반드시 이 비교에 넣는다.** 깨졌던 축이 정확히 「Health 대 나머지 넷」
    이었으므로, 넷끼리만 견주면 넷이 함께 틀린 옛 상태에서도 초록이 된다(실제로 이 시험의
    첫 판이 그랬다 — 고침을 되돌려도 통과했다). Health 의 수는 그 규칙이 화면에 내는 문장
    에서 읽는다: 「… N건이 기한을 넘겼습니다」.
    """
    hdr = _hdr(login_as)
    pid = world["project_id"]

    dashboard = client.get("/api/projects/dashboard", headers=hdr).json()
    weekly = client.get(f"/api/projects/{pid}/weekly-report", headers=hdr).json()
    home = client.get("/api/home/work-dashboard", headers=hdr).json()
    listed = client.get("/api/projects?overdue_milestones=true", headers=hdr).json()
    health = client.get(f"/api/projects/{pid}/health", headers=hdr).json()

    reason = next(
        r for r in health["reasons"] if r["rule"] == "milestone_overdue"
    )
    found = re.search(r"(\d+)건이 기한을 넘겼습니다", reason["detail"])
    assert found, f"Health 문장 모양이 바뀌었다: {reason['detail']}"

    counts = {
        "health": int(found.group(1)),
        "dashboard": dashboard["milestones"]["overdue"]["count"],
        "weekly": weekly["milestones"]["overdue"]["count"],
        "home": home["milestones"]["overdue"]["count"],
    }
    assert len(set(counts.values())) == 1, f"네 자리가 서로 다른 수를 말한다: {counts}"
    # 목록 필터는 마일스톤이 아니라 프로젝트를 센다 — 그 프로젝트가 걸려 있으면 같은 판정이다.
    assert pid in [p["id"] for p in listed["items"]], "목록만 그 프로젝트를 안 건진다"
