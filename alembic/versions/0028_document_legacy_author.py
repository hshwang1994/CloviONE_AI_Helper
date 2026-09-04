"""원본 작성자의 이름을 남길 자리.

Revision ID: 0028_document_legacy_author
Revises: 0027_document_templates
Create Date: 2026-09-04

## 무엇이 문제였나

Confluence 에서 가져온 문서 524건이 화면에서 **가져오기를 돌린 관리자가 쓴 것**으로 보인다.
`created_by` 에 실행 계정을 적었기 때문이다. 그것은 없는 정보가 아니라 **틀린 정보**다.

## 왜 이을 수 없나

Confluence v2 의 페이지 응답은 작성자의 Atlassian 계정 id 만 준다. 그 id 로 사용자 API 를
불러도 이메일은 프로필 공개 설정이 막는다 — 실측에서 작성자 8명 중 이메일을 준 것은 1명
뿐이고, 그 하나도 우리 계정에 없었다. 우리 계정과 잇는 다리는 이메일 하나뿐이므로(U11)
이 문서들의 작성자는 **우리 계정으로 이을 수 없다.**

이름은 받을 수 있다. 그래서 셋을 나눈다:
  · `created_by` 가 있다  → 우리 사용자가 썼다
  · `created_by` 가 비었고 `legacy_author_name` 이 있다 → 원본에 이렇게 적혀 있었다
  · 둘 다 없다            → 모른다

가운데가 이 마이그레이션이 만드는 자리다. 댓글 쪽은 이미 같은 규칙을 쓰고 있다 —
작성자를 못 풀면 본문 첫 줄에 원 작성자를 적는다(남의 이름을 사칭하지 않는다).

## 되돌리기

칸 하나를 지운다. 값은 이관이 다시 채울 수 있으므로 문서 쪽 손실이 없다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_document_legacy_author"
down_revision = "0027_document_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("legacy_author_name", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "legacy_author_name")
