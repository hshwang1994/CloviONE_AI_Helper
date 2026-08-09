"""Settings service: effective values + validated change pipeline (spec §14.4).

Change flow: validate → (optional) dry-run → before-snapshot (config_versions)
→ apply → audit. Every registry key is wired to a real consumer, so a change
takes effect immediately (or on the next new session for session_policy).
Effective values = registry defaults overlaid with DB rows, cached in-process
(single-process deployment), loaded at startup and refreshed on every write.

Note: settings here have no external side effect to health-check, so §14.4's
optional connection-test / auto-rollback steps do not apply — a bad value is
prevented up front by the registry validator, and any change is reversible via
the config_versions rollback endpoint.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.versioning import snapshot_config
from app.settings.models import AppSetting
from app.settings.registry import REGISTRY, get_spec, validate_value

OBJECT_TYPE = "app_setting"


class SettingsCache:
    """Thread-safe effective-settings cache (registry defaults + DB overrides).

    Loaded once at startup and refreshed on every write, so consumers can read
    effective values synchronously without a DB session (``current()``)."""

    def __init__(self, settings=None) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, Any] | None = None
        # 살아 있는 `Settings` 객체(선택). 있으면 load 마다 설치처 설정을 그 위에 얹는다 -
        # 이유는 app/core/tenant_config.py::apply_overrides 에 적어 뒀다. 없으면(테스트가
        # 캐시만 쓰는 경우) 아무 일도 안 한다.
        self._settings = settings
        # 부팅 시점의 env 값. 화면에서 값을 지웠을 때 여기로 되돌린다 - 이유는
        # app/core/tenant_config.py::OVERRIDABLE_KEYS 위에 적어 뒀다.
        self._settings_baseline: dict[str, Any] = {}

    def load(self, db: Session) -> dict[str, Any]:
        values = {key: spec.default for key, spec in REGISTRY.items()}
        rows = db.execute(select(AppSetting)).scalars().all()
        for row in rows:
            if row.key in REGISTRY:
                values[row.key] = json.loads(row.value_json)
        with self._lock:
            self._values = values
        # 락 밖에서 얹는다. 여기서 하는 일은 다른 객체의 속성 대입이라 이 락과 무관하고,
        # 락 안에서 하면 부팅 경로가 남의 객체를 잡은 채 도는 모양이 된다.
        from app.core.tenant_config import apply_overrides

        apply_overrides(self._settings, values, self._settings_baseline)
        return values

    def get_all(self, db: Session) -> dict[str, Any]:
        with self._lock:
            cached = self._values
        return cached if cached is not None else self.load(db)

    def get(self, db: Session, key: str) -> Any:
        return self.get_all(db).get(key)

    def current(self) -> dict[str, Any]:
        """Effective values without a DB session. Falls back to registry
        defaults if not yet loaded (e.g. before startup load)."""
        with self._lock:
            if self._values is not None:
                return self._values
        return {key: spec.default for key, spec in REGISTRY.items()}

    def current_value(self, key: str) -> Any:
        return self.current().get(key)

    def invalidate(self) -> None:
        with self._lock:
            self._values = None


def effective_settings(db: Session, cache: SettingsCache) -> dict[str, Any]:
    values = cache.get_all(db)
    return {
        key: {
            "value": values.get(key, spec.default),
            "type": spec.value_type,
            "restart_required": spec.restart_required,
            "description": spec.description,
            # 저장 행 유무가 아니라 '현재 값이 기본값과 같은가'로 판정한다. apply_setting은
            # 값을 기본값으로 되돌려도 AppSetting 행을 유지하므로, 행 기준으로 보면 한 번
            # 건드린 키는 영원히 '변경됨'으로 남아 오해를 준다(round6 감사 E).
            "is_default": values.get(key, spec.default) == spec.default,
        }
        for key, spec in REGISTRY.items()
    }


def dry_run(key: str, value: Any) -> dict:
    """Validate without applying (spec §14.4 step 2)."""
    validate_value(key, value)
    spec = get_spec(key)
    return {"key": key, "value": value, "restart_required": spec.restart_required, "ok": True}


def apply_setting(
    db: Session,
    cache: SettingsCache,
    *,
    key: str,
    value: Any,
    updated_by: str | None,
    now: datetime,
) -> dict:
    spec = get_spec(key)
    # 문자열 값은 저장 전에 정규화한다 - 안 하면 관리 화면이 보여 주는 값(깨끗함)과 실제
    # 저장된 값(앞뒤 공백 포함)이 달라진다. 화면에서 쓰는 NotionConsole.jsx 는 이미
    # `.trim()` 하지만, 그 화면을 거치지 않는 raw API PUT(system_admin)이나 DB 직접
    # 수정으로 공백 섞인 값이 들어오면 조회 URL 에 `%20` 이 그대로 붙는다(개행이면
    # `httpx.InvalidURL`). 검증기(`_non_empty_str` 등)는 `strip()` 해서 **모양만** 보고
    # 원문은 그대로 통과시키므로 여기서 막지 않으면 아무 데도 안 걸린다.
    if isinstance(value, str) and spec.value_type == "string":
        value = value.strip()
    validate_value(key, value)

    row = db.get(AppSetting, key)
    before = json.loads(row.value_json) if row is not None else spec.default

    # Before-snapshot for rollback (spec §14.4 step 4).
    snapshot_config(
        db, object_type=OBJECT_TYPE, object_id=key,
        snapshot={"key": key, "value": before}, created_by=updated_by,
    )

    if row is None:
        row = AppSetting(
            key=key,
            value_json=json.dumps(value, ensure_ascii=False),
            value_type=spec.value_type,
            restart_required=spec.restart_required,
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.value_json = json.dumps(value, ensure_ascii=False)
        row.updated_by = updated_by
    row.updated_at = now
    db.flush()
    # Reload (not just invalidate) so current() reflects the new value without a
    # DB session — an invalidate would drop back to registry defaults.
    cache.load(db)
    # spec §13.5의 8개 알림 유형 중 'Maintenance 공지'가 여기 하나다 — maintenance_mode가
    # False→True로 실제 켜지는 전이에만 보낸다(끌 때·이미 켜진 값 재저장까지 매번 보내면
    # 관리자가 값을 다시 저장할 때마다 전 사용자가 알림을 또 받는다). apply_setting은
    # update_setting과 rollback_setting(내부적으로 apply_setting을 부른다) 양쪽의 공통
    # 저장 경로라 여기 둔다 — 라우터 한쪽에만 있으면 rollback으로 maintenance_mode가
    # 다시 켜질 때 공지가 조용히 안 나간다.
    if key == "maintenance_mode" and value is True and before is not True:
        from app.notifications.service import notify_active_users

        notify_active_users(
            db, type_="maintenance_announcement", title="시스템 점검 안내",
            body=maintenance_message(db, cache), now=now,
        )
    return {"key": key, "before": before, "after": value, "restart_required": spec.restart_required}


def rollback_setting(
    db: Session,
    cache: SettingsCache,
    *,
    key: str,
    version: int,
    updated_by: str | None,
    now: datetime,
) -> dict:
    from app.core.versioning import get_version, load_snapshot

    snap = load_snapshot(get_version(db, OBJECT_TYPE, key, version))
    return apply_setting(
        db, cache, key=key, value=snap["value"], updated_by=updated_by, now=now
    )


def is_maintenance_mode(db: Session, cache: SettingsCache) -> bool:
    return bool(cache.get(db, "maintenance_mode"))


def maintenance_message(db: Session, cache: SettingsCache) -> str:
    return str(cache.get(db, "maintenance_message") or "현재 시스템 점검 중입니다.")
