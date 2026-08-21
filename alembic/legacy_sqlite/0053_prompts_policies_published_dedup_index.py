"""발행(published) 버전은 이름당 하나 — DB가 직접 막는다 (UB-04).

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-10

## 왜 필요한가

`prompts.service.transition()`이 발행으로 전환할 때 "발행 상태를 조회 → 이전 발행본을
archived로 바꿈 → 이 행을 published로 바꿈"을 잠금·제약 없이 한다(read-then-write, 커밋은
`get_db`가 요청 끝에 한 번만 한다). 두 관리자가 같은 이름의 서로 다른 버전을 거의 동시에
발행하면 둘 다 "기존 발행본"을 같은 시점에 보고 각자 자기 행을 published로 만들 수 있다 —
그러면 같은 이름에 published 행이 두 개가 된다.

그 뒤로는 `get_published()`(`scalar_one_or_none()`)가 `MultipleResultsFound`를 던져 그
이름의 모든 `transition`·`rollback`이 500이 되고, 그 이름에 묶인 템플릿의
`POST /documents/generate`도 함께 500이 된다 — approvals의 0052(`ux_approvals_pending_dedup`)
와 정확히 같은 실패 양식이다. 같은 해법(부분 유일 인덱스 + 서비스 계층의
`IntegrityError` → 409 변환)을 적용한다.

## 배포 전 기존 중복 정리

이미 같은 이름에 published 행이 여럿이면 `CREATE UNIQUE INDEX` 자체가 실패한다.
`published_at` 기준 가장 최근 것만 남기고 나머지는 archived로 옮겨 인덱스를 걸 수 있게
한다 — 버전 행 자체(내용·이력)는 그대로 남고 상태만 바뀐다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_TARGETS = (
    ("prompts", "ux_prompts_published_dedup"),
    ("policies", "ux_policies_published_dedup"),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    for table, index_name in _TARGETS:
        if table not in existing_tables:
            continue
        _dedupe_existing_published(bind, table)
        indexes = {i["name"] for i in sa.inspect(bind).get_indexes(table)}
        if index_name not in indexes:
            op.create_index(
                index_name,
                table,
                ["name"],
                unique=True,
                sqlite_where=sa.text("status = 'published'"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    for table, index_name in _TARGETS:
        if table not in existing_tables:
            continue
        indexes = {i["name"] for i in sa.inspect(bind).get_indexes(table)}
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)


def _dedupe_existing_published(bind, table: str) -> None:
    """같은 이름에 published 행이 여럿이면 가장 최근(published_at) 것만 남기고 나머지는
    archived로 옮긴다 — 뒤이은 인덱스 생성이 실패하지 않도록. 내용·이력은 그대로 남는다."""
    rows = bind.execute(
        sa.text(
            f"SELECT id, name, published_at FROM {table} WHERE status = 'published' "
            "ORDER BY name, published_at DESC"
        )
    ).fetchall()
    seen: set[str] = set()
    stale_ids: list[str] = []
    for row in rows:
        if row.name in seen:
            stale_ids.append(row.id)
        else:
            seen.add(row.name)
    for stale_id in stale_ids:
        bind.execute(
            sa.text(f"UPDATE {table} SET status = 'archived' WHERE id = :id"),
            {"id": stale_id},
        )
