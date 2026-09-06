"""전역 자원의 **범위** 게이트 — 부서 범위 관리자는 설치 한 벌을 바꾸지 못한다.

## 무엇이 뚫려 있었나

`CONSOLE_WRITE_ROLES` 는 역할만 본다. 그런데 이 제품의 `admin` 은 부서 범위로 좁혀질 수
있고(`admin_scope="dept"`), 그 사람이 지나는 문 뒤에는 부서라는 개념이 아예 없는 값들이
있었다. 실측(2026-09-06, 부서 범위 관리자 계정):

  * `PUT /api/admin/settings/maintenance_mode {"value": true}` → 200. 그 뒤 다른 부서
    일반 사용자의 `POST /api/tickets` 가 503 이 됐다 — 한 팀의 관리자가 전사 쓰기를 멈췄다.
  * `PUT /api/admin/settings/{password_policy,allowed_email_domains,backup_schedule}` → 200.
  * `PUT /api/admin/feature-flags/games_enabled {"enabled": false}` → 200 (전 조직에서
    그 모듈이 사라진다).
  * `POST /api/admin/mail/test` → 200 (설치 한 벌의 SMTP 계정으로 발송).
  * `POST /api/admin/integrations` → 201, `PATCH`·`enable`·`disable`·`rollback` → 200
    (이 서버가 밖으로 나가는 경로를 새로 열고 켠다).

같은 저장소가 공지·전역 쿼터·정합성 일괄 지정·조직 생성에서는 정확히 같은 이유로 이미
403 을 낸다. 빠진 넷을 `app/core/scope.py::require_global_management` 하나로 모은다.

## 이 파일이 못박는 것

「막혔다」가 아니라 **「403 이고 값이 안 바뀌었다」**, 그리고 **반례**로 「전역 범위
관리자와 시스템 관리자는 그대로 된다」다. 반례가 없으면 전부 잠가 놓고도 초록불이 된다.
읽기(GET)는 그대로 열려 있어야 한다 — 부서 관리자도 자기 화면에서 무엇이 걸려 있는지는
봐야 하고, 이 게이트는 쓰기만 좁힌다.

qa-contract-change: 시험 메일 거절 문구를 「메일 발송 설정을 바꿀」에서 「시험 메일을 보낼」로 옮긴다 (R2-04).
"""

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
D_OPS = "dept-ops-0001"

INTEGRATION = {
    "name": "scope-gate-service",
    "provider_type": "http_service",
    "base_url": "https://api.anthropic.com",
    "auth_type": "none",
    "enabled": False,
}


@pytest.fixture()
def dept(db):
    row = Department(id=D_OPS, name="서비스운영팀", org_id=DEFAULT_ORG_ID, parent_id=None)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def actors(db, make_user, dept):
    """전역 관리자 / 부서 범위 관리자 / 시스템 관리자. 역할은 같고 **범위만** 다르다."""
    made = {}

    def _mk(key, email, role, *, scope="global", scope_dept=None):
        user = make_user(email=email, role=role, display_name=key)
        user.department_id = D_OPS
        user.admin_scope = scope
        user.scope_dept_id = scope_dept
        user.scope_org_id = DEFAULT_ORG_ID if scope != "global" else None
        db.add(user)
        made[key] = user

    _mk("global_admin", "gate-ga@goodmit.co.kr", "admin")
    _mk("dept_admin", "gate-da@goodmit.co.kr", "admin", scope="dept", scope_dept=D_OPS)
    _mk("system_admin", "gate-sa@goodmit.co.kr", "system_admin")
    db.commit()
    return {k: v.email for k, v in made.items()}


