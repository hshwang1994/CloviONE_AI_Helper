"""티켓 배정 알림 (X9 + §E-6 N2).

감사 확인: **누가 나에게 티켓을 배정해도 앱이 안 알려 준다.** 담당자는 `/my-tickets` 를
스스로 열어야 자기 일이 늘어난 걸 안다. 배정은 이 저장소에서 가장 자주 일어나는 협업
사건이라, 여기가 조용하면 알림 기능 전체가 "쓸모없다"는 인상을 준다.

여기서 못박는 네 가지:

  * **내가 한 일은 나에게 안 온다.** 자기가 자기에게 배정하면 알림이 0건이다. 이걸
    빠뜨리면 배지가 늘 켜져 있게 되고, 사람들은 곧 배지를 무시한다.
  * **바뀐 사람에게만 간다.** 담당자 교체(A 를 빼고 B 를 넣기)에서 그대로 남아 있던
    공동 담당자는 아무 일도 겪지 않았다 - 그 사람에게 보내면 그건 소음이다.
  * **딥링크가 실제 화면을 가리킨다.** `/tickets/<page_id>` 는 티켓 상세를 실제로 여는
    라우트다(frontend/src/app/UserRoutes.jsx). 목록으로 보내면 대상을 다시 찾아야 한다.
  * **방해금지가 걸리면 조용하다.** 알림 행은 평소처럼 쌓이되 배지 숫자만 0 이 된다
    (app/profiles/prefs.py 모듈 docstring - 삼키면 그 시간의 일을 영영 모른다).
"""

from __future__ import annotations

import pytest

from app.core.models_base import join_names
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

PAGE_FREE = "page-free"
PAGE_BOB = "page-bob"

NID = {"amy": "notion-amy", "bob": "notion-bob", "cho": "notion-cho"}


@pytest.fixture()
def people(db, make_user, make_project) -> dict[str, str]:
    """에이미(관리자, 배정하는 사람) + 밥/초(담당자 후보). 셋 다 담당자 매핑이 확인됨."""
    made: dict[str, str] = {}
    for key, email, role, name in (
        ("amy", "amy@goodmit.co.kr", "system_admin", "에이미"),
        ("bob", "bob@goodmit.co.kr", "user", "밥"),
        ("cho", "cho@goodmit.co.kr", "user", "초"),
    ):
        user = make_user(email=email, role=role, display_name=name)
        db.add(UserNotionMapping(
            id=f"map-{key}", user_id=user.id, notion_user_id=NID[key],
            status=STATUS_VERIFIED, source=SOURCE_MANUAL,
        ))
        made[key] = user.id
    db.commit()
    # 티켓 생성은 **Portal 프로젝트 id** 를 받는다(0060) — 외부 relation id 가 아니다.
    # 조직 공통 프로젝트로 둬서 이 파일의 사용자 전원이 쓸 수 있게 한다.
    project = make_project(name="알파", external_id="proj-1")
    made["project_id"] = project.id
    return made


@pytest.fixture()
def tickets(db, people) -> None:
    """미할당 한 건 + 밥이 이미 맡고 있는 한 건. 티켓의 정본은 자체 DB(`tickets`)다.

    두 번째 건이 중요하다 - 담당자 '교체'는 빠지는 사람과 들어오는 사람이 동시에 생기는
    유일한 경우라, 수신자 규칙이 실제로 갈라지는 표본이다.
    """
    for page_id, tid, title, due, holders in (
        (PAGE_FREE, 901, "미할당 티켓", "2026-09-01", []),
        (PAGE_BOB, 902, "밥이 맡은 티켓", "2026-09-02", [NID["bob"]]),
    ):
        db.add(TicketCache(
            notion_page_id=page_id, org_id=DEFAULT_ORG_ID, notion_ticket_number=tid,
            title=title, status="진행", due_date=due,
            project_ids=join_names(["proj-1"]), project_uid=people["project_id"],
            project_link=PROJECT_LINK_OK, project_names=join_names(["알파"]),
            assignee_notion_ids=join_names(holders),
        ))
    db.commit()


def _login(client, email: str) -> str:
    response = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _notifications(app, user_id: str, kind: str = "ticket_assigned") -> list:
    from app.notifications.models import Notification

    with app.state.session_factory() as session:
        return list(
            session.query(Notification)
            .filter(Notification.user_id == user_id, Notification.type == kind)
            .order_by(Notification.created_at)
            .all()
        )


