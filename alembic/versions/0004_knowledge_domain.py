"""Knowledge Domain — 공간 · 폴더 트리 · 문서 · 판 · 태그 · 관계 · 멘션 (S7).

Revision ID: 0004_knowledge_domain
Revises: 0003_work_domain
Create Date: 2026-08-22

앱 코드를 import 하지 않는다. 0002·0003 이 적어 둔 이유 그대로다 — 마이그레이션은
**그 시점 스키마의 얼어붙은 스냅숏**이라 `app/knowledge/models.py` 를 참조하면 나중에
상수를 고치는 날 이 파일의 뜻이 소리 없이 함께 바뀐다. 값을 여기 그대로 적고
`tests/unit/test_knowledge_domain_seed.py` 가 둘을 맞물려 둔다.

## 폴더의 `path` 와 `depth` 는 트리거가 만든다 (D-244)

0003 이 `canonical_key` 에서 쓴 방법 그대로다(D-236). 자료구조가 두 벌이기 때문이다:
부모를 가리키는 `parent_id` 와 조상을 한 줄에 담은 `path`. 둘이 어긋나면 「이 폴더 아래
전부」가 틀린 답을 내는데, 그 틀림은 조용하다 — 목록에 한 건이 덜 나오는 것으로 보인다.

트리거는 셋을 한다:
  1. BEFORE INSERT/UPDATE — 부모에서 `path`·`depth` 를 파생시킨다. 앱이 무엇을 적든 덮는다
  2. 같은 트리거가 **순환을 거절한다** — 새 부모의 `path` 안에 자기 id 가 있으면 예외
  3. AFTER UPDATE — 부모가 바뀌면 **자손 전부**의 `path`·`depth` 를 따라 고친다

3번이 없으면 폴더를 옮긴 뒤 그 아래 것들이 옛 조상을 계속 가리킨다.

## `documents ↔ document_versions` 는 서로를 가리킨다

`documents.current_version_id` → `document_versions.id` 이고 `document_versions.document_id`
→ `documents.id` 다. 어느 표를 먼저 만들어도 한쪽 FK 를 걸 수 없으므로, 문서 쪽 FK 는
두 표가 다 선 다음에 `ALTER TABLE` 로 건다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0004_knowledge_domain'
down_revision = '0003_work_domain'
branch_labels = None
depends_on = None


# 값을 여기 얼려 둔다. 정본은 `app/knowledge/models.py` 이고 시험이 둘을 맞물린다.
_SPACE_OWNER_KINDS = ("project", "department", "organization", "unset")
_SOURCE_TYPES = ("USER", "AI", "MIGRATION")
_VERSION_SOURCES = ("USER", "AI", "MIGRATION", "RESTORE")
_DREL_KINDS = ("supersedes", "references", "relates_to")
_MENTION_KINDS = ("user", "document", "ticket")
_MAX_FOLDER_DEPTH = 16
# `app/knowledge/folders.py::PATH_SEP` 와 같은 글자여야 한다.
_PATH_SEP = "/"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


# ── 트리거 ───────────────────────────────────────────────────────────────────

_FOLDER_PATH_FN = f"""
CREATE OR REPLACE FUNCTION folders_set_path() RETURNS trigger AS $$
DECLARE
  parent_path text;
  parent_depth int;
BEGIN
  IF NEW.parent_id IS NULL THEN
    NEW.path := '{_PATH_SEP}' || NEW.id || '{_PATH_SEP}';
    NEW.depth := 0;
    RETURN NEW;
  END IF;

  SELECT f.path, f.depth INTO parent_path, parent_depth
    FROM folders f WHERE f.id = NEW.parent_id;

  IF parent_path IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'foreign_key_violation',
      MESSAGE = 'parent folder not found: ' || NEW.parent_id;
  END IF;

  -- 순환. 앱에서도 막지만(사람이 읽을 메시지를 주려고) 이 함수를 안 지나는 경로가
  -- 언젠가 생긴다 — 마이그레이션 · 콘솔 · 스크립트.
  IF position('{_PATH_SEP}' || NEW.id || '{_PATH_SEP}' in parent_path) > 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'check_violation',
      MESSAGE = 'folder cannot be moved inside its own subtree: ' || NEW.id;
  END IF;

  NEW.path := parent_path || NEW.id || '{_PATH_SEP}';
  NEW.depth := parent_depth + 1;

  IF NEW.depth > {_MAX_FOLDER_DEPTH} THEN
    RAISE EXCEPTION USING ERRCODE = 'check_violation',
      MESSAGE = 'folder tree deeper than {_MAX_FOLDER_DEPTH} levels: ' || NEW.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_FOLDER_MOVE_FN = f"""
CREATE OR REPLACE FUNCTION folders_move_subtree() RETURNS trigger AS $$
BEGIN
  IF NEW.path = OLD.path THEN
    RETURN NULL;
  END IF;

  -- 자손의 `path` 앞부분을 새 조상 경로로 갈아 끼운다. `depth` 는 길이 차이만큼 민다.
  -- BEFORE 트리거가 각 행에 대해 다시 도는 것이 아니라 여기서 한 번에 고친다 —
  -- 행마다 트리거를 태우면 깊은 트리에서 갱신이 제곱으로 는다.
  UPDATE folders
     SET path = NEW.path || substring(path from length(OLD.path) + 1),
         depth = depth + (NEW.depth - OLD.depth)
   WHERE path LIKE OLD.path || '%'
     AND id <> NEW.id;

  IF EXISTS (SELECT 1 FROM folders WHERE depth > {_MAX_FOLDER_DEPTH}) THEN
    RAISE EXCEPTION USING ERRCODE = 'check_violation',
      MESSAGE = 'folder tree deeper than {_MAX_FOLDER_DEPTH} levels after move';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_FOLDER_PATH_TRIGGER = """
