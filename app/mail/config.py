"""SMTP 설정 판정 (9-9 P4).

## 한 곳에서만 판정한다

"메일을 보낼 수 있는가" 를 두 벌로 적으면 한쪽만 고쳐지고, 그때 증상은 화면은 "설정됨"
이라고 하는데 워커는 계속 실패하는 상태다. 화면(app/mail/router.py), 진단
(app/health/service.py), 큐잉(app/mail/service.py), 발송(app/jobs/handlers/mail_send.py)
이 전부 이 파일의 ``configuration_problems`` 하나를 부른다.

## 비밀번호는 여기 없고, 칸 이름은 고정이다 (D-545)

DB 설정에는 비밀번호도, 비밀번호 파일의 **이름**도 두지 않는다. 로그인 비밀번호는 언제나 고정 칸
``smtp.password``(`app/core/secret_slots.py`) 하나에서 읽는다. 예전에는 설정의 ``password_ref`` 가 아무
비밀 이름이나 받았다 - 그러면 메일 설정을 바꿀 수 있는 사람이 그 이름을 AI 키나 ChatGPT 토큰 묶음으로 바꾸고
메일 서버 주소를 자기 서버로 돌린 뒤 「연결 확인」을 눌러, 워커가 진짜 비밀로 그 서버에 로그인하게 만들 수
있었다. 이름을 사용자 데이터에서 빼야 그 길이 닫힌다(옛 값은 0042 가 걷고, 설치기가 옛 파일을 고정 칸으로
옮긴다). 이 모듈은 **secret 제공자를 받을 때만** 비밀번호 문제를 말할 수 있고, 받지 못하면(예: 잡 큐잉처럼
app.state 가 없는 자리) 그 항목은 검사하지 않는다 - 그 경우 문제는 발송 시점에 ``mail_deliveries.last_error``
로 드러난다.

## '문제 목록' 이 불리언보다 중요한 이유

``configured: false`` 만 주면 운영자는 무엇을 채워야 하는지 모른다. 화면에 그대로 띄울 수
있는 한국어 문장을 준다 - 이 저장소가 tenant_config 의 ``when_unset`` 에서 쓴 것과 같은
방식이다.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.core.secret_slots import SLOT_SMTP_PASSWORD, SLOT_SMTP_RELAY_CLIENT, SLOT_SMTP_RELAY_PASSWORD

SMTP_SETTING_KEY = "smtp"

SECURITY_NONE = "none"
SECURITY_STARTTLS = "starttls"
SECURITY_SSL = "ssl"
ALL_SECURITY_MODES = (SECURITY_NONE, SECURITY_STARTTLS, SECURITY_SSL)

# 보내는 방법(D-551). 「외부 SMTP 사용」이 기본이고 지금까지의 동작이다. 「ClovirAssist 로컬 릴레이」는 이 서버에 함께 설치된 발송 전용
# 구성 요소로 보내고, 그 안에서 「상위 SMTP 이용」 · 「인터넷으로 직접 전달(고급)」을 고른다.
MODE_EXTERNAL = "external"
MODE_LOCAL_RELAY = "local_relay"
ALL_MODES = (MODE_EXTERNAL, MODE_LOCAL_RELAY)
DELIVERY_SMARTHOST = "smarthost"
DELIVERY_DIRECT = "direct"
ALL_DELIVERIES = (DELIVERY_SMARTHOST, DELIVERY_DIRECT)

# 로컬 릴레이 설정. 외부 SMTP 칸 값은 되돌아갈 때를 위해 그대로 남는다. `dkim_public` 은 사람이 넣지 않는다 - 키를 만들 때 헬퍼가
# 돌려준 공개키를 서버가 적는다(준비 점검이 DNS 의 값과 견준다).
DEFAULT_RELAY: dict[str, Any] = {
    "delivery": DELIVERY_SMARTHOST,
    "smarthost": {"host": "", "port": 587, "security": SECURITY_STARTTLS, "username": ""},
    "helo_name": "",
    "public_ip": "",
    "ipv4_only": False,
    "dkim_enabled": False,
    "dkim_selector": "",
    "dkim_public": "",
    "transport_overrides": [],
    "compare_resolvers": [],
}

# 기본값에 설치처 고유값(호스트, 도메인)을 넣지 않는다 - scripts/check_tenant_defaults.py
# 가 막는 것과 같은 종류의 사고다(다른 고객사 설치가 조용히 남의 서버를 가리킨다).
DEFAULT_SMTP: dict[str, Any] = {
    "enabled": False,
    "host": "",
    "port": 587,
    "security": SECURITY_STARTTLS,
    "from_address": "",
    "from_name": "",
    "username": "",
    "timeout_seconds": 20,
    # 서버 인증서를 확인한다(계획 3.3). 예전에는 `starttls()` · `SMTP_SSL` 에 문맥을 안 줘서 인증서와 호스트
    # 이름을 전혀 보지 않았다. 사설 CA 를 쓰는 내부 릴레이는 `ca_pem` 에 그 CA 를 붙여 넣는다.
    "tls_verify": True,
    "ca_pem": "",
    "mode": MODE_EXTERNAL,
    "relay": copy.deepcopy(DEFAULT_RELAY),
}

# 로그인 비밀번호를 읽는 유일한 칸(D-545). 이름은 슬롯 표 한 곳에만 적는다.
PASSWORD_SLOT = SLOT_SMTP_PASSWORD
CA_PEM_MAX_CHARS = 20480


@dataclass(frozen=True)
class SmarthostConfig:
    host: str = ""
    port: int = 587
    security: str = SECURITY_STARTTLS
    username: str = ""


@dataclass(frozen=True)
class RelayConfig:
    """로컬 릴레이 설정(D-551). 비밀(상위 SMTP 비밀번호 · 앱 열쇠)은 담지 않는다."""

    delivery: str = DELIVERY_SMARTHOST
    smarthost: SmarthostConfig = field(default_factory=SmarthostConfig)
    helo_name: str = ""
    public_ip: str = ""
    ipv4_only: bool = False
    dkim_enabled: bool = False
    dkim_selector: str = ""
    dkim_public: str = ""
    transport_overrides: tuple[tuple[str, str], ...] = ()
    compare_resolvers: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "delivery": self.delivery,
            "smarthost": {"host": self.smarthost.host, "port": self.smarthost.port,
                          "security": self.smarthost.security, "username": self.smarthost.username},
            "helo_name": self.helo_name, "public_ip": self.public_ip, "ipv4_only": self.ipv4_only,
            "dkim_enabled": self.dkim_enabled, "dkim_selector": self.dkim_selector, "dkim_public": self.dkim_public,
            "transport_overrides": [{"domain": d, "host": h} for d, h in self.transport_overrides],
            "compare_resolvers": list(self.compare_resolvers),
        }


def relay_config(raw: Any) -> RelayConfig:
    """설정 값의 `relay` → RelayConfig. 모양이 이상한 칸은 기본값으로 떨어진다(`smtp_config` 와 같은 원칙)."""
    values = copy.deepcopy(DEFAULT_RELAY)
    if isinstance(raw, dict):
        for key in values:
            if key in raw:
                values[key] = raw[key]
    sh = values["smarthost"] if isinstance(values["smarthost"], dict) else {}
    port = sh.get("port", 587)
    overrides = []
    for item in values["transport_overrides"] if isinstance(values["transport_overrides"], list) else []:
        if isinstance(item, dict) and item.get("domain") and item.get("host"):
            overrides.append((str(item["domain"]).strip().lower(), str(item["host"]).strip().lower()))
    resolvers = values["compare_resolvers"] if isinstance(values["compare_resolvers"], list) else []
    return RelayConfig(
        delivery=values["delivery"] if values["delivery"] in ALL_DELIVERIES else DELIVERY_SMARTHOST,
        smarthost=SmarthostConfig(
            host=str(sh.get("host") or "").strip().lower(),
            port=port if isinstance(port, int) and not isinstance(port, bool) else 587,
            security=sh.get("security") if sh.get("security") in ALL_SECURITY_MODES else SECURITY_STARTTLS,
            username=str(sh.get("username") or "").strip(),
        ),
        helo_name=str(values["helo_name"] or "").strip().lower(),
        public_ip=str(values["public_ip"] or "").strip(),
        ipv4_only=values["ipv4_only"] is True,
        dkim_enabled=values["dkim_enabled"] is True,
        dkim_selector=str(values["dkim_selector"] or "").strip().lower(),
        dkim_public=str(values["dkim_public"] or "").strip(),
        transport_overrides=tuple(overrides),
        compare_resolvers=tuple(str(r).strip() for r in resolvers if str(r).strip()),
    )


@dataclass(frozen=True)
class MailConfig:
    """지금 적용 중인 SMTP 설정. **비밀번호 값은 담지 않는다.**"""

    enabled: bool
    host: str
    port: int
    security: str
    from_address: str
    from_name: str
    username: str
    timeout_seconds: int
    tls_verify: bool = True
    ca_pem: str = ""
    mode: str = MODE_EXTERNAL
    relay: RelayConfig = field(default_factory=RelayConfig)

    @property
    def local_relay(self) -> bool:
        return self.mode == MODE_LOCAL_RELAY

    @property
    def relay_fingerprint(self) -> str:
        """로컬 릴레이 설정의 지문(건강 상태의 지문에 들어간다). 외부 SMTP 면 비어 있다."""
        if not self.local_relay:
            return ""
        return hashlib.sha256(json.dumps(self.relay.as_dict(), sort_keys=True).encode("utf-8")).hexdigest()

    @property
    def sender_domain(self) -> str:
        return self.from_address.rsplit("@", 1)[-1].lower() if "@" in self.from_address else ""

    @property
    def ehlo_name(self) -> str:
        """외부 SMTP 로 인사(EHLO)할 이름(D-572) - 설정의 서버 이름(HELO)이 도메인 모양일 때만. 비면 smtplib 기본값(이 서버의 FQDN)이다."""
        from app.mail.relay_files import DOMAIN_RE

        name = self.relay.helo_name
        return name if name and DOMAIN_RE.match(name) else ""

    def public_view(self) -> dict:
        """화면에 그대로 내보내도 되는 모양. 비밀번호도, 비밀번호 칸의 이름도 싣지 않는다."""
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "security": self.security,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "username": self.username,
            "timeout_seconds": self.timeout_seconds,
            "tls_verify": self.tls_verify,
            # 인증서 원문은 비밀이 아니지만 길다(최대 20KB). 상태 화면은 붙어 있는지만 알면 된다.
            "ca_pem_set": bool(self.ca_pem),
            "mode": self.mode,
            "relay": self.relay.as_dict(),
        }


def smtp_config(raw: Any) -> MailConfig:
    """설정 값(dict)을 MailConfig 로. 모양이 이상하면 기본값으로 떨어진다.

    떨어뜨리는 쪽이 안전하다: 기본값은 ``enabled=False`` 라 '못 보낸다' 로 귀결되고,
    그 사실은 ``configuration_problems`` 가 말한다. 반대로 예외를 던지면 설정 한 줄이
    깨졌다는 이유로 로그인 화면 렌더가 통째로 죽는다.
    """
    values = dict(DEFAULT_SMTP)
    if isinstance(raw, dict):
        for key in values:
            if key in raw:
                values[key] = raw[key]
    return MailConfig(
        enabled=bool(values["enabled"]),
        host=str(values["host"] or "").strip(),
        port=int(values["port"] or 0) if str(values["port"]).isdigit() else 0,
        security=str(values["security"] or SECURITY_STARTTLS).strip(),
        from_address=str(values["from_address"] or "").strip(),
        from_name=str(values["from_name"] or "").strip(),
        username=str(values["username"] or "").strip(),
        timeout_seconds=(
            int(values["timeout_seconds"])
            if str(values["timeout_seconds"]).strip().isdigit()
            else 20
        ),
        # 모르는 값은 확인하는 쪽으로 떨어진다 - 확인을 끄는 것은 명시적인 선택이어야 한다.
        tls_verify=values["tls_verify"] is not False,
        ca_pem=str(values["ca_pem"] or "").strip(),
        mode=values["mode"] if values["mode"] in ALL_MODES else MODE_EXTERNAL,
        relay=relay_config(values["relay"]),
    )


def helper_params(config: MailConfig) -> dict:
    """특권 헬퍼 `mailrelay.apply` 의 인자 — 저장된 설정에서만 만든다(사람이 인자를 직접 고르지 않는다).
    헬퍼가 `app/mail/relay_files.py::normalize_params` 로 다시 검사한다."""
    relay = config.relay
    params: dict[str, Any] = {
        "delivery": relay.delivery,
        "sender_domain": config.sender_domain,
        "helo_name": relay.helo_name,
        "ipv4_only": relay.ipv4_only,
    }
    if relay.delivery == DELIVERY_SMARTHOST:
        params["smarthost"] = {"host": relay.smarthost.host, "port": relay.smarthost.port,
                               "security": relay.smarthost.security, "username": relay.smarthost.username}
    else:
        params["dkim"] = {"selector": relay.dkim_selector} if relay.dkim_enabled else None
        params["transport_overrides"] = [{"domain": d, "host": h} for d, h in relay.transport_overrides]
    return params


def relay_server_cert() -> str | None:
    """로컬 릴레이의 서버 인증서(공개) - 앱이 이것 하나만 믿는다(고정). 없으면 릴레이가 아직 켜진 적이 없다."""
    from pathlib import Path

    from app.mail import relay_files

    try:
        return Path(relay_files.SERVER_CERT).read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError):
        return None


def config_from_db(db) -> MailConfig:
    """DB 설정 행에서 직접 읽는다.

    ``app.state.settings_cache`` 가 없는 자리(승인 생성, 예약 백업처럼 서비스 계층 깊은
    곳)를 위한 문이다. 캐시가 있으면 ``smtp_config(cache.current_value(...))`` 를 쓰는
    쪽이 낫다 - 질의가 없다.
    """
    from app.settings.models import AppSetting

    row = db.get(AppSetting, SMTP_SETTING_KEY)
    if row is None:
        return smtp_config(None)
    try:
        return smtp_config(json.loads(row.value_json))
    except (ValueError, TypeError):
        return smtp_config(None)


def config_from_cache(settings_cache) -> MailConfig:
    if settings_cache is None:
        return smtp_config(None)
    try:
        return smtp_config(settings_cache.current_value(SMTP_SETTING_KEY))
    except (ValueError, TypeError):
        # smtp_config 자체는 예외를 던지지 않는 게 계약이지만(모듈 docstring), 캐시에
        # registry.py 검증을 거치지 않은 값(레거시 행, 수동 DB 편집)이 들어와 있을 수
        # 있다 - config_from_db 와 같은 방어를 여기도 준다.
        return smtp_config(None)


def configuration_problems(config: MailConfig, secret_provider=None) -> list[str]:
    """왜 못 보내는가. 빈 목록이면 보낼 수 있다.

    ``secret_provider`` 를 주면 비밀번호 secret 파일 존재까지 본다. 안 주면 그 항목은
    검사하지 않는다(모듈 docstring 참조).

    ## 문장에 내부 이름을 쓰지 않는 이유 (지시 35 · 36)

    이 문장들은 관리 화면과 진단에 **그대로** 나간다. `smtp.enabled`, `(host)`,
    `(from_address)`, `password_ref` 는 설정 JSON 의 필드 이름이지 사람이 화면에서 찾는
    이름이 아니다. 고쳐야 할 자리는 같은 화면의 설정 폼이고, 그 폼은 이미 한국어 라벨을
    쓴다 - 그러니 문장이 필드 이름을 가르칠 필요가 없다.

    비밀번호 칸은 하나로 고정이라(D-545) 「어느 파일이냐」를 화면에 알릴 필요가 없다. 비밀번호가 없으면
    같은 화면의 비밀번호 칸에 넣으면 된다.
    """
    problems: list[str] = []
    if not config.enabled:
        problems.append("메일 발송이 꺼져 있습니다. 메일 설정에서 발송을 켜세요.")
    if config.local_relay:
        return problems + _relay_problems(config, secret_provider)
    if not config.host:
        problems.append("메일 서버 주소가 비어 있습니다.")
    if not (0 < config.port < 65536):
        problems.append("메일 서버 포트가 올바르지 않습니다.")
    if config.security not in ALL_SECURITY_MODES:
        problems.append(
            "보안 연결 방식이 올바르지 않습니다. 사용 안 함, STARTTLS, SSL 중에서 고르세요."
        )
    if not config.from_address:
        problems.append("보내는 사람 주소가 비어 있습니다.")
    if config.username and secret_provider is not None:
        from app.core.secret_refs import STATUS_CONFIGURED

        if secret_provider.status(PASSWORD_SLOT) != STATUS_CONFIGURED:
            problems.append("로그인 계정의 비밀번호가 저장되지 않았습니다. 메일 설정에서 비밀번호를 저장하세요.")
    return problems


def _relay_problems(config: MailConfig, secret_provider) -> list[str]:
    """로컬 릴레이 방식의 「보낼 수 없는 까닭」. 받는 문(127.0.0.1:2525)은 고정이라 사람이 채울 칸이 아니다."""
    from app.core.secret_refs import STATUS_CONFIGURED

    problems: list[str] = []
    relay = config.relay
    if not config.from_address:
        problems.append("보내는 사람 주소가 비어 있습니다.")
    if relay.delivery == DELIVERY_SMARTHOST:
        if not relay.smarthost.host:
            problems.append("상위 SMTP 서버 주소가 비어 있습니다.")
        if relay.smarthost.username and secret_provider is not None \
                and secret_provider.status(SLOT_SMTP_RELAY_PASSWORD) != STATUS_CONFIGURED:
            problems.append("상위 SMTP 계정의 비밀번호가 저장되지 않았습니다. 메일 설정에서 비밀번호를 저장하세요.")
    elif not relay.helo_name:
        problems.append("인터넷으로 직접 전달하려면 서버 이름(HELO)이 필요합니다.")
    if secret_provider is not None and (
        secret_provider.status(SLOT_SMTP_RELAY_CLIENT) != STATUS_CONFIGURED or relay_server_cert() is None
    ):
        problems.append("로컬 릴레이가 아직 켜지지 않았습니다. 메일 설정에서 로컬 릴레이를 켜세요.")
    return problems


def is_sendable(config: MailConfig, secret_provider=None) -> bool:
    return not configuration_problems(config, secret_provider)


def mail_status(config: MailConfig, secret_provider=None) -> dict:
    """화면과 진단이 함께 쓰는 한 덩어리. **비밀 값은 절대 안 들어간다.**"""
    problems = configuration_problems(config, secret_provider)
    return {
        "configured": not problems,
        "problems": problems,
        "server": config.public_view(),
        "password_secret": (
            None
            if not config.username or secret_provider is None
            else secret_provider.status(PASSWORD_SLOT)
        ),
    }
