"""티켓·게시판에도 알림이 간다 (N2).

`app/tickets/` 와 `app/board/` 전체에 `notify` 문자열이 **0건**이었다. 만들어지는 알림
14종이 전부 관리·운영 이벤트 아니면 채팅이고, **사람이 실제로 협업하는 두 축이 통째로
조용했다** — 담당자는 `/my-tickets` 를 스스로 열어야 논의가 있었다는 걸 알았다.

세 가지를 지킨다:
  * 내가 쓴 것을 **나에게는** 안 보낸다(배지가 늘 켜져 있게 된다).
  * 답글은 **부모 댓글 작성자에게도** 간다(답글은 그 사람에게 하는 말이다).
  * 알림이 실패해도 **댓글은 남는다**(알림은 본 작업보다 약한 관심사다).
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


def test_a_comment_on_my_post_notifies_me(client, login_as, make_user, app, db):
    from app.board.models import Post

    owner = make_user("bn-owner@goodmit.co.kr", role="user", display_name="글쓴이")
    db.add(Post(title="내 글", body="b", category="자유", author_user_id=owner.id))
    db.commit()
    post_id = db.query(Post).filter(Post.author_user_id == owner.id).one().id

    csrf = login_as("user", email="bn-other@goodmit.co.kr")
    r = client.post(f"/api/board/posts/{post_id}/comments", json={"body": "댓글"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code in (200, 201), r.text

    assert _unread(app, owner.id, "board_comment") == 1, "내 글에 댓글이 달렸는데 알림이 없다"


def test_my_own_comment_does_not_notify_me(client, login_as, make_user, app, db):
    """내가 쓴 것을 나에게 알리면 배지가 늘 켜져 있다."""
    from app.board.models import Post

    csrf = login_as("user", email="bn-solo@goodmit.co.kr")
    me = db.query(type(make_user("tmp-x@goodmit.co.kr"))).filter_by(email="bn-solo@goodmit.co.kr").one()
    db.add(Post(title="내 글", body="b", category="자유", author_user_id=me.id))
    db.commit()
    post_id = db.query(Post).filter(Post.author_user_id == me.id).one().id

    client.post(f"/api/board/posts/{post_id}/comments", json={"body": "내 댓글"},
                headers={"X-CSRF-Token": csrf})
    assert _unread(app, me.id, "board_comment") == 0, "내 댓글이 나에게 알림으로 왔다"


def test_a_reply_also_notifies_the_parent_comment_author(
    client, login_as, make_user, app, db
):
    """답글은 **그 사람에게 하는 말**이다 — 글쓴이만 알리면 정작 대상이 모른다."""
    from app.board.models import Post

    owner = make_user("bn-o2@goodmit.co.kr", role="user", display_name="글쓴이")
    commenter = make_user("bn-c2@goodmit.co.kr", role="user", display_name="댓글쓴이")
    db.add(Post(title="글", body="b", category="자유", author_user_id=owner.id))
    db.commit()
    post_id = db.query(Post).filter(Post.author_user_id == owner.id).one().id
    db.commit()  # 스냅샷을 새로 뜬다 — 안 그러면 아래 login_as(→create_user)가 이 세션으로
    # 쓸 때 그 사이 client.post()가 커밋한 것들과 스냅샷이 어긋나 "database is locked"

    csrf = login_as("user", email="bn-c2@goodmit.co.kr")
    r1 = client.post(f"/api/board/posts/{post_id}/comments", json={"body": "첫 댓글"},
                     headers={"X-CSRF-Token": csrf})
    assert r1.status_code in (200, 201), r1.text
    # 응답이 갱신된 글만 돌려주므로 댓글 id 는 저장소에서 읽는다.
    from app.board.models import Comment

    with app.state.session_factory() as s2:
        parent_id = s2.query(Comment).filter(Comment.post_id == post_id).one().id

    csrf = login_as("user", email="bn-r2@goodmit.co.kr")
    r = client.post(f"/api/board/posts/{post_id}/comments",
                    json={"body": "답글", "parent_comment_id": parent_id},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code in (200, 201), r.text

    assert _unread(app, commenter.id, "board_comment") == 1, "부모 댓글 작성자가 답글을 모른다"
    assert _unread(app, owner.id, "board_comment") == 2, "글쓴이도 알아야 한다"
