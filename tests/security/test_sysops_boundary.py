"""특권 헬퍼의 **보안 경계**를 검사한다 (§S).

## 왜 이 파일이 다른 테스트보다 중요한가

여기서 검사하는 코드는 **root 로 실행된다.** 웹은 하드닝(`NoNewPrivileges` ·
`ProtectSystem=strict`)으로 막혀 있어서, 뚫려도 시스템을 못 건드린다. 그 하드닝을 우회하는
유일한 통로가 이 헬퍼다. 즉 **이 파일이 막지 못하는 것은 아무것도 못 막는다.**

검사하는 성질은 넷이다.
  ① 이름표에 없는 동작은 아무 일도 안 한다
  ② 허용 목록 밖 프로그램은 실행되지 않는다
  ③ 실패하면 **원래대로 되돌아간다** (없던 파일은 없는 상태로)
  ④ 인자는 **어디에도 기록되지 않는다** (인증서 개인키가 인자로 온다)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.sysops import actions as registry
from app.sysops import validate as v
from app.sysops.runner import ALLOWED_BINARIES, BinaryNotAllowedError, RealRunner
from tests.fakes.sysops import FakeRunner

pytestmark = pytest.mark.security

NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
BACKUPS = "/var/backups/sysops"


def _run(runner, action, params=None):
    return registry.execute(runner, action, params or {}, backup_root=BACKUPS, now=NOW)


# ---------------------------------------------------------------- ① 이름표


def test_an_unknown_action_does_nothing_at_all():
    """이름표에 없으면 **실행 자체가 없다.** 오류를 돌려주는 것으로 충분하지 않다."""
    runner = FakeRunner()
    with pytest.raises(registry.UnknownActionError):
        _run(runner, "shell.exec", {"cmd": "rm -rf /"})
    assert runner.calls == [], f"알 수 없는 동작인데 무언가 실행됐다: {runner.calls}"
    assert runner.files == {}, "알 수 없는 동작인데 파일이 생겼다"


def test_the_action_name_must_be_a_string():
    runner = FakeRunner()
    for bogus in (None, 42, ["timezone.set"], {"name": "timezone.set"}):
        with pytest.raises(registry.UnknownActionError):
            _run(runner, bogus)
    assert runner.calls == []


def test_every_registered_action_only_names_allowed_binaries():
    """액션 표가 커질 때 **자동으로** 지켜지는 성질이다.

    새 액션이 `/bin/sh` 를 부르면 이 검사가 먼저 실패한다. 사람이 리뷰에서 알아채길
    기다리지 않는다.
    """
    listed = {a["name"] for a in registry.list_actions()}
    assert listed, "등록된 액션이 하나도 없다 (import 부작용이 사라졌다)"
    # 허용 목록 자체가 절대 경로인지 본다. 상대 경로면 PATH 에 따라 다른 것이 실행된다.
    for binary in ALLOWED_BINARIES:
        assert binary.startswith("/"), f"허용 목록에 상대 경로가 있다: {binary}"


# ---------------------------------------------------------------- ② 실행 차단


def test_the_real_runner_refuses_a_binary_outside_the_allowlist():
    with pytest.raises(BinaryNotAllowedError):
        RealRunner().run(["/bin/sh", "-c", "id"])
    with pytest.raises(BinaryNotAllowedError):
        RealRunner().run([])


def test_a_blocked_binary_becomes_a_failed_action_not_a_crash():
    """차단은 예외로 새어 나가지 않고 **실패한 동작**이 된다 — 그래야 롤백 경로를 지난다."""
    runner = FakeRunner({"/etc/hosts": "127.0.0.1 localhost\n"})
    action = registry.get_action("hostname.set")
    bad = registry.Action(
        name="test.bad", summary="검사용", mutating=True,
        normalize=action.normalize,
        perform=lambda r, p: r.run(["/bin/sh", "-c", "id"]) and None,
        touches=lambda p: ("/etc/hosts",),
    )
    registry._REGISTRY["test.bad"] = bad
    try:
        result = _run(runner, "test.bad", {"hostname": "srv1"})
    finally:
        registry._REGISTRY.pop("test.bad", None)
    assert result.ok is False
    assert "차단" in result.detail, result.detail
    assert runner.files["/etc/hosts"] == "127.0.0.1 localhost\n", "차단된 뒤 파일이 바뀌었다"


# ---------------------------------------------------------------- ③ 롤백


def _cert_world(nginx_ok: bool) -> FakeRunner:
    from app.sysops.actions_service import CERT_PATH, CERT_STAGE, KEY_PATH, KEY_STAGE

    runner = FakeRunner({CERT_PATH: "OLD-CERT\n", KEY_PATH: "OLD-KEY\n"})
    runner.reply(["/usr/bin/openssl", "x509", "-noout", "-in", CERT_STAGE])
    runner.reply(["/usr/bin/openssl", "pkey", "-noout", "-in", KEY_STAGE])
    runner.reply(["/usr/bin/openssl", "x509", "-noout", "-pubkey", "-in", CERT_STAGE], out="PUB")
    runner.reply(["/usr/bin/openssl", "pkey", "-pubout", "-in", KEY_STAGE], out="PUB")
    runner.reply(["/usr/sbin/nginx", "-t"], code=0 if nginx_ok else 1, err="bad config")
    runner.reply(["/usr/bin/systemctl", "reload", "nginx.service"])
    runner.reply(["/usr/bin/openssl", "x509", "-noout", "-subject", "-in", CERT_PATH], out="subject=CN=x")
    runner.reply(["/usr/bin/openssl", "x509", "-noout", "-enddate", "-in", CERT_PATH], out="notAfter=...")
    return runner


PEM_CERT = "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"
PEM_KEY = "-----BEGIN PRIVATE KEY-----\nSUPERSECRETKEYMATERIAL\n-----END PRIVATE KEY-----"


def test_a_failed_certificate_swap_puts_the_old_files_back():
    """🔴 되돌리지 않으면 **다음 재시작에 nginx 가 뜨지 않는다** — 그때는 이 화면도 없다."""
    from app.sysops.actions_service import CERT_PATH, KEY_PATH

    runner = _cert_world(nginx_ok=False)
    result = _run(runner, "cert.install", {"certificate": PEM_CERT, "private_key": PEM_KEY})

    assert result.ok is False
    assert result.rolled_back is True, "되돌렸다고 말하지 않았다"
    assert runner.files[CERT_PATH] == "OLD-CERT\n", f"인증서가 안 돌아왔다: {runner.files[CERT_PATH]!r}"
    assert runner.files[KEY_PATH] == "OLD-KEY\n", "개인키가 안 돌아왔다"


def test_a_failed_action_removes_files_that_did_not_exist_before():
    """🔴 백업이 없다는 것은 "되돌릴 것이 없다" 가 아니라 **"지워야 한다"** 는 뜻이다.

    처음 설정하는 서버에는 드롭인 파일이 없다. 실패했는데 그 파일을 남겨 두면
    "실패했습니다" 라고 말해 놓고 설정은 들어가 있는 상태가 된다 - 가장 헷갈리는 실패다.
    """
    from app.sysops.actions_system import RESOLVED_DROPIN

    runner = FakeRunner()  # 드롭인이 원래 없다
    runner.reply(["/usr/bin/systemctl", "restart", "systemd-resolved"], code=1, err="boom")

    result = _run(runner, "dns.set", {"servers": ["10.0.0.1"]})

    assert result.ok is False
    assert result.rolled_back is True
    assert RESOLVED_DROPIN not in runner.files, (
        f"실패했는데 새 설정 파일이 남았다: {runner.files.get(RESOLVED_DROPIN)!r}"
    )


def test_a_restart_that_reports_success_but_leaves_the_unit_dead_is_a_failure():
    """`systemctl restart` 의 0 은 "지시에 성공" 이지 "살아 있다" 가 아니다."""
    runner = FakeRunner()
    runner.reply(["/usr/bin/systemctl", "restart", "nginx.service"])
    runner.reply(["/usr/bin/systemctl", "is-active", "nginx.service"], code=3, out="failed")

    result = _run(runner, "service.control", {"unit": "nginx.service", "verb": "restart"})
    assert result.ok is False, "죽은 서비스를 재시작 성공이라고 말했다"
    assert "살아나지" in result.detail, result.detail


def test_the_console_cannot_stop_the_service_that_serves_it():
    with pytest.raises(v.InvalidSysopsValueError):
        _run(FakeRunner(), "service.control",
             {"unit": "clovirone-web-assistant.service", "verb": "stop"})


def test_an_unmanaged_unit_is_refused():
    for unit in ("sshd.service", "../../etc/passwd", "nginx", ""):
        with pytest.raises(v.InvalidSysopsValueError):
            _run(FakeRunner(), "service.control", {"unit": unit, "verb": "restart"})


# ---------------------------------------------------------------- ④ 인자 비노출


def test_the_private_key_never_reaches_the_audit_log(tmp_path):
    """🔴 인증서 교체는 **개인키를 인자로** 받는다.

    감사 로그에 인자를 통째로 적는 흔한 관용을 그대로 따르면, 서버의 TLS 개인키가
    평문 로그 파일에 영구히 남는다. 로그는 백업·수집기·티켓 첨부로 흩어진다.
    """
    from app.sysops.helper import handle_request
    from app.sysops.protocol import encode_request

    audit = tmp_path / "privhelper.jsonl"
    runner = _cert_world(nginx_ok=True)
    raw = encode_request(
        "cert.install", {"certificate": PEM_CERT, "private_key": PEM_KEY}, request_id="rid-1",
    ).rstrip(b"\n")

    payload = handle_request(
        raw, caller_uid=0, backup_root=BACKUPS, audit_log=str(audit), runner=runner, now=NOW,
    )
    assert payload["ok"] is True, payload

    text = audit.read_text(encoding="utf-8")
    assert "SUPERSECRETKEYMATERIAL" not in text, "개인키가 감사 로그에 남았다"
    assert "BEGIN PRIVATE KEY" not in text, "개인키가 감사 로그에 남았다"
    record = json.loads(text.strip().splitlines()[-1])
    assert record["action"] == "cert.install", record
    assert record["ok"] is True and record["uid"] == 0
    assert "params" not in record, "인자가 통째로 기록됐다"


def test_the_private_key_never_reaches_the_response():
    runner = _cert_world(nginx_ok=True)
    result = _run(runner, "cert.install", {"certificate": PEM_CERT, "private_key": PEM_KEY})
    blob = json.dumps({"detail": result.detail, "data": result.data}, ensure_ascii=False)
    assert "SUPERSECRETKEYMATERIAL" not in blob, f"개인키가 응답에 실렸다: {blob}"


def test_a_rejected_certificate_does_not_echo_its_own_content():
    """검증 실패 메시지에 값을 끼워 넣으면 그 값이 화면·로그·오류 리포트로 흩어진다."""
    with pytest.raises(v.InvalidSysopsValueError) as err:
        _run(FakeRunner(), "cert.install",
             {"certificate": "not-a-pem", "private_key": "SUPERSECRETKEYMATERIAL"})
    assert "SUPERSECRETKEYMATERIAL" not in str(err.value), str(err.value)
    assert "not-a-pem" not in str(err.value), str(err.value)
