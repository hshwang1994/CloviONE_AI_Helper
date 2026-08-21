"""게시글 종류와 제안 상태 (0048)

첫 줄에 em 대시를 쓰지 않는다. alembic 이 이 줄을 리비전 메시지로 stdout 에 찍고, Windows
콘솔(cp949)로 파이프될 때 그 한 글자가 디코딩을 깨뜨린다(0044/0045/0046 과 같은 이유).

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-06

## 왜 새 표가 아닌가

기능 개선 제안 게시판(7단계 #1)은 `board_posts` 에 **종류 한 칸**을 더한 것이다. 표를
새로 팠다면 첨부·댓글·반응·알림·검색·조직 범위 경로가 두 벌이 되고, 한쪽만 고쳐지는 날이
반드시 온다. 이 저장소는 "목록만 좁히고 단건은 안 좁혔다"를 네 번 반복한 이력이 있다
(scripts/check_scope_gates.py 서문). 길이 하나면 그 실수가 나올 자리도 하나다.

## 🔴 `kind` 가 NOT NULL + server_default 인 이유

이 마이그레이션에서 **틀리면 가장 크게 아픈 곳**이 여기다. nullable 로 두면 기존 행이
전부 NULL 이 되고, 목록 질의의 `kind = 'free'` 는 **NULL 행을 하나도 고르지 못한다**
(SQL 의 NULL 비교). 즉 사내 게시판이 배포 다음 날 통째로 빈 화면이 된다. 데이터는 그대로
있으므로 아무도 유실을 의심하지 않고, 원인을 찾는 데 하루가 간다.

server_default 를 함께 거는 이유는 두 가지다.
  * SQLite 의 `ALTER TABLE ADD COLUMN ... NOT NULL` 은 기본값 없이는 애초에 실패한다.
  * 이 컬럼을 모르는 옛 경로(수동 INSERT, 예전 스크립트)가 넣는 행도 '자유'로 떨어진다.
    파이썬 쪽 `default=` 만 있으면 ORM 을 지나지 않는 쓰기가 조용히 NULL 을 만든다.

그 위에 UPDATE 백필을 한 번 더 돌린다. server_default 가 기존 행을 채우는 것은 SQLite 의
동작이고 다른 엔진에서는 다를 수 있다 — 두 줄로 확실히 해 둔다(멱등하다).

## `idea_status` / `ticket_page_id` 는 nullable 이다

둘 다 **아이디어에만 뜻이 있다.** 자유게시글을 '제안' 으로 채워 두면 화면이 자유게시판에
상태 배지를 그리게 되고, 그건 사용자가 지적한 "종류가 뒤섞인다"의 시작이다. 값이 없는
것과 값이 '제안'인 것은 다른 사실이므로 NULL 로 남긴다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

_TABLE = "board_posts"
_KIND_FREE = "free"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    existing = _columns(_TABLE)

    if "kind" not in existing:
        op.add_column(
            _TABLE,
            sa.Column("kind", sa.String(16), nullable=False, server_default=_KIND_FREE),
        )
        op.create_index("ix_board_posts_kind", _TABLE, ["kind"])
    # 기존 행 백필. server_default 로 이미 채워졌더라도 멱등하다.
    op.execute(sa.text(f"UPDATE {_TABLE} SET kind = '{_KIND_FREE}' WHERE kind IS NULL"))

    if "idea_status" not in existing:
        op.add_column(_TABLE, sa.Column("idea_status", sa.String(16), nullable=True))
        op.create_index("ix_board_posts_idea_status", _TABLE, ["idea_status"])
    if "ticket_page_id" not in existing:
        op.add_column(_TABLE, sa.Column("ticket_page_id", sa.String(64), nullable=True))
        op.create_index("ix_board_posts_ticket_page_id", _TABLE, ["ticket_page_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    existing = _columns(_TABLE)
    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes(_TABLE)}
    for index, column in (
        ("ix_board_posts_ticket_page_id", "ticket_page_id"),
        ("ix_board_posts_idea_status", "idea_status"),
        ("ix_board_posts_kind", "kind"),
    ):
        if index in indexes:
            op.drop_index(index, table_name=_TABLE)
        if column in existing:
            op.drop_column(_TABLE, column)
