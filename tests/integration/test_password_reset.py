"""사용자가 스스로 비밀번호를 되찾는 경로 (9-9 P4).

지금까지 이 저장소에서 비밀번호를 되돌리는 방법은 **관리자가 임시 비밀번호를 발급**하는 것
하나뿐이었다(app/users/service.py::admin_reset_password). 15명짜리 조직에서는 견디지만
파는 제품에서는 안 된다.

이 파일이 못박는 것은 넷이다. 넷 다 "되긴 되는데 위험한" 구현을 막는다.

  1. **계정 열거 금지** - 있는 계정과 없는 계정의 응답이 한 글자도 달라선 안 된다.
     사내망이라도 문제다: 누가 이 회사에 다니는지가 로그인 화면에서 새어 나간다.
  2. **1회용** - 두 번째 사용은 거절된다. 안 그러면 메일함을 한 번 본 사람이 언제든 들어온다.
  3. **만료** - 시간이 지나면 죽는다. 메일은 영원히 남는다.
  4. **평문 미저장** - 토큰 원문이 DB 파일 어디에도 없어야 한다. 저장소가 secret 을 파일
     참조로 분리해 둔 이유와 같다(불변 §3). DB 를 읽을 수 있는 사람이 곧 모든 계정에
     들어갈 수 있게 되면 안 된다.
"""

from __future__ import annotations

import re

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

NEW_PASSWORD = "Reset-P4ssw0rd!"
_TOKEN_RE = re.compile(r"token=([A-Za-z0-9_\-]{20,})")


