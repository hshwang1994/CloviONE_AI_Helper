"""티켓 상태가 바뀌면 누가 알림을 받는가 (계획 3.4, D-513).

예전에는 상태 변경 알림이 작업 보드의 카드 이동에만 붙어 있어서, 목록이나 상세에서 상태를
바꾸면 아무도 몰랐다. 이제 상태를 바꾸는 모든 길이 `update_ticket` 을 지나고 알림도 거기서
한 번 나간다. 여기서 못박는 것:

  * 편집 경로(PATCH)도 관찰자와 담당자에게 한 통씩 보낸다.
  * 보드 이동은 사람마다 정확히 한 통, 상태 활동도 한 줄이다(예전에는 두 줄이었다).
  * 요청자는 완료나 취소로 끝날 때만 결과 알림(`ticket_resolved`)을 받는다. 관찰자이기도
    하면 결과 알림 한 통만 받는다.
  * 바꾼 사람 자신은 받지 않는다. 상태가 그대로면 아무도 받지 않는다.
  * 요청자를 모르는 티켓(옛 소스에서 옮겨 온 티켓)은 결과 알림이 없다.
  * 제품에서 만든 티켓은 만든 사람을 요청자로 적는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.models_base import join_names
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.work.models import ACT_STATUS, TicketActivity, TicketWatcher
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

PAGE = "page-status-notice"
NID_BOB = "notion-status-bob"
CHANGED = "ticket_status_changed"
RESOLVED = "ticket_resolved"


@pytest.fixture()
def world(db, make_user, make_project) -> dict[str, str]:
    """바꾸는 사람(에이미), 담당자(밥), 관찰자(웬디), 요청자(리타), 상관없는 사람(제로)."""
    ids: dict[str, str] = {}
    for key, email, role, name in (
        ("amy", "status-amy@goodmit.co.kr", "system_admin", "에이미"),
        ("bob", "status-bob@goodmit.co.kr", "user", "밥"),
        ("wendy", "status-wendy@goodmit.co.kr", "user", "웬디"),
        ("rita", "status-rita@goodmit.co.kr", "user", "리타"),
        ("zero", "status-zero@goodmit.co.kr", "user", "제로"),
    ):
        ids[key] = make_user(email=email, role=role, display_name=name).id
    db.add(UserNotionMapping(
        id="map-status-bob", user_id=ids["bob"], notion_user_id=NID_BOB,
        status=STATUS_VERIFIED, source=SOURCE_MANUAL,
    ))
    project = make_project(name="상태 알림", external_id="proj-status-notice")
    ticket = TicketCache(
        notion_page_id=PAGE, org_id=DEFAULT_ORG_ID, notion_ticket_number=31, seq=31,
        title="상태가 바뀌는 티켓", status="계획", due_date="2026-12-31",
        project_ids=join_names(["proj-status-notice"]), project_uid=project.id,
        project_link=PROJECT_LINK_OK, project_names=join_names(["상태 알림"]),
        assignee_notion_ids=join_names([NID_BOB]), requester_user_id=ids["rita"],
    )
    db.add(ticket)
    db.flush()
    db.add(TicketWatcher(ticket_id=ticket.id, user_id=ids["wendy"]))
    db.commit()
    ids["ticket"] = ticket.id
    ids["project"] = project.id
    return ids


def _login(client, email: str) -> str:
    response = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _patch(client, csrf: str, body: dict):
    return client.patch(f"/api/tickets/{PAGE}", json=body, headers={"X-CSRF-Token": csrf})


def _received(db, user_id: str) -> dict[str, int]:
    """이 사람이 받은 알림을 유형별로 센다."""
    db.expire_all()
    from app.notifications.models import Notification

    rows = db.execute(
        select(Notification.type, func.count()).where(Notification.user_id == user_id)
        .group_by(Notification.type)
    ).all()
    return {type_: count for type_, count in rows}


def _watch(db, ticket_id: str, user_id: str) -> None:
    db.add(TicketWatcher(ticket_id=ticket_id, user_id=user_id))
    db.commit()


# ── 편집 경로 ────────────────────────────────────────────────────────────────

def test_editing_the_status_notifies_watchers_and_assignees_once_each(client, db, world):
    csrf = _login(client, "status-amy@goodmit.co.kr")
    response = _patch(client, csrf, {"status": "진행"})
    assert response.status_code == 200, response.text

    assert _received(db, world["bob"]) == {CHANGED: 1}, "담당자가 편집 경로의 상태 변경을 못 받았다"
    assert _received(db, world["wendy"]) == {CHANGED: 1}, "관찰자가 편집 경로의 상태 변경을 못 받았다"
    assert _received(db, world["rita"]) == {}, "끝나지 않았는데 요청자에게 알림이 갔다"
    assert _received(db, world["zero"]) == {}
    assert _received(db, world["amy"]) == {}, "바꾼 사람에게 알림이 갔다"


def test_the_title_names_the_new_status_with_its_label(client, db, world):
    from app.notifications.models import Notification

    csrf = _login(client, "status-amy@goodmit.co.kr")
    assert _patch(client, csrf, {"status": "진행"}).status_code == 200
    db.expire_all()
    row = db.execute(select(Notification).where(Notification.user_id == world["wendy"])).scalar_one()
    assert row.title.endswith("상태 변경: 진행 중"), row.title
    assert row.related_object_type == "ticket" and row.related_object_id == PAGE


@pytest.mark.parametrize("closing", ["완료", "취소"])
def test_closing_sends_the_requester_one_result_notice(client, db, world, closing):
    csrf = _login(client, "status-amy@goodmit.co.kr")
    assert _patch(client, csrf, {"status": closing}).status_code == 200

    assert _received(db, world["rita"]) == {RESOLVED: 1}, "요청자가 결과를 못 받았다"
    assert _received(db, world["bob"]) == {CHANGED: 1}
    assert _received(db, world["wendy"]) == {CHANGED: 1}


def test_a_requester_who_also_watches_gets_only_the_result(client, db, world):
    _watch(db, world["ticket"], world["rita"])
    csrf = _login(client, "status-amy@goodmit.co.kr")
    assert _patch(client, csrf, {"status": "완료"}).status_code == 200
    assert _received(db, world["rita"]) == {RESOLVED: 1}, "요청자 겸 관찰자에게 두 통이 갔다"


def test_the_actor_is_never_notified_even_as_a_watcher(client, db, world):
    _watch(db, world["ticket"], world["amy"])
    csrf = _login(client, "status-amy@goodmit.co.kr")
    assert _patch(client, csrf, {"status": "검증"}).status_code == 200
    assert _received(db, world["amy"]) == {}


def test_the_same_status_or_another_field_sends_nothing(client, db, world):
    csrf = _login(client, "status-amy@goodmit.co.kr")
    assert _patch(client, csrf, {"status": "계획"}).status_code == 200
    assert _patch(client, csrf, {"title": "제목만 바꾼다"}).status_code == 200
    for who in ("bob", "wendy", "rita"):
        assert _received(db, world[who]) == {}, who


def test_a_ticket_without_a_requester_sends_no_result(client, db, world):
    row = db.get(TicketCache, world["ticket"])
    row.requester_user_id = None
    db.commit()
    csrf = _login(client, "status-amy@goodmit.co.kr")
    assert _patch(client, csrf, {"status": "완료"}).status_code == 200
    assert _received(db, world["rita"]) == {}
    assert _received(db, world["wendy"]) == {CHANGED: 1}


# ── 보드 이동 ────────────────────────────────────────────────────────────────

def test_a_board_move_sends_one_notice_per_person_and_one_status_activity(client, db, world):
    csrf = _login(client, "status-amy@goodmit.co.kr")
    response = client.post(
        f"/api/work/board/{world['ticket']}/move",
        json={"to_status": "완료", "base_version": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text

    assert _received(db, world["wendy"]) == {CHANGED: 1}, "보드 이동이 관찰자에게 두 통을 보냈다"
    assert _received(db, world["bob"]) == {CHANGED: 1}, "보드 이동이 담당자를 빠뜨렸다"
    assert _received(db, world["rita"]) == {RESOLVED: 1}
    activities = db.execute(
        select(func.count()).select_from(TicketActivity).where(
            TicketActivity.ticket_id == world["ticket"], TicketActivity.kind == ACT_STATUS,
        )
    ).scalar_one()
    assert activities == 1, "카드 이동 한 번에 상태 활동이 두 줄 남았다"


# ── 요청자 ───────────────────────────────────────────────────────────────────

def test_creating_a_ticket_records_the_creator_as_requester(client, db, world):
    csrf = _login(client, "status-amy@goodmit.co.kr")
    response = client.post(
        "/api/tickets",
        json={"title": "요청자가 적히는 티켓", "project_id": world["project"], "est_wd": 1,
              "due_date": "2026-12-31"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code in (200, 201), response.text
    db.expire_all()
    row = db.execute(
        select(TicketCache).where(TicketCache.title == "요청자가 적히는 티켓")
    ).scalar_one()
    assert row.requester_user_id == world["amy"], "만든 사람을 요청자로 적지 않았다"
