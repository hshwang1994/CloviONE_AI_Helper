"""운영 콘솔 시스템 설정 API (§S, 9-6).

여기서 검사하는 것은 **화면이 진실을 말하는가**다. 특권 헬퍼는 없을 수도 있는 부품이라
(개발 머신·컨테이너·헬퍼를 안 깐 설치) "없음" 을 정확히 전달하는 것이 기능의 일부다.
"""

from __future__ import annotations

import pytest

from app.sysops.client import STATUS_NOT_INSTALLED, STATUS_OK, HelperReply

pytestmark = pytest.mark.integration


class _FakeClient:
    """가짜 도우미. 무엇을 호출했는지 기록해 **실제로 전달됐는지** 확인한다."""

    def __init__(self, reply: HelperReply) -> None:
        self.reply = reply
        self.calls: list[tuple[str, dict]] = []

    def call(self, action, params=None):
        self.calls.append((action, dict(params or {})))
        return self.reply

    def probe(self):
        return self.call("system.info")


@pytest.fixture()
def missing_helper(client):
    fake = _FakeClient(HelperReply.unavailable(
        STATUS_NOT_INSTALLED, "시스템 설정 도우미가 설치되어 있지 않습니다(clovirone-privhelper)."
    ))
    client.app.state.sysops_client = fake
    yield fake
    client.app.state.sysops_client = None


@pytest.fixture()
def working_helper(client):
    fake = _FakeClient(HelperReply(
        available=True, status=STATUS_OK, ok=True, changed=True,
        detail="타임존을 Asia/Seoul 로 바꿨습니다.", data={"timezone": "Asia/Seoul"},
    ))
    client.app.state.sysops_client = fake
    yield fake
    client.app.state.sysops_client = None


def test_only_the_portal_operator_can_reach_system_settings(client, login_as, working_helper):
    """🔴 `admin` 은 **부서 범위로 좁혀질 수 있는** 역할이다.

    부서 관리자가 서버의 DNS·인증서를 바꿀 수 있으면 안 된다. 여기서 바뀌는 것은 조직이
    아니라 서버 한 대 전체라 범위라는 개념 자체가 없다.
    """
    login_as("admin")
    assert client.get("/api/admin/system").status_code == 403
    login_as("user")
    assert client.get("/api/admin/system").status_code == 403


def test_a_missing_helper_is_a_state_not_an_error(client, login_as, missing_helper):
    """500 을 주면 화면이 "일시적 오류" 로 읽고 재시도만 반복한다."""
    login_as("system_admin")
    r = client.get("/api/admin/system")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert "설치" in body["detail"], body["detail"]
    assert body["info"] == {}, "도우미가 없는데 정보를 지어냈다"
    assert body["actions"], "이 서버에서 무엇을 바꿀 수 있는지는 도우미 없이도 말할 수 있어야 한다"


