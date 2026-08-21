"""자유게시판 API 통합 테스트 (팀 공간 §18).

인증/CSRF/RBAC/IDOR + 전체 흐름(작성·조회·댓글·답글·반응·첨부) + 기능 플래그 격리.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD, PROJECT_ROOT

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _login_other(app, email):
    make = TestClient(app, raise_server_exceptions=False)
    make.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return make, make.get("/api/me").json()["csrf_token"]


def _create(client, csrf, *, category="자유", title="제목", body="본문"):
    r = client.post(
        "/api/board/posts",
        json={"category": category, "title": title, "body": body},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    return r.json()["post"]


def test_requires_authentication(client):
    assert client.get("/api/board/posts").status_code == 401


def test_my_activity_lists_own_posts_and_summary(app, client, login_as, make_user):
    csrf = login_as("user", email="mine@goodmit.co.kr")
    p1 = _create(client, csrf, title="내 글 1")
    _create(client, csrf, title="내 글 2")
    # 남의 글은 내 요약에 안 들어간다.
    make_user("other@goodmit.co.kr")
    oc, ocsrf = _login_other(app, "other@goodmit.co.kr")
    with oc:
        opost = oc.post("/api/board/posts", json={"category": "자유", "title": "남 글", "body": ""},
                        headers={"X-CSRF-Token": ocsrf}).json()["post"]
        # 남이 내 글 1에 댓글 → 받은 댓글 수 1.
        oc.post(f"/api/board/posts/{p1['id']}/comments", json={"body": "안녕"}, headers={"X-CSRF-Token": ocsrf})

    r = client.get("/api/board/mine").json()
    titles = [it["title"] for it in r["items"]]
    assert "내 글 1" in titles and "내 글 2" in titles and "남 글" not in titles
    assert r["summary"]["post_count"] == 2
    assert r["summary"]["comment_count_received"] == 1
    got = next(it for it in r["items"] if it["title"] == "내 글 1")
    assert got["comment_count"] == 1


def test_create_requires_csrf(client, login_as):
    login_as("user", email="csrf@goodmit.co.kr")
    r = client.post(
        "/api/board/posts", json={"category": "자유", "title": "x", "body": ""}
    )
    assert r.status_code == 403


def test_full_flow_create_list_detail_comment_reaction(client, login_as):
    csrf = login_as("user", email="flow@goodmit.co.kr")
    post = _create(client, csrf, title="첫 글", body="안녕하세요")
    pid = post["id"]

    # 목록에 뜬다.
    listing = client.get("/api/board/posts").json()
    assert listing["total"] == 1
    assert listing["items"][0]["title"] == "첫 글"
    assert listing["items"][0]["comment_count"] == 0

    # 상세 조회(GET)는 조회수를 올리지 않는다 — 조회수는 전용 /view 핑으로만.
    d1 = client.get(f"/api/board/posts/{pid}").json()["post"]
    assert d1["view_count"] == 0
    client.get(f"/api/board/posts/{pid}")
    assert client.get(f"/api/board/posts/{pid}").json()["post"]["view_count"] == 0
    # /view 핑 두 번 → 2.
    client.post(f"/api/board/posts/{pid}/view", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/board/posts/{pid}/view", headers={"X-CSRF-Token": csrf})
    assert client.get(f"/api/board/posts/{pid}").json()["post"]["view_count"] == 2

    # 댓글 + 한 단계 답글.
    r = client.post(
        f"/api/board/posts/{pid}/comments",
        json={"body": "댓글1", "parent_comment_id": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    detail = r.json()["post"]
    top_id = detail["comments"][0]["id"]
    r = client.post(
        f"/api/board/posts/{pid}/comments",
        json={"body": "답글1", "parent_comment_id": top_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert len(r.json()["post"]["comments"]) == 2

    # 반응 추가 → 상세에 반영.
    r = client.post(
        "/api/board/reactions",
        json={"target_type": "post", "target_id": pid, "emoji": "👍"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    detail = client.get(f"/api/board/posts/{pid}").json()["post"]
    assert detail["reactions"] == [{"emoji": "👍", "count": 1, "mine": True}]

    # 반응 제거.
    r = client.request(
        "DELETE",
        "/api/board/reactions",
        json={"target_type": "post", "target_id": pid, "emoji": "👍"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    detail = client.get(f"/api/board/posts/{pid}").json()["post"]
    assert detail["reactions"] == []


def test_reply_to_reply_rejected(client, login_as):
    csrf = login_as("user", email="reply@goodmit.co.kr")
    post = _create(client, csrf)
    pid = post["id"]
    d = client.post(
        f"/api/board/posts/{pid}/comments",
        json={"body": "top", "parent_comment_id": None},
        headers={"X-CSRF-Token": csrf},
    ).json()["post"]
    top_id = d["comments"][0]["id"]
    d = client.post(
        f"/api/board/posts/{pid}/comments",
        json={"body": "reply", "parent_comment_id": top_id},
        headers={"X-CSRF-Token": csrf},
    ).json()["post"]
    reply_id = [c["id"] for c in d["comments"] if c["parent_comment_id"] == top_id][0]
    # 답글에 답글 → 422.
    r = client.post(
        f"/api/board/posts/{pid}/comments",
        json={"body": "nested", "parent_comment_id": reply_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422


def test_search_and_category_filter(client, login_as):
    csrf = login_as("user", email="search@goodmit.co.kr")
    _create(client, csrf, category="자유", title="점심 뭐 먹지", body="김치찌개")
    _create(client, csrf, category="질문", title="배포 방법 질문", body="어떻게 하나요")

    only_q = client.get("/api/board/posts?category=질문").json()
    assert only_q["total"] == 1 and only_q["items"][0]["title"] == "배포 방법 질문"

    found = client.get("/api/board/posts?q=김치").json()
    assert found["total"] == 1 and found["items"][0]["title"] == "점심 뭐 먹지"


def test_non_author_cannot_edit_or_delete(app, client, login_as, make_user):
    csrf = login_as("user", email="owner@goodmit.co.kr")
    post = _create(client, csrf, title="내 글")
    pid = post["id"]

    make_user("intruder@goodmit.co.kr", role="user")
    with TestClient(app, raise_server_exceptions=False) as other:
        other.post(
            "/login",
            json={"email": "intruder@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        ocsrf = other.get("/api/me").json()["csrf_token"]
        r = other.patch(
            f"/api/board/posts/{pid}",
            json={"title": "탈취"},
            headers={"X-CSRF-Token": ocsrf},
        )
        assert r.status_code == 403
        r = other.request(
            "DELETE", f"/api/board/posts/{pid}", headers={"X-CSRF-Token": ocsrf}
        )
        assert r.status_code == 403


def test_moderator_can_pin_but_user_cannot_pin(app, client, login_as, make_user):
    csrf = login_as("user", email="poster@goodmit.co.kr")
    post = _create(client, csrf, title="공지 후보")
    pid = post["id"]

    # 일반 사용자는 고정 불가.
    r = client.post(f"/api/board/posts/{pid}/pin?pinned=true", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403

    # 관리자는 고정 가능(모더레이션 — 수정과는 다른 권한, 아래 test_moderator_cannot_edit
    # 참조).
    make_user("mod@goodmit.co.kr", role="admin")
    with TestClient(app, raise_server_exceptions=False) as mod:
        mod.post("/login", json={"email": "mod@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        mcsrf = mod.get("/api/me").json()["csrf_token"]
        r = mod.post(f"/api/board/posts/{pid}/pin?pinned=true", headers={"X-CSRF-Token": mcsrf})
        assert r.status_code == 200 and r.json()["post"]["is_pinned"] is True

    # 고정 글은 목록 맨 위.
    _create(client, csrf, title="일반 글")
    items = client.get("/api/board/posts").json()["items"]
    assert items[0]["id"] == pid and items[0]["is_pinned"] is True


def test_moderator_cannot_edit_others_post_or_comment_but_can_delete(app, client, login_as, make_user):
    """수정은 작성자 본인만, 삭제는 작성자 또는 운영자군 — 티켓·문서 댓글과 같은 규칙
    (step 9 #1). 예전엔 이 둘이 `can_edit` 하나로 뭉뚱그려져 운영자가 남의 글·댓글
    본문을 조용히 고쳐 쓸 수 있었다(감사 로그는 남지만 화면엔 흔적이 없었다)."""
    csrf = login_as("user", email="post-owner@goodmit.co.kr")
    post = _create(client, csrf, title="원작자 글")
    pid = post["id"]
    c = client.post(
        f"/api/board/posts/{pid}/comments", json={"body": "원작자 댓글"},
        headers={"X-CSRF-Token": csrf},
    )
    assert c.status_code == 200, c.text
    cid = c.json()["post"]["comments"][0]["id"]

    make_user("mod2@goodmit.co.kr", role="admin")
    with TestClient(app, raise_server_exceptions=False) as mod:
        mod.post("/login", json={"email": "mod2@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        mcsrf = mod.get("/api/me").json()["csrf_token"]

        # 수정은 운영자도 거절 — 본인 글이 아니다.
        r = mod.patch(
            f"/api/board/posts/{pid}", json={"title": "운영자가 고침"},
            headers={"X-CSRF-Token": mcsrf},
        )
        assert r.status_code == 403, r.text
        r = mod.patch(
            f"/api/board/comments/{cid}", json={"body": "운영자가 고침"},
            headers={"X-CSRF-Token": mcsrf},
        )
        assert r.status_code == 403, r.text

        # 삭제는 여전히 허용 — 모더레이션은 삭제 쪽에 남는다.
        r = mod.request(
            "DELETE", f"/api/board/comments/{cid}", headers={"X-CSRF-Token": mcsrf}
        )
        assert r.status_code == 200, r.text
        r = mod.request(
            "DELETE", f"/api/board/posts/{pid}", headers={"X-CSRF-Token": mcsrf}
        )
        assert r.status_code == 200, r.text


def test_deleted_comment_is_a_tombstone_not_a_missing_row(client, login_as):
    """삭제된 댓글은 목록에서 **사라지지 않고** 본문 없는 툼스톤으로 남는다(step 9 #4,
    티켓·문서 댓글과 같은 규약). 답글이 달린 댓글이 조용히 사라지면 그 답글만 남아 부모
    없는 대화가 된다."""
    csrf = login_as("user", email="tomb-author@goodmit.co.kr")
    post = _create(client, csrf, title="댓글 삭제 테스트")
    pid = post["id"]
    c = client.post(
        f"/api/board/posts/{pid}/comments", json={"body": "지워질 댓글"},
        headers={"X-CSRF-Token": csrf},
    )
    cid = c.json()["post"]["comments"][0]["id"]
    reply = client.post(
        f"/api/board/posts/{pid}/comments",
        json={"body": "답글", "parent_comment_id": cid},
        headers={"X-CSRF-Token": csrf},
    )
    assert reply.status_code == 200, reply.text

    r = client.request(
        "DELETE", f"/api/board/comments/{cid}", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200, r.text

    detail = client.get(f"/api/board/posts/{pid}").json()["post"]
    comments = {row["id"]: row for row in detail["comments"]}
    assert cid in comments, "삭제된 댓글 행이 목록에서 통째로 사라졌다 — 답글이 고아가 된다"
    assert comments[cid]["deleted"] is True
    assert comments[cid]["body"] == ""
    assert comments[cid]["can_edit"] is False
    assert comments[cid]["can_delete"] is False


def test_edited_comment_shows_a_different_updated_at(client, login_as):
    """'(수정됨)' 표시는 프런트가 `updated_at != created_at` 으로 판단한다
    (CommentThread.jsx 와 같은 규칙) — 서버가 그 둘을 같은 값으로 주면 절대 못 켜진다."""
    csrf = login_as("user", email="edit-author@goodmit.co.kr")
    post = _create(client, csrf, title="댓글 수정 테스트")
    pid = post["id"]
    c = client.post(
        f"/api/board/posts/{pid}/comments", json={"body": "원문"},
        headers={"X-CSRF-Token": csrf},
    )
    comment = c.json()["post"]["comments"][0]
    assert comment["created_at"] == comment["updated_at"]

    r = client.patch(
        f"/api/board/comments/{comment['id']}", json={"body": "고친 글"},
        headers={"X-CSRF-Token": csrf},
    )
    updated = next(x for x in r.json()["post"]["comments"] if x["id"] == comment["id"])
    assert updated["updated_at"] != updated["created_at"]


def test_attachment_upload_serve_and_reject_bad_type(client, login_as):
    csrf = login_as("user", email="att@goodmit.co.kr")
    post = _create(client, csrf)
    pid = post["id"]

    # 유효 PNG 업로드.
    r = client.post(
        f"/api/board/posts/{pid}/attachments",
        files={"file": ("사진.png", PNG, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    att = r.json()["attachment"]
    assert att["media_type"] == "image/png" and att["is_image"] is True

    # 서빙: 바이트 + nosniff.
    served = client.get(att["url"])
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers.get("x-content-type-options") == "nosniff"

    # 잘못된 형식(위장) 거절.
    r = client.post(
        f"/api/board/posts/{pid}/attachments",
        files={"file": ("evil.png", b"<html>hi</html>", "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422

    # 상세에 첨부가 보인다.
    detail = client.get(f"/api/board/posts/{pid}").json()["post"]
    assert len(detail["attachments"]) == 1


def test_attachment_serve_requires_auth(app, client, login_as):
    csrf = login_as("user", email="attauth@goodmit.co.kr")
    post = _create(client, csrf)
    r = client.post(
        f"/api/board/posts/{post['id']}/attachments",
        files={"file": ("a.png", PNG, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    url = r.json()["attachment"]["url"]
    with TestClient(app, raise_server_exceptions=False) as anon:
        assert anon.get(url).status_code == 401


def test_reaction_on_missing_target_404(client, login_as):
    csrf = login_as("user", email="rx@goodmit.co.kr")
    r = client.post(
        "/api/board/reactions",
        json={"target_type": "post", "target_id": "does-not-exist", "emoji": "👍"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404


def test_deleting_parent_comment_cascades_and_tombstones_the_replies(client, login_as):
    """부모 댓글 삭제는 그 답글까지 함께 지운다(카운트 불일치 방지, 검수 결함) — 하지만
    **행 자체는 사라지지 않는다.** step 9 #4 이후로는 삭제된 댓글을 툼스톤으로 남기므로
    (test_deleted_comment_is_a_tombstone_not_a_missing_row 참조), 부모·답글 둘 다 목록에
    남고 둘 다 `deleted: true`·본문 빈 문자열이어야 한다. 댓글 수 배지(comment_count)만
    0으로 줄어든다 — 그건 살아있는 댓글만 센다(app/board/repository.py::comment_count)."""
    csrf = login_as("user", email="cascade@goodmit.co.kr")
    post = _create(client, csrf)
    pid = post["id"]
    d = client.post(f"/api/board/posts/{pid}/comments",
                    json={"body": "부모", "parent_comment_id": None},
                    headers={"X-CSRF-Token": csrf}).json()["post"]
    top_id = d["comments"][0]["id"]
    reply = client.post(f"/api/board/posts/{pid}/comments",
                json={"body": "답글", "parent_comment_id": top_id},
                headers={"X-CSRF-Token": csrf}).json()["post"]
    reply_id = [c for c in reply["comments"] if c["id"] != top_id][0]["id"]

    r = client.request("DELETE", f"/api/board/comments/{top_id}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    detail = client.get(f"/api/board/posts/{pid}").json()["post"]
    by_id = {c["id"]: c for c in detail["comments"]}
    assert {top_id, reply_id} <= set(by_id), "삭제된 부모·답글 행이 통째로 사라졌다"
    assert by_id[top_id]["deleted"] is True and by_id[top_id]["body"] == ""
    assert by_id[reply_id]["deleted"] is True and by_id[reply_id]["body"] == ""
    assert client.get("/api/board/posts").json()["items"][0]["comment_count"] == 0


def test_large_attachment_upload_succeeds_past_256k(client, login_as):
    # 256KB를 넘는 실제 사진 크기(~400KB)도 올라가야 한다(본문 크기 상한 상향, HIGH 결함).
    csrf = login_as("user", email="big@goodmit.co.kr")
    post = _create(client, csrf)
    big_png = PNG + b"\x00" * (400 * 1024)  # ~400KB, 유효 PNG 매직바이트
    r = client.post(
        f"/api/board/posts/{post['id']}/attachments",
        files={"file": ("big.png", big_png, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["attachment"]["size_bytes"] == len(big_png)


def test_deleted_post_attachment_is_not_served(client, login_as):
    csrf = login_as("user", email="delatt@goodmit.co.kr")
    post = _create(client, csrf)
    pid = post["id"]
    att = client.post(f"/api/board/posts/{pid}/attachments",
                      files={"file": ("a.png", PNG, "image/png")},
                      headers={"X-CSRF-Token": csrf}).json()["attachment"]
    assert client.get(att["url"]).status_code == 200
    client.request("DELETE", f"/api/board/posts/{pid}", headers={"X-CSRF-Token": csrf})
    # 글을 내리면 첨부도 더는 서빙되지 않는다.
    assert client.get(att["url"]).status_code == 404


def test_reaction_rejected_on_comment_under_deleted_post(client, login_as):
    csrf = login_as("user", email="delrx@goodmit.co.kr")
    post = _create(client, csrf)
    pid = post["id"]
    d = client.post(f"/api/board/posts/{pid}/comments",
                    json={"body": "c", "parent_comment_id": None},
                    headers={"X-CSRF-Token": csrf}).json()["post"]
    cid = d["comments"][0]["id"]
    client.request("DELETE", f"/api/board/posts/{pid}", headers={"X-CSRF-Token": csrf})
    r = client.post("/api/board/reactions",
                    json={"target_type": "comment", "target_id": cid, "emoji": "👍"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404


def test_feature_flag_off_hides_board(db_url, tmp_path, fake_clock, fake_http):
    import shutil

    from app.core.config import Settings
    from app.main import create_app
    from app.users.service import create_user

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    (cfg / "feature-flags.json").write_text(
        json.dumps({"board_enabled": False}), encoding="utf-8"
    )
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=db_url,
        session_secret="test-session-secret",
        cookie_secure=False,
        config_dir=cfg,
        secrets_dir=secrets_dir,
        data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(
            s,
            email="ff@goodmit.co.kr",
            display_name="FF",
            password=DEFAULT_TEST_PASSWORD,
            settings=settings,
            actor_role="system_admin",
            role="user",
            active=True,
            must_change_password=False,
        )
        s.commit()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "ff@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        assert c.get("/api/board/posts").status_code == 404
