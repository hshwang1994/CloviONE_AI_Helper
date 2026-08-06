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


def _smtp(value: Any) -> None:
    """메일 발송 서버 설정(9-9 P4).

    **비밀번호를 여기 저장하지 못하게 막는 것이 이 검증기의 핵심이다.** DB 설정은
    관리 API 로 읽히고 진단 번들에도 실린다 - 값이 들어오는 순간 평문 비밀번호가
    응답을 타고 나간다(불변 §3). 그래서 `password` 같은 키는 모양이 맞아도 거절한다.
    실제 값은 `SECRETS_DIR/<password_ref>` 파일에만 둔다.

    포트, 보안 방식을 **저장 시점에** 검증하는 이유는 backup_schedule 과 같다: 워커로
    미루면 잘못된 값이 조용히 저장되고, 그 뒤로 메일이 영영 안 나간다.
    """
    from app.mail.config import ALL_SECURITY_MODES

    if not isinstance(value, dict):
        raise ValidationAppError("객체여야 합니다.")
    for banned in ("password", "passwd", "secret", "password_value"):
        if banned in value:
            raise ValidationAppError(
                "비밀번호는 설정에 저장하지 않습니다. 서버의 secret 파일 이름을 "
                "password_ref 에 적으세요."
            )
    if not isinstance(value.get("enabled"), bool):
        raise ValidationAppError("enabled는 true/false여야 합니다.")
    port = value.get("port", 587)
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port < 65536):
        raise ValidationAppError("port는 1~65535 정수여야 합니다.")
    security = value.get("security", "starttls")
    if security not in ALL_SECURITY_MODES:
        raise ValidationAppError("security는 none, starttls, ssl 중 하나여야 합니다.")
    timeout = value.get("timeout_seconds", 20)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not (1 <= timeout <= 300):
        raise ValidationAppError("timeout_seconds는 1~300 정수여야 합니다.")
    for key in ("host", "from_address", "from_name", "username", "password_ref"):
        if key in value and not isinstance(value[key], str):
            raise ValidationAppError(f"{key}는 문자열이어야 합니다.")
    # 켜 놓고 주소가 비어 있으면 큐에 쌓기만 하고 아무것도 못 보낸다 - 저장 시점에 막는다.
    if value.get("enabled"):
        if not str(value.get("host", "")).strip():
            raise ValidationAppError("메일 발송을 켜려면 host가 필요합니다.")
        if not str(value.get("from_address", "")).strip():
            raise ValidationAppError("메일 발송을 켜려면 from_address가 필요합니다.")


def _notion_database_id(value: Any) -> None:
    """노션 데이터베이스 id(9-4). **빈 문자열을 허용한다** - 그것이 '안 정함' 이다.

    비우면 `apply_overrides` 가 덮지 않으므로 환경변수 값이 그대로 산다. 즉 '지우기' 는
    '환경변수로 되돌리기' 다. 화면이 그 뜻을 말해야 한다.

    모양만 본다: 노션이 주는 것은 32자리 16진수이거나 하이픈이 섞인 UUID 인데, 사람들이
    붙여 넣는 것은 대개 **URL 통째**다(`https://notion.so/워크스페이스/<32자>?v=...`).
    그걸 그대로 저장하면 조회 URL 이 망가지고 노션은 400 을 준다 - 화면은 '조회 실패' 로
    그리고 운영자는 토큰을 의심한다. 그래서 저장 시점에 끊는다.
    """
    if not isinstance(value, str):
        raise ValidationAppError("문자열이어야 합니다.")
    text = value.strip()
    if not text:
        return
    compact = text.replace("-", "")
    if len(compact) != 32 or not all(c in "0123456789abcdefABCDEF" for c in compact):
        raise ValidationAppError(
            "노션 데이터베이스 id 는 32자리 16진수여야 합니다. 주소창의 링크가 아니라 "
            "id 부분만 넣으세요."
        )


