"""ClovirAssist 로컬 릴레이 — 메일 API · 발송 · 추적 · 준비 점검 (계획 M7, D-551 · D-555).

못박는 것:
  * 릴레이 API 는 전부 메일 설정 권한(`SYSTEM_CONFIGURE`)이다. 관리자 · 운영자 · 감사자는 403 이다.
  * `mailrelay.*` 는 범용 시스템 API(`/api/admin/system/*`)로 부를 수 없다.
  * 헬퍼 인자는 저장된 설정에서만 만든다. 외부 SMTP 방식이면 켜기 · 키 만들기 · 점검이 409 다.
  * 상위 SMTP 비밀번호는 같은 저장에서 고정 칸에 쓰이고 응답 · 감사에 값이 없다.
  * DKIM 공개키는 키를 만들 때 서버가 적고, 저장은 그 값을 지키며 선택자를 바꾸면 비운다.
  * 로컬 릴레이로 넘긴 메일은 큐 id 와 「로컬 릴레이가 접수함」을 남기고, 추적이 큐 · 로그로 바깥 결과를 채운다
    (미룸 · 전달함 · 이틀 뒤 모름). 헬퍼가 없으면 아무것도 추측하지 않는다.
  * 준비 점검 잡이 결과를 남기고 그 결과를 API 가 돌려준다.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from app.audit.models import AuditLog
from app.mail import relay_certs, relay_files
from app.sysops.client import STATUS_NOT_INSTALLED, STATUS_OK, HelperReply
from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration

RELAY_PW = "relay-api-SENTINEL-4471"
SMART = {"delivery": "smarthost", "smarthost": {"host": "smtp.office365.com", "port": 587, "security": "starttls",
                                                 "username": "notify@goodmit.co.kr"}}
BASE = {"enabled": True, "host": "", "port": 587, "security": "starttls", "from_address": "noreply@goodmit.co.kr",
        "from_name": "ClovirAssist", "username": "", "timeout_seconds": 20, "tls_verify": True, "ca_pem": ""}


class FakeHelper:
    """가짜 특권 헬퍼. 동작마다 답을 정해 두고, 무엇을 불렀는지 기록한다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.replies: dict[str, HelperReply] = {
            "mailrelay.status": HelperReply(available=True, status=STATUS_OK, ok=True, detail="",
                                            data={"component": "ready", "listeners": [], "services": {}}),
        }

    def set(self, action, *, ok=True, data=None, detail="", changed=True):
        self.replies[action] = HelperReply(available=True, status=STATUS_OK, ok=ok, detail=detail,
                                           data=data or {}, changed=changed)

    def call(self, action, params=None):
        self.calls.append((action, dict(params or {})))
        return self.replies.get(action) or HelperReply(available=True, status=STATUS_OK, ok=True, detail="ok", data={})

    def probe(self):
        return self.call("system.info")


@pytest.fixture()
def helper(client):
    fake = FakeHelper()
    client.app.state.sysops_client = fake
    yield fake
    client.app.state.sysops_client = None


@pytest.fixture()
def relay_keys(settings, monkeypatch, tmp_path):
    """릴레이가 한 번 켜진 서버 — 앱 열쇠(비밀 칸)와 서버 인증서(공개)가 있다."""
    secrets = Path(settings.secrets_dir)
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / "smtp.relay_client").write_text(relay_certs.make_client_bundle(), encoding="ascii")
    crt, _key = relay_certs.make_server_cert()
    cert = tmp_path / "server.crt"
    cert.write_text(crt, encoding="ascii")
    monkeypatch.setattr(relay_files, "SERVER_CERT", str(cert))
    yield
    (secrets / "smtp.relay_client").unlink(missing_ok=True)


def _h(login_as, role="system_admin", **kw):
    return {"X-CSRF-Token": login_as(role, **kw)}


