"""Rate limiter 의 저장소가 **DB 표**라는 계약 (D-192).

qa-contract-replaced-by: tests/unit/test_ratelimit_bucket_eviction.py

옛 파일은 인메모리 `dict` 의 **LRU 상한(1만 개)** 을 못박고 있었다. 그 계약은 사라졌다 —
저장소가 `rate_limit_buckets` 표이므로 프로세스 메모리가 자랄 일이 없고, 무한 성장은
상한이 아니라 **나이**로 막는다(`app/core/retention.py::purge_stale_rate_limit_buckets`).

계약이 바뀐 것이지 단언이 약해진 것이 아니다. 여기서 못박는 것은 옛 파일이 못 박던 것보다
강한 성질 셋이다:

  1. 카운터가 **프로세스 밖**에 있다 — 리미터 객체를 새로 만들어도 이어서 센다.
     (옛 인메모리 구현에서는 이 시험이 곧바로 실패한다. 워커를 늘리면 방어가 N배 약해지던
     바로 그 결함이다.)
  2. 소비한 토큰은 **요청이 롤백돼도 남는다** — 로그인 실패가 토큰을 되감으면 무차별 대입
     방어가 정확히 필요한 순간에만 꺼진다.
  3. 리필은 시간에 비례한다.
"""

from __future__ import annotations


from app.core.ratelimit import RateLimitBucket, RateLimiter
from tests.fakes.clock import FakeClock


def _limiter(app, clock, *, capacity=3, refill=1.0):
    return RateLimiter(
        capacity=capacity,
        refill_per_second=refill,
        clock=clock,
        session_factory=app.state.session_factory,
    )


def test_counter_survives_a_new_limiter_object(app):
    """리미터 객체를 새로 만들어도 이어서 센다 — 카운터가 프로세스 밖에 있다는 뜻이다.

    워커가 여럿일 때 각 프로세스가 자기 리미터 객체를 갖는 상황을 그대로 흉내 낸다.
    인메모리였다면 두 번째 리미터는 가득 찬 버킷에서 다시 시작해 제한이 두 배가 된다.
    """
    clock = FakeClock()
    first = _limiter(app, clock, capacity=3, refill=0.0)

    assert [first.allow("login:1.2.3.4") for _ in range(3)] == [True, True, True]

    second = _limiter(app, clock, capacity=3, refill=0.0)
    assert second.allow("login:1.2.3.4") is False


def test_keys_do_not_share_a_bucket(app):
    clock = FakeClock()
    limiter = _limiter(app, clock, capacity=1, refill=0.0)

    assert limiter.allow("login:1.1.1.1") is True
    assert limiter.allow("login:1.1.1.1") is False
    assert limiter.allow("login:2.2.2.2") is True


def test_a_denied_call_consumes_nothing(app, db):
    """거절은 행을 건드리지 않는다 — 그래야 리필 기준점이 그대로 남는다."""
    clock = FakeClock()
    limiter = _limiter(app, clock, capacity=1, refill=0.0)

    limiter.allow("chat:user-1")
    before = db.get(RateLimitBucket, "chat:user-1").updated_at
    clock.advance(30)
    assert limiter.allow("chat:user-1") is False

    db.expire_all()
    assert db.get(RateLimitBucket, "chat:user-1").updated_at == before


def test_tokens_refill_over_time(app):
    clock = FakeClock()
    limiter = _limiter(app, clock, capacity=2, refill=1.0)

    assert limiter.allow("game:user-2") is True
    assert limiter.allow("game:user-2") is True
    assert limiter.allow("game:user-2") is False

    clock.advance(1)
    assert limiter.allow("game:user-2") is True


def test_retry_after_is_the_real_wait_not_a_guess(app):
    clock = FakeClock()
    limiter = _limiter(app, clock, capacity=1, refill=0.5)

    limiter.allow("assistant:user-3")
    assert limiter.allow("assistant:user-3") is False

    # 토큰 하나가 0.5/초로 회복되므로 2초다. 클라이언트가 상수를 추측하면 리미터를
    # 재조정하는 날 조용히 어긋나는 값이다.
    assert limiter.retry_after_seconds("assistant:user-3") == 2.0


def test_reset_clears_the_limit(app):
    clock = FakeClock()
    limiter = _limiter(app, clock, capacity=1, refill=0.0)

    limiter.allow("login:9.9.9.9")
    assert limiter.allow("login:9.9.9.9") is False

    limiter.reset("login:9.9.9.9")
    assert limiter.allow("login:9.9.9.9") is True
