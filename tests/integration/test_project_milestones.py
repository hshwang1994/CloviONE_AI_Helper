"""마일스톤 CRUD 와 헬스 스냅샷이 **프로젝트와 같은 범위 게이트**를 지나는지.

가장 중요한 단정은 하나다: **마일스톤 id 로는 남의 팀 것을 못 만진다.** 이 저장소는 목록에만
범위를 걸고 단건, 쓰기에는 안 거는 실수를 네 번 했고(`scripts/check_scope_gates.py`), 하위
자원은 그 실수가 가장 나기 쉬운 자리다 - 부모의 게이트를 지났다는 이유로 자식 조회를
`db.get(Milestone, id)` 로 해 버리면 프로젝트 id 는 아무 검사도 하지 않는 장식이 된다.

그래서 여기서는 **자기 프로젝트 경로에 남의 마일스톤 id 를 끼워 넣는다.** 그러면 프로젝트
게이트는 통과하므로, 막는 것은 오직 "그 프로젝트 안에서 찾는다" 뿐이다.

헬스 쪽에서는 두 가지를 본다: 점수가 실제로 마일스톤을 보고 있는지(배선이 끊겨 있으면
순수 함수가 아무리 맞아도 화면 숫자는 안 움직인다), 그리고 잴 것이 없을 때 이력에 거짓
점수를 적지 않는지.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import ProjectMilestone

pytestmark = pytest.mark.integration

BOSS_EMAIL = "ms-boss@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 우리 팀만 관리하는 관리자 + 각 팀의 프로젝트와 마일스톤."""
    from app.org.models import Department
    from app.projects.models import Project

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    boss = make_user(BOSS_EMAIL, role="admin", display_name="팀관리자")
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    ours = Project(name="우리 프로젝트", dept_id=mine.id, org_id=DEFAULT_ORG_ID)
    theirs_project = Project(name="남의 프로젝트", dept_id=theirs.id, org_id=DEFAULT_ORG_ID)
    db.add_all([ours, theirs_project])
    db.commit()

    their_milestone = ProjectMilestone(
        project_id=theirs_project.id, name="남의 팀 1차 릴리스", due_on="2026-09-01",
    )
    db.add(their_milestone)
    db.commit()
    return {
        "mine": ours.id,
        "theirs": theirs_project.id,
        "their_milestone": their_milestone.id,
    }


def _hdr(login_as):
    """로그인은 **테스트당 한 번**만 한다.

    다시 로그인하면 세션과 함께 CSRF 토큰이 갈리므로, 먼저 받아 둔 헤더가 그 순간부터
    403 이 된다 - 증상이 권한 오류라 원인을 엉뚱한 데서 찾게 된다.
    """
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def _create(client, hdr, project_id, **over):
    body = {"name": "1차 릴리스", "due_on": "2026-09-30", **over}
    return client.post(
        f"/api/projects/{project_id}/milestones", json=body, headers=hdr
    )


