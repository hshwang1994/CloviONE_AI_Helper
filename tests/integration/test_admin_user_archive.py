"""사용자 '보관'(archive) — 삭제 대신 감추되 되돌릴 수 있어야 한다.

계정을 정말 지우면 감사 로그의 '누가 했는지'가 빈칸이 된다(§25.7의 행위자 추적이
끊긴다). 그래서 행은 DB에 남기고 목록·검색·로그인에서만 뺀다.
"""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def test_archive_hides_user_from_default_list(client, admin_csrf, make_user):
    target = make_user("archive-me@goodmit.co.kr")

    r = client.get("/api/admin/users", headers=_headers(admin_csrf))
    assert "archive-me@goodmit.co.kr" in [u["email"] for u in r.json()["items"]]

    r = client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text

    r = client.get("/api/admin/users", headers=_headers(admin_csrf))
    assert "archive-me@goodmit.co.kr" not in [u["email"] for u in r.json()["items"]]


def test_archived_user_hidden_from_search_too(client, admin_csrf, make_user):
    """검색은 목록의 '다른 문'이다 — 여기로 새면 감춘 것이 아니다."""
    target = make_user("findme@goodmit.co.kr", display_name="찾아줘")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.get("/api/admin/users", params={"q": "findme"}, headers=_headers(admin_csrf))
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_archived_visible_only_with_archived_true(client, admin_csrf, make_user):
    """복구하려면 보관된 계정을 볼 수 있어야 한다."""
    target = make_user("only-archived@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.get("/api/admin/users", params={"archived": "true"}, headers=_headers(admin_csrf))
    emails = [u["email"] for u in r.json()["items"]]
    assert emails == ["only-archived@goodmit.co.kr"], "보관 목록에는 보관된 계정만 나와야 한다"
    assert r.json()["items"][0]["archived_at"] is not None


def test_unarchive_restores_to_default_list(client, admin_csrf, make_user):
    target = make_user("comeback@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.post(f"/api/admin/users/{target.id}/unarchive", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text

    r = client.get("/api/admin/users", headers=_headers(admin_csrf))
    assert "comeback@goodmit.co.kr" in [u["email"] for u in r.json()["items"]]
    r = client.get(f"/api/admin/users/{target.id}", headers=_headers(admin_csrf))
    assert r.json()["archived_at"] is None


def test_archived_user_cannot_log_in(client, admin_csrf, make_user, app):
    """보관은 '되돌릴 수 있는 퇴사 처리'다 — 그 계정으로 들어올 수는 없어야 한다."""
    from fastapi.testclient import TestClient

    target = make_user("gone@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    with TestClient(app, raise_server_exceptions=False) as fresh:
        r = fresh.post(
            "/login", json={"email": "gone@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "account_archived"


def test_archive_revokes_existing_sessions(client, admin_csrf, make_user, app):
    """이미 들어와 있는 세션이 살아 있으면 보관은 로그인만 막은 시늉이다."""
    from fastapi.testclient import TestClient

    target = make_user("kickme@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as victim:
        victim.post(
            "/login", json={"email": "kickme@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        assert victim.get("/api/me").status_code == 200

        client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
        assert victim.get("/api/me").status_code == 401


def test_unarchived_user_can_log_in_again(client, admin_csrf, make_user, app):
    from fastapi.testclient import TestClient

    target = make_user("returning@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
    client.post(f"/api/admin/users/{target.id}/unarchive", headers=_headers(admin_csrf))

    with TestClient(app, raise_server_exceptions=False) as fresh:
        r = fresh.post(
            "/login", json={"email": "returning@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        assert r.status_code == 200, r.text


def test_archive_writes_audit_row(client, admin_csrf, make_user, db):
    from app.audit.models import AuditLog

    target = make_user("audited@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    rows = db.query(AuditLog).filter(AuditLog.action == "user.archive").all()
    assert len(rows) == 1
    assert rows[0].object_id == target.id
    assert rows[0].user_id is not None, "누가 보관했는지가 남아야 한다"


def test_unarchive_writes_audit_row(client, admin_csrf, make_user, db):
    from app.audit.models import AuditLog

    target = make_user("audited2@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
    client.post(f"/api/admin/users/{target.id}/unarchive", headers=_headers(admin_csrf))

    assert db.query(AuditLog).filter(AuditLog.action == "user.unarchive").count() == 1


def test_creating_user_with_archived_email_explains_and_offers_restore(
    client, admin_csrf, make_user
):
    """이메일은 유일 제약이다. 보관된 계정이 그 주소를 쥐고 있으면 새로 만들 수 없는데,
    500이나 '이미 등록된 이메일'만 보여 주면 사용자는 목록에 없는 계정 때문에 막힌
    이유를 알 방법이 없다."""
    target = make_user("recycled@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.post(
        "/api/admin/users",
        json={"email": "recycled@goodmit.co.kr", "display_name": "다시 온 사람", "role": "user"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "archived_email_conflict"
    assert "보관된 계정" in err["message"]
    assert "복구" in err["message"]
    # UI가 '복구하시겠습니까?'를 실제 동작으로 이어 주려면 그 계정을 가리킬 수 있어야 한다.
    assert err["details"]["archived_user_id"] == target.id


def test_live_email_conflict_message_unchanged(client, admin_csrf, make_user):
    """살아 있는 계정과의 충돌은 기존 그대로 — 보관 안내로 헷갈리게 하지 않는다."""
    make_user("living@goodmit.co.kr")
    r = client.post(
        "/api/admin/users",
        json={"email": "living@goodmit.co.kr", "display_name": "중복", "role": "user"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_archive_is_idempotent(client, admin_csrf, make_user):
    target = make_user("twice@goodmit.co.kr")
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf)
    ).status_code == 200
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf)
    ).status_code == 200


def test_archived_user_owned_schedules_are_disabled(client, admin_csrf, make_user, db):
    """비활성화와 같은 이유다(§11.5) — 보관한 사람의 스케줄이 계속 돌면 안 된다."""
    from app.schedules.models import Schedule

    target = make_user("owner@goodmit.co.kr")
    schedule = Schedule(
        name="보관자의 스케줄", schedule_type="cron", cron_expression="0 9 * * 1",
        timezone="Asia/Seoul", target_type="workflow", target_ref="wf-1",
        owner_user_id=target.id, enabled=True,
    )
    db.add(schedule)
    db.commit()

    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    db.expire_all()
    assert db.get(Schedule, schedule.id).enabled is False


def _owned_group_room(db, owner, other, *, joined_at):
    from datetime import datetime

    from app.team_chat.models import ChatRoom, ChatRoomMember

    room = ChatRoom(title="보관 전 방장 방", kind="group", is_global=False)
    db.add(room)
    db.flush()
    db.add(ChatRoomMember(room_id=room.id, user_id=owner.id, role="owner",
                           joined_at=datetime(2026, 1, 1)))
    db.add(ChatRoomMember(room_id=room.id, user_id=other.id, role="member", joined_at=joined_at))
    db.commit()
    return room


def _role_of(db, room, user):
    from sqlalchemy import select

    from app.team_chat.models import ChatRoomMember

    row = db.execute(
        select(ChatRoomMember).where(
            ChatRoomMember.room_id == room.id, ChatRoomMember.user_id == user.id
        )
    ).scalar_one_or_none()
    return None if row is None else row.role


def test_archived_user_owned_chat_rooms_are_transferred(client, admin_csrf, make_user, db):
    """`/users`에서 **바로** 보관해도(오프보딩 마법사를 거치지 않아도) 방장직은 넘어가야
    한다(step 9 #2) — 안 그러면 그 방은 그 순간부터 아무도 관리 못 하는 방으로 남는다.
    예전엔 이 인계가 오프보딩 마법사 전체 실행 경로에만 있었다."""
    from datetime import datetime

    target = make_user("room-owner@goodmit.co.kr")
    mate = make_user("room-mate@goodmit.co.kr")
    room = _owned_group_room(db, target, mate, joined_at=datetime(2026, 2, 1))

    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    db.expire_all()
    assert _role_of(db, room, mate) == "owner", "방장직이 안 넘어갔다"
    assert _role_of(db, room, target) == "member", "보관된 계정이 아직 방장이다"


def test_deactivated_user_owned_chat_rooms_are_transferred(client, admin_csrf, make_user, db):
    """비활성화도 보관과 같은 이유다 — 계정이 로그인을 못 하게 되는 순간은 같다."""
    from datetime import datetime

    target = make_user("room-owner2@goodmit.co.kr")
    mate = make_user("room-mate2@goodmit.co.kr")
    room = _owned_group_room(db, target, mate, joined_at=datetime(2026, 2, 1))

    r = client.post(
        f"/api/admin/users/{target.id}/disable", headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    assert _role_of(db, room, mate) == "owner", "방장직이 안 넘어갔다"
    assert _role_of(db, room, target) == "member", "비활성화된 계정이 아직 방장이다"


# ── 보관된 계정은 쓰기 경로에서 «없는 것» 이다 (xb-14) ────────────────────────
#
# 목록·검색·로그인에서 뺐는데 이름 수정·비활성화·잠금 해제가 그대로 먹었다. 화면은 보관 행에서
# 편집 동작을 숨기므로 API 로만 나던 결함이고, 그렇게 바꾼 값은 관리자 화면 어디에도 안 보인다.
# 범위 밖 행과 **같은 답**(404)을 준다 — 가린 것을 단건 경로가 열지 않는다.


@pytest.fixture()
def archived_user(client, admin_csrf, make_user):
    target = make_user("write-me@goodmit.co.kr", display_name="보관된 사람")
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf)
    ).status_code == 200
    return target


def test_patching_an_archived_user_is_not_found(client, admin_csrf, archived_user, db):
    r = client.patch(
        f"/api/admin/users/{archived_user.id}",
        json={"display_name": "몰래 수정"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 404, r.text

    # 404 를 냈지만 이미 썼을 수도 있다 — DB 로 되짚는다.
    db.commit()
    db.expire_all()
    from app.users.models import User

    assert db.get(User, archived_user.id).display_name == "보관된 사람"


@pytest.mark.parametrize(
    "suffix", ["/enable", "/disable", "/unlock", "/reset-password", "/revoke-sessions"],
)
def test_every_single_write_route_refuses_an_archived_user(
    client, admin_csrf, archived_user, suffix
):
    r = client.post(
        f"/api/admin/users/{archived_user.id}{suffix}", headers=_headers(admin_csrf)
    )
    assert r.status_code == 404, f"{suffix} → {r.status_code}: {r.text}"


def test_reading_an_archived_user_still_works(client, admin_csrf, archived_user):
    """오탐 방지 — 복구하려면 그 계정을 열어 볼 수 있어야 한다. 막는 것은 **쓰기**뿐이다."""
    r = client.get(f"/api/admin/users/{archived_user.id}", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text
    assert r.json()["archived_at"] is not None

    r = client.get(
        f"/api/admin/users/{archived_user.id}/sessions", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text


def test_unarchive_still_finds_the_archived_row(client, admin_csrf, archived_user):
    """복구 경로는 당연히 그 행을 찾아야 한다 — 여기까지 404 면 보관은 되돌릴 수 없는 삭제가 된다."""
    r = client.post(
        f"/api/admin/users/{archived_user.id}/unarchive", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text

    # 복구한 뒤에는 쓰기도 다시 열린다.
    r = client.patch(
        f"/api/admin/users/{archived_user.id}",
        json={"display_name": "돌아온 사람"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["display_name"] == "돌아온 사람"


def test_a_live_user_is_still_writable(client, admin_csrf, make_user):
    """오탐 방지 — 보관하지 않은 계정의 쓰기는 그대로 200 이다."""
    target = make_user("still-here@goodmit.co.kr")
    r = client.post(f"/api/admin/users/{target.id}/disable", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text


# ── 보관은 빌려준 결재 권한도 거둔다 (xc-13) ─────────────────────────────────
#
# 위임은 권한을 빌려주는 표다. 만들 때는 비활성·보관 계정을 대리자로 지정할 수 없는데, 만든
# 뒤에 그 계정을 보관하면 그 위임이 그대로 「진행 중」으로 남았다 — 아무도 결재할 수 없는
# 위임을 화면이 살아 있다고 보여 준다.

def _delegate_to(client, csrf, *, delegator_id, delegate_id, now):
    from datetime import timedelta

    r = client.post(
        "/api/admin/approval-delegations",
        json={
            "delegator_user_id": delegator_id,
            "delegate_user_id": delegate_id,
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=3)).isoformat(),
            "reason": "휴가",
        },
        headers=_headers(csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["state"] == "active"
    return r.json()["id"]


def _delegation_state(client, csrf, delegation_id):
    body = client.get(
        "/api/admin/approval-delegations", params={"page_size": 50}, headers=_headers(csrf)
    ).json()
    rows = {row["id"]: row for row in body["items"]}
    return rows[delegation_id]["state"]


def test_archiving_the_delegate_revokes_the_delegation(
    client, login_as, make_user, fake_clock
):
    csrf = login_as("system_admin")
    me = client.get("/api/me").json()["user"]
    stand_in = make_user("stand-in@goodmit.co.kr", role="operator")
    delegation_id = _delegate_to(
        client, csrf, delegator_id=me["id"], delegate_id=stand_in.id, now=fake_clock.now()
    )

    assert client.post(
        f"/api/admin/users/{stand_in.id}/archive", headers=_headers(csrf)
    ).status_code == 200

    assert _delegation_state(client, csrf, delegation_id) == "revoked"


def test_archiving_the_delegator_revokes_the_delegation(
    client, login_as, make_user, fake_clock
):
    """위임자가 사라지면 남이 그 계정의 결재 권한을 계속 대신 쓰게 된다 — 보관은 그 계정의
    권한을 거두는 일이라 빌려준 권한도 함께 거둬야 앞뒤가 맞는다."""
    csrf = login_as("system_admin")
    boss = make_user("leaving-boss@goodmit.co.kr", role="admin")
    stand_in = make_user("stand-in2@goodmit.co.kr", role="operator")
    delegation_id = _delegate_to(
        client, csrf, delegator_id=boss.id, delegate_id=stand_in.id, now=fake_clock.now()
    )

    assert client.post(
        f"/api/admin/users/{boss.id}/archive", headers=_headers(csrf)
    ).status_code == 200

    assert _delegation_state(client, csrf, delegation_id) == "revoked"


def test_archiving_someone_else_leaves_other_delegations_alone(
    client, login_as, make_user, fake_clock
):
    """오탐 방지 — 무관한 계정을 보관했다고 남의 위임까지 거두면 안 된다."""
    csrf = login_as("system_admin")
    me = client.get("/api/me").json()["user"]
    stand_in = make_user("stand-in3@goodmit.co.kr", role="operator")
    bystander = make_user("bystander@goodmit.co.kr", role="user")
    delegation_id = _delegate_to(
        client, csrf, delegator_id=me["id"], delegate_id=stand_in.id, now=fake_clock.now()
    )

    assert client.post(
        f"/api/admin/users/{bystander.id}/archive", headers=_headers(csrf)
    ).status_code == 200

    assert _delegation_state(client, csrf, delegation_id) == "active"
