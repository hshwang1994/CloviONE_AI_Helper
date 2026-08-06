"""WBS 트리 — 미러의 `parent_page_id` 로 만든 계층이 **실제로 화면까지 이어지는지**.

순수 계산은 `tests/unit/test_project_progress.py` 가 못박는다. 여기서 보는 것은 그 계산에
**무엇이 들어가는가**와, 트리를 만들다 서버가 죽지 않는가다. 네 가지를 본다.

1. **계층** - `parent_page_id` 가 부모, 자식으로 실제로 이어지는가.
2. **순환 방어** - 노션에서 A의 상위가 B, B의 상위가 A 가 만들어질 수 있다. 순진하게 재귀하면
   워커가 스택을 다 쓰고 죽는다. 요청 하나가 프로세스를 죽이면 그건 화면 버그가 아니라 장애다.
3. **0043 소프트 프룬** - "이번 회차 노션 응답에서 안 보였다" 로 표시된 티켓은 목록에서 이미
   빠져 있다. 트리에만 남으면 화면에 없는 일이 분모에 남아 진행률이 이유 없이 낮아진다.
4. **트리 진행률과 헤더 진행률이 같은 값인가** - 이게 이 파일에서 가장 중요한 단정이다.
   계산이 두 벌이 되면 같은 화면의 두 숫자가 갈라지고, 그때 사용자는 둘 다 안 믿는다.
   그래서 두 API 를 실제로 두드려 값을 맞춰 보고, **기대값도 함께 적는다** - 두 곳이 똑같이
   틀렸을 때 "같으니 통과" 로 넘어가지 않으려면 정답을 따로 알고 있어야 한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import TicketCache

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 14, 0, 0, 0)
BOSS_EMAIL = "prj-wbs@goodmit.co.kr"

PROJ_PAGE = "page-wbs"
IN_PROGRESS = "진행"


def _ticket(db, *, page_id, projects=(PROJ_PAGE,), title="작업", status=IN_PROGRESS,
            est=None, missing_at=None, parent=None):
    row = TicketCache(
        id=f"uid-{page_id}",
        notion_page_id=page_id,
        org_id=DEFAULT_ORG_ID,
        title=title,
        status=status,
        est_wd=est,
        parent_page_id=parent,
        project_ids=join_names(list(projects)),
        project_names="",
        assignee_notion_ids="",
        source="notion",
        synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
        notion_missing_at=missing_at,
    )
    db.add(row)
    return row


@pytest.fixture()
def world(db, make_user):
    boss = make_user(BOSS_EMAIL, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    db.commit()

    linked = Project(name="트리 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id=PROJ_PAGE)
    portal_only = Project(name="포털 전용 프로젝트", org_id=DEFAULT_ORG_ID)
    db.add_all([linked, portal_only])
    db.commit()
    return {"linked": linked.id, "portal_only": portal_only.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def _wbs(client, login_as, project_id):
    r = client.get(f"/api/projects/{project_id}/wbs", headers=_hdr(login_as))
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    return r.json()


def _flatten(nodes) -> dict:
    """key → node. 트리를 훑어야 확인할 수 있는 단정들이 있다."""
    out = {}
    for node in nodes:
        out[node["key"]] = node
        out.update(_flatten(node["children"]))
    return out


def _sample_with_a_parent_and_a_cancelled_task(db):
    """부모 1 + 자식 2 + 취소 1 + 홀로 1.

    **틀린 방법으로 세면 값이 달라지는** 표본이다. 부모를 함께 세거나(노션식 이중 계산)
    취소를 완료로 세면(노션 rollup) 아래 기대값이 나오지 않는다.
    """
    _ticket(db, page_id="p-parent", title="상위 작업", est=100)
    _ticket(db, page_id="p-c1", title="자식1", est=3, status="완료", parent="p-parent")
    _ticket(db, page_id="p-c2", title="자식2", est=7, parent="p-parent")
    _ticket(db, page_id="p-cancel", title="취소된 작업", est=90, status="취소")
    _ticket(db, page_id="p-solo", title="홀로", est=10, status="완료")
    db.commit()


# 위 표본의 정답. 리프만(자식1, 자식2, 취소, 홀로) 세고 취소는 분자, 분모에서 함께 뺀다:
#   (3 + 10) / (3 + 7 + 10) = 65.0
WHOLE_PROJECT_PERCENT = 65.0
# 상위 작업의 하위 트리만: 3 / (3 + 7) = 30.0
PARENT_SUBTREE_PERCENT = 30.0


def test_the_tree_mirrors_the_parent_child_relation(client, login_as, db, world):
    """`parent_page_id` 가 부모, 자식으로 실제로 이어지는가."""
    _sample_with_a_parent_and_a_cancelled_task(db)

    body = _wbs(client, login_as, world["linked"])
    roots = {node["key"]: node for node in body["roots"]}

    assert set(roots) == {"p-parent", "p-cancel", "p-solo"}, (
        f"루트가 계층을 반영하지 않는다(자식이 루트로 올라왔거나 부모가 사라졌다): {sorted(roots)}"
    )
    parent = roots["p-parent"]
    assert {c["key"] for c in parent["children"]} == {"p-c1", "p-c2"}, (
        f"자식이 부모 밑에 안 붙었다: {parent}"
    )
    assert parent["depth"] == 0 and parent["children"][0]["depth"] == 1
    assert roots["p-solo"]["children"] == []
    assert parent["title"] == "상위 작업", "화면에 그릴 제목이 안 실렸다"


def test_a_cycle_is_reported_instead_of_hanging_the_worker(client, login_as, db, world):
    """노션에서 A의 상위가 B, B의 상위가 A 가 만들어질 수 있다.

    순진하게 재귀하면 요청 하나가 프로세스를 죽인다. 그리고 조용히 빼 버리는 것도 답이
    아니다 - 트리에 안 보이는 작업이 생기면 사용자는 자기 일이 사라진 줄 안다.
    **못 그렸다는 사실을 말해야** 고칠 사람이 노션에서 고친다.
    """
    _ticket(db, page_id="p-a", title="에이", parent="p-b", est=5)
    _ticket(db, page_id="p-b", title="비", parent="p-a", est=5)
    _ticket(db, page_id="p-self", title="자기참조", parent="p-self", est=5)
    _ticket(db, page_id="p-ok", title="멀쩡한 작업", est=5, status="완료")
    db.commit()

    body = _wbs(client, login_as, world["linked"])

    assert {node["key"] for node in body["roots"]} == {"p-ok"}, (
        f"순환에 걸린 작업이 루트로 올라왔다(그 밑을 그리려다 무한 재귀가 난다): {body['roots']}"
    )
    assert set(_flatten(body["roots"])) == {"p-ok"}, "순환 노드가 트리 어딘가에 그려졌다"

    unplaced = {row["key"]: row for row in body["unplaced"]}
    assert set(unplaced) == {"p-a", "p-b", "p-self"}, (
        f"순환에 걸린 작업을 조용히 버렸다(사용자는 일이 사라진 줄 안다): {body['unplaced']}"
    )
    assert unplaced["p-a"]["reason"] == "cycle"
    assert unplaced["p-self"]["reason"] == "cycle", "자기 자신이 상위인 경우도 순환이다"
    assert unplaced["p-a"]["title"] == "에이", "무엇이 못 그려졌는지 이름으로 알 수 있어야 한다"


def test_a_chain_deeper_than_the_cap_is_reported_not_recursed(
    client, login_as, db, world
):
    """깊이 상한. 순환이 아니어도 데이터가 이상하면 깊이가 폭주할 수 있다.

    `app/core/scope.py::department_subtree_ids` 가 부서 트리에서 같은 그물을 두 겹으로
    치는 것과 같은 이유다: 방문 표시 하나에만 기대면 그 하나가 틀렸을 때 막을 것이 없다.
    """
    from app.projects.wbs import MAX_WBS_DEPTH

    parent = None
    for i in range(MAX_WBS_DEPTH + 3):
        page = f"p-chain-{i}"
        _ticket(db, page_id=page, title=f"{i}단계", parent=parent, est=1)
        parent = page
    db.commit()

    body = _wbs(client, login_as, world["linked"])
    placed = _flatten(body["roots"])

    assert len(placed) == MAX_WBS_DEPTH + 1, (
        f"상한 {MAX_WBS_DEPTH} 를 넘겨 그렸다: 깊이 {len(placed)}"
    )
    too_deep = {row["key"] for row in body["unplaced"] if row["reason"] == "too_deep"}
    assert too_deep == {
        f"p-chain-{i}" for i in range(MAX_WBS_DEPTH + 1, MAX_WBS_DEPTH + 3)
    }, f"상한에서 잘라 내고는 잘랐다고 말하지 않았다: {body['unplaced']}"


def test_softly_pruned_tickets_are_not_in_the_tree(client, login_as, db, world):
    """0043 이 '안 보임' 으로 표시한 티켓은 목록에서 이미 빠져 있다.

    트리에만 남으면 화면 어디에도 없는 일이 분모에 남아 진행률이 이유 없이 낮아진다.
    다음 회차에 돌아오면 표시가 지워져 숫자가 저절로 바뀌고, 그때는 아무도 원인을 못 찾는다.
    """
    _ticket(db, page_id="p-parent", title="상위", est=1)
    _ticket(db, page_id="p-live", title="살아 있는 자식", est=5, status="완료",
            parent="p-parent")
    _ticket(db, page_id="p-gone", title="사라진 자식", est=5, parent="p-parent",
            missing_at=NOW)
    db.commit()

    body = _wbs(client, login_as, world["linked"])
    placed = _flatten(body["roots"])

    assert "p-gone" not in placed, (
        f"소프트 프룬된 티켓이 트리에 남아 있다: {sorted(placed)}"
    )
    assert body["progress"]["percent"] == 100.0, (
        f"소프트 프룬된 티켓이 분모에 남았다: {body['progress']}"
    )
    assert body["progress"]["percent"] != 50.0, "사라진 티켓을 계속 세고 있다"


def test_the_tree_total_matches_the_header_progress(client, login_as, db, world):
    """**같은 화면의 두 숫자가 갈리지 않는다.**

    트리 진행률과 헤더 진행률이 다르면 사용자는 어느 쪽도 안 믿고, 결국 둘 다 안 본다.
    두 값이 같은지만 보면 둘이 똑같이 틀렸을 때 통과하므로 정답도 함께 적는다.
    """
    _sample_with_a_parent_and_a_cancelled_task(db)
    hdr = _hdr(login_as)

    tree = _wbs(client, login_as, world["linked"])
    header = client.get(
        f"/api/projects/{world['linked']}/progress", headers=hdr
    ).json()

    assert tree["progress"]["percent"] == WHOLE_PROJECT_PERCENT, (
        f"트리 진행률이 정답과 다르다: {tree['progress']}"
    )
    assert header["percent"] == WHOLE_PROJECT_PERCENT, (
        f"헤더 진행률이 정답과 다르다: {header}"
    )
    assert tree["progress"]["basis"] == header["basis"], (
        "계산 근거가 갈렸다 - 두 화면이 다른 표본을 세고 있다는 뜻이다\n"
        f"트리: {tree['progress']['basis']}\n헤더: {header['basis']}"
    )


def test_each_node_carries_the_progress_of_its_own_subtree(client, login_as, db, world):
    """노드 진행률은 **그 아래만** 센다. 전체를 복사해 붙이면 트리가 아무 정보도 안 준다."""
    _sample_with_a_parent_and_a_cancelled_task(db)

    body = _wbs(client, login_as, world["linked"])
    nodes = _flatten(body["roots"])

    assert nodes["p-parent"]["progress"]["percent"] == PARENT_SUBTREE_PERCENT, (
        f"상위 작업의 하위 트리 진행률이 틀렸다: {nodes['p-parent']['progress']}"
    )
    assert nodes["p-parent"]["progress"]["percent"] != WHOLE_PROJECT_PERCENT, (
        "노드마다 프로젝트 전체 진행률을 그대로 복사했다"
    )
    assert nodes["p-c1"]["progress"]["percent"] == 100.0, "완료한 리프가 100%가 아니다"
    assert nodes["p-c2"]["progress"]["percent"] == 0.0, "진행 중인 리프가 0%가 아니다"
    assert nodes["p-cancel"]["progress"]["percent"] is None, (
        "취소만 있는 노드가 0%로 나왔다 - 셀 것이 없는 것과 0%는 다른 상태다"
    )


def test_a_portal_only_project_draws_an_empty_tree(client, login_as, db, world):
    """노션 짝이 없으면 걸린 작업이 있을 수 없다. 없으면 없다고 한다."""
    _sample_with_a_parent_and_a_cancelled_task(db)

    body = _wbs(client, login_as, world["portal_only"])

    assert body["roots"] == [], f"포털 전용 프로젝트가 남의 작업을 그렸다: {body['roots']}"
    assert body["unplaced"] == []
    assert body["progress"]["percent"] is None, "셀 것이 없는데 0%라고 답한다"
