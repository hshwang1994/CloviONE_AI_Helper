"""Allowlisted editable settings (spec §14.4).

Only keys defined here can be changed via the API — the "허용 목록 방식"
(allowlist) required by spec §0.2. Each entry declares a type, a validator,
whether a restart is needed, and a default. System files are never exposed;
Secrets are never stored plaintext (spec §25.4) — none of these are secret.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from app.core.errors import ValidationAppError


@dataclass(frozen=True)
class SettingSpec:
    key: str
    value_type: str  # "string" | "int" | "bool" | "object"
    default: Any
    restart_required: bool
    description: str
    validate: Callable[[Any], None] | None = None


def _interval_seconds(value: Any) -> None:
    """동기화 주기(초). `0` 은 "서버 기본값을 따른다" 는 센티널이다.

    하한 60초: 노션 API 에는 속도 제한이 있고, 그보다 촘촘하게 돌면 미러가 빨라지는 게
    아니라 429 로 실패하기 시작한다. 상한 24시간: 그보다 길면 '주기 동기화'라고 부를 수
    없고, 그런 설치는 자동 동기화를 끄는 편이 정직하다.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationAppError("정수여야 합니다.")
    if value == 0:
        return
    if value < 60 or value > 86400:
        raise ValidationAppError("0(서버 기본값) 또는 60~86400 사이의 정수여야 합니다.")


