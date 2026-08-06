"""게시글·댓글이 **작성자가 누구인지** 말한다 (#13 / #8).

사용자 지시: *"게시글과 댓글에는 작성자의 부서·팀·직책을 함께 표시한다"*,
*"프로필 사진이 다른 사용자 화면에서도 보이는 구조인지 확인한다"*.

게시판은 `author_name` 하나만 실어 보내고 있었다 — `users.display_name` 에는 유일성
제약이 **없으므로**(`app/users/models.py`) 동명이인은 스키마상 정상 상태다. 즉 목록의
'작성자' 칸과 댓글 머리글은 **누구인지 답하지 못하는 칸**이었다. 채팅은 이미
`people: {uid: identity(...)}` 로 답하고 있었는데(`app/team_chat/router.py`) 게시판만
빠져 있었다 — 같은 질문에 화면마다 다르게 답하던 그 상태다.

사진도 같은 자리에서 빠져 있었다(X13). 서빙 경로(`/api/profile/avatar/{user_id}`)는
**이미 전 직원 대상**이라, 없던 것은 "남의 아바타 주소를 알려 주는 payload" 하나뿐이다.

그리고 **배치로** 모은다. 게시판 상세·목록은 폴링·재조회 경로다(댓글·반응을 쓸 때마다
상세를 다시 부른다) — 작성자마다 질의를 돌면 가장 자주 열리는 화면이 바로 N+1 이 된다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login_other(app, email):
    other = TestClient(app, raise_server_exceptions=False)
    other.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return other, other.get("/api/me").json()["csrf_token"]


def _create(client, csrf, *, title="제목", body="본문"):
    r = client.post(
        "/api/board/posts",
        json={"category": "자유", "title": title, "body": body},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    return r.json()["post"]


def _place(db, user, *, dept=None, title=None):
    """사람을 부서·직책에 앉힌다 — 신원은 명부(Department/JobTitle)에서 읽힌다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department, JobTitle

    if dept:
        row = Department(name=dept, org_id=DEFAULT_ORG_ID)
        db.add(row)
        db.flush()
        user.department_id = row.id
    if title:
        row = JobTitle(name=title, org_id=DEFAULT_ORG_ID)
        db.add(row)
        db.flush()
        user.title_id = row.id
    db.commit()


# ── 글 ─────────────────────────────────────────────────────────────────────
def test_post_detail_says_which_dept_and_title_the_author_is(client, login_as, db):
    csrf = login_as("user", email="bp-author@goodmit.co.kr")
    from app.users.service import get_user_by_email

    me = get_user_by_email(db, "bp-author@goodmit.co.kr")
    _place(db, me, dept="ClovirONE팀", title="팀장")

    post = _create(client, csrf, title="첫 글")
    detail = client.get(f"/api/board/posts/{post['id']}").json()["post"]

    person = detail["people"][me.id]
    assert person["dept"] == "ClovirONE팀", f"부서가 안 실린다: {person}"
    assert person["title"] == "팀장", f"직책이 안 실린다: {person}"
    assert person["display_name"] == me.display_name
    assert "avatar_url" in person, f"사진 자리가 아예 없다 — 화면이 그릴 수 없다: {person}"


def test_list_carries_people_for_every_author(app, client, login_as, make_user, db):
    """목록의 '작성자' 칸도 같은 질문에 답해야 한다 — 동명이인은 목록에서 먼저 만난다."""
    csrf = login_as("user", email="bp-list-a@goodmit.co.kr")
    from app.users.service import get_user_by_email

    mine = get_user_by_email(db, "bp-list-a@goodmit.co.kr")
    _place(db, mine, dept="A팀", title="선임")
    _create(client, csrf, title="내 글")

    other = make_user("bp-list-b@goodmit.co.kr", display_name="테스트 사용자")
    _place(db, other, dept="B팀", title="책임")
    oc, ocsrf = _login_other(app, "bp-list-b@goodmit.co.kr")
    with oc:
        _create(oc, ocsrf, title="남의 글")

    listing = client.get("/api/board/posts").json()
    people = listing["people"]
    assert people[mine.id]["dept"] == "A팀", f"목록이 작성자를 구분하지 못한다: {people}"
    assert people[other.id]["dept"] == "B팀", f"목록이 작성자를 구분하지 못한다: {people}"


