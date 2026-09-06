"""AI 사용 상한의 **대상 계정**은 닫힌 계정일 수 없다 (xb-10 · xc-06 · xc-13).

닫힌 계정(보관·비활성)에 걸린 상한은 **절대 소비되지 않는다** — 로그인할 수 없는 사람은
AI 를 부르지 않는다. 그런데 이 화면은 그 행을 살아 있는 계정의 상한과 똑같이 그렸고,
관리자는 아무 효과 없는 값을 유지하고 수정하며 시간을 썼다. 같은 제품의 티켓 담당자 지정과
승인 위임은 이미 같은 계정을 422 로 거절한다 — 한 규칙이 자리마다 다르면 좁은 쪽이
우회로가 된다.

여기서 못박는 것은 셋이다.

  * 닫힌 계정에는 상한을 **새로** 걸 수 없다(422).
  * 살아 있는 계정에는 그대로 걸린다(반례 — 「전부 막는다」가 되면 기능이 죽는다).
  * 이미 만들어진 행은 대상이 닫혀도 **고치고 지울 수 있고**, 목록이 그 상태를 말한다.
    닫혔다고 손댈 수 없게 만들면 죽은 행을 치울 방법이 사라진다.
"""

from __future__ import annotations

import pytest

from app.core.models_base import utcnow
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(client, make_user):
    make_user(email="quota-boss@goodmit.co.kr", role="system_admin", display_name="관리자")
    response = client.post(
        "/login", json={"email": "quota-boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.fixture()
def people(db, make_user):
    """살아 있는 계정 · 보관된 계정 · 비활성 계정."""
    live = make_user(email="quota-live@goodmit.co.kr", display_name="일하는사람", role="user")
    archived = make_user(email="quota-gone@goodmit.co.kr", display_name="보관계정", role="user")
    paused = make_user(email="quota-paused@goodmit.co.kr", display_name="휴직자", role="user")
    archived.archived_at = utcnow()
    archived.active = False
    paused.active = False
    db.commit()
    return {"live": live.id, "archived": archived.id, "paused": paused.id}


def _create(client, csrf, user_id, *, period="day", max_calls=5):
    return client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "user", "user_id": user_id, "period": period,
              "max_calls": max_calls},
        headers={"X-CSRF-Token": csrf},
    )


def test_a_quota_for_a_live_account_is_created(client, admin, people):
    """반례 — 원래 하려던 일은 그대로 된다."""
    response = _create(client, admin, people["live"])

    assert response.status_code == 201, response.text
    assert response.json()["user_id"] == people["live"]


def test_a_quota_for_an_archived_account_is_refused(client, admin, people, db):
    from app.quotas.models import AiQuota

    response = _create(client, admin, people["archived"])

    assert response.status_code == 422, response.text
    assert "보관된 계정" in response.json()["error"]["message"]
    assert db.query(AiQuota).count() == 0, "거절했는데 행이 만들어졌다"


def test_a_quota_for_a_deactivated_account_is_refused(client, admin, people):
    response = _create(client, admin, people["paused"])

    assert response.status_code == 422, response.text
    assert "비활성 계정" in response.json()["error"]["message"]


