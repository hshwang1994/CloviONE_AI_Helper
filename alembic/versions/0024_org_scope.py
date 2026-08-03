"""org_scope — 부서 트리 + 조직 스코프 컬럼 + 사용자 관리 범위 (§7.1.A, PLAN Phase 4)

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-03

**이 계획에서 가장 위험한 마이그레이션이다.** 이유가 두 가지고, 둘 다 조용히 깨지는 종류다.

1. **`org_id` 를 NULL 로 두면 복합 유니크가 무효가 된다.**
   SQLite 는 UNIQUE 인덱스에서 NULL 을 서로 **다른 값**으로 취급한다. 그래서
   `(org_id, name)` 유니크를 걸어 두고 `org_id` 를 NULL 로 남기면 같은 이름의 부서를
   몇 개든 넣을 수 있다 — 제약이 있는데 아무것도 막지 않는다. 오류도 안 나고 화면도
   멀쩡하다가, 부서가 둘로 갈라진 뒤에야 드러난다(그때는 이미 사용자들이 양쪽에 나뉘어
   있다). 그래서 여기서는 **DEFAULT_ORG_ID 실값으로 백필**하고,
   `tests/regression/test_migration_0024_org_scope.py` 가 백필 뒤 실제로 중복 삽입이
   거부되는지를 INSERT 를 쳐서 증명한다.
   같은 이유로 애플리케이션 모델(`OrgScopedMixin`)도 `default=DEFAULT_ORG_ID` 를 갖는다 —
   백필만 하고 신규 행을 NULL 로 만들면 구멍이 그대로 다시 열린다.

2. **SQLite `batch_alter_table` 의 다운그레이드는 테이블을 재생성한다.**
   컬럼 순서·server_default·인덱스가 조용히 달라질 수 있다. 그래서 "upgrade 가 됐다"는
   확인이 아니다 — `scripts/migration_rehearsal.sh` 가 upgrade→downgrade→upgrade 왕복
   전후의 `pragma table_info` 와 행 수를 통째로 비교하고, 회귀 테스트가 실데이터로
   같은 왕복을 돈다.

**무엇을 하는가.**
  * `departments`: `parent_id`(자기참조, nullable — 부서 트리) + `org_id`,
    전역 유니크 `ix_departments_name` → 조직별 유니크 `uq_departments_org_name`
  * 7개 테이블에 nullable `org_id` 추가 후 DEFAULT_ORG_ID 백필:
    departments / job_titles / board_posts / document_cache / chat_rooms / game_rooms /
    trash_items. (`ticket_cache` 는 0023 에서 이미 갖고 있다.)
    이 7개는 "테넌트가 소유한 내용물"이다. `notifications`·`audit_logs` 처럼 사용자에
    딸린 파생 테이블은 user_id 를 타고 스코프가 결정되므로 컬럼을 늘리지 않는다.
  * `users`: `org_id` + `admin_scope` / `scope_org_id` / `scope_dept_id`

**`job_titles` 는 왜 전역 유니크를 그대로 두는가.** 직책명('팀장')은 조직이 늘어도
같은 이름을 쓰는 것이 자연스럽고, 유니크를 바꾸면 그만큼 재생성 범위가 넓어진다.
부서 트리가 이번 변경의 목적이므로 부서에만 조직별 유니크를 건다.

**`admin_scope` 기본값이 'global' 인 이유.** 기존 관리자 전원의 동작을 **정확히 그대로**
유지하기 위해서다. 좁은 값을 기본으로 깔면 이 마이그레이션 하나로 운영 중인 관리자
화면들이 조용히 빈 목록이 된다. 좁히는 것은 명시적 설정이어야 한다.

타임스탬프는 파이썬 datetime 으로 만들어 파라미터로 바인딩한다(SQLite STRFTIME '%f'
금지 — 초를 두 번 써 넣어 ORM isoformat 파싱이 깨지고 부서 화면이 통째로 죽는다,
CLAUDE.md §8).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

# app/org/constants.py 가 정본. 마이그레이션은 적용된 뒤 불변이어야 하므로 import 대신
# 값을 못박는다(0022 와 같은 관례).
_DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"

# org_id 를 새로 갖는 테이블들. departments 는 parent_id 때문에 별도로 처리한다.
_ORG_SCOPED_TABLES = (
    "job_titles",
    "board_posts",
    "document_cache",
    "chat_rooms",
    "game_rooms",
    "trash_items",
)

# admin_scope 어휘. app/core/scope.py 가 같은 값을 쓴다.
_SCOPE_GLOBAL = "global"


def _backfill_org(table: str) -> None:
    """NULL 인 org_id 를 기본 조직 실값으로 채운다.

    NULL 로 남기면 (org_id, name) 유니크가 무효가 되고, 스코프 필터(`org_id = :org`)도
    한 행도 못 고른다 — SQL 에서 `NULL = 'x'` 는 참이 아니라 NULL 이다.
    """
    op.get_bind().execute(
        sa.text(f"UPDATE {table} SET org_id = :org WHERE org_id IS NULL").bindparams(
            org=_DEFAULT_ORG_ID
        )
    )


def upgrade() -> None:
    # ── 1) departments: 부서 트리 + 조직 스코프 ────────────────────────────────
    # SQLite 는 기존 테이블에 FK 를 붙이려면 테이블을 다시 만들어야 한다(batch).
    # env.py 가 foreign_keys 프래그마를 켜지 않으므로 users→departments 참조는
    # 재생성 중에도 이름으로 유지된다(0015 가 같은 방식으로 이미 증명했고,
    # test_migration_0024_org_scope.py 가 이번에도 확인한다).
    with op.batch_alter_table("departments") as batch:
        batch.add_column(sa.Column("org_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("parent_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_departments_org_id", "organizations", ["org_id"], ["id"]
        )
        # 자기참조. 부모를 지우면 자식이 고아가 되는 대신 최상위로 올라온다 —
        # 부서 행을 지우는 경로는 '쓰는 사람이 없을 때'만 열려 있으므로(org/service.py
        # delete_item) 이 경로로 트리가 통째로 사라지는 일은 없다.
        batch.create_foreign_key(
            "fk_departments_parent_id", "departments", ["parent_id"], ["id"],
            ondelete="SET NULL",
        )

    _backfill_org("departments")

    # 전역 유니크 → 조직별 유니크. 순서가 중요하다: 백필을 먼저 하지 않으면 모든 행이
    # (NULL, name) 이 되어 새 인덱스가 아무것도 막지 못한다.
    op.drop_index("ix_departments_name", table_name="departments")
    op.create_index("ix_departments_name", "departments", ["name"])
    op.create_index(
        "uq_departments_org_name", "departments", ["org_id", "name"], unique=True
    )
    op.create_index("ix_departments_org_id", "departments", ["org_id"])
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])

    # ── 2) 나머지 테넌트 소유 테이블에 org_id ──────────────────────────────────
    # 여기는 FK 를 붙이지 않으므로 테이블 재생성이 필요 없다(ALTER TABLE ADD COLUMN).
    # SQLite 에서 FK 를 붙이려면 전부 재생성해야 하는데, 참조 무결성이 주는 이득보다
    # 6개 테이블(그중 하나는 채팅방)을 통째로 다시 만드는 위험이 크다. 값은 앱이
    # OrgScopedMixin 기본값으로 넣고, 스코프 필터는 값 비교만 한다.
    for table in _ORG_SCOPED_TABLES:
        op.add_column(table, sa.Column("org_id", sa.String(36), nullable=True))
        _backfill_org(table)
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])

    # ── 3) users: 소속 조직 + 관리 범위 ───────────────────────────────────────
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("org_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column(
                "admin_scope",
                sa.String(16),
                nullable=False,
                server_default=_SCOPE_GLOBAL,
            )
        )
        batch.add_column(sa.Column("scope_org_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("scope_dept_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_users_org_id", "organizations", ["org_id"], ["id"])
        batch.create_foreign_key(
            "fk_users_scope_org_id", "organizations", ["scope_org_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_users_scope_dept_id", "departments", ["scope_dept_id"], ["id"],
            ondelete="SET NULL",
        )

    _backfill_org("users")
    op.create_index("ix_users_org_id", "users", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_users_org_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_scope_dept_id", type_="foreignkey")
        batch.drop_constraint("fk_users_scope_org_id", type_="foreignkey")
        batch.drop_constraint("fk_users_org_id", type_="foreignkey")
        batch.drop_column("scope_dept_id")
        batch.drop_column("scope_org_id")
        batch.drop_column("admin_scope")
        batch.drop_column("org_id")

    for table in reversed(_ORG_SCOPED_TABLES):
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("org_id")

    op.drop_index("ix_departments_parent_id", table_name="departments")
    op.drop_index("ix_departments_org_id", table_name="departments")
    op.drop_index("uq_departments_org_name", table_name="departments")
    op.drop_index("ix_departments_name", table_name="departments")
    # 0023 시절의 모양(전역 유니크)으로 되돌린다. 조직별 유니크만 있던 동안 같은 이름의
    # 부서가 두 조직에 생겼다면 여기서 IntegrityError 로 멈춘다 — 데이터를 조용히 버리는
    # 것보다 낫다(다중 조직을 실제로 쓰기 시작하면 이 다운그레이드는 더 이상 안전하지 않다).
    op.create_index("ix_departments_name", "departments", ["name"], unique=True)

    with op.batch_alter_table("departments") as batch:
        batch.drop_constraint("fk_departments_parent_id", type_="foreignkey")
        batch.drop_constraint("fk_departments_org_id", type_="foreignkey")
        batch.drop_column("parent_id")
        batch.drop_column("org_id")
