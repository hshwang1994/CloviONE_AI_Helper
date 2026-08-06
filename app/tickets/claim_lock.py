"""미할당 티켓을 **둘이 동시에 잡는 것**을 막는다 (Z1).

## 무엇이 잘못됐나

`claim_ticket` 은 담당자를 읽고 → Notion 에 쓴다. 그 사이에 **왕복이 두 번(0.5~3초)** 들어간다.
두 사람이 트리아지 화면에서 같은 티켓을 거의 동시에 누르면:

    A: 담당자를 읽는다 -> []          B: 담당자를 읽는다 -> []
    A: [A] 로 쓴다                    B: [B] 로 쓴다      <- A 를 덮어쓴다
    A: "배정됐습니다"                  B: "배정됐습니다"    <- **둘 다 성공 토스트**

A 는 자기 티켓이라고 믿고 일을 시작하는데 실제 담당자는 B 다. 아무 오류도 안 난다.
회의 중 트리아지에서 실제로 자주 일어나는 모양이다.

## 왜 프로세스 안 잠금으로 충분한가

웹은 **`--workers 1` 로 고정**돼 있다. systemd 유닛이 그렇게 못박고, 그 이유가 유닛 주석에
적혀 있다(로그인 무차별 대입 제한·채팅 제한 카운터가 전부 프로세스 안 메모리에 있어서
워커를 늘리면 제한이 N배 약해진다). 그래서 이 앱을 지나는 요청은 **전부 이 프로세스**를 지난다.

🔴 **워커를 늘리려면 이 잠금도 함께 옮겨야 한다.** 레이트 리미터와 **정확히 같은 조건**이다.
공유 저장소(Redis 또는 DB 행 잠금)로 바꾸기 전에는 워커 수를 올리면 안 된다.

## 못 막는 것 (알고 두는 한계)

Notion 에서 **직접** 담당자를 바꾸는 경우는 못 막는다. Notion REST 에 조건부 갱신(CAS)이
없어서 어떤 방법으로도 못 막는다. 여기서 닫는 것은 **포털 안의 경합**이고, 사용자가 겪는
경합의 대부분이 그것이다.
"""

from __future__ import annotations

import threading

from app.core.errors import AppError

# page_id -> Lock. 한 번 만든 잠금은 지우지 않는다 — 지우려면 "지금 아무도 안 쓴다" 를 다시
# 잠금 없이 판정해야 해서 같은 종류의 경합이 하나 더 생긴다. 티켓 수(수천)만큼 자라 봐야
# Lock 객체 하나가 수십 바이트라 문제가 되지 않는다.
_locks: dict[str, threading.Lock] = {}
_registry_guard = threading.Lock()


class ClaimInProgressError(AppError):
    status_code = 409
    code = "claim_in_progress"
    default_message = "다른 사람이 지금 이 티켓을 배정하고 있습니다. 잠시 후 다시 시도해 주세요."


def _lock_for(page_id: str) -> threading.Lock:
    with _registry_guard:
        lock = _locks.get(page_id)
        if lock is None:
            lock = threading.Lock()
            _locks[page_id] = lock
        return lock


class claim_guard:
    """이 티켓의 배정을 한 번에 한 사람만 진행하게 한다.

    **기다리지 않는다.** 이미 누가 진행 중이면 곧바로 409 다. 기다리게 하면 Notion 이 느린 날
    요청이 줄줄이 쌓여 워커가 잠기고, 사용자는 그냥 멈춘 화면을 본다. "지금은 안 된다" 를
    빨리 말해 주는 편이 낫다.
    """

    def __init__(self, page_id: str) -> None:
        self._lock = _lock_for(page_id)
        self._held = False

    def __enter__(self) -> "claim_guard":
        self._held = self._lock.acquire(blocking=False)
        if not self._held:
            raise ClaimInProgressError()
        return self

    def __exit__(self, *_exc) -> None:
        if self._held:
            self._lock.release()
            self._held = False
