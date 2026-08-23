"""AI Index — `document_chunks` · `ai_index_state` (S9).

Revision ID: 0007_ai_index
Revises: 0006_file_storage
Create Date: 2026-08-23

앱 코드를 import 하지 않는다. 0002~0006 이 적어 둔 이유 그대로다 — 마이그레이션은
**그 시점 스키마의 얼어붙은 스냅숏**이라 `app/ai/models.py` 를 참조하면 나중에 상수를
고치는 날 이 파일의 뜻이 소리 없이 함께 바뀐다. 값을 여기 그대로 적고
`tests/unit/test_ai_domain_seed.py` 가 둘을 맞물려 둔다.

## 🔴 권한 컬럼이 없다

chunk 는 「이 문서의 이 자리에 이런 글이 있다」만 안다. 「누가 볼 수 있는가」는 질의
시각에 `effective_visibility_clause` 가 답한다(D-194 · D-202). 그래서 Permission 변경은
**재임베딩이 아니라 필터 재계산**이고, 재계산은 다음 질의에서 이미 끝나 있다(D-203).

## Vector 인덱스를 만들지 않는다 (D-210)

384차원 exact 스캔이 1,169 벡터에 0.88ms · 49,098 벡터에 42ms 다. Cutover 시점 벡터는
수천 규모라 인덱스가 **필요 없다.** 임계는 약 1.2만 벡터이고, 그때 HNSW
(`m=32`·`ef_construction=200`)를 별도 마이그레이션으로 만든다. 미리 만들면 빌드 비용·
디스크·재색인 복잡도만 지고 얻는 것이 없다.

## `vector` 확장을 **여기서** 만든다

`0001_pg_baseline` 은 `pg_trgm` 만 만들었다 — S2 시점에는 벡터 컬럼이 하나도 없었고,
안 쓰는 확장을 미리 켜 두지 않는 것이 맞았다. 그 타입을 처음 쓰는 것이 이 판이므로
여기서 만든다. Installer Stage 7 도 같은 일을 하지만 `IF NOT EXISTS` 라 겹쳐도 된다.

**확장이 설치되어 있지 않으면 이 줄에서 죽는다.** 그것이 맞다 — 「타입이 없다」보다
「확장이 없다」가 운영자에게 훨씬 가까운 사실이고, 조치도 한 줄이다
(`apt-get install postgresql-16-pgvector`).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0007_ai_index'
down_revision = '0006_file_storage'
branch_labels = None
depends_on = None


# 값을 여기 얼려 둔다. 정본은 `app/ai/models.py` 와 `app/ai/catalog.py` 이고 시험이 맞물린다.
_SOURCE_KINDS = ("document", "file")
_ANCHOR_KINDS = ("block", "page", "slide", "section", "sheet", "text")
_STATES = ("pending", "ok", "failed")
_VECTOR_DIM = 384


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


def upgrade() -> None:
    # `vector(384)` 를 쓰기 전에. 없으면 여기서 죽고, 그 죽음이 「확장이 없다」를 말한다.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_chunks()
    _create_index_state()


def _create_chunks() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        # 🔴 권한을 묻는 자리. 첨부에서 나온 chunk 도 부모 문서를 가리킨다(D-253).
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("anchor_kind", sa.String(length=16), nullable=False),
        sa.Column("anchor_ref", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("anchor_label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        # pgvector 의 고정 차원 실수 배열. 아직 임베딩이 없으면 NULL 이고 **그것이 정상**
        # 이다 — 모델이 없는 설치에서도 파싱과 chunk 는 돈다(D-201 의 경계).
        sa.Column("embedding", _vector_type(), nullable=True),
        sa.Column("parser_version", sa.String(length=16), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("embedding_version", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("indexed_at", sa.DateTime(), nullable=False),
        sa.Column("embedded_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # 문서가 사라지면 그 문서의 chunk 도 사라진다. 파생 데이터라 남길 이유가 없다.
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("source_kind", _SOURCE_KINDS), name="ck_chunk_source_kind"),
        sa.CheckConstraint(_in_list("anchor_kind", _ANCHOR_KINDS), name="ck_chunk_anchor_kind"),
        sa.CheckConstraint("length(btrim(text)) > 0", name="ck_chunk_text_nonempty"),
        sa.CheckConstraint("ordinal >= 0", name="ck_chunk_ordinal_nonneg"),
        sa.CheckConstraint("length(text_sha256) = 64", name="ck_chunk_sha_len"),
        sa.CheckConstraint(
            "(source_kind = 'file') = (file_id IS NOT NULL)", name="ck_chunk_file_pair"
        ),
        # 벡터가 있으면 **무엇으로 만들었는지도 있다.** 없으면 모델을 바꾼 날 어느
        # 벡터가 옛것인지 가릴 수가 없다.
        sa.CheckConstraint(
            "embedding IS NULL OR ("
            "embedded_at IS NOT NULL AND length(btrim(embedding_model)) > 0 "
            "AND length(btrim(embedding_version)) > 0)",
            name="ck_chunk_embedding_provenance",
        ),
        sa.CheckConstraint(
            "(embedding IS NULL) = (embedded_at IS NULL)", name="ck_chunk_embedded_pair"
        ),
    )
    op.create_index(
        op.f("ix_document_chunks_source_kind"), "document_chunks", ["source_kind"]
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"]
    )
    op.create_index(op.f("ix_document_chunks_file_id"), "document_chunks", ["file_id"])
    op.create_index(
        op.f("ix_document_chunks_text_sha256"), "document_chunks", ["text_sha256"]
    )
    # `file_id` 가 NULL 인 문서 chunk 와 파일 chunk 를 한 인덱스로 묶으려면 NULL 을 값으로
    # 접어야 한다 — PG 는 NULL 을 서로 다른 값으로 보기 때문에 그냥 두면 중복이 들어온다.
    op.execute(
        "CREATE UNIQUE INDEX uq_chunk_unit_ordinal ON document_chunks "
        "(document_id, coalesce(file_id, ''), ordinal)"
    )
    op.create_index(
        "ix_chunk_document_ordinal", "document_chunks", ["document_id", "ordinal"]
    )
    # 「임베딩이 아직 없는 chunk」 — 모델이 나중에 생긴 설치가 이것으로 따라잡는다.
    op.execute(
        "CREATE INDEX ix_chunk_pending_embedding ON document_chunks (document_id) "
        "WHERE embedding IS NULL"
    )


def _create_index_state() -> None:
    op.create_table(
        "ai_index_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("indexed_version_id", sa.String(length=36), nullable=True),
        sa.Column("parser_version", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("embedding_model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("embedding_version", sa.String(length=16), nullable=False, server_default=""),
        sa.Column(
            "attachment_fingerprint", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.CheckConstraint(_in_list("status", _STATES), name="ck_index_state_status"),
        sa.CheckConstraint("chunk_count >= 0", name="ck_index_state_chunks_nonneg"),
        sa.CheckConstraint(
            "embedded_count >= 0 AND embedded_count <= chunk_count",
            name="ck_index_state_embedded_range",
        ),
    )
    op.create_index(op.f("ix_ai_index_state_status"), "ai_index_state", ["status"])
    # 문서 하나에 상태 행은 하나다. 둘이면 「할 일」이 두 번 잡히고 chunk 가 두 벌 생긴다.
    op.create_index("uq_index_state_document", "ai_index_state", ["document_id"], unique=True)
    op.create_index(
        "ix_index_state_queue", "ai_index_state", ["status", "next_attempt_at", "queued_at"]
    )


def _vector_type():
    """`vector(384)` 컬럼 타입.

    `app/ai/models.py::Vector` 를 import 하지 않는다(위 docstring). 마이그레이션이
    필요한 것은 **DDL 문자열 하나**뿐이라 여기서 최소한으로 다시 적는다.
    """
    from sqlalchemy.types import UserDefinedType

    class _Vector(UserDefinedType):
        cache_ok = True

        def get_col_spec(self, **kw):  # noqa: ARG002
            return f"vector({_VECTOR_DIM})"

    return _Vector()


def downgrade() -> None:
    op.drop_index("ix_index_state_queue", table_name="ai_index_state")
    op.drop_index("uq_index_state_document", table_name="ai_index_state")
    op.drop_index(op.f("ix_ai_index_state_status"), table_name="ai_index_state")
    op.drop_table("ai_index_state")

    op.execute("DROP INDEX IF EXISTS ix_chunk_pending_embedding")
    op.drop_index("ix_chunk_document_ordinal", table_name="document_chunks")
    op.execute("DROP INDEX IF EXISTS uq_chunk_unit_ordinal")
    op.drop_index(op.f("ix_document_chunks_text_sha256"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_file_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_source_kind"), table_name="document_chunks")
    op.drop_table("document_chunks")
