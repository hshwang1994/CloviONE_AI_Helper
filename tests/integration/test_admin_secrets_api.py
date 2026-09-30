"""비밀 값 관리 API (계획 2.3).

값은 들어오기만 하고 나가지 않는다. 확인하는 것:
- 범위 없는 system_admin 만 쓴다(부서 관리자와 일반 사용자는 403).
- 응답과 감사 기록에 값이 없다.
- 개발 경로(웹이 직접 쓸 수 있는 디렉터리)에서는 파일이 실제로 생긴다.
- 운영 경로(웹이 못 쓰는 디렉터리)에서는 헬퍼로 넘어가고, 헬퍼가 없으면 되는 척하지 않는다.
- 범용 시스템 액션 경로로는 비밀 값 액션을 부를 수 없다.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.core.secret_store import SecretStore
from app.sysops.client import STATUS_NOT_INSTALLED, STATUS_OK, HelperReply

pytestmark = pytest.mark.integration

VALUE = "sk-ant-api03-test-secret-value"


class _ReadOnlyProvider:
    """운영 설치처럼 쓸 수 없는 디렉터리를 흉내 낸다. 읽기는 진짜 provider 에 맡긴다."""

    def __init__(self, real) -> None:
        self._real = real

    def writable(self) -> bool:
        return False

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FakeHelper:
    def __init__(self, reply: HelperReply) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict]] = []

    def call(self, action, params=None):
        self.calls.append((action, dict(params or {})))
        return self.reply


@pytest.fixture()
def restore_store(client):
    yield
    client.app.state.secret_store = None


def test_only_the_portal_operator_can_manage_secrets(client, login_as):
    for role in ("admin", "operator", "user"):
        csrf = login_as(role)
        assert client.get("/api/admin/secrets").status_code == 403, role
        r = client.put("/api/admin/secrets/smtp.password", json={"value": VALUE},
                       headers={"X-CSRF-Token": csrf})
        assert r.status_code == 403, role


def test_a_secret_is_written_but_never_read_back(client, login_as, app):
    csrf = login_as("system_admin")
    r = client.put("/api/admin/secrets/ai.anthropic.api_key", json={"value": VALUE},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored"] is True and body["changed"] is True
    assert body["updated_at"]
    assert VALUE not in r.text

    path = app.state.settings.secrets_dir / "ai.anthropic.api_key"
    assert path.read_text(encoding="utf-8") == VALUE

    listing = client.get("/api/admin/secrets")
    assert listing.status_code == 200
    assert VALUE not in listing.text
    item = next(i for i in listing.json()["items"] if i["slot"] == "ai.anthropic.api_key")
    assert item["stored"] is True


def test_the_audit_record_names_the_slot_but_not_the_value(client, login_as, db):
    csrf = login_as("system_admin")
    client.put("/api/admin/secrets/smtp.password", json={"value": VALUE},
               headers={"X-CSRF-Token": csrf})
    rows = db.execute(
        select(AuditLog).where(AuditLog.action == "secret.write")
    ).scalars().all()
    assert rows, "비밀 값 교체가 감사에 남지 않았다"
    for row in rows:
        assert row.object_id == "smtp.password"
        dumped = json.dumps([row.before_json, row.after_json], default=str)
        assert VALUE not in dumped, "감사 기록에 비밀 값이 남았다"


def test_delete_removes_the_file(client, login_as, app):
    csrf = login_as("system_admin")
    client.put("/api/admin/secrets/ai.openai.api_key", json={"value": VALUE},
               headers={"X-CSRF-Token": csrf})
    r = client.delete("/api/admin/secrets/ai.openai.api_key", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["stored"] is False
    assert not (app.state.settings.secrets_dir / "ai.openai.api_key").exists()


def test_unknown_or_product_owned_slots_are_refused(client, login_as):
    csrf = login_as("system_admin")
    for slot in ("session_secret", "ai.openai.chatgpt", "..%2Fpasswd"):
        r = client.put(f"/api/admin/secrets/{slot}", json={"value": VALUE},
                       headers={"X-CSRF-Token": csrf})
        assert r.status_code in (404, 422), (slot, r.status_code)


def test_a_value_with_a_line_break_is_refused_without_echoing_it(client, login_as):
    csrf = login_as("system_admin")
    r = client.put("/api/admin/secrets/smtp.password", json={"value": "abc\nhidden-part"},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422
    assert "hidden-part" not in r.text


def test_production_path_goes_through_the_helper(client, login_as, app, restore_store):
    helper = _FakeHelper(HelperReply(available=True, status=STATUS_OK, ok=True, changed=True,
                                     detail="비밀 값을 저장했습니다.", data={}))
    app.state.secret_store = SecretStore(_ReadOnlyProvider(app.state.secret_provider), helper)
    csrf = login_as("system_admin")
    r = client.put("/api/admin/secrets/smtp.password", json={"value": VALUE},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert helper.calls == [("secret.write", {"name": "smtp.password", "value": VALUE})]


def test_a_missing_helper_never_pretends_to_save(client, login_as, app, restore_store):
    helper = _FakeHelper(HelperReply.unavailable(STATUS_NOT_INSTALLED, "도우미가 없습니다."))
    app.state.secret_store = SecretStore(_ReadOnlyProvider(app.state.secret_provider), helper)
    csrf = login_as("system_admin")
    r = client.put("/api/admin/secrets/smtp.password", json={"value": VALUE},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, r.text
    assert "도우미" in r.json()["error"]["message"]
    assert VALUE not in r.text


def test_the_generic_system_route_refuses_secret_actions(client, login_as):
    csrf = login_as("system_admin")
    r = client.post("/api/admin/system/secret.write",
                    json={"params": {"name": "smtp.password", "value": VALUE}},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, r.text
    overview = client.get("/api/admin/system")
    names = [a["name"] for a in overview.json()["actions"]]
    assert not [n for n in names if n.startswith("secret.")], names
