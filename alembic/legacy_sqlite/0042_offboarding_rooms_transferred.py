"""오프보딩이 채팅방 방장직을 넘긴 건수를 기록한다 (X8).

퇴사자가 그룹 채팅방의 **방장으로 남으면 아무도 그 방을 관리할 수 없다** — 사람을 더
부르거나 방 이름을 바꾸거나 방을 파할 사람이 없다. 그런데 오프보딩은 티켓만 옮기고
방은 손대지 않은 채 **"완료"** 를 보고했다. 관리자는 끝났다고 믿는다.

## 왜 컬럼을 새로 만드는가

이미 있는 것으로 대신할 수 없다. `ticket_moved`/`ticket_failed` 는 티켓 얘기고, 방 이전은
다른 사건이다(실패해도 티켓 이동은 유효하다). 응답에만 싣고 저장하지 않으면 **오프보딩
이력 화면이 "이 실행이 방을 몇 개 넘겼는지" 를 영원히 답하지 못한다** — 그 화면이 존재하는
이유가 "무엇을 했는가" 를 나중에 확인하는 것이다.

기본값 0 이라 기존 행은 "넘긴 방 없음" 으로 읽힌다. 그게 사실이다(그때는 안 했다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_TABLE = "offboarding_runs"
_COLUMN = "rooms_transferred"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
