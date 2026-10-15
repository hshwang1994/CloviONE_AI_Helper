"""대표 서비스 주소 — 미리 확인(`domain.preview`) · 적용(`domain.apply`) · 지연 재시작(`service.restart_deferred`) (계획 M3, D-573).

## 정본과 쓰는 길 (D-c)

서비스 주소의 정본은 env 파일의 `APP_BASE_URL` · `TLS_CERT_PATH` 와 설치 매니페스트의 `dns_name` · `alias_names` · `bind_ip` 다. 쓰는
쪽은 설치기(`deploy/install.sh`)와 여기 `domain.apply` 둘뿐이다. 설정 등록부(DB)에 키를 새로 두지 않는다 — 두면 `install.sh upgrade`
의 Stage 8 이 env 를 다시 쓰는 순간 둘째 정본이 생긴다. 이 액션이 매니페스트도 함께 고치므로 다음 upgrade 가 새 이름과 별칭을
그대로 이어 받는다.

## 옛 이름은 리디렉션 없는 별칭으로 남는다 (D-d)

별칭은 같은 server 블록의 `server_name` 에 서고 인증서 SAN 에 들어간다. 옛 이름으로 들어온 사람에게 새 이름으로 보내지 않는다 —
즐겨찾기 · 검증 스크립트 · 분리 DNS 사용자가 옛 이름을 쓰고 있고, 보내도 사내 사용자는 같은 자체 서명 경고를 받는다.

## 순서와 되돌리기 (D-i)

검증 → 인증서 → vhost 쓰기 → `nginx -t` → nginx reload → env → 매니페스트 → 자체 확인 → 뒷단 유닛 재시작 → (원하면) web 지연 재시작.
- 자체 확인을 유닛 재시작보다 **먼저** 한다. 자체 확인은 nginx 와 지금 떠 있는 웹만 지나므로 유닛 재시작과 상관이 없고, 실패해서
  되돌릴 때 이미 새 env 로 다시 뜬 유닛이 없어야 되돌림이 깨끗하다.
- 백업과 파일 복원은 엔진(`actions.execute`)이 `touches` 로 한다. 다만 엔진은 파일만 돌려놓고 nginx 를 다시 읽히지 않는다 — 그래서
  vhost 를 쓴 뒤 실패하면 이 액션이 그 자리에서 옛 글을 다시 쓰고 `nginx -t` → reload 를 한 번 더 한다(`_revert_and_reload`,
  `actions_system._revert_and_restart` 와 같은 모양). 엔진은 그 뒤에 같은 내용을 다시 쓴다.
- web 은 지금 이 요청을 처리하는 프로세스라 동기로 재시작하면 자기 응답을 죽인다. `systemd-run --on-active=3` 으로 3초 뒤에 맡긴다.
- 뒷단 유닛(배치 · 대화형 · 예약 · 색인)은 동기로 재시작하되 하나에 25초를 넘기지 않는다 — 배치 작업을 마무리하는 중인 유닛은 그
  뒤에도 systemd 가 마저 재시작한다. 이 단계의 실패는 주소 바꾸기를 되돌리지 않는다(주소는 이미 자체 확인을 지났다). 경고로 알린다.
  꺼져 있던 유닛은 켜지 않는다(대화형 레인은 설정에 따라 꺼져 있는 것이 정상이다, D-118).

## 비밀

`provided` 인증서의 개인키는 `params` 로만 온다. `detail` · `data` · 단계 문장 어디에도 싣지 않는다(`actions_service` 머리말과 같은
규칙). 되돌리기용으로 읽어 둔 옛 파일 글도 메모리에만 있다.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Mapping

from app.core import product
from app.core.text import object_particle, subject_particle, topic_particle
from app.mail import relay_files
from app.sysops import domain_files as df
from app.sysops import validate as v
from app.sysops.actions import Action, ActionOutcome, register
from app.sysops.actions_service import MANAGED_UNITS, _pem, _validate_pair, domain_state
from app.sysops.runner import Runner

logger = logging.getLogger("app.sysops.actions")

OPENSSL = "/usr/bin/openssl"
NGINX = "/usr/sbin/nginx"
SYSTEMCTL = "/usr/bin/systemctl"
SYSTEMD_RUN = "/usr/bin/systemd-run"

CERT_STRATEGIES = ("self_signed", "keep", "provided")
MAX_RESOLVERS = 3
# 시간 상한 — 웹이 이 동작을 170초 기다린다(`router.DOMAIN_APPLY_TIMEOUT`). 최악(유닛 넷이 모두 상한까지 · 자체 확인 세 번이 모두
# 연결 시간 초과)이 25 × 4 + 5 × 3 × 3 + 그 밖 몇 초 ≈ 150초라 그 안이다.
UNIT_RESTART_TIMEOUT = 25
PROBE_TIMEOUT = 5.0
WEB_RESTART_DELAY = 3
DEFERRED_DELAY = (2, 30)
SELF_CHECK_ATTEMPTS = 3
# 로그인 화면의 폼 표지. 제품 이름은 브랜딩 설정으로 바뀔 수 있어 표지로 쓰지 않는다 — 이 표지는 제품 틀(`login.html`)이 정한다.
LOGIN_MARKER = 'id="login-form"'
# 다시 시작하는 뒷단 유닛 — `APP_BASE_URL` 을 프로세스 시작 때 읽는 쪽 전부(메일 링크 · AI 링크 허용 · 예약 작업).
BACKEND_UNITS = (product.WORKER_UNIT, product.WORKER_CONVERSATIONAL_UNIT, product.SCHEDULER_UNIT, product.INDEX_UNIT)
UNIT_LABELS = {
    product.WEB_UNIT: "웹 서버",
    product.WORKER_UNIT: "백그라운드 작업",
    product.WORKER_CONVERSATIONAL_UNIT: "대화형 작업",
    product.SCHEDULER_UNIT: "예약 실행",
    product.INDEX_UNIT: "검색 색인",
    "nginx.service": "웹 프록시",
}
CHECK_LABELS = {"dns": "DNS", "https": "HTTPS", "web": "웹 서버", "app": "서비스 설정"}
STEP_LABELS = {
    "validate": "입력 확인", "cert": "인증서", "web": "웹 서버 설정", "config": "설정 파일", "check": "자체 확인",
    "services": "서비스 재시작", "web_restart": "웹 서버 다시 시작", "rollback": "되돌리기",
}


def _make_dns(nameservers: list[str] | None = None):
    from app.mail.dns import MailDns  # noqa: PLC0415 - 조회가 필요할 때만 dnspython 을 싣는다

    return MailDns(nameservers)


# 시험이 바꿔 끼우는 자리 — DNS 조회기, HTTPS 확인, 기다림.
DNS_FACTORY = _make_dns
SLEEP = time.sleep


def _https_get(bind_ip: str, host: str, path: str, cadata: str, timeout: float = PROBE_TIMEOUT,
               port: int = 443) -> tuple[int | None, str, str | None]:
    """`bind_ip:443` 에 `host` 이름(SNI 와 Host 머리)으로 붙어 `path` 를 GET 한다. 신뢰 기준은 `cadata` 하나뿐이다 — 이 인증서로
    이 이름이 검증돼야 통과다. 돌려주는 것은 (상태 코드, 본문 앞부분, 오류 종류). `port` 는 시험이 임시 포트의 진짜 TLS 서버로 이
    확인 자체를 재는 자리다(`tests/unit/test_sysops_domain_actions.py`)."""
    import http.client  # noqa: PLC0415
    import socket  # noqa: PLC0415
    import ssl  # noqa: PLC0415

    try:
        ctx = ssl.create_default_context(cadata=cadata)
    except (ssl.SSLError, ValueError) as exc:
        return None, "", f"trust: {exc.__class__.__name__}"
    ctx.check_hostname = True
    # 잎 인증서 하나를 신뢰 기준으로 받는다(사설 CA 사슬 전체가 없어도 「nginx 가 이 인증서를 낸다」를 잰다).
    ctx.verify_flags |= getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    try:
        raw = socket.create_connection((bind_ip, port), timeout=timeout)
    except OSError as exc:
        return None, "", f"connect: {exc.__class__.__name__}"
    try:
        tls = ctx.wrap_socket(raw, server_hostname=host)
    except (ssl.SSLError, ssl.CertificateError, OSError) as exc:
        raw.close()
        return None, "", f"tls: {str(exc)[:200]}"
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    conn.sock = tls
    try:
        conn.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host)
        conn.putheader("User-Agent", f"{product.SLUG}-privhelper")
        conn.putheader("Connection", "close")
        conn.endheaders()
        resp = conn.getresponse()
        body = resp.read(256 * 1024).decode("utf-8", "replace")
        return resp.status, body, None
    except (OSError, http.client.HTTPException) as exc:
        return None, "", f"http: {exc.__class__.__name__}"
    finally:
        conn.close()


HTTPS_PROBE = _https_get


# ── 문장 도우미 ────────────────────────────────────────────────────────────────


def _obj(word: str) -> str:
    return f"{word}{object_particle(word)}"


def _subj(word: str) -> str:
    return f"{word}{subject_particle(word)}"


def _topic(word: str) -> str:
    return f"{word}{topic_particle(word)}"


def _names_text(names: list[str]) -> str:
    return ", ".join(names)


# ── 입력 검증 (웹 라우터도 같은 함수로 먼저 거른다) ───────────────────────────


def _host(value: object, *, field: str = "새 주소") -> str:
    text = v.fqdn(value)
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return text
    raise v.InvalidSysopsValueError(f"{field}에는 IP 주소가 아니라 이름을 넣으세요.")


def _name_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        items = [part for part in value.replace(" ", ",").split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise v.InvalidSysopsValueError("함께 쓰는 주소는 목록이어야 합니다.")
    if len(items) > 20:
        raise v.InvalidSysopsValueError("함께 쓰는 주소가 너무 많습니다.")
    return items


def _aliases(value: object, host: str) -> list[str]:
    names = [_host(item, field="함께 쓰는 주소") for item in _name_list(value)]
    try:
        return df.normalize_aliases(host, names)
    except ValueError as exc:
        raise v.InvalidSysopsValueError(str(exc)) from exc


def _resolvers(value: object) -> list[str]:
    if value is None or value == "":
        return []
    items = value.replace(" ", ",").split(",") if isinstance(value, str) else value
    if not isinstance(items, (list, tuple)):
        raise v.InvalidSysopsValueError("비교할 DNS 서버는 목록이어야 합니다.")
    out: list[str] = []
    for item in items:
        if isinstance(item, str) and not item.strip():
            continue
        ip = v.ip_address(item)
        if ip not in out:
            out.append(ip)
    if len(out) > MAX_RESOLVERS:
        raise v.InvalidSysopsValueError(f"비교할 DNS 서버는 최대 {MAX_RESOLVERS}개까지입니다.")
    return out


def normalize_preview(params: Mapping) -> dict:
    raw = params.get("host")
    host = _host(raw) if raw not in (None, "") else None
    return {
        "host": host,
        "aliases": _aliases(params.get("aliases"), host) if host else None,
        "resolvers": _resolvers(params.get("resolvers")),
    }


def normalize_apply(params: Mapping) -> dict:
    host = _host(params.get("host"))
    aliases = _aliases(params.get("aliases"), host)
    cert = params.get("cert")
    if not isinstance(cert, Mapping):
        raise v.InvalidSysopsValueError("인증서 방식을 고르세요.")
    strategy = cert.get("strategy")
    if strategy not in CERT_STRATEGIES:
        raise v.InvalidSysopsValueError("인증서 방식이 올바르지 않습니다.")
    out_cert: dict = {"strategy": strategy}
    if strategy == "provided":
        out_cert["certificate"] = _pem(cert.get("certificate"), kind="인증서")
        out_cert["private_key"] = _pem(cert.get("private_key"), kind="개인키")
    restart_web = params.get("restart_web", False)
    if not isinstance(restart_web, bool):
        raise v.InvalidSysopsValueError("웹 서버 다시 시작 여부가 올바르지 않습니다.")
    return {"host": host, "aliases": aliases, "cert": out_cert, "restart_web": restart_web}


# ── 읽기 ─────────────────────────────────────────────────────────────────────


def _read_cert(runner: Runner, path: str) -> dict:
    """인증서 파일 하나의 사실 — 못 읽으면 `readable: False`."""
    if not path:
        return {"path": "", "readable": False}
    got = runner.run([OPENSSL, "x509", "-noout", "-subject", "-issuer", "-enddate", "-ext", "subjectAltName", "-in", path])
    if not got.ok:
        return {"path": path, "readable": False}
    info = df.parse_x509(got.stdout)
    return {
        "path": path, "readable": True, "subject": info["subject"], "issuer": info["issuer"],
        "not_after": info["not_after"], "self_signed": info["self_signed"],
        "sans": info["san"]["dns"], "ips": info["san"]["ip"],
    }


def _listening_443(runner: Runner, bind_ip: str) -> bool | None:
    tcp = runner.read_text("/proc/net/tcp")
    tcp6 = runner.read_text("/proc/net/tcp6")
    if tcp is None and tcp6 is None:
        return None
    heard = relay_files.parse_listeners(tcp, tcp6)
    wanted = {f"{bind_ip}:443", "0.0.0.0:443", f"[{bind_ip}]:443", "[::]:443"}
    return any(item in wanted for item in heard)


def _lookup(name: str, dns) -> dict:
    got = dns.a(name)
    return {"name": name, "answers": list(got.values), "error": got.error}


def _is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def _dns_state(row: dict, bind_ip: str) -> str:
    if row["error"] in ("nxdomain", "noanswer"):
        return "warn"
    if row["error"]:
        return "unknown"
    if bind_ip and bind_ip in row["answers"]:
        return "ok"
    # 이 서버의 hosts 항목이 자기 이름을 루프백(127.0.1.1 — Ubuntu 기본)으로 푸는 경우다. 이 서버 자신을 가리키므로 「이 서버로 풀리지
    # 않는다」가 아니다. 다만 다른 컴퓨터가 보는 사내 DNS 답은 이 점검이 보지 못하므로 그 사실은 문장으로 남긴다(랩 실측 2026-10-15).
    if row["answers"] and all(_is_loopback(a) for a in row["answers"]):
        row["local"] = True
        return "ok"
    return "warn"


def _dns_check(names: list[str], bind_ip: str, resolvers: list[str]) -> tuple[dict, dict]:
    system = DNS_FACTORY()
    rows = []
    for name in names:
        row = _lookup(name, system)
        row["state"] = _dns_state(row, bind_ip)
        rows.append(row)
    compare = []
    for ip in resolvers:
        row = _lookup(names[0], DNS_FACTORY([ip]))
        row["resolver"] = ip
        compare.append(row)

    first = rows[0]
    host = first["name"]
    if first["state"] == "ok" and first.get("local"):
        message = (f"이 서버의 hosts 항목이 {_obj(host)} 이 서버 자신({', '.join(first['answers'])})으로 풉니다. "
                   "다른 컴퓨터가 보는 사내 DNS 답은 이 점검이 보지 못하므로 따로 확인하세요.")
    elif first["state"] == "ok":
        message = f"이 서버가 쓰는 DNS 가 {_obj(host)} 이 서버 주소({bind_ip})로 풉니다."
    elif first["error"] in ("nxdomain", "noanswer"):
        message = f"이 서버가 쓰는 DNS 에 {_subj(host)} 없습니다. DNS 담당자가 이름을 넣어야 사내에서 이 주소로 열립니다."
    elif first["error"]:
        message = f"{_subj(host)} 어느 주소로 풀리는지 DNS 답을 받지 못했습니다."
    else:
        message = (f"이 서버가 쓰는 DNS 가 {_obj(host)} 다른 주소({', '.join(first['answers'])})로 풉니다. "
                   "앞단 프록시를 거쳐 들어오는 구성이면 정상입니다.")
    others = [r["name"] for r in rows[1:] if r["state"] != "ok"]
    if others:
        message += f" 함께 쓰는 주소 중 {_subj(_names_text(others))} 이 서버로 풀리지 않습니다."
    states = [r["state"] for r in rows]
    state = "ok" if all(s == "ok" for s in states) else ("unknown" if first["state"] == "unknown" else "warn")
    technical = "; ".join(f"{r['name']}={','.join(r['answers']) or r['error']}" for r in rows)
    check = {"key": "dns", "label": CHECK_LABELS["dns"], "state": state, "message": message, "technical": technical}
    return check, {"system": rows, "compare": compare}


def _https_check(cert: dict, names: list[str]) -> dict:
    base = {"key": "https", "label": CHECK_LABELS["https"]}
    if not cert.get("readable"):
        return {**base, "state": "unknown", "message": "지금 인증서를 읽지 못했습니다.", "technical": cert.get("path") or None}
    missing = df.missing_names({"dns": cert.get("sans") or []}, names)
    technical = f"SAN={','.join(cert.get('sans') or [])}; notAfter={cert.get('not_after')}"
    if missing:
        return {**base, "state": "warn", "technical": technical,
                "message": (f"지금 인증서에 {_subj(_names_text(missing))} 없습니다. 자체 서명 인증서를 새로 만들거나 "
                            "이 이름이 든 인증서를 붙여 넣으세요.")}
    message = "지금 인증서가 이 이름을 모두 담고 있습니다."
    if cert.get("self_signed"):
        message += " 자체 서명 인증서라 처음 여는 브라우저가 경고합니다."
    return {**base, "state": "ok", "message": message, "technical": technical}


def _web_check(runner: Runner, names: list[str], bind_ip: str) -> tuple[dict, list[str]]:
    base = {"key": "web", "label": CHECK_LABELS["web"]}
    template = runner.read_text(df.TEMPLATE_FILE)
    if not df.template_supports_aliases(template):
        return {**base, "state": "fail", "technical": df.TEMPLATE_FILE,
                "message": "웹 서버 설정 틀이 옛 버전입니다. 제품을 먼저 업그레이드하세요."}, []
    if not runner.exists(df.SITE_ENABLED):
        return {**base, "state": "fail", "technical": df.SITE_ENABLED,
                "message": "이 제품의 웹 서버 설정이 켜져 있지 않습니다. 설치기로 다시 설치하세요."}, []
    dump = runner.run([NGINX, "-T"], timeout=30)
    if not dump.ok:
        return {**base, "state": "unknown", "technical": (dump.stderr or "").strip()[-300:] or None,
                "message": "웹 서버 설정을 읽지 못했습니다."}, []
    server_names = df.site_server_names(dump.stdout)
    conflicts = df.name_conflicts(dump.stdout, names)
    if conflicts:
        path, name = conflicts[0]
        return {**base, "state": "fail", "technical": "; ".join(f"{p}: {n}" for p, n in conflicts),
                "message": f"다른 웹 서버 설정({path})이 {_obj(name)} 이미 씁니다. 그 설정에서 이름을 뺀 뒤 다시 확인하세요."}, server_names
    listening = _listening_443(runner, bind_ip)
    if listening is False:
        return {**base, "state": "fail", "technical": f"{bind_ip}:443",
                "message": f"웹 서버가 {bind_ip}:443 에서 요청을 받지 않습니다."}, server_names
    missing = [n for n in names if n not in server_names]
    if missing:
        return {**base, "state": "warn", "technical": " ".join(server_names) or None,
                "message": f"웹 서버 설정에 {_subj(_names_text(missing))} 아직 없습니다. 적용하면 더합니다."}, server_names
    return {**base, "state": "ok", "technical": " ".join(server_names),
            "message": "웹 서버가 이 이름들로 들어오는 요청을 받습니다."}, server_names


def _app_check(state: dict, host: str) -> dict:
    base = {"key": "app", "label": CHECK_LABELS["app"]}
    if not state["env_readable"]:
        return {**base, "state": "fail", "technical": product.ENV_FILE, "message": "서비스 설정 파일을 읽지 못했습니다."}
    if not state["manifest_readable"] or not state["bind_ip"]:
        return {**base, "state": "fail", "technical": df.MANIFEST_FILE,
                "message": "설치 기록을 읽지 못했습니다. 설치기로 한 번 업그레이드하세요."}
    want = f"https://{host}"
    if state["app_base_url"].rstrip("/") == want:
        return {**base, "state": "ok", "technical": f"APP_BASE_URL={state['app_base_url']}",
                "message": f"알림 메일과 링크가 {_obj(want)} 씁니다."}
    return {**base, "state": "warn", "technical": f"APP_BASE_URL={state['app_base_url']}",
            "message": f"지금 알림 메일과 링크는 {_obj(state['app_base_url'] or '빈 주소')} 씁니다. 적용하면 {want}로 바뀝니다."}


def _impact(state: dict, host: str, aliases: list[str]) -> list[str]:
    current = state["canonical"]
    if not current or (current == host and aliases == state["aliases"]):
        return []
    out = []
    if current != host:
        out.append("새 주소로 처음 들어올 때 한 번 다시 로그인해야 합니다. 로그인은 주소마다 따로 유지됩니다.")
        out.append("알림 메일과 공유 링크가 새 주소를 씁니다. 이미 보낸 메일의 링크는 옛 주소를 가리킵니다.")
        if current in aliases:
            out.append(f"옛 주소 {_topic(current)} 함께 쓰는 주소로 남아 그대로 열립니다.")
        else:
            out.append(f"옛 주소 {_topic(current)} 더 이상 열리지 않습니다. 함께 쓰는 주소에 넣으면 계속 열 수 있습니다.")
    out.append("사내 DNS 와 공개 DNS 는 바뀌지 않습니다. 이름을 넣거나 빼는 일은 DNS 담당자가 합니다.")
    return out


def _perform_preview(runner: Runner, params: dict) -> ActionOutcome:
    """읽기 전용. 하나를 못 읽어도 나머지는 준다(`system.info` 와 같은 규칙)."""
    state = domain_state(runner)
    host = params["host"] or state["canonical"]
    if not host:
        return ActionOutcome(ok=False, detail="지금 서비스 주소를 읽지 못했습니다. 설치 기록과 설정 파일을 확인하세요.",
                             data={"current": _current_view(state, None, [])})
    aliases = params["aliases"] if params["host"] else [a for a in state["aliases"] if a != host]
    names = [host, *aliases]
    bind_ip = state["bind_ip"]
    cert = _read_cert(runner, state["cert_path"])
    web, server_names = _web_check(runner, names, bind_ip)
    try:
        dns_check, dns = _dns_check(names, bind_ip, params["resolvers"])
    except Exception as exc:  # noqa: BLE001 - 조회기를 못 만들어도(해석기 설정 없음) 나머지 확인은 준다
        logger.warning("DNS 확인을 하지 못했습니다: %s", exc.__class__.__name__)
        dns_check = {"key": "dns", "label": CHECK_LABELS["dns"], "state": "unknown",
                     "message": "DNS 를 확인하지 못했습니다.", "technical": exc.__class__.__name__}
        dns = {"system": [], "compare": []}
    checks = [dns_check, _https_check(cert, names), web, _app_check(state, host)]
    data = {
        "target": {"host": host, "aliases": aliases, "names": names,
                   "changes": host != state["canonical"] or aliases != state["aliases"]},
        "current": _current_view(state, cert, server_names),
        "checks": checks,
        "dns": dns,
        "impact": _impact(state, host, aliases),
        "can_apply": not any(c["state"] == "fail" for c in checks),
    }
    return ActionOutcome(ok=True, detail="서비스 주소를 확인했습니다.", data=data)


def _current_view(state: dict, cert: dict | None, server_names: list[str]) -> dict:
    return {
        "canonical": state["canonical"], "app_base_url": state["app_base_url"], "dns_name": state["dns_name"],
        "aliases": state["aliases"], "bind_ip": state["bind_ip"], "upstream_proxies": state["upstream_proxies"],
        "cert": cert or {"path": state["cert_path"], "readable": False}, "server_names": server_names,
    }


# ── 적용 ─────────────────────────────────────────────────────────────────────


def _apply_touches(params: dict) -> tuple[str, ...]:
    crt, key = df.cert_paths(product.TLS_DIR, params["host"])
    return (product.ENV_FILE, df.MANIFEST_FILE, df.SITE_AVAILABLE, crt, key)


class _Steps:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool, detail: str, **extra) -> None:
        self.rows.append({"name": name, "label": STEP_LABELS.get(name, name), "ok": ok, "detail": detail, **extra})


def _fail(steps: _Steps, name: str, detail: str, **extra) -> ActionOutcome:
    steps.add(name, False, detail, **extra)
    return ActionOutcome(ok=False, detail=detail, data={"steps": steps.rows})


def _file_mode(path: str) -> int:
    """되쓸 때의 권한 — 개인키 0600, env · 매니페스트 0640(설치기와 같은 값), 나머지 0644."""
    if path.endswith(".key"):
        return 0o600
    if path in (product.ENV_FILE, df.MANIFEST_FILE):
        return 0o640
    return 0o644


def _restore_files(runner: Runner, previous: dict[str, str | None]) -> None:
    """옛 글을 되쓴다(없던 파일은 지운다). 엔진도 뒤에 백업에서 같은 일을 한다 — 여기서 먼저 하는 까닭은 nginx 를 옛 설정으로 다시
    읽히려면 파일이 먼저 돌아와 있어야 하기 때문이다."""
    for path, text in previous.items():
        try:
            if text is None:
                runner.remove(path)
            else:
                runner.write_text(path, text, mode=_file_mode(path))
        except OSError:
            logger.exception("되돌리기 중 파일을 쓰지 못했습니다: %s", path)


def _revert_and_reload(runner: Runner, previous: dict[str, str | None], steps: _Steps) -> None:
    """vhost 를 쓴 뒤 실패했을 때 — 그 자리에서 옛 글을 되쓰고 nginx 를 다시 읽힌다. 엔진은 뒤에 같은 파일을 다시 복원한다."""
    _restore_files(runner, previous)
    checked = runner.run([NGINX, "-t"], timeout=30)
    if not checked.ok:
        steps.add("rollback", False, "설정을 되돌렸지만 웹 서버 설정 검사가 실패했습니다. 서버에서 nginx -t 를 확인하세요.",
                  technical=(checked.stderr or "").strip()[-300:])
        return
    reloaded = runner.run([SYSTEMCTL, "reload", "nginx.service"], timeout=30)
    steps.add("rollback", reloaded.ok,
              "바꾸기 전 설정으로 되돌리고 웹 서버가 다시 읽게 했습니다." if reloaded.ok
              else "설정을 되돌렸지만 웹 서버가 다시 읽지 못했습니다.",
              technical=None if reloaded.ok else (reloaded.stderr or "").strip()[-300:])


def _prepare_cert(runner: Runner, params: dict, state: dict, names: list[str], crt: str, key: str) -> tuple[str | None, str | None, str]:
    """인증서를 `crt`/`key` 자리에 준비한다. (실패 문장, 기술 정보, 신뢰 기준으로 쓸 인증서 글)."""
    strategy = params["cert"]["strategy"]
    if strategy == "self_signed":
        got = runner.run(df.self_signed_argv(OPENSSL, crt=crt, key=key, host=params["host"], names=params["aliases"],
                                             bind_ip=state["bind_ip"]), timeout=60)
        if not got.ok:
            return "자체 서명 인증서를 만들지 못했습니다.", (got.stderr or "").strip()[-300:], ""
    elif strategy == "keep":
        current = _read_cert(runner, state["cert_path"])
        if not current.get("readable"):
            return "지금 인증서를 읽지 못했습니다.", state["cert_path"], ""
        missing = df.missing_names({"dns": current.get("sans") or []}, names)
        if missing:
            return (f"지금 인증서에 {_subj(_names_text(missing))} 없습니다. 자체 서명 인증서를 새로 만들거나 "
                    "이 이름이 든 인증서를 붙여 넣으세요."), f"SAN={','.join(current.get('sans') or [])}", ""
        if state["cert_path"] != crt:
            if not (runner.copy(state["cert_path"], crt) and runner.copy(df.key_path_for(state["cert_path"]), key)):
                return "지금 인증서의 개인키를 찾지 못했습니다.", df.key_path_for(state["cert_path"]), ""
    else:
        stage_crt, stage_key = f"{product.TLS_DIR}/.staged.crt", f"{product.TLS_DIR}/.staged.key"
        try:
            why = _validate_pair(runner, params["cert"]["certificate"], params["cert"]["private_key"],
                                 cert_stage=stage_crt, key_stage=stage_key)
            if why:
                return why, None, ""
            staged = _read_cert(runner, stage_crt)
            missing = df.missing_names({"dns": staged.get("sans") or []}, names)
            if missing:
                return f"붙여 넣은 인증서에 {_subj(_names_text(missing))} 없습니다.", f"SAN={','.join(staged.get('sans') or [])}", ""
            runner.write_text(crt, params["cert"]["certificate"], mode=0o644)
            runner.write_text(key, params["cert"]["private_key"], mode=0o600)
        finally:
            runner.remove(stage_crt)
            runner.remove(stage_key)
    runner.chown(key, "root", "root", mode=0o600)
    runner.chown(crt, "root", "root", mode=0o644)
    text = runner.read_text(crt) or ""
    return None, None, text


def _self_check(bind_ip: str, names: list[str], cadata: str) -> list[str]:
    """새 인증서를 신뢰 기준으로 이 서버 443 에 이름마다 붙어 본다. 문제 목록을 돌려준다(비면 통과)."""
    problems: list[str] = []
    host = names[0]
    status, _body, error = HTTPS_PROBE(bind_ip, host, "/healthz", cadata)
    if status != 200:
        problems.append(f"https://{host}/healthz -> {status or error}")
    status, body, error = HTTPS_PROBE(bind_ip, host, "/login", cadata)
    if status != 200 or LOGIN_MARKER not in (body or ""):
        problems.append(f"https://{host}/login -> {status or error}")
    for alias in names[1:]:
        status, _body, error = HTTPS_PROBE(bind_ip, alias, "/healthz", cadata)
        if status != 200:
            problems.append(f"https://{alias}/healthz -> {status or error}")
    return problems


def _restart_backends(runner: Runner) -> list[dict]:
    rows: list[dict] = []
    for unit in BACKEND_UNITS:
        label = UNIT_LABELS[unit]
        before = (runner.run([SYSTEMCTL, "is-active", unit]).stdout or "").strip()
        if before != "active":
            rows.append({"unit": unit, "label": label, "ok": True, "skipped": True,
                         "detail": "꺼져 있어 다시 시작하지 않았습니다."})
            continue
        got = runner.run([SYSTEMCTL, "restart", unit], timeout=UNIT_RESTART_TIMEOUT)
        after = (runner.run([SYSTEMCTL, "is-active", unit]).stdout or "").strip()
        if got.ok and after == "active":
            rows.append({"unit": unit, "label": label, "ok": True, "detail": "다시 시작했습니다."})
        elif got.returncode == 124:
            rows.append({"unit": unit, "label": label, "ok": False,
                         "detail": f"{UNIT_RESTART_TIMEOUT}초 안에 다시 시작하지 못했습니다. 하던 작업을 마치는 중일 수 있습니다."})
        else:
            rows.append({"unit": unit, "label": label, "ok": False,
                         "detail": f"다시 시작하지 못했습니다(지금 상태 {after or '알 수 없음'})."})
    return rows


def transient_unit_name(unit: str) -> str:
    stem = unit[:-len(".service")] if unit.endswith(".service") else unit
    return f"{stem}-restart" if stem.startswith(f"{product.SLUG}-") else f"{product.SLUG}-{stem}-restart"


def restart_argv(unit: str, delay: int) -> list[str]:
    """`systemd-run` 한 줄. 타이머는 울린 뒤 내려간다(`RemainAfterElapse=no`) — 기본값(yes)이면 울린 타이머가 실린 채 남아 같은 이름으로
    두 번째 예약을 할 수 없다. 서비스 쪽은 `--collect` 로 실패해도 내려간다."""
    return [SYSTEMD_RUN, f"--on-active={delay}", f"--unit={transient_unit_name(unit)}", "--collect",
            "--timer-property=RemainAfterElapse=no", f"--description=deferred restart of {unit}",
            SYSTEMCTL, "restart", unit]


def _schedule_restart(runner: Runner, unit: str, delay: int) -> tuple[bool, str, str]:
    transient = transient_unit_name(unit)
    got = runner.run(restart_argv(unit, delay), timeout=20)
    return got.ok, transient, (got.stderr or "").strip()[-300:]


def _perform_apply(runner: Runner, params: dict) -> ActionOutcome:
    steps = _Steps()
    host, aliases = params["host"], params["aliases"]
    names = [host, *aliases]
    state = domain_state(runner)
    crt, key = df.cert_paths(product.TLS_DIR, host)

    # ① 검증 — 여기서 실패하면 아무것도 쓰지 않았다.
    if not state["env_readable"]:
        return _fail(steps, "validate", "서비스 설정 파일을 읽지 못했습니다.")
    if not state["manifest_readable"] or not state["bind_ip"]:
        return _fail(steps, "validate", "설치 기록을 읽지 못했습니다. 설치기로 한 번 업그레이드하세요.")
    template = runner.read_text(df.TEMPLATE_FILE)
    if template is None:
        return _fail(steps, "validate", "웹 서버 설정 틀을 찾지 못했습니다. 설치기로 다시 설치하세요.", technical=df.TEMPLATE_FILE)
    try:
        rendered = df.render_vhost(template, state["bind_ip"], host, aliases)
    except ValueError:
        return _fail(steps, "validate", "웹 서버 설정 틀이 옛 버전입니다. 제품을 먼저 업그레이드하세요.", technical=df.TEMPLATE_FILE)
    if not runner.exists(df.SITE_ENABLED):
        return _fail(steps, "validate", "이 제품의 웹 서버 설정이 켜져 있지 않습니다. 설치기로 다시 설치하세요.")
    dump = runner.run([NGINX, "-T"], timeout=30)
    if dump.ok:
        conflicts = df.name_conflicts(dump.stdout, names)
        if conflicts:
            path, name = conflicts[0]
            return _fail(steps, "validate", f"다른 웹 서버 설정({path})이 {_obj(name)} 이미 씁니다.",
                         technical="; ".join(f"{p}: {n}" for p, n in conflicts))
    env_text = state["_env_text"] or ""
    manifest = dict(state["_manifest"])
    new_env = df.env_set(df.env_set(env_text, "APP_BASE_URL", f"https://{host}"), "TLS_CERT_PATH", crt)
    manifest["dns_name"] = host
    manifest["alias_names"] = df.join_names(aliases)
    new_manifest = df.dump_manifest(manifest)
    current_vhost = runner.read_text(df.SITE_AVAILABLE)
    if (params["cert"]["strategy"] == "keep" and state["cert_path"] == crt and current_vhost == rendered
            and new_env == env_text and state["dns_name"] == host and state["aliases"] == aliases):
        steps.add("validate", True, "이미 이 주소로 설정돼 있어 바꿀 것이 없습니다.")
        return ActionOutcome(ok=True, changed=False, detail=f"이미 {host} 주소로 설정돼 있습니다.",
                             data={"steps": steps.rows, "host": host, "aliases": aliases, "url": f"https://{host}"})
    steps.add("validate", True, f"{_obj(_names_text(names))} 쓸 수 있는지 확인했습니다.")

    # 되돌리기용 옛 글. 개인키 글도 들지만 메모리 밖으로 나가지 않는다.
    previous = {path: runner.read_text(path) for path in (df.SITE_AVAILABLE, crt, key, product.ENV_FILE, df.MANIFEST_FILE)}
    phase = "cert"
    try:
        # ② 인증서
        why, technical, cadata = _prepare_cert(runner, params, state, names, crt, key)
        if why:
            _restore_files(runner, previous)
            return _fail(steps, "cert", why, technical=technical)
        steps.add("cert", True, {
            "self_signed": "자체 서명 인증서를 새로 만들었습니다.",
            "keep": "지금 인증서를 그대로 씁니다.",
            "provided": "붙여 넣은 인증서를 확인하고 넣었습니다.",
        }[params["cert"]["strategy"]])

        # ③ 웹 서버 설정
        phase = "web"
        runner.write_text(df.SITE_AVAILABLE, rendered, mode=0o644)
        checked = runner.run([NGINX, "-t"], timeout=30)
        if not checked.ok:
            steps.add("web", False, "웹 서버가 새 설정을 받아들이지 않았습니다.", technical=(checked.stderr or "").strip()[-300:])
            _revert_and_reload(runner, previous, steps)
            return ActionOutcome(ok=False, detail="웹 서버가 새 설정을 받아들이지 않았습니다.", data={"steps": steps.rows})
        reloaded = runner.run([SYSTEMCTL, "reload", "nginx.service"], timeout=30)
        if not reloaded.ok:
            steps.add("web", False, "웹 서버가 새 설정을 다시 읽지 못했습니다.", technical=(reloaded.stderr or "").strip()[-300:])
            _revert_and_reload(runner, previous, steps)
            return ActionOutcome(ok=False, detail="웹 서버가 새 설정을 다시 읽지 못했습니다.", data={"steps": steps.rows})
        steps.add("web", True, "웹 서버 설정에 이름을 넣고 다시 읽게 했습니다.")

        # ④ 설정 파일 — env 와 매니페스트(다음 upgrade 가 이어 받는다)
        phase = "config"
        runner.write_text(product.ENV_FILE, new_env, mode=0o640)
        runner.chown(product.ENV_FILE, "root", product.SERVICE_GROUP, mode=0o640)
        runner.write_text(df.MANIFEST_FILE, new_manifest, mode=0o640)
        runner.chown(df.MANIFEST_FILE, "root", product.SERVICE_GROUP, mode=0o640)
        steps.add("config", True, "서비스 설정 파일과 설치 기록에 새 주소를 적었습니다.")

        # ⑤ 자체 확인 — nginx reload 가 새 작업 프로세스를 띄우는 동안 잠깐 기다렸다 다시 본다.
        phase = "check"
        problems: list[str] = []
        for attempt in range(SELF_CHECK_ATTEMPTS):
            problems = _self_check(state["bind_ip"], names, cadata)
            if not problems:
                break
            if attempt + 1 < SELF_CHECK_ATTEMPTS:
                SLEEP(1)
        if problems:
            steps.add("check", False, "새 주소로 접속하는 확인을 통과하지 못했습니다.", technical="; ".join(problems)[:500])
            _revert_and_reload(runner, previous, steps)
            return ActionOutcome(ok=False, detail="새 주소로 접속하는 확인을 통과하지 못했습니다.", data={"steps": steps.rows})
        steps.add("check", True, "새 인증서로 새 주소에 접속해 로그인 화면까지 확인했습니다.")
    except Exception as exc:  # noqa: BLE001 - 파일을 쓴 뒤라면 nginx 를 옛 설정으로 되돌린 뒤 실패로 알린다
        logger.exception("대표 주소 적용 중 오류 (%s)", exc.__class__.__name__)
        steps.add(phase, False, f"처리 중 오류가 발생했습니다({exc.__class__.__name__}).")
        _revert_and_reload(runner, previous, steps)
        return ActionOutcome(ok=False, detail=f"처리 중 오류가 발생했습니다({exc.__class__.__name__}).", data={"steps": steps.rows})

    # ⑥ 뒷단 유닛 — 실패해도 되돌리지 않는다(머리말).
    units = _restart_backends(runner)
    restarted_bad = [u for u in units if not u["ok"]]
    steps.add("services", not restarted_bad,
              "백그라운드 서비스를 새 설정으로 다시 시작했습니다." if not restarted_bad
              else "일부 백그라운드 서비스를 다시 시작하지 못했습니다.", units=units)

    # ⑦ web — 이 요청을 처리하는 프로세스라 몇 초 뒤에 맡긴다.
    web_restart = {"scheduled": False, "delay_seconds": WEB_RESTART_DELAY}
    warnings = [f"{u['label']}: {u['detail']}" for u in restarted_bad]
    if params["restart_web"]:
        ok, transient, err = _schedule_restart(runner, product.WEB_UNIT, WEB_RESTART_DELAY)
        web_restart.update({"scheduled": ok, "unit": transient})
        steps.add("web_restart", ok,
                  f"웹 서버를 {WEB_RESTART_DELAY}초 뒤에 다시 시작합니다." if ok
                  else "웹 서버 다시 시작을 예약하지 못했습니다. 설정 화면의 서비스에서 웹 서버를 다시 시작하세요.",
                  technical=None if ok else err)
        if not ok:
            warnings.append("웹 서버 다시 시작을 예약하지 못했습니다.")
    detail = f"대표 주소를 {host}로 바꿨습니다."
    if warnings:
        detail += " 다시 시작하지 못한 서비스가 있습니다."
    return ActionOutcome(
        ok=True, changed=True, detail=detail,
        data={"steps": steps.rows, "host": host, "aliases": aliases, "url": f"https://{host}", "cert_path": crt,
              "web_restart": web_restart, "warnings": warnings},
    )


# ── 지연 재시작 ──────────────────────────────────────────────────────────────


def normalize_restart_deferred(params: Mapping) -> dict:
    unit = params.get("unit")
    if unit not in MANAGED_UNITS:
        raise v.InvalidSysopsValueError(f"관리 대상 서비스가 아닙니다: {str(unit)[:64]}")
    delay = params.get("delay_seconds", WEB_RESTART_DELAY)
    low, high = DEFERRED_DELAY
    if not isinstance(delay, int) or isinstance(delay, bool) or not (low <= delay <= high):
        raise v.InvalidSysopsValueError(f"기다릴 시간은 {low}초에서 {high}초 사이로 정합니다.")
    return {"unit": unit, "delay_seconds": delay}


def _perform_restart_deferred(runner: Runner, params: dict) -> ActionOutcome:
    unit, delay = params["unit"], params["delay_seconds"]
    ok, transient, err = _schedule_restart(runner, unit, delay)
    label = UNIT_LABELS.get(unit, unit)
    if not ok:
        return ActionOutcome(ok=False, detail=f"{label} 다시 시작을 예약하지 못했습니다.", data={"technical": err})
    return ActionOutcome(ok=True, changed=True, detail=f"{_obj(label)} {delay}초 뒤에 다시 시작합니다.",
                         data={"unit": unit, "delay_seconds": delay, "transient_unit": transient})


register(Action(
    name="domain.preview",
    summary="서비스 주소 미리 확인",
    mutating=False,
    normalize=normalize_preview,
    perform=_perform_preview,
))

register(Action(
    name="domain.apply",
    summary="서비스 주소 바꾸기",
    mutating=True,
    normalize=normalize_apply,
    perform=_perform_apply,
    touches=_apply_touches,
))

register(Action(
    name="service.restart_deferred",
    summary="서비스 지연 재시작",
    mutating=True,
    normalize=normalize_restart_deferred,
    perform=_perform_restart_deferred,
))
