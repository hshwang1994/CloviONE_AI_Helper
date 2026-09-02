"""0026 — 문서 카테고리 표와 FK 가 계약대로 섰는가.

여기서 못박는 성질 셋:

1. **스키마가 모델과 같은 모양이다** — 표·컬럼·유일 인덱스·SET NULL FK. 시험 DB 는
   conftest 가 `alembic upgrade head` 로 만들므로, 이 단언이 통과하면 0026 의 DDL 이
   실제로 그 모양을 만들었다는 뜻이다.
2. **SET NULL 이 실제로 동작한다** — 카테고리를 지우면 문서 행이 남고 분류만 풀린다.
   FK 선언과 동작은 다른 사실이다(선언만 보고 통과시키면 ondelete 오타를 못 잡는다).
3. **시드의 정규화 규칙이 앱과 같은 한 벌이다** — 0026 은 앱 모듈을 import 하지 않고
   `_slugify` 를 다시 적었다(0024 와 같은 근거). 두 벌 규칙이 갈라지면 시드가 만든
   카테고리를 관리 화면이 「같은 이름」으로 못 알아본다. 0024 는 그 걱정을 docstring
   으로만 남겼고, 여기서는 시험으로 못박는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.regression


def _cols(db, table: str) -> set[str]:
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def test_the_category_table_has_the_contracted_shape(db):
    insp = inspect(db.get_bind())
    assert "document_categories" in set(insp.get_table_names())
    assert {"id", "org_id", "name", "slug", "sort_order", "created_at", "updated_at"} <= _cols(
        db, "document_categories"
    )
    uniques = {
        tuple(ix["column_names"])
        for ix in insp.get_indexes("document_categories")
        if ix.get("unique")
    }
    assert ("org_id", "slug") in uniques, "조직 안 slug 유일 규약이 없다"


def test_documents_point_at_categories_with_set_null(db):
    insp = inspect(db.get_bind())
    assert "category_id" in _cols(db, "documents")
    fks = {
        tuple(fk["constrained_columns"]): fk
        for fk in insp.get_foreign_keys("documents")
    }
    fk = fks.get(("category_id",))
    assert fk is not None, "FK 선언이 없다 — 지워진 카테고리를 가리키는 문서가 남는다"
    assert fk["referred_table"] == "document_categories"
    assert (fk.get("options") or {}).get("ondelete", "").upper() == "SET NULL"


def test_deleting_a_category_orphans_nothing(db, make_user):
    """SET NULL 의 **실동작** — 카테고리 행을 지우면 문서는 남고 분류만 풀린다."""
    from app.knowledge.models import Document, DocumentCategory, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    space = KnowledgeSpace(name="0026 공간", slug="mig-0026", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()
    category = DocumentCategory(org_id=DEFAULT_ORG_ID, name="0026분류", slug="0026분류")
    db.add(category)
    db.flush()
    doc = Document(space_id=space.id, title="0026 문서", category_id=category.id)
    db.add(doc)
    db.commit()

    # ORM 을 우회해 DB 차원의 삭제로 FK 동작 자체를 본다.
    from sqlalchemy import text

    db.execute(text("DELETE FROM document_categories WHERE id = :i"), {"i": category.id})
    db.commit()
    db.expire_all()

    survivor = db.get(Document, doc.id)
    assert survivor is not None, "카테고리를 지웠는데 문서가 함께 사라졌다"
    assert survivor.category_id is None


def test_the_seed_slug_rule_matches_the_app_rule():
    """0026 의 `_slugify` 사본과 `app.knowledge.tags.slugify` 가 같은 답을 낸다."""
    import importlib.util
    from pathlib import Path

    from app.knowledge.tags import slugify

    path = Path("alembic/versions/0026_document_categories.py")
    spec = importlib.util.spec_from_file_location("mig_0026", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    samples = [
        "회의록", " 회의록 ", "회의  록", "Tech Note", "TECH NOTE",
        "ＴＥＣＨ", "기술/인프라", "", "   ",
    ]
    for sample in samples:
        assert module._slugify(sample) == slugify(sample), sample
