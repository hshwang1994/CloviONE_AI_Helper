"""설정 저장 경합 — 같은 키를 동시에 저장해도 5xx 가 없고 판 이력이 안 빈다.

## 무엇이 터졌나 (2026-09-06 실측)

설정 대부분은 첫 저장 전까지 `app_settings` 에 행이 없다(응답의 `is_default=true`). 그래서
**처음 저장하는 순간이 곧 기본키 INSERT 경합**이었다. `session_policy` 를 4-way 로 동시에
저장하면 200 하나 + `500 internal_error` 셋이 났고, 서버 로그는
`duplicate key value violates unique constraint "app_settings_pkey"` 였다.

그 하나를 `is_insert_race` 관용구로 감싸도 500 이 하나 남았다 — 이번엔 판 번호였다.
`snapshot_config` 이 `max(version)+1` 을 읽어 넣는데 재시도 예산이 1회라, 4-way 에서는 진
쪽 둘이 다시 같은 번호를 계산해 `uq_config_versions_object_version` 을 위반했다.

둘은 뿌리가 하나다 — **같은 키를 두 요청이 나란히 고친다.** 그래서 재시도를 겹치는 대신
`app/settings/service.py::_lock_or_insert` 가 그 행을 잠가 줄을 세운다.

## 이 파일이 못박는 것

정책 저장은 관리자가 가장 자주 두 번 누르는 단추이고, 두 관리자가 같은 정책을 동시에
손보는 것도 흔하다. 그때 「Internal server error」가 나오면 관리자는 정책이 적용됐는지
확인할 방법이 화면에 없다. 그래서 단언은 세 가지다: **5xx 0**, **최종값이 보낸 값 중
하나**, **판 이력이 한 칸도 안 빔**(누가 무엇을 시도했는지가 남는다).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import OperationalError

from app.core.db import make_engine, make_session_factory

# 전용 DB 가 필요하다(D-190) — 스레드마다 다른 커넥션이 서로의 커밋을 봐야 경합이 재현된다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

THREADS = 8


def _save(url: str, key: str, value, now):
    """한 요청이 하는 일 그대로 — 자기 세션에서 저장하고 커밋한다."""
    from app.settings.service import SettingsCache, apply_setting

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            try:
                result = apply_setting(
                    db, SettingsCache(), key=key, value=value, updated_by=None, now=now
                )
                db.commit()
                return ("ok", result["after"])
            except Exception as exc:  # noqa: BLE001 — 무엇이 새 나왔는지가 이 시험의 관심사다
                db.rollback()
                return ("error", f"{type(exc).__name__}: {exc}")
    finally:
        engine.dispose()


def _versions(url: str, key: str) -> list[int]:
    from app.core.versioning import list_versions
    from app.settings.service import OBJECT_TYPE

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            return sorted(row.version for row in list_versions(db, OBJECT_TYPE, key))
    finally:
        engine.dispose()


def _current(url: str, key: str):
    from app.settings.service import SettingsCache

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            return SettingsCache().load(db)[key]
    finally:
        engine.dispose()


def test_concurrent_first_save_of_a_key_with_no_row_never_500s(db_url, fake_clock):
    """DB 행이 아직 없는 키 — 예전에는 여기서 200 하나 + 500 셋이 났다."""
    key = "session_policy"
    now = fake_clock.now()
    assert _versions(db_url, key) == [], "이 키는 아직 저장된 적이 없어야 한다"

    wanted = [
        {"idle_timeout_seconds": 1800 + i, "absolute_timeout_seconds": 28800}
        for i in range(THREADS)
    ]
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(lambda i: _save(db_url, key, wanted[i], now), range(THREADS)))

    errors = [r[1] for r in results if r[0] == "error"]
    assert errors == [], f"동시 첫 저장이 예외로 샜다: {errors}"
    assert _current(db_url, key) in wanted, "최종값이 아무도 보내지 않은 값이다"
    # 판 이력이 한 칸도 안 빈다 — 진 쪽의 스냅샷이 사라지면 '누가 무엇을 시도했나'가 없어진다.
    assert _versions(db_url, key) == list(range(1, THREADS + 1))


def test_concurrent_save_of_an_existing_row_never_500s(db_url, fake_clock):
    """행이 이미 있는 키 — 반례 축이다. 첫 저장만 고치고 끝냈으면 여기가 남는다."""
    key = "trash_retention_days"
    now = fake_clock.now()
    seeded = _save(db_url, key, 5, now)
    assert seeded[0] == "ok", seeded

    wanted = [10 + i for i in range(THREADS)]
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(lambda i: _save(db_url, key, wanted[i], now), range(THREADS)))

    errors = [r[1] for r in results if r[0] == "error"]
    assert errors == [], f"동시 저장이 예외로 샜다: {errors}"
    assert _current(db_url, key) in wanted
    assert _versions(db_url, key) == list(range(1, THREADS + 2))


def test_single_save_still_records_the_value_it_started_from(db_url, fake_clock):
    """반례. 잠금을 넣느라 평범한 저장이 망가지지 않았는지 본다."""
    key = "conversation_retention_days"
    now = fake_clock.now()

    first = _save(db_url, key, 30, now)
    assert first == ("ok", 30)
    second = _save(db_url, key, 45, now)
    assert second == ("ok", 45)
    assert _current(db_url, key) == 45
    assert _versions(db_url, key) == [1, 2]

    from app.core.versioning import list_versions, load_snapshot
    from app.settings.service import OBJECT_TYPE

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            rows = sorted(list_versions(db, OBJECT_TYPE, key), key=lambda row: row.version)
            snapshots = [load_snapshot(row) for row in rows]
    finally:
        engine.dispose()
    # 첫 판은 「아직 저장된 적 없음」(레지스트리 기본값 90), 두 번째 판은 30 이다.
    assert [snap["value"] for snap in snapshots] == [90, 30]


# ── 스냅샷이 실패하면 새 값도 남지 않는다 ────────────────────────────────────
#
# `snapshot_config` 의 경합 재시도 경로는 `db.commit()` 을 한다(app/core/versioning.py) —
# 그 앞에 새 값이 세션에 올라와 있으면 그 커밋에 함께 실려 **굳는다**. 두 번째 시도마저
# 실패하면 설치는 `maintenance_mode=true` 인데 되돌릴 판도, `setting.update` 감사 행도,
# 갱신된 캐시도 없다 — 관리자는 「Internal server error」를 보고 아무것도 안 바뀐 줄 안다.
# 점검 모드는 전 사원의 쓰기를 멈추는 값이라 그 오해의 값이 가장 비싸다.


def _read_stored(url: str, key: str):
    """DB 에 **커밋된** 값. 행이 없으면 `None`."""
    import json as _json

    from app.settings.models import AppSetting

    engine = make_engine(url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            row = db.get(AppSetting, key)
            return None if row is None else _json.loads(row.value_json)
    finally:
        engine.dispose()


def test_a_snapshot_that_commits_then_fails_leaves_no_new_value_behind(
    db_url, fake_clock, monkeypatch
):
    from app.settings import service as settings_service
    from app.settings.service import SettingsCache, apply_setting

    key = "maintenance_mode"
    assert _versions(db_url, key) == [], "이 키는 아직 저장된 적이 없어야 한다"
    assert _read_stored(db_url, key) is None

    def commit_then_fail(db, **kwargs):
        # 재시도 경로가 실제로 하는 일: 스냅샷을 새로 뜨려고 커밋한다. 그 뒤 다시 부딪힌다.
        db.commit()
        raise OperationalError("INSERT INTO config_versions", {}, Exception("boom"))

    monkeypatch.setattr(settings_service, "snapshot_config", commit_then_fail)

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            with pytest.raises(OperationalError):
                apply_setting(
                    db, SettingsCache(), key=key, value=True,
                    updated_by=None, now=fake_clock.now(),
                )
            db.rollback()
    finally:
        engine.dispose()

    assert _versions(db_url, key) == [], "판 이력 없이 값만 남았다"
    assert _read_stored(db_url, key) is not True, (
        "되돌릴 판도 감사 행도 없이 점검 모드가 켜진 채 커밋됐다"
    )


def test_a_successful_save_still_commits_the_new_value_and_a_version(db_url, fake_clock):
    """반례 — 위 시험이 「아무것도 저장하지 않는다」로 통과하지 못하게 한다."""
    key = "maintenance_mode"
    assert _save(db_url, key, True, fake_clock.now()) == ("ok", True)
    assert _read_stored(db_url, key) is True
    assert _versions(db_url, key) == [1]
