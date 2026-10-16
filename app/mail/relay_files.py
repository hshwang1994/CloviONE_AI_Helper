"""ClovirAssist 로컬 릴레이의 설정 파일 (계획 M7, D-551).

이 모듈은 **순수 함수**다. 특권 헬퍼(`app/sysops/actions_mailrelay.py`)가 이 함수들로 Postfix · OpenDKIM 설정을 만들어 쓰고,
시험은 같은 함수의 결과를 황금 파일과 견준다. DB 도, 네트워크도, 파일도 만지지 않는다(헬퍼 프로세스가 앱 전체를 끌어오지 않게).

## 보안 계약 넷과 지키는 자리

1. **외부에서 접근할 수 없다** — `inet_interfaces = loopback-only` 이고 master.cf 의 받는 문은 `127.0.0.1:2525` 하나다. 패키지
   기본의 `smtp inet`(25번) 줄을 걷는다 - 켠 뒤에도 25번은 아무도 듣지 않는다(바깥으로 보내는 25번 연결은 그대로다).
2. **ClovirAssist 만 쓸 수 있다** — 받는 문은 보안 연결을 강제하고(`smtpd_tls_security_level = encrypt`) 중계 허가는
   `permit_tls_clientcerts` 하나다. 허가 목록(`relay_clientcerts`)에는 앱만 가진 클라이언트 인증서의 지문 하나만 있다.
3. **열린 중계가 될 수 없다** — `smtpd_relay_restrictions` 와 `smtpd_recipient_restrictions` 가 둘 다
   `permit_tls_clientcerts, reject` 다. 로컬 배달도 없다(`mydestination =` · `local_transport = error:…`).
4. **일반 로컬 프로세스가 임의로 발송할 수 없다** — 같은 서버의 다른 프로세스가 2525 에 붙어도 인증서가 없으면 「Relay access
   denied」다. Postfix 의 `sendmail` 명령(setgid `postdrop`)으로 큐에 넣는 길도 닫는다: `authorized_submit_users =`(빈 목록 =
   아무도 못 넣는다)이고 그 길의 집배원인 `pickup` 서비스를 master.cf 에서 걷는다. 큐 보기 · 비우기도 root 만이다.

## 제품이 관리하는 파일인가 (기존 구성 보존)

`main.cf` 의 첫 줄 표지(`MARKER`)와 헬퍼 상태 파일(`STATE_FILE`)의 같은 지문이 둘 다 있어야 「제품이 만든 파일」이다. 표지가
없거나 지문이 다르면 **기존 구성**이고 헬퍼는 지우지도, 덮지도, 인수하지도 않는다. `main.cf` 가 없으면(꾸러미만 깔린 상태)
기존 구성이 아니다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping

# ── 고정 값 ─────────────────────────────────────────────────────────────────

RELAY_HOST = "127.0.0.1"
RELAY_PORT = 2525
MILTER_PORT = 8891

POSTFIX_DIR = "/etc/postfix"
MAIN_CF = f"{POSTFIX_DIR}/main.cf"
MASTER_CF = f"{POSTFIX_DIR}/master.cf"
MASTER_CF_PROTO = f"{POSTFIX_DIR}/master.cf.proto"
MANAGED_DIR = f"{POSTFIX_DIR}/clovirassist"
SERVER_CERT = f"{MANAGED_DIR}/server.crt"
SERVER_KEY = f"{MANAGED_DIR}/server.key"
CLIENT_CERTS = f"{MANAGED_DIR}/clientcerts"
SASL_PASSWD = f"{MANAGED_DIR}/sasl_passwd"
TRANSPORT_MAP = f"{MANAGED_DIR}/transport"
STATE_FILE = f"{MANAGED_DIR}/state.json"
OPENDKIM_CONF = "/etc/opendkim.conf"
OPENDKIM_KEYS = "/etc/opendkim/keys"
CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"

POSTFIX_UNIT = "postfix.service"
POSTFIX_INSTANCE_UNIT = "postfix@-.service"
OPENDKIM_UNIT = "opendkim.service"

MARKER = "# managed-by: clovirassist"
DELIVERY_SMARTHOST = "smarthost"
DELIVERY_DIRECT = "direct"
SECURITY_NONE = "none"
SECURITY_STARTTLS = "starttls"
SECURITY_SSL = "ssl"
MAX_OVERRIDES = 20

# ── 입력 모양 (헬퍼가 다시 검사한다 — 웹이 뚫렸다는 가정에서도 설정 파일에 줄이 끼지 않게) ────────────────

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DOMAIN_RE = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})+$")
HOST_RE = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})*$")
SELECTOR_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
IPV4_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$")
# 계정은 SASL 사용자 이름이다. 공백 · 줄바꿈 · `=` · 콜론이 들어가면 sasl_passwd 한 줄이 깨진다.
USERNAME_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/?^_`{|}~@-]{1,320}$")
FINGERPRINT_RE = re.compile(r"^(?:[0-9A-F]{2}:){31}[0-9A-F]{2}$")


class RelayParamsError(ValueError):
    """설정 값이 모양에 맞지 않는다. 문구는 사람에게 그대로 간다 - 값을 싣지 않는다."""


def _text(value: object) -> str:
    return str(value or "").strip()


def normalize_params(raw: Mapping) -> dict:
    """헬퍼의 `mailrelay.apply` 인자. 모르는 키는 거절한다 — 인자로 설정 줄을 끼워 넣을 틈을 남기지 않는다."""
    allowed = {"delivery", "sender_domain", "helo_name", "ipv4_only", "smarthost", "dkim", "transport_overrides"}
    unknown = sorted(k for k in raw if k not in allowed)
    if unknown:
        raise RelayParamsError("알 수 없는 항목이 있습니다.")
    delivery = _text(raw.get("delivery"))
    if delivery not in (DELIVERY_SMARTHOST, DELIVERY_DIRECT):
        raise RelayParamsError("전달 방식이 올바르지 않습니다.")
    sender_domain = _text(raw.get("sender_domain")).lower()
    if not DOMAIN_RE.match(sender_domain):
        raise RelayParamsError("보내는 주소의 도메인이 올바르지 않습니다.")
    helo = _text(raw.get("helo_name")).lower()
    if helo and not DOMAIN_RE.match(helo):
        raise RelayParamsError("메일 서버 이름(HELO)은 mail.example.com 같은 이름이어야 합니다.")
    if delivery == DELIVERY_DIRECT and not helo:
        raise RelayParamsError("인터넷으로 직접 전달하려면 서버 이름(HELO)이 필요합니다.")
    ipv4_only = raw.get("ipv4_only", False)
    if not isinstance(ipv4_only, bool):
        raise RelayParamsError("IPv4만 쓰기 값이 올바르지 않습니다.")
    out: dict = {"delivery": delivery, "sender_domain": sender_domain, "helo_name": helo, "ipv4_only": ipv4_only,
                 "smarthost": None, "dkim": None, "transport_overrides": []}
    if delivery == DELIVERY_SMARTHOST:
        out["smarthost"] = _normalize_smarthost(raw.get("smarthost"))
    else:
        out["dkim"] = _normalize_dkim(raw.get("dkim"), sender_domain)
        out["transport_overrides"] = normalize_overrides(raw.get("transport_overrides") or [])
    return out


def _normalize_smarthost(raw: object) -> dict:
    if not isinstance(raw, Mapping):
        raise RelayParamsError("상위 SMTP 서버 설정이 없습니다.")
    unknown = sorted(k for k in raw if k not in ("host", "port", "security", "username"))
    if unknown:
        raise RelayParamsError("상위 SMTP 서버 설정에 알 수 없는 항목이 있습니다.")
    host = _text(raw.get("host")).lower()
    if not (HOST_RE.match(host) or IPV4_RE.match(host)):
        raise RelayParamsError("상위 SMTP 서버 주소는 smtp.example.com처럼 이름이나 IP만 적습니다.")
    port = raw.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port < 65536):
        raise RelayParamsError("상위 SMTP 서버 포트는 1~65535 사이의 정수여야 합니다.")
    security = _text(raw.get("security"))
    if security not in (SECURITY_NONE, SECURITY_STARTTLS, SECURITY_SSL):
        raise RelayParamsError("상위 SMTP 서버의 보안 연결 방식이 올바르지 않습니다.")
    username = _text(raw.get("username"))
    if username and not USERNAME_RE.match(username):
        raise RelayParamsError("상위 SMTP 계정에 쓸 수 없는 문자가 있습니다.")
    return {"host": host, "port": port, "security": security, "username": username}


def _normalize_dkim(raw: object, sender_domain: str) -> dict | None:
    if raw in (None, False):
        return None
    if not isinstance(raw, Mapping):
        raise RelayParamsError("DKIM 서명 설정이 올바르지 않습니다.")
    selector = _text(raw.get("selector")).lower()
    if not SELECTOR_RE.match(selector):
        raise RelayParamsError("DKIM 선택자는 영문 소문자와 숫자, 하이픈으로 씁니다.")
    return {"domain": sender_domain, "selector": selector}


def normalize_overrides(raw: Iterable) -> list[dict]:
    """「받는 도메인별 전달 서버」(분리 DNS 용). 최대 20줄, 도메인과 호스트 모양만 받는다."""
    if not isinstance(raw, (list, tuple)):
        raise RelayParamsError("받는 도메인별 전달 서버는 목록이어야 합니다.")
    if len(raw) > MAX_OVERRIDES:
        raise RelayParamsError(f"받는 도메인별 전달 서버는 {MAX_OVERRIDES}줄까지 넣을 수 있습니다.")
    seen: set[str] = set()
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, Mapping) or sorted(item) != ["domain", "host"]:
            raise RelayParamsError("받는 도메인별 전달 서버 한 줄은 도메인과 전달 서버 둘로 씁니다.")
        domain = _text(item.get("domain")).lower()
        host = _text(item.get("host")).lower()
        if not DOMAIN_RE.match(domain):
            raise RelayParamsError("받는 도메인은 example.com 같은 이름이어야 합니다.")
        if not (HOST_RE.match(host) or IPV4_RE.match(host)):
            raise RelayParamsError("전달 서버는 mx.example.com처럼 이름이나 IP만 적습니다.")
        if domain in seen:
            raise RelayParamsError("같은 받는 도메인을 두 번 넣었습니다.")
        seen.add(domain)
        out.append({"domain": domain, "host": host})
    return out


# ── 파일 내용 ────────────────────────────────────────────────────────────────


def _lines(pairs: Iterable[tuple[str, str]]) -> str:
    return "".join(f"{key} = {value}".rstrip() + "\n" for key, value in pairs)


def render_main_cf(params: Mapping) -> str:
    """main.cf 전체. 첫 줄은 표지이고 그 뒤는 고정 보안 키 + 전달 방식별 키다."""
    delivery = params["delivery"]
    smarthost = params.get("smarthost") or {}
    dkim = params.get("dkim")
    head = [
        MARKER,
        "# 이 파일은 ClovirAssist 가 만든다. 손으로 고치면 「기존 메일 발송 구성」으로 보고 다시 적용하지 않는다.",
        "# 발송 전용이다: 받는 문은 127.0.0.1:2525 하나이고 앱의 클라이언트 인증서가 있어야 중계한다.",
        "",
    ]
    pairs: list[tuple[str, str]] = [
        ("compatibility_level", "3.6"),
    ]
    if params.get("helo_name"):
        pairs.append(("myhostname", params["helo_name"]))
    pairs += [
        ("myorigin", params["sender_domain"]),
        # 로컬 배달 없음 — 메일함도, 별칭도, postmaster 알림도 없다.
        ("mydestination", ""),
        ("local_recipient_maps", ""),
        ("local_transport", "error:local delivery disabled"),
        ("alias_maps", ""),
        ("alias_database", ""),
        ("notify_classes", ""),
        ("biff", "no"),
        # 받는 문은 루프백뿐이다(계약 1).
        ("inet_interfaces", "loopback-only"),
        ("inet_protocols", "ipv4" if params.get("ipv4_only") else "all"),
        ("mynetworks", "127.0.0.0/8 [::1]/128"),
        ("smtpd_banner", "$myhostname ESMTP"),
        ("disable_vrfy_command", "yes"),
        ("smtpd_helo_required", "yes"),
        # `sendmail` 명령으로 큐에 넣는 길을 닫는다(계약 4). 큐 보기 · 비우기는 root(헬퍼)만이다.
        ("authorized_submit_users", ""),
        ("authorized_mailq_users", "root"),
        ("authorized_flush_users", "root"),
        # 보안 연결을 강제하고 앱 인증서의 지문만 중계를 허가한다(계약 2 · 3).
        ("smtpd_tls_security_level", "encrypt"),
        ("smtpd_tls_cert_file", SERVER_CERT),
        ("smtpd_tls_key_file", SERVER_KEY),
        ("smtpd_tls_protocols", ">=TLSv1.2"),
        ("smtpd_tls_mandatory_protocols", ">=TLSv1.2"),
        ("smtpd_tls_ask_ccert", "yes"),
        ("smtpd_tls_fingerprint_digest", "sha256"),
        ("relay_clientcerts", f"texthash:{CLIENT_CERTS}"),
        ("smtpd_client_restrictions", "permit_mynetworks, reject"),
        ("smtpd_relay_restrictions", "permit_tls_clientcerts, reject"),
        ("smtpd_recipient_restrictions", "permit_tls_clientcerts, reject"),
        # 바깥으로 못 나간 메일은 하루 뒤 끝낸다(반송은 보내는 주소의 메일함으로 간다).
        ("maximal_queue_lifetime", "1d"),
        ("bounce_queue_lifetime", "1d"),
    ]
    if delivery == DELIVERY_SMARTHOST:
        security = smarthost.get("security")
        pairs.append(("relayhost", f"[{smarthost['host']}]:{smarthost['port']}"))
        if security == SECURITY_NONE:
            pairs.append(("smtp_tls_security_level", "none"))
        else:
            pairs += [("smtp_tls_security_level", "encrypt"), ("smtp_tls_CAfile", CA_BUNDLE)]
            if security == SECURITY_SSL:
                pairs.append(("smtp_tls_wrappermode", "yes"))
        if smarthost.get("username"):
            pairs += [
                ("smtp_sasl_auth_enable", "yes"),
                ("smtp_sasl_password_maps", f"texthash:{SASL_PASSWD}"),
                ("smtp_sasl_security_options", "noanonymous"),
                ("smtp_sasl_tls_security_options", "noanonymous"),
            ]
    else:
        pairs += [("smtp_tls_security_level", "may"), ("smtp_tls_CAfile", CA_BUNDLE)]
        if params.get("transport_overrides"):
            pairs.append(("transport_maps", f"texthash:{TRANSPORT_MAP}"))
        if dkim:
            pairs += [
                ("smtpd_milters", f"inet:127.0.0.1:{MILTER_PORT}"),
                ("non_smtpd_milters", "$smtpd_milters"),
                ("milter_default_action", "accept"),
                ("milter_protocol", "6"),
            ]
    return "\n".join(head) + _lines(pairs)


_SERVICE_LINE = re.compile(r"^(?P<name>\S+)\s+(?P<type>\S+)\s+")
OUR_SERVICE = (
    f"{RELAY_HOST}:{RELAY_PORT} inet n       -       y       -       -       smtpd\n"
    "  -o syslog_name=postfix/clovirassist\n"
)


def render_master_cf(proto: str) -> str:
    """패키지의 master.cf.proto 에서 듣는 서비스(`inet`)와 `pickup` 을 걷고 우리 받는 문 하나를 더한다.

    나머지 서비스(qmgr · cleanup · smtp 클라이언트 …)는 그 버전의 꾸러미가 준 그대로다 - 고정 틀로 덮으면 Postfix 가 새 서비스를
    요구하는 날 조용히 깨진다. 걷은 서비스의 `-o` 이어지는 줄도 함께 걷는다.
    """
    out: list[str] = [MARKER + "\n"]
    dropping = False
    for line in proto.splitlines(keepends=True):
        if line[:1].isspace() and line.strip() and not line.lstrip().startswith("#"):
            # 바로 위 서비스의 이어지는 줄(-o …).
            if not dropping:
                out.append(line)
            continue
        dropping = False
        match = _SERVICE_LINE.match(line)
        if match and not line.startswith("#"):
            if match.group("type") == "inet" or match.group("name") == "pickup":
                dropping = True
                continue
        out.append(line if line.endswith("\n") else line + "\n")
    if not out[-1].endswith("\n"):
        out[-1] += "\n"
    out.append("# ClovirAssist 로컬 릴레이의 받는 문: 루프백 2525 하나(D-551).\n")
    out.append(OUR_SERVICE)
    return "".join(out)


def render_client_certs(fingerprints: Iterable[str]) -> str:
    rows = [MARKER]
    for fp in fingerprints:
        if not FINGERPRINT_RE.match(fp):
            raise RelayParamsError("클라이언트 인증서 지문 모양이 올바르지 않습니다.")
        rows.append(f"{fp} clovirassist-app")
    return "\n".join(rows) + "\n"


def render_sasl_passwd(smarthost: Mapping, password: str) -> str:
    """상위 SMTP 로그인 한 줄. 값은 이 파일(root 0600)에만 산다 - 반환값을 로그 · 응답에 싣지 않는다."""
    if not password or "\n" in password or "\r" in password or "\x00" in password:
        raise RelayParamsError("상위 SMTP 비밀번호가 비어 있거나 쓸 수 없는 문자가 들어 있습니다. 비밀번호를 다시 입력하세요.")
    return f"[{smarthost['host']}]:{smarthost['port']} {smarthost['username']}:{password}\n"


def render_transport(overrides: Iterable[Mapping]) -> str:
    rows = [MARKER]
    for item in overrides:
        rows.append(f"{item['domain']} smtp:[{item['host']}]:25")
    return "\n".join(rows) + "\n"


def render_opendkim_conf(dkim: Mapping) -> str:
    """서명 전용 OpenDKIM. 받는 문은 루프백 8891 이고, 키는 opendkim 만 읽는다(`RequireSafeKeys`)."""
    domain, selector = dkim["domain"], dkim["selector"]
    pairs = [
        ("Syslog", "yes"),
        ("SyslogSuccess", "yes"),
        ("LogWhy", "yes"),
        ("Mode", "s"),
        ("Canonicalization", "relaxed/simple"),
        ("OversignHeaders", "From"),
        ("UserID", "opendkim"),
        ("UMask", "007"),
        ("Socket", f"inet:{MILTER_PORT}@127.0.0.1"),
        ("PidFile", "/run/opendkim/opendkim.pid"),
        ("Domain", domain),
        ("Selector", selector),
        ("KeyFile", dkim_key_path(domain, selector)),
        ("RequireSafeKeys", "yes"),
        ("TrustAnchorFile", "/usr/share/dns/root.key"),
    ]
    return MARKER + "\n" + "".join(f"{k}\t{v}\n" for k, v in pairs)


def dkim_key_path(domain: str, selector: str) -> str:
    return f"{OPENDKIM_KEYS}/{domain}/{selector}.private"


def dkim_record_name(domain: str, selector: str) -> str:
    return f"{selector}._domainkey.{domain}"


# ── 표지와 지문 ──────────────────────────────────────────────────────────────


def content_fingerprint(main_cf: str, master_cf: str) -> str:
    return hashlib.sha256((main_cf + "\0" + master_cf).encode("utf-8")).hexdigest()


def render_state(main_cf: str, master_cf: str, *, relay_fingerprint: str) -> str:
    return json.dumps({
        "managed_by": "clovirassist",
        "fingerprint": content_fingerprint(main_cf, master_cf),
        "relay_fingerprint": relay_fingerprint,
    }, ensure_ascii=False, sort_keys=True) + "\n"


def main_cf_state(main_cf: str | None, master_cf: str | None, state_text: str | None) -> str:
    """`absent`(꾸러미만 있음) · `managed`(제품이 만든 그대로) · `foreign`(기존 구성 - 건드리지 않는다)."""
    if main_cf is None:
        return "absent"
    if not main_cf.startswith(MARKER) or state_text is None:
        return "foreign"
    try:
        state = json.loads(state_text)
    except ValueError:
        return "foreign"
    if not isinstance(state, dict) or state.get("fingerprint") != content_fingerprint(main_cf, master_cf or ""):
        return "foreign"
    return "managed"


def applied_relay_fingerprint(state_text: str | None) -> str | None:
    if not state_text:
        return None
    try:
        state = json.loads(state_text)
    except ValueError:
        return None
    value = state.get("relay_fingerprint") if isinstance(state, dict) else None
    return value if isinstance(value, str) else None


def relay_fingerprint(params: Mapping) -> str:
    """적용할 릴레이 설정의 지문 — 화면이 「저장한 설정이 아직 적용되지 않았다」를 말할 때 견준다."""
    return hashlib.sha256(json.dumps(params, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# ── 듣는 소켓 (/proc/net/tcp · tcp6) ──────────────────────────────────────


def _ipv4(hex_addr: str) -> str:
    raw = bytes.fromhex(hex_addr)
    return ".".join(str(b) for b in reversed(raw))


def _ipv6(hex_addr: str) -> str:
    raw = bytes.fromhex(hex_addr)
    words = [raw[i:i + 4][::-1].hex() for i in range(0, 16, 4)]
    full = "".join(words)
    groups = [full[i:i + 4].lstrip("0") or "0" for i in range(0, 32, 4)]
    text = ":".join(groups)
    if text == "0:0:0:0:0:0:0:0":
        return "::"
    if text == "0:0:0:0:0:0:0:1":
        return "::1"
    return text


def parse_listeners(tcp: str | None, tcp6: str | None = None) -> list[str]:
    """듣는(LISTEN, 상태 0A) TCP 소켓 → `주소:포트` 목록. `ss` 를 부르지 않고 커널 표를 읽는다(헬퍼의 실행 파일을 늘리지 않게)."""
    found: list[str] = []
    for text, v6 in ((tcp, False), (tcp6, True)):
        for line in (text or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "0A":
                continue
            addr_hex, _, port_hex = parts[1].partition(":")
            try:
                port = int(port_hex, 16)
                addr = _ipv6(addr_hex) if v6 else _ipv4(addr_hex)
            except ValueError:
                continue
            found.append(f"[{addr}]:{port}" if v6 else f"{addr}:{port}")
    return sorted(set(found))


def listening_on(listeners: Iterable[str], port: int) -> list[str]:
    return [item for item in listeners if item.rsplit(":", 1)[-1] == str(port)]
