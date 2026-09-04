"""빈 문서를 치운다 (사용자 지시 2026-09-04).

## 무엇을 지우나

「본문에 내용이 없거나 글자 수가 20자 이하인 문서」다. Confluence 와 Notion 에는 제목만
있는 페이지가 흔하다 — 하위를 묶는 목차이거나 만들다 만 자리다. 우리 쪽에서는 목록과
검색에서 자리를 차지하는데 열어 보면 아무것도 없다.

## 여기서 보는 것

  1. 20자 이하가 지워지고 21자는 안 지워진다 — 문턱이 실제로 문턱이다.
  2. 판이 아예 없는 문서(한 번도 저장 안 됨)도 지워진다.
  3. 🔴 **자체 작성 문서는 안 지워진다.** 사람이 방금 만든 빈 문서는 쓰려던 자리다.
  4. 지우는 방식이 **제품의 삭제**다 — 행이 남고, 휴지통에 뜨고, 되돌릴 수 있다.
  5. `--dry-run` 이 아무것도 안 쓴다.
  6. 제목은 안 센다 — 사용자가 말한 것은 본문이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "prune-me@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    """길이가 서로 다른 문서 다섯 + 자체 작성 하나."""
    from app.core.models_base import new_uuid
    from app.knowledge.models import (
        SOURCE_MIGRATION, SOURCE_USER, Document, DocumentVersion, KnowledgeSpace,
    )
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping
    from app.org.constants import DEFAULT_ORG_ID

    actor = make_user(ME, role="system_admin", display_name="지운 사람")
    space = KnowledgeSpace(name="팀 문서", slug="prune-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()

    def make(title: str, text: str | None, *, native: bool = False) -> Document:
        doc = Document(
            space_id=space.id, title=title,
            source_type=(SOURCE_USER if native else SOURCE_MIGRATION),
        )
        db.add(doc)
        db.flush()
        if text is not None:
            version = DocumentVersion(
                id=new_uuid(), document_id=doc.id, version_no=1,
                body={"type": "doc", "content": []},
                body_text=text, body_markdown=text, author_id=actor.id,
            )
            db.add(version)
            db.flush()
            doc.current_version_id = version.id
        if not native:
            db.add(LegacyMapping(
                legacy_source=SRC_CONFLUENCE, legacy_source_id=f"page-{title}",
                target_type=T_DOCUMENT, target_id=doc.id,
            ))
        db.flush()
        return doc

    ids = {
        "empty": make("빈 문서", "").id,
        "no_version": make("판이 없는 문서", None).id,
        "twenty": make("스무 자 문서", "가" * 20).id,
        "twentyone": make("스물한 자 문서", "가" * 21).id,
        # 🔴 제목이 길어도 본문이 짧으면 지운다 — 세는 것은 본문이다.
        "long_title": make("아주 긴 제목을 가진 문서인데 본문은 비어 있습니다", "").id,
        "native": make("사람이 만든 빈 문서", "", native=True).id,
    }
    db.commit()
    return {"actor": actor, "ids": ids}


def _prune(db, world, **kw):
    from app.migration import prune

    result = prune.prune_empty(db, actor=world["actor"], **kw)
    db.commit()
    return result


def _archived(db, doc_id) -> bool:
    from app.knowledge.models import Document

    db.expire_all()
    return bool(db.get(Document, doc_id).archived)


def test_the_threshold_is_actually_a_threshold(db, world):
    """20자는 지우고 21자는 안 지운다. 반례가 없으면 「전부 지운다」도 초록이다."""
    _prune(db, world)
    assert _archived(db, world["ids"]["twenty"]), "20자 문서가 안 지워졌다"
    assert not _archived(db, world["ids"]["twentyone"]), "21자 문서까지 지웠다"


def test_a_document_that_was_never_saved_is_pruned_too(db, world):
    """판이 아예 없는 문서도 「본문에 내용이 없는 문서」다."""
    _prune(db, world)
    assert _archived(db, world["ids"]["no_version"])
    assert _archived(db, world["ids"]["empty"])


def test_a_long_title_does_not_save_an_empty_document(db, world):
    """세는 것은 **본문**이다 — 제목이 길어도 본문이 비었으면 빈 문서다."""
    _prune(db, world)
    assert _archived(db, world["ids"]["long_title"])


def test_a_native_document_is_never_pruned(db, world):
    """🔴 사람이 방금 만든 빈 문서는 쓰레기가 아니라 **쓰려던 자리**다."""
    result = _prune(db, world)
    assert not _archived(db, world["ids"]["native"]), "자체 작성 문서를 지웠다"
    assert result.refused_native == 1, result.as_dict()


def test_pruning_is_the_product_delete_not_a_row_removal(db, world):
    """행이 남고 휴지통에 뜨고 되돌릴 수 있다 — 이관이 삭제 의미를 새로 만들지 않는다."""
    from app.knowledge.models import Document

    _prune(db, world)
    doc = db.get(Document, world["ids"]["empty"])
    assert doc is not None, "행을 지웠다 — 이력·멘션·관계가 함께 사라진다"
    assert doc.archived is True
    assert doc.archived_at is not None, "언제 지웠는지가 없으면 휴지통이 말할 수 없다"
    assert doc.archived_by == world["actor"].id, "누가 지웠는지가 없다"


def test_dry_run_writes_nothing(db, world):
    """세기만 하는 회차가 하나라도 지우면 그것은 세는 것이 아니라 쓰는 것이다."""
    result = _prune(db, world, dry_run=True)
    assert result.deleted >= 4, result.as_dict()
    for key in ("empty", "no_version", "twenty", "long_title"):
        assert not _archived(db, world["ids"][key]), f"{key} 를 dry-run 이 지웠다"


def test_the_limit_is_a_parameter_not_a_constant(db, world):
    """문턱을 바꾸면 결과가 바뀐다 — 20 이 코드에 박혀 있지 않다."""
    _prune(db, world, max_chars=25)
    assert _archived(db, world["ids"]["twentyone"]), "문턱을 올렸는데 21자가 남았다"
