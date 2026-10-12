"""사람을 보여 주는 행마다 얼굴 두 칸(`avatar_url` · `avatar_default_key`)이 실린다 (D-556).

조직 관리의 구성원 표는 `/api/admin/users` 행으로 사람을 그리는데 두 칸이 없어 화면이 사용자 id 로
기본 그림을 배정했다 — **본인이 올린 사진 · 고른 그림과 다른 얼굴**이 서서 프로필 화면과 어긋났다.
같은 결함이 관리 콘솔의 사람 후보(`/api/admin/people`), 팀 채팅 디렉터리, 놀이방 참여자에 있었다.
네 경로가 같은 정본(`app/core/people.py::avatar_map`)을 싣는다.

사진이 **실제로 있는** 상태를 먼저 만든다 — 사진이 없으면 두 칸이 비어 있어도 시험이 통과해 버린다.
"""

from __future__ import annotations

import pytest

from tests.fakes.images import png_bytes

pytestmark = pytest.mark.integration

pytest.importorskip("PIL", reason="Pillow 가 없으면 아바타 업로드 경로 자체가 없다")
PNG_BYTES = png_bytes()


def _upload_photo(client, csrf) -> str:
    r = client.post("/api/me/avatar", files={"file": ("me.png", PNG_BYTES, "image/png")},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url
    return url


def test_admin_user_rows_carry_the_photo_the_person_uploaded(client, login_as, make_user):
    face = make_user("face@goodmit.co.kr", role="user", display_name="얼굴")
    csrf = login_as("user", email="face@goodmit.co.kr")
    url = _upload_photo(client, csrf)

    login_as("admin")
    rows = client.get("/api/admin/users?q=face").json()["items"]
    row = next(r for r in rows if r["id"] == face.id)
    assert row["avatar_url"] == url, f"목록 행이 프로필의 사진 주소와 다르다: {row}"
    assert "avatar_default_key" in row

    detail = client.get(f"/api/admin/users/{face.id}").json()
    assert detail["avatar_url"] == url

    people = client.get("/api/admin/people?q=face").json()["items"]
    person = next(p for p in people if p["id"] == face.id)
    assert person["avatar_url"] == url, f"사람 후보 줄이 사진을 모른다: {person}"


def test_rows_carry_the_default_picture_the_person_chose(client, login_as, make_user):
    """사진이 없는 사람은 **고른 그림**이 실린다 — 화면이 id 로 배정한 그림 대신 그것을 그린다."""
    picker = make_user("picker@goodmit.co.kr", role="user", display_name="고름")
    csrf = login_as("user", email="picker@goodmit.co.kr")
    r = client.patch("/api/me/preferences", json={"avatar_default_key": "thumbs:4"},
                     headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text

    login_as("admin")
    row = next(r for r in client.get("/api/admin/users?q=picker").json()["items"] if r["id"] == picker.id)
    assert row["avatar_url"] is None
    assert row["avatar_default_key"] == "thumbs:4"


def test_team_chat_directory_and_game_members_carry_faces(app, client, login_as, make_user):
    face = make_user("face2@goodmit.co.kr", role="user", display_name="얼굴둘")
    csrf = login_as("user", email="face2@goodmit.co.kr")
    url = _upload_photo(client, csrf)

    # 놀이방 참여자 — 방을 만든 사람 자신이 첫 참여자다.
    r = client.post("/api/games/rooms", json={"title": "얼굴 방", "game_type": "random_draw"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    rid = r.json()["room"]["id"]
    members = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["members"]
    me = next(m for m in members if m["user_id"] == face.id)
    assert me["avatar_url"] == url, f"놀이방 참여자 줄이 사진을 모른다: {me}"
    assert "avatar_default_key" in me

    # 팀 채팅 디렉터리 — 다른 사람이 볼 때.
    make_user("viewer@goodmit.co.kr", role="user", display_name="보는이")
    login_as("user", email="viewer@goodmit.co.kr")
    users = client.get("/api/team-chat/directory").json()["users"]
    entry = next(u for u in users if u["user_id"] == face.id)
    assert entry["avatar_url"] == url, f"디렉터리 줄이 사진을 모른다: {entry}"
    assert set(entry) == {"user_id", "display_name", "dept", "title", "avatar_url", "avatar_default_key"}, (
        f"디렉터리는 신원 조각과 얼굴 두 칸만 싣는다(이메일 · 역할 금지): {entry}"
    )


def test_global_admin_can_fetch_an_archived_users_photo_but_a_plain_user_cannot(client, login_as, make_user, db):
    """관리 범위가 그 사람을 담으면 보관된 사람의 사진도 준다 — 목록이 보여 주는 사람의 얼굴만 빠지면 안 된다.
    일반 사용자에게는 예전처럼 404 다(보관된 사람은 디렉터리에 없다)."""
    from app.core.models_base import utcnow

    leaver = make_user("leaver@goodmit.co.kr", role="user", display_name="퇴사자")
    csrf = login_as("user", email="leaver@goodmit.co.kr")
    url = _upload_photo(client, csrf)

    leaver.archived_at = utcnow()
    db.commit()

    login_as("admin")
    assert client.get(url).status_code == 200, "전역 관리자는 보관 사용자 목록을 보는데 그 얼굴만 404 다"

    make_user("plain@goodmit.co.kr", role="user", display_name="일반")
    login_as("user", email="plain@goodmit.co.kr")
    assert client.get(url).status_code == 404, "일반 사용자에게 보관된 사람의 사진이 나간다"
    assert leaver.id
