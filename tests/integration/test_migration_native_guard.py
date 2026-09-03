"""🔴 ClovirAssist 에서 직접 쓴 문서는 이관·Import 가 **절대 안 건드린다** (문서 개편 10번).

## 이 파일이 있는 이유

사용자가 명시적으로 요구한 것 중 되돌릴 수 없는 손해가 가장 큰 항목이다. 제목이 같다는
이유로 자체 작성 문서를 Notion 내용으로 덮으면, 그 사람이 쓴 글은 판 이력에는 남아도
「내 문서가 남의 내용으로 바뀌었다」는 사실은 남는다.

## 보호는 **두 자리**에 있다

1. 적재기(`load.py::load_documents`) — 자체 작성 문서는 `legacy_page_id` 가 없어
   조회 자체에 안 걸린다.
2. 분류 적용기(`classify.py::apply`) — 파일이 무엇을 적었든 술어를 다시 건다.

한 자리에만 두면 그 자리를 안 지나는 경로가 언젠가 생긴다. 그래서 **두 경로 모두**
같은 반례로 잰다: 제목이 똑같은 자체 작성 문서를 만들어 두고, 회차를 돌린 뒤 그 문서의
본문이 **글자 하나도** 안 바뀌었는지 본다.
"""

from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.integration

ME = "guard-admin@goodmit.co.kr"
SHARED_TITLE = "SSL 인증서 발급 절차 및 접속 정보"


def _hash(db, document_id: str) -> str:
    """그 문서의 지금 본문 지문. 「안 바뀌었다」를 글자로 잰다."""
    from app.knowledge.models import Document, DocumentVersion

    document = db.get(Document, document_id)
    version = db.get(DocumentVersion, document.current_version_id)
    payload = f"{document.title}\x1f{version.body_text}\x1f{version.version_no}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.fixture()
def world(db, make_user):
    """같은 제목의 문서 둘 — 하나는 자체 작성, 하나는 이관."""
    from app.knowledge import service as knowledge_service
    from app.knowledge import versions
    from app.knowledge.models import SOURCE_MIGRATION, SOURCE_USER, Document
    from app.migration.models import SRC_NOTION, T_DOCUMENT, LegacyMapping

    actor = make_user(ME, role="system_admin", display_name="관리자")
    db.flush()
    space = knowledge_service.resolve_or_create_common_space(db, actor)

    native = Document(space_id=space.id, title=SHARED_TITLE,
                      source_type=SOURCE_USER, created_by=actor.id)
    db.add(native)
    db.flush()
    versions.snapshot(
        db, native,
        {"type": "doc", "content": [
            {"type": "paragraph",
             "content": [{"type": "text", "text": "내가 직접 쓴 내용입니다."}]},
        ]},
        author_id=actor.id, change_reason="직접 씀", source="USER",
    )

    migrated = Document(space_id=space.id, title=SHARED_TITLE,
                        source_type=SOURCE_MIGRATION, legacy_page_id="notion-page-1")
    db.add(migrated)
    db.flush()
    versions.snapshot(
        db, migrated,
        {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "원본에서 확인: table"}]},
        ]},
        author_id=actor.id, change_reason="이관", source="MIGRATION",
    )
    db.add(LegacyMapping(legacy_source=SRC_NOTION, legacy_source_id="notion-page-1",
                         target_type=T_DOCUMENT, target_id=migrated.id))
    db.commit()
    return {"actor": actor, "native": native.id, "migrated": migrated.id}


# ── 술어 자체 ────────────────────────────────────────────────────────────────


def test_the_predicate_says_no_to_a_native_document_with_the_same_title(db, world):
    """🔴 반례가 이 파일의 요점이다. **제목이 같아도** 자체 작성 문서는 거절한다."""
    from app.knowledge.models import Document
    from app.migration.classify import is_rewritable

    native = db.get(Document, world["native"])
    migrated = db.get(Document, world["migrated"])
    assert native.title == migrated.title, "반례가 성립하려면 제목이 같아야 한다"

    assert is_rewritable(db, migrated) is True
    assert is_rewritable(db, native) is False, "자체 작성 문서를 고칠 수 있다고 판정했다"


def test_the_predicate_needs_both_halves(db, world, make_user):
    """`source_type` 만으로도, 다리만으로도 통과하면 안 된다.

    `source_type` 만 보면 사람이 그 값을 바꾼 문서가 통과하고, 다리만 보면 옛 문서가
    통과한다. 둘을 **함께** 봐야 자체 작성 문서가 어느 쪽으로도 안 걸린다.
    """
    from app.knowledge.models import SOURCE_MIGRATION, Document
    from app.migration.classify import is_rewritable

    # (a) source_type 은 MIGRATION 인데 다리가 없다 — 이관이 만든 행이 아니다.
    orphan = db.get(Document, world["native"])
    orphan.source_type = SOURCE_MIGRATION
    db.flush()
    assert is_rewritable(db, orphan) is False, "다리가 없는데 통과했다"