def _save(client, h, **over):
    body = {**BASE, "mode": "local_relay", "relay": SMART, **over}
    return client.put("/api/admin/mail/settings", json=body, headers=h)


@pytest.mark.parametrize("role", ["admin", "operator", "auditor"])
def test_only_mail_configurers_reach_the_relay_api(client, login_as, helper, role):
    h = _h(login_as, role)
    assert client.get("/api/admin/mail/relay", headers=h).status_code == 403
    for path in ("/api/admin/mail/relay/apply", "/api/admin/mail/relay/disable", "/api/admin/mail/relay/dkim",
                 "/api/admin/mail/relay/check", "/api/admin/mail/relay/flush"):
        assert client.post(path, json={}, headers=h).status_code == 403, path
    assert not [c for c in helper.calls if c[0].startswith("mailrelay.") and c[0] != "mailrelay.status"]


def test_relay_actions_are_not_reachable_through_the_generic_system_api(client, login_as, helper):
    h = _h(login_as)
    for name in ("mailrelay.apply", "mailrelay.disable", "mailrelay.flush"):
        r = client.post(f"/api/admin/system/{name}", json={"params": {}}, headers=h)
        assert r.status_code == 404, r.text
    assert helper.calls == []


def test_external_mode_cannot_drive_the_relay(client, login_as, helper):
    configure_smtp(client.app)
    h = _h(login_as)
    for path in ("/api/admin/mail/relay/apply", "/api/admin/mail/relay/dkim", "/api/admin/mail/relay/check"):
        assert client.post(path, json={}, headers=h).status_code == 409, path
    assert not [c for c in helper.calls if c[0] in ("mailrelay.apply", "mailrelay.dkim_generate")]


def test_saving_the_relay_writes_the_password_slot_without_echoing_it(client, db, login_as, helper, settings):
    h = _h(login_as)
    r = _save(client, h, relay_password=RELAY_PW)
    assert r.status_code == 200, r.text
    assert RELAY_PW not in r.text
    body = r.json()
    assert body["settings"]["mode"] == "local_relay" and body["relay_password"]["stored"] is True
    assert (Path(settings.secrets_dir) / "smtp.relay_password").read_text(encoding="utf-8").strip() == RELAY_PW
    audits = db.query(AuditLog).all()
    assert all(RELAY_PW not in (a.after_json or "") + (a.before_json or "") for a in audits)
    # 릴레이가 꺼져 있으면 저장은 적용을 부르지 않는다(화면의 「로컬 릴레이 켜기」가 켠다).
    assert not [c for c in helper.calls if c[0] == "mailrelay.apply"]
    (Path(settings.secrets_dir) / "smtp.relay_password").unlink()


def test_apply_builds_the_arguments_from_saved_settings(client, login_as, helper, relay_keys):
    h = _h(login_as)
    assert _save(client, h, relay={"delivery": "direct", "helo_name": "mail.goodmit.co.kr",
                                   "transport_overrides": [{"domain": "goodmit.co.kr",
                                                            "host": "goodmit-co-kr.mail.protection.outlook.com"}]}).status_code == 200
    helper.set("mailrelay.apply", detail="로컬 릴레이를 켰습니다.")
    r = client.post("/api/admin/mail/relay/apply", json={}, headers=h)
    assert r.status_code == 200, r.text
    action, params = [c for c in helper.calls if c[0] == "mailrelay.apply"][-1]
    assert params == {"delivery": "direct", "sender_domain": "goodmit.co.kr", "helo_name": "mail.goodmit.co.kr",
                      "ipv4_only": False, "smarthost": None, "dkim": None,
                      "transport_overrides": [{"domain": "goodmit.co.kr",
                                               "host": "goodmit-co-kr.mail.protection.outlook.com"}]}
    assert r.json()["result"]["ok"] is True
    assert r.json()["verify"] and r.json()["verify"]["job_id"], "켜고 나면 앱 → 릴레이 연결 확인을 시작한다"