# ── 댓글 ───────────────────────────────────────────────────────────────────
def test_comment_authors_ride_the_same_people_map(app, client, login_as, make_user, db):
    """댓글 작성자도 같은 묶음에 실린다 — 댓글마다 신원을 되풀이하면 폴링 응답이 부푼다."""
    csrf = login_as("user", email="bp-owner@goodmit.co.kr")
    post = _create(client, csrf, title="질문 있습니다")

    commenter = make_user("bp-commenter@goodmit.co.kr", display_name="댓글쓴이")
    _place(db, commenter, dept="인프라팀", title="수석")
    oc, ocsrf = _login_other(app, "bp-commenter@goodmit.co.kr")
    with oc:
        r = oc.post(
            f"/api/board/posts/{post['id']}/comments",
            json={"body": "제가 답니다"},
            headers={"X-CSRF-Token": ocsrf},
        )
        assert r.status_code == 200, r.text

    detail = client.get(f"/api/board/posts/{post['id']}").json()["post"]
    person = detail["people"][commenter.id]
    assert person["dept"] == "인프라팀", f"댓글 작성자의 소속이 없다: {person}"
    assert person["title"] == "수석", f"댓글 작성자의 직책이 없다: {person}"


# ── 떠난 사람 ───────────────────────────────────────────────────────────────
def test_people_says_when_the_author_is_gone(app, client, login_as, make_user, db):
    """퇴사자가 영원히 작성자로 살아 있으면 보는 사람은 답이 안 오는 글에 답글을 단다 (N3)."""
    author = make_user("bp-gone@goodmit.co.kr", display_name="떠난사람")
    oc, ocsrf = _login_other(app, "bp-gone@goodmit.co.kr")
    with oc:
        post = _create(oc, ocsrf, title="마지막 글")

    author.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    author.active = False
    db.commit()

    login_as("system_admin")
    detail = client.get(f"/api/board/posts/{post['id']}").json()["post"]
    assert detail["people"][author.id]["archived"] is True, (
        f"떠난 사람인데 화면이 그 사실을 모른다: {detail['people']}"
    )


def test_a_living_author_is_not_marked_archived(client, login_as, db):
    """오탐 방지 — 멀쩡한 사람에게 (보관됨)을 붙이면 아무도 그에게 말을 걸지 않는다."""
    csrf = login_as("user", email="bp-alive@goodmit.co.kr")
    from app.users.service import get_user_by_email

    me = get_user_by_email(db, "bp-alive@goodmit.co.kr")
    post = _create(client, csrf, title="살아 있는 글")

    detail = client.get(f"/api/board/posts/{post['id']}").json()["post"]
    assert detail["people"][me.id]["archived"] is False


# ── 사진 ───────────────────────────────────────────────────────────────────
def test_avatar_url_is_carried_with_a_fingerprint(client, login_as, db):
    """X13 — 주소를 안 실으면 남의 사진을 그릴 방법이 없다. 지문(?v=)이 없으면 바꿔도 옛 사진."""
    from app.profiles.models import UserPreference
    from app.users.service import get_user_by_email

    csrf = login_as("user", email="bp-face@goodmit.co.kr")
    me = get_user_by_email(db, "bp-face@goodmit.co.kr")
    db.add(UserPreference(
        user_id=me.id, avatar_stored_name="face.png",
        avatar_updated_at=datetime(2026, 8, 1, 0, 0, 0),
    ))
    db.commit()

    post = _create(client, csrf, title="사진 있는 사람의 글")
    person = client.get(f"/api/board/posts/{post['id']}").json()["post"]["people"][me.id]
    assert person["avatar_url"], f"사진이 있는데 주소가 안 실린다: {person}"
    assert person["avatar_url"].startswith(f"/api/profile/avatar/{me.id}?v="), (
        f"지문이 없으면 사진을 바꿔도 캐시 때문에 옛 사진이 보인다: {person['avatar_url']}"
    )


