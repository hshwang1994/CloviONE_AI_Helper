"""게시판 알림의 두 빈틈 (교차기능 감사, THREAD B).

1. **board_comment 알림이 딥링크가 없다.** `app/notifications/destinations.py` 의
   `RELATED_DESTINATIONS` 표는 ticket/document 댓글 알림이 눌러도 아무 데도 안 가던 것을
   고치며 만들어졌다(그 표의 주석 참고) — 그런데 게시판 댓글(`related=("board_post", ...)`)
   자체는 표에 없다. `/board/:id`(BoardPost.jsx)가 이미 그 id 를 그대로 소비하므로(표
   docstring 의 첫 번째 규칙을 만족) 이건 의도적 누락이 아니라 ticket/document 와 같은
   자리에서 빠뜨린 것으로 보인다.

2. **아이디어 상태 전환이 제안자에게 알리지 않는다.** `board/service.py::change_idea_status`
   는 댓글 알림(`_notify_post_comment`)과 달리 `notify_user` 를 한 번도 부르지 않는다.
   제안자는 자기 제안이 검토중/진행/완료/보류로 바뀐 것을 `/ideas` 를 스스로 열어야만 안다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _unread(app, user_id, kind):
    from app.notifications.models import Notification

    with app.state.session_factory() as db:
        return (
            db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.type == kind)
            .count()
        )


def test_a_board_comment_notification_deep_links_to_the_post(client, login_as, app, db):
    """board_comment 알림을 눌렀을 때 그 글로 가야 한다(ticket_comment/document_comment 와
    같은 계약, tests/integration/test_document_comments.py::
    test_the_notification_deep_links_to_the_document 참고)."""
    from app.board.models import Post

    owner = login_as("user", email="bg-owner@goodmit.co.kr")
    r = client.post(
        "/api/board/posts",
        json={"category": "자유", "title": "딥링크 확인용 글", "body": "b"},
        headers={"X-CSRF-Token": owner},
    )
    assert r.status_code == 200, r.text
    post_id = r.json()["post"]["id"]

    other = login_as("user", email="bg-other@goodmit.co.kr")
    r = client.post(
        f"/api/board/posts/{post_id}/comments", json={"body": "댓글"},
        headers={"X-CSRF-Token": other},
    )
    assert r.status_code in (200, 201), r.text

    login_as("user", email="bg-owner@goodmit.co.kr")
    items = client.get("/api/notifications?type=board_comment").json()["items"]
    assert len(items) == 1
    assert items[0]["related_object_type"] == "board_post"
    assert items[0]["related_object_id"] == post_id
    assert items[0]["related_route"] == f"/board/{post_id}", (
        "게시판 댓글 알림 딥링크가 그 글을 안 가리킨다 "
        f"(related_route={items[0]['related_route']!r})"
    )


def test_moving_an_idea_along_notifies_its_author(client, login_as, app, db):
    """제안자는 자기 제안의 상태가 바뀐 것을 알아야 한다(댓글 알림과 같은 원칙, N2)."""
    author = login_as("user", email="bg-author@goodmit.co.kr")
    r = client.post(
        "/api/board/posts",
        json={"kind": "idea", "category": "기능", "title": "상태 알림 확인용 제안", "body": "b"},
        headers={"X-CSRF-Token": author},
    )
    assert r.status_code == 200, r.text
    idea_id = r.json()["post"]["id"]
    from app.users.service import get_user_by_email
    author_user = get_user_by_email(db, "bg-author@goodmit.co.kr")

    op = login_as("operator", email="bg-op@goodmit.co.kr")
    r = client.post(
        f"/api/board/posts/{idea_id}/status", json={"status": "검토중"},
        headers={"X-CSRF-Token": op},
    )
    assert r.status_code == 200, r.text

    assert _unread(app, author_user.id, "idea_status_changed") == 1, (
        "제안 상태가 바뀌었는데 제안자에게 알림이 없다"
    )


def test_an_operator_moving_their_own_idea_does_not_self_notify(client, login_as, app, db):
    """내가 낸 제안을 내가(운영자 권한으로) 진행시켜도 나에게는 알리지 않는다(배지가 늘
    켜져 있게 되는 것을 피한다 — 다른 알림들과 같은 원칙)."""
    op = login_as("operator", email="bg-op-self@goodmit.co.kr")
    r = client.post(
        "/api/board/posts",
        json={"kind": "idea", "category": "기능", "title": "내가 낸 제안", "body": "b"},
        headers={"X-CSRF-Token": op},
    )
    assert r.status_code == 200, r.text
    idea_id = r.json()["post"]["id"]
    from app.users.service import get_user_by_email
    op_user = get_user_by_email(db, "bg-op-self@goodmit.co.kr")

    r = client.post(
        f"/api/board/posts/{idea_id}/status", json={"status": "검토중"},
        headers={"X-CSRF-Token": op},
    )
    assert r.status_code == 200, r.text

    assert _unread(app, op_user.id, "idea_status_changed") == 0, (
        "내가 바꾼 내 제안 상태가 나에게 알림으로 왔다"
    )
