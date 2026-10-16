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
from pathlib import Path, PurePosixPath

from app.core import product
from app.sysops import domain_files
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
# 대화형 워커와 색인 레인도 여기 있다(M3) — 대표 도메인을 바꾸면 `APP_BASE_URL` 을 읽는 모든 뒷단 유닛을 다시 시작해야 하고,
# 서비스 화면이 그 둘의 상태도 보여 준다.
MANAGED_UNITS = (
    product.WEB_UNIT,
    product.WORKER_UNIT,
    product.WORKER_CONVERSATIONAL_UNIT,
    product.SCHEDULER_UNIT,
    product.INDEX_UNIT,
    "nginx.service",
    "systemd-timesyncd.service",
    "systemd-resolved.service",
)
SELF_UNIT = product.WEB_UNIT
CONTROL_VERBS = ("start", "stop", "restart", "reload")
# 결과 문장에 쓰는 동작 이름 — systemctl 의 영어 동사를 그대로 넣으면 「restart 했습니다」가 화면에 섰다(r23 문구 대장).
CONTROL_VERB_KO = {"start": "시작", "stop": "중지", "restart": "다시 시작", "reload": "설정 다시 읽기"}

# SYS-01: 예전엔 이 넷이 `/etc/ssl/clovirone/…` 로 하드코딩돼 있었는데, nginx 는
# deploy/install.sh 가 만든 `$ETC_DIR/tls/$DNS_NAME.{crt,key}` 만 읽는다
# (deploy/nginx/clovirassist.conf, `/etc/ssl/clovirassist/` 는 설치 스크립트가
# 디렉터리만 만들고 아무도 안 읽는다). 그 결과 이 액션은 openssl 쌍 검증 → nginx -t →
# reload 까지 전부 성공하고 새 인증서의 subject·만료일을 보여 주면서도, 실제로 nginx 가
# 서빙하는 인증서는 그대로였다 — **조용한 무동작**.
#
# `settings.tls_cert_path`(env `TLS_CERT_PATH`) 가 이미 그 정답을 들고 있다
# (`app/health/service.py::cert_days_remaining`, `app/setup/probes.py::probe_tls` 가 그것을
# 읽는다) — 다만 이 파일은 웹 프로세스가 아니라 **특권 헬퍼**(별도 프로세스, `app/sysops/
# helper.py`)에서 돌아서 FastAPI `Settings` 객체가 없다. 대신 헬퍼 유닛에 같은
# 설정 파일을 `EnvironmentFile=` 로 얹어(`deploy/systemd/clovirassist-privhelper.service`)
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
            f"{product.SSL_FALLBACK_DIR}/server.crt", f"{product.SSL_FALLBACK_DIR}/server.key",
            f"{product.SSL_FALLBACK_DIR}/.staged.crt", f"{product.SSL_FALLBACK_DIR}/.staged.key",
        )
    cert = PurePosixPath(configured)
    tls_dir = cert.parent
    return (str(cert), str(tls_dir / (cert.stem + ".key")),
            str(tls_dir / ".staged.crt"), str(tls_dir / ".staged.key"))


# 이 프로세스가 **시작될 때** 본 값. 아래 `tls_paths()` 의 마지막 폴백이자, env 파일이 없는 개발 · 시험 환경의 값이다.
CERT_PATH, KEY_PATH, CERT_STAGE, KEY_STAGE = _resolve_tls_paths_for(os.environ.get("TLS_CERT_PATH", ""))


def _read_env_file() -> str | None:
    """env 파일 글. 헬퍼는 root 라 읽을 수 있고, 없으면(개발 머신) None. 시험은 이 함수를 바꿔 끼운다(`tests/unit/test_sysops_tls_paths.py`)."""
    try:
        return Path(product.ENV_FILE).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def configured_cert_path(env_text: str | None) -> str:
    """지금 env 파일이 말하는 `TLS_CERT_PATH`. 없으면 프로세스 환경(유닛의 `EnvironmentFile=` 이 준 값)."""
    return (domain_files.env_get(env_text, "TLS_CERT_PATH") if env_text else None) or os.environ.get("TLS_CERT_PATH", "")