def _positive_int(max_value: int):
    def _v(value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > max_value:
            raise ValidationAppError(f"1~{max_value} 사이의 정수여야 합니다.")
    return _v


def _non_empty_str(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationAppError("비어 있지 않은 문자열이어야 합니다.")


def _bool(value: Any) -> None:
    if not isinstance(value, bool):
        raise ValidationAppError("true 또는 false여야 합니다.")


def _password_policy(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    min_len = value.get("min_length")
    if not isinstance(min_len, int) or min_len < 8 or min_len > 128:
        raise ValidationAppError("min_length는 8~128 정수여야 합니다.")
    # Only 4 character classes exist — an impossible min_classes would lock out
    # every password change.
    min_classes = value.get("min_classes", 3)
    if not isinstance(min_classes, int) or min_classes < 1 or min_classes > 4:
        raise ValidationAppError("min_classes는 1~4 정수여야 합니다.")


def _session_policy(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    for k in ("idle_timeout_seconds", "absolute_timeout_seconds"):
        v = value.get(k)
        if not isinstance(v, int) or v < 60:
            raise ValidationAppError(f"{k}는 60 이상 정수여야 합니다.")


def _lockout_policy(value: Any) -> None:
    """ADM-05: 계정 잠금 정책(로그인 실패 임계값·잠금 시간)이 예전엔 env 전용이라 화면에서
    보지도 바꾸지도 못했다 — session_policy가 이미 쓰는 "env 기본값 + DB override" 모양을
    그대로 따른다(app/auth/router.py::_effective_lockout_policy)."""
    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    max_failures = value.get("max_failures")
    if not isinstance(max_failures, int) or isinstance(max_failures, bool) or not (1 <= max_failures <= 20):
        raise ValidationAppError("max_failures는 1~20 정수여야 합니다.")
    lock_seconds = value.get("lock_seconds")
    if not isinstance(lock_seconds, int) or isinstance(lock_seconds, bool) or not (60 <= lock_seconds <= 86400):
        raise ValidationAppError("lock_seconds는 60~86400(24시간) 정수여야 합니다.")


def _email_domains(value: Any) -> None:
    # 빈 목록([])은 '도메인 제한 없음'을 뜻한다 — Settings 화면 안내('빈 배열이면 제한
    # 없음')와 create_user의 소비 로직이 이 뜻으로 일치한다(round10 감사 C). 값이 있으면
    # 각 항목은 점을 포함한 도메인 문자열이어야 한다.
    if not isinstance(value, list) or not all(
        isinstance(d, str) and "." in d for d in value
    ):
        raise ValidationAppError("도메인 문자열 목록이어야 합니다(빈 목록이면 제한 없음).")


def _ui_branding(value: Any) -> None:
    # validate=None이면 dry-run/저장이 모양을 검증하지 않아, 문자열·product_name 없는
    # 객체가 그대로 저장되고 로그인/채팅 제목 소비자가 조용히 깨진다(round10 감사 C).
    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    product_name = value.get("product_name")
    if not isinstance(product_name, str) or not product_name.strip():
        raise ValidationAppError("product_name은 비어 있지 않은 문자열이어야 합니다.")


def _backup_schedule(value: Any) -> None:
    """백업 스케줄(0033). cron 표현식과 타임존을 **저장 시점에** 검증한다.

    검증을 워커로 미루면 잘못된 표현식이 조용히 저장되고, 그 뒤로 백업이 영영 안 돈다 —
    그리고 아무 오류도 안 난다(워커가 예외를 삼키므로). 백업이 그런 식으로 멈추는 것은
    복원이 필요해진 날에야 알게 된다.
    """
    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    if not isinstance(value.get("enabled"), bool):
        raise ValidationAppError("enabled는 true/false여야 합니다.")
    keep = value.get("keep", 14)
    if not isinstance(keep, int) or isinstance(keep, bool) or keep < 1 or keep > 365:
        raise ValidationAppError("keep은 1~365 정수여야 합니다.")
    # 나이 바닥(S12). 0 을 허용한다 — 「개수만으로 자른다」를 명시적으로 고르는 값이다.
    # 그 선택이 왜 위험한지는 `app/backups/service.py::apply_retention` 에 적혀 있다.
    keep_days = value.get("keep_days", 7)
    if (
        not isinstance(keep_days, int)
        or isinstance(keep_days, bool)
        or keep_days < 0
        or keep_days > 365
    ):
        raise ValidationAppError("keep_days는 0~365 정수여야 합니다.")
    from app.schedules import cron as _cron

    tz_name = value.get("timezone", "Asia/Seoul")
    if not isinstance(tz_name, str):
        raise ValidationAppError("timezone은 문자열이어야 합니다 (예: Asia/Seoul).")
    expression = value.get("cron", "")
    if not isinstance(expression, str) or not expression.strip():
        raise ValidationAppError("cron 표현식이 필요합니다 (예: 0 3 * * *).")
    # 아래 두 함수는 잘못된 값이면 ValidationAppError 를 던진다(불리언을 돌려주지 않는다).
    _cron.validate_timezone(tz_name)
    _cron.validate_cron(expression)


def _smtp(value: Any) -> None:
    """메일 발송 서버 설정(9-9 P4, D-545).

    **비밀번호와 비밀번호의 이름을 여기 두지 못하게 막는 것이 이 검증기의 핵심이다.** DB 설정은
    관리 API 로 읽히고 진단 번들에도 실린다 - 값이 들어오는 순간 평문 비밀번호가 응답을 타고
    나간다(불변 §3). 그래서 `password` 같은 키는 모양이 맞아도 거절한다. 비밀번호는 고정 칸
    `smtp.password` 하나에만 산다.

    비밀번호 칸의 **이름**(`password_ref`)도 받지 않는다(빈 값만 옛 모양으로 받는다 - 읽는 쪽은 무시한다).
    이름을 사람이 고를 수 있으면 메일 설정을 바꾸는 사람이 그 이름을 AI 키 같은 다른 비밀로 바꾸고 서버
    주소를 자기 서버로 돌려, 「연결 확인」 한 번에 워커가 진짜 비밀로 그 서버에 로그인하게 만들 수 있었다.
    모르는 항목도 받지 않는다 - 받아 두면 다음 사람이 그 항목이 쓰인다고 읽는다.

    포트, 보안 방식을 **저장 시점에** 검증하는 이유는 backup_schedule 과 같다: 워커로
    미루면 잘못된 값이 조용히 저장되고, 그 뒤로 메일이 영영 안 나간다.
    """
    from app.mail.config import ALL_SECURITY_MODES, DEFAULT_SMTP

    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    for banned in ("password", "passwd", "secret", "password_value"):
        if banned in value:
            raise ValidationAppError(
                "비밀번호는 설정에 저장하지 않습니다. 메일 설정의 비밀번호 칸에 저장하세요."
            )
    if str(value.get("password_ref") or "").strip():
        raise ValidationAppError(
            "비밀번호를 읽을 곳은 바꿀 수 없습니다. 비밀번호는 메일 설정의 비밀번호 칸에 저장하세요."
        )
    unknown = sorted(k for k in value if k not in DEFAULT_SMTP and k != "password_ref")
    if unknown:
        raise ValidationAppError("메일 설정에 없는 항목입니다: " + ", ".join(unknown))
    if not isinstance(value.get("enabled"), bool):
        raise ValidationAppError("메일 발송은 사용 또는 사용 안 함이어야 합니다.")
    port = value.get("port", 587)
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port < 65536):
        raise ValidationAppError("포트는 1~65535 사이의 정수여야 합니다.")
    security = value.get("security", "starttls")
    if security not in ALL_SECURITY_MODES:
        raise ValidationAppError("보안 연결은 STARTTLS, SSL, 사용 안 함 중 하나여야 합니다.")
    timeout = value.get("timeout_seconds", 20)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not (1 <= timeout <= 300):
        raise ValidationAppError("응답 대기 시간은 1~300초 사이의 정수여야 합니다.")
    for key, label in (("host", "메일 서버 주소"), ("from_address", "보내는 사람 주소"), ("from_name", "보내는 사람 이름"),
                       ("username", "로그인 계정"), ("password_ref", "비밀번호 칸"), ("ca_pem", "CA 인증서")):
        if key in value and not isinstance(value[key], str):
            raise ValidationAppError(f"{label} 칸에는 글자만 넣을 수 있습니다.")
    _smtp_text_fields(value)
    if "tls_verify" in value and not isinstance(value["tls_verify"], bool):
        raise ValidationAppError("서버 인증서 확인은 켬 또는 끔이어야 합니다.")
    _smtp_ca(value, security)
    from app.mail.config import ALL_MODES, MODE_LOCAL_RELAY

    mode = value.get("mode", "external")
    if mode not in ALL_MODES:
        raise ValidationAppError("보내는 방법은 외부 SMTP 사용 또는 ClovirAssist 로컬 릴레이여야 합니다.")
    if "relay" in value:
        _smtp_relay(value["relay"], enabled=bool(value.get("enabled")) and mode == MODE_LOCAL_RELAY)
    # 켜 놓고 주소가 비어 있으면 큐에 쌓기만 하고 아무것도 못 보낸다 - 저장 시점에 막는다.
    if value.get("enabled"):
        if mode != MODE_LOCAL_RELAY and not str(value.get("host", "")).strip():
            raise ValidationAppError("메일 발송을 켜려면 메일 서버 주소가 필요합니다.")
        if not str(value.get("from_address", "")).strip():
            raise ValidationAppError("메일 발송을 켜려면 보내는 사람 주소가 필요합니다.")


def _smtp_relay(relay: Any, *, enabled: bool) -> None:
    """로컬 릴레이 설정(D-551). 칸 모양은 헬퍼가 설정 파일을 쓸 때 다시 검사한다(`app/mail/relay_files.py`) - 여기서는 저장 전에
    사람에게 빠른 오류를 준다. 공개키(`dkim_public`)는 서버가 적는 칸이라 모양만 본다."""
    from app.mail import relay_files as rf
    from app.mail.config import ALL_DELIVERIES, ALL_SECURITY_MODES, DEFAULT_RELAY, DELIVERY_SMARTHOST

    if not isinstance(relay, dict):
        raise ValidationAppError("로컬 릴레이 설정은 객체여야 합니다.")
    unknown = sorted(k for k in relay if k not in DEFAULT_RELAY)
    if unknown:
        raise ValidationAppError("로컬 릴레이 설정에 없는 항목입니다: " + ", ".join(unknown))
    delivery = relay.get("delivery", DELIVERY_SMARTHOST)
    if delivery not in ALL_DELIVERIES:
        raise ValidationAppError("전달 방식은 상위 SMTP 이용 또는 인터넷으로 직접 전달이어야 합니다.")
    smarthost = relay.get("smarthost", {})
    if not isinstance(smarthost, dict) or any(k not in ("host", "port", "security", "username") for k in smarthost):
        raise ValidationAppError("상위 SMTP 서버 설정이 올바르지 않습니다.")
    host = str(smarthost.get("host") or "").strip().lower()
    if host and not (rf.HOST_RE.match(host) or rf.IPV4_RE.match(host)):
        raise ValidationAppError("상위 SMTP 서버 주소는 smtp.example.com 처럼 이름이나 IP 만 적습니다.")
    port = smarthost.get("port", 587)
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port < 65536):
        raise ValidationAppError("상위 SMTP 서버 포트는 1~65535 사이의 정수여야 합니다.")
    if smarthost.get("security", "starttls") not in ALL_SECURITY_MODES:
        raise ValidationAppError("상위 SMTP 서버의 보안 연결은 STARTTLS, SSL, 사용 안 함 중 하나여야 합니다.")
    username = str(smarthost.get("username") or "").strip()
    if username and not rf.USERNAME_RE.match(username):
        raise ValidationAppError("상위 SMTP 계정에는 공백이나 줄바꿈을 넣을 수 없습니다.")
    helo = str(relay.get("helo_name") or "").strip().lower()
    if helo and not rf.DOMAIN_RE.match(helo):
        raise ValidationAppError("서버 이름(HELO)은 mail.example.com 같은 이름이어야 합니다.")
    public_ip = str(relay.get("public_ip") or "").strip()
    if public_ip and not rf.IPV4_RE.match(public_ip):
        raise ValidationAppError("공인 IP 는 203.0.113.10 같은 IPv4 주소여야 합니다.")
    for key, label in (("ipv4_only", "IPv4 만 쓰기"), ("dkim_enabled", "DKIM 서명")):
        if key in relay and not isinstance(relay[key], bool):
            raise ValidationAppError(f"{label}는 켬 또는 끔이어야 합니다.")
    selector = str(relay.get("dkim_selector") or "").strip().lower()
    if selector and not rf.SELECTOR_RE.match(selector):
        raise ValidationAppError("DKIM 선택자는 영문 소문자와 숫자, 하이픈으로 씁니다.")
    if relay.get("dkim_enabled") and not selector:
        raise ValidationAppError("DKIM 서명을 켜려면 선택자가 필요합니다.")
    public = str(relay.get("dkim_public") or "")
    if public and (len(public) > 1024 or not re.fullmatch(r"[A-Za-z0-9+/=]+", public)):
        raise ValidationAppError("DKIM 공개키 모양이 올바르지 않습니다.")
    try:
        rf.normalize_overrides(relay.get("transport_overrides") or [])
    except rf.RelayParamsError as exc:
        raise ValidationAppError(str(exc)) from None
    resolvers = relay.get("compare_resolvers") or []
    if not isinstance(resolvers, list) or len(resolvers) > 3 or not all(
            isinstance(r, str) and rf.IPV4_RE.match(r.strip()) for r in resolvers):
        raise ValidationAppError("비교할 공개 DNS 서버는 IPv4 주소로 세 개까지 넣을 수 있습니다.")
    if enabled:
        if delivery == DELIVERY_SMARTHOST and not host:
            raise ValidationAppError("상위 SMTP 이용을 고르면 상위 SMTP 서버 주소가 필요합니다.")
        if delivery != DELIVERY_SMARTHOST and not helo:
            raise ValidationAppError("인터넷으로 직접 전달하려면 서버 이름(HELO)이 필요합니다.")


_SMTP_HOST_FORBIDDEN = re.compile(r"[\s/@?#\\]")
_EMAIL_SHAPE = re.compile(r"^[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[^@\s<>,;\"]+$")


def _smtp_text_fields(value: dict) -> None:
    """칸 하나하나의 모양. 보내는 사람 이름과 주소는 메일 머리에 그대로 들어가서 줄바꿈 하나가 머리 주입이 된다."""
    host = str(value.get("host") or "").strip()
    if host:
        if "://" in host or _SMTP_HOST_FORBIDDEN.search(host):
            raise ValidationAppError("메일 서버 주소에는 smtp.example.com 처럼 이름이나 IP 만 적습니다.")
        if len(host) > 253:
            raise ValidationAppError("메일 서버 주소가 너무 깁니다.")
    sender = str(value.get("from_address") or "").strip()
    if sender and (len(sender) > 320 or not _EMAIL_SHAPE.match(sender)):
        raise ValidationAppError("보내는 사람 주소는 name@example.com 모양이어야 합니다.")
    for key, label, limit in (("from_name", "보내는 사람 이름", 100), ("username", "로그인 계정", 320)):
        text = str(value.get(key) or "")
        if "\r" in text or "\n" in text:
            raise ValidationAppError(f"{label}에는 줄바꿈을 넣을 수 없습니다.")
        if len(text) > limit:
            raise ValidationAppError(f"{label}이 너무 깁니다.")


def _smtp_ca(value: dict, security: str) -> None:
    """사설 CA 인증서(PEM). 저장할 때 실제로 읽어 본다 — 못 읽는 원문을 받아 두면 발송할 때마다 보안 연결이
    실패하고, 그 원인은 설정 화면이 아니라 발송 기록에서야 보인다."""
    import ssl

    from app.mail.config import CA_PEM_MAX_CHARS, SECURITY_NONE

    pem = str(value.get("ca_pem") or "").strip()
    if not pem:
        return
    if security == SECURITY_NONE:
        raise ValidationAppError("보안 연결을 쓰지 않으면 CA 인증서는 쓰이지 않습니다. 보안 연결을 고르거나 인증서를 비우세요.")
    if len(pem) > CA_PEM_MAX_CHARS:
        raise ValidationAppError("CA 인증서가 너무 깁니다. 인증서 한두 개의 PEM 원문만 붙여 넣으세요.")
    if "-----BEGIN CERTIFICATE-----" not in pem:
        raise ValidationAppError("CA 인증서는 -----BEGIN CERTIFICATE----- 로 시작하는 PEM 원문이어야 합니다.")
    try:
        ssl.create_default_context(cadata=pem)
    except (ssl.SSLError, ValueError):
        raise ValidationAppError("CA 인증서를 읽지 못했습니다. PEM 원문 전체를 그대로 붙여 넣으세요.") from None


def _mail_notification_types(value: Any) -> None:
    """메일로도 보낼 수 있는 알림 유형(계획 3.4). 메일로 보낼 수 있는 유형 밖의 값은 받지 않는다."""
    from app.profiles.prefs import MAILABLE_TYPES

    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationAppError("알림 유형 목록이어야 합니다.")
    unknown = sorted({v for v in value if v not in MAILABLE_TYPES})
    if unknown:
        raise ValidationAppError("메일로 보낼 수 없는 알림 유형입니다: " + ", ".join(unknown))
    if len(set(value)) != len(value):
        raise ValidationAppError("같은 알림 유형이 두 번 들어 있습니다.")


# AI 생성 설정(계획 3.13, D-515). 소비자는 `app/ai/runtime.py` 하나다 - 호출마다 이 값을 읽으므로 저장하면 다음 호출부터
# 쓰인다. 제공자와 인증 방식의 짝은 여기서 따로 보고, 둘을 함께 맞는지는 AI 설정 API 가 한 벌로 본다.
def _ai_provider(value: Any) -> None:
    from app.ai.providers.base import PROVIDERS

    if value != "" and value not in PROVIDERS:
        raise ValidationAppError("지원하지 않는 AI 제공자입니다.")


def _ai_auth_method(value: Any) -> None:
    from app.ai.providers.base import PROVIDERS

    known = {m.key for spec in PROVIDERS.values() for m in spec.auth_methods}
    if value != "" and value not in known:
        raise ValidationAppError("지원하지 않는 인증 방식입니다.")


def _ai_model(value: Any) -> None:
    """모델 이름. 비우면 AI 는 꺼진다 - 제품이 모델을 대신 고르지 않는다."""
    if not isinstance(value, str):
        raise ValidationAppError("문자열이어야 합니다.")
    if len(value) > 200:
        raise ValidationAppError("200자 이하여야 합니다.")
    if any(c in value for c in "\r\n\x00"):
        raise ValidationAppError("줄바꿈이나 널 문자를 넣을 수 없습니다.")


def _ai_timeout(value: Any) -> None:
    from app.ai.concurrency import MAX_TIMEOUT_SECONDS, MIN_TIMEOUT_SECONDS

    if not isinstance(value, int) or isinstance(value, bool) or not (
        MIN_TIMEOUT_SECONDS <= value <= MAX_TIMEOUT_SECONDS
    ):
        raise ValidationAppError(f"{MIN_TIMEOUT_SECONDS}~{MAX_TIMEOUT_SECONDS}초 사이의 정수여야 합니다.")


def _bounded_int(low: int, high: int, unit: str):
    def check(value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or not (low <= value <= high):
            raise ValidationAppError(f"{low}~{high}{unit} 사이의 정수여야 합니다.")
    return check


def _setup_choices(value: Any) -> None:
    """초기 설정의 선택 값(계획 3.5 · S1, D-520 · D-534). 메일 · AI 는 「사용」(use) · 「사용하지 않음」(unused), TLS 는 「이 서버의
    인증서」(app) · 「외부 프록시가 맡음」(proxy)."""
    from app.setup.steps import CHOICE_VALUES

    if not isinstance(value, dict):
        raise ValidationAppError("선택 항목마다 값을 적는 객체여야 합니다.")
    unknown = sorted(k for k in value if k not in CHOICE_VALUES)
    if unknown:
        raise ValidationAppError("모르는 선택 항목입니다: " + ", ".join(unknown))
    for key, choice in value.items():
        if choice not in CHOICE_VALUES[key]:
            raise ValidationAppError(f"{key} 의 값은 " + ", ".join(CHOICE_VALUES[key]) + " 중 하나입니다.")


def _ai_concurrency(value: Any) -> None:
    from app.ai.concurrency import MAX_CONCURRENCY

    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= MAX_CONCURRENCY):
        raise ValidationAppError(f"1~{MAX_CONCURRENCY} 사이의 정수여야 합니다.")


# Every key here is wired to a real consumer (verified — no placebos). Settings
# that are only configurable via env or per-object (base URL, default timeout,
# page size, timezone, retry policy, schedule misfire default) are intentionally
# NOT here so the admin console never presents a switch with no effect.
REGISTRY: dict[str, SettingSpec] = {
    s.key: s
    for s in [
        SettingSpec("conversation_retention_days", "int", 90, False,
                    "대화 보존 기간(일). 초과 시 백그라운드 작업이 자동 삭제", _positive_int(3650)),
        SettingSpec("notification_retention_days", "int", 90, False,
                    "알림 보존 기간(일). 초과 시 백그라운드 작업이 정리", _positive_int(3650)),
        SettingSpec("trash_retention_days", "int", 7, False,
                    "휴지통 보관 기간(일). 초과 시 원본을 보관처리하고 휴지통에서 삭제", _positive_int(365)),
        # 문서 휴지통은 **다른 정책**을 갖는다 (지시 22.7 개정 · D-352).
        #
        # 위 `trash_retention_days` 가 하는 일은 「원본을 보관처리하고 휴지통 행을 지우는」
        # 것이라 되돌릴 여지가 남는다. 문서 쪽은 이미 보관된 상태로 휴지통에 있으므로 그
        # 다음 단계가 **행을 지우는 것**이다 — 판·태그·댓글·색인이 함께 사라지고 되돌릴 수
        # 없다. 그래서 기간을 따로 두고, 무엇보다 **끌 수 있게** 둔다: 자동으로 지우는 일을
        # 원하지 않는 설치가 그것을 고르는 방법이 있어야 한다.
        SettingSpec("document_trash_autopurge", "bool", True, False,
                    "켜 두면 보관 기간이 지난 문서를 자동으로 영구 삭제합니다. 끄면 사람이 누를 때만 지워집니다",
                    _bool),
        SettingSpec("document_trash_retention_days", "int", 7, False,
                    "문서를 휴지통에 두는 기간(일). 버린 시각부터 세고, 그 기간이 지나면 영구 삭제합니다",
                    _positive_int(365)),
        SettingSpec("ui_branding", "object", {"product_name": "ClovirAssist"}, False,
                    "UI 브랜딩(제품명). 로그인/채팅 화면 제목", _ui_branding),
        SettingSpec("maintenance_mode", "bool", False, False,
                    "유지보수 모드 (일반 사용자 신규 요청 차단)", _bool),
        SettingSpec("maintenance_message", "string", "현재 시스템 점검 중입니다.", False,
                    "유지보수 공지 메시지", _non_empty_str),
        SettingSpec("password_policy", "object", {"min_length": 12, "min_classes": 3}, False,
                    "비밀번호 정책: 즉시 적용", _password_policy),
        # "신규 세션부터 적용"은 absolute_timeout_seconds에만 맞는 말이다(app/core/sessions.py
        # ::create가 그 값을 세션 생성 시점에 expires_at으로 굳힌다). idle_timeout_seconds는
        # 굳지 않는다 - validate()가 매 요청마다 그때의 설정값으로 idle_deadline을 다시 계산하므로,
        # 줄이면 저장 즉시 이미 열려 있는 모든 세션에(저장한 관리자 본인 포함) 적용된다. 바로 위
        # password_policy 설명("즉시 적용")은 정확한데 이 칸만 두 필드를 뭉뚱그려 틀렸었다.
        SettingSpec("session_policy", "object",
                    {"idle_timeout_seconds": 1800, "absolute_timeout_seconds": 28800}, False,
                    "세션 정책: 유휴 제한은 저장 즉시(이미 열린 세션 포함), 최대 세션 길이는 신규 세션부터 적용",
                    _session_policy),
        # ADM-05: 예전엔 env(app/core/config.py의 login_max_failures/login_lock_seconds)
        # 전용이라 화면에서 볼 수도 바꿀 수도 없었다 - 조정하려면 서버 파일을 고치고
        # 재시작해야 했다. session_policy와 같은 "env 기본값 + DB override" 모양으로 신설.
        # 기본값은 기존 env 기본값(5회/900초)과 같게 둬서, 아무도 저장하지 않은 설치는
        # 지금과 똑같이 동작한다. 다음 로그인 시도부터 즉시 적용(별도 굳는 지점 없음).
        SettingSpec("lockout_policy", "object",
                    {"max_failures": 5, "lock_seconds": 900}, False,
                    "계정 잠금 정책: 로그인 실패 임계값과 잠금 시간. 다음 로그인 시도부터 즉시 적용",
                    _lockout_policy),
        # 기본값이 비어 있다(= 제한 없음). 설치처마다 다른 값이라 여기에 한 회사의 도메인을
        # 박아 두면 다른 고객사 설치에서도 그 회사 도메인으로만 계정을 만들 수 있게 된다.
        # env 기본값(app/core/config.py)만 비우고 여기를 두면 첫 부팅에서 레지스트리
        # 기본값이 DB 로 내려앉아 고객 도메인이 되살아난다 — 두 곳을 같이 비운다.
        SettingSpec("allowed_email_domains", "object", [], False,
                    "허용 이메일 도메인: 사용자 생성 시 즉시 적용, 비우면 제한 없음", _email_domains),
        # config_dir/feature-flags.json에 있던 값을 관리 콘솔에서 켜고 끌 수 있게 옮긴다 —
        # 예전엔 이 값을 바꾸려면 서버 파일을 직접 편집해야 했다(Settings 화면에 노출 안 됨).
        # ── 주기 설정 (지시 1 · 29) ─────────────────────────────────────────
        #
        # 예전에는 문서·티켓·프로젝트 미러 동기화 주기가 여기 함께 있었다. 그 셋은 이제
        # 없다 — 세 미러가 사라졌고, 돌지 않는 동기화의 주기를 관리자가 고를 수 있게 두면
        # 값을 바꾼 사람이 무언가 달라졌다고 믿는 거짓 스위치가 된다.
        #
        # 기본값 `0` 은 "서버 기본값(app/core/config.py)을 따른다" 는 뜻이다. 실제 값을
        # 여기 박아 두면 env 로 주기를 정해 둔 기존 설치가 업그레이드하는 순간 조용히
        # 다른 값으로 바뀐다 — `llm_timeout_seconds` 가 이미 쓰는 규약과 같다.
        #
        # `restart_required=False`: 워커 틱이 매번 이 값을 다시 읽는다
        # (app/worker_main.py). 설정 캐시 재적재가 60초 간격이므로 늦어도 그 안에 반영된다.
        SettingSpec("search_index_interval_seconds", "int", 0, False,
                    "검색 색인 갱신 주기(초). 0이면 서버 기본값을 씁니다. 최소 60초",
                    _interval_seconds),
        SettingSpec("document_automation_enabled", "bool", True, False,
                    "문서 자동화: 끄면 신규 문서 생성 요청이 거부됩니다", _bool),
        # AI 기능 셋(계획 3.13, D-507). 예전에는 feature-flags.json 소유라 운영에서 관리 화면이 못 켰다.
        SettingSpec("chat_enabled", "bool", True, False,
                    "AI 도우미 채팅: 끄면 채팅 화면과 대화 API 가 닫힙니다", _bool),
        SettingSpec("game_ai_enabled", "bool", False, False,
                    "AI 퀴즈 만들기: 켜면 놀이 화면에서 AI 가 퀴즈 초안을 만듭니다", _bool),
        SettingSpec("assistant_narrative_enabled", "bool", False, False,
                    "AI 도우미 문장 요약: 켜면 홈과 도우미가 숫자 옆에 한두 문장 요약을 붙입니다", _bool),
        # 백업 스케줄(0033, PLAN Phase 6). 워커가 이 값을 읽어 실제로 백업을 만든다
        # (app/worker_main.py::backup_schedule_tick) — '되는 척하는 스위치'가 아니다.
        # 기본은 꺼짐: 켜는 순간 디스크를 쓰기 시작하므로 운영자가 의도해서 켜야 한다.
        SettingSpec("backup_schedule", "object",
                    {"enabled": False, "cron": "0 3 * * *", "timezone": "Asia/Seoul",
                     "keep": 14, "keep_days": 7},
                    False,
                    # 지시 36: 설명은 화면에 그대로 나간다 — 내부 어휘(cron·keep·워커)로
                    # 쓰면 관리자가 무엇을 정하는 값인지 알 수 없다. 무엇이 언제 일어나고
                    # 무엇이 남는지로 쓴다.
                    "정해진 시각마다 데이터베이스를 자동으로 백업하고, 정한 개수와 기간만큼 남깁니다",
                    _backup_schedule),
        # 메일 발송(9-9 P4). 소비자가 넷 붙어 있다: 비밀번호 재설정, 초대, 백업 실패,
        # 승인 요청. '되는 척하는 스위치'가 아니라는 뜻이다. 기본은 꺼짐이고, 꺼져 있으면
        # 화면과 진단이 "설정 없음"을 분명히 말한다(app/mail/config.py).
        # 비밀번호는 여기 없다 - 고정 칸 smtp.password 에만 있다(D-545).
        SettingSpec("smtp", "object",
                    {"enabled": False, "host": "", "port": 587, "security": "starttls",
                     "from_address": "", "from_name": "", "username": "",
                     "timeout_seconds": 20},
                    False,
                    # 지시 36: 비밀번호를 저장하지 않는다는 사실은 관리자가 알아야 하지만,
                    # 그 저장 방식의 내부 필드 이름까지 알 필요는 없다.
                    "메일 발송에 쓸 서버 정보. 비밀번호는 여기 저장하지 않고 메일 설정의 비밀번호 칸에 "
                    "따로 저장합니다",
                    _smtp),
        # 알림을 메일로도 보내기(계획 3.4, D-514). 사용자는 이 목록 안에서 받을 유형을 고른다. 관리자가 목록에서
        # 빼면 그 유형은 켜 둔 사람에게도 나가지 않는다. 소비자는 `app/notifications/mail.py` 다.
        SettingSpec("mail_notification_types", "object",
                    ["ticket_assigned", "ticket_status_changed", "ticket_resolved"], False,
                    "메일로도 보낼 수 있는 알림 유형입니다. 사용자는 이 안에서 메일로 받을 알림을 고릅니다",
                    _mail_notification_types),
        SettingSpec("mail_notification_max_age_days", "int", 7, False,
                    "메일 서버가 멈춘 동안 쌓인 메일은 이 기간(일)이 지나면 보내지 않습니다",
                    _positive_int(30)),
        # 초기 설정 화면이 고친다(D-520). 메일과 AI 를 쓰지 않는 설치도 정상 설치다 - 「사용하지 않음」이면 설정이 비어
        # 있어도 초기 설정의 할 일로 세지 않는다.
        SettingSpec("setup_optional_choices", "object", {"mail": "use", "llm": "use", "tls": "app"}, False,
                    "초기 설정에서 메일과 AI 를 쓰는지, TLS 를 누가 맡는지 고릅니다", _setup_choices),
        # 노션 데이터베이스 id 셋(9-4)이 여기 있었다. 티켓 목록과 문서 목록이 그 값을
        # 읽어 노션을 조회했기 때문이다. 지금은 셋 다 자체 데이터베이스에서 나오므로
        # 관리자가 정할 것이 없다. 옛 데이터를 한 번 읽어 오는 이관 CLI 는 데이터베이스를
        # 제목으로 찾거나 명령행 인자로 받는다(app/migration/source_notion.py).
        # ── AI 생성 (계획 3.13, D-515) ──────────────────────────────────────
        #
        # 소비자는 `app/ai/runtime.py` 하나다. 호출마다 이 값을 읽으므로 저장하면 재시작 없이 다음 호출부터 쓰인다.
        # 빈 제공자, 빈 모델, 꺼짐이 기본이다 - AI 를 기본으로 켜 두는 관례가 이 저장소에 없고, 모델은 제품이 대신 고를
        # 자리가 아니다. 서버에 로그인된 구독 명령줄 도구로 돌던 옛 설정(`llm_*`)은 0037 이 옮겼다.
        SettingSpec("ai_generation_enabled", "bool", False, False,
                    "AI 답변 생성: 켜면 채팅, 작업 공간, 홈 요약, 퀴즈가 설정한 AI 제공자로 답을 만듭니다", _bool),
        SettingSpec("ai_provider", "string", "", False, "답변을 만드는 AI 제공자입니다", _ai_provider),
        SettingSpec("ai_auth_method", "string", "", False, "AI 제공자에 연결하는 방법입니다", _ai_auth_method),
        SettingSpec("ai_model", "string", "", False, "답변을 만드는 모델 이름입니다. 비우면 AI 가 꺼집니다", _ai_model),
        SettingSpec("ai_timeout_seconds", "int", 60, False,
                    "AI 호출 하나를 기다리는 시간(초)입니다", _ai_timeout),
        SettingSpec("ai_max_concurrency", "int", 2, False,
                    "웹과 워커가 함께 나눠 쓰는 AI 동시 실행 수입니다", _ai_concurrency),
        # ChatGPT 계정 연결의 토큰 수명 기본값(계획 3.15, D-516). **정본은 제공자의 응답이다** - 응답의 `expires_in` ·
        # JWT `exp` · `refresh_token_expires_in` 이 없을 때만 이 값을 쓴다. 제공자가 수명을 바꿔도 코드를 고치지 않는다.
        SettingSpec("ai_openai_access_ttl_fallback_seconds", "int", 3600, False,
                    "제공자가 access token 수명을 알려 주지 않을 때 쓰는 값(초)입니다",
                    _bounded_int(300, 86400, "초")),
        SettingSpec("ai_openai_refresh_ttl_fallback_days", "int", 30, False,
                    "제공자가 갱신 토큰 수명을 알려 주지 않을 때 쓰는 값(일)입니다", _bounded_int(1, 365, "일")),
        SettingSpec("ai_token_refresh_lead_seconds", "int", 300, False,
                    "access token 이 끝나기 이만큼 전에 미리 갱신합니다(초)", _bounded_int(30, 3600, "초")),
    ]
}


# 시스템 관리자만 바꿀 수 있는 키 (9-4, 9-5).
#
# 나머지 설정과 달리 이 여섯은 **설치 한 벌 전체가 무엇을 띄우는가**를 정한다.
# `CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고 이 제품의 `admin` 은 부서 범위로 좁혀질 수
# 있다(`admin_scope="dept"`) - 부서 관리자가 이 서버가 띄우는 실행 파일 경로를 바꿀 수
# 있으면 안 된다.
#
# 게이트를 라우터가 아니라 여기에 두는 이유: 키를 추가하는 사람과 라우터를 고치는 사람이
# 다르다. 표 옆에 두면 새 키를 넣을 때 이 목록이 눈에 들어온다.
# 전용 API 가 있는 키 → 범용 설정 API 가 거절할 때의 문장(D-548). 그 키의 저장 · 미리 검증 · 되돌리기는 전용 화면의 API 만 한다.
DEDICATED_API_KEYS: dict[str, str] = {
    "smtp": "메일 설정은 메일 화면에서 바꿉니다.",
}

SYSTEM_ADMIN_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "ai_generation_enabled",
        "ai_provider",
        "ai_auth_method",
        "ai_model",
        "ai_timeout_seconds",
        "ai_max_concurrency",
        "ai_openai_access_ttl_fallback_seconds",
        "ai_openai_refresh_ttl_fallback_days",
        "ai_token_refresh_lead_seconds",
        "chat_enabled",
        "game_ai_enabled",
        "assistant_narrative_enabled",
        # 초기 설정 화면 자체가 시스템 관리자 전용이다(app/setup/router.py).
        "setup_optional_choices",
        # 메일 서버 설정(D-545). 서버 주소를 바꾸고 「연결 확인」을 누르면 워커가 저장된 SMTP 비밀번호로 그 서버에
        # 로그인한다. 비밀번호 칸은 시스템 관리자 전용인데 서버 주소를 전역 관리자가 바꿀 수 있으면, 그 비밀번호를
        # 자기 서버로 빼낼 수 있다. 비밀번호 칸의 이름을 고정한 것(`_smtp`)과 둘이 함께 있어야 두 길이 다 닫힌다.
        "smtp",
    }
)


def get_spec(key: str) -> SettingSpec:
    spec = REGISTRY.get(key)
    if spec is None:
        raise ValidationAppError(f"수정 허용 목록에 없는 설정 키입니다: {key}")
    return spec


def validate_value(key: str, value: Any) -> None:
    spec = get_spec(key)
    if spec.validate is not None:
        spec.validate(value)
