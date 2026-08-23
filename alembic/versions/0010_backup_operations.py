"""백업 행이 매니페스트와 파일 상태를 든다 (S12).

Revision ID: 0010_backup_operations
Revises: 0009_drop_external_automation
Create Date: 2026-08-23

## 세 칸이 왜 필요한가

**`manifest_json`** — 매니페스트의 정본은 세트 디렉터리 안의 `manifest.json` 이다
(백업과 **함께 이동해야** 하므로). 이 칸은 그 사본이고, 목록 화면이 행 50개마다 디스크를
읽지 않게 한다. 둘이 어긋나면 파일 쪽이 옳다.

**`file_state`** — 「내려받았으니 서버에서도 지운다」에 사람이 답한 결과다(D-204: 자동
삭제하지 않는다). 행까지 지우지 않는 이유는 감사 로그다 — 「그때 백업을 만들어 받아
갔다」는 사실은 남아야 한다. 그래서 상태를 두고, 목록은 그 행을 「파일 없음」으로 보여
준다. `NOT NULL DEFAULT 'present'` 라 기존 행은 전부 「있다」가 된다 — 그것이 사실이다.

**`downloaded_at`** — 마지막으로 내려받은 시각. **기록만 한다.** 서버가 이 값을 보고
파일을 지우는 일은 없다: 브라우저가 받다 만 것과 다 받은 것을 서버는 구별하지 못한다.

## 되감기

셋 다 내린다. 데이터는 안 돌아온다(이 저장소의 되감기 규약). `file_state` 가 사라지면
「사람이 지웠다」와 「없어졌다」를 다시 구별하지 못하게 되는데, 그것이 이 칸을 만든
이유이므로 되감기의 대가로 기록해 둔다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0010_backup_operations'
down_revision = '0009_drop_external_automation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `JsonText` 는 저장 타입이 `jsonb` 다(app/core/models_base.py) — `Text` 로 만들면
    # 모델과 스키마가 어긋나고 autogenerate diff 가 그것을 잡는다.
    op.add_column(
        'backups',
        sa.Column('manifest_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'backups',
        sa.Column(
            'file_state', sa.String(length=16), nullable=False, server_default='present'
        ),
    )
    op.add_column('backups', sa.Column('downloaded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('backups', 'downloaded_at')
    op.drop_column('backups', 'file_state')
    op.drop_column('backups', 'manifest_json')
