"""Dashboard '최근 주요 변경' (recent_critical_audit) role gating + maintenance flag.

recent_critical_audit is a sensitive audit slice (누가 역할 변경/롤백/승인했나) — it
must only reach roles that can read the audit log (admin/system_admin/auditor).
operator sees the dashboard but NOT the audit log (app/audit/router.py), so the
dashboard must withhold the slice from operator to avoid a bypass leak
(app/health/router.py:dashboard, app/health/service.py:build_dashboard).

The dashboard also surfaces the current maintenance_mode state so the UI can raise
a danger banner — assert it tracks the setting both on and off.
"""

import pytest

pytestmark = pytest.mark.integration


def _seed_critical_audit(db):
    from app.audit.models import AuditLog

    row = AuditLog(
        action="user.role_change",
        object_type="user",
        object_id="target-user-123",
    )
    db.add(row)
    db.commit()
    return row


def test_operator_dashboard_hides_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("operator")
    body = client.get("/api/admin/dashboard").json()
    # operator has no audit-read authority → the whole slice is withheld.
    assert body["recent_critical_audit"] == []


def test_admin_dashboard_shows_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    actions = [row["action"] for row in body["recent_critical_audit"]]
    assert "user.role_change" in actions


def test_critical_audit_row_carries_a_readable_target_name(client, login_as, db, make_user):
    """C16 재감사: "「대상」 열에 UUID 앞머리가 그대로 보인다" — object_type == "user" 인
    행은 object_id(대상 사용자 UUID)를 그 사람의 display_name 으로도 함께 내려준다.
    Dashboard.jsx 는 이 값이 있으면 그것을 보여주고, 없으면(다른 object_type 이거나
    대상이 이미 지워졌으면) 기존의 잘린 ID + 복사 표시로 물러난다."""
    from app.audit.models import AuditLog

    target = make_user(email="target@goodmit.co.kr", display_name="대상 사용자")
    row = AuditLog(action="user.role_change", object_type="user", object_id=target.id)
    db.add(row)
    db.commit()

    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    matches = [r for r in body["recent_critical_audit"] if r["object_id"] == target.id]
    assert len(matches) == 1
    assert matches[0]["object_label"] == "대상 사용자"


def test_critical_audit_row_falls_back_when_target_user_is_gone(client, login_as, db):
    """대상 사용자가 이미 지워졌거나(레코드 없음) object_type 이 user 가 아니면
    object_label 은 조용히 사라지지 않고 명시적으로 "모른다"고 말한다 — actor 해석이
    이미 지키는 것과 같은 계약(빈 값은 "삭제됨"과 "원래 없음"을 구별 못 한다)."""
    _seed_critical_audit(db)  # object_id="target-user-123" — 실제로 존재하지 않는 사용자
    login_as("admin")
    body = client.get("/api/admin/dashboard").json()
    matches = [r for r in body["recent_critical_audit"] if r["object_id"] == "target-user-123"]
    assert len(matches) == 1
    assert matches[0]["object_label"] == "(알 수 없는 사용자)"


def test_auditor_dashboard_shows_critical_audit(client, login_as, db):
    _seed_critical_audit(db)
    login_as("auditor")
    body = client.get("/api/admin/dashboard").json()
    actions = [row["action"] for row in body["recent_critical_audit"]]
    assert "user.role_change" in actions


def test_dashboard_maintenance_flag_reflects_setting(client, login_as):
    csrf = login_as("system_admin")

    # Default: maintenance off.
    body = client.get("/api/admin/dashboard").json()
    assert body["maintenance"] is False

    # Turn it on → flag flips to True.
    r = client.put(
        "/api/admin/settings/maintenance_mode",
        json={"value": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = client.get("/api/admin/dashboard").json()
    assert body["maintenance"] is True

    # Turn it back off → flag returns to False.
    r = client.put(
        "/api/admin/settings/maintenance_mode",
        json={"value": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = client.get("/api/admin/dashboard").json()
    assert body["maintenance"] is False
