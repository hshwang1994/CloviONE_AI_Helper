"""프로젝트 코드를 서버가 짓는다 — 그리고 옛 이름 층을 걷는다 (S14).

Revision ID: 0012_project_code_policy
Revises: 0011_legacy_mapping
Create Date: 2026-08-24

## 이 판이 하는 말

**프로젝트 코드는 대문자 여섯 글자이고, 전역에서 하나이며, 사람이 못 고친다** (D-282).

앞 정책은 사람이 20건을 손으로 확정하고(옛 D-243) 필요하면 바꿀 수 있었다(옛 D-195).
그 둘을 없애면 세 자리가 함께 죽는다:

| 자리 | 왜 죽는가 |
|---|---|
| `project_key_registry` | 예약(`GIT`)·회수(`retired`)·소유 대장이었다. 코드를 안 바꾸고 프로젝트를 안 지우므로(보관만 한다) `projects.code` 의 유니크가 곧 영구 소유다 |
| `ticket_key_aliases` | 행이 생기는 경로가 둘뿐이었다 — Key 변경(`superseded`)과 옛 이름(`legacy`). 앞엣것은 없어졌고 뒤엣것은 안 옮긴다(D-283) |
| `tickets.legacy_key` | `GIT-142` 를 담던 칸이다. 옛 코드를 폐기하므로 들어올 값이 없다(D-283) |

## 옛 정책의 코드는 **지운다**

`ABCDEFGHJKMNPQRSTUVWXYZ` 여섯 글자가 아닌 `projects.code` 는 NULL 로 만든다. 그 코드에서
파생된 티켓 번호(`seq`)도 함께 지운다 — `canonical_key` 는 트리거가 따라서 지운다.

지우는 것이 옳은 이유: 그 이름들은 **아직 아무 데도 안 나갔다.** Dry Run 은 임시 DB 로
갔고 운영은 이 판을 처음 받는다. 반대로 남겨 두면 `SKH-1` 처럼 새 모양이 아닌 이름이
영구 식별자 자리에 앉고, 그것은 되돌릴 수 없다.

운영과 재실행에서 이 UPDATE 는 **한 행도 안 건드린다** — 운영 `projects.code` 는 22건
전부 NULL 이고, 재실행 DB 의 코드는 이미 새 모양이다.

## 되감기

표 둘과 컬럼 하나를 **모양만** 되돌린다. 행은 안 돌아온다 — 이 저장소의 되감기 규약이다.
지운 코드와 번호도 안 돌아온다. 되감은 뒤 이관을 다시 돌리면 같은 씨앗에서 **같은 코드**가
나오므로(D-282) 그 점은 손해가 아니다.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0012_project_code_policy'
down_revision = '0011_legacy_mapping'
branch_labels = None
depends_on = None

# `app/work/codes.py::CODE_ALPHABET` · `CODE_LENGTH` 의 사본이다.
# `tests/unit/test_project_codes.py` 가 이 파일의 문자열과 그 상수가 같은지 확인한다.
_CODE_SHAPE = "^[ABCDEFGHJKMNPQRSTUVWXYZ]{6}$"


def upgrade() -> None:
    # ── 1. 옛 이름 층을 걷는다 ────────────────────────────────────────────────
    op.drop_index("ix_ticket_key_aliases_ticket_id", table_name="ticket_key_aliases")
    op.drop_table("ticket_key_aliases")

    op.drop_index("uq_tickets_legacy", table_name="tickets")
    op.drop_column("tickets", "legacy_key")

    op.drop_index("uq_pkr_active_project", table_name="project_key_registry")
    op.drop_index("uq_pkr_key_ci", table_name="project_key_registry")
    op.drop_index("ix_project_key_registry_project_id", table_name="project_key_registry")
    op.drop_table("project_key_registry")

    # ── 2. 옛 정책의 코드와 그 코드에서 나온 번호를 지운다 ────────────────────
    #
    # 번호를 먼저 지운다. 코드를 먼저 지우면 그 뒤의 `UPDATE tickets SET seq = NULL` 이
    # 트리거를 태우는데, 트리거가 「번호는 있는데 프로젝트에 코드가 없다」로 거절할 수
    # 있는 상태를 스스로 만드는 셈이다.
    op.execute(
        sa.text(
            "UPDATE tickets SET seq = NULL WHERE project_uid IN ("
            "  SELECT id FROM projects WHERE code IS NOT NULL AND code !~ :shape)"
        ).bindparams(shape=_CODE_SHAPE)
    )
    op.execute(
        sa.text(
            "UPDATE projects SET code = NULL WHERE code IS NOT NULL AND code !~ :shape"
        ).bindparams(shape=_CODE_SHAPE)
    )

    # ── 3. 유일성을 조직 안에서 전역으로 올린다 ───────────────────────────────
    #
    # 옛 인덱스는 `(org_id, code)` 였고 `org_id` 가 NULL 인 행끼리는 서로 다른 값이라
    # **아무것도 막지 않았다.** 티켓 이름 `<CODE>-<SEQ>` 는 조직을 지고 다니지 않으므로
    # 유일성도 조직을 지면 안 된다.
    op.drop_index("uq_projects_org_code", table_name="projects")
    op.execute(
        "CREATE UNIQUE INDEX uq_projects_code ON projects (code) "
        "WHERE code IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_projects_code_shape", "projects", f"code IS NULL OR code ~ '{_CODE_SHAPE}'"
    )

    # ── 4. 옮긴 티켓이 **그때 불리던 이름**을 남긴다 ──────────────────────────
    #
    # 퇴사 처리 화면은 지금까지 `"GIT-" + ticket_number` 로 이름을 **지어내고** 있었다.
    # 옛 코드를 폐기하면 그 문자열은 제품 어디에도 없는 이름이 되고, 붙여 넣어도 아무
    # 티켓이 안 열린다. `ticket_title` 과 같은 자리에 같은 이유로 스냅숏을 남긴다.
    op.add_column(
        "offboarding_ticket_moves",
        sa.Column("ticket_key", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("offboarding_ticket_moves", "ticket_key")

    op.drop_constraint("ck_projects_code_shape", "projects", type_="check")
    op.drop_index("uq_projects_code", table_name="projects")
    op.create_index("uq_projects_org_code", "projects", ["org_id", "code"], unique=True)

    op.create_table(
        "project_key_registry",
        sa.Column("key", sa.String(length=10), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
        sa.CheckConstraint(r"key ~ '^[A-Z][A-Z0-9]{1,9}$'", name="ck_pkr_key_shape"),
        sa.CheckConstraint(
            "state IN ('active', 'retired', 'reserved')", name="ck_pkr_state"
        ),
        sa.CheckConstraint(
            "(state = 'reserved' AND project_id IS NULL) OR "
            "(state <> 'reserved' AND project_id IS NOT NULL)",
            name="ck_pkr_reserved_has_no_project",
        ),
    )
    op.create_index(
        "ix_project_key_registry_project_id", "project_key_registry", ["project_id"]
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pkr_key_ci ON project_key_registry (upper(key))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pkr_active_project ON project_key_registry (project_id) "
        "WHERE state = 'active'"
    )

    op.add_column("tickets", sa.Column("legacy_key", sa.String(length=64), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX uq_tickets_legacy ON tickets (legacy_key) "
        "WHERE legacy_key IS NOT NULL"
    )

    op.create_table(
        "ticket_key_aliases",
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("alias"),
        sa.CheckConstraint("kind IN ('legacy', 'superseded')", name="ck_tka_kind"),
    )
    op.create_index(
        "ix_ticket_key_aliases_ticket_id", "ticket_key_aliases", ["ticket_id"]
    )
