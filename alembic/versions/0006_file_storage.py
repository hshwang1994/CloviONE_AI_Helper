"""File Storage — 저장소 · 파일 metadata · 문서 첨부 (S8).

Revision ID: 0006_file_storage
Revises: 0005_real_dates
Create Date: 2026-08-22

앱 코드를 import 하지 않는다. 0002~0004 가 적어 둔 이유 그대로다 — 마이그레이션은
**그 시점 스키마의 얼어붙은 스냅숏**이라 `app/storage/models.py` 를 참조하면 나중에
상수를 고치는 날 이 파일의 뜻이 소리 없이 함께 바뀐다. 값을 여기 그대로 적고
`tests/unit/test_storage_domain_seed.py` 가 둘을 맞물려 둔다.

## 표 셋이 함께 선다

S7 이 `document_attachments` 를 **일부러 안 만들었다.** 첨부는 `files` 를 가리키고
`files` 는 `storage_providers` 를 가리킨다(D-199). 저장소 없이 첨부 표만 만들면 그
컬럼이 무엇을 가리키는지 정하지 못한 채 굳는다.

## 역할마다 켜진 저장소는 하나뿐이다

`uq_sprov_role_enabled` 가 부분 유니크로 강제한다. 「업로드가 어디로 가는가」에 답이
둘이면 어제 올린 파일과 오늘 올린 파일이 다른 장치에 있고, 그 사실은 백업을 복원할
때 처음 드러난다.

## 기본 LOCAL 저장소를 여기서 넣지 않는다

경로가 설치처마다 다르기 때문이다(`data_dir`). 마이그레이션에 경로를 박으면 개발
머신에서 만든 값이 운영에 그대로 간다. 부트스트랩은 `app/storage/service.py::
ensure_default_provider` 가 하고, Installer Stage 11 이 그것을 부른다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0006_file_storage'
down_revision = '0005_real_dates'
branch_labels = None
depends_on = None


# 값을 여기 얼려 둔다. 정본은 `app/storage/adapters.py` 이고 시험이 둘을 맞물린다.
_KINDS = ("LOCAL", "NFS", "SMB")
_ROLES = ("OPERATIONAL", "BACKUP")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    _create_providers()
    _create_files()
    _create_attachments()


# ── 1. 저장소 ────────────────────────────────────────────────────────────────


def _create_providers() -> None:
    op.create_table(
        "storage_providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="LOCAL"),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="OPERATIONAL"),
        sa.Column("base_path", sa.Text(), nullable=False),
        sa.Column("mount_point", sa.Text(), nullable=True),
        sa.Column(
            "config_json", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default="{}",
        ),
        # **이름이지 값이 아니다.** 실제 자격증명은 `secrets_dir` 파일에 있다.
        sa.Column("credentials_ref", sa.String(length=120), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(_in_list("kind", _KINDS), name="ck_sprov_kind"),
        sa.CheckConstraint(_in_list("role", _ROLES), name="ck_sprov_role"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_sprov_name_nonempty"),
        # 절대 경로만 받는다. 상대 경로는 프로세스의 작업 디렉터리에 따라 다른 곳을
        # 가리키고, 워커와 웹은 작업 디렉터리가 같다는 보장이 없다.
        #
        # **드라이브 문자를 함께 허용한다**(`C:/…`). 제품이 도는 곳은 Ubuntu 뿐이고
        # 거기서는 첫 갈래만 쓰이지만, 개발·시험 머신은 Windows 다. POSIX 모양만
        # 받으면 저장소 도메인이 그 머신에서 **한 건도 시험되지 않는다** — 이 제약이
        # 막으려는 것은 「상대 경로」이지 「Windows」가 아니다.
        sa.CheckConstraint(
            "base_path LIKE '/%' OR base_path ~ '^[A-Za-z]:/'",
            name="ck_sprov_base_absolute",
        ),
        sa.CheckConstraint(
            "mount_point IS NULL OR mount_point LIKE '/%' "
            "OR mount_point ~ '^[A-Za-z]:/'",
            name="ck_sprov_mount_absolute",
        ),
        sa.CheckConstraint(
            "(kind = 'LOCAL') = (mount_point IS NULL)", name="ck_sprov_mount_pair"
        ),
    )
    op.create_index(op.f("ix_storage_providers_kind"), "storage_providers", ["kind"])
    op.create_index(op.f("ix_storage_providers_role"), "storage_providers", ["role"])
    op.create_index(op.f("ix_storage_providers_enabled"), "storage_providers", ["enabled"])
    op.create_index("uq_sprov_name", "storage_providers", ["name"], unique=True)
    op.create_index("ix_sprov_role_enabled", "storage_providers", ["role", "enabled"])
    # 역할마다 **켜진 것은 하나**. 부분 유니크라 꺼 둔 저장소는 몇 개든 남길 수 있다 —
    # 옮겨 가는 중에는 옛 저장소를 꺼서 남겨 둬야 파일을 마저 읽을 수 있다.
    op.execute(
        "CREATE UNIQUE INDEX uq_sprov_role_enabled ON storage_providers (role) "
        "WHERE enabled"
    )


# ── 2. 파일 ──────────────────────────────────────────────────────────────────


def _create_files() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("storage_provider_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=120), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("owner_ref", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        # 파일이 남아 있는 저장소는 못 지운다. 지울 수 있게 하면 그 행들이 어느 장치를
        # 가리켰는지 아무도 모르게 된다.
        sa.ForeignKeyConstraint(
            ["storage_provider_id"], ["storage_providers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("size_bytes > 0", name="ck_file_size_positive"),
        sa.CheckConstraint("length(checksum_sha256) = 64", name="ck_file_checksum_len"),
        sa.CheckConstraint("length(btrim(filename)) > 0", name="ck_file_name_nonempty"),
    )
    op.create_index(
        op.f("ix_files_storage_provider_id"), "files", ["storage_provider_id"]
    )
    op.create_index(op.f("ix_files_checksum_sha256"), "files", ["checksum_sha256"])
    op.create_index(op.f("ix_files_owner_ref"), "files", ["owner_ref"])
    op.create_index(op.f("ix_files_created_at"), "files", ["created_at"])
    op.create_index(
        "uq_file_provider_key", "files", ["storage_provider_id", "storage_key"], unique=True
    )
    op.create_index("ix_file_owner_ref", "files", ["owner_ref", "created_at"])


# ── 3. 문서 첨부 ─────────────────────────────────────────────────────────────


def _create_attachments() -> None:
    op.create_table(
        "document_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Numeric(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        # `document_tags` 와 같은 규약이다 — 문서를 지우면 연결이 사라진다.
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        # 파일 행을 지우면 연결도 사라진다. 반대로 연결을 지운다고 파일이 사라지지는
        # 않는다 — 한 파일이 여러 문서에 붙어 있을 수 있다.
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_attachments_document_id"), "document_attachments", ["document_id"]
    )
    op.create_index(
        op.f("ix_document_attachments_file_id"), "document_attachments", ["file_id"]
    )
    op.create_index(
        "uq_dattach_document_file", "document_attachments",
        ["document_id", "file_id"], unique=True,
    )
    op.create_index(
        "ix_dattach_order", "document_attachments", ["document_id", "sort_order"]
    )


def downgrade() -> None:
    op.drop_index("ix_dattach_order", table_name="document_attachments")
    op.drop_index("uq_dattach_document_file", table_name="document_attachments")
    op.drop_index(
        op.f("ix_document_attachments_file_id"), table_name="document_attachments"
    )
    op.drop_index(
        op.f("ix_document_attachments_document_id"), table_name="document_attachments"
    )
    op.drop_table("document_attachments")

    op.drop_index("ix_file_owner_ref", table_name="files")
    op.drop_index("uq_file_provider_key", table_name="files")
    op.drop_index(op.f("ix_files_created_at"), table_name="files")
    op.drop_index(op.f("ix_files_owner_ref"), table_name="files")
    op.drop_index(op.f("ix_files_checksum_sha256"), table_name="files")
    op.drop_index(op.f("ix_files_storage_provider_id"), table_name="files")
    op.drop_table("files")

    op.execute("DROP INDEX IF EXISTS uq_sprov_role_enabled")
    op.drop_index("ix_sprov_role_enabled", table_name="storage_providers")
    op.drop_index("uq_sprov_name", table_name="storage_providers")
    op.drop_index(op.f("ix_storage_providers_enabled"), table_name="storage_providers")
    op.drop_index(op.f("ix_storage_providers_role"), table_name="storage_providers")
    op.drop_index(op.f("ix_storage_providers_kind"), table_name="storage_providers")
    op.drop_table("storage_providers")