# LLM 설정(9-5). 빈 값 = '안 정함'(환경변수를 따른다)이라는 규약을 세 검증기가 공유한다.
_LLM_ENABLED_CHOICES = ("", "on", "off")
_LLM_BACKEND_CHOICES = ("", "cli", "api")


def _llm_enabled(value: Any) -> None:
    if value not in _LLM_ENABLED_CHOICES:
        raise ValidationAppError("빈 값(환경변수를 따름), on, off 중 하나여야 합니다.")


def _llm_backend(value: Any) -> None:
    if value not in _LLM_BACKEND_CHOICES:
        raise ValidationAppError("빈 값(환경변수를 따름), cli, api 중 하나여야 합니다.")


def _llm_text(value: Any) -> None:
    """모델 이름과 실행 파일 경로. 빈 값 허용, **줄바꿈과 널 문자는 거절**.

    이 값은 argv 로 들어간다(app/llm/cli_backend.py::build_argv). `shell=False` 라
    명령 주입은 안 되지만, 줄바꿈이 섞인 경로는 실행 실패의 원인을 로그에서 못 읽게 만든다.
    """
    if not isinstance(value, str):
        raise ValidationAppError("문자열이어야 합니다.")
    if len(value) > 512:
        raise ValidationAppError("512자 이하여야 합니다.")
    if any(c in value for c in "\r\n\x00"):
        raise ValidationAppError("줄바꿈이나 널 문자를 넣을 수 없습니다.")


def _llm_timeout(value: Any) -> None:
    """0 = '안 정함'. 상한은 cli_backend.MAX_TIMEOUT_SECONDS 와 같은 값을 쓴다."""
    from app.llm.cli_backend import MAX_TIMEOUT_SECONDS, MIN_TIMEOUT_SECONDS

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValidationAppError("0 이상 정수여야 합니다(0이면 환경변수나 기본값을 따릅니다).")
    if value and not (MIN_TIMEOUT_SECONDS <= value <= MAX_TIMEOUT_SECONDS):
        raise ValidationAppError(
            f"{MIN_TIMEOUT_SECONDS}~{MAX_TIMEOUT_SECONDS}초 사이여야 합니다(0이면 기본값)."
        )


