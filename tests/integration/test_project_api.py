"""프로젝트 API 가 **미러와 실제로 이어져 있는지**, 그리고 잘못된 입력에 500 을 내지 않는지.

진행률 계산 자체는 `tests/unit/test_project_progress.py` 가 순수 함수로 못박는다. 여기서
보는 것은 그 함수에 **무엇이 들어가는가**다 - 계산이 아무리 맞아도 표본이 틀리면 화면의
숫자는 틀린다. 그 다리는 세 곳에서 끊어질 수 있다:

  1. `project_ids` 는 구분자로 감싼 다중값 문자열이다. 토큰으로 안 감싸고 부분일치로
     찾으면 page id 접두사가 겹치는 **남의 프로젝트 티켓이 분모에 섞인다**.
  2. 0043 의 소프트 프룬(`notion_missing_at`)으로 목록에서 빠진 티켓을 진행률만 계속
     세면, 화면에 안 보이는 일이 분모에 남아 진행률이 이유 없이 낮게 나온다.
  3. Notion 짝이 없는 포털 전용 프로젝트에서 폴백으로 '전체 티켓'을 세면 회사의 모든
     작업이 그 프로젝트의 분모가 된다.

입력 쪽도 함께 본다. 유니크 제약과 NOT NULL 을 DB 에 맡기면 사용자는 400 이 아니라 **500**
을 보고, 화면은 "서버 오류"라고 말한다 - 아무도 자기 입력을 의심하지 않는다.
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
BOSS_EMAIL = "prj-api@goodmit.co.kr"

# 접두사가 겹치는 짝. 토큰으로 안 감싸면 `page-proj` 필터에 `page-proj-2` 가 따라온다.
PROJ_PAGE = "page-proj"
OTHER_PROJ_PAGE = "page-proj-2"


def _ticket(db, *, uid, page_id, projects, status="진행", est=None, missing_at=None,
            parent=None):
    row = TicketCache(
        id=uid,
        notion_page_id=page_id,
        org_id=DEFAULT_ORG_ID,
        title="작업",
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

    linked = Project(
        name="노션에 짝이 있는 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id=PROJ_PAGE,
    )
    portal_only = Project(name="포털 전용 프로젝트", org_id=DEFAULT_ORG_ID)
    db.add_all([linked, portal_only])
    db.commit()
    return {"linked": linked.id, "portal_only": portal_only.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def test_progress_counts_only_this_projects_tickets(client, login_as, db, world):
    """다중값 열을 토큰으로 감싸 맞추는지 - 접두사가 겹치는 프로젝트가 섞이면 안 된다."""
    _ticket(db, uid="t-mine-done", page_id="p-1", projects=(PROJ_PAGE,),
            status="완료", est=3)
    _ticket(db, uid="t-mine-open", page_id="p-2", projects=(PROJ_PAGE,),
            status="진행", est=7)
    _ticket(db, uid="t-other", page_id="p-3", projects=(OTHER_PROJ_PAGE,),
            status="완료", est=90)
    db.commit()

    body = client.get(
        f"/api/projects/{world['linked']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["counted_tasks"] == 2, (
        f"남의 프로젝트 티켓이 분모에 섞였다: {body['basis']}"
    )
    assert body["percent"] == 30.0, f"3 / (3 + 7) 이 아니다: {body}"


def test_softly_pruned_tickets_leave_the_denominator(client, login_as, db, world):
    """0043 이 '안 보임'으로 표시한 티켓은 목록에서 이미 빠져 있다.

    진행률만 계속 세면 화면에 없는 일이 분모에 남아 진행률이 이유 없이 낮아진다.
    그리고 다음 회차에 돌아오면 표시가 지워져 아무 일도 없었던 것이 된다 - 그때 숫자가
    저절로 바뀌면 아무도 원인을 못 찾는다.
    """
    _ticket(db, uid="t-live", page_id="p-1", projects=(PROJ_PAGE,), status="완료", est=5)
    _ticket(db, uid="t-gone", page_id="p-2", projects=(PROJ_PAGE,), status="진행",
            est=5, missing_at=NOW)
    db.commit()

    body = client.get(
        f"/api/projects/{world['linked']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["counted_tasks"] == 1, (
        f"소프트 프룬된 티켓이 분모에 남아 있다: {body['basis']}"
    )
    assert body["percent"] == 100.0


def test_a_portal_only_project_counts_nothing_rather_than_everything(
    client, login_as, db, world
):
    """Notion 짝이 없으면 걸린 작업이 있을 수 없다. 폴백으로 전체를 세면 안 된다."""
    _ticket(db, uid="t-somebody", page_id="p-1", projects=(PROJ_PAGE,),
            status="완료", est=5)
    db.commit()

    body = client.get(
        f"/api/projects/{world['portal_only']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["sample_tasks"] == 0, (
        f"포털 전용 프로젝트가 남의 작업을 세고 있다: {body['basis']}"
    )
    assert body["percent"] is None, "셀 것이 없는데 0% 라고 답한다"


def test_the_child_and_the_parent_are_not_counted_twice(client, login_as, db, world):
    """미러의 `parent_page_id` 가 리프 판정까지 실제로 이어지는지."""
    _ticket(db, uid="t-parent", page_id="page-parent", projects=(PROJ_PAGE,),
            status="진행", est=100)
    _ticket(db, uid="t-child", page_id="page-child", projects=(PROJ_PAGE,),
            status="완료", est=10, parent="page-parent")
    db.commit()

    body = client.get(
        f"/api/projects/{world['linked']}/progress", headers=_hdr(login_as)
    ).json()

    assert body["basis"]["parent_tasks_excluded"] == 1, (
        f"부모가 분모에 남았다(이중 계산): {body['basis']}"
    )
    assert body["percent"] == 100.0


def test_recompute_caches_the_percent_on_the_row(client, login_as, db, world):
    """목록이 프로젝트마다 티켓을 다시 세지 않도록 캐시한다."""
    _ticket(db, uid="t-1", page_id="p-1", projects=(PROJ_PAGE,), status="완료", est=1)
    _ticket(db, uid="t-2", page_id="p-2", projects=(PROJ_PAGE,), status="진행", est=3)
    db.commit()

    assert db.get(Project, world["linked"]).progress_pct is None, (
        "계산 전에는 NULL 이어야 한다 - 0.0 은 '셌는데 0%' 라는 뜻이다"
    )

    r = client.post(
        f"/api/projects/{world['linked']}/progress/recompute", headers=_hdr(login_as)
    )
    assert r.status_code == 200, r.text

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(Project, world["linked"]).progress_pct == 25.0


def test_a_duplicate_code_in_the_same_org_is_409_not_500(client, login_as, world):
    """유니크 제약에 맡기면 IntegrityError 가 500 으로 나간다."""
    hdr = _hdr(login_as)
    first = client.post("/api/projects", json={"name": "가", "code": "PRJ-1"}, headers=hdr)
    assert first.status_code == 200, first.text

    second = client.post("/api/projects", json={"name": "나", "code": "PRJ-1"}, headers=hdr)
    assert second.status_code == 409, f"중복 코드가 409 가 아니다: {second.status_code}"


def test_projects_without_a_code_do_not_collide(client, login_as, world):
    """코드는 없을 수 있다. NULL 끼리는 충돌하지 않는다(그래서 빈 문자열로 안 채운다)."""
    hdr = _hdr(login_as)
    assert client.post("/api/projects", json={"name": "코드 없음 1"}, headers=hdr).status_code == 200
    assert client.post("/api/projects", json={"name": "코드 없음 2"}, headers=hdr).status_code == 200


def test_an_unknown_department_is_404_not_500(client, login_as, world):
    """FK 에 맡기면 IntegrityError 가 500 으로 나가고, FK 가 꺼진 환경이면 어느 부서
    목록에도 안 나오는 유령 행이 남는다. 범위 밖 부서와 **같은 404** 여야 한다."""
    r = client.post(
        "/api/projects",
        json={"name": "유령", "dept_id": "there-is-no-such-department"},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"없는 부서로 프로젝트가 만들어진다: {r.status_code} {r.text}"


def test_blanking_a_required_field_is_422_not_500(client, login_as, world):
    """NOT NULL 컬럼에 명시적 null 을 넣으면 400 대가 나와야 한다."""
    r = client.patch(
        f"/api/projects/{world['linked']}", json={"name": None}, headers=_hdr(login_as)
    )
    assert r.status_code == 422, f"이름을 비웠는데 {r.status_code} 다: {r.text}"


def test_progress_is_not_settable_from_the_client(client, login_as, world):
    """`progress_pct` 를 입력으로 받으면 화면이 보고 싶은 숫자를 써 넣을 수 있다.

    그러면 "앱이 다시 계산한다"는 이 subsystem 의 전제가 그 자리에서 무너진다 - 틀린 것보다
    나쁘다(틀린 줄도 모른다).
    """
    r = client.patch(
        f"/api/projects/{world['linked']}",
        json={"progress_pct": 99.0},
        headers=_hdr(login_as),
    )
    assert r.status_code == 422, f"클라이언트가 진행률을 직접 넣을 수 있다: {r.status_code}"
