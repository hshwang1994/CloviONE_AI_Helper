"""In-process token-bucket rate limiter (spec §25.2).

Single-process deployment (spec §26.1 workers=1), so in-memory state is
authoritative. Clock-injected for deterministic tests.
"""

from __future__ import annotations

import threading

from app.core.clock import Clock



# CORE-12: 이 프로세스는 단일 워커로 계속 산다(spec §26.1) — `_buckets`는 지금까지 본
# 키(대개 클라이언트 IP)마다 행 하나를 영원히 들고 있고 정리 경로가 없었다. 내부
# 도구치고는 느린 누수지만 그래도 누수다. dict는 삽입 순서를 보존하므로 이를 LRU
# 순서로 재사용한다 — 키를 건드릴 때마다 pop 후 재삽입해 맨 뒤(최신)로 옮기고,
# 상한을 넘으면 맨 앞(가장 오래 안 쓴 키)을 하나 지운다. 시계 정밀도에 기대지
# 않는다.
_MAX_BUCKETS = 10_000


class RateLimiter:
    def __init__(self, capacity: int, refill_per_second: float, clock: Clock) -> None:
        self._capacity = float(capacity)
        self._refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _touch(self, key: str, value: tuple[float, object]) -> None:
        """호출자가 이미 락을 쥔 상태에서만 부른다."""
        self._buckets.pop(key, None)
        self._buckets[key] = value
        if len(self._buckets) > _MAX_BUCKETS:
            del self._buckets[next(iter(self._buckets))]

    def allow(self, key: str) -> bool:
        with self._lock:
            now = self._clock.now()
            tokens, last = self._buckets.get(key, (self._capacity, now))
            elapsed = (now - last).total_seconds()
            tokens = min(self._capacity, tokens + elapsed * self._refill_per_second)
            if tokens >= 1.0:
                self._touch(key, (tokens - 1.0, now))
                return True
            self._touch(key, (tokens, now))
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
