"""CORE-12: RateLimiter._buckets must not grow without bound in a long-lived,
single-worker process (spec §26.1). Fully-refilled buckets are equivalent to
having no entry at all (allow() defaults to full capacity for unknown keys),
so they are safe to evict once the table grows past the cap.
"""

from __future__ import annotations

from app.core.ratelimit import _MAX_BUCKETS, RateLimiter
from tests.fakes.clock import FakeClock


def test_buckets_are_capped_when_many_distinct_keys_are_seen():
    clock = FakeClock()
    limiter = RateLimiter(capacity=5, refill_per_second=1.0, clock=clock)

    for i in range(_MAX_BUCKETS + 500):
        limiter.allow(f"client-{i}")

    assert len(limiter._buckets) <= _MAX_BUCKETS


def test_eviction_drops_the_least_recently_touched_key_and_keeps_the_newest():
    clock = FakeClock()
    limiter = RateLimiter(capacity=5, refill_per_second=1.0, clock=clock)

    limiter.allow("stale-key")

    for i in range(_MAX_BUCKETS):
        limiter.allow(f"client-{i}")

    assert "stale-key" not in limiter._buckets
    assert f"client-{_MAX_BUCKETS - 1}" in limiter._buckets
