"""로컬 릴레이의 비밀은 웹 응답 · 감사 · 헬퍼 인자 어디에도 실리지 않는다 (계획 M7, D-551).

로컬 릴레이에는 비밀이 둘 있다 — 상위 SMTP 비밀번호(`smtp.relay_password`, 사람이 넣는다)와 앱의 클라이언트 열쇠(`smtp.relay_client`,
헬퍼가 만든다). 둘 다 파일 칸에만 산다. 웹은 상위 SMTP 비밀번호를 헬퍼에 넘기지 않는다 - 헬퍼가 root 로 그 칸을 읽어
`sasl_passwd`(0600)에 쓴다. 메일 화면의 GET 셋과 감사 · 헬퍼 인자를 훑어 값이 하나도 없는지 본다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.audit.models import AuditLog
from app.mail import relay_certs
from tests.integration.test_mail_relay_api import BASE, FakeHelper

pytestmark = pytest.mark.security

RELAY_PW = "RELAY-PW-NEVER-LEAK-6618"


@pytest.fixture()
def seeded(client, login_as, settings):
    secrets = Path(settings.secrets_dir)
    secrets.mkdir(parents=True, exist_ok=True)
    bundle = relay_certs.make_client_bundle()
    (secrets / "smtp.relay_client").write_text(bundle, encoding="ascii")
    helper = FakeHelper()
    client.app.state.sysops_client = helper
    h = {"X-CSRF-Token": login_as("system_admin")}
    r = client.put("/api/admin/mail/settings", headers=h, json={
        **BASE, "mode": "local_relay", "relay_password": RELAY_PW,
        "relay": {"delivery": "smarthost", "smarthost": {"host": "smtp.office365.com", "port": 587, "security": "starttls",
                                                          "username": "notify@goodmit.co.kr"}},
    })
    assert r.status_code == 200, r.text
    key_line = bundle.split("-----END PRIVATE KEY-----")[0].splitlines()[1]
    yield {"h": h, "helper": helper, "key_line": key_line}
    client.app.state.sysops_client = None
    for name in ("smtp.relay_client", "smtp.relay_password"):
        (secrets / name).unlink(missing_ok=True)


def test_mail_screen_responses_carry_no_relay_secret(client, seeded):
    helper = seeded["helper"]
    helper.set("mailrelay.apply", detail="로컬 릴레이를 켰습니다.")
    responses = [
        client.get("/api/admin/mail/status", headers=seeded["h"]),
        client.get("/api/admin/mail/settings", headers=seeded["h"]),
        client.get("/api/admin/mail/relay", headers=seeded["h"]),
        client.post("/api/admin/mail/relay/apply", json={}, headers=seeded["h"]),
    ]
    for r in responses:
        assert r.status_code == 200, r.text
        assert RELAY_PW not in r.text and seeded["key_line"] not in r.text


def test_the_helper_never_receives_the_password_and_audits_hold_no_value(client, db, seeded):
    seeded["helper"].set("mailrelay.apply", detail="ok")
    client.post("/api/admin/mail/relay/apply", json={}, headers=seeded["h"])
    sent = json.dumps(seeded["helper"].calls, ensure_ascii=False)
    assert RELAY_PW not in sent and seeded["key_line"] not in sent, "웹은 비밀을 헬퍼 인자로 넘기지 않는다"
    for row in db.query(AuditLog).all():
        text = (row.before_json or "") + (row.after_json or "")
        assert RELAY_PW not in text and seeded["key_line"] not in text
