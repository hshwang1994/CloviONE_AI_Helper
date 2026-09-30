"""AI 설정 화면의 판단 — 무엇을 보이고 무엇을 저장하는가 (계획 3.13 · 3.14, D-515).

화면은 한 흐름이다: 연결 상태 → 제공자 → 인증 → 모델 → 실행 옵션 → AI 기능 → 저장 → 연결 확인. 이 모듈이 그 흐름에
필요한 값을 한 번에 준다(`overview`)와 저장을 한 트랜잭션으로 한다(`apply_config`).

## 비밀 값은 여기서 다루지 않는다

API 키는 비밀 칸 API(`/api/admin/secrets/{slot}`)가 쓰고 되읽지 않는다. 여기서는 저장돼 있는지와 끝 네 글자만
보인다 - 어느 키를 넣었는지 사람이 알아볼 수 있게.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.ai import concurrency
from app.ai.providers import base
from app.core.errors import ValidationAppError

JOB_TYPE_VERIFY = "llm_connection_test"
OBJECT_TYPE = "ai_config"

FEATURE_KEYS = ("chat_enabled", "assistant_narrative_enabled", "game_ai_enabled")
CONFIG_KEYS = {
    "generation_enabled": "ai_generation_enabled",
    "provider": "ai_provider",
    "auth_method": "ai_auth_method",
    "model": "ai_model",
    "timeout_seconds": "ai_timeout_seconds",
    "max_concurrency": "ai_max_concurrency",
}
MODEL_MAX_CHARS = 200


def _hint(secrets, slot: str) -> str | None:
    """저장된 키의 끝 네 글자. 짧은 값은 보이지 않는다 - 네 글자가 값의 큰 몫이 된다."""
    if secrets is None:
        return None
    try:
        value = secrets.get(slot)
    except Exception:  # noqa: BLE001 - 못 읽으면 보이지 않는다
        return None
    text = value.reveal() if value is not None else ""
    return f"끝자리 {text[-4:]}" if len(text) >= 16 else None


def providers_view(secrets) -> list[dict]:
    from app.core.secret_refs import STATUS_CONFIGURED

    out = []
    for spec in base.PROVIDERS.values():
        out.append({
            "key": spec.key,
            "label": spec.label,
            "help": spec.help,
            "auth_methods": [
                {
                    "key": m.key, "label": m.label, "help": m.help, "secret_slot": m.secret_slot,
                    "secret_set": bool(secrets is not None and secrets.status(m.secret_slot) == STATUS_CONFIGURED),
                    "secret_hint": _hint(secrets, m.secret_slot),
                }
                for m in spec.auth_methods
            ],
        })
    return out


def overview(db: Session, runtime, secrets, settings_cache) -> dict:
    config = runtime.config(db)
    values = settings_cache.current() if settings_cache is not None else {}
    return {
        "config": {
            "generation_enabled": config.generation_enabled,
            "provider": config.provider,
            "auth_method": config.auth_method,
            "model": config.model,
            "timeout_seconds": config.timeout_seconds,
            "max_concurrency": config.max_concurrency,
        },
        "state": runtime.status(db),
        "providers": providers_view(secrets),
        "features": {key: values.get(key) is True for key in FEATURE_KEYS},
        "limits": {
            "timeout_seconds": [concurrency.MIN_TIMEOUT_SECONDS, concurrency.MAX_TIMEOUT_SECONDS],
            "max_concurrency": [1, concurrency.MAX_CONCURRENCY],
        },
    }


def validate_config(current, changes: dict) -> dict:
    """바꿀 값을 합친 뒤 **한 벌로** 검사한다. 저장할 `{설정 키: 값}` 을 돌려준다."""
    merged = {
        "generation_enabled": current.generation_enabled, "provider": current.provider,
        "auth_method": current.auth_method, "model": current.model,
        "timeout_seconds": current.timeout_seconds, "max_concurrency": current.max_concurrency,
    }
    for key, value in changes.items():
        if key in merged and value is not None:
            merged[key] = value.strip() if isinstance(value, str) else value
    provider = merged["provider"]
    spec = base.provider_spec(provider)
    if provider and spec is None:
        raise ValidationAppError("지원하지 않는 AI 제공자입니다.")
    if spec is not None:
        if not merged["auth_method"] and len(spec.auth_methods) == 1:
            # 방식이 하나뿐인 제공자는 사람이 고를 것이 없다.
            merged["auth_method"] = spec.auth_methods[0].key
        if merged["auth_method"] and spec.method(merged["auth_method"]) is None:
            raise ValidationAppError(f"{spec.label}에서 쓸 수 없는 인증 방식입니다.")
    elif merged["auth_method"]:
        raise ValidationAppError("제공자를 먼저 고르세요.")
    if len(merged["model"]) > MODEL_MAX_CHARS:
        raise ValidationAppError(f"모델 이름은 {MODEL_MAX_CHARS}자까지 넣을 수 있습니다.")
    timeout = merged["timeout_seconds"]
    if not isinstance(timeout, int) or not (concurrency.MIN_TIMEOUT_SECONDS <= timeout <= concurrency.MAX_TIMEOUT_SECONDS):
        raise ValidationAppError(
            f"제한 시간은 {concurrency.MIN_TIMEOUT_SECONDS}초에서 {concurrency.MAX_TIMEOUT_SECONDS}초 사이여야 합니다."
        )
    slots = merged["max_concurrency"]
    if not isinstance(slots, int) or not (1 <= slots <= concurrency.MAX_CONCURRENCY):
        raise ValidationAppError(f"동시 실행 수는 1에서 {concurrency.MAX_CONCURRENCY} 사이여야 합니다.")
    if merged["generation_enabled"] and not (merged["provider"] and merged["auth_method"] and merged["model"]):
        raise ValidationAppError("AI 답변 생성을 켜려면 제공자, 인증 방식, 모델을 먼저 정하세요.")
    return {CONFIG_KEYS[k]: v for k, v in merged.items()}


def apply_config(db: Session, settings_cache, *, current, changes: dict, user_id: str, now: datetime) -> dict:
    """바뀐 값만 저장한다(설정 버전 기록이 남는다). 바뀐 `{설정 키: 새 값}` 을 돌려준다."""
    from app.settings.service import apply_setting

    target = validate_config(current, changes)
    values = settings_cache.current() if settings_cache is not None else {}
    changed = {}
    for key, value in target.items():
        if values.get(key) == value:
            continue
        apply_setting(db, settings_cache, key=key, value=value, updated_by=user_id, now=now)
        changed[key] = value
    return changed
