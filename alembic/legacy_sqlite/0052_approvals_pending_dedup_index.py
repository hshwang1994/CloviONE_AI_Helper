"""승인 요청 중복 방지 — 같은 (request_type, object_id, payload) pending 요청은 DB가
직접 막는다 (backend-approvals-jobs 감사 #1).

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-08

## 왜 필요한가

`approvals.service.create_approval`의 중복 방지는 "조회 후 삽입"이라 **요청 전체가
처리되는 동안**(커밋은 `get_db`가 요청 끝에 한 번에 한다) 경합 창이 열려 있다. 두 요청이
거의 동시에 들어오면 둘 다 "기존 pending 없음"을 보고 각각 삽입할 수 있다 — 더블클릭,
폼 재제출, 두 관리자가 거의 동시에 같은 대상을 조작하는 경우가 전부 해당한다.

그렇게 만들어진 두 번째 pending 행부터는 그다음 그 대상에 대한 어떤 요청이든
(`select(...).scalar_one_or_none()`) `MultipleResultsFound`를 던져 500으로 막힌다 —
대상 객체에 대한 모든 승인 요청 경로가 관리자가 수동으로 정리할 때까지 죽는다.

## 왜 (request_type, object_id) 가 아니라 payload 까지 묶는가

같은 대상에 대해 **내용이 다른** 재요청(예: 다른 역할로의 재요청)은 의도적으로 여러
pending 행을 허용한다(`create_approval`의 주석 참고) — payload가 다르면 새 요청이 옛
pending 건을 가로채면 안 되기 때문이다. 유일성을 (request_type, object_id) 만으로
걸면 이 의도된 재요청까지 막아 버린다. payload 까지 포함해야 "완전히 같은 내용의
요청이 중복 삽입되는 것"만 막고, 의도된 재요청은 그대로 허용한다.

## 배포 전 기존 중복 정리

새 유일 인덱스를 걸기 전에 이미 중복이 있으면 `CREATE UNIQUE INDEX` 자체가 실패한다.
(request_type, object_id, payload)가 같은 pending 행이 여럿이면 가장 최근
(requested_at 기준) 것만 남기고 나머지는 `cancelled`로 옮겨 인덱스를 걸 수 있게 한다 —
요청 행 자체는 감사 이력으로 남고 상태만 바뀐다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

_TABLE = "approvals"
_INDEX = "ux_approvals_pending_dedup"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    _dedupe_existing_pending(bind)
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(
            _INDEX,
            _TABLE,
            ["request_type", "object_id", "request_payload_json"],
            unique=True,
            sqlite_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes(_TABLE)}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name=_TABLE)


def _dedupe_existing_pending(bind) -> None:
    """(request_type, object_id, payload)가 같은 pending 중복이 이미 있으면 가장 최근
    것만 남기고 나머지는 cancelled로 옮긴다 — 뒤이은 인덱스 생성이 실패하지 않도록.
    승인/거절 이력은 그대로 남고 상태만 바뀐다."""
    rows = bind.execute(
        sa.text(
            "SELECT id, request_type, object_id, request_payload_json, requested_at "
            "FROM approvals WHERE status = 'pending' "
            "ORDER BY request_type, object_id, request_payload_json, requested_at DESC"
        )
    ).fetchall()
    seen: set[tuple[str, str, str]] = set()
    stale_ids: list[str] = []
    for row in rows:
        key = (row.request_type, row.object_id, row.request_payload_json)
        if key in seen:
            stale_ids.append(row.id)
        else:
            seen.add(key)
    for stale_id in stale_ids:
        bind.execute(
            sa.text(
                "UPDATE approvals SET status = 'cancelled', decision_comment = "
                "COALESCE(decision_comment, '') || :note WHERE id = :id"
            ),
            {
                "note": "[system] 마이그레이션 0052: 동일 내용의 중복 pending 요청이라 자동 취소됨",
                "id": stale_id,
            },
        )
