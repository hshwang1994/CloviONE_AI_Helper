"""게시판 조직 격리 — **목록만 가려서는 아무 의미가 없다** (§0-A 3순위 IDOR).

`list_posts` 는 1순위 #4 에서 `org_id` 를 받게 됐는데, 같은 판정이 **단건·댓글·첨부·쓰기**
에는 없었다. 그 경로들은 전부 id 를 직접 받는다 — 즉 목록에서 가린 글이 id 하나로

  * 읽히고(상세·댓글·첨부 바이트),
  * **고쳐지고 지워졌다**(운영자군이면 남의 회사 글을 그대로 수정·삭제·고정).

`two_orgs` 가 있어야 이 판정이 검증 가능해진다: 조직이 하나뿐이면 `WHERE org_id = :org`
는 한 행도 안 걸러 **초록불이 아무것도 증명하지 못한다**(PLAN4).

**403 이 아니라 404** — 403 은 그 글이 존재한다는 사실을 알려 준다(저장소 규칙).

그리고 이 파일의 절반은 **오탐 방지**다: 게시판은 조직 축만 건다. 자유게시판은 **사내**
공지판이라 부서로 좁히면 그 성격이 사라진다 — 같은 조직 다른 부서 사람은 여전히 다 된다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _seed_org_a_post(client, login_as):
    """조직 A 사람이 글 + 첨부 + 댓글을 만든다. (A 사람의 org_id 는 DEFAULT_ORG_ID 다.)"""
    csrf = login_as("user", email="orga@goodmit.co.kr")
    post = client.post(
        "/api/board/posts",
        json={"category": "공지", "title": "A조직 내부 공지", "body": "우리 회사만 볼 내용"},
        headers={"X-CSRF-Token": csrf},
    )
    assert post.status_code == 200, post.text
    post_id = post.json()["post"]["id"]

    att = client.post(
        f"/api/board/posts/{post_id}/attachments",
        files={"file": ("사내자료.png", PNG, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert att.status_code == 200, att.text

    cm = client.post(
        f"/api/board/posts/{post_id}/comments",
        json={"body": "A조직 댓글"},
        headers={"X-CSRF-Token": csrf},
    )
    assert cm.status_code == 200, cm.text
    detail = cm.json()["post"]
    return {
        "post_id": post_id,
        "comment_id": detail["comments"][0]["id"],
        "attachment_url": att.json()["attachment"]["url"],
    }


def _login_org_b_moderator(client, login_as, two_orgs, db):
    """조직 B 사람을 **운영자군**으로 만들어 로그인한다.

    평사원으로 확인하면 쓰기 경로가 소유권 검사(403)에 먼저 걸려 **조직 판정이 있는지
    없는지 구별되지 않는다.** 운영자군은 남의 글도 고칠 수 있으므로, 여기서 막는 것은
    오직 조직 판정뿐이다.
    """
    from app.core.authz import ROLE_OPERATOR

    two_orgs.user_b.role = ROLE_OPERATOR
    db.commit()
    return login_as("user", email="orgb@goodmit.co.kr")


def _read_post(app, post_id):
    from app.board.models import Post

    with app.state.session_factory() as s:
        return s.get(Post, post_id)


# ── 조직 밖은 없는 것으로 보여야 한다 ────────────────────────────────────────
def test_you_cannot_open_another_organizations_post(client, login_as, two_orgs, db):
    seeded = _seed_org_a_post(client, login_as)
    _login_org_b_moderator(client, login_as, two_orgs, db)

    r = client.get(f"/api/board/posts/{seeded['post_id']}")
    assert r.status_code == 404, (
        f"다른 조직 글이 id 하나로 열린다({r.status_code}) — 목록에서 가린 의미가 없다"
    )


def test_you_cannot_download_another_organizations_attachment(client, login_as, two_orgs, db):
    """첨부는 **부모 글을 통해** 판정한다.

    이미 '부모 글이 삭제됐으면 첨부도 서빙 안 한다' 는 판단이 이 자리에 있었다 —
    조직도 같은 자리에서 본다. 첨부는 사내 자료 바이트 그 자체라 여기가 새면 상세를
    막아도 소용이 없다.
    """
    seeded = _seed_org_a_post(client, login_as)
    _login_org_b_moderator(client, login_as, two_orgs, db)

    r = client.get(seeded["attachment_url"])
    assert r.status_code == 404, (
        f"다른 조직 첨부 바이트가 그대로 내려온다({r.status_code})"
    )


def test_you_cannot_read_or_write_comments_on_another_organizations_post(
    client, login_as, two_orgs, db
):
    """댓글 목록은 상세 응답에 실려 있다 — 상세가 막히면 목록도 막힌다.
    작성·수정·삭제는 각각 post_id / comment_id 를 직접 받으므로 따로 확인한다."""
    seeded = _seed_org_a_post(client, login_as)
    csrf = _login_org_b_moderator(client, login_as, two_orgs, db)
    headers = {"X-CSRF-Token": csrf}

    create = client.post(
        f"/api/board/posts/{seeded['post_id']}/comments",
        json={"body": "남의 회사 글에 댓글"},
        headers=headers,
    )
    assert create.status_code == 404, f"다른 조직 글에 댓글이 달린다: {create.status_code}"

    patch = client.patch(
        f"/api/board/comments/{seeded['comment_id']}",
        json={"body": "몰래 수정"},
        headers=headers,
    )
    assert patch.status_code == 404, f"다른 조직 댓글이 수정된다: {patch.status_code}"

    delete = client.delete(
        f"/api/board/comments/{seeded['comment_id']}", headers=headers
    )
    assert delete.status_code == 404, f"다른 조직 댓글이 삭제된다: {delete.status_code}"


def test_you_cannot_change_another_organizations_post(client, login_as, two_orgs, db, app):
    """**실제로 안 바뀌었는지**까지 본다 — 상태 코드만 보면 404 를 돌려주면서 저장은
    이미 끝난 구현도 통과한다."""
    seeded = _seed_org_a_post(client, login_as)
    csrf = _login_org_b_moderator(client, login_as, two_orgs, db)
    headers = {"X-CSRF-Token": csrf}
    post_id = seeded["post_id"]

    patch = client.patch(
        f"/api/board/posts/{post_id}",
        json={"title": "남의 회사 공지 변조"},
        headers=headers,
    )
    assert patch.status_code == 404, f"다른 조직 글이 수정된다: {patch.status_code}"
    assert _read_post(app, post_id).title == "A조직 내부 공지", "제목이 실제로 바뀌었다"

    pin = client.post(f"/api/board/posts/{post_id}/pin?pinned=true", headers=headers)
    assert pin.status_code == 404, f"다른 조직 글이 고정된다: {pin.status_code}"
    assert _read_post(app, post_id).is_pinned is False, "고정 상태가 실제로 바뀌었다"

    delete = client.delete(f"/api/board/posts/{post_id}", headers=headers)
    assert delete.status_code == 404, f"다른 조직 글이 삭제된다: {delete.status_code}"
    assert _read_post(app, post_id).deleted_at is None, "글이 실제로 삭제됐다"


def test_you_cannot_attach_or_react_to_another_organizations_post(
    client, login_as, two_orgs, db, app
):
    """업로드·반응도 post_id / target_id 를 직접 받는다 — 같은 문이다."""
    from app.board.repository import attachment_count

    seeded = _seed_org_a_post(client, login_as)
    csrf = _login_org_b_moderator(client, login_as, two_orgs, db)
    headers = {"X-CSRF-Token": csrf}
    post_id = seeded["post_id"]

    up = client.post(
        f"/api/board/posts/{post_id}/attachments",
        files={"file": ("침입.png", PNG, "image/png")},
        headers=headers,
    )
    assert up.status_code == 404, f"다른 조직 글에 파일이 올라간다: {up.status_code}"
    with app.state.session_factory() as s:
        assert attachment_count(s, post_id) == 1, "첨부가 실제로 추가됐다"

    react = client.post(
        "/api/board/reactions",
        json={"target_type": "post", "target_id": post_id, "emoji": "👍"},
        headers=headers,
    )
    assert react.status_code == 404, f"다른 조직 글에 반응이 달린다: {react.status_code}"

    react_c = client.post(
        "/api/board/reactions",
        json={"target_type": "comment", "target_id": seeded["comment_id"], "emoji": "👍"},
        headers=headers,
    )
    assert react_c.status_code == 404, f"다른 조직 댓글에 반응이 달린다: {react_c.status_code}"


# ── 오탐 방지: 조직 축만 건다(부서로 좁히면 안 된다) ─────────────────────────
def _make_org_a_teammate(make_user, db, email, *, role="user"):
    """같은 조직(A) **다른 부서** 사람. 자유게시판은 사내 공지판이라 부서는 축이 아니다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    other_team = Department(name="A팀2", org_id=DEFAULT_ORG_ID)
    db.add(other_team)
    db.flush()
    mate = make_user(email, role=role, display_name="A사람2")
    mate.org_id = DEFAULT_ORG_ID
    mate.department_id = other_team.id
    db.commit()
    return mate


