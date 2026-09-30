"""일시 장애 때 요청이 줄줄이 제한 시간까지 매달리지 않게 하는 작은 차단기 (계획 3.15, D-515).

일시 장애는 다음 호출을 막지 않는다 - 다음 실제 호출이 다시 시도하고 성공하면 저절로 정상이다. 다만 제공자가 몇 분
동안 응답하지 않으면 그 사이 모든 사용자 요청이 제한 시간(60초)을 다 기다린다. 그래서 2분 안에 일시 실패가 세 번
이어지면 30초 동안만 호출을 곧바로 「일시 장애」로 돌려보낸다. 30초 뒤 첫 호출은 실제로 보낸다(반쯤 열림). 성공하면
바로 닫히고, 실패하면 다시 30초다. 복구를 늦추지 않는 것이 목적이라 창과 쉬는 시간을 짧게 잡는다.

프로세스 메모리에 둔다. 웹과 워커가 각자 센다 - 한쪽이 연 차단기가 다른 쪽을 막지 않는다. 그 대신 DB 를 매 요청
잠그지 않는다.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta

WINDOW = timedelta(seconds=120)
THRESHOLD = 3
COOLDOWN = timedelta(seconds=30)


class Breaker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[tuple, deque] = {}
        self._open_until: dict[tuple, datetime] = {}
        self._probing: set[tuple] = set()

    def allow(self, key: tuple, now: datetime) -> bool:
        with self._lock:
            until = self._open_until.get(key)
            if until is None:
                return True
            if now < until or key in self._probing:
                return False
            # 반쯤 열림 - 한 호출만 실제로 보낸다. 그 결과가 닫을지 다시 열지 정한다.
            self._probing.add(key)
            return True

    def success(self, key: tuple) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._open_until.pop(key, None)
            self._probing.discard(key)

    def failure(self, key: tuple, now: datetime) -> None:
        with self._lock:
            if key in self._probing:
                self._probing.discard(key)
                self._open_until[key] = now + COOLDOWN
                return
            window = self._failures.setdefault(key, deque())
            window.append(now)
            while window and now - window[0] > WINDOW:
                window.popleft()
            if len(window) >= THRESHOLD:
                self._open_until[key] = now + COOLDOWN
                window.clear()

    def is_open(self, key: tuple, now: datetime) -> bool:
        with self._lock:
            until = self._open_until.get(key)
            return until is not None and now < until