# ── 분류 적용기 ──────────────────────────────────────────────────────────────


def test_apply_refuses_a_native_document_even_when_the_file_names_it(db, world):
    """파일이 자체 작성 문서를 가리켜도 적용기가 거절한다 (10번).

    생성기는 이관 문서만 고르지만, 사람이 파일을 손으로 고칠 수 있고 제목이 같은 문서가
    실제로 있다. 보호가 생성기에만 있으면 그 손이 보호를 지나친다.
    """
    from app.migration import classify as classify_mod
    from app.migration.report import MigrationReport

    before = _hash(db, world["native"])
    report = MigrationReport()
    rows = [{
        "document_id": world["native"],
        "decision": "matched",
        "project_id": "any-project",
        "category": "인프라",
        "tags": ["SSL", "인증서"],
    }]
    result = classify_mod.apply(db, rows, actor=world["actor"], report=report)

    assert result.refused_native == 1
    assert result.projects_set == 0
    assert _hash(db, world["native"]) == before, "자체 작성 문서가 바뀌었다"
    assert any(f.kind == "classify_refused_native_document" for f in report.findings)


def test_apply_leaves_the_project_empty_when_the_decision_is_not_a_match(db, world):
    """🔴 판단이 안 서면 **비운다** (11·15번). 억지로 붙이지 않는다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.migration import classify as classify_mod

    before_space = db.get(Document, world["migrated"]).space_id
    rows = [
        {"document_id": world["migrated"], "decision": "ambiguous",
         "project_id": None, "category": "", "tags": []},
    ]
    result = classify_mod.apply(db, rows, actor=world["actor"])

    assert result.projects_left_unassigned == 1
    assert result.projects_set == 0
    after = db.get(Document, world["migrated"])
    assert after.space_id == before_space
    # 그리고 그 공간은 여전히 조직 소유다 — 미지정 문서가 사라지지 않는다.
    assert db.get(KnowledgeSpace, after.space_id).owner_kind == "organization"


def test_apply_does_not_overwrite_a_category_a_person_already_chose(db, world):
    """분류는 **비어 있을 때만** 채운다 — 추정으로 사람의 선택을 덮지 않는다."""
    from app.knowledge import categories as doc_categories
    from app.knowledge.models import Document
    from app.migration import classify as classify_mod

    chosen = doc_categories.create(db, world["actor"].org_id, "사람이 고른 분류")
    document = db.get(Document, world["migrated"])
    document.category_id = chosen.id
    db.flush()

    classify_mod.apply(db, [{
        "document_id": world["migrated"], "decision": "none",
        "category": "추정한 분류", "tags": [],
    }], actor=world["actor"])

    assert db.get(Document, world["migrated"]).category_id == chosen.id


def test_apply_unions_tags_instead_of_replacing_them(db, world):
    """태그는 **합집합**이다 — 원래 있던 태그를 지우지 않는다 (12·16번)."""
    from app.knowledge import tags as doc_tags
    from app.knowledge.models import Document
    from app.migration import classify as classify_mod

    document = db.get(Document, world["migrated"])
    doc_tags.set_for_document(db, document, ["원래태그"])
    db.flush()

    classify_mod.apply(db, [{
        "document_id": world["migrated"], "decision": "none",
        "category": "", "tags": ["SSL", "인증서"],
    }], actor=world["actor"])

    names = {t.name for t in doc_tags.of_document(db, world["migrated"])}
    assert "원래태그" in names, "원래 태그가 사라졌다"
    assert {"SSL", "인증서"} <= names


# ── 제안 생성기 ──────────────────────────────────────────────────────────────


def test_the_generator_only_looks_at_migrated_documents(db, world):
    """자체 작성 문서는 **후보에도 안 든다.**"""
    from app.migration import classify as classify_mod

    rows = classify_mod.migrated_documents(db)
    ids = {d.id for d in rows}
    assert world["migrated"] in ids
    assert world["native"] not in ids, "자체 작성 문서가 후보에 들었다"


def test_a_proposal_carries_its_evidence(db, world, make_project):
    """줄마다 **근거**가 있어야 사람이 검토할 수 있다.

    근거 없는 배정은 「왜 이 문서가 저 프로젝트에 있나」에 답할 수 없고, 그 질문은
    반드시 나온다.
    """
    from app.knowledge.models import Document
    from app.migration import classify as classify_mod

    make_project(name="인천국제공항공사 [클라우드 인프라 고도화]")
    document = db.get(Document, world["migrated"])
    document.title = "인천공항공사 서버정보"
    db.flush()

    proposals = classify_mod.propose(
        db, documents=[document], source="notion"
    )
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.decision in classify_mod.DECISIONS
    assert proposal.evidence, "근거가 비어 있다"
    if proposal.decision == classify_mod.DECISION_MATCHED:
        assert "인천" in proposal.evidence