class FakeSmtp:
    """워커가 실제로 부르는 자리에 끼우는 가짜 발송기."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.fail = fail

    def send(self, config, secret_provider, *, to_email, subject, body) -> None:
        if self.fail:
            raise RuntimeError("SMTP 서버가 응답하지 않습니다")
        self.sent.append({"to": to_email, "subject": subject, "body": body})


def configure_smtp(app, **overrides):
    """SMTP 설정을 '채워진 설치' 상태로 만든다."""
    from app.settings.service import apply_setting

    value = {
        "enabled": True,
        "host": "smtp.internal",
        "port": 587,
        "security": "starttls",
        "from_address": "noreply@example.com",
        "from_name": "ClovirAssist",
        "username": "",
        "password_ref": "",
        "timeout_seconds": 10,
    }
    value.update(overrides)
    with app.state.session_factory() as db:
        apply_setting(
            db,
            app.state.settings_cache,
            key="smtp",
            value=value,
            updated_by=None,
            now=app.state.clock.now(),
        )
        db.commit()
    return value


def drain_worker(app, settings, fake_clock, transport):
    """큐에 쌓인 메일 잡을 워커에서 처리한다. 처리한 건수를 돌려준다."""
    from app.core.secret_refs import FileSecretReferenceProvider
    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import build_handlers

    ctx = WorkerContext(
        settings=settings,
        clock=fake_clock,
        extras={
            "mail_transport": transport,
            "secret_provider": FileSecretReferenceProvider(settings.secrets_dir),
        },
    )
    worker = Worker(app.state.session_factory, fake_clock, build_handlers(), ctx)
    processed = 0
    while worker.run_once():
        processed += 1
        if processed > 20:  # 무한 루프 방지
            break
    return processed


def request_reset(client, email):
    return client.post("/forgot-password", json={"email": email})


# ── 1. 계정 열거 금지 ────────────────────────────────────────────────────────


def test_request_answers_identically_for_known_and_unknown_accounts(client, app, make_user):
    configure_smtp(app)
    make_user("known@goodmit.co.kr")

    known = request_reset(client, "known@goodmit.co.kr")
    unknown = request_reset(client, "nobody-here@goodmit.co.kr")

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # 있는 계정을 가리키는 어떤 힌트도 본문에 있으면 안 된다.
    assert "known@goodmit.co.kr" not in known.text


def test_request_for_a_disabled_account_looks_the_same(client, app, make_user):
    configure_smtp(app)
    make_user("off@goodmit.co.kr", active=False)

    disabled = request_reset(client, "off@goodmit.co.kr")
    unknown = request_reset(client, "ghost@goodmit.co.kr")
    assert disabled.status_code == unknown.status_code == 200
    assert disabled.json() == unknown.json()


def test_only_a_real_account_actually_gets_a_mail_queued(client, app, make_user):
    """응답은 같아도 **실제 발송**은 진짜 계정에만 일어난다."""
    from app.mail.models import MailDelivery

    configure_smtp(app)
    make_user("real@goodmit.co.kr")
    request_reset(client, "real@goodmit.co.kr")
    request_reset(client, "fake@goodmit.co.kr")

    with app.state.session_factory() as db:
        rows = db.query(MailDelivery).all()
        assert [r.to_email for r in rows] == ["real@goodmit.co.kr"]


# ── 2. 설정이 없으면 없다고 한다 ─────────────────────────────────────────────


def test_unconfigured_smtp_is_reported_instead_of_pretending(client, app, make_user):
    """조용히 200 을 주면 사용자는 오지 않을 메일을 기다린다."""
    from app.mail.models import MailDelivery

    make_user("waiting@goodmit.co.kr")
    response = request_reset(client, "waiting@goodmit.co.kr")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "mail_not_configured"
    # 보내지 못한 요청을 큐에 쌓아 두지도 않는다 - 영원히 재시도할 잡을 만들면
    # 설정을 켜는 날 몇 달 전 토큰 메일이 한꺼번에 나간다.
    with app.state.session_factory() as db:
        assert db.query(MailDelivery).count() == 0


def test_unconfigured_answer_is_also_the_same_for_unknown_accounts(client, make_user):
    """설정 문제는 계정과 무관하다 - 여기서도 열거가 새면 안 된다."""
    make_user("waiting2@goodmit.co.kr")
    known = request_reset(client, "waiting2@goodmit.co.kr")
    unknown = request_reset(client, "nobody2@goodmit.co.kr")
    assert known.status_code == unknown.status_code == 503
    assert known.json()["error"]["code"] == unknown.json()["error"]["code"]


# ── 3. 토큰: 1회용, 만료, 평문 미저장 ────────────────────────────────────────


def _token_from_mail(transport) -> str:
    assert transport.sent, "메일이 한 통도 나가지 않았다"
    match = _TOKEN_RE.search(transport.sent[-1]["body"])
    assert match, f"메일 본문에 재설정 토큰이 없다: {transport.sent[-1]['body'][:300]}"
    return match.group(1)


@pytest.fixture()
def issued_token(client, app, settings, fake_clock, make_user):
    configure_smtp(app)
    make_user("reset-me@goodmit.co.kr")
    assert request_reset(client, "reset-me@goodmit.co.kr").status_code == 200
    transport = FakeSmtp()
    drain_worker(app, settings, fake_clock, transport)
    return _token_from_mail(transport)


def test_token_resets_the_password_and_lets_the_user_log_in(client, issued_token):
    response = client.post(
        "/reset-password", json={"token": issued_token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 200, response.text

    old = client.post(
        "/login", json={"email": "reset-me@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert old.status_code == 401
    new = client.post(
        "/login", json={"email": "reset-me@goodmit.co.kr", "password": NEW_PASSWORD}
    )
    assert new.status_code == 200, new.text


def test_token_is_single_use(client, issued_token):
    first = client.post(
        "/reset-password", json={"token": issued_token, "new_password": NEW_PASSWORD}
    )
    assert first.status_code == 200
    second = client.post(
        "/reset-password", json={"token": issued_token, "new_password": "Another-P4ss!x"}
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_reset_token"


def test_token_expires(client, app, fake_clock, issued_token):
    from app.auth.reset_service import RESET_TOKEN_TTL_SECONDS

    fake_clock.advance(RESET_TOKEN_TTL_SECONDS + 1)
    response = client.post(
        "/reset-password", json={"token": issued_token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


def test_token_is_never_stored_in_plaintext(app, db, issued_token):
    """**DB 안 어디에도** 재설정 토큰 원문이 없어야 한다 — 컬럼 하나를 보는 것으로는 부족하다.

    잡 payload, 메일 아웃박스, 감사 로그 어디로도 새면 안 된다. 실제로 새기 쉬운 자리가
    잡 payload 다(메일 본문을 payload 에 실으면 그 순간 평문이 DB 에 앉는다).

    qa-contract-change: 예전에는 SQLite 파일 바이트를 통째로 훑었다(`-wal`·`-shm` 포함).
    PG 에는 그렇게 훑을 «파일» 이 없다 — 데이터는 서버가 들고 있다. 그래서 같은 성질을
    스키마를 통해 확인한다: 문자열을 담을 수 있는 **모든 컬럼**(text·varchar·jsonb)을
    전수로 훑는다. 오히려 이쪽이 정확하다 — 파일 스캔은 이미 지워진 페이지의 잔해까지
    보므로 «아직 안 지워진 옛 값» 과 «지금 저장된 값» 을 구별하지 못했다.
    """
    from sqlalchemy import text as sql_text

    columns = db.execute(sql_text("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type IN ('text', 'character varying', 'jsonb')
        ORDER BY table_name, column_name
    """)).all()

    # 빈 목록을 훑고 초록을 찍는 상태가 아님을 먼저 보인다(D-213).
    assert len(columns) > 100, f"훑을 컬럼을 {len(columns)}개밖에 못 찾았다 - 검사가 헛돈다"

    found = []
    for table, column, _dtype in columns:
        hits = db.execute(
            sql_text(
                f'SELECT count(*) FROM "{table}" WHERE CAST("{column}" AS text) LIKE :needle'  # noqa: S608
            ),
            {"needle": f"%{issued_token}%"},
        ).scalar()
        if hits:
            found.append(f"{table}.{column} ({hits}행)")

    assert not found, "재설정 토큰 원문이 DB 에 저장돼 있다: " + ", ".join(found)


