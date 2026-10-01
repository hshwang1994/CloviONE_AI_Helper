"""초기 설정의 필수와 선택, 「사용하지 않음」, 저장된 상태로 읽는 메일과 AI (계획 3.5, D-520).

qa-contract-change: AI 항목의 링크가 설정의 AI 탭(`#/settings?tab=ai`)에서 AI 연결 화면(`#/ai-connection`)으로 옮겼고(D-539), 확인
전의 물음이 「연결 확인을 눌러 주세요」에서 「AI 연결 화면에서 지금 확인을 누르세요」로 바뀌었다(상태 면과 같은 함수, A8).

못박는 성질:
1. 설치가 끝났는가(`complete`)는 필수 항목(관리자 계정, 조직과 부서, TLS)만 본다. 메일과 AI 가 비어 있어도 필수가 끝나면
   완료이고, 남은 선택 항목은 `optional_pending` 이 따로 말한다.
2. 메일이나 AI 를 「사용하지 않음」으로 표시하면 설정이 비어 있는 동안 그 항목은 `skipped` 다. 값을 채우면 선택과
   무관하게 실제 상태를 보인다.
3. 메일은 설정만 채워서는 「확인 전」(확인 불가)이다. 연결 확인이나 발송이 성공해야 「됨」이다. AI 도 연결을 확인하기
   전에는 「확인 불가」다.
4. 항목마다 서버가 고치는 화면의 주소를 준다 - 같은 항목이라도 상태마다 가야 할 곳이 다르다.
5. 선택은 시스템 관리자만 바꾼다. 모르는 항목과 모르는 값은 거절한다.
6. 사용자 배너는 필수 항목이 남았을 때만 뜬다 - 메일과 AI 를 쓰지 않는 설치에서 배너가 영원히 뜨지 않는다.
"""

from __future__ import annotations

import pytest

from app.setup.checklist import USER_NOTICE_ID

pytestmark = pytest.mark.integration

CHECKLIST = "/api/admin/setup/checklist"
CHOICES = "/api/admin/settings/setup_optional_choices"


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _checklist(client):
    reply = client.get(CHECKLIST)
    assert reply.status_code == 200, reply.text
    return reply.json()


def _by_key(payload):
    return {item["key"]: item for item in payload["items"]}


def _organization(db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    db.add(Department(name="운영팀", org_id=DEFAULT_ORG_ID))
    db.commit()


def _trusted_tls(app, tmp_path, monkeypatch):
    """필수 항목 TLS 를 끝낸다 - 경로가 있고 만료가 멀다."""
    cert = tmp_path / "server.crt"
    cert.write_text("-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n", encoding="utf-8")
    monkeypatch.setattr(app.state.settings, "tls_cert_path", str(cert), raising=False)
    monkeypatch.setattr("app.health.service.cert_days_remaining", lambda settings, now=None: 200)
    monkeypatch.setattr("app.health.service.is_self_signed_cert", lambda settings: True)


def test_required_items_decide_completion(client, app, db, login_as, tmp_path, monkeypatch):
    login_as("system_admin")
    before = _checklist(client)
    assert before["complete"] is False and "organization" in before["required_remaining"]
    assert {i["key"]: i["required"] for i in before["items"]} == {
        "admin_account": True, "mail": False, "organization": True, "llm": False, "integrations": False,
        "tls": True,
    }

    _organization(db)
    _trusted_tls(app, tmp_path, monkeypatch)
    after = _checklist(client)
    assert after["complete"] is True and after["required_complete"] is True
    assert set(after["optional_pending"]) == {"mail", "llm"}, "선택 항목이 완료를 막았거나 사라졌다"
    assert _by_key(after)["tls"]["state"] == "done", "설치가 만든 자체 서명 인증서는 끝난 것이다"
    assert after["summary"] == "정상 설치입니다."


def test_unused_optional_items_are_skipped_until_configured(client, app, db, login_as, tmp_path, monkeypatch):
    from tests.integration.test_password_reset import configure_smtp

    csrf = login_as("system_admin")
    _organization(db)
    _trusted_tls(app, tmp_path, monkeypatch)
    reply = client.put(CHOICES, json={"value": {"mail": "unused", "llm": "unused"}}, headers=_h(csrf))
    assert reply.status_code == 200, reply.text

    payload = _checklist(client)
    items = _by_key(payload)
    assert (items["mail"]["state"], items["llm"]["state"]) == ("skipped", "skipped")
    assert payload["optional_pending"] == [] and payload["skipped"] == ["mail", "llm"]
    assert payload["summary"] == "정상 설치입니다(메일 사용 안 함, AI 사용 안 함)."

    # 값을 채우면 선택과 무관하게 실제 상태를 보인다 - 「안 쓰기로 했다」 뒤에 실패를 숨기지 않는다.
    configure_smtp(client.app)
    mail = _by_key(_checklist(client))["mail"]
    assert mail["state"] == "unknown" and mail["configured"] is True


def test_mail_is_done_only_after_a_real_check(client, db, login_as, fake_clock):
    from app.mail import health as mail_health
    from app.mail.config import config_from_db
    from tests.integration.test_password_reset import configure_smtp

    login_as("system_admin")
    configure_smtp(client.app)
    mail = _by_key(_checklist(client))["mail"]
    assert mail["state"] == "unknown" and mail["href"] == "#/mail"
    assert "연결 확인" in mail["question"]

    with client.app.state.session_factory() as s:
        mail_health.record_result(s, config_from_db(s), ok=True, now=fake_clock.now(), source="verify")
        s.commit()
    mail = _by_key(_checklist(client))["mail"]
    assert mail["state"] == "done" and mail["checked_at"] is not None


def test_unconfigured_mail_points_at_the_settings_row(client, login_as):
    login_as("system_admin")
    mail = _by_key(_checklist(client))["mail"]
    assert (mail["state"], mail["href"], mail["link_label"]) == ("todo", "#/settings?setting=smtp", "메일 설정 열기")
    assert mail["configured"] is False and "사용하지 않음" in mail["action"]


def test_ai_is_a_question_until_the_connection_is_checked(client, login_as):
    from tests.fakes.ai import configure_ai

    login_as("system_admin")
    configure_ai(client.app)
    llm = _by_key(_checklist(client))["llm"]
    assert llm["state"] == "unknown" and "지금 확인" in llm["question"]
    assert llm["href"] == "#/ai-connection" and llm["link_label"] == "AI 연결 열기"


def test_only_a_system_admin_changes_the_choices_and_values_are_checked(client, login_as):
    csrf = login_as("admin", email="setup-admin@goodmit.co.kr")
    assert client.put(CHOICES, json={"value": {"mail": "unused"}}, headers=_h(csrf)).status_code == 403
    csrf = login_as("system_admin")
    for bad in ({"sms": "unused"}, {"mail": "maybe"}, ["mail"]):
        assert client.put(CHOICES, json={"value": bad}, headers=_h(csrf)).status_code == 422, bad


def test_optional_gaps_never_raise_the_user_banner(client, app, db, login_as, tmp_path, monkeypatch):
    """메일과 AI 를 안 쓰는 설치에서 사용자 배너가 영원히 뜨면 사람들은 배너를 안 읽게 된다."""
    _organization(db)
    login_as("user")
    notices = client.get("/api/system/status").json()["notices"]
    assert [n for n in notices if n["id"] == USER_NOTICE_ID] == [], "선택 항목 때문에 사용자 배너가 떴다"