def tls_paths(env_text: str | None) -> tuple[str, str, str, str]:
    """**호출마다** env 파일을 다시 본다(M3). `domain.apply` 가 `TLS_CERT_PATH` 를 새 이름으로 바꾸면 헬퍼를 다시 띄우지 않아도
    다음 `cert.install` 이 새 경로에 쓴다 — import 시점 상수만 보면 옛 이름의 파일을 갈아 끼우고 「교체했다」고 말한다."""
    return _resolve_tls_paths_for(configured_cert_path(env_text))


def _value(runner: Runner, argv: list[str]) -> str:
    got = runner.run(argv)
    return got.stdout.strip() if got.ok else ""


# ---------------------------------------------------------------- 시스템 정보


# 이 콘솔이 쓴 드롭인 파일 경로. `actions_system.py` 가 **쓰는** 자리와 같아야 한다 —
# 두 파일이 각자 경로를 적으면 한쪽만 바뀌는 날 조회가 조용히 빈 값을 준다.
RESOLVED_DROPIN = product.RESOLVED_DROPIN
PROXY_DROPIN_UNITS = (product.WEB_UNIT, product.WORKER_UNIT, product.SCHEDULER_UNIT)


def _proxy_dropin_path(unit: str) -> str:
    return f"/etc/systemd/system/{unit}.d/{product.PROXY_DROPIN_NAME}"


def _read_dns(runner: Runner) -> dict:
    """이 콘솔이 지정한 DNS. **OS 가 실제로 쓰는 값이 아니라 우리가 쓴 값**이다.

    둘은 다를 수 있다(DHCP·다른 드롭인). 화면이 그 차이를 말할 수 있게 `source` 를 함께
    준다 — "지정 안 함" 과 "읽지 못함" 도 서로 다른 사실이라 구분한다.
    """
    out = {"configured": False, "servers": [], "search": None, "source": "unset"}
    try:
        if not runner.exists(RESOLVED_DROPIN):
            return out
        text = runner.read_text(RESOLVED_DROPIN) or ""
    except Exception:  # 조회가 화면 전체를 죽이지 않는다 — 나머지 정보는 그대로 준다.
        out["source"] = "unreadable"
        return out
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("DNS="):
            out["servers"] = [x for x in line[4:].split() if x]
        elif line.startswith("Domains="):
            out["search"] = line[len("Domains="):].strip() or None
    out["configured"] = bool(out["servers"])
    out["source"] = "console" if out["configured"] else "unset"
    return out


def _read_proxy(runner: Runner) -> dict:
    """이 콘솔이 지정한 아웃바운드 프록시. `_read_dns` 와 같은 규칙이다."""
    out = {"configured": False, "url": None, "no_proxy": None, "source": "unset"}
    for unit in PROXY_DROPIN_UNITS:
        path = _proxy_dropin_path(unit)
        try:
            if not runner.exists(path):
                continue
            text = runner.read_text(path) or ""
        except Exception:
            out["source"] = "unreadable"
            return out
        for line in text.splitlines():
            line = line.strip()
            # `Environment="HTTPS_PROXY=http://..."` 모양에서 값만 뽑는다.
            if "HTTPS_PROXY=" in line or "HTTP_PROXY=" in line:
                out["url"] = line.split("PROXY=", 1)[1].strip().strip('"')
            elif "NO_PROXY=" in line:
                out["no_proxy"] = line.split("NO_PROXY=", 1)[1].strip().strip('"')
        if out["url"]:
            out["configured"] = True
            out["source"] = "console"
            return out
    return out


MANIFEST_FILE = domain_files.MANIFEST_FILE