def test_an_author_without_a_photo_gets_null_not_a_broken_url(client, login_as, db):
    """오탐 방지 — 없는 사진에 주소를 주면 화면에 깨진 이미지가 뜬다."""
    from app.users.service import get_user_by_email

    csrf = login_as("user", email="bp-nopic@goodmit.co.kr")
    me = get_user_by_email(db, "bp-nopic@goodmit.co.kr")
    post = _create(client, csrf, title="사진 없는 사람의 글")

    person = client.get(f"/api/board/posts/{post['id']}").json()["post"]["people"][me.id]
    assert person["avatar_url"] is None, f"없는 사진의 주소를 줬다: {person}"


# ── 소속이 없는 사람 ────────────────────────────────────────────────────────
def test_an_author_without_a_dept_still_gets_a_row(client, login_as, db):
    """오탐 방지 — 부서가 비어도 신원 줄 자체는 있어야 한다(화면이 이름은 그린다)."""
    from app.users.service import get_user_by_email

    csrf = login_as("user", email="bp-nodept@goodmit.co.kr")
    me = get_user_by_email(db, "bp-nodept@goodmit.co.kr")
    post = _create(client, csrf, title="소속 없는 사람의 글")

    person = client.get(f"/api/board/posts/{post['id']}").json()["post"]["people"][me.id]
    assert person["dept"] == "" and person["title"] == ""


# ── 배치 (N+1 방지) ─────────────────────────────────────────────────────────
def _count_statements(fn):
    """이 호출 동안 나간 SQL 문 수. 붙였다 떼는 리스너라 다른 테스트에 남지 않는다."""
    n = 0

    def _tick(conn, cursor, statement, params, context, executemany):
        nonlocal n
        n += 1

    event.listen(Engine, "before_cursor_execute", _tick)
    try:
        fn()
    finally:
        event.remove(Engine, "before_cursor_execute", _tick)
    return n


def test_people_is_batched_not_one_query_per_author(app, client, login_as, make_user, db):
    """작성자가 늘어도 질의 수는 그대로다.

    상세는 댓글·반응을 쓸 때마다 다시 불린다 — 여기서 건별 조회를 하면 가장 자주 열리는
    화면이 바로 N+1 이 된다(채팅 `people` 이 이미 겪고 피한 모양, X13/H4).
    """
    csrf = login_as("user", email="bp-batch@goodmit.co.kr")
    few = _create(client, csrf, title="댓글 하나")
    many = _create(client, csrf, title="댓글 다섯")

    for i in range(5):
        email = f"bp-batch-{i}@goodmit.co.kr"
        make_user(email, display_name=f"댓글러{i}")
        oc, ocsrf = _login_other(app, email)
        with oc:
            target = few if i == 0 else many
            oc.post(f"/api/board/posts/{target['id']}/comments",
                    json={"body": f"댓글 {i}"}, headers={"X-CSRF-Token": ocsrf})
            if i > 0:
                oc.post(f"/api/board/posts/{many['id']}/comments",
                        json={"body": f"또 {i}"}, headers={"X-CSRF-Token": ocsrf})

    hit_few = _count_statements(lambda: client.get(f"/api/board/posts/{few['id']}"))
    hit_many = _count_statements(lambda: client.get(f"/api/board/posts/{many['id']}"))
    assert hit_many == hit_few, (
        f"등장 인물 수만큼 질의가 늘었다 — 건별 조회다 (2명 {hit_few}회 vs 5명 {hit_many}회)"
    )
