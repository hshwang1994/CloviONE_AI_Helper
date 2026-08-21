"""문서 단위 열람 제한(SEC-10) — `document_cache.restricted`.

Notion 문서 1건에 평문 자격증명이 있고, 이 앱의 미러가 그것을 인증된 사용자 전원에게
보여 주는 문제(`docs/BACKLOG.md` SEC-10)를 완화한다. 원본 콘텐츠(실고객 Notion 워크스페이스)는
건드릴 수 없으므로, 앱 측에서 할 수 있는 두 대응 중 ① 문서 단위 열람 범위 제한을 구현한다
(② 원본 제거·회전은 사용자가 Notion에서 직접 해야 하는 별도 조치).

`classification_manual`(0018)과 같은 자리 — Notion에 대응 필드가 없는 순수 앱 측 플래그라
`app/team_docs/sync.py::_upsert`가 이 컬럼을 절대 건드리지 않는다(재동기화 때마다 제한이
풀리면 안 되므로).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("document_cache")}
    if "restricted" not in cols:
        op.add_column(
            "document_cache",
            sa.Column("restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index(
            "ix_document_cache_restricted", "document_cache", ["restricted"]
        )


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("document_cache")}
    if "restricted" in cols:
        op.drop_index("ix_document_cache_restricted", table_name="document_cache")
        op.drop_column("document_cache", "restricted")