def test_another_department_in_the_same_organization_still_reads_everything(
    client, login_as, two_orgs, db, make_user
):
    """부서로 좁히면 여기서 걸린다 — 사내 공지가 자기 팀에만 보이면 공지판이 아니다."""
    seeded = _seed_org_a_post(client, login_as)
    _make_org_a_teammate(make_user, db, "orga2@goodmit.co.kr")
    csrf = login_as("user", email="orga2@goodmit.co.kr")

    detail = client.get(f"/api/board/posts/{seeded['post_id']}")
    assert detail.status_code == 200, f"같은 조직 다른 부서 사람이 글을 못 연다: {detail.text[:200]}"
    assert len(detail.json()["post"]["comments"]) == 1, "댓글이 안 보인다"

    served = client.get(seeded["attachment_url"])
    assert served.status_code == 200, f"같은 조직 첨부를 못 받는다: {served.status_code}"
    assert served.content == PNG

    wrote = client.post(
        f"/api/board/posts/{seeded['post_id']}/comments",
        json={"body": "다른 팀에서 다는 댓글"},
        headers={"X-CSRF-Token": csrf},
    )
    assert wrote.status_code == 200, f"같은 조직 글에 댓글을 못 단다: {wrote.text[:200]}"


def test_a_moderator_in_another_department_can_still_moderate(
    client, login_as, two_orgs, db, make_user, app
):
    """운영자군의 중재는 **조직 안**에서는 그대로여야 한다. 부서로 좁히면 자기 팀 글만
    중재할 수 있게 되어 공지판 운영이 불가능해진다."""
    from app.core.authz import ROLE_OPERATOR

    seeded = _seed_org_a_post(client, login_as)
    _make_org_a_teammate(make_user, db, "orgamod@goodmit.co.kr", role=ROLE_OPERATOR)
    csrf = login_as("user", email="orgamod@goodmit.co.kr")
    headers = {"X-CSRF-Token": csrf}
    post_id = seeded["post_id"]

    patch = client.patch(
        f"/api/board/posts/{post_id}", json={"title": "정정된 공지"}, headers=headers
    )
    assert patch.status_code == 200, f"같은 조직 운영자가 글을 못 고친다: {patch.text[:200]}"
    assert _read_post(app, post_id).title == "정정된 공지"

    pin = client.post(f"/api/board/posts/{post_id}/pin?pinned=true", headers=headers)
    assert pin.status_code == 200, f"같은 조직 운영자가 공지를 못 고정한다: {pin.text[:200]}"

    delete = client.delete(f"/api/board/comments/{seeded['comment_id']}", headers=headers)
    assert delete.status_code == 200, f"같은 조직 운영자가 댓글을 못 지운다: {delete.text[:200]}"

    delete_post = client.delete(f"/api/board/posts/{post_id}", headers=headers)
    assert delete_post.status_code == 200, f"같은 조직 운영자가 글을 못 지운다: {delete_post.text[:200]}"


def test_the_owner_still_sees_their_own_post(client, login_as, two_orgs):
    """가장 흔한 오탐 — 판정을 잘못 걸면 **본인 글까지** 404 가 된다."""
    seeded = _seed_org_a_post(client, login_as)
    r = client.get(f"/api/board/posts/{seeded['post_id']}")
    assert r.status_code == 200, f"작성자 본인이 자기 글을 못 연다: {r.text[:200]}"
