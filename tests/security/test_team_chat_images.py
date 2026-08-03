"""팀 채팅 붙여넣기 이미지의 접근 통제 (PLAN §D-3의 알려진 결함 방지).

**이 파일이 막는 결함**: 게시판 첨부 경로(`uploads/board/<post_id>` +
`GET /api/board/attachments/{id}`)를 채팅이 재사용하면, 게시판 서빙 라우트가 방 멤버십을
모르기 때문에 **1:1 DM 사진이 로그인한 전 직원에게 열린다**. 그래서 채팅 이미지는
- 다른 네임스페이스(`uploads/team_chat/<room_id>/`)에 저장되고,
- 방 접근 검사를 먼저 하는 전용 라우트로만 서빙되며,
- 접근 불가는 403이 아니라 **404**로 답한다(존재 자체를 확인해 주지 않는다).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 32


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c, c.get("/api/me").json()["csrf_token"]


def _paste(client, csrf, room_id, content=PNG, name="paste.png", mime="image/png"):
    return client.post(
        f"/api/team-chat/rooms/{room_id}/images",
        files={"file": (name, content, mime)},
        headers={"X-CSRF-Token": csrf},
    )


def _group_with(client, csrf, member_ids, title="사진방"):
    return client.post("/api/team-chat/rooms", json={"title": title, "member_user_ids": member_ids},
                       headers={"X-CSRF-Token": csrf}).json()["room"]["id"]


def test_paste_image_round_trip_serves_bytes_with_nosniff(client, login_as):
    csrf = login_as("user", email="img1@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    r = _paste(client, csrf, rid)
    assert r.status_code == 200, r.text
    url = r.json()["image"]["url"]
    # 게시판 첨부 주소를 절대 쓰지 않는다 — 그 라우트는 방 멤버십을 모른다.
    assert url.startswith("/api/team-chat/messages/") and "/board/" not in url

    served = client.get(url)
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers.get("x-content-type-options") == "nosniff"
    assert served.headers.get("content-type", "").startswith("image/png")

    # 메시지 폴링에 이미지가 인라인으로 딸려 온다.
    msgs = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()["messages"]
    img_msgs = [m for m in msgs if m["kind"] == "image"]
    assert len(img_msgs) == 1 and img_msgs[0]["images"][0]["url"] == url

    # 목록 미리보기는 저장 파일명이 아니라 '사진'이다(목록이 파일 탐색기처럼 읽히지 않게).
    row = next(x for x in client.get("/api/team-chat/rooms").json()["items"] if x["id"] == rid)
    assert row["last_preview"] == "사진"


def test_non_member_gets_404_not_403_on_another_rooms_image(app, client, login_as, make_user):
    """비멤버에게 403을 주면 '그 방에 그 이미지가 있다'를 확인해 준다 — 404로 감춘다."""
    csrf = login_as("user", email="imgown@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    url = _paste(client, csrf, rid).json()["image"]["url"]

    make_user("imgout@goodmit.co.kr")
    outsider, _ = _login_other(app, "imgout@goodmit.co.kr")
    with outsider:
        r = outsider.get(url)
        assert r.status_code == 404, r.text
        # 대비: 방 자체는 예전처럼 403이다(그 방을 아는 상태에서의 접근 거부).
        # 이미지만 404로 감추는 것은 의도적이다 — URL 을 쥔 사람에게 '있다/없다'를
        # 알려주지 않는다.
        assert outsider.get(f"/api/team-chat/rooms/{rid}/messages?since=0").status_code == 403


def test_direct_message_image_is_not_readable_by_a_third_person(app, client, login_as, make_user):
    """1:1 DM 사진이 전사 공개되지 않는다 — 이 프로젝트에서 실제로 우려됐던 결함."""
    csrf = login_as("user", email="dmimg1@goodmit.co.kr")
    u2 = make_user(email="dmimg2@goodmit.co.kr", display_name="디엠상대")
    rid = client.post("/api/team-chat/rooms/direct", json={"user_id": u2.id},
                      headers={"X-CSRF-Token": csrf}).json()["room"]["id"]
    url = _paste(client, csrf, rid).json()["image"]["url"]

    # 상대는 볼 수 있다.
    c2, _ = _login_other(app, "dmimg2@goodmit.co.kr")
    with c2:
        assert c2.get(url).status_code == 200
    # 제3자는 못 본다.
    make_user("dmimg3@goodmit.co.kr")
    c3, _ = _login_other(app, "dmimg3@goodmit.co.kr")
    with c3:
        assert c3.get(url).status_code == 404


def test_image_requires_authentication(app, client, login_as):
    csrf = login_as("user", email="imgauth@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    url = _paste(client, csrf, rid).json()["image"]["url"]
    with TestClient(app, raise_server_exceptions=False) as anon:
        assert anon.get(url).status_code == 401


def test_png_named_text_file_is_rejected_by_magic_byte_sniffing(client, login_as):
    """확장자·Content-Type 은 사용자가 정한다 — 앞 바이트로만 판정한다."""
    csrf = login_as("user", email="imgsniff@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    r = _paste(client, csrf, rid, content=b"<html><script>alert(1)</script></html>",
               name="evil.png", mime="image/png")
    assert r.status_code == 422, r.text
    # 메시지도 만들어지지 않는다(빈 이미지 말풍선이 남으면 안 된다).
    msgs = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()["messages"]
    assert [m for m in msgs if m["kind"] == "image"] == []


def test_pdf_is_rejected_in_chat_even_though_the_board_allows_it(client, login_as):
    """채팅 말풍선은 이미지 전용이다 — 게시판이 허용하는 PDF도 여기선 안 된다."""
    csrf = login_as("user", email="imgpdf@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    r = _paste(client, csrf, rid, content=b"%PDF-1.4\n" + b"\x00" * 32,
               name="doc.pdf", mime="application/pdf")
    assert r.status_code == 422, r.text


def test_upload_to_a_room_you_are_not_in_is_forbidden(app, client, login_as, make_user):
    csrf = login_as("user", email="imgup1@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    make_user("imgup2@goodmit.co.kr")
    other, ocsrf = _login_other(app, "imgup2@goodmit.co.kr")
    with other:
        assert _paste(other, ocsrf, rid).status_code == 403


def test_image_id_from_another_room_cannot_be_attached_to_my_message(app, client, login_as, make_user):
    """(message_id, image_id) 쌍으로만 조회한다 — 내 방 메시지 id + 남의 이미지 id 조합 차단."""
    csrf = login_as("user", email="imgmix1@goodmit.co.kr")
    mine = _group_with(client, csrf, [], title="내방")
    my_url = _paste(client, csrf, mine).json()["image"]["url"]
    my_message_id = my_url.split("/")[4]

    make_user("imgmix2@goodmit.co.kr")
    other, ocsrf = _login_other(app, "imgmix2@goodmit.co.kr")
    with other:
        theirs = _group_with(other, ocsrf, [], title="남의방")
        their_image_id = _paste(other, ocsrf, theirs).json()["image"]["id"]

    r = client.get(f"/api/team-chat/messages/{my_message_id}/images/{their_image_id}")
    assert r.status_code == 404, r.text


def test_image_is_not_served_after_the_room_is_disbanded(client, login_as):
    csrf = login_as("user", email="imgdis@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    url = _paste(client, csrf, rid).json()["image"]["url"]
    assert client.get(url).status_code == 200
    client.post(f"/api/team-chat/rooms/{rid}/disband", headers={"X-CSRF-Token": csrf})
    assert client.get(url).status_code == 404


def test_image_upload_requires_csrf(client, login_as):
    csrf = login_as("user", email="imgcsrf@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    r = client.post(f"/api/team-chat/rooms/{rid}/images", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 403


def test_gif_is_accepted_and_stored_in_the_team_chat_namespace(client, login_as, settings):
    csrf = login_as("user", email="imggif@goodmit.co.kr")
    rid = _group_with(client, csrf, [])
    r = _paste(client, csrf, rid, content=GIF, name="a.gif", mime="image/gif")
    assert r.status_code == 200, r.text
    # 게시판 네임스페이스를 오염시키지 않는다.
    assert (settings.data_dir / "uploads" / "team_chat" / rid).is_dir()
    assert not (settings.data_dir / "uploads" / "board" / rid).exists()