def test_a_refused_apply_is_reported_and_audited(client, db, login_as, helper):
    h = _h(login_as)
    _save(client, h)
    helper.set("mailrelay.apply", ok=False, detail="이 서버에는 기존 메일 발송 구성이 있습니다. ClovirAssist 로컬 릴레이가 자동으로 구성되지 않았습니다.")
    r = client.post("/api/admin/mail/relay/apply", json={}, headers=h)
    assert r.status_code == 200 and r.json()["result"]["ok"] is False and r.json()["verify"] is None
    row = db.query(AuditLog).filter(AuditLog.action == "mail.relay.apply").one()
    assert row.result == "failure"


def test_the_component_words_and_stale_flag(client, login_as, helper):
    h = _h(login_as)
    _save(client, h)
    for state, label in (("ready", "구성 요소 준비됨"), ("not_installed", "설치되지 않음"),
                         ("foreign", "기존 메일 발송 구성이 있음"), ("stopped", "멈춤")):
        helper.set("mailrelay.status", data={"component": state, "listeners": []})
        view = client.get("/api/admin/mail/relay", headers=h).json()
        assert view["component"]["state"] == state and view["component"]["label"] == label
    helper.set("mailrelay.status", data={"component": "running", "listeners": ["127.0.0.1:2525"],
                                         "applied_relay_fingerprint": "old"})
    assert client.get("/api/admin/mail/relay", headers=h).json()["component"]["stale"] is True
    client.app.state.sysops_client.replies["mailrelay.status"] = HelperReply.unavailable(STATUS_NOT_INSTALLED, "없음")
    view = client.get("/api/admin/mail/relay", headers=h).json()
    assert view["component"]["state"] == "unavailable"


def test_dkim_public_key_is_written_by_the_server_and_kept_by_saves(client, login_as, helper):
    h = _h(login_as)
    direct = {"delivery": "direct", "helo_name": "mail.goodmit.co.kr", "dkim_enabled": False}
    _save(client, h, relay=direct)
    helper.set("mailrelay.dkim_generate", data={"public": "QUJD", "record_name": "ca1._domainkey.goodmit.co.kr"})
    r = client.post("/api/admin/mail/relay/dkim", json={}, headers=h)
    assert r.status_code == 200, r.text
    assert [c for c in helper.calls if c[0] == "mailrelay.dkim_generate"][-1][1] == {"domain": "goodmit.co.kr", "selector": "ca1"}
    assert r.json()["relay"]["config"]["dkim_public"] == "QUJD"
    # 저장은 서버가 적은 공개키를 지킨다 - 화면이 보내지 않는 칸이다.
    saved = _save(client, h, relay={**direct, "dkim_selector": "ca1", "dkim_enabled": True}).json()
    assert saved["settings"]["relay"]["dkim_public"] == "QUJD"
    # 선택자를 바꾸면 비운다(새 선택자의 키를 만들 때 다시 적힌다).
    saved = _save(client, h, relay={**direct, "dkim_selector": "ca2", "dkim_enabled": True}).json()
    assert saved["settings"]["relay"]["dkim_public"] == ""


def test_relay_settings_refuse_injection_and_unknown_fields(client, login_as, helper):
    h = _h(login_as)
    for relay in ({"delivery": "direct", "helo_name": "mail.x.com\nrelayhost = [evil]"},
                  {"delivery": "smarthost", "smarthost": {"host": "smtp.x.com", "port": 587, "security": "starttls",
                                                          "username": "a b"}},
                  {"delivery": "direct", "helo_name": "m.x.com", "transport_overrides": [{"domain": "x.com", "host": "a b"}]},
                  {"delivery": "direct", "helo_name": "m.x.com", "takeover": True},
                  {"delivery": "direct", "helo_name": "m.x.com", "dkim_public": "QUJD"}):
        r = _save(client, h, relay=relay)
        assert r.status_code == 422, (relay, r.text)


