"""시스템 정보 조회 · 서비스 제어 · 인증서 교체 액션 (§S).

## 인증서 교체에서 개인키를 다루는 규칙

개인키는 **소켓을 지나 헬퍼까지만** 간다. 감사 로그에도, 응답에도, 오류 메시지에도 넣지 않는다.
그래서 이 파일의 어떤 `detail` 문자열도 `params` 값을 끼워 넣지 않는다 —
검증 실패를 알릴 때조차 "형식이 올바르지 않습니다" 라고만 한다. 값을 보여 주면 그 값이
로그·화면·오류 리포트로 흩어진다.

`openssl` 로 **키와 인증서가 실제로 한 쌍인지** 확인한 뒤에만 교체한다. 이걸 안 하면 nginx 가
다음 재시작에 뜨지 않고, 그때는 이미 관리 화면에도 못 들어간다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import PurePosixPath

from app.sysops import validate as v
from app.sysops.actions import Action, ActionOutcome, register
from app.sysops.runner import Runner

SYSTEMCTL = "/usr/bin/systemctl"
HOSTNAMECTL = "/usr/bin/hostnamectl"
TIMEDATECTL = "/usr/bin/timedatectl"
OPENSSL = "/usr/bin/openssl"
NGINX = "/usr/sbin/nginx"
DF = "/usr/bin/df"

# 제어할 수 있는 유닛의 전부. 이름을 자유롭게 받으면 헬퍼가 **임의 서비스 제어기**가 된다.
MANAGED_UNITS = (
    "clovirone-web-assistant.service",
    "clovirone-web-worker.service",
    "nginx.service",
    "systemd-timesyncd.service",
    "systemd-resolved.service",
)
SELF_UNIT = "clovirone-web-assistant.service"
CONTROL_VERBS = ("start", "stop", "restart", "reload")

# SYS-01: 예전엔 이 넷이 `/etc/ssl/clovirone/…` 로 하드코딩돼 있었는데, nginx 는
# install-clovirone-web-assistant.sh 가 만든 `$ETC_DIR/tls/$DNS_NAME.{crt,key}` 만 읽는다
# (deploy/nginx/clovirone-web-assistant.conf, `/etc/ssl/clovirone/` 는 설치 스크립트가
# 디렉터리만 만들고 아무도 안 읽는다). 그 결과 이 액션은 openssl 쌍 검증 → nginx -t →
# reload 까지 전부 성공하고 새 인증서의 subject·만료일을 보여 주면서도, 실제로 nginx 가
# 서빙하는 인증서는 그대로였다 — **조용한 무동작**.
#
# `settings.tls_cert_path`(env `TLS_CERT_PATH`) 가 이미 그 정답을 들고 있다
# (`app/health/service.py::cert_days_remaining`, `app/setup/probes.py::probe_tls` 가 그것을
# 읽는다) — 다만 이 파일은 웹 프로세스가 아니라 **특권 헬퍼**(별도 프로세스, `app/sysops/
# helper.py`)에서 돌아서 FastAPI `Settings` 객체가 없다. 대신 헬퍼 유닛에 같은
# `web.env` 를 `EnvironmentFile=` 로 얹어(`deploy/systemd/clovirone-privhelper.service`)
# 같은 값을 **환경변수로** 받는다 — 세 소비자가 결국 같은 한 값을 읽는다(D-22).
#
# 키·스테이징 경로는 nginx 템플릿과 같은 관례(같은 디렉터리, 같은 basename, 확장자만
# `.crt`/`.key`)로 유도한다 — 인증서 자리 옆에 개인키를 두는 것이 설치 스크립트가 이미
# 하는 일이다. `TLS_CERT_PATH` 가 없는 설치(dev/test, 또는 앞단 프록시가 TLS 를 끊는 구성)는
# 예전 기본 경로로 남겨 둔다 — 그 경우 이 액션이 실제로 쓰이는 서버가 없으므로 무해하다.
def _resolve_tls_paths_for(configured: str) -> tuple[str, str, str, str]:
    configured = (configured or "").strip()
    if not configured:
        return (
            "/etc/ssl/clovirone/server.crt", "/etc/ssl/clovirone/server.key",
            "/etc/ssl/clovirone/.staged.crt", "/etc/ssl/clovirone/.staged.key",
        )
    cert = PurePosixPath(configured)
    tls_dir = cert.parent
    return (str(cert), str(tls_dir / (cert.stem + ".key")),
            str(tls_dir / ".staged.crt"), str(tls_dir / ".staged.key"))


CERT_PATH, KEY_PATH, CERT_STAGE, KEY_STAGE = _resolve_tls_paths_for(os.environ.get("TLS_CERT_PATH", ""))


def _value(runner: Runner, argv: list[str]) -> str:
    got = runner.run(argv)
    return got.stdout.strip() if got.ok else ""


# ---------------------------------------------------------------- 시스템 정보


def _perform_info(runner: Runner, _params: dict) -> ActionOutcome:
    """읽기 전용. 하나가 없어도 나머지는 준다 — 전부 아니면 아무것도가 되면 진단에 못 쓴다."""
    units = {}
    for unit in MANAGED_UNITS:
        got = runner.run([SYSTEMCTL, "is-active", unit])
        # `is-active` 는 inactive 일 때 0 이 아닌 값을 준다. 그건 오류가 아니라 **답**이다.
        units[unit] = (got.stdout or got.stderr).strip() or "unknown"

    disk = runner.run([DF, "-h", "/"])
    data = {
        "hostname": _value(runner, [HOSTNAMECTL, "show", "-p", "StaticHostname", "--value"]),
        "timezone": _value(runner, [TIMEDATECTL, "show", "-p", "Timezone", "--value"]),
        "ntp_synchronized": _value(runner, [TIMEDATECTL, "show", "-p", "NTPSynchronized", "--value"]),
        "units": units,
        "disk_root": disk.stdout.strip() if disk.ok else None,
    }
    # 못 읽은 항목은 빈 문자열로 남는다. 화면이 "확인하지 못했습니다" 라고 말하도록
    # 어떤 항목이 비었는지 함께 알린다 (§불변 6: 없는 것을 있는 척하지 않는다).
    data["unavailable"] = sorted(k for k, val in data.items() if val == "")
    return ActionOutcome(ok=True, detail="시스템 정보를 읽었습니다.", data=data)


register(Action(
    name="system.info",
    summary="시스템 정보 조회",
    mutating=False,
    normalize=lambda _p: {},
    perform=_perform_info,
))


# ---------------------------------------------------------------- 서비스 제어


def _normalize_service(params: Mapping) -> dict:
    unit = params.get("unit")
    if unit not in MANAGED_UNITS:
        raise v.InvalidSysopsValueError(f"관리 대상 서비스가 아닙니다: {str(unit)[:64]}")
    verb = params.get("verb")
    if verb not in CONTROL_VERBS:
        raise v.InvalidSysopsValueError(f"허용되지 않은 동작입니다: {str(verb)[:32]}")
    if unit == SELF_UNIT and verb == "stop":
        # 멈추면 이 콘솔로는 다시 켤 수 없다. 서버에 직접 접속해야 한다.
        raise v.InvalidSysopsValueError(
            "이 화면을 제공하는 서비스는 여기서 중지할 수 없습니다. 서버에서 직접 실행하세요."
        )
    return {"unit": unit, "verb": verb}


def _perform_service(runner: Runner, params: dict) -> ActionOutcome:
    unit, verb = params["unit"], params["verb"]
    got = runner.run([SYSTEMCTL, verb, unit], timeout=60)
    if not got.ok:
        return ActionOutcome(ok=False, detail=f"{unit} {verb} 에 실패했습니다: {got.stderr.strip()}")

    if verb == "stop":
        state = runner.run([SYSTEMCTL, "is-active", unit]).stdout.strip()
        ok = state != "active"
        return ActionOutcome(
            ok=ok,
            detail=f"{unit} 를 중지했습니다." if ok else f"{unit} 가 여전히 실행 중입니다.",
            changed=ok, data={"unit": unit, "state": state},
        )

    state = runner.run([SYSTEMCTL, "is-active", unit]).stdout.strip()
    if state != "active":
        # 🔴 여기가 중요하다. `systemctl restart` 는 **유닛을 띄우라고 지시하는 데 성공**하면
        # 0 을 준다. 프로세스가 곧바로 죽어도 0 일 수 있다. 상태를 다시 읽지 않으면
        # "재시작했습니다" 라고 말해 놓고 서비스가 꺼져 있는 상태가 된다.
        return ActionOutcome(
            ok=False,
            detail=f"{unit} 가 다시 살아나지 않았습니다(현재 {state or '알 수 없음'}).",
            data={"unit": unit, "state": state},
        )
    return ActionOutcome(
        ok=True, detail=f"{unit} 를 {verb} 했습니다.", changed=True,
        data={"unit": unit, "state": state},
    )


register(Action(
    name="service.control",
    summary="서비스 시작/중지/재시작",
    mutating=True,
    normalize=_normalize_service,
    perform=_perform_service,
))


# ---------------------------------------------------------------- 인증서


def _pem(value: object, *, kind: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise v.InvalidSysopsValueError(f"{kind} 내용이 비어 있습니다.")
    text = value.strip() + "\n"
    if len(text) > 64 * 1024:
        raise v.InvalidSysopsValueError(f"{kind} 가 너무 큽니다.")
    if "-----BEGIN" not in text or "-----END" not in text:
        # 값 자체는 절대 되돌려 주지 않는다 (개인키일 수 있다).
        raise v.InvalidSysopsValueError(f"{kind} 가 PEM 형식이 아닙니다.")
    return text


def _normalize_cert(params: Mapping) -> dict:
    return {
        "certificate": _pem(params.get("certificate"), kind="인증서"),
        "private_key": _pem(params.get("private_key"), kind="개인키"),
    }


def _modulus(runner: Runner, argv: list[str]) -> str:
    got = runner.run(argv)
    return got.stdout.strip() if got.ok else ""


def _perform_cert(runner: Runner, params: dict) -> ActionOutcome:
    """검사를 **전부 통과한 뒤에야** 실제 경로로 옮긴다.

    순서가 핵심이다. 실제 경로에 먼저 쓰고 검사하면, 검사에 실패한 짧은 순간에 nginx 가
    재시작될 경우 뜨지 않는다. 임시 이름으로 쓰고 검사한 뒤 옮기면 그 창이 없다.
    """
    runner.write_text(CERT_STAGE, params["certificate"], mode=0o644)
    runner.write_text(KEY_STAGE, params["private_key"], mode=0o600)

    def _cleanup() -> None:
        runner.remove(CERT_STAGE)
        runner.remove(KEY_STAGE)

    cert_ok = runner.run([OPENSSL, "x509", "-noout", "-in", CERT_STAGE])
    if not cert_ok.ok:
        _cleanup()
        return ActionOutcome(ok=False, detail="인증서를 읽을 수 없습니다(형식 오류).")

    key_ok = runner.run([OPENSSL, "pkey", "-noout", "-in", KEY_STAGE])
    if not key_ok.ok:
        _cleanup()
        return ActionOutcome(ok=False, detail="개인키를 읽을 수 없습니다(형식 오류이거나 암호가 걸려 있습니다).")

    cert_pub = _modulus(runner, [OPENSSL, "x509", "-noout", "-pubkey", "-in", CERT_STAGE])
    key_pub = _modulus(runner, [OPENSSL, "pkey", "-pubout", "-in", KEY_STAGE])
    if not cert_pub or not key_pub or cert_pub != key_pub:
        _cleanup()
        return ActionOutcome(ok=False, detail="인증서와 개인키가 한 쌍이 아닙니다.")

    runner.write_text(CERT_PATH, params["certificate"], mode=0o644)
    runner.write_text(KEY_PATH, params["private_key"], mode=0o600)
    _cleanup()

    checked = runner.run([NGINX, "-t"], timeout=30)
    if not checked.ok:
        # 엔진이 백업본으로 되돌린다. 되돌린 뒤 다시 검사해야 "되돌렸다" 가 사실이 된다.
        return ActionOutcome(ok=False, detail=f"nginx 설정 검사에 실패했습니다: {checked.stderr.strip()[:300]}")

    reloaded = runner.run([SYSTEMCTL, "reload", "nginx.service"], timeout=30)
    if not reloaded.ok:
        return ActionOutcome(ok=False, detail=f"nginx 를 다시 읽지 못했습니다: {reloaded.stderr.strip()[:300]}")

    subject = _value(runner, [OPENSSL, "x509", "-noout", "-subject", "-in", CERT_PATH])
    not_after = _value(runner, [OPENSSL, "x509", "-noout", "-enddate", "-in", CERT_PATH])
    return ActionOutcome(
        ok=True, detail="인증서를 교체하고 nginx 를 다시 읽었습니다.", changed=True,
        data={"subject": subject, "not_after": not_after},
    )


register(Action(
    name="cert.install",
    summary="TLS 인증서 교체",
    mutating=True,
    normalize=_normalize_cert,
    perform=_perform_cert,
    touches=lambda _p: (CERT_PATH, KEY_PATH),
))
