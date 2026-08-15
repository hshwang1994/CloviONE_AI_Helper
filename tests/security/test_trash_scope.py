"""휴지통도 범위를 지킨다 (1순위 유출 #6).

`GET /api/trash` 는 조건이 **하나도 없었다** — `repository.list_items()` 가 전 행을 그대로
돌려준다. 그래서 로그인만 하면 **남의 팀이 지운 티켓·문서의 제목과 URL** 이 그대로 보였다.
목록 화면에서 가려 둔 것이 휴지통에서 새는 전형적인 경로다.

그리고 `trash_items` 는 `OrgScopedMixin` 을 상속한다 — **모델은 범위를 선언하는데 유일한
조회자가 그걸 안 걸고 있었다**(Z15). 두 곳이 다른 의도를 말하고 있었다.

## 판정 기준: 지운 사람

휴지통 항목에는 담당자가 없다. 있는 것은 `deleted_by_user_id` 다 — 그리고 그게 맞는 기준이다.
"내 팀이 지운 것" 이 내 팀이 되돌릴 수 있는 것이고, 되돌리기가 이 화면의 목적이다.
지운 사람이 **보관된 계정**(퇴사자)이면 그 사람은 `visible_user_ids` 에 안 잡힌다.
그 항목을 없애면 **퇴사자가 지운 것을 아무도 못 되돌린다** — 오프보딩 직후가 정확히
"저 사람이 뭘 지웠더라" 를 확인해야 하는 때다. 그래서 남긴다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def depts(db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    a = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    b = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([a, b])
    db.commit()
    return a, b


def _trash(db, *, title, by, page):
    from app.trash.models import TRASH_TICKET, TrashItem

    db.add(TrashItem(
        item_type=TRASH_TICKET, notion_page_id=page, title=title,
        url="https://notion/" + page,
        deleted_by_user_id=by.id if by else None,
        deleted_by_name=by.display_name if by else "시스템",
        deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.commit()


def test_a_user_does_not_see_what_another_team_deleted(client, login_as, make_user, db, depts):
    mine, theirs = depts
    me = make_user("trash-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("trash-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.commit()

    _trash(db, title="우리팀이 지운 것", by=me, page="p-mine")
    _trash(db, title="남의팀이 지운 것", by=other, page="p-theirs")

    login_as("user", email="trash-me@goodmit.co.kr")
    titles = {i["title"] for i in client.get("/api/trash").json()["items"]}

    assert "우리팀이 지운 것" in titles, "내 팀이 지운 것이 안 보인다 — 되돌릴 수가 없다"
    assert "남의팀이 지운 것" not in titles, "남의 팀이 지운 티켓의 제목과 URL 이 보인다"


def test_what_an_offboarded_person_deleted_is_still_visible(
    client, login_as, make_user, db, depts
):
    """퇴사자가 지운 것을 없애면 **아무도 못 되돌린다.** 오프보딩 직후가 정확히
    "저 사람이 뭘 지웠더라" 를 확인해야 하는 때다."""
    from datetime import datetime, timezone

    mine, _ = depts
    me = make_user("trash-keep@goodmit.co.kr", role="user", display_name="나")
    gone = make_user("trash-gone@goodmit.co.kr", role="user", display_name="퇴사자")
    me.department_id = mine.id
    gone.department_id = mine.id
    db.commit()
    _trash(db, title="퇴사자가 지운 것", by=gone, page="p-gone")

    # 보관 처리 — `visible_user_ids` 는 활성 사용자만 본다.
    gone.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    gone.active = False
    db.commit()

    login_as("user", email="trash-keep@goodmit.co.kr")
    titles = {i["title"] for i in client.get("/api/trash").json()["items"]}
    assert "퇴사자가 지운 것" in titles, "퇴사자가 지운 것이 사라졌다 — 아무도 되돌릴 수 없다"


def test_the_visible_total_does_not_count_another_teams_hidden_items(
    client, login_as, make_user, db, depts
):
    """UA-10 확증으로 생긴 total도 범위를 지켜야 한다 — 안 그러면 항목 자체는 가려도
    "남의 팀이 몇 건 지웠는지"가 숫자로 새는 또 다른 경로가 된다."""
    mine, theirs = depts
    me = make_user("trash-total-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("trash-total-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.commit()

    _trash(db, title="우리팀 것", by=me, page="p-total-mine")
    _trash(db, title="남의팀 것1", by=other, page="p-total-other-1")
    _trash(db, title="남의팀 것2", by=other, page="p-total-other-2")

    login_as("user", email="trash-total-me@goodmit.co.kr")
    body = client.get("/api/trash").json()
    assert len(body["items"]) == 1
    assert body["total"] == 1, f"안 보이는 남의 팀 개수가 total로 샜다: {body['total']}"


def test_a_global_admin_still_sees_everything(client, login_as, make_user, db, depts):
    mine, theirs = depts
    other = make_user("trash-far@goodmit.co.kr", role="user", display_name="남")
    other.department_id = theirs.id
    db.commit()
    _trash(db, title="남의팀이 지운 것", by=other, page="p-far")

    login_as("system_admin")
    titles = {i["title"] for i in client.get("/api/trash").json()["items"]}
    assert "남의팀이 지운 것" in titles, "전체 관리자가 못 본다 — 범위가 너무 좁다"


# ---------------------------------------------------------------------------
# 쓰기 경로 — 목록만 가려서는 아무 의미가 없다 (3순위 IDOR)
#
# 위 세 테스트는 **목록**만 본다. 그런데 복원·영구삭제는 id 를 직접 받으므로 목록을 안 거친다.
# 즉 가려 놓은 항목을 **id 하나로 영구삭제**할 수 있었고, 그 결과는 되돌릴 수 없다.
# 그리고 단건만 막으면 **일괄 경로가 그대로 뚫린다** — 그래서 판정을 네 경로가 모두 지나는
# `ensure_can_manage` 한 곳에 뒀다. 아래가 그 네 경로를 전부 친다.
# ---------------------------------------------------------------------------


@pytest.fixture()
def scoped_admin(make_user, db, depts):
    """부서 범위 관리자 — 자기 팀만 관리한다(F2 로 만든 설정 경로와 같은 값)."""
    mine, _ = depts
    u = make_user("trash-mod@goodmit.co.kr", role="admin", display_name="팀관리자")
    u.department_id = mine.id
    u.admin_scope = "dept"
    u.scope_dept_id = mine.id
    db.commit()
    return u


def _still_there(db, page: str) -> bool:
    from sqlalchemy import select

    from app.trash.models import TrashItem

    return db.execute(
        select(TrashItem).where(TrashItem.notion_page_id == page)
    ).scalar_one_or_none() is not None


def test_a_scoped_moderator_cannot_purge_another_teams_item(
    client, login_as, make_user, db, depts, scoped_admin
):
    """영구삭제는 **되돌릴 수 없다** — 여기서 새면 남의 팀 자료가 영영 사라진다."""
    _, theirs = depts
    other = make_user("trash-victim@goodmit.co.kr", role="user", display_name="남")
    other.department_id = theirs.id
    db.commit()
    _trash(db, title="남의팀이 지운 것", by=other, page="p-idor")

    from sqlalchemy import select

    from app.trash.models import TrashItem

    hdr = {"X-CSRF-Token": login_as("admin", email="trash-mod@goodmit.co.kr")}
    item_id = db.execute(
        select(TrashItem.id).where(TrashItem.notion_page_id == "p-idor")
    ).scalar_one()

    r = client.post(f"/api/trash/{item_id}/purge", headers=hdr)
    assert r.status_code == 404, f"범위 밖 항목이 영구삭제됐다: {r.status_code}"
    assert _still_there(db, "p-idor"), "범위 밖 항목이 실제로 지워졌다"

    r = client.post(f"/api/trash/{item_id}/restore", headers=hdr)
    assert r.status_code == 404, f"범위 밖 항목이 복원됐다: {r.status_code}"
    assert _still_there(db, "p-idor")


def test_bulk_paths_cannot_reach_another_teams_item(
    client, login_as, make_user, db, depts, scoped_admin
):
    """단건만 막으면 소용없다 — 일괄 경로는 id 목록을 그대로 받는다."""
    from sqlalchemy import select

    from app.trash.models import TrashItem

    _, theirs = depts
    other = make_user("trash-victim2@goodmit.co.kr", role="user", display_name="남")
    other.department_id = theirs.id
    db.commit()
    _trash(db, title="남의팀이 지운 것2", by=other, page="p-bulk")

    hdr = {"X-CSRF-Token": login_as("admin", email="trash-mod@goodmit.co.kr")}
    item_id = db.execute(
        select(TrashItem.id).where(TrashItem.notion_page_id == "p-bulk")
    ).scalar_one()

    r = client.post("/api/trash/purge-bulk", json={"ids": [item_id]}, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["purged"] == [], f"일괄 영구삭제가 범위 밖 항목을 지웠다: {r.json()}"
    assert _still_there(db, "p-bulk"), "일괄 경로로 범위 밖 항목이 지워졌다"

    r = client.post("/api/trash/restore-bulk", json={"ids": [item_id]}, headers=hdr)
    assert r.json()["restored"] == [], f"일괄 복원이 범위 밖 항목을 건드렸다: {r.json()}"
    assert _still_there(db, "p-bulk")


def test_the_scoped_moderator_can_still_manage_their_own_teams_item(
    client, login_as, make_user, db, depts, scoped_admin
):
    """오탐 방지 — 좁히느라 자기 팀 것까지 못 만지게 하면 그건 기능 고장이다."""
    from sqlalchemy import select

    from app.trash.models import TrashItem

    mine, _ = depts
    mate = make_user("trash-mate@goodmit.co.kr", role="user", display_name="동료")
    mate.department_id = mine.id
    db.commit()
    _trash(db, title="우리팀이 지운 것", by=mate, page="p-ok")

    hdr = {"X-CSRF-Token": login_as("admin", email="trash-mod@goodmit.co.kr")}
    item_id = db.execute(
        select(TrashItem.id).where(TrashItem.notion_page_id == "p-ok")
    ).scalar_one()

    r = client.post(f"/api/trash/{item_id}/restore", headers=hdr)
    assert r.status_code == 200, f"자기 팀 항목을 복원할 수 없다: {r.status_code} {r.text}"
    db.commit()  # 스냅샷을 새로 뜬다 — 위 SELECT가 이미 연 트랜잭션은 restore 이전 상태를 본다
    assert not _still_there(db, "p-ok"), "복원했는데 휴지통에 남아 있다"


# RBAC 재감사(2026-08-16)로 발견: list_visible/visible_to가 `is_dept`일 때만 걸러 org 범위
# (admin_scope="org") 관리자를 global과 똑같이 취급했다 — 위 dept 시험들과 별개로 이 org
# 경계는 어떤 시험도 없었다. 여기서는 그 결과가 **되돌릴 수 없는 영구삭제**라 더 심각하다.
@pytest.fixture()
def org_scoped_admin(make_user, db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Organization

    other_org = Organization(slug="trash-org-scope-tenant", name="다른 회사", status="active")
    db.add(other_org)
    db.flush()
    u = make_user("trash-org-mod@goodmit.co.kr", role="admin", display_name="A조직관리자")
    u.org_id = DEFAULT_ORG_ID
    u.admin_scope = "org"
    u.scope_org_id = DEFAULT_ORG_ID
    other = make_user("trash-org-victim@goodmit.co.kr", role="user", display_name="B조직원")
    other.org_id = other_org.id
    db.commit()
    return u, other


def test_org_scoped_admin_does_not_see_another_organizations_trash(client, login_as, db, org_scoped_admin):
    _, other = org_scoped_admin
    _trash(db, title="B조직이 지운 것", by=other, page="p-org-list")

    login_as("admin", email="trash-org-mod@goodmit.co.kr")
    titles = {i["title"] for i in client.get("/api/trash").json()["items"]}
    assert "B조직이 지운 것" not in titles, "org 범위 관리자에게 다른 조직 휴지통 항목이 보인다"


def test_org_scoped_admin_cannot_purge_another_organizations_item(client, login_as, db, org_scoped_admin):
    """영구삭제는 되돌릴 수 없다 — org 경계가 뚫리면 다른 조직 자료가 영영 사라진다."""
    from sqlalchemy import select

    from app.trash.models import TrashItem

    _, other = org_scoped_admin
    _trash(db, title="B조직이 지운 것", by=other, page="p-org-idor")

    hdr = {"X-CSRF-Token": login_as("admin", email="trash-org-mod@goodmit.co.kr")}
    item_id = db.execute(
        select(TrashItem.id).where(TrashItem.notion_page_id == "p-org-idor")
    ).scalar_one()

    r = client.post(f"/api/trash/{item_id}/purge", headers=hdr)
    assert r.status_code == 404, f"org 범위 밖 항목이 영구삭제됐다: {r.status_code}"
    assert _still_there(db, "p-org-idor"), "org 범위 밖 항목이 실제로 지워졌다"
