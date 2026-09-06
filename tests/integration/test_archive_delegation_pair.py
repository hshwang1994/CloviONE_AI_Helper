"""계정 보관이 거둔 승인 위임은 **누가 거뒀는지 남고, 되돌리면 함께 돌아온다** (R5-06).

계정을 보관하면 그 계정에 걸린 살아 있는 승인 위임이 전부 회수된다
(`tests/integration/test_admin_user_archive.py` 가 그 규칙을 센다). 그 회수에는 두 구멍이
있었다.

① **행위자가 없다.** 위임 표는 그 자체가 감사 근거인데(`app/approvals/models.py`),
   보관 경로는 `revoked_at` 만 찍고 지나갔다 — 위임 화면에는 「거둠」이 행위자 없이 남고
   「누가 이 위임을 거뒀나」에 아무도 답할 수 없다. 사람이 위임 화면에서 거두는 경로는
   이미 같은 이름의 감사 행을 남긴다.

② **되돌려도 안 돌아온다.** 오프보딩을 잘못 눌러 1분 안에 되돌리는 일은 실제로 있고
   (`app/offboarding/service.py::undo`), 그때 계정·티켓·채팅방은 돌아오는데 위임만
   그대로 거둬져 있었다. 대리 결재자는 아무 말 없이 권한을 잃고, 잃은 사람도 되돌린
   사람도 그 사실을 화면 어디에서도 볼 수 없다.

되살리는 것은 **그 보관이 거둔 것**뿐이다 — 사람이 손으로 거둔 위임까지 되살아나면
되돌리기가 남의 결정을 뒤집는 일이 된다. 마지막 시험이 그 경계를 센다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _delegate_to(client, csrf, *, delegator_id, delegate_id, now):
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


def _state(client, csrf, delegation_id) -> str:
    body = client.get(
        "/api/admin/approval-delegations", params={"page_size": 50}, headers=_headers(csrf)
    ).json()
    return {row["id"]: row for row in body["items"]}[delegation_id]["state"]


def _audit(db, action: str, object_id: str) -> list:
    from app.audit.models import AuditLog

    return (
        db.query(AuditLog)
        .filter(AuditLog.action == action, AuditLog.object_id == object_id)
        .all()
    )


def test_archiving_records_who_revoked_the_delegation(
    client, login_as, make_user, db, fake_clock
):
    """「누가 이 위임을 거뒀나」에 답이 있어야 한다 — 표 자체가 감사 근거다."""
    csrf = login_as("system_admin")
    me = client.get("/api/me").json()["user"]
    stand_in = make_user("pair-stand-in@goodmit.co.kr", role="operator")
    delegation_id = _delegate_to(
        client, csrf, delegator_id=me["id"], delegate_id=stand_in.id, now=fake_clock.now()
    )

    assert client.post(
        f"/api/admin/users/{stand_in.id}/archive", headers=_headers(csrf)
    ).status_code == 200

    assert _state(client, csrf, delegation_id) == "revoked"
    rows = _audit(db, "approval_delegation.revoke", delegation_id)
    assert len(rows) == 1, "보관이 거둔 위임에 감사 행이 없다"
    assert rows[0].user_id == me["id"], "거둔 사람이 기록되지 않았다"
    assert "user.archive" in (rows[0].after_json or ""), (
        "왜 거뒀는지가 없다 — 사람이 누른 회수와 구별할 수 없다"
    )


def test_undoing_the_archive_brings_the_delegation_back(
    client, login_as, make_user, db, fake_clock
):
    """잘못 보관한 것을 되돌리면 대리 결재자의 권한도 돌아와야 한다."""
    csrf = login_as("system_admin")
    me = client.get("/api/me").json()["user"]
    stand_in = make_user("pair-undo@goodmit.co.kr", role="operator")
    delegation_id = _delegate_to(
        client, csrf, delegator_id=me["id"], delegate_id=stand_in.id, now=fake_clock.now()
    )
    assert client.post(
        f"/api/admin/users/{stand_in.id}/archive", headers=_headers(csrf)
    ).status_code == 200
    assert _state(client, csrf, delegation_id) == "revoked"

    fake_clock.advance(60)
    assert client.post(
        f"/api/admin/users/{stand_in.id}/unarchive", headers=_headers(csrf)
    ).status_code == 200

    assert _state(client, csrf, delegation_id) == "active", (
        "계정은 돌아왔는데 위임만 거둬진 채로 남았다"
    )
    assert len(_audit(db, "approval_delegation.restore", delegation_id)) == 1, (
        "되살린 사실도 기록해야 한다 — 권한이 다시 열리는 일이다"
    )


def test_a_delegation_a_person_revoked_by_hand_stays_revoked(
    client, login_as, make_user, db, fake_clock
):
    """반례 — 되돌리기는 그 보관이 거둔 것만 되살린다. 사람의 결정을 뒤집지 않는다."""
    csrf = login_as("system_admin")
    me = client.get("/api/me").json()["user"]
    stand_in = make_user("pair-handrevoked@goodmit.co.kr", role="operator")
    by_hand = _delegate_to(
        client, csrf, delegator_id=me["id"], delegate_id=stand_in.id, now=fake_clock.now()
    )

    assert client.post(
        f"/api/admin/approval-delegations/{by_hand}/revoke", headers=_headers(csrf)
    ).status_code == 200
    assert _state(client, csrf, by_hand) == "revoked"

    # 사람이 거둔 시각과 보관 시각은 다르다 — 실제 시계에서도 그렇다.
    fake_clock.advance(60)
    assert client.post(
        f"/api/admin/users/{stand_in.id}/archive", headers=_headers(csrf)
    ).status_code == 200
    fake_clock.advance(60)
    assert client.post(
        f"/api/admin/users/{stand_in.id}/unarchive", headers=_headers(csrf)
    ).status_code == 200

    assert _state(client, csrf, by_hand) == "revoked", (
        "사람이 거둔 위임을 계정 복구가 되살렸다"
    )
    assert _audit(db, "approval_delegation.restore", by_hand) == []
