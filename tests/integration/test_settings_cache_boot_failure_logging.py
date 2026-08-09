"""A failed settings-cache load at boot must be logged, not swallowed silently
(CORE-12).

`create_app`'s startup previously did `except Exception: pass` around
`settings_cache.load(...)` with a comment claiming the only case is
"tables may not exist yet (before first migration)" — but the bare except
caught everything, including a locked or corrupted database. In that case
the app still boots (intentionally — a fresh install with no migrations
run yet is a normal state), but `settings_cache` silently falls back to
registry/env defaults with **no trace anywhere** that a DB-backed admin
override (session policy, retention days, etc.) failed to load and isn't
taking effect.
"""

from __future__ import annotations

import logging

import pytest

from app.main import create_app

pytestmark = pytest.mark.integration


def test_a_settings_cache_load_failure_at_boot_is_logged(settings, monkeypatch):
    from app.settings.service import SettingsCache

    def _boom(self, db):
        raise RuntimeError("simulated: locked or corrupt database")

    monkeypatch.setattr(SettingsCache, "load", _boom)

    captured: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            captured.append(record)

    main_logger = logging.getLogger("app.main")
    handler = _Collect()
    main_logger.addHandler(handler)
    try:
        create_app(settings)
    finally:
        main_logger.removeHandler(handler)

    assert captured, "설정 캐시 초기 로드 실패가 아무 로그도 안 남기고 조용히 넘어갔다"
    assert captured[0].levelno >= logging.WARNING