def test_check_job_runs_and_its_result_is_returned(client, app, login_as, helper, settings, fake_clock, relay_keys):
    from app.jobs.handlers import mail_relay_check
    from tests.unit.test_mail_relay_parts import FakeDns

    h = _h(login_as)
    # 비교할 공개 해석기를 하나 넣었다 - 시스템 해석기가 모르는 MX 를 그쪽이 알면 분리 DNS 다.
    _save(client, h, relay={"delivery": "direct", "helo_name": "mail.goodmit.co.kr", "compare_resolvers": ["8.8.8.8"]})
    r = client.post("/api/admin/mail/relay/check", json={"probe_domain": "goodmit.co.kr"}, headers=h)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    helper.set("mailrelay.status", data={"component": "running", "listeners": ["127.0.0.1:2525"]})

    class FakeTransport:
        def verify(self, config, secret_provider, *, probe_recipient=None):
            return {"ok": True, "stages": []}

    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import build_handlers

    public = FakeDns(mx={"goodmit.co.kr": ["0 goodmit-co-kr.mail.protection.outlook.com"]})
    ctx = WorkerContext(settings=settings, clock=fake_clock, extras={
        "secret_provider": app.state.secret_provider, "sysops_client": helper, "mail_transport": FakeTransport(),
        "mail_dns_factory": lambda servers=None: public if servers else FakeDns(),
        "mx_probe": lambda host, helo: {"host": host, "connected": True, "egress_ip": "221.147.80.10", "ehlo": "250 hi"},
    })
    # 저장이 넣은 연결 확인 잡은 이 시험의 일이 아니다 - 점검 잡만 집는 워커다.
    worker = Worker(app.state.session_factory, fake_clock, build_handlers(), ctx,
                    include_types=(mail_relay_check.MAIL_RELAY_CHECK_JOB_TYPE,))
    assert worker.run_once()
    got = client.get(f"/api/admin/mail/relay/check/{job_id}", headers=h).json()
    assert got["pending"] is False and got["readiness"]["delivery"] == "direct"
    rows = {row["key"]: row for row in got["readiness"]["checks"]}
    assert rows["app_to_relay"]["state"] == "ok"
    assert rows["recipient_mx"]["state"] == "fail" and "분리 DNS" in rows["recipient_mx"]["message"]
    # 받는 쪽 MX 를 몰라 25번 시험을 못 했으니 바깥 IP 를 모르고, 역방향 이름도 판정하지 않는다(추측하지 않는다).
    assert rows["egress_ip"]["state"] == "warn" and rows["ptr_fcrdns"]["state"] == "unknown"
    assert rows["outbound_25"]["state"] == "unknown"
    assert any(rec["key"] == "override" for rec in got["readiness"]["records"])
    assert client.get("/api/admin/mail/relay/check/no-such-job", headers=h).status_code == 404


# ── 발송과 추적 ──────────────────────────────────────────────────────────────


class RelaySmtp(FakeSmtp):
    """로컬 릴레이처럼 큐 id 가 든 응답을 준다."""

    def send(self, config, secret_provider, *, to_email, subject, body, html=None, inline=None):
        from app.mail.transport import SendReceipt

        super().send(config, secret_provider, to_email=to_email, subject=subject, body=body, html=html)
        return SendReceipt(message_id="<m@goodmit.co.kr>", response="250 2.0.0 Ok: queued as C87DBF6954")


def _send_one(client, app, settings, fake_clock, login_as):
    h = _h(login_as)
    r = client.post("/api/admin/mail/test", json={}, headers=h)
    assert r.status_code == 200, r.text
    drain_worker(app, settings, fake_clock, RelaySmtp())