def test_a_milestone_round_trips_through_the_project_path(client, login_as, world):
    """만들고, 목록에 나오고, 고치고, 지운다."""
    hdr = _hdr(login_as)
    created = _create(client, hdr, world["mine"])
    assert created.status_code == 200, created.text
    milestone_id = created.json()["milestone"]["id"]
    assert created.json()["milestone"]["status"] == "planned", "기본 상태가 안 붙었다"

    listed = client.get(f"/api/projects/{world['mine']}/milestones", headers=hdr).json()
    assert [m["id"] for m in listed["items"]] == [milestone_id]

    patched = client.patch(
        f"/api/projects/{world['mine']}/milestones/{milestone_id}",
        json={"status": "done"}, headers=hdr,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["milestone"]["status"] == "done"
    assert patched.json()["milestone"]["due_on"] == "2026-09-30", (
        "안 건드린 기한이 조용히 지워졌다 - 준 필드만 바꿔야 한다"
    )

    gone = client.delete(
        f"/api/projects/{world['mine']}/milestones/{milestone_id}", headers=hdr
    )
    assert gone.status_code == 200, gone.text
    after = client.get(f"/api/projects/{world['mine']}/milestones", headers=hdr).json()
    assert after["items"] == []


def test_another_teams_milestone_id_does_not_work_in_my_own_project_path(
    client, login_as, db, world
):
    """**이 파일의 핵심.** 프로젝트 게이트는 통과시키고 마일스톤 id 만 남의 것으로 바꾼다.

    `db.get(Milestone, id)` 로 꺼내는 구현이면 여기서 남의 팀 일정이 바뀐다. 경로의
    프로젝트 id 는 검사에 아무 영향도 주지 않는 장식이 되기 때문이다.
    """
    hdr = _hdr(login_as)
    target = f"/api/projects/{world['mine']}/milestones/{world['their_milestone']}"

    patched = client.patch(target, json={"name": "탈취됨"}, headers=hdr)
    assert patched.status_code == 404, (
        f"남의 팀 마일스톤을 내 프로젝트 경로로 고칠 수 있다: {patched.status_code} {patched.text}"
    )

    removed = client.delete(target, headers=hdr)
    assert removed.status_code == 404, (
        f"남의 팀 마일스톤을 지울 수 있다: {removed.status_code} {removed.text}"
    )

    db.expire_all()
    survivor = db.get(ProjectMilestone, world["their_milestone"])
    assert survivor is not None, "404 를 돌려주고도 남의 팀 마일스톤이 실제로 지워졌다"
    assert survivor.name == "남의 팀 1차 릴리스", (
        "404 를 돌려주고도 남의 팀 마일스톤이 실제로 바뀌었다"
    )


def test_another_teams_project_path_is_404_for_every_milestone_verb(
    client, login_as, db, world
):
    """목록에서 가린 것이 하위 경로로 새면 가린 의미가 없다."""
    hdr = _hdr(login_as)
    base = f"/api/projects/{world['theirs']}/milestones"

    assert client.get(base, headers=hdr).status_code == 404, "남의 팀 마일스톤 목록이 열린다"
    assert client.post(base, json={"name": "심기"}, headers=hdr).status_code == 404
    assert client.get(
        f"/api/projects/{world['theirs']}/health", headers=hdr
    ).status_code == 404, "남의 팀 헬스 점수와 이유가 열린다"
    assert client.get(
        f"/api/projects/{world['theirs']}/wbs", headers=hdr
    ).status_code == 404, "남의 팀 작업 계층이 열린다"

    db.expire_all()
    planted = db.query(ProjectMilestone).filter(
        ProjectMilestone.name == "심기"
    ).all()
    assert planted == [], "404 를 돌려주고도 남의 팀에 마일스톤이 만들어졌다"


def test_a_bad_milestone_payload_is_422_not_500(client, login_as, world):
    """경계에서 안 막으면 NOT NULL 과 형식 오류가 500 으로 나간다."""
    hdr = _hdr(login_as)
    assert _create(client, hdr, world["mine"], name=" ").status_code == 422
    assert _create(
        client, hdr, world["mine"], due_on="2026/09/30"
    ).status_code == 422, "날짜 형식이 섞이면 비교가 조용히 어긋난다"
    assert _create(
        client, hdr, world["mine"], status="언젠가"
    ).status_code == 422, "모르는 상태가 그대로 저장된다"


def test_the_health_score_actually_reads_the_milestones(client, login_as, world):
    """**배선 확인.** 순수 함수가 맞아도 입력이 안 이어져 있으면 화면 숫자는 안 움직인다.

    이 저장소는 그 실패를 이미 겪었다(계산은 옳은데 입력이 비어 있어 통과한 테스트).
    그래서 기한이 남은 마일스톤과 기한이 지난 마일스톤으로 **점수가 달라지는지** 본다.
    """
    hdr = _hdr(login_as)
    url = f"/api/projects/{world['mine']}/health"

    created = _create(client, hdr, world["mine"], due_on="2099-01-01")
    milestone_id = created.json()["milestone"]["id"]
    healthy = client.get(url, headers=hdr).json()
    assert healthy["score"] is not None, f"마일스톤이 있는데 못 세고 있다: {healthy}"

    client.patch(
        f"/api/projects/{world['mine']}/milestones/{milestone_id}",
        json={"due_on": "2000-01-01"}, headers=hdr,
    )
    overdue = client.get(url, headers=hdr).json()

    assert overdue["score"] < healthy["score"], (
        f"기한을 넘긴 마일스톤이 점수를 안 움직인다(입력이 안 이어져 있다): "
        f"{healthy['score']} vs {overdue['score']}"
    )
    rules = {r["rule"] for r in overdue["reasons"]}
    assert "milestone_overdue" in rules, f"이유 목록에 규칙이 없다: {overdue}"
    assert overdue["reasons"][0]["detail"], "이유에 사람이 읽을 설명이 없다"


def test_a_project_with_nothing_to_measure_says_so_instead_of_scoring_it(
    client, login_as, db, world
):
    """마일스톤도 작업도 없는 포털 전용 프로젝트는 **100점이 아니라 모름**이다.

    그리고 이력에는 아무것도 안 적는다. 스냅샷의 점수 열은 NOT NULL 이라 무언가 적으려면
    거짓말을 해야 하고, 그 거짓말은 몇 주 뒤 추세선에서 진짜 값과 구별되지 않는다.
    """
    hdr = _hdr(login_as)
    body = client.get(f"/api/projects/{world['mine']}/health", headers=hdr).json()

    assert body["score"] is None, f"잴 것이 없는데 점수를 냈다: {body}"
    assert body["checked"] == []
    assert {u["rule"] for u in body["unknown"]} == {
        "milestone_overdue", "task_overdue", "unassigned", "stale", "notion_trouble",
    }, f"못 센 지표를 목록에서 빠뜨렸다: {body}"

    saved = client.post(
        f"/api/projects/{world['mine']}/health/snapshot", headers=hdr
    ).json()
    assert saved["snapshot"] is None, (
        f"점수를 낼 수 없는데 이력에 한 줄 적었다: {saved['snapshot']}"
    )
    history = client.get(
        f"/api/projects/{world['mine']}/health/history", headers=hdr
    ).json()
    assert history["items"] == [], "추세선에 거짓 점수가 들어갔다"


def test_the_snapshot_keeps_one_row_per_week_with_its_reasons(
    client, login_as, db, world
):
    """재계산이 행을 쌓으면 '주간 이력' 이 아니라 '실행 로그' 가 된다.

    그리고 이유를 함께 남기지 않으면 6주 뒤에 "왜 그때 그 점수였나" 에 아무도 답하지 못하고,
    그러면 점수 자체를 아무도 안 믿는다.
    """
    hdr = _hdr(login_as)
    _create(client, hdr, world["mine"], due_on="2000-01-01")

    first = client.post(
        f"/api/projects/{world['mine']}/health/snapshot", headers=hdr
    ).json()
    assert first["snapshot"] is not None, f"점수를 냈는데 이력에 안 적었다: {first}"
    assert first["snapshot"]["reasons"], "점수만 남기고 이유를 안 남겼다"

    client.post(f"/api/projects/{world['mine']}/health/snapshot", headers=hdr)
    history = client.get(
        f"/api/projects/{world['mine']}/health/history", headers=hdr
    ).json()

    assert len(history["items"]) == 1, (
        f"같은 주에 두 줄이 쌓였다(추세선이 실행 횟수를 그린다): {history['items']}"
    )
    assert history["items"][0]["score"] == first["score"]
    assert {r["rule"] for r in history["items"][0]["reasons"]} == {
        r["rule"] for r in first["reasons"]
    }, "저장된 이유가 그때 판단과 다르다"


def test_the_snapshot_caches_the_score_on_the_project_row(client, login_as, db, world):
    """목록이 프로젝트마다 규칙을 다시 돌리지 않도록 캐시한다(진행률과 같은 규약)."""
    from app.projects.models import Project

    hdr = _hdr(login_as)
    _create(client, hdr, world["mine"], due_on="2000-01-01")

    db.expire_all()
    assert db.get(Project, world["mine"]).health_score is None, (
        "계산 전에는 NULL 이어야 한다 - 0 은 '셌는데 0점' 이라는 뜻이다"
    )

    result = client.post(
        f"/api/projects/{world['mine']}/health/snapshot", headers=hdr
    ).json()

    db.expire_all()
    assert db.get(Project, world["mine"]).health_score == result["score"]