def test_a_missing_helper_never_reports_success(client, login_as, missing_helper):
    """🔴 가장 나쁜 실패다 - 사용자는 타임존을 바꿨다고 믿고 떠나는데 아무것도 안 바뀐다."""
    csrf = login_as("system_admin")
    r = client.post(
        "/api/admin/system/timezone.set",
        json={"params": {"timezone": "Asia/Seoul"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False, f"도우미가 없는데 성공이라고 답했다: {body}"
    assert body["available"] is False
    assert body["changed"] is False


def test_the_request_actually_reaches_the_helper(client, login_as, working_helper):
    """오탐 방지 - 막는 것만 검사하면 아무것도 전달 안 해도 통과한다."""
    csrf = login_as("system_admin")
    r = client.post(
        "/api/admin/system/timezone.set",
        json={"params": {"timezone": "Asia/Seoul"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert working_helper.calls[-1] == ("timezone.set", {"timezone": "Asia/Seoul"}), (
        f"도우미에게 전달된 내용이 다르다: {working_helper.calls}"
    )


def test_the_audit_trail_records_the_action_but_not_its_arguments(
    client, login_as, db, working_helper
):
    """🔴 인증서 교체는 **개인키를 인자로** 받는다. 감사 로그는 오래 남고 널리 복사된다."""
    from sqlalchemy import select

    from app.core.audit import AuditLog

    csrf = login_as("system_admin")
    client.post(
        "/api/admin/system/cert.install",
        json={"params": {"certificate": "-----BEGIN CERTIFICATE-----\nX\n-----END CERTIFICATE-----",
                         "private_key": "SUPERSECRETKEYMATERIAL"}},
        headers={"X-CSRF-Token": csrf},
    )
    db.expire_all()
    rows = db.execute(
        select(AuditLog).where(AuditLog.object_type == "system_setting")
    ).scalars().all()
    assert rows, "시스템 변경이 감사에 남지 않았다"
    blob = "\n".join(str(r.after_json or "") + str(r.before_json or "") for r in rows)
    assert "SUPERSECRETKEYMATERIAL" not in blob, f"개인키가 감사 로그에 남았다: {blob}"
    assert rows[-1].object_id == "cert.install", rows[-1].object_id


def test_a_failed_action_is_still_audited(client, login_as, db, missing_helper):
    """되돌아간 시도는 나중에 "그때 무슨 일이 있었나" 를 재구성할 유일한 단서다."""
    from sqlalchemy import select

    from app.core.audit import AuditLog

    csrf = login_as("system_admin")
    client.post(
        "/api/admin/system/dns.set",
        json={"params": {"servers": ["10.0.0.1"]}},
        headers={"X-CSRF-Token": csrf},
    )
    db.expire_all()
    rows = db.execute(
        select(AuditLog).where(AuditLog.object_type == "system_setting")
    ).scalars().all()
    assert rows, "실패한 시스템 변경이 감사에 남지 않았다"
    assert rows[-1].result == "failure", rows[-1].result


# ── 규약 오류는 500 이 아니다 (P4 · B-3) ─────────────────────────────────────
#
# `ProtocolError` 는 AppError 가 아니다. 웹 쪽에서 그것을 던지는 자리는 요청을 싸는 순간
# (`encode_request` — 인증서처럼 큰 값이 상한을 넘을 때)과 헬퍼의 답을 푸는 순간
# (`decode_response` — 답이 우리 규약이 아닐 때) 둘이고, 둘 다 `SysopsClient.call` 이 잡아
# 「도우미를 못 썼다」는 답으로 접는다. 여기서는 가짜 도우미가 아니라 **진짜 클라이언트**를
# 지나게 해서 그 접기가 실제 요청 경로에 있다는 것을 본다(`tests/unit/test_domain_exceptions_are_handled.py`
# 의 분류가 이 두 시험을 근거로 댄다).


class _GarbledSocket:
    """연결은 되는데 규약이 아닌 한 줄을 돌려주는 도우미."""

    def __init__(self, *_args):
        self._sent = False

    def settimeout(self, _seconds):
        pass

    def connect(self, _path):
        pass

    def sendall(self, _payload):
        pass

    def recv(self, _size):
        if self._sent:
            return b""
        self._sent = True
        return b"<html>not the protocol</html>\n"

    def close(self):
        pass


def _real_client(client, monkeypatch, *, socket_module=None):
    """앱에 가짜를 꽂지 않는다 — 라우터가 기본 `SysopsClient()` 를 만든다."""
    import app.sysops.client as client_mod

    client.app.state.sysops_client = None
    # Windows 개발 머신에는 AF_UNIX 가 없어 규약까지 가기 전에 「이 운영체제에서는 …」로 끝난다.
    monkeypatch.setattr(client_mod, "_AF_UNIX", object())
    if socket_module is not None:
        monkeypatch.setattr(client_mod, "socket", socket_module)


def test_an_oversized_request_is_a_failed_reply_not_a_500(client, login_as, monkeypatch):
    from app.sysops.protocol import MAX_MESSAGE_BYTES

    _real_client(client, monkeypatch)
    csrf = login_as("system_admin")
    r = client.post(
        "/api/admin/system/cert.install",
        json={"params": {"certificate": "A" * (MAX_MESSAGE_BYTES + 1), "private_key": "K"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False and body["available"] is False, body
    assert body["detail"] == "요청이 너무 큽니다.", body["detail"]


def test_a_garbled_helper_reply_is_a_failed_reply_not_a_500(client, login_as, monkeypatch):
    import socket as real_socket
    from types import SimpleNamespace

    fake_socket = SimpleNamespace(
        socket=_GarbledSocket, SOCK_STREAM=real_socket.SOCK_STREAM, timeout=real_socket.timeout,
    )
    _real_client(client, monkeypatch, socket_module=fake_socket)
    csrf = login_as("system_admin")
    r = client.post(
        "/api/admin/system/timezone.set",
        json={"params": {"timezone": "Asia/Seoul"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False and body["available"] is False, body
    assert body["detail"] == "응답을 해석할 수 없습니다.", body["detail"]
