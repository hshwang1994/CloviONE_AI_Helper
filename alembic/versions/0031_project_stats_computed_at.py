"""projects.stats_computed_at — 진행률 · Health 캐시의 '계산 전' 과 '셀 것 없음' 을 가른다.

Revision ID: 0031_project_stats_computed_at
Revises: 0030_search_fold

`progress_pct` · `health_score` 의 NULL 은 두 뜻이었다: 한 번도 계산하지 않았다, 계산했는데
셀 작업(판정할 규칙)이 없었다. 목록은 둘 다 "아직 계산하지 않았습니다" 라고 했다.
이 칸이 **언제 계산했는가**를 따로 들고, 상태는 거기서 파생한다(`app/projects/stats.py::view`).

## 되채우기

값이 하나라도 있는 행은 이미 계산된 것이므로 지금 시각을 넣는다. 둘 다 NULL 인 행은 어느 쪽인지
모르므로 NULL 로 둔다 - 다음 스윕이 `stats_computed_at ASC NULLS FIRST` 로 가장 먼저 채운다.

## 되돌리기

칸과 인덱스를 지운다. 값은 파생 정보라 잃는 것이 없다.

(BACKLOG P-94 가 `0031` 을 예약해 두었지만 그 작업보다 이 회차가 먼저 들어간다. P-94 는 다음 빈 번호를 쓴다.)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_project_stats_computed_at"
down_revision = "0030_search_fold"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("stats_computed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_projects_stats_computed_at", "projects", ["stats_computed_at"])
    op.execute(
        "UPDATE projects SET stats_computed_at = (now() AT TIME ZONE 'UTC') "
        "WHERE progress_pct IS NOT NULL OR health_score IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_projects_stats_computed_at", table_name="projects")
    op.drop_column("projects", "stats_computed_at")
