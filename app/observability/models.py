"""관측성 모델 — 사용 이벤트 + 동기화 상태 (0026, PLAN Phase 4).

두 표의 성격이 다르다:
  * `UsageEvent` 는 **추가만 하는 로그**다. 저빈도 지점에서만 쓴다(모듈 `service.py` 의
    금지 규칙 참조).
  * `SyncStatus` 는 컴포넌트당 **한 행짜리 현재 상태**다. 워커가 upsert 하고 화면이 읽는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, OrgScopedMixin, UUIDPrimaryKeyMixin, utcnow

# 상태 어휘. 실제로 적히는 값은 이 셋뿐이다. 예전에는 'running' 도 있었는데, 미러 워커가
# 사라진 뒤로 이 표에 쓰는 잡은 회차가 **끝난 다음에** 결과만 적어서 그 값을 아무도 넣지
# 않았다. 아무도 안 넣는 값을 남겨 두면 화면을 만드는 사람이 오지 않는 상태를 그린다.
SYNC_IDLE = "idle"
SYNC_OK = "ok"
SYNC_ERROR = "error"

# 컴포넌트 이름. 지금 이 표에 쓰는 코드가 있는 것은 아래 둘뿐이다.
#
# 통합 검색 인덱스(0030). 운영자가 묻는 질문이 "무엇이 언제 마지막으로 갱신됐는가" 라서
# 원래 미러들과 같은 표를 쓴다.
COMPONENT_SEARCH = "search"
# 주간 프로젝트 헬스 스냅샷 잡. 미러도 인덱스도 아닌 **주기 잡**이지만 운영자가 묻는
# 질문은 검색 인덱스와 똑같다: "마지막으로 언제 돌았고, 이번에 무엇을 못 했나".
# 이 줄이 없으면 잡이 몇 주째 안 돌아도 화면에 아무 표시가 없고, 그러면 비어 있는 추세선이
# "아무도 안 쟀다" 가 아니라 "별일 없었다" 처럼 보인다.
COMPONENT_PROJECT_HEALTH = "project_health"

# 아래 둘은 없어진 노션 미러의 이름이다. **쓰는 코드가 없고**, 운영에 굳어 있던 행도
# 0015_drop_dead_mirror_sync_rows 가 지웠다. 이름만 남긴 이유는 하나다: 그 행이 다시
# 생겼을 때 사용자 화면에 배너가 굳지 않는다는 회귀 시험이 이 이름으로 행을 심는다
# (tests/integration/test_admin_backlog.py). 새 상태 행을 이 이름으로 만들지 않는다.
COMPONENT_TICKETS = "tickets"
COMPONENT_DOCUMENTS = "documents"


class UsageEvent(OrgScopedMixin, UUIDPrimaryKeyMixin, Base):
    """사람이 의도해서 한 드문 행동 하나."""

    __tablename__ = "usage_events"

    # 계정이 보관·삭제돼도 집계는 남아야 하므로 FK 를 걸지 않는다(감사 로그와 같은 판단).
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str | None] = mapped_column(String(48))
    object_id: Mapped[str | None] = mapped_column(String(64))
    # **개인정보·비밀은 넣지 않는다.** 기록 함수가 값을 검사하지 않으므로 부르는 쪽 책임이다.
    meta_json: Mapped[str | None] = mapped_column(JsonText)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )


class SyncStatus(Base):
    """동기화 컴포넌트 하나의 현재 상태(화면에 그대로 보여줄 공통 모양)."""

    __tablename__ = "sync_status"

    component: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SYNC_IDLE)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 소스가 페이지 상한에서 잘렸는가. 잘린 채로 prune 을 돌리면 나머지가 전부 삭제된다
    # (계획 C4) — 그 사실을 화면에도 드러낸다.
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    detail_json: Mapped[str | None] = mapped_column(JsonText)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
