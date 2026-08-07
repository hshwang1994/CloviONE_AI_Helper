"""AI 쿼터의 '확인 → 소비' 를 **사람 단위로 직렬화**한다 (Z15).

## 무엇이 잘못됐나

상한 판정은 두 걸음이다: `enforce()` 가 지금까지 쓴 수를 **세고**, 나중에 `record_call()` 이
그 수를 **늘린다**. 그 사이는 잠기지 않은 창이다.

    A: used=9 < 10 -> 통과            B: used=9 < 10 -> 통과
    A: AI 호출                        B: AI 호출
    A: 10 으로 기록                    B: 11 로 기록     <- 상한 10 인데 11회를 썼다

아무 오류도 안 난다. 화면의 숫자만 상한을 넘어 있고, 그것도 다음에 누가 볼 때까지는 아무도
모른다. 창이 넓을수록 자주 일어나는데 하필 그 창 안에 **AI 호출 자체**(수 초)가 들어 있다.

## 왜 프로세스 안 잠금으로 충분한가

웹은 **`--workers 1` 로 고정**돼 있다. systemd 유닛이 그렇게 못박고, 그 이유가 유닛 주석에
적혀 있다(로그인 무차별 대입 제한, 채팅 전송 제한 카운터가 전부 프로세스 안 메모리에 있어서
워커를 늘리면 제한이 N배 약해진다). 그래서 이 앱을 지나는 요청은 **전부 이 프로세스**를
지나고, 프로세스 안 잠금이 곧 전역 잠금이다.

🔴 **워커를 늘리려면 이 잠금도 함께 옮겨야 한다.** `app/tickets/claim_lock.py`, 레이트
리미터와 **정확히 같은 조건**이다. 공유 저장소(Redis 또는 DB 행 잠금)로 바꾸기 전에는
워커 수를 올리면 안 된다. 올리는 날 이 파일을 같이 고치지 않으면 상한은 다시 새는데,
증상은 "청구서가 예상보다 크다" 라서 몇 달 뒤에나 드러난다.

## 왜 기다리는가 (claim_ticket 은 안 기다리는데)

티켓 배정은 "지금은 안 된다" 가 옳은 답이다 - 어차피 남이 가져간 티켓이다. 쿼터는 다르다.
앞 요청이 끝나고 나면 **답이 달라질 수 있다**(앞 요청이 실패하면 내 차례는 통과다). 여기서
409 를 던지면 상한이 남아 있는 사람에게 "안 된다" 고 거짓말을 하게 된다. 그래서 기다린다.

무한정 기다리지는 않는다. 창 안에 외부 AI 호출이 들어 있어 앞 요청이 오래 걸릴 수 있고,
스레드풀이 한 사람 때문에 잠기면 안 된다. 시간을 넘기면 잠금 없이 진행한다 - 그 순간
막으려던 것은 '드물게 한 번 더 쓰는 것' 인데, 대신 얻는 것이 '전 사용자 정지' 라면
바꿀 이유가 없다(쿼터는 비용 통제 장치이지 보안 장치가 아니다, `service.enforce` 주석).
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("app.quotas")

# 앞 요청을 기다려 주는 최대 시간(초). AI 호출 한 번의 상한(러너 타임아웃)보다 넉넉하되,
# 스레드가 사람 하나 때문에 영원히 잠기지 않을 만큼 짧다.
WAIT_SECONDS = 30.0

# user_id -> Lock. 한 번 만든 잠금은 지우지 않는다 - 지우려면 "지금 아무도 안 쓴다" 를 다시
# 잠금 없이 판정해야 해서 같은 종류의 경합이 하나 더 생긴다(claim_lock.py 와 같은 판단).
# 사용자 수(1000명 규모)만큼 자라 봐야 Lock 객체 하나가 수십 바이트다.
_locks: dict[str, threading.Lock] = {}
_registry_guard = threading.Lock()


def _lock_for(user_id: str) -> threading.Lock:
    with _registry_guard:
        lock = _locks.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _locks[user_id] = lock
        return lock


class quota_guard:
    """이 사람의 쿼터 판정을 한 번에 하나만 진행하게 한다.

    잠금을 못 잡아도 **예외를 던지지 않는다** - 모듈 docstring 의 마지막 문단이 이유다.
    """

    def __init__(self, user_id: str, *, wait_seconds: float = WAIT_SECONDS) -> None:
        self._lock = _lock_for(str(user_id))
        self._wait = wait_seconds
        self._held = False

    def __enter__(self) -> "quota_guard":
        self._held = self._lock.acquire(timeout=self._wait)
        if not self._held:
            logger.warning(
                "AI 쿼터 잠금을 %.0f초 안에 못 잡았다. 이번 판정은 잠금 없이 진행한다 "
                "(동시 요청이 상한을 함께 지날 수 있다)",
                self._wait,
            )
        return self

    def __exit__(self, *_exc) -> None:
        if self._held:
            self._lock.release()
            self._held = False
