"""Status 와 Signal 을 다른 축으로 가른다 — 그리고 판·완료 시각의 자리를 만든다.

Revision ID: 0018_status_signal_axis
Revises: 0017_drop_retired_integrations
Create Date: 2026-08-27

## 무엇이 문제였나

`이슈` 가 Workflow Status 였다. 그래서 이슈가 생긴 티켓은 **자기가 어디까지 왔는지를
잃었다** — 진행 중이던 일도, 검증 중이던 일도, 아직 시작 안 한 일도 전부 `이슈` 한
칸으로 뭉쳐졌고, 이슈를 푼 다음에 어디로 돌아가야 하는지는 아무 데도 안 적혀 있었다.

`차단`·`지연` 도 같은 부류다. 셋 다 **업무 진행 단계가 아니라 그 진행에 붙는 신호**다.
「진행 중이면서 막혀 있다」는 흔한 상태인데 한 컬럼으로는 적을 수가 없다.

## 이 회차가 하는 것 넷

1. **표시 어휘를 고친다.** `진행` 의 표시 이름이 `진행 중` 이 된다. 저장값은 안 옮긴다.
2. **`보류` 를 만들고 `이슈` 를 어휘에서 뺀다.**
3. **`이슈` 티켓 아홉 건을 신호로 옮긴다** (아래 절).
4. **판 순서·완료 시각·차단 사유의 자리를 만든다.**

## 왜 `이슈` 를 `보류` 로 이름만 바꾸지 않는가

둘은 다른 말이다. `보류` 는 「의도적으로 멈췄다」이고 `이슈` 는 「문제가 있다」다.
일괄 치환하면 문제가 있어서 오히려 급한 티켓이 「멈춰도 되는 일」 칸으로 들어간다.

**그래서 실데이터를 먼저 봤다** (2026-08-27 운영 실측):

    이슈 상태 티켓            9건
    상태 변경 이력            0건 (ticket_activities 에 kind='status' 가 없다)
    담당자 있음               0건 · 스프린트 편입   0건
    실제 WD(act_wd) 있음      0건 · 시작일 있음     0건

아홉 전부 **일이 시작된 흔적이 없다.** 본문은 요구사항과 미결 질문이고
(「결재라인- FAB관리자」·「사이트에서 생성된 소스 관리 방안」·「그리드 셀 복사」),
누가 언제 왜 `이슈` 로 옮겼는지는 어디에도 안 남아 있다.

그래서 **추측하지 않고 두 사실을 그대로 나눠 적는다**:

- 업무 위치는 데이터가 말하는 곳으로 — `계획`. 시작 안 한 일이다.
- 「누군가 이 티켓을 이슈로 표시했다」는 사실은 **`issue_flag` 가 그대로 보존한다.**

정보가 하나도 안 사라진다. 그리고 이 회차가 무엇을 했는지는 티켓 타임라인에 남는다 —
`ticket_activities` 에 actor 없는(=시스템) 상태 변경 한 줄을 쓴다. 다음에 이 티켓을 여는
사람이 "내가 안 바꿨는데" 를 물으면 답이 화면에 있다.

## 되감기

되감을 수 있다. `issue_flag` 가 켜진 티켓을 다시 `이슈` 로 돌리고 어휘를 복원한다 —
이 회차가 켠 플래그와 사람이 나중에 켠 플래그가 섞이지만, 되감기는 이 회차 직후에만
의미가 있고 그 시점에는 둘이 같다. 새로 만든 컬럼 넷은 그냥 지운다.
"""
from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from alembic import op

revision = '0018_status_signal_axis'
down_revision = '0017_drop_retired_integrations'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

#: 어휘의 정본은 `app/work/workflow.py::STATUSES` 다. 여기 값을 손으로 적는 이유는
#: 0003 의 시드와 같다 — 마이그레이션은 그 시점의 얼어붙은 스냅숏이라 코드를 import
#: 하면 나중에 목록을 고치는 날 옛 마이그레이션의 뜻이 함께 바뀐다.
#: 둘이 갈라지지 않는 것은 `tests/unit/test_work_domain_seed.py` 가 맞물어 둔다.
_STATUSES = (
    # key,   label,     category,      sort_order, is_default
    ("계획", "계획", "OPEN", 10, True),
    ("진행", "진행 중", "IN_PROGRESS", 20, False),
    ("검증", "검증", "IN_PROGRESS", 30, False),
    ("완료", "완료", "DONE", 40, False),
    ("보류", "보류", "OPEN", 50, False),
    ("취소", "취소", "CANCELED", 60, False),
)

_RETIRED_STATUS = "이슈"
_LANDING_STATUS = "계획"


