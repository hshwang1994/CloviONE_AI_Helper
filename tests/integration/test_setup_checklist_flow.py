# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""초기 설정 체크리스트 — 상태 일곱 · 선택 저장 · 요약 띠 · 메일 방식별 표 · 배너 비용 (계획 S1 · M6 · A8, D-534).

못박는 것:
  1. 선택 값은 전용 API(`PUT /api/admin/setup/choices/{key}`) 하나로 바꾼다 — 시스템 관리자만(관리자 · 운영자 · 감사자 403), CSRF
     필수, 모르는 항목 404 · 모르는 값 422. 서버가 그 키 하나만 행 잠금 안에서 합치고(다른 선택을 지킨다) 감사(`setting.update`)를
     남기며 새 체크리스트를 돌려준다.
  2. 줄마다 화면 상태가 있다 — 완료 · 해야 함 · 확인 필요 · 정하지 않음 · 문제 있음 · 사용하지 않음 · 앞 항목 대기.
  3. 요약 띠: 필수가 남으면 그 수와 다음 할 일, 끝나면 「기본 설정이 끝났습니다」와 선택 기능의 상태(다섯 시나리오).
  4. 메일(M6): 꺼짐은 숨길 수 있는 「정하지 않음」, 켰는데 비면 숨길 수 없는 「해야 함」, 실패는 「문제 있음」. 로컬 릴레이는 구성
     요소 → 앱 → 릴레이 → 준비 점검 → 바깥 전달 순서로 보고, 바깥 전달을 본 뒤에만 완료다.
  5. TLS: 인증서 경로가 없는 설치는 「외부 프록시가 맡음」을 고를 수 있고 고르면 완료(메모가 붙는다).
  6. `/api/system/status` 의 배너 판정은 조직 판정 하나뿐이고 60초 동안 다시 쓴다(모든 사용자의 폴링이 여섯 판정을 돌지 않는다).
