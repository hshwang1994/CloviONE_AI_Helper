"""Allowlisted editable settings (spec §14.4).

Only keys defined here can be changed via the API — the "허용 목록 방식"
(allowlist) required by spec §0.2. Each entry declares a type, a validator,
whether a restart is needed, and a default. System files are never exposed;
Secrets are never stored plaintext (spec §25.4) — none of these are secret.
"""

from __future__ import annotations

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


def _retry_policy(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    ma = value.get("max_attempts", 3)
    if not isinstance(ma, int) or ma < 1 or ma > 10:
        raise ValidationAppError("max_attempts는 1~10 정수여야 합니다.")


# Every key here is wired to a real consumer (verified — no placebos). Settings
# that are only configurable via env or per-object (base URL, default timeout,
# page size, timezone, retry policy, schedule misfire default) are intentionally
# NOT here so the admin console never presents a switch with no effect.
REGISTRY: dict[str, SettingSpec] = {
    s.key: s
    for s in [
        SettingSpec("conversation_retention_days", "int", 90, False,
                    "대화 보존 기간(일) — 초과 시 백그라운드 작업이 자동 삭제", _positive_int(3650)),
        SettingSpec("notification_retention_days", "int", 90, False,
                    "알림 보존 기간(일) — 초과 시 백그라운드 작업이 정리", _positive_int(3650)),
        SettingSpec("trash_retention_days", "int", 7, False,
                    "휴지통 보관 기간(일) — 초과 시 노션 원본을 보관처리하고 휴지통에서 삭제", _positive_int(365)),
        SettingSpec("ui_branding", "object", {"product_name": "ClovirAssist"}, False,
                    "UI 브랜딩(제품명) — 로그인/채팅 화면 제목", _ui_branding),
        SettingSpec("maintenance_mode", "bool", False, False,
                    "유지보수 모드 (일반 사용자 신규 요청 차단)", _bool),
        SettingSpec("maintenance_message", "string", "현재 시스템 점검 중입니다.", False,
                    "유지보수 공지 메시지", _non_empty_str),
        SettingSpec("password_policy", "object", {"min_length": 12, "min_classes": 3}, False,
                    "비밀번호 정책 — 즉시 적용", _password_policy),
        SettingSpec("session_policy", "object",
                    {"idle_timeout_seconds": 1800, "absolute_timeout_seconds": 28800}, False,
                    "세션 정책 — 신규 세션부터 적용", _session_policy),
        SettingSpec("allowed_email_domains", "object", ["goodmit.co.kr"], False,
                    "허용 이메일 도메인 — 사용자 생성 시 즉시 적용", _email_domains),
        # config_dir/feature-flags.json에 있던 값을 관리 콘솔에서 켜고 끌 수 있게 옮긴다 —
        # 예전엔 이 값을 바꾸려면 서버 파일을 직접 편집해야 했다(Settings 화면에 노출 안 됨).
        SettingSpec("document_automation_enabled", "bool", True, False,
                    "문서 자동화 — 끄면 신규 문서 생성 요청이 거부됩니다", _bool),
        # 백업 스케줄(0033, PLAN Phase 6). 워커가 이 값을 읽어 실제로 백업을 만든다
        # (app/worker_main.py::backup_schedule_tick) — '되는 척하는 스위치'가 아니다.
        # 기본은 꺼짐: 켜는 순간 디스크를 쓰기 시작하므로 운영자가 의도해서 켜야 한다.
        SettingSpec("backup_schedule", "object",
                    {"enabled": False, "cron": "0 3 * * *", "timezone": "Asia/Seoul", "keep": 14},
                    False,
                    "자동 백업 일정 — 워커가 이 cron 에 맞춰 DB 스냅숏을 만들고 keep개만 남깁니다",
                    _backup_schedule),
    ]
}


def get_spec(key: str) -> SettingSpec:
    spec = REGISTRY.get(key)
    if spec is None:
        raise ValidationAppError(f"수정 허용 목록에 없는 설정 키입니다: {key}")
    return spec


def validate_value(key: str, value: Any) -> None:
    spec = get_spec(key)
    if spec.validate is not None:
        spec.validate(value)
