"""이관이 가져온 티켓 첨부에는 올린 사람이 없다 (S14 · D12).

Revision ID: 0014_ticket_attachment_uploader
Revises: 0013_document_origin_dates
Create Date: 2026-08-24

## 왜 NOT NULL 을 푸는가

티켓 본문의 이미지 222블록(113쪽)이 붙을 자리가 `ticket_attachments` 인데, 그 표의
`uploaded_by_user_id` 가 NOT NULL 이었다. 이관에는 올린 사람이 없다 — 원본에서 그
이미지는 페이지 본문에 박혀 있었을 뿐이고, 누가 붙였는지를 Notion 이 파일 단위로
알려 주지 않는다.

아무 사용자나 골라 적으면 「이 사람이 올렸다」가 **거짓 기록**으로 남는다. 그 거짓은
화면에 정상으로 보이기 때문에 아무도 신고하지 않는다. 사람을 새로 만드는 것도 막혀
있고(D9), 내용을 버리는 것은 이관이 하려는 일의 반대다.

`NULL` 의 뜻은 「이관이 가져왔고 올린 사람이 없다」이고, 그것이 사실이다. 문서 첨부는
이미 같은 모양이다(`document_attachments.created_by` 가 nullable). 같은 뜻을 두 표가
다른 모양으로 적을 이유가 없다.

FK 자체는 그대로 둔다. 값이 있으면 그 값은 여전히 실재하는 사용자여야 한다.

## 되감기

`NOT NULL` 을 다시 세운다. **올린 사람이 없는 행이 하나라도 있으면 되감기가 실패한다.**
그것이 옳다: 되감으려면 그 행들을 지울지 누구를 적을지 사람이 먼저 정해야 하고, 그
결정을 이 파일이 대신하면 이관이 옮긴 이미지가 조용히 사라지거나 거짓 이름이 박힌다.
그래서 여기서는 **왜 못 되감는지 세어서 말한다** — 조용히 실패하는 것이 가장 나쁘다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0014_ticket_attachment_uploader'
down_revision = '0013_document_origin_dates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'ticket_attachments', 'uploaded_by_user_id',
        existing_type=sa.String(length=36), nullable=True,
    )


def downgrade() -> None:
    orphans = int(op.get_bind().execute(sa.text(
        "SELECT count(*) FROM ticket_attachments WHERE uploaded_by_user_id IS NULL"
    )).scalar_one())
    if orphans:
        raise RuntimeError(
            f"올린 사람이 없는 티켓 첨부가 {orphans}건 있어 되감을 수 없습니다. "
            "이관이 티켓 본문에서 옮겨 온 파일입니다. "
            "그 행들을 지울지 누구를 적을지 먼저 정하십시오."
        )
    op.alter_column(
        'ticket_attachments', 'uploaded_by_user_id',
        existing_type=sa.String(length=36), nullable=False,
    )
