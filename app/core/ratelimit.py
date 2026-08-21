"""토큰 버킷 rate limiter — **저장소가 DB 다** (D-192).

## 왜 옮겼나

예전에는 `dict` 하나였다. 그건 **한 프로세스 안에서만** 성립한다. 워커를 N개로 올리면
카운터도 N벌이 되고 요청이 프로세스에 흩어지므로, "분당 10회" 제한이 실질 "N×10회" 가 된다
— **워커를 늘리는 순간 로그인 무차별 대입 방어가 조용히 N배 약해진다.** 로그에도 아무
흔적이 없다. systemd 유닛이 워커 수를 1로 고정하고 있던 이유의 절반이 이것이었다.

**순서 규약: 공유 저장소를 먼저 만들고 그 다음에 워커를 올린다.** 이 파일이 그 앞쪽이다.

## 왜 자기 트랜잭션에서 커밋하는가

토큰 소비는 **요청이 실패해도 남아야 한다.** 요청 세션(`get_db`)을 쓰면 안 되는 이유가
바로 그것이다: 로그인 실패는 `AppError` 를 던지고 `get_db` 는 그때 세션을 통째로 롤백한다
— 그러면 방금 쓴 토큰도 함께 되감긴다. 즉 **틀린 비밀번호를 계속 넣는 공격자는 토큰을
하나도 안 쓴다.** 무차별 대입 방어가 정확히 방어해야 할 경우에만 꺼지는 셈이다.

그래서 이 리미터는 자기 세션을 열어 곧바로 커밋한다.

## 원자성

`INSERT … ON CONFLICT DO UPDATE … WHERE … RETURNING` 한 문장이다. 리필 계산과 차감과
"토큰이 남았는가" 판정이 전부 그 안에서 일어나므로, 두 요청이 같은 순간에 와도 토큰 하나를
둘이 나눠 갖지 못한다. 읽고-계산하고-쓰는 세 걸음으로 나누면 그 사이가 곧 우회 경로다.

행이 안 돌아오면(`WHERE` 가 거짓) 거절이다.

## 리필

`tokens(t) = min(capacity, tokens0 + (t - t0) × refill)`. 거절할 때는 행을 **안 건드린다** —
`updated_at` 이 그대로라 다음 호출이 같은 기준점에서 다시 계산한다. 선형 리필이라 결과가
같고, 문장이 하나 줄어든다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import Clock
from app.core.models_base import Base

# 리필된 토큰 수. 세 자리(INSERT 분기 제외)에서 같은 식을 쓰므로 한 번만 적는다.
_REFILLED = (
    "LEAST(:capacity, b.tokens + "
    "EXTRACT(EPOCH FROM (CAST(:now AS timestamp) - b.updated_at)) * :refill)"
)

_CONSUME_SQL = text(
    f"""
    INSERT INTO rate_limit_buckets AS b (key, tokens, updated_at)
    VALUES (:key, :capacity - 1, :now)
    ON CONFLICT (key) DO UPDATE
       SET tokens = {_REFILLED} - 1,
           updated_at = :now
     WHERE {_REFILLED} >= 1
    RETURNING b.tokens
    """
)

_PEEK_SQL = text(
    f"""
    SELECT {_REFILLED} AS tokens FROM rate_limit_buckets AS b WHERE b.key = :key
    """
)


class RateLimitBucket(Base):
    """키 하나의 토큰 버킷.

    키는 호출부가 정한다 — 로그인은 클라이언트 IP, 채팅·퀴즈·도우미는 사용자 id 다.
    앞에 용도 접두를 붙여(`login:1.2.3.4`) 서로 다른 리미터가 같은 행을 쓰지 않게 한다.

    오래된 행 청소는 `app/core/retention.py` 가 한다. 예전 인메모리 버전은 LRU 로 1만 개
    상한을 뒀는데, 그건 메모리 누수를 막으려던 것이고 표에서는 그 걱정이 없다.
    """

    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    tokens: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class RateLimiter:
    """공유 토큰 버킷 하나. `capacity` 만큼 버스트를 허용하고 초당 `refill_per_second` 회복한다."""

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        clock: Clock,
        session_factory,
    ) -> None:
        self._capacity = float(capacity)
        self._refill_per_second = float(refill_per_second)
        self._clock = clock
        # 요청 세션이 아니라 **자기 세션**이다(모듈 docstring). 이 인자를 지우고 요청
        # 세션을 받게 만들면 실패한 요청이 토큰을 안 쓰게 된다.
        self._session_factory = session_factory

    def _params(self, key: str) -> dict:
        return {
            "key": key,
            "capacity": self._capacity,
            "refill": self._refill_per_second,
            "now": self._clock.now(),
        }

    def allow(self, key: str) -> bool:
        """토큰 하나를 쓴다. 남아 있지 않으면 False(아무것도 안 쓴다)."""
        with self._session_factory() as db:
            row = db.execute(_CONSUME_SQL, self._params(key)).first()
            db.commit()
            return row is not None

    def reset(self, key: str) -> None:
        """이 키의 제한을 푼다. 로그인 성공처럼 "이제 정상 사용자다" 가 확인된 자리에서 쓴다."""
        with self._session_factory() as db:
            db.execute(
                text("DELETE FROM rate_limit_buckets WHERE key = :key"), {"key": key}
            )
            db.commit()

    def retry_after_seconds(self, key: str) -> float:
        """지금부터 토큰 하나가 회복될 때까지의 초. `allow()` 가 False 를 준 직후에 부른다.

        최선 추정이다 — 이 호출과 클라이언트의 재시도 사이에 같은 키로 다른 요청이 오면
        실제 대기는 조금 달라진다. 클라이언트가 상수를 추측하는 것보다는 훨씬 낫다:
        상수는 리미터를 재조정하는 날 조용히 어긋난다.
        """
        if self._refill_per_second <= 0:
            return 0.0
        with self._session_factory() as db:
            row = db.execute(_PEEK_SQL, self._params(key)).first()
        if row is None:
            return 0.0
        tokens = float(row[0])
        if tokens >= 1.0:
            return 0.0
        return (1.0 - tokens) / self._refill_per_second
