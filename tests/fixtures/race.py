"""경합 시험의 두 부품 — 창을 여는 바리어와, 같은 요청 여럿을 한꺼번에 쏘는 손.

## 왜 바리어인가

스레드 여럿을 그냥 띄우면 먼저 뜬 요청이 커밋까지 끝낸 뒤에야 늦은 요청이 사전 검사에 닿는 일이 흔하다. 그러면
늦은 요청은 「이미 있다」로 곱게 거절되고, 경합은 일어나지 않았는데 시험은 초록이다(거짓 초록 — 공지 닫기 경합
시험 `tests/regression/test_announcement_dismiss_race.py` 가 1차 시도에서 실제로 겪었다). 사전 검사 **바로 뒤**에
바리어를 세우면 N 개가 모두 「아직 없다」를 본 뒤에야 쓰기로 간다.

그 창이 실제로 열렸는지도 센다(`Window.opened`). 바리어가 깨졌으면(누가 제때 안 왔으면) 그 시험은 경합을 증명하지
못한 것이라 실패시킨다 — 요청이 뜻밖에 한 줄로 늘어서 도는 환경에서 조용히 초록이 되지 않게 한다.

## 요청은 진짜 요청이다

`fire` 는 시험 클라이언트 하나를 스레드 여럿이 함께 쓴다. 앱은 동기 처리기를 작업 스레드에서 돌리고 요청마다 자기
세션(자기 연결)을 연다 — `@pytest.mark.real_db` 의 전용 DB 위라 커밋도 진짜다. 응답 코드 · 봉투 문장 · 요청 끝
커밋까지 제품이 실제로 지나는 길을 그대로 지난다.
"""

from __future__ import annotations

import threading

BARRIER_TIMEOUT_SECONDS = 10
JOIN_TIMEOUT_SECONDS = 60


class Window:
    """N 개의 요청이 모두 사전 검사를 지난 뒤에야 쓰기로 가게 하는 문."""

    def __init__(self, parties: int) -> None:
        self.parties = parties
        self._barrier = threading.Barrier(parties)
        self._seen = threading.local()
        self._lock = threading.Lock()
        self.arrived = 0
        self.broken = False

    def wait(self) -> None:
        # 스레드마다 한 번만 기다린다 — 진 요청이 이긴 행을 다시 읽는 두 번째 호출은 그냥 지나간다.
        if getattr(self._seen, "done", False):
            return
        self._seen.done = True
        try:
            self._barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        except threading.BrokenBarrierError:
            with self._lock:
                self.broken = True
            return
        with self._lock:
            self.arrived += 1

    @property
    def opened(self) -> bool:
        return not self.broken and self.arrived == self.parties


def hold_after(monkeypatch, owner, name: str, window: Window) -> None:
    """`owner.name` 이 끝난 **뒤에** 문 앞에서 기다리게 한다(사전 검사 함수에 건다)."""
    real = getattr(owner, name)

    def held(*args, **kwargs):
        result = real(*args, **kwargs)
        window.wait()
        return result

    monkeypatch.setattr(owner, name, held)


def fire(n: int, call) -> list:
    """`call(i)` 를 스레드 n 개에서 동시에 부른다. 돌아온 값 또는 던진 예외를 순서대로 모은다."""
    results: list = [None] * n

    def run(i: int) -> None:
        try:
            results[i] = call(i)
        except BaseException as exc:  # noqa: BLE001 — 실패의 모양 자체를 시험이 본다
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT_SECONDS)
    return results


def statuses(responses) -> list[int]:
    """응답 코드 목록. 요청 자체가 예외로 끝났으면 그 자리는 599 다 — 5xx 로 센다."""
    return [getattr(r, "status_code", 599) for r in responses]


def messages(responses, status: int) -> list[str]:
    return [r.json()["error"]["message"] for r in responses if getattr(r, "status_code", None) == status]
