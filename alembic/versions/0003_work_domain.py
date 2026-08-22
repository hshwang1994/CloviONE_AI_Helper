"""Work Domain — 티켓 식별자·채번·관계·활동·상태·스프린트, 그리고 `ticket_cache` → `tickets` (S6).

Revision ID: 0003_work_domain
Revises: 0002_identity_access
Create Date: 2026-08-22

앱 코드를 import 하지 않는다. 0002 가 적어 둔 이유 그대로다 — 마이그레이션은 **그 시점
스키마의 얼어붙은 스냅숏**이라 `app/work/workflow.py` 를 참조하면 나중에 상태 목록을
고치는 날 이 파일의 뜻이 소리 없이 함께 바뀐다. 값을 여기 그대로 적고
`tests/unit/test_work_domain_seed.py` 가 둘을 맞물려 둔다.

## 표 이름을 바꾼다 — `ticket_cache` → `tickets`

0023 이 이 표를 만들 때는 이름이 정직했다(Notion 미러). S6 이 티켓 번호·표시 이름·
상태·순서를 붙이면서 틀린 말이 됐다 — 캐시는 지워도 되는 것이고 이 표는 지우면 티켓
번호가 사라진다.

D-234 가 `departments` → `org_units` 에서 배운 것을 그대로 쓴다: PostgreSQL 의
`ALTER TABLE … RENAME TO` 는 인덱스·제약을 **옛 이름 그대로** 데려가므로 이름도 함께
옮긴다. 안 옮기면 다음 사람이 `ix_ticket_cache_status` 를 보고 없는 표를 찾는다.
**컬럼 이름은 그대로 둔다** — `project_uid` 는 API 응답에 나가는 이름이다.

## canonical_key 는 트리거가 만든다 (D-195)

`GENERATED ALWAYS AS (project_key || '-' || seq)` 는 구현할 수 없다. PostgreSQL
Generated Column 은 다른 표(`projects.code`)를 참조할 수 없다. 실제 저장 컬럼 +
BEFORE INSERT/UPDATE 트리거로 대체한다. **앱은 이 컬럼을 쓰지 않는다.**
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0003_work_domain'
down_revision = '0002_identity_access'
branch_labels = None
depends_on = None


# 옛 시스템의 티켓 번호 접두어. 실측(INVENTORY 07): `unique_id` prefix `GIT`, 27~1536.
_LEGACY_PREFIX = "GIT"

# 표시 Status → 내부 Category (§5.2). 정본은 `app/work/workflow.py::STATUSES` 이고
# 여기는 그 결과를 얼려 둔 것이다. (key, label, category, sort_order, is_default)
_TICKET_STATUSES: tuple[tuple[str, str, str, int, bool], ...] = (
    ("계획", "계획", "OPEN", 10, True),
    ("이슈", "이슈", "OPEN", 20, False),
    ("진행", "진행", "IN_PROGRESS", 30, False),
    ("검증", "검증", "IN_PROGRESS", 40, False),
    ("완료", "완료", "DONE", 50, False),
    ("취소", "취소", "CANCELED", 60, False),
)

# 예약 Key. `GIT` 하나뿐인 이유는 `app/work/keys.py::RESERVED_KEYS` 에 적었다.
_RESERVED_KEYS: tuple[str, ...] = ("GIT",)

_CANONICAL_KEY_FN = """
CREATE OR REPLACE FUNCTION tickets_set_canonical_key() RETURNS trigger AS $$
DECLARE
  project_key text;
