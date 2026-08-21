"""티켓 첨부(이미지·PDF) 표.

지시서 §4 "티켓에 연결된 이미지가 있다면 현재 화면과 티켓 상세에서 바로 확인" + 제품화 지시
("사용자가 노션에 접근하지 않아도 본인 업무를 모두 관리")를 위해 **포털에서 직접 이미지를
붙일 수 있게** 하는 표다.

소유자 키가 `ticket_cache.id`(자체 UUID)인 이유는 댓글(0023/ticket_comments)과 같다:
Notion page id 에 걸면 소스를 바꾸는 순간 첨부가 전부 고아가 된다. CASCADE 도 같은 이유 —
sync._prune 이 캐시 행을 지울 때 FK 가 남아 있으면 그 DELETE 가 실패하고 동기화가 조용히 멈춘다.

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("ticket_uid", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_uid"], ["ticket_cache.id"], ondelete="CASCADE",
            name="fk_ticket_attachments_ticket_uid",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"],
            name="fk_ticket_attachments_uploaded_by",
        ),
    )
    op.create_index("ix_ticket_attachments_ticket_uid", "ticket_attachments", ["ticket_uid"])
    op.create_index(
        "ix_ticket_attachments_uploaded_by_user_id", "ticket_attachments",
        ["uploaded_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_attachments_uploaded_by_user_id", table_name="ticket_attachments")
    op.drop_index("ix_ticket_attachments_ticket_uid", table_name="ticket_attachments")
    op.drop_table("ticket_attachments")
