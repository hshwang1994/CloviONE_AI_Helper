"""AI 호출의 동시 실행 슬롯 — 웹과 워커가 **함께** 센다 (계획 3.13, D-515).

`app/llm/service.py` 의 슬롯 락을 옮겼다. 파일 N 개를 원자적으로 만드는(O_EXCL) 방식이라 같은 파일시스템을 보는
프로세스(웹, 배치 워커, 대화형 워커)가 한 벌의 슬롯을 나눠 쓴다. 예전에는 웹과 대화형 워커의 생성 경로가 이 슬롯을
지나지 않아 설정한 동시 실행 수가 주간 요약에만 걸렸다.

## 왜 앞에서부터 채우는가

무작위로 고르면 슬롯이 고르게 차서, 동시 실행 수를 줄인 뒤 어느 슬롯이 아직 도는지 사람이 못 읽는다. 앞에서부터
채우면 `llm.lock` 하나만 있으면 한 개가 도는 중이라는 뜻이다. 파일 이름은 옛 이름을 그대로 쓴다 - 업그레이드
순간 옛 프로세스의 살아 있는 리스를 새 프로세스가 못 보면 그 사이 호출이 겹친다.

## 리스 길이

제한 시간보다 길게 잡는다. 짧으면 아직 도는 호출의 슬롯을 다음 호출이 빼앗고, 무한이면 프로세스가 죽었을 때 영영
못 잡는다.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from app.core.worker_lock import WorkerLock

LOCK_FILENAME = "llm.lock"
LOCK_GRACE_SECONDS = 60
DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 8
MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 60


def clamp_timeout(seconds) -> int:
    """설정값을 [MIN, MAX] 로 접는다. 제한 시간이 없으면 요청 한 칸이 영원히 잠긴다."""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, value))


def clamp_concurrency(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY
    return max(1, min(MAX_CONCURRENCY, number))


def _lock_path(data_dir, slot: int) -> Path:
    return Path(data_dir) / (LOCK_FILENAME if slot == 0 else f"llm.{slot}.lock")


def _new_lock(data_dir, slot: int, *, lease: float) -> WorkerLock:
    # 소유자를 PID 만으로 두면 같은 프로세스의 두 번째 호출이 자기 것처럼 보인다. 호출마다 다른 토큰을 붙인다.
    owner = f"ai:{os.getpid()}:{secrets.token_hex(4)}"
    return WorkerLock(_lock_path(data_dir, slot), lease_seconds=lease, owner=owner)


class SlotLock:
    """슬롯 N 개 중 **하나라도** 비어 있으면 잡는다. 전부 차 있으면 실패한다."""

    def __init__(self, data_dir, *, slots: int, lease_seconds: float) -> None:
        self._locks = [_new_lock(data_dir, slot, lease=lease_seconds) for slot in range(max(1, slots))]
        self._held: WorkerLock | None = None

    def acquire(self) -> bool:
        for lock in self._locks:
            if lock.acquire():
                self._held = lock
                return True
        return False

    def release(self) -> None:
        held, self._held = self._held, None
        if held is not None:
            held.release()


def concurrency_lock(data_dir, *, timeout_seconds: int, max_concurrency: int) -> SlotLock:
    lease = clamp_timeout(timeout_seconds) + LOCK_GRACE_SECONDS
    return SlotLock(data_dir, slots=clamp_concurrency(max_concurrency), lease_seconds=lease)
