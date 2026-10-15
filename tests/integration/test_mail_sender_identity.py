"""보내는 사람 이름 · 더할 메일 머리 · 받은 편지함 아이콘 안내 (D-571 · D-572).

못박는 것:
  * 보내는 사람 이름이 비어 있으면 제품 이름(`ui_branding.product_name`)으로 보낸다. 이름이 있으면 그대로다.
  * 브랜딩의 문의 주소가 있으면 실제 발송이 `Reply-To` 를 단다. 알림 메일이 아닌 시험 메일에는 `List-Unsubscribe` 가 없다.
  * `GET /api/admin/mail/status` 의 `help.inbox_icon` 은 `{provider, what, who, external, note}` 목록이다(화면이 그대로 그린다).
"""

from __future__ import annotations

import pytest

from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration


def _branding(app, **value):
    from app.settings.service import apply_setting

    with app.state.session_factory() as db:
        apply_setting(db, app.state.settings_cache, key="ui_branding", value={"product_name": "ClovirAssist", **value},
                      updated_by=None, now=app.state.clock.now())
        db.commit()


def _send_test(client, app, settings, fake_clock, login_as) -> dict:
    r = client.post("/api/admin/mail/test", json={}, headers={"X-CSRF-Token": login_as("system_admin")})
    assert r.status_code == 200, r.text
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    assert len(server.sent) == 1
    return server.sent[0]


def test_an_empty_sender_name_goes_out_as_the_product_name(client, app, settings, fake_clock, login_as):
    configure_smtp(app, from_name="")
    _branding(app, product_name="굿모닝 포털")
    sent = _send_test(client, app, settings, fake_clock, login_as)
    assert sent["from_name"] == "굿모닝 포털"
    assert sent["headers"] == {}, "문의 주소가 없으면 Reply-To 도 없고, 시험 메일에는 List-Unsubscribe 가 없다"


def test_a_sender_name_is_kept_and_the_support_address_becomes_reply_to(client, app, settings, fake_clock, login_as):
    configure_smtp(app, from_name="사내 알림")
    _branding(app, support_email="help@example.com")
    sent = _send_test(client, app, settings, fake_clock, login_as)
    assert sent["from_name"] == "사내 알림"
    assert sent["headers"] == {"Reply-To": "help@example.com"}


def test_the_status_carries_the_inbox_icon_help(client, login_as):
    from app.mail.help import INBOX_ICON_HELP

    body = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": login_as("auditor")}).json()
    items = body["help"]["inbox_icon"]
    assert items == INBOX_ICON_HELP and len(items) >= 3
    for item in items:
        assert set(item) == {"provider", "what", "who", "external", "note"}
        assert isinstance(item["external"], bool) and all(isinstance(item[k], str) and item[k] for k in ("provider", "what", "who", "note"))
        assert "·" not in "".join(item[k] for k in ("provider", "what", "who", "note"))
    providers = " ".join(item["provider"] for item in items)
    assert "Microsoft 365" in providers and "Gmail" in providers
    assert any("BIMI" in item["what"] + item["note"] and "VMC" in item["note"] for item in items)
