"""projects.org_id 되채우기 — 조직이 없는 프로젝트를 근거 있는 조직으로 채운다 (계획 3.2).

Revision ID: 0033_project_org_backfill
Revises: 0032_ticket_completed_backfill

조직이 없는 프로젝트는 소속을 판정할 수 없어 전체 관리자만 보고, 그 프로젝트의 티켓도 함께 닫힌다.
제품은 이런 행을 만들 수 없다(`create_project` 가 늘 조직을 넣는다). 남은 것은 믹스인의 기본값이
생기기 전에 들어온 옛 행이다. 정합성 화면은 이 행을 「조직이 지정되지 않은 프로젝트」로 세지만,
화면에는 프로젝트의 조직을 고치는 자리가 없다. 그래서 여기서 한 번 채우고 검사는 감시로 남긴다.

## 근거가 있는 값만 쓴다

1. 프로젝트의 부서가 속한 조직(`org_units.org_id`). 부서가 조직을 말하므로 추측이 아니다.
2. 부서가 없으면 기본 조직(`DEFAULT_ORG_ID`) - 0024 가 옛 데이터 전부를 그 조직으로 옮겼다.
   그 행이 없는 설치에서는 조직이 하나뿐일 때만 그 조직을 쓴다.

조직이 여럿인데 기본 조직도 없으면 채우지 않는다. 고를 근거가 없고, 잘못 고르면 그 프로젝트가
다른 조직에 열린다. 그런 행은 정합성 화면에 그대로 남는다.

## 되돌리기

하지 않는다. 채운 값과 처음부터 있던 값을 가를 표시가 없어서, 되돌리면 멀쩡한 행까지 비운다.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0033_project_org_backfill"
down_revision = "0032_ticket_completed_backfill"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.0033")

# `app/org/constants.py::DEFAULT_ORG_ID` 의 값이다. 마이그레이션은 앱 코드를 import 하지 않는다 -
# 앱 상수가 나중에 바뀌어도 이 마이그레이션이 한 일은 바뀌면 안 된다.
DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"

# 빈 문자열은 볼 필요가 없다 - `projects.org_id` 는 `organizations.id` 를 가리키는 FK 라 그 값이 들어갈 수 없다.
_MISSING = "p.org_id IS NULL"


def upgrade() -> None:
    conn = op.get_bind()
    from_dept = conn.execute(sa.text(
        "UPDATE projects p SET org_id = d.org_id FROM org_units d "
        f"WHERE p.dept_id = d.id AND d.org_id IS NOT NULL AND d.org_id <> '' AND {_MISSING}"
    )).rowcount

    fallback = conn.execute(sa.text(
        "SELECT id FROM organizations WHERE id = :default"
    ), {"default": DEFAULT_ORG_ID}).scalar()
    if fallback is None:
        orgs = conn.execute(sa.text("SELECT id FROM organizations LIMIT 2")).scalars().all()
        fallback = orgs[0] if len(orgs) == 1 else None
    from_default = 0
    if fallback is not None:
        from_default = conn.execute(sa.text(
            f"UPDATE projects p SET org_id = :org WHERE {_MISSING}"
        ), {"org": fallback}).rowcount
    remaining = conn.execute(sa.text(f"SELECT count(*) FROM projects p WHERE {_MISSING}")).scalar()
    logger.info(
        "0033 projects.org_id 되채우기: 부서의 조직 %s건, 기본 조직 %s건, 채우지 못한 프로젝트 %s건",
        from_dept, from_default, remaining,
    )


def downgrade() -> None:
    # 되돌리지 않는다(머리말). 스키마 변경이 없으므로 내려가는 것 자체는 안전하다.
    pass
