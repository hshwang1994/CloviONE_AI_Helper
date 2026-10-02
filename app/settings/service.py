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
import logging
import threading
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import is_insert_race
from app.core.versioning import snapshot_config
from app.settings.models import AppSetting
from app.settings.registry import REGISTRY, SettingSpec, get_spec, validate_value

OBJECT_TYPE = "app_setting"

logger = logging.getLogger("app.settings")


# 판 번호를 읽지 못할 때만 쓰는 예전 나이 규칙(초, D-192). 평소에는 아래 판 번호가 다른 프로세스의 저장을 바로
# 따라잡는다(D-532).
DEFAULT_CACHE_TTL_SECONDS = 30.0

# 같은 프로세스 안에서 판 번호를 이보다 자주 묻지 않는다(초). 요청 길목과 워커가 부르므로 바쁜 웹 프로세스도
# 초당 질의 하나를 넘지 않는다.
STAMP_CHECK_INTERVAL_SECONDS = 1.0

# 설정 표 전체의 지문. 시각(`updated_at`)이 아니라 **내용**으로 만든다 - 시계를 멈춘 시험이나 같은 마이크로초에 들어온
# 두 저장도 가른다. 행은 수십 개라 초당 한 번 훑어도 싸다. 이 제품은 PostgreSQL 전용이다.
_STAMP_SQL = text(
    "SELECT md5(coalesce(string_agg(key || '=' || value_json::text, '|' ORDER BY key), '')) FROM app_settings"
)


class SettingsCache:
    """Thread-safe effective-settings cache (registry defaults + DB overrides).

    시작할 때 한 번 읽고 쓰기가 있을 때마다 새로 채운다. 그래서 소비자는 DB 세션 없이
    (``current()``) 유효 설정을 읽을 수 있다.

    **프로세스가 여럿이면 그것만으로는 부족하다**(D-192 · D-532). 값을 바꾼 것은 한 프로세스(웹 워커 넷 중 하나)인데
    나머지 웹 워커 · 배치와 대화형 워커 · 스케줄러는 자기 메모리의 옛 값을 계속 들고 있다. 예전에는 30초 나이 규칙만
    있어서 「사용하지 않음」을 누른 뒤 다시 읽으면 「안 됨」이 보이거나, 메일 상태 응답 한 번 안에서 옛 값과 새 값이
    섞였다. 이제 ``refresh_if_stale()`` 이 설정 표의 **판 번호**(내용의 지문)를 프로세스당 초당 한 번 확인하고, 다르면
    그 자리에서 다시 읽는다 - 다른 프로세스의 저장을 다음 요청에서 따라잡는다. 판 번호를 못 읽으면 예전 나이 규칙으로
    떨어진다.

    시각을 재는 데 `time.monotonic()` 을 쓴다 — 주입된 `Clock` 이 아니다. 이건 도메인 시각이 아니라 "이 메모리를 언제
    확인했나" 이고, 시계를 멈춰 둔 시험에서 확인이 영원히 안 일어나거나 매번 일어나면 안 된다.
    """

    def __init__(
        self, settings=None, *, ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        stamp_interval_seconds: float = STAMP_CHECK_INTERVAL_SECONDS,
    ) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, Any] | None = None
        self._loaded_at: float | None = None
        self._ttl = float(ttl_seconds)
        self._stamp: str | None = None
        self._checked_at: float | None = None
        self._stamp_interval = float(stamp_interval_seconds)
        # 살아 있는 `Settings` 객체(선택). 예전에는 load 마다 AI 설정을 그 위에 얹었다. AI 런타임이 캐시를 직접
        # 읽게 되면서(D-515) 얹을 값이 없다 - 부르는 쪽의 모양을 바꾸지 않으려고 받기만 한다.
        self._settings = settings

    @staticmethod
    def stamp(db: Session) -> str | None:
        """설정 표의 판 번호(내용의 지문). 질의 하나다. 못 읽으면 None 이다.

        세이브포인트 안에서 묻는다 - 저장 직후(`apply_setting` 이 같은 트랜잭션에서 `load` 를 부른다) 이 질의가 실패해도
        그 저장까지 되감지 않는다.
        """
        try:
            with db.begin_nested():
                return str(db.execute(_STAMP_SQL).scalar_one())
        except Exception:  # noqa: BLE001 - 판 번호가 없으면 부르는 쪽이 나이 규칙으로 떨어진다
            logger.warning("설정 판 번호를 읽지 못했다", exc_info=True)
            return None

    def load(self, db: Session) -> dict[str, Any]:
        # 판 번호를 **먼저** 읽는다. 둘 사이에 다른 프로세스가 저장하면 값이 판 번호보다 새것이 되고, 다음 확인이
        # 한 번 더 읽을 뿐이다. 순서가 반대면 새 판 번호에 옛 값을 묶어 그 저장을 영영 못 따라잡는다.
        stamp = self.stamp(db)
        values = {key: spec.default for key, spec in REGISTRY.items()}
        rows = db.execute(select(AppSetting)).scalars().all()
        for row in rows:
            if row.key in REGISTRY:
                values[row.key] = json.loads(row.value_json)
        now = time.monotonic()
        with self._lock:
            self._values = values
            self._loaded_at = now
            self._stamp = stamp
            self._checked_at = now
        return values

    def get_all(self, db: Session) -> dict[str, Any]:
        with self._lock:
            cached = self._values
        return cached if cached is not None else self.load(db)

    def get(self, db: Session, key: str) -> Any:
        return self.get_all(db).get(key)

    def current(self) -> dict[str, Any]:
        """Effective values without a DB session. Falls back to registry
        defaults if not yet loaded (e.g. before startup load).

        CORE-12: returns a **copy** — the old code returned the cache's own
        dict by reference, so any caller mutating what current() gave them
        (even by accident, e.g. building a response dict via `**current()`
        then `.update(...)`-ing a field back onto it) silently corrupted the
        shared cache for every other reader, with no DB write involved.
        `feature_flags.load_feature_flags()` already guards against exactly
        this for the same reason (its own docstring: "부르는 쪽이 dict를
        고쳐도 캐시가 오염되지 않게").
        """
        with self._lock:
            if self._values is not None:
                return dict(self._values)
        return {key: spec.default for key, spec in REGISTRY.items()}

    def current_value(self, key: str) -> Any:
        return self.current().get(key)

    def invalidate(self) -> None:
        with self._lock:
            self._values = None
            self._loaded_at = None

    def is_stale(self) -> bool:
        with self._lock:
            if self._values is None or self._loaded_at is None:
                return True
            return (time.monotonic() - self._loaded_at) >= self._ttl

    def refresh_if_stale(self, db: Session) -> None:
        """다른 프로세스가 설정을 바꿨으면 다시 읽는다(D-532).

        요청 길목(`app/core/deps.py::get_db`)과 워커(잡 직전 · 반복마다)가 부른다. 같은 프로세스 안에서는
        ``STAMP_CHECK_INTERVAL_SECONDS`` 에 한 번만 판 번호를 묻고, 대부분의 호출은 시각 비교 하나로 끝난다.
        판 번호를 못 읽으면 예전 나이 규칙(``DEFAULT_CACHE_TTL_SECONDS``)으로 떨어진다.
        """
        now = time.monotonic()
        with self._lock:
            empty = self._values is None
            if not empty and self._checked_at is not None and now - self._checked_at < self._stamp_interval:
                return
            self._checked_at = now
            known = self._stamp
        if empty:
            self.load(db)
            return
        current = self.stamp(db)
        if current is None:
            # 판 번호를 못 읽으면 예전 나이 규칙으로 판정한다.
            if self.is_stale():
                self.load(db)
            return
        if current != known:
            self.load(db)


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


