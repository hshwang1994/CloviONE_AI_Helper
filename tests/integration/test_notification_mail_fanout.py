"""알림을 메일로도 보내기 (계획 3.4, D-514).

못박는 것:
  * 켜 둔 사람에게 사건 하나당 메일 한 통이다. 끈 사람, 고르지 않은 유형, 관리자가 허용하지 않은 유형, 비활성이나
    보관된 계정에는 메일 행 자체가 없다.
  * 메일 서버 설정이 없으면 행은 `unconfigured` 이고 잡은 없다. **서버가 실패하고 있는 순간의 사건도 큐에 들어간다** -
    일시 실패는 재시도하고, 서버 탓 실패는 복구 때 아직 의미가 있는 것만 다시 보낸다.
  * 장애 동안 한 티켓이 보류, 계획, 진행 중, 검증, 완료로 바뀌면 복구 뒤 관찰자는 완료 메일 한 통만 받고 앞의 셋은
    `superseded` 다. 요청자는 결과 메일 한 통을 받는다.
  * 담당에서 빠진 사람, 다시 열린 티켓의 결과, 오래된 사건은 보내지 않는다. 재시도할 때마다 다시 본다.
  * 큐에 들어간 뒤 메일 알림을 끄거나 계정이 보관되면 보내지 않고(`cancelled`), 이메일을 바꿨으면 새 주소로 보낸다.
  * 방해금지는 메일에 영향을 주지 않는다. 관리자 알림 방송은 메일이 되지 않는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.models_base import join_names
from app.mail.models import (
    FAILURE_AUTH,
    FAILURE_RECIPIENT,
    FAILURE_TEMPORARY,
    MAIL_CANCELLED,
    MAIL_FAILED,
    MAIL_QUEUED,
    MAIL_RETRYING,
    MAIL_SENT,
    MAIL_SUPERSEDED,
    MAIL_UNCONFIGURED,
    MailDelivery,
)
from app.mail.transport import MailTransportError
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.work.models import TicketWatcher
from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.integration.test_mail_health import FakeServer
from tests.integration.test_password_reset import configure_smtp, drain_worker

pytestmark = pytest.mark.integration

PAGE = "page-mail-fanout"
NID_BOB = "notion-mail-bob"
TEMP_FAIL = MailTransportError("SMTP 421 잠시 뒤", kind=FAILURE_TEMPORARY, permanent=False, stage="send")
AUTH_FAIL = MailTransportError("SMTPAuthenticationError: (535, b'bad')", kind=FAILURE_AUTH, permanent=True, stage="auth")
RECIPIENT_FAIL = MailTransportError("SMTPRecipientsRefused", kind=FAILURE_RECIPIENT, permanent=True, stage="send")


@pytest.fixture()
def world(db, make_user, make_project) -> dict[str, str]:
    """바꾸는 사람(에이미), 담당자(밥), 관찰자(웬디), 요청자(리타)."""
    ids: dict[str, str] = {}
    for key, email, role, name in (
        ("amy", "mail-amy@goodmit.co.kr", "system_admin", "에이미"),
        ("bob", "mail-bob@goodmit.co.kr", "user", "밥"),
        ("wendy", "mail-wendy@goodmit.co.kr", "user", "웬디"),
        ("rita", "mail-rita@goodmit.co.kr", "user", "리타"),
    ):
        ids[key] = make_user(email=email, role=role, display_name=name).id
    db.add(UserNotionMapping(
        id="map-mail-bob", user_id=ids["bob"], notion_user_id=NID_BOB,
        status=STATUS_VERIFIED, source=SOURCE_MANUAL,
    ))
    project = make_project(name="메일 알림", external_id="proj-mail-fanout")
    ticket = TicketCache(
        notion_page_id=PAGE, org_id=DEFAULT_ORG_ID, notion_ticket_number=41, seq=41,
        title="메일로 알리는 티켓", status="계획", due_date="2026-12-31",
        project_ids=join_names(["proj-mail-fanout"]), project_uid=project.id,
        project_link=PROJECT_LINK_OK, project_names=join_names(["메일 알림"]),
        assignee_notion_ids=join_names([NID_BOB]), requester_user_id=ids["rita"],
    )
    db.add(ticket)
    db.flush()
    db.add(TicketWatcher(ticket_id=ticket.id, user_id=ids["wendy"]))
    db.commit()
    ids["ticket"] = ticket.id
    return ids


def _login(client, email: str) -> str:
    response = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _opt_in(app, user_id: str, types: list[str] | None = None, *, dnd: bool = False) -> None:
    from app.profiles.service import ensure_preference

    with app.state.session_factory() as db:
        pref = ensure_preference(db, user_id, now=app.state.clock.now())
        pref.mail_enabled = True
        pref.mail_types = None if types is None else ",".join(types)
        pref.dnd_enabled = dnd
        db.commit()


def _allow(app, types: list[str]) -> None:
    from app.settings.service import apply_setting

    with app.state.session_factory() as db:
        apply_setting(db, app.state.settings_cache, key="mail_notification_types", value=types,
                      updated_by=None, now=app.state.clock.now())
        db.commit()


def _status(client, csrf: str, status: str):
    r = client.patch(f"/api/tickets/{PAGE}", json={"status": status}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def _mails(app, email: str | None = None) -> list[MailDelivery]:
    with app.state.session_factory() as db:
        stmt = select(MailDelivery).where(MailDelivery.kind == "notification").order_by(MailDelivery.created_at)
        rows = list(db.execute(stmt).scalars())
        db.expunge_all()
    return [r for r in rows if email is None or r.to_email == email]


def _verify(client, csrf, app, settings, fake_clock, server):
    r = client.post("/api/admin/mail/verify", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    drain_worker(app, settings, fake_clock, server)


# ── 켜 둔 사람에게 한 통, 나머지는 행도 없다 ─────────────────────────────────

def test_an_opted_in_watcher_gets_exactly_one_mail_per_event(client, app, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")

    rows = _mails(app)
    assert [r.to_email for r in rows] == ["mail-wendy@goodmit.co.kr"], "켠 사람에게만 한 통이어야 한다"
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    assert [m["to"] for m in server.sent] == ["mail-wendy@goodmit.co.kr"]
    body = server.sent[0]["body"]
    assert f"/#/tickets/{PAGE}" in body, "메일이 그 티켓으로 바로 가는 주소를 싣지 않았다"
    assert "메일 알림을 끌 수 있습니다" in body
    assert _mails(app)[0].status == MAIL_SENT


def test_nobody_who_should_not_get_mail_gets_a_row(client, app, db, world):
    configure_smtp(app)
    _opt_in(app, world["bob"], types=["ticket_assigned"])       # 상태 변경을 고르지 않았다
    _opt_in(app, world["rita"])                                  # 끝나지 않았으니 결과 알림이 없다
    from app.users.models import User

    wendy = db.get(User, world["wendy"])
    wendy.active = False                                         # 비활성 계정
    db.commit()
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    assert _mails(app) == [], [r.to_email for r in _mails(app)]


def test_a_type_the_admin_does_not_allow_is_never_mailed(client, app, world):
    configure_smtp(app)
    _allow(app, ["ticket_assigned"])
    _opt_in(app, world["wendy"], types=["ticket_status_changed"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    assert _mails(app) == []


def test_dnd_does_not_silence_mail(client, app, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"], dnd=True)
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    assert len(_mails(app, "mail-wendy@goodmit.co.kr")) == 1, "방해금지가 메일까지 막았다"


def test_admin_broadcasts_do_not_become_mail(app, world):
    configure_smtp(app)
    _opt_in(app, world["amy"])
    from app.notifications.service import notify_admins

    with app.state.session_factory() as db:
        notify_admins(db, type_="backup_failed", title="백업 실패", now=app.state.clock.now())
        db.commit()
    assert _mails(app) == []


def test_the_same_notification_never_makes_two_mails(app, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    from app.notifications.mail import fan_out_mail
    from app.notifications.service import notify_user

    with app.state.session_factory() as db:
        row = notify_user(db, world["wendy"], type_="ticket_status_changed", title="상태 변경",
                          related=("ticket", PAGE), now=app.state.clock.now())
        fan_out_mail(db, row, now=app.state.clock.now())
        db.commit()
    assert len(_mails(app)) == 1


# ── 설정이 없거나 서버가 실패할 때 ───────────────────────────────────────────

def test_without_mail_settings_the_row_is_unconfigured_and_no_job_exists(client, app, world):
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    rows = _mails(app)
    assert len(rows) == 1 and rows[0].status == MAIL_UNCONFIGURED and rows[0].job_id is None
    status = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()
    assert status["pending_unconfigured_count"] == 1, "설정 뒤 보낼 수 있는 알림 메일로 세지 않았다"


def test_an_event_during_a_failing_server_is_queued_and_sent_after_it_recovers(
    client, app, settings, fake_clock, world,
):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _verify(client, csrf, app, settings, fake_clock, FakeServer(fail_with=TEMP_FAIL))
    health = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()["health"]
    assert health["state"] == "failing"

    _status(client, csrf, "진행")
    (row,) = _mails(app)
    assert row.status == MAIL_QUEUED and row.job_id, "서버가 실패하고 있다는 이유로 사건을 버렸다"
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=TEMP_FAIL))
    assert _mails(app)[0].status == MAIL_RETRYING

    fake_clock.advance(61)
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    assert _mails(app)[0].status == MAIL_SENT
    assert len(server.sent) == 1


def test_recovery_resends_server_failures_but_not_recipient_refusals(
    client, app, settings, fake_clock, world,
):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    _opt_in(app, world["bob"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=AUTH_FAIL))
    assert {r.status for r in _mails(app)} == {MAIL_FAILED}

    # 밥의 메일만 받는 사람 거부로 바꿔 둔다 - 서버가 살아나도 같은 결과라 다시 보내지 않는다.
    with app.state.session_factory() as db:
        bob_row = db.execute(select(MailDelivery).where(MailDelivery.to_email == "mail-bob@goodmit.co.kr")).scalar_one()
        bob_row.failure_kind = FAILURE_RECIPIENT
        db.commit()
    fake_clock.advance(60)
    server = FakeServer()
    _verify(client, csrf, app, settings, fake_clock, server)
    by_to = {r.to_email: r.status for r in _mails(app)}
    assert by_to == {"mail-wendy@goodmit.co.kr": MAIL_SENT, "mail-bob@goodmit.co.kr": MAIL_FAILED}


def test_after_an_outage_only_the_last_status_mail_goes_out(client, app, db, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    _opt_in(app, world["rita"])
    row = db.get(TicketCache, world["ticket"])
    row.status = "보류"
    db.commit()
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    broken = FakeServer(fail_with=AUTH_FAIL)
    for status in ("계획", "진행", "검증", "완료"):
        fake_clock.advance(300)
        _status(client, csrf, status)
        drain_worker(app, settings, fake_clock, broken)
    assert {r.status for r in _mails(app)} == {MAIL_FAILED}

    fake_clock.advance(300)
    server = FakeServer()
    _verify(client, csrf, app, settings, fake_clock, server)

    wendy = _mails(app, "mail-wendy@goodmit.co.kr")
    assert [r.status for r in wendy] == [MAIL_SUPERSEDED] * 3 + [MAIL_SENT]
    assert {r.skip_reason for r in wendy[:3]} == {"newer_status_event"}
    assert wendy[-1].subject.endswith("완료")
    rita = _mails(app, "mail-rita@goodmit.co.kr")
    assert [r.status for r in rita] == [MAIL_SENT], "요청자가 결과 메일 한 통을 받지 못했다"
    assert sorted(m["to"] for m in server.sent) == ["mail-rita@goodmit.co.kr", "mail-wendy@goodmit.co.kr"]


def test_a_retrying_mail_is_rechecked_before_every_attempt(client, app, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    drain_worker(app, settings, fake_clock, FakeServer(fail_with=TEMP_FAIL))
    assert _mails(app)[0].status == MAIL_RETRYING

    fake_clock.advance(30)
    _status(client, csrf, "검증")          # 더 새로운 사건이 생겼다
    fake_clock.advance(61)
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    first, second = _mails(app)
    assert first.status == MAIL_SUPERSEDED and first.skip_reason == "newer_status_event"
    assert second.status == MAIL_SENT
    assert len(server.sent) == 1



# ── 열람 권한은 판정이 터져도 보내지 않는다 (D-547) ─────────────────────────────

def test_a_watcher_who_lost_access_to_the_ticket_is_not_mailed(client, app, settings, fake_clock, world):
    """큐에 들어간 뒤 그 티켓을 볼 수 없게 되면(소속이 빠졌다) 티켓 제목이 담긴 메일을 보내지 않는다."""
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    from app.users.models import User

    with app.state.session_factory() as db:
        db.get(User, world["wendy"]).membership_kind = "unassigned"
        db.commit()
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    (mail,) = _mails(app, "mail-wendy@goodmit.co.kr")
    assert (mail.status, mail.skip_reason) == (MAIL_CANCELLED, "no_access")
    assert server.sent == []


def test_a_crashing_relevance_rule_cannot_open_the_access_check(client, app, settings, fake_clock, world, monkeypatch):
    """의미 판정이 터지면 보내는 쪽으로 넘어가지만(fail-open), 열람 권한은 따로 다시 본다(fail-closed)."""
    from app.mail import relevance
    from app.users.models import User

    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")

    def boom(*_a, **_kw):
        raise RuntimeError("의미 판정 오류")

    monkeypatch.setitem(relevance.NOTIFICATION_RULES, "ticket_status_changed", boom)
    with app.state.session_factory() as db:
        db.get(User, world["wendy"]).membership_kind = "unassigned"
        db.commit()
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    (mail,) = _mails(app, "mail-wendy@goodmit.co.kr")
    assert (mail.status, mail.skip_reason) == (MAIL_CANCELLED, "no_access")
    assert server.sent == []


# ── 의미를 잃은 사건 ─────────────────────────────────────────────────────────

def test_an_assignment_mail_is_dropped_when_the_person_was_unassigned(client, app, db, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    r = client.patch(f"/api/tickets/{PAGE}", json={"assignee_user_ids": [world["bob"], world["wendy"]]},
                     headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/tickets/{PAGE}", json={"assignee_user_ids": [world["bob"]]},
                     headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    drain_worker(app, settings, fake_clock, FakeServer())
    (mail,) = [m for m in _mails(app, "mail-wendy@goodmit.co.kr")]
    assert mail.status == MAIL_SUPERSEDED and mail.skip_reason == "no_longer_assignee"


def test_a_result_mail_is_dropped_when_the_ticket_was_reopened(client, app, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["rita"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "완료")
    fake_clock.advance(60)
    _status(client, csrf, "진행")
    drain_worker(app, settings, fake_clock, FakeServer())
    (mail,) = _mails(app, "mail-rita@goodmit.co.kr")
    assert mail.status == MAIL_SUPERSEDED and mail.skip_reason == "reopened"


def test_an_old_event_is_not_sent(client, app, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    from app.settings.service import apply_setting

    with app.state.session_factory() as db:
        apply_setting(db, app.state.settings_cache, key="mail_notification_max_age_days", value=1,
                      updated_by=None, now=app.state.clock.now())
        db.commit()
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    fake_clock.advance(2 * 86400)
    drain_worker(app, settings, fake_clock, FakeServer())
    (mail,) = _mails(app)
    assert mail.status == MAIL_SUPERSEDED and mail.skip_reason == "too_old"


# ── 큐에 들어간 뒤 받는 사람이 바뀌면 ────────────────────────────────────────

def test_opting_out_after_queueing_cancels_without_sending(client, app, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    wendy = _login(client, "mail-wendy@goodmit.co.kr")
    r = client.patch("/api/me/preferences", json={"mail_enabled": False}, headers={"X-CSRF-Token": wendy})
    assert r.status_code == 200, r.text
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    (mail,) = _mails(app)
    assert mail.status == MAIL_CANCELLED and mail.skip_reason == "opted_out"
    assert server.sent == [], "끈 사람에게 보냈다"


def test_archiving_after_queueing_cancels(client, app, db, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    from app.users.models import User

    db.get(User, world["wendy"]).archived_at = app.state.clock.now()
    db.commit()
    drain_worker(app, settings, fake_clock, FakeServer())
    (mail,) = _mails(app)
    assert mail.status == MAIL_CANCELLED and mail.skip_reason == "archived"


def test_a_changed_email_gets_the_mail_at_the_new_address(client, app, db, settings, fake_clock, world):
    configure_smtp(app)
    _opt_in(app, world["wendy"])
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    _status(client, csrf, "진행")
    from app.users.models import User

    db.get(User, world["wendy"]).email = "mail-wendy-new@goodmit.co.kr"
    db.commit()
    server = FakeServer()
    drain_worker(app, settings, fake_clock, server)
    assert [m["to"] for m in server.sent] == ["mail-wendy-new@goodmit.co.kr"]


# ── 내 설정 화면과 관리 화면 ─────────────────────────────────────────────────

def test_preferences_carry_the_mail_block_and_accept_changes(client, app, world):
    csrf = _login(client, "mail-wendy@goodmit.co.kr")
    body = client.get("/api/me/preferences", headers={"X-CSRF-Token": csrf}).json()["mail"]
    assert body["enabled"] is False, "메일 알림은 기본으로 꺼져 있어야 한다"
    assert body["types"] == ["ticket_assigned", "ticket_status_changed", "ticket_resolved"]
    assert [c["key"] for c in body["catalog"]] == body["types"]
    assert body["delivery"]["state"] == "unconfigured"
    assert "설정하지 않아" in body["delivery"]["message"]

    r = client.patch("/api/me/preferences", json={"mail_enabled": True}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["mail"]["enabled"] is True
    r = client.patch("/api/me/preferences", json={"mail_types": ["ticket_resolved"]}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["mail"]["types"] == ["ticket_resolved"]
    # 둘러보기 경로도 같은 모양을 돌려준다 - 한쪽만 빠뜨리면 화면 캐시가 그 칸을 잃는다.
    r = client.post("/api/me/tour", json={"action": "skip"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["mail"]["types"] == ["ticket_resolved"]


def test_a_type_the_admin_does_not_allow_cannot_be_chosen(client, world):
    csrf = _login(client, "mail-wendy@goodmit.co.kr")
    r = client.patch("/api/me/preferences", json={"mail_types": ["chat_mentioned"]}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422, r.text


def test_the_admin_status_lists_the_mailable_catalog(client, world):
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    body = client.get("/api/admin/mail/status", headers={"X-CSRF-Token": csrf}).json()["notification_mail"]
    assert body["allowed"] == ["ticket_assigned", "ticket_status_changed", "ticket_resolved"]
    # 메일로 보낼 수 있는 유형은 여덟이다 - D-516 이 AI 연결 상태를 더했다(시스템 관리자만 받는다).
    assert len(body["catalog"]) == 8 and body["max_age_days"] == 7
    assert "ai_provider_state" in {item["key"] for item in body["catalog"]}


def test_the_allow_list_rejects_types_that_cannot_be_mailed(client, world):
    csrf = _login(client, "mail-amy@goodmit.co.kr")
    r = client.put("/api/admin/settings/mail_notification_types", json={"value": ["backup_failed"]},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422, r.text
