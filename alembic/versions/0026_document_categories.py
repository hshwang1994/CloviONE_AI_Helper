"""문서 카테고리 — 조직이 스스로 만드는 분류 어휘와 그 첫 시드.

Revision ID: 0026_document_categories
Revises: 0025_ticket_body_doc
Create Date: 2026-09-02

## 무엇이 문제였나

`documents.doc_type` 은 CHECK 도 CRUD 도 없는 자유 문자열이었다. 값의 출처는 Notion
이관뿐이고, 신규 문서는 전부 `NULL` 로 만들어졌다 — 화면에 분류를 고를 자리도, 분류를
관리할 자리도 없었으므로 그 축은 이관 시점에 얼어붙어 있었다.

## 무엇을 하는가

1. `document_categories` 표를 만든다 — `tags` 와 같은 조직 스코프·slug 유일 규약.
2. `documents.category_id` 를 더한다 — `ON DELETE SET NULL`(폴더와 같은 규약: 분류를
   지워도 문서는 미분류로 돌아올 뿐 지워지지 않는다).
3. **시드**: 조직별 distinct `doc_type` 값마다 카테고리를 만들고, 그 값을 가진 문서를
   매핑한다. 근거 없는 분류는 만들지 않는다 — `doc_type` 이 NULL 인 문서는 미분류로
   남는다(0022 폴더 이관이 정한 것과 같은 원칙).

`doc_type` 컬럼은 **지우지 않는다.** 이관 데이터의 정본이고, 검색 인덱서가 카테고리
없는 문서의 분류로 계속 읽는다. 신규 기록만 화면이 중단한다.

## 시드가 멱등인 이유

문서 매핑이 `category_id IS NULL` 조건을 달아, 다시 돌려도 이미 분류된 문서를 덮지
않는다. 카테고리 생성은 slug 조회 후 없을 때만 INSERT 라(0024 의 `_ensure_tag` 와 같은
모양) 중복이 생기지 않고, 경합은 `uq_dcat_slug` 가 잡는다.

## 되돌리기

FK → 인덱스 → 컬럼 → 표 순서로 지운다. `doc_type` 이 손대지 않은 정본이라 이관분의
분류는 무손실로 돌아간다. 0026 이후 화면에서 새로 만든 카테고리와 새로 단 분류만
사라진다 — 그것을 알고 지운다(0022 와 같은 「기능적 복원」 수준).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0026_document_categories"
down_revision = "0025_ticket_body_doc"
branch_labels = None
depends_on = None

_SPACE_RE = re.compile(r"\s+")

#: 새 카테고리 사이 간격 — `app/knowledge/categories.py::_SORT_STEP` 과 같은 값.
_SORT_STEP = 1024


def _slugify(name: str) -> str:
    """`app/knowledge/tags.py::slugify` 와 동일한 규칙이다. 마이그레이션은 그 시점의 앱
    모듈이 아니라 이 규칙 자체(NFKC 정규화 + 공백 접기 + casefold)에 의존해야 하므로
    여기 다시 적는다 — 앱 코드가 나중에 바뀌어도 이미 적용된 마이그레이션은 안 바뀐다.
    (규칙 표류는 tests/regression/test_migration_0026_categories.py 가 두 벌을 대조해 잡는다.)
    """
    folded = unicodedata.normalize("NFKC", name or "").strip().casefold()
    return _SPACE_RE.sub(" ", folded)


def _ensure_category(conn, cache: dict, org_id, name: str, sort_order: int, now) -> str:
    slug = _slugify(name)
    key = (org_id, slug)
    if key in cache:
        return cache[key]
    category_id = conn.execute(sa.text(
        "SELECT id FROM document_categories WHERE slug = :s"
        " AND ((org_id IS NULL AND CAST(:o AS varchar) IS NULL) OR org_id = :o)"
    ), {"s": slug, "o": org_id}).scalar()
    if category_id is None:
        category_id = str(uuid.uuid4())
        conn.execute(sa.text(
            "INSERT INTO document_categories"
            " (id, org_id, name, slug, sort_order, created_at, updated_at)"
            " VALUES (:id, :o, :n, :s, :so, :now, :now)"
        ), {"id": category_id, "o": org_id, "n": name, "s": slug, "so": sort_order, "now": now})
    cache[key] = category_id
    return category_id


def upgrade() -> None:
    op.create_table(
        "document_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_dcat_name_nonempty"),
    )
    op.create_index(op.f("ix_document_categories_org_id"), "document_categories", ["org_id"])
    op.create_index("uq_dcat_slug", "document_categories", ["org_id", "slug"], unique=True)

    op.add_column("documents", sa.Column("category_id", sa.String(length=36), nullable=True))
    # 이름을 명시하는 이유: 이름 없는 제약은 autogenerate 가 모델과 대조할 때마다
    # 삭제 diff 를 낸다 (0021 `documents_archived_by_fkey` 와 같은 관례).
    op.create_foreign_key(
        "documents_category_id_fkey", "documents", "document_categories",
        ["category_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_documents_category_id"), "documents", ["category_id"])

    # ── 시드 — 조직별 distinct doc_type → 카테고리 + 문서 매핑 ───────────────
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cache: dict = {}

    rows = conn.execute(sa.text(
        "SELECT DISTINCT s.org_id AS org_id, d.doc_type AS doc_type"
        "  FROM documents d JOIN knowledge_spaces s ON s.id = d.space_id"
        " WHERE d.doc_type IS NOT NULL AND length(btrim(d.doc_type)) > 0"
        " ORDER BY org_id, doc_type"
    )).all()

    order_by_org: dict = {}
    for org_id, doc_type in rows:
        name = str(doc_type).strip()
        slug = _slugify(name)
        if not slug:
            continue
        order_by_org[org_id] = order_by_org.get(org_id, 0) + _SORT_STEP
        category_id = _ensure_category(conn, cache, org_id, name, order_by_org[org_id], now)
        conn.execute(sa.text(
            "UPDATE documents d SET category_id = :cid"
            " WHERE d.doc_type = :dt AND d.category_id IS NULL"
            "   AND d.space_id IN ("
            "     SELECT id FROM knowledge_spaces"
            "      WHERE ((org_id IS NULL AND CAST(:o AS varchar) IS NULL) OR org_id = :o)"
            "   )"
        ), {"cid": category_id, "dt": doc_type, "o": org_id})


def downgrade() -> None:
    op.drop_constraint("documents_category_id_fkey", "documents", type_="foreignkey")
    op.drop_index(op.f("ix_documents_category_id"), table_name="documents")
    op.drop_column("documents", "category_id")
    op.drop_index("uq_dcat_slug", table_name="document_categories")
    op.drop_index(op.f("ix_document_categories_org_id"), table_name="document_categories")
    op.drop_table("document_categories")