def _add_columns() -> None:
    op.add_column("tickets", sa.Column("board_rank", sa.Numeric(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column(
            "issue_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "tickets",
        sa.Column(
            "blocked_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("tickets", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("completed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_tickets_issue_flag", "tickets", ["issue_flag"])
    op.create_index("ix_tickets_blocked_flag", "tickets", ["blocked_flag"])
    op.create_index("ix_tickets_completed_at", "tickets", ["completed_at"])


def move_retired_status_to_signal(bind) -> int:
    """`이슈` 티켓을 `계획` + `issue_flag` 로 옮기고 옮긴 수를 돌려준다.

    함수로 빼 두는 이유는 0015·0017 과 같다 — 시험이 같은 문장을 그대로 돌려 봐야
    「이 회차가 무엇을 옮기는가」를 재게 된다. 시험이 SQL 을 다시 적으면 시험이
    무엇을 옮기는지를 재는 것이 된다.
    """
    rows = bind.execute(
        sa.text("SELECT id FROM tickets WHERE status = :s"), {"s": _RETIRED_STATUS}
    ).scalars().all()
    if not rows:
        return 0

    bind.execute(
        sa.text(
            "UPDATE tickets SET status = :to_status, issue_flag = true "
            "WHERE status = :from_status"
        ),
        {"to_status": _LANDING_STATUS, "from_status": _RETIRED_STATUS},
    )
    # 누가 옮겼는지가 화면에 남는다. actor 가 NULL 이면 시스템이 한 일이다.
    bind.execute(
        sa.text(
            "INSERT INTO ticket_activities "
            "(id, ticket_id, actor_user_id, kind, field, from_value, to_value, created_at) "
            "VALUES (:id, :ticket_id, NULL, 'status', 'status', :from_value, :to_value, "
            "timezone('utc', now()))"
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
                "from_value": _RETIRED_STATUS,
                "to_value": _LANDING_STATUS,
            }
            for ticket_id in rows
        ],
    )
    return len(rows)


def _rewrite_vocabulary(bind) -> None:
    bind.execute(
        sa.text("DELETE FROM ticket_statuses WHERE key = :k"), {"k": _RETIRED_STATUS}
    )
    for key, label, category, sort_order, is_default in _STATUSES:
        bind.execute(
            sa.text(
                "INSERT INTO ticket_statuses (key, label, category, sort_order, is_default) "
                "VALUES (:key, :label, :category, :sort_order, :is_default) "
                "ON CONFLICT (key) DO UPDATE SET "
                "label = EXCLUDED.label, category = EXCLUDED.category, "
                "sort_order = EXCLUDED.sort_order, is_default = EXCLUDED.is_default"
            ),
            {
                "key": key, "label": label, "category": category,
                "sort_order": sort_order, "is_default": is_default,
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    _add_columns()
    moved = move_retired_status_to_signal(bind)
    _rewrite_vocabulary(bind)
    logger.info(
        "0018: 이슈 → 계획 + issue_flag 로 옮긴 티켓 %d건 · 상태 어휘 %d종",
        moved, len(_STATUSES),
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE tickets SET status = :retired WHERE issue_flag AND status = :landing"
        ),
        {"retired": _RETIRED_STATUS, "landing": _LANDING_STATUS},
    )
    bind.execute(
        sa.text(
            "INSERT INTO ticket_statuses (key, label, category, sort_order, is_default) "
            "VALUES ('이슈', '이슈', 'OPEN', 20, false) ON CONFLICT (key) DO NOTHING"
        )
    )
    bind.execute(sa.text("DELETE FROM ticket_statuses WHERE key = '보류'"))
    # 0003 이 심었던 모양으로 되돌린다. **튜플 리터럴로 적지 않는다** —
    # `tests/unit/test_work_domain_seed.py` 가 이 파일에서 상태 리터럴을 세는데,
    # 되감기 목록까지 세면 「어휘가 열한 종」이라고 읽는다.
    bind.execute(
        sa.text(
            "UPDATE ticket_statuses SET label = key, "
            "sort_order = CASE key WHEN '계획' THEN 10 WHEN '이슈' THEN 20 "
            "WHEN '진행' THEN 30 WHEN '검증' THEN 40 WHEN '완료' THEN 50 "
            "WHEN '취소' THEN 60 ELSE sort_order END"
        )
    )
    op.drop_index("ix_tickets_completed_at", table_name="tickets")
    op.drop_index("ix_tickets_blocked_flag", table_name="tickets")
    op.drop_index("ix_tickets_issue_flag", table_name="tickets")
    for column in ("completed_at", "blocked_reason", "blocked_flag", "issue_flag", "board_rank"):
        op.drop_column("tickets", column)