def _llm_concurrency(value: Any) -> None:
    """동시 실행 슬롯. 상한을 낮게 잡는 이유는 app/llm/service.py 에 적어 뒀다 -
    구독 한도는 이 서버에서 CLI 를 쓰는 **사람과 공유**한다."""
    from app.llm.service import MAX_CONCURRENCY

    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= MAX_CONCURRENCY):
        raise ValidationAppError(f"1~{MAX_CONCURRENCY} 사이의 정수여야 합니다.")


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
                    "대화 보존 기간(일). 초과 시 백그라운드 작업이 자동 삭제", _positive_int(3650)),
        SettingSpec("notification_retention_days", "int", 90, False,
                    "알림 보존 기간(일). 초과 시 백그라운드 작업이 정리", _positive_int(3650)),
        SettingSpec("trash_retention_days", "int", 7, False,
                    "휴지통 보관 기간(일). 초과 시 노션 원본을 보관처리하고 휴지통에서 삭제", _positive_int(365)),
        SettingSpec("ui_branding", "object", {"product_name": "ClovirAssist"}, False,
                    "UI 브랜딩(제품명). 로그인/채팅 화면 제목", _ui_branding),
        SettingSpec("maintenance_mode", "bool", False, False,
                    "유지보수 모드 (일반 사용자 신규 요청 차단)", _bool),
        SettingSpec("maintenance_message", "string", "현재 시스템 점검 중입니다.", False,
                    "유지보수 공지 메시지", _non_empty_str),
        SettingSpec("password_policy", "object", {"min_length": 12, "min_classes": 3}, False,
                    "비밀번호 정책: 즉시 적용", _password_policy),
        SettingSpec("session_policy", "object",
                    {"idle_timeout_seconds": 1800, "absolute_timeout_seconds": 28800}, False,
                    "세션 정책: 신규 세션부터 적용", _session_policy),
        # 기본값이 비어 있다(= 제한 없음). 설치처마다 다른 값이라 여기에 한 회사의 도메인을
        # 박아 두면 다른 고객사 설치에서도 그 회사 도메인으로만 계정을 만들 수 있게 된다.
        # env 기본값(app/core/config.py)만 비우고 여기를 두면 첫 부팅에서 레지스트리
        # 기본값이 DB 로 내려앉아 고객 도메인이 되살아난다 — 두 곳을 같이 비운다.
        SettingSpec("allowed_email_domains", "object", [], False,
                    "허용 이메일 도메인: 사용자 생성 시 즉시 적용, 비우면 제한 없음", _email_domains),
        # config_dir/feature-flags.json에 있던 값을 관리 콘솔에서 켜고 끌 수 있게 옮긴다 —
        # 예전엔 이 값을 바꾸려면 서버 파일을 직접 편집해야 했다(Settings 화면에 노출 안 됨).
        SettingSpec("document_automation_enabled", "bool", True, False,
                    "문서 자동화: 끄면 신규 문서 생성 요청이 거부됩니다", _bool),
        # 백업 스케줄(0033, PLAN Phase 6). 워커가 이 값을 읽어 실제로 백업을 만든다
        # (app/worker_main.py::backup_schedule_tick) — '되는 척하는 스위치'가 아니다.
        # 기본은 꺼짐: 켜는 순간 디스크를 쓰기 시작하므로 운영자가 의도해서 켜야 한다.
        SettingSpec("backup_schedule", "object",
                    {"enabled": False, "cron": "0 3 * * *", "timezone": "Asia/Seoul", "keep": 14},
                    False,
                    "자동 백업 일정: 워커가 이 cron 에 맞춰 DB 스냅숏을 만들고 keep개만 남깁니다",
                    _backup_schedule),
        # 메일 발송(9-9 P4). 소비자가 넷 붙어 있다: 비밀번호 재설정, 초대, 백업 실패,
        # 승인 요청. '되는 척하는 스위치'가 아니라는 뜻이다. 기본은 꺼짐이고, 꺼져 있으면
        # 화면과 진단이 "설정 없음"을 분명히 말한다(app/mail/config.py).
        # 비밀번호는 여기 없다 - password_ref 는 서버 secret 파일의 **이름**일 뿐이다.
        SettingSpec("smtp", "object",
                    {"enabled": False, "host": "", "port": 587, "security": "starttls",
                     "from_address": "", "from_name": "", "username": "",
                     "password_ref": "", "timeout_seconds": 20},
                    False,
                    "메일(SMTP) 발송 서버. 비밀번호는 저장하지 않고 서버 secret 파일 이름"
                    "(password_ref)만 적습니다",
                    _smtp),
        # ── Notion 데이터베이스 id (9-4) ─────────────────────────────────────
        #
        # 예전에는 이 셋을 바꾸려면 서버에 들어가 env 파일을 고치고 서비스를 재시작해야
        # 했다. 셋업 마법사는 "넣으세요" 라고 말하는데 넣을 화면이 없었다.
        #
        # 저장하면 **즉시** 반영된다: 소비자는 `settings.notion_*_database_id` 를 읽고,
        # 캐시가 저장할 때마다 그 위에 값을 얹는다(app/core/tenant_config.py::apply_overrides).
        # 워커는 자기 틱에서 캐시를 다시 읽으므로 한 틱 뒤에 따라온다 - 화면은 그 사실을
        # 그대로 말한다(즉시 / 워커는 다음 틱).
        # 토큰은 여기 없다. 토큰은 시크릿 파일 참조다(app/core/secret_refs.py).
        SettingSpec("notion_tasks_database_id", "string", "", False,
                    "노션 작업 데이터베이스 id. 티켓 목록과 리포트가 이 데이터베이스를 읽습니다. "
                    "비우면 서버 환경변수 값을 그대로 씁니다",
                    _notion_database_id),
        SettingSpec("notion_documents_database_id", "string", "", False,
                    "노션 문서 데이터베이스 id. 팀 공간 문서 목록이 이 데이터베이스를 읽습니다. "
                    "비우면 서버 환경변수 값을 그대로 씁니다",
                    _notion_database_id),
        SettingSpec("notion_sprint_database_id", "string", "", False,
                    "팀이 쓰는 노션 스프린트 데이터베이스 id. 진단 전용입니다. 포털의 이번 주는 "
                    "작업 데이터베이스의 마감일로 계산하므로 이 값을 넣어도 화면 내용은 바뀌지 "
                    "않고, 두 곳이 어긋났는지만 알려 줍니다",
                    _notion_database_id),
        # ── LLM (9-5) ────────────────────────────────────────────────────────
        #
        # 소비자는 `app/llm/provider.py::resolve_config` 다. 그 함수는 이미
        # `Settings` 필드 → 환경변수 → 기본값 순으로 읽으므로, 여기 저장한 값이 위 오버레이를
        # 거쳐 `Settings` 에 얹히면 **provider 코드를 고치지 않고** 그쪽이 이긴다.
        # 빈 값과 0 이 '안 정함' 이고, 그때는 환경변수가 산다.
        SettingSpec("llm_enabled", "string", "", False,
                    "AI 요약 사용 여부. on 이면 켜고 off 면 끕니다. 비우면 서버 환경변수"
                    "(LLM_ENABLED)를 따릅니다",
                    _llm_enabled),
        SettingSpec("llm_backend", "string", "", False,
                    "AI 백엔드. cli 는 서버에 로그인된 구독 명령줄 도구, api 는 Anthropic API "
                    "입니다. 비우면 환경변수(LLM_BACKEND)를 따릅니다",
                    _llm_backend),
        SettingSpec("llm_executable", "string", "", False,
                    "명령줄 도구의 실행 파일 이름 또는 절대 경로. 비우면 claude 를 씁니다",
                    _llm_text),
        SettingSpec("llm_model", "string", "", False,
                    "사용할 모델 이름. 비우면 sonnet 을 씁니다",
                    _llm_text),
        SettingSpec("llm_timeout_seconds", "int", 0, False,
                    "AI 호출 하나의 제한 시간(초). 0이면 기본값(120초)을 씁니다",
                    _llm_timeout),
        SettingSpec("llm_max_concurrency", "int", 1, False,
                    "동시에 돌 수 있는 AI 호출 수. 구독 한도를 이 서버에서 명령줄 도구를 쓰는 "
                    "사람과 나눠 쓰므로 작게 잡습니다",
                    _llm_concurrency),
    ]
}


# 시스템 관리자만 바꿀 수 있는 키 (9-4, 9-5).
#
# 나머지 설정과 달리 이 여섯은 **설치 한 벌 전체가 어디를 보고 무엇을 띄우는가**를 정한다.
# `CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고 이 제품의 `admin` 은 부서 범위로 좁혀질 수
# 있다(`admin_scope="dept"`) - 부서 관리자가 포털 전체를 다른 노션 워크스페이스로 돌리거나
# 이 서버가 띄우는 실행 파일 경로를 바꿀 수 있으면 안 된다.
#
# 게이트를 라우터가 아니라 여기에 두는 이유: 키를 추가하는 사람과 라우터를 고치는 사람이
# 다르다. 표 옆에 두면 새 키를 넣을 때 이 목록이 눈에 들어온다.
SYSTEM_ADMIN_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "notion_tasks_database_id",
        "notion_documents_database_id",
        "notion_sprint_database_id",
        "llm_enabled",
        "llm_backend",
        "llm_executable",
        "llm_model",
        "llm_timeout_seconds",
        "llm_max_concurrency",
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