def _locked_row(db: Session, key: str) -> AppSetting | None:
    """이 키의 행을 **잠근 채로** 읽는다. 없으면 None.

    `populate_existing=True` 를 붙이는 이유: 이 세션이 앞서 같은 행을 읽어 뒀으면
    SQLAlchemy 는 신원 지도(identity map)의 값을 그대로 주고 새로 읽은 값을 버린다 —
    잠금은 걸리는데 손에 든 값은 낡은 채가 되어, 「잠그고 읽었다」가 거짓이 된다.
    """
    return db.execute(
        select(AppSetting)
        .where(AppSetting.key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _lock_or_insert(
    db: Session,
    *,
    key: str,
    spec: SettingSpec,
    updated_by: str | None,
    now: datetime,
) -> tuple[AppSetting, Any]:
    """이 키의 행을 이 트랜잭션에 묶고 `(잠긴 행, 이 요청이 시작할 때의 값)` 을 돌려준다.

    ## 같은 키의 동시 저장이 두 군데서 터졌다

    1. **행이 아직 없을 때.** 설정 대부분은 첫 저장 전까지 `app_settings` 에 행이 없다
       (응답의 `is_default=true`). 그러니 **처음 저장하는 순간이 곧 기본키 INSERT 경합**이고,
       진 쪽은 `duplicate key value violates unique constraint "app_settings_pkey"` 로
       500 이 됐다(실측: 4-way 동시 저장에서 200 하나 + 500 셋).
    2. **판 번호.** `snapshot_config` 은 `max(version)+1` 을 읽어 넣는데, 같은 키를 동시에
       저장하면 여럿이 같은 번호를 계산한다. 그쪽 재시도 예산이 1회라 4-way 에서는 다시
       부딪혀 `uq_config_versions_object_version` 위반으로 또 500 이었다(실측).

    둘 다 뿌리가 하나다 — **같은 설정 키를 두 요청이 나란히 고친다**. 그래서 재시도를 겹겹이
    쌓는 대신 행 하나를 잠가 줄을 세운다. 줄을 서면 판 번호 경합도 같이 사라진다: 잠금을
    쥔 요청만 스냅샷을 뜨고, 다음 요청은 앞사람이 커밋한 뒤에 최신 번호를 읽는다
    (READ COMMITTED 에서 `FOR UPDATE` 는 잠금이 풀린 뒤 **최신 판**을 다시 읽는다).

    행이 없으면 잠글 것이 없으므로 넣어야 잠긴다. 그 INSERT 가 지면 승자 행을 잠그고 읽는다
    (`app/core/db.py::is_insert_race` 의 「넣어 보고 지면 남의 행을 읽는다」). SAVEPOINT 안에서
    넣기 때문에 실패해도 바깥 트랜잭션은 그대로 살아 있다.

    두 번 도는 이유: 승자가 자기 트랜잭션을 되감으면 다시 읽을 때 행이 없다. 그때는 한 번 더
    넣어 본다. 그 다음에도 없으면 경합이 아니라 다른 문제이므로 예외를 올린다.

    ## 이 자리에 **새 값**을 넣지 않는다

    잠그려고 넣는 행은 「이 요청이 시작할 때의 값」(= 레지스트리 기본값)을 든 자리표다.
    새 값은 스냅샷을 뜬 **뒤에** `apply_setting` 이 대입한다. 여기서 새 값을 미리 넣으면
    바로 다음 줄의 `snapshot_config` 이 경합 재시도에서 `db.commit()` 을 하는 순간
    (`app/core/versioning.py`) 그 새 값이 **되돌릴 근거 없이 굳는다** — 이어지는 시도가
    실패하면 설치는 `maintenance_mode=true` 인데 config_versions 행도 `setting.update`
    감사 행도 없고 캐시도 안 바뀐 채 관리자는 500 을 보고 「아무것도 안 바뀌었다」고 믿는다.
    """
    row = _locked_row(db, key)
    if row is not None:
        return row, json.loads(row.value_json)

    placeholder_json = json.dumps(spec.default, ensure_ascii=False)
    for _attempt in range(2):
        candidate = AppSetting(
            key=key,
            value_json=placeholder_json,
            value_type=spec.value_type,
            restart_required=spec.restart_required,
            updated_by=updated_by,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            # 우리가 넣었다 — 직전 값은 「아직 저장된 적 없음」, 곧 레지스트리 기본값이다.
            return candidate, spec.default
        except (IntegrityError, OperationalError) as exc:
            # 제약 이름을 대서 **이 경합만** 삼킨다. 이름을 안 대면 같은 표의 다른 유니크
            # 위반까지 조용히 넘어가고, 그 버그는 영영 안 보인다(D-191).
            if not is_insert_race(exc, constraint="app_settings_pkey"):
                raise
            winner = _locked_row(db, key)
            if winner is None:
                continue
            return winner, json.loads(winner.value_json)
    raise RuntimeError(f"설정 행을 넣지도 읽지도 못했습니다: {key}")


def lock_for_merge(db: Session, *, key: str, updated_by: str | None, now: datetime) -> Any:
    """설정 한 키의 행을 이 트랜잭션에 잠그고(없으면 기본값 자리표를 넣어 잠근다) 지금 값을 돌려준다.

    객체 설정의 **한 칸만** 바꾸는 저장(초기 설정의 선택, D-534)이 쓴다. 잠그기 전에 읽은 값으로 합치면 두 요청이 같은 옛 값에서
    각자 합쳐 한쪽의 칸을 잃는다 - 특히 행이 아직 없는 첫 저장에서는 `FOR UPDATE` 가 잠글 행이 없다(실측: 동시 두 저장에서 한
    칸이 사라졌다). 잠근 뒤 읽고 합친 값을 `apply_setting` 에 넘긴다(같은 트랜잭션이라 다시 잠가도 기다리지 않는다).
    """
    _row, current = _lock_or_insert(db, key=key, spec=get_spec(key), updated_by=updated_by, now=now)
    return current


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

    value_json = json.dumps(value, ensure_ascii=False)
    # 행을 먼저 잠근다. 스냅샷을 그 뒤로 미루는 이유는 정확성이다 — 잠그기 전에 읽은
    # 「직전 값」은 그 사이 남이 이미 갈아치웠을 수 있고, 그런 값으로 뜬 되돌리기 판은
    # 이 요청이 실제로 시작한 지점이 아니다.
    #
    # **순서가 계약이다**: 잠근다 → 직전 값을 읽는다 → 스냅샷을 뜬다 → **그 다음에** 새 값을
    # 대입한다. `snapshot_config` 은 경합 재시도에서 커밋하므로, 그 앞에 새 값이 세션에 올라와
    # 있으면 그 커밋에 함께 실려 굳는다(`_lock_or_insert` 의 자리표 문단).
    row, before = _lock_or_insert(
        db, key=key, spec=spec, updated_by=updated_by, now=now
    )

    # Before-snapshot for rollback (spec §14.4 step 4).
    snapshot_config(
        db, object_type=OBJECT_TYPE, object_id=key,
        snapshot={"key": key, "value": before}, created_by=updated_by,
    )

    row.value_json = value_json
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
