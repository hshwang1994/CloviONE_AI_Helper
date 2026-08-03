"""presence 쓰기 스로틀 30초 (PLAN Phase 4 — 스케일 심).

놀이 방은 1.2초마다 폴링한다. 예전 임계값 2초는 "두 번에 한 번은 쓴다"는 뜻이라 사실상
스로틀이 아니었고, 읽기 폴링이 그대로 쓰기 부하가 됐다(SQLite writer 는 하나다).

이 검사는 두 방향을 다 본다:
  * 30초 안에는 쓰지 않는다(부하 감소가 실제로 일어나는가)
  * 그런데 **재접속은 즉시** 반영된다(돌아온 사람이 30초 동안 안 보이면 안 된다)
  * 그리고 소비자 임계값(PRESENCE_SECONDS=90)보다 충분히 작다 — 그렇지 않으면 실제로
    붙어 있는 사람이 오프라인으로 깜빡인다
"""

from datetime import datetime, timedelta

import pytest

from app.core.presence import PRESENCE_THROTTLE_SECONDS, should_touch

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 12, 0, 0)


def test_throttle_is_thirty_seconds():
    assert PRESENCE_THROTTLE_SECONDS == 30.0


def test_no_write_within_the_window():
    assert should_touch(NOW - timedelta(seconds=1.2), NOW) is False
    assert should_touch(NOW - timedelta(seconds=29), NOW) is False


def test_write_after_the_window():
    assert should_touch(NOW - timedelta(seconds=30), NOW) is True
    assert should_touch(NOW - timedelta(seconds=31), NOW) is True


def test_first_sighting_always_writes():
    assert should_touch(None, NOW) is True


def test_a_clock_that_went_backwards_does_not_wedge_the_throttle():
    """시계가 뒤로 가면 경과가 음수가 된다. 그때 안 쓰면 시계가 정상으로 돌아올 때까지
    영원히 스로틀에 걸려 그 사람이 오프라인으로 보인다."""
    assert should_touch(NOW + timedelta(seconds=60), NOW) is True


def test_throttle_is_well_below_the_online_threshold():
    """스로틀이 접속자 판정 창에 가까워지면 붙어 있는 사람이 깜빡이기 시작한다.

    이 두 값은 **함께** 봐야 하는 짝이다 — 한쪽만 조정하면 그 순간 증상이 나온다.
    """
    from app.games.service import PRESENCE_SECONDS

    assert PRESENCE_THROTTLE_SECONDS * 2 <= PRESENCE_SECONDS, (
        f"스로틀 {PRESENCE_THROTTLE_SECONDS}s 가 접속자 판정 창 {PRESENCE_SECONDS}s 에 비해 "
        "너무 크다 — 창 안에 갱신이 두 번은 들어가야 안 깜빡인다"
    )


def test_game_presence_writes_are_throttled(db, make_user):
    """서비스 계층에서 실제로 스로틀이 도는지. 헬퍼만 시험하면 배선이 빠져도 통과한다."""
    from app.games import service

    host = make_user(email="host@goodmit.co.kr")
    room = service.create_room(
        db, host=host, title="방", game_type="ladder",
        max_players=8, allow_spectators=True, config={}, now=NOW,
    )
    db.flush()
    member = service.repository.get_member(db, room.id, host.id)
    assert member.last_seen == NOW

    # 1.2초 뒤(= 폴링 한 번) — 쓰지 않는다.
    service.touch_presence(db, room, host, now=NOW + timedelta(seconds=1.2))
    assert member.last_seen == NOW, "폴링마다 쓰고 있다 — 읽기가 쓰기가 된다"

    # 31초 뒤 — 쓴다.
    later = NOW + timedelta(seconds=31)
    service.touch_presence(db, room, host, now=later)
    assert member.last_seen == later


def test_reconnect_is_written_immediately_even_inside_the_window(db, make_user):
    """돌아온 사람이 30초 동안 목록에 안 뜨면, 스로틀이 기능 저하가 된다."""
    from app.games import service

    host = make_user(email="host2@goodmit.co.kr")
    room = service.create_room(
        db, host=host, title="방", game_type="ladder",
        max_players=8, allow_spectators=True, config={}, now=NOW,
    )
    db.flush()
    member = service.repository.get_member(db, room.id, host.id)
    member.active = False  # 폴링이 끊겨 비활성으로 표시된 상태
    db.flush()

    just_now = NOW + timedelta(seconds=1)
    service.touch_presence(db, room, host, now=just_now)
    assert member.active is True, "재접속이 스로틀에 걸려 무시됐다"
    assert member.last_seen == just_now
