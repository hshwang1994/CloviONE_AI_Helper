"""오프보딩 중복 실행 방지 — 대상 사용자당 열린(안 되돌린) 실행은 하나뿐 (UA-15)

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-11

## 무엇이 문제였나

`run_offboarding()`은 대상 사용자에게 이미 열린(되돌리지 않은) 실행이 있는지 확인하지
않았다 — `preview()`의 `_open_run_view`가 경고만 보여줄 뿐, 실행 자체를 막는 코드는
없었다. 게다가 `service.py`가 느린 Notion 이동 단계 **전에** 장부(`OffboardingRun`)를
먼저 커밋한다(C3, "요청 세션이 롤백돼도 되돌리기의 입력이 사라지면 안 된다") — 그래서
더블클릭·새로고침으로 같은 대상에게 거의 동시에 두 번 요청이 가면, 두 번째 요청의
`OffboardingTicketMove.before_user_ids`가 이미 **첫 번째 실행이 넣은 후임**을 "원래
담당자"로 기록해 버린다. 그 상태에서 되돌리기를 부르면 후임에게서 후임으로 되돌리는
꼴이 되어 원래 담당자(퇴사자)는 영영 안 돌아온다 - 되돌리기 계약이 깨진다.

## 고치는 법

`offboarding_runs(user_id)`에 `undone_at IS NULL`(아직 안 되돌린 실행)일 때만 걸리는
부분 유일 인덱스를 건다 - approvals의 0052(`ux_approvals_pending_dedup`), prompts/
policies의 0053(`ux_{prompts,policies}_published_dedup`)과 같은 관용이다. 서비스
계층은 실행 전에 미리 확인(빠른 경로) + 그래도 경합하면 INSERT의 유일 인덱스 위반을
깨끗한 409로 바꾼다(느린 경로, 진짜 동시 요청 대비).

## 배포 전 기존 데이터

프로덕션 실측(2026-08-08, `docs/WORK_STATE.md` §5): `offboarding_runs` **0행** — 이
기능 자체가 아직 실사용 전이라 배포 전 정리가 필요 없다. 혹시 이 마이그레이션이 나중에
0행이 아닌 환경에 적용될 경우를 대비해, 그래도 안전하게 가장 최근 것만 "열린" 상태로
남기고 나머지는 건드리지 않는다(행을 지우거나 고치지 않는다 - `undone_at`을 인위적으로
채우면 그 실행이 실제로 되돌려진 것처럼 보여 거짓 기록이 된다. 그래서 정리가 아니라
**경고만** 남긴다 - 운영자가 직접 봐야 하는 상황이다).
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_INDEX_NAME = "ux_offboarding_runs_open_user"


def upgrade() -> None:
    bind = op.get_bind()
    if "offboarding_runs" not in sa.inspect(bind).get_table_names():
        return
    dupes = bind.execute(
        sa.text(
            "SELECT user_id, COUNT(*) AS n FROM offboarding_runs "
            "WHERE undone_at IS NULL GROUP BY user_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dupes:
        # 0052/0053과 달리 여기서는 행을 archived로 옮기는 식의 정리를 하지 않는다 -
        # undone_at을 건드리면 실제로 안 되돌린 실행을 되돌린 것처럼 거짓 기록하게 된다.
        # 운영자가 직접 보고 판단해야 하는 상황이라 인덱스 생성을 건너뛰고 경고만 남긴다.
        logger.warning(
            "0056: 이미 같은 사용자에게 열린 오프보딩 실행이 여럿이다(%d명) — "
            "부분 유일 인덱스를 걸지 않고 건너뛴다. 수동으로 확인 필요: %s",
            len(dupes), ", ".join(f"{row.user_id}={row.n}건" for row in dupes),
        )
        return
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("offboarding_runs")}
    if _INDEX_NAME not in indexes:
        op.create_index(
            _INDEX_NAME,
            "offboarding_runs",
            ["user_id"],
            unique=True,
            sqlite_where=sa.text("undone_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "offboarding_runs" not in sa.inspect(bind).get_table_names():
        return
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("offboarding_runs")}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name="offboarding_runs")
