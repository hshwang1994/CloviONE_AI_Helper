"""AI 사용 쿼터 — 사용자/기간별 상한 (0033, PLAN Phase 6).

## 왜 새 카운터 표를 만들지 않는가

소비량은 0026 의 `usage_events` 에서 **센다**. 별도 카운터 행을 두면 "증가" 쓰기가 AI 호출
경로마다 하나씩 생기고, 그 행은 곧 경합 지점이 된다(같은 행을 모든 요청이 UPDATE 한다).
`usage_events` 는 append-only 라 경합이 없고, 상한 판정은 인덱스(`created_at`, `user_id`)를
탄 COUNT 한 번이면 된다 — AI 호출 한 번의 비용에 비하면 무료다.

## 뜨거운 경로에는 걸지 않는다

계획서 C9 와 `app/observability/service.py` 규칙 그대로다. 그래서 쿼터가 붙는 곳은
**폴링이 아닌** 두 곳이다: AI 도우미 문장 생성(`/api/assistant/*?narrate=true`)과 채팅
답변(잡이 실제로 답을 만든 뒤에 센다). 문서 자동 생성은 S11 이 그 기능과 함께 걷어냈다.
놀이 퀴즈 AI 는 이미 분당 5건 레이트리밋이 걸려 있고 그 모듈은 관측성 import 자체가
금지돼 있어(테스트가 고정) 여기 들어오지 않는다 — 지어내지 않고 그대로 적어 둔다.

## user_id 가 NULL 이 아니라 빈 문자열인 이유

SQLite 는 UNIQUE 에서 NULL 을 서로 다른 값으로 취급한다. 전역 쿼터를 NULL 로 표현하면
`(scope_type, user_id, period)` 유니크가 전역 행에 대해 무효가 되어 '하루 상한'이 여러 개
생긴다. 0024 가 org_id 를 실값으로 백필한 것과 같은 판단이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, UUIDPrimaryKeyMixin, utcnow

SCOPE_GLOBAL = "global"
SCOPE_USER = "user"
ALL_SCOPES = (SCOPE_GLOBAL, SCOPE_USER)

PERIOD_DAY = "day"
PERIOD_MONTH = "month"
ALL_PERIODS = (PERIOD_DAY, PERIOD_MONTH)

# 전역 행의 user_id 자리표시자. 빈 문자열이라 UNIQUE 가 정상 동작한다.
GLOBAL_USER_ID = ""


class AiQuota(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_quotas"
    __table_args__ = (
        UniqueConstraint("scope_type", "user_id", "period", name="uq_ai_quota_scope"),
    )

    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, default=GLOBAL_USER_ID)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    # 0 이면 '차단'이라는 뜻이다(무제한이 아니다). 무제한을 원하면 행을 지운다 —
    # "상한 0 = 무제한"으로 해석하는 시스템은 언젠가 실수로 전부 열어 준다.
    max_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
