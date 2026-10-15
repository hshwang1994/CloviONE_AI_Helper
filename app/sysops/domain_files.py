"""대표 도메인 전환의 순수 함수 (계획 M3, D-573).

파일도 프로세스도 건드리지 않는다. 헬퍼 액션(`actions_domain.py`)이 읽은 글을 여기로 넘겨 해석하고, 쓸 글을 여기서 만든다 —
그래서 Windows 개발 머신에서 그대로 시험된다(`tests/unit/test_domain_files.py`).

정본 파일 셋의 **글 모양**이 이 모듈의 계약이다(D-c: 서비스 주소의 정본은 env 파일 + 설치 매니페스트이고, 쓰는 쪽은 설치기와
`domain.apply` 둘뿐이다).
- env 파일(`/etc/clovirassist/clovirassist.env`): `KEY=value` 한 줄씩. 설치기의 `env_set` 과 같은 규칙으로 바꾼다 — 있으면 그 줄을
  갈아 끼우고 없으면 끝에 붙인다.
- 설치 매니페스트(`installed_manifest.json`): 설치기가 `printf` 로 쓰는 JSON. 설치기의 `jq_get` 은 `"key": "value"` 가 **한 줄에**
  있어야 읽으므로, 여기서 다시 쓸 때도 키 하나가 한 줄이고 목록 · 객체는 한 줄로 접는다.
  🔴 이미 깔린 매니페스트는 엄격한 JSON 이 아닐 수 있다 — 랩의 것은 `"version": "0.1.0-dev\r"` 처럼 문자열 안에 날 CR 이 들어 있다
  (Windows 체크아웃에서 `git archive` 로 보낸 `VERSION` 이 CRLF 였고, 설치기의 `json_str` 이 CR 을 이스케이프하지 않았다).
  그래서 읽을 때는 `strict=False` 로 받고 문자열 값의 제어 문자를 걷는다. 다시 쓸 때는 `json.dumps` 라 언제나 엄격한 JSON 이다.
- nginx vhost: 저장소 템플릿(`deploy/nginx/clovirassist.conf`)의 `__BIND_IP__` · `__SERVER_NAMES__` · `__DNS_NAME__` 을 치환한다.
  설치기 Stage 16 과 같은 자리 표시자다. 치환이 남으면 잘못된 vhost 를 nginx 에 물리지 않고 여기서 거절한다.
"""

from __future__ import annotations

import json
import re
import ssl
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core import product

MANIFEST_FILE = f"{product.ETC_DIR}/installed_manifest.json"
TEMPLATE_FILE = f"{product.APP_DIR}/deploy/nginx/{product.SLUG}.conf"
SITE_AVAILABLE = f"/etc/nginx/sites-available/{product.NGINX_SITE}"
SITE_ENABLED = f"/etc/nginx/sites-enabled/{product.NGINX_SITE}"

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_SAN_ENTRY = re.compile(r"(DNS|IP Address|IP):\s*([^,\s]+)")
_SERVER_NAME_LINE = re.compile(r"^\s*server_name\s+([^;]+);", re.M)
_CONFIG_HEADER = re.compile(r"^# configuration file (.+?):\s*$", re.M)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TEMPLATE_SERVER_NAMES = re.compile(r"^\s*server_name\s+__SERVER_NAMES__\s*;", re.M)
PLACEHOLDERS = ("__BIND_IP__", "__SERVER_NAMES__", "__DNS_NAME__")
MAX_ALIASES = 5


# ── env 파일 ─────────────────────────────────────────────────────────────────


def env_get(text: str | None, key: str) -> str | None:
    """`KEY=value` 의 값. 같은 키가 여러 줄이면 **마지막** 줄이다(설치기의 `do_verify` 가 `tail -1` 로 읽는 것과 같다)."""
    value: str | None = None
    for line in (text or "").splitlines():
        m = _ENV_LINE.match(line.strip())
        if m and m.group(1) == key:
            value = m.group(2).strip()
    if value is None:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def env_set(text: str | None, key: str, value: str) -> str:
    """설치기 `env_set` 과 같은 규칙. 있으면 그 줄을 바꾸고(중복 줄은 하나로 접는다) 없으면 끝에 붙인다. 다른 줄은 손대지 않는다."""
    out: list[str] = []
    done = False
    for line in (text or "").splitlines():
        m = _ENV_LINE.match(line.strip())
        if m and m.group(1) == key:
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


def host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        return None
    return host.lower() if host else None


# ── 매니페스트 ────────────────────────────────────────────────────────────────


