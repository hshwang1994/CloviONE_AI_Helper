"""`SettingsCache.current()`가 내부 dict를 참조로 주면 안 된다 (CORE-12).

부르는 쪽이 `current()`가 준 dict를 고치면(실수로든 의도적으로든) 그 순간 캐시 자체가
오염된다 — DB 왕복도, `invalidate()`도 없이 다음 호출자부터 잘못된 값을 본다.
`feature_flags.load_feature_flags()`는 같은 이유로 이미 사본을 준다(그 모듈 자신의
docstring이 "부르는 쪽이 dict를 고쳐도 캐시가 오염되지 않게"라고 적어 뒀다) — 두 캐시가
같은 규약을 따라야 한다.
"""

from __future__ import annotations

import pytest

from app.settings.service import SettingsCache

pytestmark = pytest.mark.unit


def test_current_returns_a_copy_not_the_cached_dict(db):
    cache = SettingsCache()
    original = cache.load(db)
    snapshot = dict(original)

    got = cache.current()
    # 부르는 쪽이 받은 dict를 고쳐 본다 — 캐시가 오염되면 안 된다.
    got["session_policy"] = "오염"

    again = cache.current()
    assert again == snapshot, "current()가 반환한 dict를 고쳤더니 캐시 자체가 오염됐다"
    assert "session_policy" not in again or again["session_policy"] != "오염"