def _login(client, email):
    response = client.post("/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _settings_value(client, key):
    body = client.get("/api/admin/settings")
    assert body.status_code == 200, body.text
    return body.json()["settings"][key]["value"]


def _flag_value(client, name):
    body = client.get("/api/admin/feature-flags")
    assert body.status_code == 200, body.text
    return {row["name"]: row["value"] for row in body.json()["items"]}[name]


@pytest.fixture()
def flags_file(settings):
    """플래그 파일을 바이트로 백업했다가 되돌린다 — 시험이 저장소 파일을 남기면 안 된다."""
    from app.core.feature_flags import flags_path, reset_cache

    path = flags_path(settings.config_dir)
    original = path.read_bytes() if path.exists() else None
    yield path
    if original is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(original)
    reset_cache()


# ── 설정 표 ──────────────────────────────────────────────────────────────────


def test_dept_scoped_admin_cannot_change_settings_and_value_is_unchanged(client, actors):
    headers = _login(client, actors["dept_admin"])
    assert _settings_value(client, "maintenance_mode") is False

    response = client.put(
        "/api/admin/settings/maintenance_mode", json={"value": True}, headers=headers
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["message"] == (
        "시스템 설정은 전체 범위 관리자만 바꿀 수 있습니다."
    )
    # 거절이 값을 건드리지 않았다 — 「막혔다」와 「막혔는데 이미 켜졌다」는 다른 사실이다.
    assert _settings_value(client, "maintenance_mode") is False


def test_dept_scoped_admin_cannot_dry_run_or_rollback_settings(client, actors):
    headers = _login(client, actors["dept_admin"])

    dry_run = client.post(
        "/api/admin/settings/trash_retention_days/dry-run", json={"value": 9}, headers=headers
    )
    assert dry_run.status_code == 403, dry_run.text

    rollback = client.post(
        "/api/admin/settings/trash_retention_days/rollback", json={"version": 1}, headers=headers
    )
    assert rollback.status_code == 403, rollback.text


def test_refused_write_is_recorded_but_a_successful_read_is_not(client, actors, db):
    """막힌 **쓰기** 시도는 감사에 남는다. 읽기는 안 남는다.

    범위 게이트는 핸들러 안에서 판정하므로 역할 게이트가 쓰는
    `app/core/deps.py::audit_forbidden_write` 자리를 지나지 않는다 — 라우터가 직접 부르지
    않으면 「점검 모드를 켜려던 시도」가 저장소 어디에도 남지 않는다.
    """
    import json as _json

    from app.audit.models import AuditLog
    from app.core.deps import FORBIDDEN_AUDIT_ACTION

    def _denied():
        return db.query(AuditLog).filter(AuditLog.action == FORBIDDEN_AUDIT_ACTION).all()

    headers = _login(client, actors["dept_admin"])
    # id 로 「이번에 생긴 행」을 가른다. 조회에 order_by 가 없어 `rows[-4:]` 같은 자르기는
    # PostgreSQL 이 돌려주는 순서에 기대게 되고, 그러면 무엇을 세고 있는지가 불확실해진다.
    before_ids = {row.id for row in _denied()}

    assert client.get("/api/admin/settings").status_code == 200
    assert {row.id for row in _denied()} == before_ids, "읽기 거부가 아닌 정상 조회가 감사에 남았다"

    refused = [
        ("PUT", "/api/admin/settings/maintenance_mode", lambda: client.put(
            "/api/admin/settings/maintenance_mode", json={"value": True}, headers=headers
        )),
        ("PUT", "/api/admin/feature-flags/board_enabled", lambda: client.put(
            "/api/admin/feature-flags/board_enabled", json={"enabled": False}, headers=headers
        )),
        ("POST", "/api/admin/mail/test", lambda: client.post(
            "/api/admin/mail/test", headers=headers
        )),
        ("POST", "/api/admin/integrations", lambda: client.post(
            "/api/admin/integrations", json=INTEGRATION, headers=headers
        )),
    ]
    for _method, _path, call in refused:
        assert call().status_code == 403

    new_rows = [row for row in _denied() if row.id not in before_ids]
    assert len(new_rows) == 4, "막힌 쓰기 넷 중 일부가 감사에 안 남았다"
    assert {row.result for row in new_rows} == {"failure"}
    # **어느 문이 막혔는지**까지 남아야 조사에 쓸 수 있다. 결과 열만 보면 「네 endpoint 가
    # 각각 기록됐다」와 「한 endpoint 가 네 번 기록됐다」가 구별되지 않는다.
    recorded = {
        (payload.get("method"), payload.get("path"))
        for payload in (_json.loads(row.after_json or "{}") for row in new_rows)
    }
    assert recorded == {(method, path) for method, path, _call in refused}


def test_dept_scoped_admin_still_reads_settings(client, actors):
    """게이트는 **쓰기만** 좁힌다. 읽기까지 막으면 화면이 통째로 빈다."""
    _login(client, actors["dept_admin"])
    assert client.get("/api/admin/settings").status_code == 200
    assert client.get("/api/admin/settings/maintenance_mode/versions").status_code == 200


def test_global_admin_and_system_admin_still_change_settings(client, actors):
    """반례. 이것이 없으면 전부 잠가 놓고도 위 시험들이 초록불이다."""
    for key in ("global_admin", "system_admin"):
        headers = _login(client, actors[key])
        response = client.put(
            "/api/admin/settings/trash_retention_days", json={"value": 9}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert _settings_value(client, "trash_retention_days") == 9

        dry_run = client.post(
            "/api/admin/settings/trash_retention_days/dry-run",
            json={"value": 8}, headers=headers,
        )
        assert dry_run.status_code == 200, dry_run.text

        versions = client.get("/api/admin/settings/trash_retention_days/versions")
        assert versions.status_code == 200, versions.text
        latest = versions.json()["items"][-1]["version"]
        rollback = client.post(
            "/api/admin/settings/trash_retention_days/rollback",
            json={"version": latest}, headers=headers,
        )
        assert rollback.status_code == 200, rollback.text


# ── 기능 플래그 ──────────────────────────────────────────────────────────────


def test_dept_scoped_admin_cannot_toggle_feature_flags(client, actors, flags_file):
    headers = _login(client, actors["dept_admin"])
    assert _flag_value(client, "board_enabled") is True

    response = client.put(
        "/api/admin/feature-flags/board_enabled", json={"enabled": False}, headers=headers
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["message"] == (
        "기능 플래그는 전체 범위 관리자만 바꿀 수 있습니다."
    )
    assert _flag_value(client, "board_enabled") is True


def test_global_admin_still_toggles_feature_flags(client, actors, flags_file):
    headers = _login(client, actors["global_admin"])
    response = client.put(
        "/api/admin/feature-flags/board_enabled", json={"enabled": False}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert _flag_value(client, "board_enabled") is False


# ── 메일 시험 발송 ───────────────────────────────────────────────────────────


def test_dept_scoped_admin_cannot_send_test_mail(client, actors, db):
    from app.mail.models import MailDelivery

    headers = _login(client, actors["dept_admin"])
    before = db.query(MailDelivery).count()

    response = client.post("/api/admin/mail/test", headers=headers)
    assert response.status_code == 403, response.text
    # 거절된 것은 **발송**이다. 「설정을 바꿀 수 없다」고 답하면 건드린 적 없는 설정 화면을
    # 찾아가게 만든다 — 서버 문구는 방금 누른 단추(「시험 메일 보내기」)를 그대로 부른다.
    assert response.json()["error"]["message"] == (
        "시험 메일은 전체 범위 관리자만 보낼 수 있습니다."
    )
    # 큐에 아무것도 안 들어갔다.
    assert db.query(MailDelivery).count() == before
    # 진단은 그대로 볼 수 있다.
    assert client.get("/api/admin/mail/status").status_code == 200


def test_global_admin_still_sends_test_mail(client, actors):
    headers = _login(client, actors["global_admin"])
    response = client.post("/api/admin/mail/test", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["delivery"]["kind"] == "test"


# ── 외부 연동 ────────────────────────────────────────────────────────────────


def test_dept_scoped_admin_cannot_write_integrations(client, actors):
    admin_headers = _login(client, actors["system_admin"])
    created = client.post(
        "/api/admin/integrations", json=INTEGRATION, headers=admin_headers
    )
    assert created.status_code == 201, created.text
    row_id = created.json()["integration"]["id"]

    headers = _login(client, actors["dept_admin"])
    create = client.post(
        "/api/admin/integrations",
        json={**INTEGRATION, "name": "scope-gate-nope"},
        headers=headers,
    )
    assert create.status_code == 403, create.text
    assert create.json()["error"]["message"] == "외부 연동은 전체 범위 관리자만 바꿀 수 있습니다."

    patch = client.patch(
        f"/api/admin/integrations/{row_id}", json={"description": "부서가 고침"}, headers=headers
    )
    assert patch.status_code == 403, patch.text

    enable = client.post(f"/api/admin/integrations/{row_id}/enable", headers=headers)
    assert enable.status_code == 403, enable.text

    disable = client.post(f"/api/admin/integrations/{row_id}/disable", headers=headers)
    assert disable.status_code == 403, disable.text

    rollback = client.post(
        f"/api/admin/integrations/{row_id}/rollback", json={"version": 1}, headers=headers
    )
    assert rollback.status_code == 403, rollback.text

    # 목록도 상세도 그대로 읽힌다. 그리고 아무것도 안 바뀌었다.
    listed = client.get("/api/admin/integrations")
    assert listed.status_code == 200, listed.text
    assert [r["name"] for r in listed.json()["items"]] == ["scope-gate-service"]
    detail = client.get(f"/api/admin/integrations/{row_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["integration"]["description"] is None
    assert detail.json()["integration"]["enabled"] is False


def test_a_dept_scoped_admin_can_still_run_a_health_check(client, actors, db, fake_http):
    """건강 검사는 **일부러** 이 문 밖이다 — 그 결정을 문서가 아니라 시험으로 고정한다.

    그것도 쓰기이긴 하다(`last_health_status`·`last_health_at` 을 쓰고 저장된 secret 을 실어
    보낸다). 그런데도 여는 이유는 대상 주소를 이 문 밖에서 정할 수 없고, 쓰는 두 칸이 설정이
    아니라 진단 결과이며, 「지금 붙는가」가 장애 대응의 첫 질문이기 때문이다
    (`app/integrations/router.py::_guard_scope`). 이 시험이 없으면 다음 사람이 「쓰기인데 왜
    열려 있지」로 막아 야간 당직의 진단 수단을 없앤다.
    """
    from app.integrations.models import Integration

    admin_headers = _login(client, actors["system_admin"])
    created = client.post(
        "/api/admin/integrations", json=INTEGRATION, headers=admin_headers
    )
    assert created.status_code == 201, created.text
    row_id = created.json()["integration"]["id"]

    headers = _login(client, actors["dept_admin"])
    fake_http.on("https://api.anthropic.com", json_body={})
    health = client.post(f"/api/admin/integrations/{row_id}/health", headers=headers)
    assert health.status_code == 200, health.text
    assert health.json()["status"] in {"up", "down"}

    db.expire_all()
    row = db.get(Integration, row_id)
    assert row.last_health_at is not None, "진단 결과가 기록되지 않았다"
    # 반례 — 열린 것은 진단 하나다. 같은 사람이 그 대상의 **주소**를 바꾸는 것은 여전히 막힌다.
    patch = client.patch(
        f"/api/admin/integrations/{row_id}",
        json={"base_url": "https://elsewhere.example.com"}, headers=headers,
    )
    assert patch.status_code == 403, patch.text


# ── 시스템 관리자는 자기 손으로 자기를 잠그지 못한다 ─────────────────────────
#
# `admin_scope` 는 역할과 무관하게 아무 계정에나 걸린다(`_apply_admin_scope` 는 값만 본다).
# 그래서 `PATCH /api/admin/users/{id} {"admin_scope":"dept"}` 한 번이면 system_admin 도
# 좁혀지고, 그 순간 이 파일이 세는 모든 문이 닫힌다 — 설정·기능 깃발·연동·메일·조직·
# 프롬프트·스케줄이 한꺼번에. system_admin 이 하나뿐인 설치에서는 되돌릴 사람이 바로 그
# 잠긴 사람이라, API 로는 복구할 방법이 없고 DB 직접 수정만 남는다.


def test_a_system_admin_narrowed_to_one_department_is_not_locked_out(
    client, db, make_user, dept
):
    user = make_user(
        email="gate-sa-scoped@goodmit.co.kr", role="system_admin", display_name="좁혀진 시스템 관리자"
    )
    user.department_id = D_OPS
    user.admin_scope = "dept"
    user.scope_dept_id = D_OPS
    user.scope_org_id = DEFAULT_ORG_ID
    db.add(user)
    db.commit()

    headers = _login(client, user.email)
    saved = client.put(
        "/api/admin/settings/trash_retention_days", json={"value": 9}, headers=headers
    )
    assert saved.status_code == 200, (
        f"좁혀진 시스템 관리자가 설치 한 벌을 못 고친다 — 포털이 통째로 잠겼다: {saved.text}"
    )
    assert _settings_value(client, "trash_retention_days") == 9

    # 그리고 자기 범위를 스스로 되돌릴 수 있다. 이것이 없으면 「잠기지 않았다」가 반쪽이다.
    fixed = client.patch(
        f"/api/admin/users/{user.id}", json={"admin_scope": "global"}, headers=headers
    )
    assert fixed.status_code == 200, fixed.text


def test_a_dept_scoped_plain_admin_is_still_refused(client, actors):
    """반례 — 열린 것은 system_admin 하나다. 이 시험이 없으면 위 수정이 「범위 게이트를
    통째로 없앴다」로도 초록불이 된다."""
    headers = _login(client, actors["dept_admin"])
    before = _settings_value(client, "trash_retention_days")
    response = client.put(
        "/api/admin/settings/trash_retention_days", json={"value": before + 3}, headers=headers
    )
    assert response.status_code == 403, response.text
    assert _settings_value(client, "trash_retention_days") == before


def test_system_admin_still_writes_integrations(client, actors):
    headers = _login(client, actors["system_admin"])
    created = client.post("/api/admin/integrations", json=INTEGRATION, headers=headers)
    assert created.status_code == 201, created.text
    row_id = created.json()["integration"]["id"]

    patch = client.patch(
        f"/api/admin/integrations/{row_id}", json={"description": "전역이 고침"}, headers=headers
    )
    assert patch.status_code == 200, patch.text
    assert client.post(f"/api/admin/integrations/{row_id}/enable", headers=headers).status_code == 200
