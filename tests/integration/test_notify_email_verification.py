"""알림 받을 메일 주소의 확인 코드 (계획 M4, D-550).

못박는 것:
  * 다른 주소는 그 주소로 보낸 6자리 코드를 넣어야 쓴다. 확인이 끝나기 전에는 알림이 계정 주소로 간다.
  * 코드는 워커가 메일을 그릴 때만 생긴다 - 발송 행 · 잡 payload · params · 확인 행 어디에도 6자리 평문이 없다(HMAC 만).
  * 틀린 코드는 다섯 번까지다(여섯 번째는 맞아도 429). 15분이 지나면 만료다. 확인 메일은 사람당 15분에 3통이다.
  * 「허용 이메일 도메인」이 있으면 그 도메인만 받는다. 확인한 주소가 나중에 허용 밖이 되면 계정 주소로 돌아간다.
  * 다른 사람의 확인을 쓸 수 없다(IDOR). 쓰기는 CSRF 를 요구한다. 메일을 보낼 수 없는 설치는 409 다.
  * 계정 주소를 넣으면 다른 주소를 지운다.
"""

from __future__ import annotations

import re

import pytest

from tests.integration.test_password_reset import FakeSmtp, configure_smtp, drain_worker

pytestmark = pytest.mark.integration

PASSWORD = "Str0ng-Passw0rd!"
OTHER = "me.elsewhere@goodmit.co.kr"


