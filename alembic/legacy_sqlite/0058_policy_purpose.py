"""정책(Policy)에 purpose 컬럼 추가 (WF1 단독 결함 — admin_policies)

자매 엔티티 Prompt에는 `purpose`(무엇을 강제하는 규칙인지)가 있고 관리 콘솔에도
'용도' 열이 있는데, Policy에는 그 컬럼 자체가 없어 목록에서 "이 정책이 왜 있는지"를
말할 방법이 없었다(`app/prompts/models.py::Prompt.purpose` vs `Policy`에 대응 필드 부재).
화면만 고쳐선 해결 안 되는 스키마 비대칭이었다 — 그 컬럼을 신설한다.

`Prompt.purpose`와 같은 정의(`sa.Text()`, nullable, 기본값 없음)를 그대로 따른다.
기존 행은 전부 NULL(용도 미기재)로 시작하고, 화면에서 "설명 없음"으로 안내한다
(운영자가 되짚어 채울 값이라 앱이 추측해 채우지 않는다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("policies")}
    if "purpose" not in cols:
        op.add_column("policies", sa.Column("purpose", sa.Text()))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("policies")}
    if "purpose" in cols:
        op.drop_column("policies", "purpose")