def test_stored_row_holds_only_a_hash(app, issued_token):
    from app.auth.models import PasswordResetToken
    from app.core.security import hash_token

    with app.state.session_factory() as db:
        rows = db.query(PasswordResetToken).all()
        assert len(rows) == 1
        assert rows[0].token_hash == hash_token(issued_token)
        assert issued_token not in rows[0].token_hash


def test_reset_revokes_existing_sessions(client, app, settings, fake_clock, make_user):
    """비밀번호를 잃어버린 이유가 '털렸기 때문' 일 수 있다."""
    from fastapi.testclient import TestClient

    configure_smtp(app)
    make_user("hijacked@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as other:
        other.post(
            "/login",
            json={"email": "hijacked@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        assert other.get("/api/me").status_code == 200

        request_reset(client, "hijacked@goodmit.co.kr")
        transport = FakeSmtp()
        drain_worker(app, settings, fake_clock, transport)
        token = _token_from_mail(transport)
        assert client.post(
            "/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
        ).status_code == 200

        assert other.get("/api/me").status_code == 401


def test_weak_password_is_rejected_by_the_same_policy(client, issued_token):
    response = client.post(
        "/reset-password", json={"token": issued_token, "new_password": "short"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_token_is_rejected(client, app):
    configure_smtp(app)
    response = client.post(
        "/reset-password", json={"token": "not-a-real-token-value", "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


# ── 4. 화면이 실제로 있다 ────────────────────────────────────────────────────


def test_the_pages_the_mail_links_to_actually_exist(client, app, issued_token):
    """메일이 가리키는 주소가 없으면 그건 없는 것을 있는 척 그린 것이다."""
    assert client.get("/forgot-password").status_code == 200
    page = client.get(f"/reset-password?token={issued_token}")
    assert page.status_code == 200
    assert "비밀번호" in page.text


def test_login_page_offers_the_link_only_when_mail_works(client, app):
    """눌러도 안 되는 링크를 그려 두면 사용자를 두 번 헛걸음시킨다."""
    before = client.get("/login")
    assert before.status_code == 200
    assert "/forgot-password" not in before.text

    configure_smtp(app)
    after = client.get("/login")
    assert "/forgot-password" in after.text


def test_forgot_password_page_says_it_cannot_send(client):
    page = client.get("/forgot-password")
    assert page.status_code == 200
    assert "메일 발송이 설정되어 있지 않아" in page.text
    # 보내지도 못할 폼을 그려 두지 않는다.
    assert 'action="/forgot-password"' not in page.text


def test_no_js_form_flow_works_end_to_end(client, app, settings, fake_clock, make_user):
    """JS 가 막힌 브라우저에서도 끝까지 간다 - 이 화면엔 스크립트가 하나도 없다."""
    configure_smtp(app)
    make_user("nojs@goodmit.co.kr")
    posted = client.post(
        "/forgot-password", data={"email": "nojs@goodmit.co.kr"}, follow_redirects=False
    )
    assert posted.status_code == 200
    assert "요청을 접수했습니다" in posted.text

    transport = FakeSmtp()
    drain_worker(app, settings, fake_clock, transport)
    token = _token_from_mail(transport)

    done = client.post(
        "/reset-password",
        data={"token": token, "new_password": NEW_PASSWORD},
        follow_redirects=False,
    )
    assert done.status_code == 303
    assert done.headers["location"] == "/login?reset=1"
    assert client.post(
        "/login", json={"email": "nojs@goodmit.co.kr", "password": NEW_PASSWORD}
    ).status_code == 200
