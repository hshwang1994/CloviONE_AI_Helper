"""첫 관리자 계정 경로 (계획 3.17, D-522).

설치가 끝난 서버에 계정이 하나도 없을 때 첫 시스템 관리자를 만드는 유일한 문이다. 로그인 전 경로라 세션도 CSRF 토큰도
없으므로, 이 문을 지키는 것이 무엇인지를 하나씩 잰다.

못박는 성질:
1. 계정이 하나도 없을 때만 열린다. 사용자가 한 명이라도 있으면 화면도 쓰기도 404 다.
2. 설정 코드는 128비트 이상이고 서버에는 해시만 남는다. 원문은 코드 파일, 감사 기록, 응답 어디에도 없다.
3. 틀린 코드는 실패로 세고 다섯 번이면 코드를 폐기한다. 만료된 코드는 쓸 수 없다.
4. 맞는 코드면 시스템 관리자 한 명을 만들고 코드를 지운다. 같은 코드로 두 번째 계정을 만들 수 없다.
5. 비밀번호 정책에 걸리면 코드를 태우지 않는다. 오타 한 번에 서버로 돌아가게 만들지 않는다.
6. 다른 사이트에서 온 요청은 Origin 검사가, 쏟아지는 요청은 속도 제한이 막는다.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.setup import first_admin

pytestmark = pytest.mark.security

PAGE = "/setup/first-admin"
GOOD_PASSWORD = "Clovi-first-admin-2026!"


@pytest.fixture()
def data_dir(client, tmp_path, monkeypatch):
    monkeypatch.setattr(client.app.state.settings, "data_dir", tmp_path)
    return tmp_path


def _issue(client, db, data_dir):
    issued = first_admin.issue_code(db, data_dir, now=client.app.state.clock.now())
    assert issued is not None
    return issued


def _post(client, code, **extra):
    body = {"code": code, "email": "first@example.com", "name": "첫 관리자", "password": GOOD_PASSWORD,
            "password_confirm": GOOD_PASSWORD, **extra}
    return client.post(PAGE, json=body)


def test_the_code_is_long_random_and_only_its_hash_is_stored(client, db, data_dir):
    assert first_admin.users_exist(db) is False
    one = _issue(client, db, data_dir)
    stored = (data_dir / first_admin.CODE_FILE_NAME).read_text(encoding="utf-8")
    assert len(first_admin.normalize_code(one.code)) >= 26, "128비트보다 짧은 코드다"
    assert first_admin.normalize_code(one.code) not in stored and one.code not in stored, "코드 원문이 파일에 남았다"
    assert json.loads(stored)["failures"] == 0
    two = _issue(client, db, data_dir)
    assert one.code != two.code, "다시 만든 코드가 같다"


def test_the_page_says_when_there_is_no_code(client, db, data_dir):
    page = client.get(PAGE)
    assert page.status_code == 200
    assert "지금 쓸 수 있는 설정 코드가 없습니다" in page.text and "<form" not in page.text
    _issue(client, db, data_dir)
    assert 'action="/setup/first-admin"' in client.get(PAGE).text


def test_a_right_code_creates_one_system_admin_and_burns_the_code(client, db, data_dir):
    from app.audit.models import AuditLog
    from app.users.models import ROLE_SYSTEM_ADMIN, User

    issued = _issue(client, db, data_dir)
    # 사람이 콘솔에서 옮겨 적으면 대시와 대소문자가 섞인다. 뜻이 없으므로 같은 코드다.
    created = _post(client, first_admin.format_code(issued.code).lower())
    assert created.status_code == 201, created.text
    assert issued.code not in created.text

    users = db.query(User).all()
    assert [(u.email, u.role, u.must_change_password) for u in users] == [("first@example.com", ROLE_SYSTEM_ADMIN, False)]
    assert not (data_dir / first_admin.CODE_FILE_NAME).exists(), "쓴 코드가 남아 있다"
    audit = db.query(AuditLog).filter(AuditLog.action == "setup.first_admin_created").one()
    assert issued.code not in json.dumps([audit.before_json, audit.after_json], ensure_ascii=False, default=str)

    # 이제 계정이 있다. 문이 닫힌다 - 같은 코드든 새 코드든.
    assert client.get(PAGE).status_code == 404
    assert _post(client, issued.code, email="second@example.com").status_code == 404
    assert first_admin.issue_code(db, data_dir, now=client.app.state.clock.now()) is None


def test_the_door_is_closed_when_any_user_exists(client, db, data_dir, make_user):
    _issue(client, db, data_dir)
    make_user("someone@example.com", role="user")
    assert client.get(PAGE).status_code == 404
    assert _post(client, "ANYTHING").status_code == 404


def test_wrong_codes_count_and_the_fifth_discards_the_code(client, db, data_dir):
    from app.audit.models import AuditLog

    issued = _issue(client, db, data_dir)
    path = data_dir / first_admin.CODE_FILE_NAME
    for attempt in range(1, first_admin.MAX_FAILURES):
        reply = _post(client, "WRONG-CODE-0000")
        assert reply.status_code == 400, reply.text
        assert json.loads(path.read_text(encoding="utf-8"))["failures"] == attempt
    last = _post(client, "WRONG-CODE-0000")
    assert last.status_code == 400 and "폐기" in last.json()["error"]["message"]
    assert not path.exists(), "다섯 번 틀렸는데 코드가 살아 있다"
    assert db.query(AuditLog).filter(AuditLog.action == "setup.first_admin_locked").count() == 1
    # 폐기된 코드는 맞게 넣어도 쓸 수 없다.
    assert _post(client, issued.code).status_code == 400


def test_an_expired_code_does_not_work(client, db, data_dir):
    issued = first_admin.issue_code(db, data_dir, now=client.app.state.clock.now() - first_admin.CODE_TTL - timedelta(minutes=1))
    reply = _post(client, issued.code)
    assert reply.status_code == 400 and "만료" in reply.json()["error"]["message"]
    assert not (data_dir / first_admin.CODE_FILE_NAME).exists()


def test_a_weak_password_does_not_burn_the_code(client, db, data_dir):
    issued = _issue(client, db, data_dir)
    weak = _post(client, issued.code, password="short", password_confirm="short")
    assert weak.status_code == 422, weak.text
    stored = json.loads((data_dir / first_admin.CODE_FILE_NAME).read_text(encoding="utf-8"))
    assert stored["failures"] == 0, "비밀번호 오타가 코드 실패로 세어졌다"
    mismatch = _post(client, issued.code, password_confirm="Different-2026!")
    assert mismatch.status_code == 422
    assert _post(client, issued.code).status_code == 201


def test_cross_site_requests_and_floods_are_refused(client, db, data_dir, monkeypatch):
    issued = _issue(client, db, data_dir)
    cross = client.post(PAGE, json={"code": issued.code}, headers={"Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403, cross.text
    monkeypatch.setattr(client.app.state.login_ratelimiter, "allow", lambda key: False)
    assert _post(client, issued.code).status_code == 429
