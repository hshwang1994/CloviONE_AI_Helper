"""아바타 지문(캐시 버스팅 `?v=`)이 naive UTC 를 실제로 UTC 로 해석하는지.

`avatar_updated_at` 은 앱 전체 규약대로 naive UTC 다(`app/core/models_base.py`).
naive datetime 에 tzinfo 없이 `.timestamp()` 를 부르면 파이썬은 이를 **서버 로컬
시각**으로 해석해 버린다 — 이 저장소의 개발 호스트가 이미 UTC 가 아닌 Asia/Seoul
(UTC+9)이라, 수정 전에는 여기서 계산한 스탬프가 실제 UTC epoch 와 9시간 어긋났다.

두 함수(`profiles/router.py::_avatar_url`, `core/people.py::avatar_map`)가 각각
독립적으로 같은 실수를 갖고 있었으므로 둘 다 확인한다. 값은 항상 `tzinfo=timezone.utc`
를 명시한 변환과 비교한다 — 그래야 이 테스트 자체가 실행 호스트의 로컬 시간대에
좌우되지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit

NAIVE_UTC = datetime(2026, 1, 1, 0, 0, 0)  # naive UTC 자정
EXPECTED_EPOCH = int(NAIVE_UTC.replace(tzinfo=timezone.utc).timestamp())


class _FakePref:
    avatar_stored_name = "avatar.png"
    avatar_updated_at = NAIVE_UTC


def test_avatar_url_stamp_treats_naive_datetime_as_utc():
    from app.profiles.router import _avatar_url

    url = _avatar_url(_FakePref(), "user-1")
    assert url == f"/api/profile/avatar/user-1?v={EXPECTED_EPOCH}"


def test_avatar_url_with_no_avatar_updated_at_falls_back_to_zero():
    class _NoStampPref:
        avatar_stored_name = "avatar.png"
        avatar_updated_at = None

    from app.profiles.router import _avatar_url

    assert _avatar_url(_NoStampPref(), "user-1") == "/api/profile/avatar/user-1?v=0"


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeRow:
    def __init__(self, user_id, avatar_updated_at, stored_name="avatar.png", default_key=None):
        self.user_id = user_id
        self.avatar_updated_at = avatar_updated_at
        # 사진이 없는 사람도 이 맵에 실린다 — 그 사람이 **고른 기본 그림**을 화면이
        # 알아야 하기 때문이다(D-349 회차의 Avatar 시스템). 그때 URL 은 `None` 이다.
        self.avatar_stored_name = stored_name
        self.avatar_default_key = default_key


class _FakeDB:
    """`avatar_map`이 던지는 select 문을 실행하지 않고 미리 준비한 행을 그대로 낸다 —
    이 테스트가 확인하려는 것은 쿼리가 아니라 스탬프 산술이다."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _FakeResult(self._rows)


def test_avatar_map_stamp_treats_naive_datetime_as_utc():
    from app.core.people import avatar_map

    db = _FakeDB([_FakeRow("user-1", NAIVE_UTC)])
    result = avatar_map(db, ["user-1"])
    assert result == {
        "user-1": {
            "url": f"/api/profile/avatar/user-1?v={EXPECTED_EPOCH}",
            "default_key": None,
        }
    }


def test_avatar_map_carries_the_chosen_default_even_without_a_photo():
    """🔴 사진이 없는 사람도 이 맵에 실린다.

    예전에는 질의가 `avatar_stored_name IS NOT NULL` 로 좁혀 있었다. 그때는 사진이 없으면
    화면이 아무것도 안 그렸으니 그것으로 충분했다. 지금은 사진이 없는 사람도 그림을 갖고,
    그 사람이 **직접 고른 그림**이 있으면 화면이 그것을 알아야 한다.
    """
    from app.core.people import avatar_map

    db = _FakeDB([_FakeRow("user-2", None, stored_name=None, default_key="penguin")])
    assert avatar_map(db, ["user-2"]) == {
        "user-2": {"url": None, "default_key": "penguin"}
    }