def _read_quietly(runner: Runner, path: str) -> str | None:
    """조회 화면용 읽기 — 못 읽으면 None 이다. 파일 하나 때문에 시스템 정보 전체가 실패로 바뀌지 않는다(`_read_dns` 와 같은 규칙)."""
    try:
        return runner.read_text(path)
    except (OSError, ValueError):
        return None


def domain_state(runner: Runner) -> dict:
    """서비스 주소의 정본(D-c) 한 벌 — env `APP_BASE_URL` · `TLS_CERT_PATH` 와 설치 매니페스트 `dns_name` · `alias_names` · `bind_ip` ·
    `upstream_proxies`. 파일 둘만 읽는다(DNS · openssl · nginx 는 `domain.preview` 의 일이다). `system.info` 가 매 화면 진입에 부르므로
    싸야 한다."""
    env_text = _read_quietly(runner, product.ENV_FILE)
    manifest = domain_files.parse_manifest(_read_quietly(runner, MANIFEST_FILE))
    app_base_url = domain_files.env_get(env_text, "APP_BASE_URL") or ""
    dns_name = str(manifest.get("dns_name") or "").strip().lower() or None
    canonical = domain_files.host_from_url(app_base_url) or dns_name
    cert_path = configured_cert_path(env_text) or (domain_files.cert_paths(product.TLS_DIR, canonical)[0] if canonical else "")
    return {
        "canonical": canonical,
        "app_base_url": app_base_url,
        "dns_name": dns_name,
        "aliases": domain_files.split_names(manifest.get("alias_names")),
        "bind_ip": str(manifest.get("bind_ip") or "").strip(),
        "upstream_proxies": domain_files.split_names(manifest.get("upstream_proxies")),
        "cert_path": cert_path,
        "env_readable": env_text is not None,
        "manifest_readable": bool(manifest),
        "_env_text": env_text,
        "_manifest": manifest,
    }


def _public_domain(state: dict) -> dict:
    return {k: val for k, val in state.items() if not k.startswith("_")}