def _login(client, make_user, email):
    make_user(email=email, role="user", password=PASSWORD)
    r = client.post("/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _mail_block(client, h):
    return client.get("/api/me/preferences", headers=h).json()["mail"]


def _code_from(server) -> str:
    text = server.sent[-1]["body"]
    found = re.findall(r"확인 코드: (\d{6})", text)
    assert found, text
    return found[-1]


def test_a_new_address_is_used_only_after_the_code(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    h = _login(client, make_user, "notify-a@goodmit.co.kr")
    r = client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    assert r.status_code == 200, r.text
    address = r.json()["mail"]["address"]
    assert address["pending"]["email"] == OTHER and address["effective"] == "notify-a@goodmit.co.kr"
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    assert [m["to"] for m in server.sent] == [OTHER]
    code = _code_from(server)
    r = client.post("/api/me/notify-email/verify", json={"code": code}, headers=h)
    assert r.status_code == 200, r.text
    address = r.json()["mail"]["address"]
    assert address["custom"]["email"] == OTHER and address["custom"]["active"] is True
    assert address["effective"] == OTHER and address["pending"] is None


def test_the_code_lives_only_in_the_rendered_mail(client, app, db, settings, fake_clock, make_user):
    from app.jobs.models import Job
    from app.mail.models import MailDelivery
    from app.profiles.models import MailAddressVerification

    configure_smtp(app)
    h = _login(client, make_user, "notify-b@goodmit.co.kr")
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    code = _code_from(server)
    db.expire_all()
    delivery = db.query(MailDelivery).filter(MailDelivery.kind == "notify_email_verification").one()
    job = db.get(Job, delivery.job_id)
    row = db.query(MailAddressVerification).one()
    for stored in (delivery.params_json, job.payload_json, delivery.subject, row.code_hash or ""):
        assert code not in stored, "코드 평문이 저장됐다"
    assert row.code_hash and len(row.code_hash) == 64


# 틀린 횟수는 요청이 422 로 되감겨도 남아야 한다 - 리미터가 자기 세션에서 커밋한다. 공유 하네스에서는 그 세션이 같은 커넥션의
# SAVEPOINT 라 요청 롤백이 셈까지 되감으므로 자기 DB 가 필요하다(tests/conftest.py 의 다섯째 경우).
@pytest.mark.real_db
def test_five_wrong_codes_lock_the_verification(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    h = _login(client, make_user, "notify-c@goodmit.co.kr")
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    code = _code_from(server)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/api/me/notify-email/verify", json={"code": wrong}, headers=h).status_code == 422
    r = client.post("/api/me/notify-email/verify", json={"code": code}, headers=h)
    assert r.status_code == 429, r.text


def test_an_expired_code_is_refused(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    h = _login(client, make_user, "notify-d@goodmit.co.kr")
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    code = _code_from(server)
    fake_clock.advance(16 * 60)
    r = client.post("/api/me/notify-email/verify", json={"code": code}, headers=h)
    assert r.status_code == 422 and "만료" in r.text, r.text


def test_three_mails_per_window(client, app, fake_clock, make_user):
    configure_smtp(app)
    h = _login(client, make_user, "notify-e@goodmit.co.kr")
    codes = []
    for n in range(4):
        codes.append(client.post("/api/me/notify-email", json={"email": f"other{n}@goodmit.co.kr"}, headers=h).status_code)
        fake_clock.advance(61)
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_the_domain_rule_applies_and_narrowing_falls_back(client, app, settings, fake_clock, make_user):
    from app.settings.service import apply_setting

    configure_smtp(app)
    with app.state.session_factory() as db:
        apply_setting(db, app.state.settings_cache, key="allowed_email_domains", value=["goodmit.co.kr"],
                      updated_by=None, now=fake_clock.now())
        db.commit()
    h = _login(client, make_user, "notify-f@goodmit.co.kr")
    r = client.post("/api/me/notify-email", json={"email": "someone@gmail.com"}, headers=h)
    assert r.status_code == 422 and "goodmit.co.kr" in r.text, r.text
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    assert client.post("/api/me/notify-email/verify", json={"code": _code_from(server)}, headers=h).status_code == 200
    with app.state.session_factory() as db:
        apply_setting(db, app.state.settings_cache, key="allowed_email_domains", value=["other.example"],
                      updated_by=None, now=fake_clock.now())
        db.commit()
    address = _mail_block(client, h)["address"]
    assert address["custom"]["active"] is False and "허용 도메인이 바뀌어" in address["custom"]["inactive_reason"]
    assert address["effective"] == "notify-f@goodmit.co.kr"


def test_another_user_cannot_use_my_verification(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    owner = _login(client, make_user, "notify-g@goodmit.co.kr")
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=owner)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    code = _code_from(server)
    intruder = _login(client, make_user, "notify-h@goodmit.co.kr")
    r = client.post("/api/me/notify-email/verify", json={"code": code}, headers=intruder)
    assert r.status_code == 422, r.text
    assert _mail_block(client, intruder)["address"]["custom"] is None


def test_writes_need_csrf_and_a_sendable_install(client, app, make_user):
    h = _login(client, make_user, "notify-i@goodmit.co.kr")
    assert client.post("/api/me/notify-email", json={"email": OTHER}).status_code == 403
    r = client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    assert r.status_code == 409 and "메일 발송" in r.text, r.text


def test_the_account_address_clears_the_custom_one(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    h = _login(client, make_user, "notify-j@goodmit.co.kr")
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    client.post("/api/me/notify-email/verify", json={"code": _code_from(server)}, headers=h)
    r = client.post("/api/me/notify-email", json={"email": "NOTIFY-J@goodmit.co.kr"}, headers=h)
    assert r.status_code == 200 and r.json()["mail"]["address"]["custom"] is None
    r = client.delete("/api/me/notify-email", headers=h)
    assert r.status_code == 200 and r.json()["mail"]["address"]["effective"] == "notify-j@goodmit.co.kr"


def test_notifications_go_to_the_verified_address(client, app, settings, fake_clock, make_user):
    """확인한 주소가 있으면 알림 메일의 받는 주소가 보내는 순간 그 주소로 풀린다(`recheck_recipient`)."""
    import json

    from app.mail.models import MailDelivery
    from app.notifications.mail import recheck_recipient
    from app.profiles.service import get_preference
    from app.users.models import User

    configure_smtp(app)
    h = _login(client, make_user, "notify-k@goodmit.co.kr")
    client.post("/api/me/notify-email", json={"email": OTHER}, headers=h)
    server = FakeSmtp()
    drain_worker(app, settings, fake_clock, server)
    client.post("/api/me/notify-email/verify", json={"code": _code_from(server)}, headers=h)
    client.patch("/api/me/preferences", json={"mail_enabled": True}, headers=h)
    with app.state.session_factory() as db:
        user = db.query(User).filter(User.email == "notify-k@goodmit.co.kr").one()
        assert get_preference(db, user.id).notify_email == OTHER
        now = fake_clock.now()
        row = MailDelivery(
            kind="notification", to_email=user.email, subject="[ClovirAssist] 알림", status="queued", attempt_count=0,
            params_json=json.dumps({"user_id": user.id, "type": "ticket_assigned"}), recipient_user_id=user.id,
            created_at=now, updated_at=now,
        )
        db.add(row)
        db.flush()
        assert recheck_recipient(db, row) is None
        assert row.to_email == OTHER, "확인한 주소로 보내지 않았다"
