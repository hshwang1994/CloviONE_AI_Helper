"""티켓에 댓글이 달리면 담당자가 **실제로 알림을 받는다** (S18 · W8).

## 왜 아무도 못 봤나

`_notify_ticket_comment` 는 자기 실패를 삼킨다 — 그렇게 설계했다. 알림 하나 때문에 댓글
저장을 실패시키지 않는 것이 옳다. 그런데 그 «옳은 관용» 이 **함수 전체가 죽어 있어도**
바깥에서는 200 으로만 보이게 만든다. 실제로 그 안의 `split_names` 가 임포트되지 않아
`NameError` 가 났고, 댓글이 전부 정상으로 저장되는 동안 **담당자 알림은 한 건도 안 나갔다**.
로그에만 남고 응답에는 흔적이 없으니, 응답 코드를 보는 어떤 시험도 이것을 못 잡는다.

S18 의 실브라우저 Flow(FF-0093)가 서버 로그에서 그 예외를 보고 잡았다.

## 그래서 여기서 무엇을 고정하나

**알림 행이 생겼는가**를 본다. 그리고 반례를 함께 둔다 — 자기 댓글에는 알림이 안 가야 하고,
담당자가 없으면 아무 일도 없어야 한다. 그것이 없으면 「무조건 한 건 만든다」도 통과한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.notifications.models import Notification

pytestmark = pytest.mark.integration


def _ticket_comment_notifications(db, user_id: str) -> list:
    return list(db.execute(
        select(Notification).where(Notification.user_id == user_id,
                                   Notification.type == "ticket_comment")
    ).scalars().all())


def _post(client, csrf, path, body):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf})


def test_comment_notifies_the_assignee(client, login_as, db, make_ticket, make_user,
                                       portal_project):
    """담당자가 있는 티켓에 **다른 사람**이 댓글을 달면 담당자에게 알림이 간다."""
    assignee = make_user(email="comment-assignee@goodmit.co.kr", role="user",
                         display_name="이서연")
    ticket = make_ticket(title="댓글 알림 티켓", project=portal_project,
                         assignees=[assignee.id])

    csrf = login_as("system_admin")
    res = _post(client, csrf, "/api/tickets/%s/comments" % ticket.id,
                {"body": "확인 부탁드립니다."})
    assert res.status_code == 200, res.text[:400]

    got = _ticket_comment_notifications(db, assignee.id)
    assert len(got) == 1, (
        "댓글은 저장됐는데 담당자 알림이 %d건이다 — 알림 경로가 조용히 죽어 있다" % len(got))
    assert ticket.title in (got[0].body or "")


def test_own_comment_does_not_notify_self(client, login_as, db, make_ticket, make_user,
                                          portal_project):
    """반례 ① — 내가 단 댓글로 나에게 알림이 오면 안 된다."""
    me = make_user(email="comment-self@goodmit.co.kr", role="system_admin",
                   display_name="본인")
    ticket = make_ticket(title="자기 댓글 티켓", project=portal_project,
                         assignees=[me.id])

    csrf = login_as("system_admin", email=me.email)
    res = _post(client, csrf, "/api/tickets/%s/comments" % ticket.id,
                {"body": "내가 남기는 메모."})
    assert res.status_code == 200, res.text[:400]
    assert _ticket_comment_notifications(db, me.id) == []


def test_no_assignee_means_no_notification(client, login_as, db, make_ticket, make_user,
                                           portal_project):
    """반례 ② — 담당자가 없으면 아무에게도 안 간다(그리고 댓글은 그대로 저장된다)."""
    watcher = make_user(email="comment-watcher@goodmit.co.kr", role="user",
                        display_name="박민준")
    ticket = make_ticket(title="담당자 없는 티켓", project=portal_project, assignees=[])

    csrf = login_as("system_admin")
    res = _post(client, csrf, "/api/tickets/%s/comments" % ticket.id,
                {"body": "담당자가 없는 티켓입니다."})
    assert res.status_code == 200, res.text[:400]
    assert _ticket_comment_notifications(db, watcher.id) == []