def _assign(client, csrf, page_id: str, user_ids: list[str]):
    return client.patch(
        f"/api/tickets/{page_id}",
        json={"assignee_user_ids": user_ids},
        headers={"X-CSRF-Token": csrf},
    )


# ── 기본: 배정하면 그 사람이 안다 ─────────────────────────────────────────────

def test_assigning_a_ticket_to_someone_notifies_them(client, app, people, tickets):
    csrf = _login(client, "amy@goodmit.co.kr")
    response = _assign(client, csrf, PAGE_FREE, [people["bob"]])
    assert response.status_code == 200, response.text

    rows = _notifications(app, people["bob"])
    assert len(rows) == 1, "티켓을 배정받았는데 알림이 없다"
    assert "902" not in rows[0].title, "다른 티켓의 알림이 왔다"
    assert "901" in rows[0].title, f"어느 티켓인지 알 수 없는 제목: {rows[0].title}"


def test_creating_a_ticket_for_someone_notifies_them(client, app, people, tickets):
    """생성 시 배정도 배정이다 - 여기만 빠지면 '남이 나에게 일을 만든' 경우가 조용해진다."""
    csrf = _login(client, "amy@goodmit.co.kr")
    response = client.post(
        "/api/tickets",
        json={"title": "새로 만든 티켓", "project_id": people["project_id"],
              "assignee_user_ids": [people["cho"]]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code in (200, 201), response.text
    assert len(_notifications(app, people["cho"])) == 1, "생성과 동시에 배정받은 사람이 모른다"


# ── 내가 한 일은 나에게 안 온다 ───────────────────────────────────────────────

def test_assigning_a_ticket_to_myself_notifies_nobody(client, app, people, tickets):
    """자기가 자기에게 배정하면 알림이 없어야 한다 - 배지가 늘 켜져 있게 된다."""
    csrf = _login(client, "bob@goodmit.co.kr")
    response = _assign(client, csrf, PAGE_FREE, [people["bob"]])
    assert response.status_code == 200, response.text

    assert _notifications(app, people["bob"]) == [], "내가 나에게 한 배정이 나에게 알림으로 왔다"


def test_claiming_a_ticket_notifies_nobody(client, app, people, tickets):
    """'내가 맡기' 버튼도 같은 규칙이다 - 다른 경로로 들어와도 자기 알림은 없다."""
    csrf = _login(client, "cho@goodmit.co.kr")
    response = client.post(
        f"/api/tickets/{PAGE_FREE}/claim", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.text

    assert _notifications(app, people["cho"]) == [], "내가 맡은 티켓이 나에게 알림으로 왔다"


# ── 여러 명이 바뀔 때: 새로 들어온 사람에게만 ─────────────────────────────────

def test_only_the_newly_added_assignee_hears_about_it(client, app, people, tickets):
    """담당자를 밥에서 밥+초로 늘린다. 그대로 남은 밥에게는 아무 일도 없었다."""
    csrf = _login(client, "amy@goodmit.co.kr")
    response = _assign(client, csrf, PAGE_BOB, [people["bob"], people["cho"]])
    assert response.status_code == 200, response.text

    assert len(_notifications(app, people["cho"])) == 1, "새 공동 담당자가 모른다"
    assert _notifications(app, people["bob"]) == [], "그대로 남은 담당자에게 소음이 갔다"


def test_a_swap_notifies_the_incoming_assignee_only(client, app, people, tickets):
    """교체(밥 → 초). 들어온 사람에게만 간다.

    빠진 사람에게 보내지 않는 이유는 구현 쪽 `_notify_assignees_added` 주석에 적었다 -
    요약하면 '해제'는 배정과 다른 사건이고, 한 유형에 두 뜻을 섞으면 사용자가 배정 알림을
    껐을 때 해제 통보까지 같이 꺼진다.
    """
    csrf = _login(client, "amy@goodmit.co.kr")
    response = _assign(client, csrf, PAGE_BOB, [people["cho"]])
    assert response.status_code == 200, response.text

    assert len(_notifications(app, people["cho"])) == 1, "새 담당자가 모른다"
    assert _notifications(app, people["bob"]) == [], "빠진 사람에게 배정 알림이 갔다"


def test_a_no_op_edit_notifies_nobody(client, app, people, tickets):
    """같은 담당자를 다시 저장해도 아무 일도 안 일어난다 - 저장 버튼이 배지를 만들면 안 된다."""
    csrf = _login(client, "amy@goodmit.co.kr")
    assert _assign(client, csrf, PAGE_BOB, [people["bob"]]).status_code == 200

    assert _notifications(app, people["bob"]) == [], "안 바뀐 배정이 알림을 만들었다"


# ── 딥링크 ────────────────────────────────────────────────────────────────────

def test_the_deep_link_points_at_the_ticket_screen(client, app, people, tickets):
    csrf = _login(client, "amy@goodmit.co.kr")
    assert _assign(client, csrf, PAGE_FREE, [people["bob"]]).status_code == 200

    _login(client, "bob@goodmit.co.kr")
    items = client.get("/api/notifications?type=ticket_assigned").json()["items"]
    assert len(items) == 1
    assert items[0]["related_object_type"] == "ticket"
    assert items[0]["related_object_id"] == PAGE_FREE
    assert items[0]["related_route"] == f"/tickets/{PAGE_FREE}", "딥링크가 티켓 상세를 안 가리킨다"


# ── 방해금지 / 유형별 끄기 ────────────────────────────────────────────────────

def test_do_not_disturb_silences_the_badge_but_keeps_the_notification(
    client, app, people, tickets
):
    """조용해지는 것은 배지뿐이다. 삼키면 그 시간에 배정받은 티켓을 영영 모른다."""
    bob_csrf = _login(client, "bob@goodmit.co.kr")
    assert client.patch(
        "/api/me/preferences", json={"dnd_enabled": True},
        headers={"X-CSRF-Token": bob_csrf},
    ).status_code == 200

    amy_csrf = _login(client, "amy@goodmit.co.kr")
    assert _assign(client, amy_csrf, PAGE_FREE, [people["bob"]]).status_code == 200

    _login(client, "bob@goodmit.co.kr")
    badge = client.get("/api/notifications/unread-count").json()
    assert badge["quiet"] is True
    assert badge["badge"] == 0, "방해금지 중인데 배지가 켜졌다"
    assert badge["by_type"] == {}, "방해금지 중인데 사이드바 배지가 켜졌다"
    assert badge["unread"] >= 1, "방해금지가 알림 자체를 삼켰다"
    assert len(_notifications(app, people["bob"])) == 1


def test_muting_the_type_keeps_it_out_of_the_badge(client, app, people, tickets):
    """유형별 끄기를 지난다 - 끈 유형은 배지에서 빠지고 목록에는 muted 로 남는다."""
    bob_csrf = _login(client, "bob@goodmit.co.kr")
    response = client.patch(
        "/api/me/preferences", json={"muted_types": ["ticket_assigned"]},
        headers={"X-CSRF-Token": bob_csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()["notifications"]["muted_types"] == ["ticket_assigned"], (
        "새 유형이 설정 레지스트리에 없어 뮤트가 저장되지 않았다"
    )

    amy_csrf = _login(client, "amy@goodmit.co.kr")
    assert _assign(client, amy_csrf, PAGE_FREE, [people["bob"]]).status_code == 200

    _login(client, "bob@goodmit.co.kr")
    badge = client.get("/api/notifications/unread-count").json()
    assert "ticket_assigned" not in badge["by_type"], "끈 유형이 배지에 잡힌다"
    items = client.get("/api/notifications?type=ticket_assigned").json()["items"]
    assert len(items) == 1 and items[0]["muted"] is True, "끈 유형이 목록에서도 사라졌다"


# ── 알림이 본 작업을 막지 않는다 ──────────────────────────────────────────────

def test_a_broken_notifier_does_not_block_the_assignment(
    client, app, people, tickets, monkeypatch
):
    """알림 표 하나가 티켓 편집을 멈추면 안 된다. 다만 조용히 삼키지도 않는다(로그)."""
    import app.notifications.service as noti

    def _boom(*args, **kwargs):
        raise RuntimeError("알림 저장 실패")

    monkeypatch.setattr(noti, "notify_user", _boom)

    csrf = _login(client, "amy@goodmit.co.kr")
    response = _assign(client, csrf, PAGE_FREE, [people["bob"]])
    assert response.status_code == 200, response.text
    assert response.json()["ticket"]["assignee_user_ids"] == [people["bob"]]