def _perform_info(runner: Runner, _params: dict) -> ActionOutcome:
    """읽기 전용. 하나가 없어도 나머지는 준다 — 전부 아니면 아무것도가 되면 진단에 못 쓴다."""
    units = {}
    for unit in MANAGED_UNITS:
        got = runner.run([SYSTEMCTL, "is-active", unit])
        # `is-active` 는 inactive 일 때 0 이 아닌 값을 준다. 그건 오류가 아니라 **답**이다.
        units[unit] = (got.stdout or got.stderr).strip() or "unknown"

    disk = runner.run([DF, "-h", "/"])
    data = {
        # SYS-02: `hostnamectl show -p … --value` 는 systemd 255 에 없는 verb다(이 서버
        # 실측: `Unknown command verb 'show'`) - `/system` 화면이 호스트 이름을 영구히
        # "확인하지 못했습니다"로 보여준다. `hostname.set`(actions_system.py:202)은 이미
        # `status --static` 을 먼저 쓰는 폴백을 갖고 있고 그게 이 서버에서 동작한다 -
        # 같은 지식을 조회 쪽에도 적용한다. `show -p` 는 더 신버전 systemd 를 위한 폴백으로 남긴다.
        "hostname": (
            _value(runner, [HOSTNAMECTL, "status", "--static"])
            or _value(runner, [HOSTNAMECTL, "show", "-p", "StaticHostname", "--value"])
        ),
        "timezone": _value(runner, [TIMEDATECTL, "show", "-p", "Timezone", "--value"]),
        "ntp_synchronized": _value(runner, [TIMEDATECTL, "show", "-p", "NTPSynchronized", "--value"]),
        "units": units,
        "disk_root": disk.stdout.strip() if disk.ok else None,
        # UI-R42: 화면이 DNS·프록시 줄을 "서버에서만 확인할 수 있습니다"로 비워 두고 있었다 —
        # 정직했지만 답은 아니었다. 이 콘솔이 쓴 드롭인을 그대로 읽어 준다.
        "dns": _read_dns(runner),
        "proxy": _read_proxy(runner),
        # 서비스 주소(M3) — 화면의 「서비스 주소」 카드가 대표 주소 · 별칭 · 인증서 경로를 여기서 읽는다. DNS 조회는 하지 않는다.
        "domain": _public_domain(domain_state(runner)),
    }
    # 못 읽은 항목은 빈 문자열로 남는다. 화면이 "확인하지 못했습니다" 라고 말하도록
    # 어떤 항목이 비었는지 함께 알린다 (§불변 6: 없는 것을 있는 척하지 않는다).
    # dns/proxy/domain 은 dict 라 이 판정에 안 걸린다 — 그쪽은 자기 `source` 로 상태를 말한다.
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
        return ActionOutcome(ok=False, detail=f"{unit} {CONTROL_VERB_KO.get(verb, verb)}에 실패했습니다: {got.stderr.strip()}")

    if verb == "stop":
        state = runner.run([SYSTEMCTL, "is-active", unit]).stdout.strip()
        ok = state != "active"
        return ActionOutcome(
            ok=ok,
            detail=f"{unit}를 중지했습니다." if ok else f"{unit}가 여전히 실행 중입니다.",
            changed=ok, data={"unit": unit, "state": state},
        )

    state = runner.run([SYSTEMCTL, "is-active", unit]).stdout.strip()
    if state != "active":
        # 🔴 여기가 중요하다. `systemctl restart` 는 **유닛을 띄우라고 지시하는 데 성공**하면
        # 0 을 준다. 프로세스가 곧바로 죽어도 0 일 수 있다. 상태를 다시 읽지 않으면
        # "재시작했습니다" 라고 말해 놓고 서비스가 꺼져 있는 상태가 된다.
        return ActionOutcome(
            ok=False,
            detail=f"{unit}가 다시 시작되지 않았습니다(현재 {state or '알 수 없음'}).",
            data={"unit": unit, "state": state},
        )
    return ActionOutcome(
        ok=True, detail=f"{unit}를 {CONTROL_VERB_KO.get(verb, verb)}했습니다.", changed=True,
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
        raise v.InvalidSysopsValueError(f"{kind}가 너무 큽니다.")
    if "-----BEGIN" not in text or "-----END" not in text:
        # 값 자체는 절대 되돌려 주지 않는다 (개인키일 수 있다).
        raise v.InvalidSysopsValueError(f"{kind}가 PEM 형식이 아닙니다.")
    return text


def _normalize_cert(params: Mapping) -> dict:
    """경로도 여기서 **한 번** 푼다(M3, D-573). 엔진의 백업(`touches`)과 실제 쓰기(`perform`)가 같은 값을 받아야 한다 — 둘이 env 파일을
    따로 읽으면 그 사이에 바뀐 값 하나로 엉뚱한 파일을 되돌리고 진짜 대상은 깨진 채 남는다."""
    return {
        "certificate": _pem(params.get("certificate"), kind="인증서"),
        "private_key": _pem(params.get("private_key"), kind="개인키"),
        "paths": tls_paths(_read_env_file()),
    }


def _modulus(runner: Runner, argv: list[str]) -> str:
    got = runner.run(argv)
    return got.stdout.strip() if got.ok else ""


def _validate_pair(runner: Runner, certificate: str, private_key: str, *, cert_stage: str, key_stage: str) -> str | None:
    """PEM 쌍을 **임시 자리**에 쓰고 검사한다. 실패하면 임시 파일을 지우고 문구를 돌려준다(값은 싣지 않는다). 성공이면 `None` 이고
    임시 파일은 남는다 — 호출자가 SAN 을 더 보거나 실제 자리로 옮긴 뒤 지운다(`cert.install` · `domain.apply` 둘이 쓴다)."""
    runner.write_text(cert_stage, certificate, mode=0o644)
    runner.write_text(key_stage, private_key, mode=0o600)

    def _cleanup() -> None:
        runner.remove(cert_stage)
        runner.remove(key_stage)

    cert_ok = runner.run([OPENSSL, "x509", "-noout", "-in", cert_stage])
    if not cert_ok.ok:
        _cleanup()
        return "인증서를 읽을 수 없습니다(형식 오류)."

    key_ok = runner.run([OPENSSL, "pkey", "-noout", "-in", key_stage])
    if not key_ok.ok:
        _cleanup()
        return "개인키를 읽을 수 없습니다(형식 오류이거나 암호가 걸려 있습니다)."

    cert_pub = _modulus(runner, [OPENSSL, "x509", "-noout", "-pubkey", "-in", cert_stage])
    key_pub = _modulus(runner, [OPENSSL, "pkey", "-pubout", "-in", key_stage])
    if not cert_pub or not key_pub or cert_pub != key_pub:
        _cleanup()
        return "인증서와 개인키가 한 쌍이 아닙니다."
    return None


def _perform_cert(runner: Runner, params: dict) -> ActionOutcome:
    """검사를 **전부 통과한 뒤에야** 실제 경로로 옮긴다.

    순서가 핵심이다. 실제 경로에 먼저 쓰고 검사하면, 검사에 실패한 짧은 순간에 nginx 가
    재시작될 경우 뜨지 않는다. 임시 이름으로 쓰고 검사한 뒤 옮기면 그 창이 없다.
    경로는 호출 시점의 env 파일에서 푼다(`tls_paths`, `_normalize_cert` 가 한 번 푼 값) — 대표 도메인을 바꾼 뒤에도 nginx 가 실제로 읽는
    파일에 쓴다.
    """
    cert_path, key_path, cert_stage, key_stage = params["paths"]
    why = _validate_pair(runner, params["certificate"], params["private_key"], cert_stage=cert_stage, key_stage=key_stage)
    if why:
        return ActionOutcome(ok=False, detail=why)

    runner.write_text(cert_path, params["certificate"], mode=0o644)
    runner.write_text(key_path, params["private_key"], mode=0o600)
    runner.remove(cert_stage)
    runner.remove(key_stage)

    checked = runner.run([NGINX, "-t"], timeout=30)
    if not checked.ok:
        # 엔진이 백업본으로 되돌린다. 되돌린 뒤 다시 검사해야 "되돌렸다" 가 사실이 된다.
        return ActionOutcome(ok=False, detail=f"웹 서버 설정 검사에 실패했습니다: {checked.stderr.strip()[:300]}")

    reloaded = runner.run([SYSTEMCTL, "reload", "nginx.service"], timeout=30)
    if not reloaded.ok:
        return ActionOutcome(ok=False, detail=f"웹 서버가 설정을 다시 읽지 못했습니다: {reloaded.stderr.strip()[:300]}")

    subject = _value(runner, [OPENSSL, "x509", "-noout", "-subject", "-in", cert_path])
    not_after = _value(runner, [OPENSSL, "x509", "-noout", "-enddate", "-in", cert_path])
    return ActionOutcome(
        ok=True, detail="인증서를 교체하고 웹 서버가 설정을 다시 읽게 했습니다.", changed=True,
        data={"subject": subject, "not_after": not_after},
    )


def _cert_touches(params: dict) -> tuple[str, ...]:
    """엔진이 백업할 파일 — `_perform_cert` 가 쓰는 것과 **같은 값**(`_normalize_cert` 가 푼 `paths`)이다."""
    cert_path, key_path, _, _ = params["paths"]
    return (cert_path, key_path)


register(Action(
    name="cert.install",
    summary="TLS 인증서 교체",
    mutating=True,
    normalize=_normalize_cert,
    perform=_perform_cert,
    touches=_cert_touches,
))
