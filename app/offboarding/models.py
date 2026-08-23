"""오프보딩 실행 기록 (Phase 6 — 관리자 백로그 최우선 항목).

**왜 표가 필요한가.** 오프보딩은 한 번에 여러 개를 바꾼다: 티켓 N건의 담당자, 계정의 활성
상태, 보관 여부, 세션. 감사 로그(`audit_log`)는 "무슨 일이 있었다"를 남기지만 **되돌리기의
입력**이 되지는 못한다 — before/after 가 JSON 텍스트라 코드가 그걸 다시 파싱해 되돌리는 순간
감사 로그의 형식이 곧 실행 계약이 되어 버린다. 그래서 되돌리기에 필요한 값만 별도의 표에
1급 컬럼으로 남긴다. 감사 로그는 그대로 함께 남긴다(둘은 목적이 다르다).

**되돌릴 수 없는 버튼은 아무도 못 쓴다.** 퇴사 처리는 잘못 누르면 사람 하나의 업무가 통째로
남에게 넘어가고 계정이 잠긴다. 되돌릴 방법이 화면 안에 없으면 관리자는 그 버튼을 영원히
안 누르고, 결국 아무도 쓰지 않는 기능이 된다.

## `ticket_uid` 에 FK 를 걸지 않는 이유

`ticket_cache` 행은 동기화 prune 이 지운다(Notion 에서 티켓이 사라지면). FK 를 걸면 두 가지
중 하나가 된다: CASCADE 면 되돌리기 이력이 조용히 증발하고, RESTRICT 면 prune 이 실패해
**티켓 미러 전체가 멈춘다**(`TicketComment` docstring 이 같은 함정을 기록한다). 여기 남는 값은
'그때 그 티켓이 무엇이었는가'라는 **기록**이므로, 참조 무결성보다 보존이 우선이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    OrgScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

# 실행 상태. 부분 실패를 'completed' 로 뭉개지 않는다 — 12건 중 3건이 실패한 실행을 성공으로
# 적어 두면 화면이 그 3건을 다시는 보여 주지 못한다.
# `running` 은 **끝까지 가지 못한 실행**이다(C3). 실행은 요청 하나 안에서 동기로 끝나므로,
# 남의 눈에 `running` 으로 보이는 행은 사실상 전부 중단된 실행이다 — 계정 단계에서 예외가
# 났거나, 프로세스가 죽었거나, DB 잠금에 걸렸거나. 이 상태가 없으면 중단된 실행이
# `completed` 로 남아 **"다 옮겼다"고 거짓말**한다.
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_PARTIAL = "partial"
RUN_UNDONE = "undone"
RUN_UNDO_PARTIAL = "undo_partial"

# 티켓 한 건의 이동 상태.
# `pending` 은 **소스를 부르기 직전에 먼저 적어 둔 표시**다(C3). Notion PATCH 가 나갔는지
# 안 나갔는지 모르는 유일한 구간을 침묵이 아니라 기록으로 만든다 — 되돌릴 수는 없지만
# (직전 담당자를 아직 모른다) 관리자가 그 티켓을 확인할 수는 있다.
MOVE_PENDING = "pending"
MOVE_MOVED = "moved"
MOVE_SKIPPED = "skipped"        # 이미 그 상태였다(소스를 부르지 않았다)
MOVE_FAILED = "failed"
MOVE_REVERTED = "reverted"
MOVE_REVERT_FAILED = "revert_failed"

# 되돌리기 대상으로 삼는 상태(실제로 무언가를 바꾼 것들).
REVERTIBLE_MOVES = frozenset({MOVE_MOVED, MOVE_REVERT_FAILED})


class OffboardingRun(OrgScopedMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """오프보딩 한 번. 대상 사용자·후임·무엇을 바꿨는지·되돌렸는지."""

    __tablename__ = "offboarding_runs"
    __table_args__ = (
        # 되돌리지 않은 실행은 사람당 하나뿐이다(마이그레이션 0056). 두 개가 열려 있으면
        # 되돌리기가 어느 쪽 값을 복원해야 하는지 알 수 없다. **부분** 유니크라 이미 되돌린
        # (`undone_at IS NOT NULL`) 이력은 몇 번이든 쌓인다 — 전체 유니크로 만들면 같은
        # 사람을 두 번 오프보딩할 수 없게 된다.
        Index(
            "ux_offboarding_runs_open_user", "user_id", unique=True,
            postgresql_where=text("undone_at IS NULL"),
        ),
    )

    # 대상(퇴사자). 계정은 지우지 않고 비활성/보관만 하므로 FK 가 끊길 일이 없다.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    # 후임. 없을 수 있다(티켓을 미할당으로 되돌리는 경우).
    successor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RUN_COMPLETED)
    # 계정에 실제로 무엇을 했는지. 되돌리기가 이 값만 되돌린다 — 원래 비활성이던 계정을
    # 되돌리기가 활성으로 만들어 버리면 없던 권한을 주는 셈이 된다.
    deactivated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text)

    # 방장직을 넘긴 그룹 채팅방 수 (X8, 0042). 퇴사자가 방장으로 남으면 **아무도 그 방을
    # 관리할 수 없다** — 사람을 더 부르거나 방을 파할 사람이 없어진다.
    rooms_transferred: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    ticket_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ticket_moved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ticket_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    undone_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    undone_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    undo_error: Mapped[str | None] = mapped_column(Text)


class OffboardingTicketMove(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """티켓 한 건의 이동 기록. **되돌리기의 입력이 되는 표다.**

    `before_user_ids` 는 옮기기 **직전**의 담당자 구성(앱 user_id)이다. 소스 id 가 아니라
    앱 id 로 적는 이유: 되돌릴 때 다시 소스 id 로 해석되므로 그 사이 Notion 연결이 바뀌어도
    "그 사람에게 되돌린다"가 유지된다.
    """

    __tablename__ = "offboarding_ticket_moves"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offboarding_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 딥링크·감사가 쓰는 외부 키. 자체 UUID(uid)는 알면 함께 남기되 FK 는 걸지 않는다
    # (모듈 docstring 참조).
    ticket_page_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ticket_uid: Mapped[str | None] = mapped_column(String(36))
    # 옛 소스가 매긴 번호. 이름이 아니다 — 아래 `ticket_key` 가 이름이다.
    ticket_number: Mapped[int | None] = mapped_column(Integer)
    # 옮길 때 이 티켓이 불리던 이름 `<CODE>-<SEQ>` (D-282). `ticket_title` 과 같은
    # 이유로 스냅숏이다 — 되돌리기 화면은 「그때 무엇을 옮겼는가」를 보여 준다.
    ticket_key: Mapped[str | None] = mapped_column(String(64))
    ticket_title: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    before_user_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")
    after_user_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=MOVE_MOVED)
    error: Mapped[str | None] = mapped_column(Text)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime)