"""

from __future__ import annotations

import json
import threading

import pytest

from app.audit.models import AuditLog
from tests.integration.test_mail_relay_api import FakeHelper
from tests.integration.test_setup_required_optional import _organization, _trusted_tls

pytestmark = pytest.mark.integration

CHECKLIST = "/api/admin/setup/checklist"


def _choice(client, key, value, csrf):
    return client.put(f"/api/admin/setup/choices/{key}", json={"value": value}, headers={"X-CSRF-Token": csrf})


def _items(payload):
    return {item["key"]: item for item in payload["items"]}


def _stored(client):
    from app.settings.models import AppSetting

    with client.app.state.session_factory() as s:
        row = s.get(AppSetting, "setup_optional_choices")
        return json.loads(row.value_json) if row else None


# ── 1. 선택 저장 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["admin", "operator", "auditor"])
def test_only_a_system_admin_saves_a_choice(client, login_as, role):
    csrf = login_as(role, email=f"setup-choice-{role}@goodmit.co.kr")
    assert _choice(client, "mail", "unused", csrf).status_code == 403
    assert _stored(client) is None


def test_a_choice_needs_the_csrf_token(client, login_as):
    login_as("system_admin")
    r = client.put("/api/admin/setup/choices/mail", json={"value": "unused"})
    assert r.status_code == 403


def test_one_key_is_merged_audited_and_the_new_checklist_comes_back(client, db, login_as):
    csrf = login_as("system_admin")
    first = _choice(client, "mail", "unused", csrf)
    assert first.status_code == 200, first.text
    assert _items(first.json())["mail"]["status"] == "skipped"
    second = _choice(client, "tls", "proxy", csrf)
    assert second.status_code == 200, second.text
    assert _stored(client) == {"mail": "unused", "llm": "use", "tls": "proxy"}, "앞의 선택을 지켜야 한다"
    tls = _items(second.json())["tls"]
    assert tls["status"] == "done" and any("외부 프록시가 TLS를 맡는다고" in n for n in tls["notes"])
    assert {"key": "tls", "value": "app", "label": "이 서버의 인증서 사용"} in tls["choices"]
    audits = db.query(AuditLog).filter(AuditLog.action == "setting.update",
                                       AuditLog.object_id == "setup_optional_choices").all()
    assert len(audits) == 2


def test_unknown_keys_values_and_fields_are_refused(client, login_as):
    csrf = login_as("system_admin")
    assert _choice(client, "sms", "unused", csrf).status_code == 404
    assert _choice(client, "mail", "proxy", csrf).status_code == 422
    assert _choice(client, "tls", "unused", csrf).status_code == 422
    r = client.put("/api/admin/setup/choices/mail", json={"value": "unused", "extra": 1}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422


@pytest.mark.real_db
def test_two_admins_saving_different_keys_at_once_keep_both(app, make_user):
    """두 관리자가 동시에 다른 키를 바꿔도 하나를 잃지 않는다 — 서버가 행 잠금 안에서 그 키만 합친다."""
    from fastapi.testclient import TestClient

    make_user("setup-race-a@goodmit.co.kr", role="system_admin", password="Race-Pass-1234!")
    make_user("setup-race-b@goodmit.co.kr", role="system_admin", password="Race-Pass-1234!")
    clients, tokens = [], []
    for email in ("setup-race-a@goodmit.co.kr", "setup-race-b@goodmit.co.kr"):
        c = TestClient(app, base_url="https://testserver")
        r = c.post("/login", json={"email": email, "password": "Race-Pass-1234!"})
        assert r.status_code == 200, r.text
        clients.append(c)
        tokens.append(r.json()["csrf_token"])
    results: list[int] = []
    barrier = threading.Barrier(2)

    def run(i, key, value):
        barrier.wait()
        results.append(_choice(clients[i], key, value, tokens[i]).status_code)

    threads = [threading.Thread(target=run, args=(0, "mail", "unused")), threading.Thread(target=run, args=(1, "tls", "proxy"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(results) == [200, 200], results
    assert _stored(clients[0]) == {"mail": "unused", "llm": "use", "tls": "proxy"}


# ── 2 · 3. 상태와 요약 띠 — 다섯 시나리오 ──────────────────────────────────────


@pytest.fixture()
def basics(client, app, db, login_as, tmp_path, monkeypatch):
    """필수(관리자 · 조직 · TLS)를 끝낸 설치."""
    csrf = login_as("system_admin")
    _organization(db)
    _trusted_tls(app, tmp_path, monkeypatch)
    return csrf


def _mail_ok(client, fake_clock, ok=True):
    from app.mail import health as mail_health
    from app.mail.config import config_from_db
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app)
    with client.app.state.session_factory() as s:
        mail_health.record_result(s, config_from_db(s), ok=ok, now=fake_clock.now(), source="verify",
                                  failure_kind="auth", stage="auth", summary="메일 서버가 로그인을 거부했습니다.",
                                  counts_any_failure=True)
        s.commit()


def _ai(client, fake_clock, result="ok"):
    from tests.fakes.ai import configure_ai

    configure_ai(client.app)
    runtime = client.app.state.ai_runtime
    with client.app.state.session_factory() as s:
        runtime.record(runtime.config(s), result=result, code=None if result == "ok" else "invalid_key",
                       now=fake_clock.now())
        s.commit()


def test_required_left_says_how_many_and_what_is_next(client, login_as):
    login_as("system_admin")
    payload = client.get(CHECKLIST).json()
    assert payload["headline"].startswith("필수 설정 ") and payload["headline"].endswith("개가 남았습니다.")
    assert payload["required_total"] == 3
    assert f"필수 3개 중 {payload['required_done']}개가 끝났습니다." in payload["subline"]
    current = _items(payload)[payload["current_key"]]
    assert current["current"] is True and f"다음 할 일은 {current['label']}입니다." in payload["subline"]
    assert sum(1 for i in payload["items"] if i["current"]) == 1


def test_scenario_required_done_optional_undecided(client, basics):
    payload = client.get(CHECKLIST).json()
    assert payload["headline"] == "기본 설정이 끝났습니다."
    assert payload["subline"] == "선택 기능 2개는 아직 정하지 않았거나 확인하지 않았습니다."
    items = _items(payload)
    assert items["mail"]["status"] == "pending" and items["mail"]["status_label"] == "정하지 않음"
    assert {"key": "mail", "value": "unused", "label": "사용하지 않음"} in items["mail"]["choices"]


def test_scenario_optional_unused(client, basics):
    _choice(client, "mail", "unused", basics)
    payload = _choice(client, "llm", "unused", basics).json()
    items = _items(payload)
    assert items["mail"]["status"] == "skipped" and items["llm"]["status"] == "skipped"
    assert {"key": "mail", "value": "use", "label": "다시 사용"} in items["mail"]["choices"]
    assert payload["headline"] == "기본 설정이 끝났습니다." and payload["subline"] == "선택 기능도 모두 정했습니다."


def test_scenario_mail_failing(client, basics, fake_clock):
    _mail_ok(client, fake_clock, ok=False)
    payload = client.get(CHECKLIST).json()
    mail = _items(payload)["mail"]
    assert mail["status"] == "problem" and mail["status_label"] == "문제 있음"
    assert mail["choices"] == [], "켜고 채운 메일은 숨길 수 없다"
    assert payload["headline"] == "기본 설정이 끝났습니다." and "메일 발송에 문제가 있습니다." in payload["subline"]


def test_scenario_ai_failing(client, basics, fake_clock):
    _ai(client, fake_clock, result="auth")
    llm = _items(client.get(CHECKLIST).json())["llm"]
    assert llm["status"] == "problem", llm


def test_scenario_everything_ok(client, basics, fake_clock):
    _mail_ok(client, fake_clock)
    _ai(client, fake_clock)
    payload = client.get(CHECKLIST).json()
    statuses = {i["key"]: i["status"] for i in payload["items"]}
    assert statuses == {"admin_account": "done", "mail": "done", "organization": "done", "llm": "done",
                        "integrations": "done", "tls": "done"}
    assert payload["current_key"] is None and payload["subline"] == "선택 기능도 모두 정했습니다."


# ── 4. 메일 — 보내는 방법마다 (M6) ────────────────────────────────────────────


def test_enabled_mail_with_gaps_cannot_be_hidden(client, basics):
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app, username="mailer")  # 계정은 있는데 비밀번호가 없다
    mail = _items(client.get(CHECKLIST).json())["mail"]
    assert mail["status"] == "todo" and mail["detail"].startswith("메일 설정 일부가 남아 있습니다:")
    assert mail["choices"] == []


@pytest.fixture()
def relay(client, settings, monkeypatch, tmp_path):
    from tests.integration.test_mail_relay_api import relay_keys  # noqa: F401 - 같은 준비를 쓴다

    helper = FakeHelper()
    client.app.state.sysops_client = helper
    from pathlib import Path

    from app.mail import relay_certs, relay_files

    secrets = Path(settings.secrets_dir)
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / "smtp.relay_client").write_text(relay_certs.make_client_bundle(), encoding="ascii")
    crt, _key = relay_certs.make_server_cert()
    cert = tmp_path / "relay.crt"
    cert.write_text(crt, encoding="ascii")
    monkeypatch.setattr(relay_files, "SERVER_CERT", str(cert))
    yield helper
    client.app.state.sysops_client = None
    (secrets / "smtp.relay_client").unlink(missing_ok=True)


def _relay_mode(client):
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app, host="", mode="local_relay",
                   relay={"delivery": "direct", "helo_name": "mail.goodmit.co.kr"})


@pytest.mark.parametrize("component, status, words", [
    ("not_installed", "todo", "구성 요소가 설치되지 않았습니다"),
    ("foreign", "todo", "기존 메일 발송 구성이 있습니다"),
    ("ready", "todo", "로컬 릴레이가 비활성화되어 있습니다"),
    ("stopped", "problem", "메일 발송 구성 요소가 동작하지 않습니다"),
])
def test_local_relay_component_rows(client, basics, relay, component, status, words):
    _relay_mode(client)
    relay.set("mailrelay.status", data={"component": component, "listeners": []})
    mail = _items(client.get(CHECKLIST).json())["mail"]
    assert mail["status"] == status and words in mail["detail"], mail


def test_local_relay_is_done_only_after_an_outer_delivery(client, db, basics, relay, fake_clock):
    from app.mail import health as mail_health
    from app.mail.config import config_from_db
    from app.mail.models import MailDelivery

    _relay_mode(client)
    relay.set("mailrelay.status", data={"component": "running", "listeners": ["127.0.0.1:2525"]})
    assert _items(client.get(CHECKLIST).json())["mail"]["status"] == "check", "앱 → 릴레이를 아직 확인하지 않았다"
    with client.app.state.session_factory() as s:
        # 로컬 릴레이의 지문에는 앱 열쇠의 표지가 든다 - 화면이 쓰는 같은 비밀 제공자로 적어야 같은 지문이다.
        mail_health.record_result(s, config_from_db(s), ok=True, now=fake_clock.now(), source="verify",
                                  secret_provider=client.app.state.secret_provider)
        s.commit()
    mail = _items(client.get(CHECKLIST).json())["mail"]
    assert mail["status"] == "check" and "준비 점검을 실행하고 시험 메일을 보내세요" in mail["question"]
    # 「지금 설정 이후」의 기준은 메일 설정 행을 저장한 시각이다(그 시각 뒤에 넘긴 메일의 바깥 결과만 센다).
    from datetime import timedelta

    from app.settings.models import AppSetting

    now = db.get(AppSetting, "smtp").updated_at + timedelta(seconds=5)
    row = MailDelivery(kind="test", to_email="a@goodmit.co.kr", subject="[ClovirAssist] 시험", status="sent",
                       attempt_count=0, params_json="{}", sent_at=now, relay_queue_id="C87DBF6954",
                       relay_delivery="direct", remote_status="bounced", remote_stage="rejected",
                       remote_checked_at=now, created_at=now, updated_at=now)
    db.add(row)
    db.commit()
    mail = _items(client.get(CHECKLIST).json())["mail"]
    assert mail["status"] == "problem" and "받는 쪽 메일 서버가 메일을 거부했습니다" in mail["detail"]
    row.remote_status, row.remote_stage = "delivered", None
    db.commit()
    mail = _items(client.get(CHECKLIST).json())["mail"]
    assert mail["status"] == "done" and mail["detail"] == "수신측 메일 서버까지 전달을 확인했습니다."


def test_local_relay_readiness_failures_are_named(client, basics, relay, fake_clock):
    from app.mail import health as mail_health, relay_readiness
    from app.mail.config import config_from_db

    _relay_mode(client)
    relay.set("mailrelay.status", data={"component": "running", "listeners": ["127.0.0.1:2525"]})
    with client.app.state.session_factory() as s:
        config = config_from_db(s)
        mail_health.record_result(s, config, ok=True, now=fake_clock.now(), source="verify",
                                  secret_provider=client.app.state.secret_provider)
        relay_readiness.save(s, {"state": "fail", "fingerprint": config.relay_fingerprint, "checks": [
            {"key": "spf", "label": "SPF", "state": "fail"}, {"key": "ptr_fcrdns", "label": "역방향 이름(PTR)", "state": "fail"},
            {"key": "dmarc", "label": "DMARC", "state": "ok"}]}, now=fake_clock.now())
        s.commit()
    mail = _items(client.get(CHECKLIST).json())["mail"]
    assert mail["status"] == "todo" and mail["detail"] == "준비 점검에서 고칠 것이 있습니다: SPF, 역방향 이름(PTR)."


# ── 6. 배너 비용 ─────────────────────────────────────────────────────────────


def test_the_status_poll_runs_only_the_organization_probe_and_reuses_it(client, login_as, monkeypatch, fake_clock):
    from app.setup import probes

    calls: list[str] = []
    for key, func in list(probes.PROBES.items()):
        def counted(ctx, _key=key, _func=func):
            calls.append(_key)
            return _func(ctx)
        monkeypatch.setitem(probes.PROBES, key, counted)
    login_as("user")
    for _ in range(3):
        assert client.get("/api/system/status").status_code == 200
    assert calls == ["organization"], f"상태 폴링이 판정을 더 돌렸다: {calls}"
    fake_clock.advance(61)
    client.get("/api/system/status")
    assert calls == ["organization", "organization"], "60초가 지나면 다시 판정한다"


def test_the_setup_link_goes_only_to_system_admins(client, login_as):
    for role, has_link in (("system_admin", True), ("admin", False), ("operator", False), ("user", False)):
        login_as(role, email=f"setup-banner-{role}@goodmit.co.kr")
        notice = [n for n in client.get("/api/system/status").json()["notices"] if n["id"] == "setup.incomplete"][0]
        assert (notice["href"] is not None) is has_link, role
        if not has_link:
            assert "시스템 관리자가 초기 설정을 끝내야 합니다" in notice["message"]