def _clean(value: object) -> object:
    """문자열 값의 제어 문자(날 CR 등)를 걷는다. 목록 · 객체는 안으로 들어간다."""
    if isinstance(value, str):
        return _CONTROL.sub("", value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def parse_manifest(text: str | None) -> dict:
    """설치 매니페스트. 없거나 깨졌으면 빈 dict — 읽는 쪽이 「없다」를 따로 판정한다.

    `strict=False` 는 문자열 안의 날 제어 문자를 받아들인다(머리말의 랩 사례). 받은 뒤에는 그 문자를 걷어 낸 값을 돌려준다 —
    `version` 끝의 CR 이 화면이나 다음 매니페스트로 옮겨 가지 않는다."""
    if not text:
        return {}
    try:
        data = json.loads(text, strict=False)
    except ValueError:
        return {}
    return _clean(data) if isinstance(data, dict) else {}


def dump_manifest(data: dict) -> str:
    """설치기가 쓰는 모양 그대로 — 키 하나가 한 줄, 목록 · 객체는 한 줄로 접는다(`jq_get` 의 한 줄 정규식이 읽을 수 있게).
    값은 `json.dumps` 를 지나므로 제어 문자가 남아 있어도 이스케이프된다 — 결과는 언제나 엄격한 JSON 이다."""
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        lines.append(f"  {json.dumps(str(key), ensure_ascii=False)}: {rendered}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


def split_names(value: object) -> list[str]:
    """`a,b` 또는 `a b` → 소문자 목록. 빈 칸과 중복은 버린다(설치기의 `ALIAS_NAMES` · `UPSTREAM_PROXIES` 와 같은 쉼표 모양)."""
    if isinstance(value, (list, tuple)):
        raw = ",".join(str(v) for v in value)
    else:
        raw = str(value or "")
    out: list[str] = []
    for part in raw.replace(" ", ",").split(","):
        item = part.strip().lower()
        if item and item not in out:
            out.append(item)
    return out


def join_names(names: list[str]) -> str:
    return ",".join(names)


def normalize_aliases(host: str, aliases: list[str], *, limit: int = MAX_ALIASES) -> list[str]:
    """대표 이름을 뺀 별칭 목록. 중복을 접고 상한을 넘으면 거절한다 — `server_name` 한 줄이 끝없이 길어지지 않게."""
    out: list[str] = []
    for alias in aliases:
        item = alias.strip().lower().rstrip(".")
        if not item or item == host or item in out:
            continue
        out.append(item)
    if len(out) > limit:
        raise ValueError(f"함께 쓰는 주소는 최대 {limit}개까지입니다(지금 {len(out)}개).")
    return out


# ── 인증서 ────────────────────────────────────────────────────────────────────


def cert_paths(tls_dir: str, host: str) -> tuple[str, str]:
    """설치기 Stage 15 와 nginx 템플릿의 관례 — 같은 디렉터리, 이름이 곧 파일 이름, 확장자만 `.crt`/`.key`."""
    return f"{tls_dir}/{host}.crt", f"{tls_dir}/{host}.key"


def key_path_for(cert_path: str) -> str:
    """인증서 옆 개인키 — 같은 디렉터리 · 같은 이름 · 확장자만 `.key`(`actions_service._resolve_tls_paths_for` 와 같은 관례)."""
    head, _, _ext = cert_path.rpartition(".")
    return f"{head}.key" if head else f"{cert_path}.key"


def parse_san(text: str | None) -> dict:
    """`openssl x509 -ext subjectAltName` 출력의 `DNS:` · `IP Address:` 항목."""
    dns: list[str] = []
    ips: list[str] = []
    for kind, value in _SAN_ENTRY.findall(text or ""):
        item = value.strip().lower()
        target = dns if kind == "DNS" else ips
        if item and item not in target:
            target.append(item)
    return {"dns": dns, "ip": ips}


def parse_x509(text: str | None) -> dict:
    """`openssl x509 -noout -subject -issuer -enddate -ext subjectAltName` 출력 한 덩어리 → subject · issuer · 만료(ISO, UTC) · SAN ·
    자체 서명 여부(issuer == subject)."""
    subject = issuer = not_after_raw = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("subject="):
            subject = stripped[len("subject="):].strip()
        elif stripped.startswith("issuer="):
            issuer = stripped[len("issuer="):].strip()
        elif stripped.startswith("notAfter="):
            not_after_raw = stripped[len("notAfter="):].strip()
    not_after = None
    if not_after_raw:
        try:
            not_after = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after_raw), tz=timezone.utc).isoformat()
        except ValueError:
            not_after = None
    san = parse_san(text)
    self_signed = (subject == issuer) if subject and issuer else None
    return {"subject": subject, "issuer": issuer, "not_after": not_after, "not_after_raw": not_after_raw,
            "san": san, "self_signed": self_signed}


def missing_names(san: dict | None, names: list[str]) -> list[str]:
    have = {n.lower() for n in (san or {}).get("dns", [])}
    return [n for n in names if n.lower() not in have]


