"""In-process token-bucket rate limiter (spec §25.2).

Single-process deployment (spec §26.1 workers=1), so in-memory state is
authoritative. Clock-injected for deterministic tests.
"""

from __future__ import annotations

import threading

from app.core.clock import Clock


class RateLimiter:
    def __init__(self, capacity: int, refill_per_second: float, clock: Clock) -> None:
        self._capacity = float(capacity)
        self._refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        with self._lock:
            now = self._clock.now()
            tokens, last = self._buckets.get(key, (self._capacity, now))
            elapsed = (now - last).total_seconds()
            tokens = min(self._capacity, tokens + elapsed * self._refill_per_second)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True
            self._buckets[key] = (tokens, now)
            return False

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def retry_after_seconds(self, key: str) -> float:
        """Seconds until ``key`` would earn back 1 token, given current state.

        Meant to be called right after ``allow()`` returned False so the
        caller can tell the client a real wait time instead of a hardcoded
        client-side guess (which silently drifts if the limiter is ever
        retuned). Best-effort: a concurrent request for the same key between
        this call and the client's retry can shift the real wait slightly.
        """
        with self._lock:
            now = self._clock.now()
            tokens, last = self._buckets.get(key, (self._capacity, now))
            elapsed = (now - last).total_seconds()
            tokens = min(self._capacity, tokens + elapsed * self._refill_per_second)
            if tokens >= 1.0 or self._refill_per_second <= 0:
                return 0.0
            return (1.0 - tokens) / self._refill_per_second
