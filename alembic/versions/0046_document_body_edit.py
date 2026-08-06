"""문서 본문 정본과 원본 반영 상태 (0046)

첫 줄에 em 대시를 쓰지 않는다. alembic 이 이 줄을 리비전 메시지로 stdout 에 찍고, Windows
콘솔(cp949)로 파이프될 때 그 한 글자가 디코딩을 깨뜨린다(0044/0045 와 같은 이유).

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-06

## 왜 문서 본문을 우리 DB 에 담는가 (지금까지는 안 담았다)

`document_cache` 모듈 docstring 은 "본문(블록)은 캐시하지 않고 상세 조회 때 실시간으로
읽는다" 고 적어 놓았고, **읽기만 할 때는 그게 맞았다**. 포털에서 편집을 열면 사정이 바뀐다.

저장 순서가 '우리 DB 먼저 → Notion push' 여야 하기 때문이다. 반대로 하면 Notion 이 죽은
날 사용자가 방금 친 글이 통째로 사라진다. 정본을 담을 자리가 없으면 그 순서를 지킬 수
없고, 순서를 못 지키면 편집 기능은 사용자 글을 잃는 기능이 된다.
(`ticket_cache.body_markdown` 이 티켓에서 같은 판단을 이미 기록해 놓았다.)

## 왜 `body_sync_error` 를 행에 두는가

push 실패로 로컬 저장을 롤백하지 않는다. 롤백하면 Notion 장애의 대가를 사용자 입력으로
치르게 하는 것이다. 대신 어긋난 사실을 여기 적어 두고 상세 화면이 "저장됨, 원본 반영
실패" 를 말하게 한다. 토스트는 사라지지만 이 값은 남으므로 다시 열어도 보인다.

셋 다 nullable 이다. NULL 인 `body_markdown` 은 "아직 포털에서 고친 적이 없다" 는 뜻이고,
빈 문자열로 채우면 **동기화된 모든 문서의 본문이 빈 것으로 보인다**(그리고 그 상태에서
저장하면 원본 본문이 지워진다).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_TABLE = "document_cache"

_NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    # 포털에서 저장한 본문 마크다운. NULL = 아직 포털에서 고친 적 없음(원본이 정본).
    ("body_markdown", sa.Text()),
    # 마지막 저장이 원본(Notion)까지 갔는가. 값이 있으면 어긋난 상태이고 그 이유다.
    ("body_sync_error", sa.Text()),
    ("body_synced_at", sa.DateTime()),
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _TABLE not in tables:
        return
    existing = _columns(_TABLE)
    for name, type_ in _NEW_COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _TABLE not in tables:
        return
    existing = _columns(_TABLE)
    for name, _type in reversed(_NEW_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