def test_a_target_outside_the_scope_is_still_a_404_not_a_422(client, db, make_user, two_orgs):
    """범위 밖은 **존재를 숨긴다** — 상태를 말하기 전에 범위부터 본다(IDOR 계약)."""
    from app.users.models import ADMIN_SCOPE_ORG

    boss = make_user(email="org-a-boss@goodmit.co.kr", role="admin", display_name="A조직관리자")
    boss.admin_scope = ADMIN_SCOPE_ORG
    boss.scope_org_id = two_orgs.org_a_id
    boss.org_id = two_orgs.org_a_id
    outsider = two_orgs.user_b
    outsider.archived_at = utcnow()
    outsider.active = False
    db.commit()

    response = client.post(
        "/login", json={"email": "org-a-boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]

    created = _create(client, csrf, outsider.id)
    assert created.status_code == 404, created.text


def test_an_existing_quota_can_still_be_fixed_after_the_target_is_archived(
    client, admin, people, db
):
    """이미 있는 행은 계속 손댈 수 있다 — **죽은 행을 치울 방법**이 사라지면 안 된다.

    새로 지정하는 것과 이미 지정된 것은 다른 일이다. 여기까지 막으면 계정을 보관한 순간
    그 사람의 상한이 목록에 영구히 남는다.
    """
    from app.quotas.models import AiQuota

    created = _create(client, admin, people["live"])
    row_id = created.json()["id"]

    from app.users.models import User

    target = db.get(User, people["live"])
    target.archived_at = utcnow()
    target.active = False
    db.commit()

    patched = client.patch(
        f"/api/admin/ai-quotas/{row_id}", json={"max_calls": 1},
        headers={"X-CSRF-Token": admin},
    )
    assert patched.status_code == 200, patched.text

    deleted = client.delete(
        f"/api/admin/ai-quotas/{row_id}", headers={"X-CSRF-Token": admin}
    )
    assert deleted.status_code == 200, deleted.text
    assert db.get(AiQuota, row_id) is None


def test_the_list_says_which_targets_are_closed_accounts(client, admin, people, db):
    """목록이 보관 계정을 살아 있는 계정과 똑같이 그리면 관리자는 그 사실을 알 수 없다.

    상태는 코드로 낸다(`file_state` 와 같은 규약) — 사람이 읽을 문구는 화면이 정한다.
    """
    from app.users.models import User

    live_row = _create(client, admin, people["live"]).json()
    target = db.get(User, people["live"])
    target.archived_at = utcnow()
    target.active = False
    db.commit()

    items = client.get("/api/admin/ai-quotas").json()["items"]
    listed = next(i for i in items if i["id"] == live_row["id"])

    assert listed["user_state"] == "archived"
    assert listed["user_name"] == "일하는사람", "상태를 실으면서 이름을 잃으면 안 된다"


def test_a_live_target_is_listed_as_active(client, admin, people):
    """반례 — 살아 있는 계정의 상한은 그대로 `active` 다(전부 닫혔다고 말하지 않는다)."""
    row = _create(client, admin, people["live"]).json()

    items = client.get("/api/admin/ai-quotas").json()["items"]
    listed = next(i for i in items if i["id"] == row["id"])

    assert listed["user_state"] == "active"


def test_the_global_quota_row_has_no_target_state(client, admin):
    """전역 상한에는 대상 계정이 없다 — 모르는 것을 지어내지 않는다."""
    created = client.post(
        "/api/admin/ai-quotas",
        json={"scope_type": "global", "period": "day", "max_calls": 100},
        headers={"X-CSRF-Token": admin},
    )
    assert created.status_code == 201, created.text

    items = client.get("/api/admin/ai-quotas").json()["items"]
    listed = next(i for i in items if i["id"] == created.json()["id"])

    assert listed["user_state"] is None


# ── 후보 목록과 거절 규칙은 **같은 축**을 써야 한다 (R5-02) ────────────────────
#
# 폼의 사람 후보는 `GET /api/admin/people` 에서 온다. 그 목록이 비활성 계정을 실으면서
# 저장은 422 로 거절하면, 폼은 **반드시 실패하는 선택지**를 권한 셈이 된다 — 보관 계정을
# 후보에서 뺀 이유(`registry/shared.js`)와 같은 사건이 비활성 계정에서 그대로 남아 있었다.


def test_the_people_lookup_can_hide_exactly_what_the_quota_form_would_refuse(
    client, admin, people
):
    """`include_archived=false&include_inactive=false` 가 거절 대상과 같은 집합을 뺀다."""
    body = client.get(
        "/api/admin/people",
        params={"include_archived": "false", "include_inactive": "false"},
    ).json()
    offered = {item["id"] for item in body["items"]}

    assert people["live"] in offered, "살아 있는 계정까지 후보에서 사라지면 폼이 죽는다"
    for key in ("archived", "paused"):
        assert people[key] not in offered, (
            f"저장이 422 로 거절할 계정을 후보로 권하고 있다: {key}"
        )
        assert _create(client, admin, people[key]).status_code == 422


def test_the_default_people_lookup_still_lists_them(client, admin, people):
    """반례 — 기본 목록은 예전 그대로다. 감사 로그의 행위자 필터는 닫힌 계정도 골라야 한다."""
    offered = {
        item["id"] for item in client.get("/api/admin/people").json()["items"]
    }

    for key in ("live", "archived", "paused"):
        assert people[key] in offered