def self_signed_argv(openssl: str, *, crt: str, key: str, host: str, names: list[str], bind_ip: str,
                     days: int = 365) -> list[str]:
    """설치기 Stage 15 와 **같은 openssl 호출**(ECDSA P-256 · 365일 · CN=대표 이름 · SAN=이름 전부 + IP). 설치처와 헬퍼가 어긋나지
    않게 이 모양을 유지한다."""
    dns = list(dict.fromkeys([host, *names]))
    entries = [f"DNS:{n}" for n in dns] + ([f"IP:{bind_ip}"] if bind_ip else [])
    return [openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
            "-keyout", key, "-out", crt, "-days", str(days), "-nodes",
            "-subj", f"/CN={host}", "-addext", f"subjectAltName={','.join(entries)}"]


# ── nginx ─────────────────────────────────────────────────────────────────────


def template_supports_aliases(template: str | None) -> bool:
    """설치된 vhost 틀이 별칭 자리(`server_name __SERVER_NAMES__;`)를 가진 새 틀인가. 옛 틀이면 별칭을 넣을 곳이 없다."""
    return bool(template) and bool(_TEMPLATE_SERVER_NAMES.search(template))


def render_vhost(template: str, bind_ip: str, dns_name: str, server_names: list[str]) -> str:
    """템플릿의 자리 표시자를 설치처 값으로 치환한다. `server_name` 은 대표 이름 뒤에 별칭이 선다. 인증서 경로는 대표 이름(`__DNS_NAME__`)
    그대로다. 치환이 남거나 템플릿에 `server_name __SERVER_NAMES__;` 자리가 없으면 거절한다 — `nginx -t` 는 그것을 못 잡는다."""
    if not template_supports_aliases(template):
        raise ValueError("vhost 템플릿에 __SERVER_NAMES__ 자리가 없습니다. 설치 자산이 옛 버전입니다.")
    if not bind_ip or not dns_name:
        raise ValueError("vhost 를 만들 주소나 이름이 비어 있습니다.")
    names = " ".join(dict.fromkeys([dns_name, *server_names]))
    out = (template.replace("__BIND_IP__", bind_ip)
           .replace("__SERVER_NAMES__", names)
           .replace("__DNS_NAME__", dns_name))
    left = [p for p in PLACEHOLDERS if p in out]
    if left:
        raise ValueError(f"vhost 템플릿 치환이 남았습니다: {', '.join(left)}")
    return out


def parse_server_names(text: str | None) -> list[str]:
    """설정 글 안의 모든 `server_name` 줄에 선 이름(소문자, 순서 유지, 중복 제거). 주석 줄은 줄머리가 `#` 라 걸리지 않는다."""
    out: list[str] = []
    for line in _SERVER_NAME_LINE.findall(text or ""):
        for name in line.split():
            item = name.strip().lower()
            if item and item not in out:
                out.append(item)
    return out


def nginx_sections(text: str | None) -> dict[str, str]:
    """`nginx -T` 출력 → {설정 파일 경로: 그 파일의 글}. 출력은 파일마다 `# configuration file <경로>:` 머리로 시작한다."""
    body = text or ""
    heads = list(_CONFIG_HEADER.finditer(body))
    out: dict[str, str] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        out[m.group(1).strip()] = body[m.end():end]
    return out


def is_own_site(path: str) -> bool:
    """이 제품의 vhost 인가 — sites-enabled 의 연결이든 sites-available 의 원본이든."""
    return path in (SITE_ENABLED, SITE_AVAILABLE)


def site_server_names(text: str | None) -> list[str]:
    """`nginx -T` 출력에서 **이 제품 vhost** 의 server_name 들. vhost 가 nginx 에 실려 있지 않으면 빈 목록이다."""
    names: list[str] = []
    for path, body in nginx_sections(text).items():
        if is_own_site(path):
            for name in parse_server_names(body):
                if name not in names:
                    names.append(name)
    return names


def name_conflicts(text: str | None, names: list[str]) -> list[tuple[str, str]]:
    """다른 설정 파일이 같은 이름을 `server_name` 에 들고 있는가 — (경로, 이름) 목록.

    같은 이름을 두 server 블록이 들면 nginx 는 경고만 내고 **먼저 읽은 쪽이 조용히 이긴다**(설치기 Stage 16 의 「블록 둘」 단언과 같은
    까닭). 그러면 적용은 성공한 듯 보이는데 그 이름의 요청은 다른 서비스가 받는다."""
    wanted = {n.lower() for n in names}
    out: list[tuple[str, str]] = []
    for path, body in nginx_sections(text).items():
        if is_own_site(path):
            continue
        for name in parse_server_names(body):
            if name in wanted:
                out.append((path, name))
    return out
