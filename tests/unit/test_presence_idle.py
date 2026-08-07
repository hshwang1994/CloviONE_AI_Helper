"""유휴면 접속 표시를 갱신하지 않는다 (X12).

## 무엇이 틀렸었나

모니터만 끄고 간 사람은 탭이 여전히 보이는 상태다. 브라우저는 그 탭의 폴링을 멈추지 않고,
서버는 폴링 한 번을 '아직 여기 있다' 로 기록했다. 그래서 **퇴근한 사람이 밤새 '접속 중'**
이었다. 동료는 초록 점을 보고 말을 걸고, 답은 다음 날 아침에 왔다.

## 이 검사가 지키는 것 셋

1. 유휴 신호가 오면 `last_seen` 을 **쓰지 않는다** (지우지도, 과거로 돌리지도 않는다).
2. 그 결과로 온라인 창(120초)이 지나면 점이 **저절로 꺼진다**.
3. 돌아와서 한 번이라도 움직이면 **즉시** 다시 켜진다 — 늦게 켜지면 그건 그것대로 고장이다.

그리고 놀이(app/games)에는 이 신호를 걸지 않는다는 것도 함께 못박는다: 거기서 `last_seen`
은 표시가 아니라 **추첨 대상 풀**을 가르기 때문에(`_present_players`), 결과를 기다리며
화면만 보고 있는 사람이 조용히 빠진다.
"""

from datetime import datetime, timedelta

import pytest

from app.core.presence import PRESENCE_THROTTLE_SECONDS, should_touch

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 7, 19, 30, 0)


def test_idle_never_writes():
    """스로틀 창을 한참 지났어도 유휴면 쓰지 않는다."""
    assert should_touch(NOW - timedelta(hours=3), NOW, idle=True) is False
    assert should_touch(NOW - timedelta(seconds=PRESENCE_THROTTLE_SECONDS + 1), NOW, idle=True) is False


def test_idle_does_not_light_up_a_first_time_member():
    """`last_seen` 이 없는 사람은 원래 무조건 쓴다 — 유휴면 그 예외도 적용되지 않는다.

    이게 없으면 방을 처음 여는 순간(아직 아무 입력도 없는 상태) 점이 한 번 켜진다.
    """
    assert should_touch(None, NOW, idle=True) is False
    assert should_touch(None, NOW) is True


def test_present_user_is_unaffected():
    """기본값은 예전과 똑같다 — 파라미터를 안 붙이는 옛 클라이언트가 조용히 사라지면 안 된다."""
    assert should_touch(None, NOW, idle=False) is True
    assert should_touch(NOW - timedelta(seconds=31), NOW, idle=False) is True
    assert should_touch(NOW - timedelta(seconds=5), NOW, idle=False) is False


def test_chat_presence_goes_dark_after_the_online_window(db, make_user):
    """서비스와 온라인 판정을 **함께** 본다 — 헬퍼만 시험하면 배선이 빠져도 통과한다."""
    from app.team_chat import service

    me = make_user(email="idle-me@goodmit.co.kr")
    other = make_user(email="idle-other@goodmit.co.kr")
    room = service.create_or_get_direct(db, me, other_user_id=other.id, now=NOW)
    db.flush()

    # 자리에 있는 동안은 폴링이 접속 표시를 갱신한다.
    service.touch_presence(db, room, me, now=NOW)
    member = service.repository.get_member(db, room.id, me.id)
    assert member.last_seen == NOW
    assert service.is_online(member.last_seen, NOW) is True

    # 사람은 없고 탭만 남았다 — 폴링은 계속 오지만 표시는 갱신되지 않는다.
    later = NOW + timedelta(minutes=1)
    service.touch_presence(db, room, me, now=later, idle=True)
    assert member.last_seen == NOW, "유휴 폴링이 접속 표시를 갱신했다 — 퇴근한 사람이 계속 켜져 있다"

    # 온라인 창(120초)이 지나면 점이 저절로 꺼진다.
    much_later = NOW + timedelta(seconds=service.ONLINE_SECONDS + 1)
    service.touch_presence(db, room, me, now=much_later, idle=True)
    assert service.is_online(member.last_seen, much_later) is False


def test_returning_user_lights_up_again_immediately(db, make_user):
    """돌아온 사람이 30초를 기다려야 보이면, 유휴 감지가 기능 저하가 된다."""
    from app.team_chat import service

    me = make_user(email="back-me@goodmit.co.kr")
    other = make_user(email="back-other@goodmit.co.kr")
    room = service.create_or_get_direct(db, me, other_user_id=other.id, now=NOW)
    db.flush()
    service.touch_presence(db, room, me, now=NOW)
    member = service.repository.get_member(db, room.id, me.id)

    # 한참 자리를 비웠다 → 꺼진 상태.
    gone = NOW + timedelta(minutes=30)
    service.touch_presence(db, room, me, now=gone, idle=True)
    assert service.is_online(member.last_seen, gone) is False

    # 마우스를 한 번 움직였다 → 다음 폴링은 idle 없이 나가고, 그 자리에서 켜진다.
    back = gone + timedelta(seconds=1)
    service.touch_presence(db, room, me, now=back)
    assert member.last_seen == back
    assert service.is_online(member.last_seen, back) is True


def test_games_presence_does_not_take_the_idle_signal():
    """놀이의 `touch_presence` 는 이 신호를 받지 않는다.

    같은 값이라도 소비하는 쪽이 다르면 답이 달라진다. 놀이에서 `last_seen` 은 추첨 대상
    풀(`_present_players`)을 가르므로, 결과를 기다리며 화면만 보는 사람을 유휴로 잡으면
    그 사람이 사다리에서 조용히 빠진다.
    """
    import inspect

    from app.games import service as games_service

    params = inspect.signature(games_service.touch_presence).parameters
    assert "idle" not in params, (
        "놀이에 유휴 신호를 붙이려면 _present_players 부터 다시 보라 — "
        "표시가 아니라 추첨 대상 풀이 걸려 있다"
    )
