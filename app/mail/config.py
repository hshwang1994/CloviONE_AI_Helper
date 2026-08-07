"""SMTP 설정 판정 (9-9 P4).

## 한 곳에서만 판정한다

"메일을 보낼 수 있는가" 를 두 벌로 적으면 한쪽만 고쳐지고, 그때 증상은 화면은 "설정됨"
이라고 하는데 워커는 계속 실패하는 상태다. 화면(app/mail/router.py), 진단
(app/health/service.py), 큐잉(app/mail/service.py), 발송(app/jobs/handlers/mail_send.py)
이 전부 이 파일의 ``configuration_problems`` 하나를 부른다.

## 비밀번호는 여기 없다

DB 설정에는 ``password_ref``(이름)만 둔다. 실제 값은 ``SECRETS_DIR/<ref>`` 파일이다
(불변 §3). 그래서 이 모듈은 **secret 제공자를 받을 때만** 비밀번호 문제를 말할 수 있고,
받지 못하면(예: 잡 큐잉처럼 app.state 가 없는 자리) 그 항목은 검사하지 않는다 - 그 경우
문제는 발송 시점에 ``mail_deliveries.last_error`` 로 드러난다.

## '문제 목록' 이 불리언보다 중요한 이유

``configured: false`` 만 주면 운영자는 무엇을 채워야 하는지 모른다. 화면에 그대로 띄울 수
있는 한국어 문장을 준다 - 이 저장소가 tenant_config 의 ``when_unset`` 에서 쓴 것과 같은
방식이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SMTP_SETTING_KEY = "smtp"

SECURITY_NONE = "none"
SECURITY_STARTTLS = "starttls"
SECURITY_SSL = "ssl"
ALL_SECURITY_MODES = (SECURITY_NONE, SECURITY_STARTTLS, SECURITY_SSL)

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
    "password_ref": "",
    "timeout_seconds": 20,
}


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
    password_ref: str
    timeout_seconds: int

    @property
    def from_header(self) -> str:
        """``이름 <주소>`` 형태. 이름이 없으면 주소만."""
        if self.from_name:
            return f"{self.from_name} <{self.from_address}>"
        return self.from_address

    def public_view(self) -> dict:
        """화면에 그대로 내보내도 되는 모양. 비밀번호는 **이름조차** 값이 아니다."""
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "security": self.security,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "username": self.username,
            "password_ref": self.password_ref,
            "timeout_seconds": self.timeout_seconds,
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
        password_ref=str(values["password_ref"] or "").strip(),
        timeout_seconds=(
            int(values["timeout_seconds"])
            if str(values["timeout_seconds"]).strip().isdigit()
            else 20
        ),
    )


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
    """
    problems: list[str] = []
    if not config.enabled:
        problems.append("메일 발송이 꺼져 있습니다. 설정에서 smtp.enabled 를 켜세요.")
    if not config.host:
        problems.append("SMTP 서버 주소(host)가 비어 있습니다.")
    if not (0 < config.port < 65536):
        problems.append("SMTP 포트가 올바르지 않습니다.")
    if config.security not in ALL_SECURITY_MODES:
        problems.append(
            "SMTP 보안 방식은 none, starttls, ssl 중 하나여야 합니다."
        )
    if not config.from_address:
        problems.append("보내는 사람 주소(from_address)가 비어 있습니다.")
    if config.username and not config.password_ref:
        problems.append(
            "SMTP 사용자 이름이 있는데 비밀번호 secret 이름(password_ref)이 비어 있습니다."
        )
    if config.password_ref and secret_provider is not None:
        from app.core.secret_refs import STATUS_CONFIGURED

        if secret_provider.status(config.password_ref) != STATUS_CONFIGURED:
            problems.append(
                f"SMTP 비밀번호 secret 파일이 서버에 없습니다: {config.password_ref}"
            )
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
            if not config.password_ref or secret_provider is None
            else secret_provider.status(config.password_ref)
        ),
    }