BEGIN
  IF NEW.seq IS NULL THEN
    NEW.canonical_key := NULL;
    RETURN NEW;
  END IF;

  -- 형식 지시자(%)를 쓰지 않는다. 이 본문은 파라미터 없이 실행되지만, 드라이버가
  -- 바뀌거나 이 문자열이 파라미터와 함께 도는 자리로 옮겨 가면 %가 조용히 먹힌다.
  IF NEW.project_uid IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'check_violation',
      MESSAGE = 'ticket has a sequence number but no project: ' || NEW.id;
  END IF;

  SELECT p.code INTO project_key FROM projects p WHERE p.id = NEW.project_uid;

  IF project_key IS NULL OR project_key = '' THEN
    RAISE EXCEPTION USING ERRCODE = 'check_violation',
      MESSAGE = 'project has no project key; cannot derive canonical_key: '
        || NEW.project_uid;
  END IF;

  NEW.canonical_key := project_key || '-' || NEW.seq::text;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_CANONICAL_KEY_TRIGGER = """
CREATE TRIGGER trg_tickets_canonical_key
  BEFORE INSERT OR UPDATE OF seq, project_uid ON tickets
  FOR EACH ROW EXECUTE FUNCTION tickets_set_canonical_key();
"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    _rename_ticket_cache()
    _create_key_registry()
    _create_sprints()
    _extend_tickets()
    _create_relations_and_activity()
    _create_statuses()
    _add_record_versions()
    _seed()


# ── 1. ticket_cache → tickets ────────────────────────────────────────────────


def _rename_ticket_cache() -> None:
    op.execute("ALTER TABLE ticket_cache RENAME TO tickets")
    for old, new in (
        ("ix_ticket_cache_due_date", "ix_tickets_due_date"),
        ("ix_ticket_cache_notion_missing_at", "ix_tickets_notion_missing_at"),
        ("ix_ticket_cache_notion_page_id", "ix_tickets_notion_page_id"),
        ("ix_ticket_cache_org_id", "ix_tickets_org_id"),
        ("ix_ticket_cache_parent_page_id", "ix_tickets_parent_page_id"),
        ("ix_ticket_cache_project_link", "ix_tickets_project_link"),
        ("ix_ticket_cache_project_uid", "ix_tickets_project_uid"),
        ("ix_ticket_cache_status", "ix_tickets_status"),
        ("ticket_cache_pkey", "tickets_pkey"),
    ):
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    op.execute(
        "ALTER TABLE tickets RENAME CONSTRAINT ticket_cache_org_id_fkey "
        "TO tickets_org_id_fkey"
    )
    op.execute(
        "ALTER TABLE tickets RENAME CONSTRAINT ticket_cache_project_uid_fkey "
        "TO tickets_project_uid_fkey"
    )


# ── 2. Project Key 대장과 카운터 ─────────────────────────────────────────────


def _create_key_registry() -> None:
    op.create_table(
        "project_key_registry",
        sa.Column("key", sa.String(length=10), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(r"key ~ '^[A-Z][A-Z0-9]{1,9}$'", name="ck_pkr_key_shape"),
        sa.CheckConstraint(
            "state IN ('active', 'retired', 'reserved')", name="ck_pkr_state"
        ),
        sa.CheckConstraint(
            "(state = 'reserved' AND project_id IS NULL) OR "
            "(state <> 'reserved' AND project_id IS NOT NULL)",
            name="ck_pkr_reserved_has_no_project",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        op.f("ix_project_key_registry_project_id"), "project_key_registry",
        ["project_id"], unique=False,
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pkr_key_ci ON project_key_registry (upper(key))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pkr_active_project ON project_key_registry (project_id) "
        "WHERE state = 'active'"
    )

    op.create_table(
        "project_ticket_counters",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("last_seq", sa.Integer(), nullable=False),
        sa.CheckConstraint("last_seq >= 0", name="ck_ptc_last_seq_nonneg"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "ticket_key_aliases",
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('legacy', 'superseded')", name="ck_tka_kind"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("alias"),
    )
    op.create_index(
        op.f("ix_ticket_key_aliases_ticket_id"), "ticket_key_aliases",
        ["ticket_id"], unique=False,
    )

    op.create_table(
        "migration_exceptions",
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column(
            "source_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "reason IN ('ambiguous', 'missing', 'unresolved', 'source_missing')",
            name="ck_mex_reason",
        ),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_migration_exceptions_ticket_id"), "migration_exceptions",
        ["ticket_id"], unique=False,
    )
    op.create_index(
        op.f("ix_migration_exceptions_resolved_at"), "migration_exceptions",
        ["resolved_at"], unique=False,
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_mex_open_ticket ON migration_exceptions (ticket_id) "
        "WHERE resolved_at IS NULL"
    )


# ── 3. 스프린트 (tickets.sprint_id 보다 먼저 서야 한다) ──────────────────────


def _create_sprints() -> None:
    op.create_table(
        "sprints",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("starts_on", sa.String(length=10), nullable=False),
        sa.Column("ends_on", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "state IN ('planned', 'active', 'closed')", name="ck_sprints_state"
        ),
        sa.CheckConstraint("starts_on < ends_on", name="ck_sprints_window"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sprints_org_id"), "sprints", ["org_id"], unique=False)
    op.create_index(
        op.f("ix_sprints_project_id"), "sprints", ["project_id"], unique=False
    )
    op.create_index("ix_sprints_window", "sprints", ["org_id", "starts_on", "ends_on"])
    op.create_index(
        "uq_sprints_name", "sprints", ["org_id", "project_id", "name"], unique=True
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sprints_active ON sprints (org_id, coalesce(project_id, '')) "
        "WHERE state = 'active'"
    )


# ── 4. tickets 확장: 세 층의 이름 · 잠금 · 순서 ──────────────────────────────


def _extend_tickets() -> None:
    op.add_column("tickets", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("canonical_key", sa.String(length=64), nullable=True))
    op.add_column("tickets", sa.Column("legacy_key", sa.String(length=64), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("tickets", sa.Column("sprint_id", sa.String(length=36), nullable=True))
    op.add_column("tickets", sa.Column("backlog_rank", sa.Numeric(), nullable=True))

    # 옛 이름을 채운다. `GIT-142` 는 영구 별칭이라 **하나의 티켓만** 가리켜야 한다 —
    # 번호가 겹치면 여기서 크게 실패하는 것이 맞다. 조용히 한쪽을 고르면 그 링크가
    # 어느 티켓으로 가는지 아무도 모르게 된다.
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT notion_ticket_number, count(*) AS n FROM tickets "
            "WHERE notion_ticket_number IS NOT NULL "
            "GROUP BY notion_ticket_number HAVING count(*) > 1 ORDER BY 1 LIMIT 20"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{_LEGACY_PREFIX}-{row[0]} ({row[1]}건)" for row in duplicates)
        raise RuntimeError(
            "옛 티켓 번호가 겹칩니다 — 영구 별칭이 두 티켓을 가리킬 수 없습니다: " + listed
        )
    bind.execute(
        sa.text(
            "UPDATE tickets SET legacy_key = :prefix || '-' || notion_ticket_number "
            "WHERE notion_ticket_number IS NOT NULL AND legacy_key IS NULL"
        ),
        {"prefix": _LEGACY_PREFIX},
    )
    bind.execute(
        sa.text(
            "INSERT INTO ticket_key_aliases (alias, ticket_id, kind, created_at) "
            "SELECT legacy_key, id, 'legacy', :now FROM tickets "
            "WHERE legacy_key IS NOT NULL ON CONFLICT (alias) DO NOTHING"
        ),
        {"now": _now()},
    )

    op.create_foreign_key(
        "tickets_sprint_id_fkey", "tickets", "sprints", ["sprint_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_tickets_sprint_id"), "tickets", ["sprint_id"], unique=False)
    op.create_index("ix_tickets_backlog", "tickets", ["project_uid", "backlog_rank"])

    op.create_check_constraint(
        "ck_tickets_seq_positive", "tickets", "seq IS NULL OR seq > 0"
    )
    # 초안(§5.2)은 `project_id` 까지 셋을 묶었다. 지금 그 제약을 걸면 미러 전량이
    # 위반이다 — 프로젝트에는 연결돼 있는데 Project Key 가 하나도 없어서 번호를 줄 수
    # 없고, 재채번은 D-197 이 사용자 확인 뒤 S13 으로 정해 둔 일이다. 실제로 지켜야
    # 하는 불변식만 남긴다: **번호는 Key 를 가진 프로젝트 안에서만 발급된다.**
    # 나머지 절반(프로젝트에 Key 가 있는가)은 아래 트리거가 막는다.
    op.create_check_constraint(
        "ck_tickets_key_assigned",
        "tickets",
        "(seq IS NULL AND canonical_key IS NULL) OR "
        "(seq IS NOT NULL AND canonical_key IS NOT NULL AND project_uid IS NOT NULL)",
    )
    op.create_check_constraint("ck_tickets_version_positive", "tickets", "version > 0")
    op.execute(
        "CREATE UNIQUE INDEX uq_tickets_project_seq ON tickets (project_uid, seq) "
        "WHERE project_uid IS NOT NULL AND seq IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tickets_canonical ON tickets (canonical_key) "
        "WHERE canonical_key IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tickets_legacy ON tickets (legacy_key) "
        "WHERE legacy_key IS NOT NULL"
    )

    op.execute(_CANONICAL_KEY_FN)
    op.execute(_CANONICAL_KEY_TRIGGER)


# ── 5. 관계 · 활동 · 관찰자 ──────────────────────────────────────────────────


def _create_relations_and_activity() -> None:
    op.create_table(
        "ticket_relations",
        sa.Column("from_ticket_id", sa.String(length=36), nullable=False),
        sa.Column("to_ticket_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "kind IN ('subtask_of', 'blocks', 'relates_to')", name="ck_trel_kind"
        ),
        sa.CheckConstraint("from_ticket_id <> to_ticket_id", name="ck_trel_not_self"),
        sa.CheckConstraint(
            "kind <> 'relates_to' OR from_ticket_id < to_ticket_id",
            name="ck_trel_symmetric_ordered",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["from_ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_relations_from_ticket_id"), "ticket_relations",
        ["from_ticket_id"], unique=False,
    )
    op.create_index(
        op.f("ix_ticket_relations_to_ticket_id"), "ticket_relations",
        ["to_ticket_id"], unique=False,
    )
    op.create_index(
        op.f("ix_ticket_relations_kind"), "ticket_relations", ["kind"], unique=False
    )
    op.create_index(
        "uq_trel_edge", "ticket_relations",
        ["from_ticket_id", "to_ticket_id", "kind"], unique=True,
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_trel_single_parent ON ticket_relations (from_ticket_id) "
        "WHERE kind = 'subtask_of'"
    )

    op.create_table(
        "ticket_activities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=True),
        sa.Column("from_value", sa.Text(), nullable=True),
        sa.Column("to_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "seq", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('created', 'status', 'assignee', 'sprint', 'rank', 'relation', 'field')",
            name="ck_tact_kind",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_activities_ticket_id"), "ticket_activities",
        ["ticket_id"], unique=False,
    )
    op.create_index(
        op.f("ix_ticket_activities_kind"), "ticket_activities", ["kind"], unique=False
    )
    op.create_index(
        op.f("ix_ticket_activities_created_at"), "ticket_activities",
        ["created_at"], unique=False,
    )
    op.create_index(
        "ix_ticket_activities_timeline", "ticket_activities", ["ticket_id", "seq"]
    )

    op.create_table(
        "ticket_watchers",
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticket_id", "user_id"),
    )


# ── 6. 상태 어휘 ─────────────────────────────────────────────────────────────


def _create_statuses() -> None:
    op.create_table(
        "ticket_statuses",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        op.f("ix_ticket_statuses_category"), "ticket_statuses", ["category"], unique=False
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_ticket_statuses_default ON ticket_statuses (is_default) "
        "WHERE is_default"
    )


# ── 7. 레코드 잠금 — Ticket · Document · Project 가 같은 이름을 쓴다 ─────────


def _add_record_versions() -> None:
    for table in ("projects", "document_cache"):
        op.add_column(
            table, sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )


# ── 8. 시드 ──────────────────────────────────────────────────────────────────


def _seed() -> None:
    bind = op.get_bind()
    now = _now()

    bind.execute(
        sa.text(
            "INSERT INTO ticket_statuses (key, label, category, sort_order, is_default) "
            "VALUES (:key, :label, :category, :sort_order, :is_default)"
        ),
        [
            {
                "key": key, "label": label, "category": category,
                "sort_order": sort_order, "is_default": is_default,
            }
            for key, label, category, sort_order, is_default in _TICKET_STATUSES
        ],
    )

    bind.execute(
        sa.text(
            "INSERT INTO project_key_registry (key, project_id, state, created_at) "
            "VALUES (:key, NULL, 'reserved', :now)"
        ),
        [{"key": key, "now": now} for key in _RESERVED_KEYS],
    )


def downgrade() -> None:
    for table in ("document_cache", "projects"):
        op.drop_column(table, "version")

    op.drop_index("uq_ticket_statuses_default", table_name="ticket_statuses")
    op.drop_index(op.f("ix_ticket_statuses_category"), table_name="ticket_statuses")
    op.drop_table("ticket_statuses")

    op.drop_table("ticket_watchers")

    op.drop_index("ix_ticket_activities_timeline", table_name="ticket_activities")
    op.drop_index(op.f("ix_ticket_activities_created_at"), table_name="ticket_activities")
    op.drop_index(op.f("ix_ticket_activities_kind"), table_name="ticket_activities")
    op.drop_index(op.f("ix_ticket_activities_ticket_id"), table_name="ticket_activities")
    op.drop_table("ticket_activities")

    op.drop_index("uq_trel_single_parent", table_name="ticket_relations")
    op.drop_index("uq_trel_edge", table_name="ticket_relations")
    op.drop_index(op.f("ix_ticket_relations_kind"), table_name="ticket_relations")
    op.drop_index(op.f("ix_ticket_relations_to_ticket_id"), table_name="ticket_relations")
    op.drop_index(op.f("ix_ticket_relations_from_ticket_id"), table_name="ticket_relations")
    op.drop_table("ticket_relations")

    op.execute("DROP TRIGGER IF EXISTS trg_tickets_canonical_key ON tickets")
    op.execute("DROP FUNCTION IF EXISTS tickets_set_canonical_key()")

    op.drop_index("uq_tickets_legacy", table_name="tickets")
    op.drop_index("uq_tickets_canonical", table_name="tickets")
    op.drop_index("uq_tickets_project_seq", table_name="tickets")
    op.drop_constraint("ck_tickets_version_positive", "tickets", type_="check")
    op.drop_constraint("ck_tickets_key_assigned", "tickets", type_="check")
    op.drop_constraint("ck_tickets_seq_positive", "tickets", type_="check")
    op.drop_index("ix_tickets_backlog", table_name="tickets")
    op.drop_index(op.f("ix_tickets_sprint_id"), table_name="tickets")
    op.drop_constraint("tickets_sprint_id_fkey", "tickets", type_="foreignkey")
    for column in ("backlog_rank", "sprint_id", "version", "legacy_key", "canonical_key", "seq"):
        op.drop_column("tickets", column)

    op.execute("DROP INDEX IF EXISTS uq_sprints_active")
    op.drop_index("uq_sprints_name", table_name="sprints")
    op.drop_index("ix_sprints_window", table_name="sprints")
    op.drop_index(op.f("ix_sprints_project_id"), table_name="sprints")
    op.drop_index(op.f("ix_sprints_org_id"), table_name="sprints")
    op.drop_table("sprints")

    op.drop_index("uq_mex_open_ticket", table_name="migration_exceptions")
    op.drop_index(op.f("ix_migration_exceptions_resolved_at"), table_name="migration_exceptions")
    op.drop_index(op.f("ix_migration_exceptions_ticket_id"), table_name="migration_exceptions")
    op.drop_table("migration_exceptions")

    op.drop_index(op.f("ix_ticket_key_aliases_ticket_id"), table_name="ticket_key_aliases")
    op.drop_table("ticket_key_aliases")
    op.drop_table("project_ticket_counters")

    op.drop_index("uq_pkr_active_project", table_name="project_key_registry")
    op.drop_index("uq_pkr_key_ci", table_name="project_key_registry")
    op.drop_index(op.f("ix_project_key_registry_project_id"), table_name="project_key_registry")
    op.drop_table("project_key_registry")

    op.execute(
        "ALTER TABLE tickets RENAME CONSTRAINT tickets_project_uid_fkey "
        "TO ticket_cache_project_uid_fkey"
    )
    op.execute(
        "ALTER TABLE tickets RENAME CONSTRAINT tickets_org_id_fkey "
        "TO ticket_cache_org_id_fkey"
    )
    for new, old in (
        ("ix_tickets_due_date", "ix_ticket_cache_due_date"),
        ("ix_tickets_notion_missing_at", "ix_ticket_cache_notion_missing_at"),
        ("ix_tickets_notion_page_id", "ix_ticket_cache_notion_page_id"),
        ("ix_tickets_org_id", "ix_ticket_cache_org_id"),
        ("ix_tickets_parent_page_id", "ix_ticket_cache_parent_page_id"),
        ("ix_tickets_project_link", "ix_ticket_cache_project_link"),
        ("ix_tickets_project_uid", "ix_ticket_cache_project_uid"),
        ("ix_tickets_status", "ix_ticket_cache_status"),
        ("tickets_pkey", "ticket_cache_pkey"),
    ):
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    op.execute("ALTER TABLE tickets RENAME TO ticket_cache")