CREATE TRIGGER trg_folders_set_path
  BEFORE INSERT OR UPDATE OF parent_id ON folders
  FOR EACH ROW EXECUTE FUNCTION folders_set_path();
"""

_FOLDER_MOVE_TRIGGER = """
CREATE TRIGGER trg_folders_move_subtree
  AFTER UPDATE OF parent_id ON folders
  FOR EACH ROW EXECUTE FUNCTION folders_move_subtree();
"""


def upgrade() -> None:
    _create_spaces()
    _create_folders()
    _create_documents()
    _create_versions()
    _link_current_version()
    _create_relations()
    _create_tags()
    _create_mentions()


# ── 1. 공간 ──────────────────────────────────────────────────────────────────


def _create_spaces() -> None:
    op.create_table(
        "knowledge_spaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_kind", sa.String(length=16), nullable=False, server_default="unset"),
        sa.Column("owner_dept_id", sa.String(length=36), nullable=True),
        sa.Column("owner_project_id", sa.String(length=36), nullable=True),
        sa.Column("confidential", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_dept_id"], ["org_units.id"]),
        sa.ForeignKeyConstraint(["owner_project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            _in_list("owner_kind", _SPACE_OWNER_KINDS), name="ck_kspace_owner_kind"
        ),
        sa.CheckConstraint(
            "(owner_kind = 'department') = (owner_dept_id IS NOT NULL)",
            name="ck_kspace_dept_pair",
        ),
        sa.CheckConstraint(
            "(owner_kind = 'project') = (owner_project_id IS NOT NULL)",
            name="ck_kspace_project_pair",
        ),
    )
    op.create_index(op.f("ix_knowledge_spaces_org_id"), "knowledge_spaces", ["org_id"])
    op.create_index(
        op.f("ix_knowledge_spaces_owner_kind"), "knowledge_spaces", ["owner_kind"]
    )
    op.create_index(
        op.f("ix_knowledge_spaces_owner_dept_id"), "knowledge_spaces", ["owner_dept_id"]
    )
    op.create_index(
        op.f("ix_knowledge_spaces_owner_project_id"), "knowledge_spaces", ["owner_project_id"]
    )
    op.create_index(
        op.f("ix_knowledge_spaces_confidential"), "knowledge_spaces", ["confidential"]
    )
    op.create_index(op.f("ix_knowledge_spaces_archived"), "knowledge_spaces", ["archived"])
    op.create_index("uq_kspace_slug", "knowledge_spaces", ["org_id", "slug"], unique=True)
    op.create_index(
        "ix_kspace_owner", "knowledge_spaces", ["org_id", "owner_kind", "archived"]
    )


# ── 2. 폴더 트리 ─────────────────────────────────────────────────────────────


def _create_folders() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("space_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("path", sa.Text(), nullable=False, server_default=""),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["space_id"], ["knowledge_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["folders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id <> parent_id", name="ck_folder_not_self"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_folder_name_nonempty"),
        sa.CheckConstraint(f"depth <= {_MAX_FOLDER_DEPTH}", name="ck_folder_depth"),
    )
    op.create_index(op.f("ix_folders_space_id"), "folders", ["space_id"])
    op.create_index(op.f("ix_folders_parent_id"), "folders", ["parent_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_folder_sibling_name ON folders (space_id, parent_id, name) "
        "WHERE parent_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_folder_root_name ON folders (space_id, name) "
        "WHERE parent_id IS NULL"
    )
    op.create_index(
        "ix_folder_sibling_order", "folders", ["space_id", "parent_id", "sort_order"]
    )
    # 접두 검색(`path LIKE '/a/%'`)이 인덱스를 타려면 `text_pattern_ops` 여야 한다 —
    # 기본 연산자 클래스는 로캘 정렬이라 LIKE 접두를 못 쓴다.
    op.execute("CREATE INDEX ix_folder_subtree ON folders (path text_pattern_ops)")

    op.execute(_FOLDER_PATH_FN)
    op.execute(_FOLDER_PATH_TRIGGER)
    op.execute(_FOLDER_MOVE_FN)
    op.execute(_FOLDER_MOVE_TRIGGER)


# ── 3. 문서 ──────────────────────────────────────────────────────────────────


def _create_documents() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("space_id", sa.String(length=36), nullable=False),
        sa.Column("folder_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="USER"),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("confidential", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("legacy_page_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["space_id"], ["knowledge_spaces.id"], ondelete="CASCADE"),
        # 폴더를 지워도 문서는 안 지운다 — 공간 뿌리로 올라온다.
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            _in_list("source_type", _SOURCE_TYPES), name="ck_document_source_type"
        ),
    )
    op.create_index(op.f("ix_documents_space_id"), "documents", ["space_id"])
    op.create_index(op.f("ix_documents_folder_id"), "documents", ["folder_id"])
    op.create_index(op.f("ix_documents_doc_type"), "documents", ["doc_type"])
    op.create_index(op.f("ix_documents_source_type"), "documents", ["source_type"])
    op.create_index(op.f("ix_documents_confidential"), "documents", ["confidential"])
    op.create_index(op.f("ix_documents_archived"), "documents", ["archived"])
    op.execute(
        "CREATE UNIQUE INDEX uq_document_legacy_page ON documents (legacy_page_id) "
        "WHERE legacy_page_id IS NOT NULL"
    )
    op.create_index(
        "ix_document_space_folder", "documents", ["space_id", "folder_id", "archived"]
    )
    op.create_index("ix_document_updated", "documents", ["space_id", "updated_at"])


# ── 4. 판 ────────────────────────────────────────────────────────────────────


def _create_versions() -> None:
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        # 정본. `JsonText`(문자열 계약)가 아니라 진짜 `jsonb` 다 — 이 값은 블록 단위로
        # 읽는다(diff · 인용 앵커 · 멘션 추출).
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column("change_reason", sa.String(length=500), nullable=True),
        sa.Column("ai_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="USER"),
        sa.Column("prev_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["prev_version_id"], ["document_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in_list("source", _VERSION_SOURCES), name="ck_dver_source"),
        sa.CheckConstraint("version_no >= 1", name="ck_dver_no_positive"),
    )
    op.create_index(op.f("ix_document_versions_document_id"), "document_versions", ["document_id"])
    op.create_index(op.f("ix_document_versions_created_at"), "document_versions", ["created_at"])
    op.create_index(
        "uq_dver_document_no", "document_versions", ["document_id", "version_no"], unique=True
    )
    op.create_index("ix_dver_history", "document_versions", ["document_id", "version_no"])


def _link_current_version() -> None:
    """두 표가 다 선 다음에 문서 → 판 FK 를 건다.

    `SET NULL` 인 이유: 판이 지워지는 유일한 경로는 문서가 지워질 때의 CASCADE 인데,
    그 순간 이 컬럼은 이미 사라진다. 그래도 `RESTRICT` 로 두면 데이터 정리 스크립트가
    판 하나를 지우려다 문서 전체를 못 건드리게 된다.
    """
    op.create_foreign_key(
        "documents_current_version_id_fkey", "documents", "document_versions",
        ["current_version_id"], ["id"], ondelete="SET NULL",
    )


# ── 5. 관계 ──────────────────────────────────────────────────────────────────


def _create_relations() -> None:
    op.create_table(
        "document_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("from_document_id", sa.String(length=36), nullable=False),
        sa.Column("to_document_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["from_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in_list("kind", _DREL_KINDS), name="ck_drel_kind"),
        sa.CheckConstraint("from_document_id <> to_document_id", name="ck_drel_not_self"),
        sa.CheckConstraint(
            "kind <> 'relates_to' OR from_document_id < to_document_id",
            name="ck_drel_symmetric_ordered",
        ),
    )
    op.create_index(
        op.f("ix_document_relations_from_document_id"), "document_relations",
        ["from_document_id"],
    )
    op.create_index(
        op.f("ix_document_relations_to_document_id"), "document_relations", ["to_document_id"]
    )
    op.create_index(op.f("ix_document_relations_kind"), "document_relations", ["kind"])
    op.create_index(
        "uq_drel_edge", "document_relations",
        ["from_document_id", "to_document_id", "kind"], unique=True,
    )


# ── 6. 태그 ──────────────────────────────────────────────────────────────────


def _create_tags() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_tag_name_nonempty"),
    )
    op.create_index(op.f("ix_tags_org_id"), "tags", ["org_id"])
    op.create_index("uq_tag_slug", "tags", ["org_id", "slug"], unique=True)

    op.create_table(
        "document_tags",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "tag_id"),
    )
    op.create_index("ix_dtag_by_tag", "document_tags", ["tag_id", "document_id"])


# ── 7. 멘션 ──────────────────────────────────────────────────────────────────


def _create_mentions() -> None:
    op.create_table(
        "document_mentions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        # FK 를 안 건다 — 대상 표가 셋이라 한 컬럼으로 걸 수 없다. 지워진 대상을
        # 가리키는 멘션은 화면에서 「없는 대상」으로 보이는 것이 맞다.
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in_list("target_kind", _MENTION_KINDS), name="ck_dmention_kind"),
    )
    op.create_index(
        op.f("ix_document_mentions_document_id"), "document_mentions", ["document_id"]
    )
    op.create_index(
        "uq_dmention", "document_mentions",
        ["document_id", "block_id", "target_kind", "target_id"], unique=True,
    )
    op.create_index(
        "ix_dmention_target", "document_mentions", ["target_kind", "target_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_dmention_target", table_name="document_mentions")
    op.drop_index("uq_dmention", table_name="document_mentions")
    op.drop_index(op.f("ix_document_mentions_document_id"), table_name="document_mentions")
    op.drop_table("document_mentions")

    op.drop_index("ix_dtag_by_tag", table_name="document_tags")
    op.drop_table("document_tags")
    op.drop_index("uq_tag_slug", table_name="tags")
    op.drop_index(op.f("ix_tags_org_id"), table_name="tags")
    op.drop_table("tags")

    op.drop_index("uq_drel_edge", table_name="document_relations")
    op.drop_index(op.f("ix_document_relations_kind"), table_name="document_relations")
    op.drop_index(
        op.f("ix_document_relations_to_document_id"), table_name="document_relations"
    )
    op.drop_index(
        op.f("ix_document_relations_from_document_id"), table_name="document_relations"
    )
    op.drop_table("document_relations")

    op.drop_constraint("documents_current_version_id_fkey", "documents", type_="foreignkey")

    op.drop_index("ix_dver_history", table_name="document_versions")
    op.drop_index("uq_dver_document_no", table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_created_at"), table_name="document_versions")
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_table("document_versions")

    op.drop_index("ix_document_updated", table_name="documents")
    op.drop_index("ix_document_space_folder", table_name="documents")
    op.execute("DROP INDEX IF EXISTS uq_document_legacy_page")
    op.drop_index(op.f("ix_documents_archived"), table_name="documents")
    op.drop_index(op.f("ix_documents_confidential"), table_name="documents")
    op.drop_index(op.f("ix_documents_source_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_doc_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_folder_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_space_id"), table_name="documents")
    op.drop_table("documents")

    op.execute("DROP TRIGGER IF EXISTS trg_folders_move_subtree ON folders")
    op.execute("DROP FUNCTION IF EXISTS folders_move_subtree()")
    op.execute("DROP TRIGGER IF EXISTS trg_folders_set_path ON folders")
    op.execute("DROP FUNCTION IF EXISTS folders_set_path()")
    op.execute("DROP INDEX IF EXISTS ix_folder_subtree")
    op.drop_index("ix_folder_sibling_order", table_name="folders")
    op.execute("DROP INDEX IF EXISTS uq_folder_root_name")
    op.execute("DROP INDEX IF EXISTS uq_folder_sibling_name")
    op.drop_index(op.f("ix_folders_parent_id"), table_name="folders")
    op.drop_index(op.f("ix_folders_space_id"), table_name="folders")
    op.drop_table("folders")

    op.drop_index("ix_kspace_owner", table_name="knowledge_spaces")
    op.drop_index("uq_kspace_slug", table_name="knowledge_spaces")
    op.drop_index(op.f("ix_knowledge_spaces_archived"), table_name="knowledge_spaces")
    op.drop_index(op.f("ix_knowledge_spaces_confidential"), table_name="knowledge_spaces")
    op.drop_index(
        op.f("ix_knowledge_spaces_owner_project_id"), table_name="knowledge_spaces"
    )
    op.drop_index(op.f("ix_knowledge_spaces_owner_dept_id"), table_name="knowledge_spaces")
    op.drop_index(op.f("ix_knowledge_spaces_owner_kind"), table_name="knowledge_spaces")
    op.drop_index(op.f("ix_knowledge_spaces_org_id"), table_name="knowledge_spaces")
    op.drop_table("knowledge_spaces")