def test_a_relay_handoff_records_the_queue_id_and_tracking_fills_the_outcome(
        client, app, db, login_as, helper, settings, fake_clock, relay_keys):
    from app.mail.models import MailDelivery
    from app.mail.relay_tracking import track_once

    configure_smtp(app, host="", mode="local_relay", relay={"delivery": "direct", "helo_name": "mail.goodmit.co.kr"})
    _send_one(client, app, settings, fake_clock, login_as)
    row = db.query(MailDelivery).filter(MailDelivery.kind == "test").one()
    db.refresh(row)
    assert row.status == "sent" and row.relay_queue_id == "C87DBF6954" and row.remote_status == "queued"
    view = client.get(f"/api/admin/mail/deliveries/{row.id}", headers=_h(login_as)).json()["delivery"]
    assert view["status_label"] == "로컬 릴레이가 접수함" and view["relay"]["remote_label"] == "전달 대기"

    # 1) 아직 큐에 있고 받는 쪽이 연결을 거부했다 → 미룸(연결 단계).
    helper.set("mailrelay.queue", data={"items": [{"queue_id": "C87DBF6954", "queue_name": "deferred", "recipients": [
        {"address": row.to_email, "delay_reason": "connect to mx.x.com[192.0.2.1]:25: Connection timed out"}]}]})
    with app.state.session_factory() as s:
        track_once(s, helper, now=fake_clock.now())
        s.commit()
    db.refresh(row)
    assert row.remote_status == "deferred" and row.remote_stage == "connect"
    assert client.get(f"/api/admin/mail/deliveries/{row.id}", headers=_h(login_as)).json()["delivery"]["status_label"] ==         "전달 재시도 중"

    # 2) 큐를 떠났고 로그가 전달함을 말한다.
    helper.set("mailrelay.queue", data={"items": []})
    helper.set("mailrelay.log", data={"results": {"C87DBF6954": {"status": "delivered", "dsn": "2.0.0", "stage": None,
                                                                 "said": "250 2.6.0 Queued mail for delivery"}}})
    with app.state.session_factory() as s:
        track_once(s, helper, now=fake_clock.now())
        s.commit()
    db.refresh(row)
    assert row.remote_status == "delivered"
    view = client.get(f"/api/admin/mail/deliveries/{row.id}", headers=_h(login_as)).json()["delivery"]
    assert view["status_label"] == "수신측 메일 서버로 전달함"
    assert "도착" not in json.dumps(view, ensure_ascii=False)


def test_tracking_does_not_guess_when_the_helper_is_missing_and_gives_up_after_two_days(
        client, app, db, login_as, helper, settings, fake_clock, relay_keys):
    from app.mail.models import MailDelivery
    from app.mail.relay_tracking import track_once

    configure_smtp(app, host="", mode="local_relay", relay=SMART)
    (Path(settings.secrets_dir) / "smtp.relay_password").write_text("x", encoding="utf-8")
    try:
        _send_one(client, app, settings, fake_clock, login_as)
    finally:
        (Path(settings.secrets_dir) / "smtp.relay_password").unlink()
    row = db.query(MailDelivery).filter(MailDelivery.kind == "test").one()
    helper.replies["mailrelay.queue"] = HelperReply.unavailable(STATUS_NOT_INSTALLED, "없음")
    with app.state.session_factory() as s:
        assert track_once(s, helper, now=fake_clock.now())["checked"] == 0
        s.commit()
    db.refresh(row)
    assert row.remote_status == "queued", "헬퍼가 없으면 상태를 추측하지 않는다"
    helper.set("mailrelay.queue", data={"items": []})
    helper.set("mailrelay.log", data={"results": {}})
    later = fake_clock.now() + timedelta(days=3)
    with app.state.session_factory() as s:
        track_once(s, helper, now=later)
        s.commit()
    db.refresh(row)
    assert row.remote_status == "unknown"
    detail = client.get("/api/admin/mail/deliveries/" + row.id, headers=_h(login_as)).json()["delivery"]
    assert detail["relay"]["remote_label"] == "결과를 알 수 없음"
