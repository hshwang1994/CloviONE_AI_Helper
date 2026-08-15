"""문서 동기화·파서 유닛 테스트 (팀 공간 §17)."""

from __future__ import annotations

import pytest

from app.core.models_base import utcnow
from app.team_docs import notion_docs, sync
from app.team_docs.classify import DOC_TYPES, WORK_FIELDS, classify
from app.team_docs.models import SYNC_ERROR, SYNC_OK, DocumentCache, split_names
from app.team_docs.repository import get_by_page_id

pytestmark = pytest.mark.unit

RELMAPS = {
    notion_docs.PROP_TYPE: {"t1": "계약서", "t2": "제안서"},
    notion_docs.PROP_CATEGORY: {"c1": "영업"},
    notion_docs.PROP_PROJECT: {"pr1": "프로젝트X"},
}


def _doc(pid, title, **over):
    base = {
        "notion_page_id": pid, "url": f"https://notion/{pid}",
        "last_edited": "2026-07-01T00:00:00.000Z", "created_time": "2026-06-01T00:00:00.000Z",
        "title": title, "type_ids": ["t1"], "category_ids": ["c1"], "project_ids": ["pr1"],
        "status": "활성", "priority": "높음", "author_names": ["홍길동"], "owner": "김소유",
        "doc_date": "2026-07-01", "orig_date": None, "original_url": "https://orig",
        "source_url": None, "memo": "메모내용", "notion_favorite": False,
        "archived": False, "has_files": True,
    }
    base.update(over)
    return base


def _patch(monkeypatch, docs, *, truncated=False):
    monkeypatch.setattr(notion_docs, "fetch_documents_schema", lambda o, s: {})
    # `failures` 는 C4 로 생긴 선택 인자다(실패한 relation 이름을 담아 준다).
    # 여기서는 실패가 없는 경우를 흉내 내므로 받기만 하고 아무것도 넣지 않는다.
    monkeypatch.setattr(notion_docs, "resolve_relation_maps",
                        lambda o, s, sch, failures=None: RELMAPS)
    monkeypatch.setattr(notion_docs, "query_all_documents", lambda o, s: (docs, truncated))


def test_sync_populates_cache_with_resolved_names(db, settings, monkeypatch):
    _patch(monkeypatch, [_doc("p1", "계약서 A"), _doc("p2", "제안서 B", type_ids=["t2"], archived=True)])
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    assert state.status == SYNC_OK and state.doc_count == 2
    d1 = get_by_page_id(db, "p1")
    assert d1.title == "계약서 A"
    assert split_names(d1.type_names) == ["계약서"]
    assert split_names(d1.category_names) == ["영업"]
    assert split_names(d1.project_names) == ["프로젝트X"]
    assert split_names(d1.author_names) == ["홍길동"] and d1.owner == "김소유" and d1.has_files is True
    # 신규 택소노미가 동기화 때 자동 계산됐다.
    assert d1.document_type in DOC_TYPES and d1.work_field in WORK_FIELDS
    assert d1.classification_manual is False
    d2 = get_by_page_id(db, "p2")
    assert split_names(d2.type_names) == ["제안서"] and d2.archived is True
    # RBAC 재감사(2026-08-16, SEC-35와 같은 자리): 새로 만든 캐시 행이 org_id를 명시적으로
    # 갖는지 확인한다 — tickets/sync.py와 같은 관용. 정직한 한계: 컬럼 기본값도 우연히
    # DEFAULT_ORG_ID라 이 assertion만으로는 "명시했다"와 "기본값이었다"를 구분 못 한다
    # (revert-to-verify로 확인 시도했으나 두 경우 다 통과함, 실제로 확인해 본 뒤 남긴
    # 기록이다) — 그래도 회귀 방지용 문서화 가치는 있어 남긴다.
    from app.org.constants import DEFAULT_ORG_ID
    assert d1.org_id == DEFAULT_ORG_ID


def test_classify_taxonomy():
    dt, wf, tags = classify(["회의록"], ["고객 프로젝트"], "포스코DX 요금 기능 회의")
    assert dt == "회의록" and wf == "개발"
    dt, wf, tags = classify(["보안 점검 보고서"], ["보안 컴플라이언스"], "WEB 보안취약점")
    assert dt == "보고서" and wf == "보안"
    dt, wf, tags = classify([], [], "Docker Iptables 변경")
    assert wf == "자동화" and "Docker" in tags
    # 목록 밖 태그는 안 나온다.
    _, _, tags = classify([], [], "Ubuntu LVM 디스크 용량 확장")
    assert all(t in __import__("app.team_docs.classify", fromlist=["TECH_TAGS"]).TECH_TAGS for t in tags)


def test_sync_truncated_skips_prune(db, settings, monkeypatch):
    # 첫 동기화로 p1,p2 저장.
    _patch(monkeypatch, [_doc("p1", "A"), _doc("p2", "B")])
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    # 다음 동기화가 상한에 걸려 p1만 받아왔다면(truncated) p2를 삭제하지 않는다.
    _patch(monkeypatch, [_doc("p1", "A")], truncated=True)
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    assert state.status == SYNC_OK and state.error  # 일부만 동기화 안내
    assert get_by_page_id(db, "p2") is not None  # 안 받아온 문서를 지우지 않음


def test_sync_prunes_removed_documents(db, settings, monkeypatch):
    _patch(monkeypatch, [_doc("p1", "A"), _doc("p2", "B")])
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    # 두 번째 동기화에서 p2가 사라지면 캐시에서도 지워진다.
    _patch(monkeypatch, [_doc("p1", "A")])
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    assert state.doc_count == 1
    assert get_by_page_id(db, "p1") is not None
    assert get_by_page_id(db, "p2") is None


def test_sync_error_keeps_last_good_cache(db, settings, monkeypatch):
    _patch(monkeypatch, [_doc("p1", "A")])
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    def boom(o, s):
        raise notion_docs.NotionDocsQueryError("Notion 502")

    monkeypatch.setattr(notion_docs, "query_all_documents", boom)
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    assert state.status == SYNC_ERROR and state.error
    # 캐시는 마지막 정상 동기화 그대로.
    assert get_by_page_id(db, "p1") is not None


def test_parse_document_extracts_properties():
    row = {
        "id": "abc", "url": "https://notion/abc", "last_edited_time": "2026-07-05T00:00:00.000Z",
        "created_time": "2026-06-01T00:00:00.000Z",
        "properties": {
            "제목": {"type": "title", "title": [{"plain_text": "테스트 문서"}]},
            "상태": {"type": "select", "select": {"name": "서명됨"}},
            "우선순위": {"type": "select", "select": {"name": "보통"}},
            "유형": {"type": "relation", "relation": [{"id": "t1"}]},
            "즐겨찾기": {"type": "checkbox", "checkbox": True},
            "보관됨": {"type": "checkbox", "checkbox": False},
            "소유자": {"type": "rich_text", "rich_text": [{"plain_text": "소유자님"}]},
            "출처": {"type": "url", "url": "https://example.com"},
            "첨부파일": {"type": "files", "files": [{"name": "a.pdf"}]},
        },
    }
    d = notion_docs.parse_document(row)
    assert d["title"] == "테스트 문서"
    assert d["status"] == "서명됨" and d["priority"] == "보통"
    assert d["type_ids"] == ["t1"]
    assert d["notion_favorite"] is True and d["archived"] is False
    assert d["owner"] == "소유자님" and d["source_url"] == "https://example.com"
    assert d["has_files"] is True


def test_build_create_properties():
    props = notion_docs.build_create_properties(
        title="계약서", status="초안", priority="높음", owner="김소유", memo="메모",
        type_ids=["t1"], category_ids=["c1"], project_ids=[],
    )
    assert props["제목"]["title"][0]["text"]["content"] == "계약서"
    assert props["상태"]["select"]["name"] == "초안"
    assert props["우선순위"]["select"]["name"] == "높음"
    assert props["소유자"]["rich_text"][0]["text"]["content"] == "김소유"
    assert props["유형"]["relation"] == [{"id": "t1"}]
    assert props["카테고리"]["relation"] == [{"id": "c1"}]
    assert "프로젝트" not in props  # 빈 관계는 넣지 않음


def test_body_children_splits_lines_and_caps():
    blocks = notion_docs.body_children("첫 줄\n\n둘째 줄")
    assert [b["type"] for b in blocks] == ["paragraph", "paragraph", "paragraph"]
    assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "첫 줄"
    assert blocks[1]["paragraph"]["rich_text"] == []  # 빈 줄
    big = notion_docs.body_children("\n".join(str(i) for i in range(300)))
    assert len(big) == 100  # Notion children 상한


def test_body_children_recognizes_light_markdown():
    blocks = notion_docs.body_children("## 개요\n- 항목1\n1. 첫째\n---\n일반 문단 ✅")
    assert [b["type"] for b in blocks] == [
        "heading_2", "bulleted_list_item", "numbered_list_item", "divider", "paragraph",
    ]
    assert blocks[0]["heading_2"]["rich_text"][0]["text"]["content"] == "개요"
    assert blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "항목1"
    assert blocks[2]["numbered_list_item"]["rich_text"][0]["text"]["content"] == "첫째"
    assert blocks[3]["divider"] == {}
    assert blocks[4]["paragraph"]["rich_text"][0]["text"]["content"] == "일반 문단 ✅"


def test_document_create_requires_type_and_field():
    from pydantic import ValidationError

    from app.team_docs.schemas import DocumentCreate

    ok = DocumentCreate(title="제목", document_type=list(DOC_TYPES)[0], work_field=list(WORK_FIELDS)[0])
    assert ok.document_type in DOC_TYPES and ok.work_field in WORK_FIELDS
    with pytest.raises(ValidationError):
        DocumentCreate(title="제목", work_field=list(WORK_FIELDS)[0])  # 문서 종류 누락
    with pytest.raises(ValidationError):
        DocumentCreate(title="제목", document_type=list(DOC_TYPES)[0])  # 업무 분야 누락


def test_document_create_body_over_line_cap_is_rejected_not_truncated():
    """본문은 그대로 노션 블록으로 바뀐다(notion_docs.body_children → markdown_to_blocks).
    그 변환기는 100줄을 넘으면 조용히 잘라내므로, 총 글자 수(MAX_BODY=20000)만 보고
    통과시키면 짧은 줄 150개(1300자 남짓, 상한 밑)도 뒤 50줄이 소리 없이 사라진다.
    여기서 거절해야 한다(DocumentBodyUpdate와 같은 규칙)."""
    from pydantic import ValidationError

    from app.team_docs.schemas import DocumentCreate

    body = "\n".join(f"line {i}" for i in range(150))
    with pytest.raises(ValidationError):
        DocumentCreate(
            title="제목", document_type=list(DOC_TYPES)[0], work_field=list(WORK_FIELDS)[0],
            body=body,
        )


def test_block_rendering_maps_known_types():
    # fetch_page_blocks 는 outbound가 필요하므로 여기선 매핑 상수만 확인(구조 안정성).
    assert notion_docs._TEXT_BLOCK_TYPES["heading_1"] == "heading_1"
    assert notion_docs._TEXT_BLOCK_TYPES["bulleted_list_item"] == "bulleted"
    assert notion_docs._TEXT_BLOCK_TYPES["to_do"] == "todo"
    blk = {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "본문"}]}}
    assert notion_docs._block_text(blk, "paragraph") == "본문"


# ── prune 바닥 (C1b) ──────────────────────────────────────────────────────────
# 문서 쪽이 티켓보다 위험하다. `document_cache` 는 미러가 아니라 **일부 필드의 정본**이다:
# `classification_manual=True`(사용자가 손으로 고친 분류)는 Notion 에 대응 필드가 없어서,
# prune 이 지우면 영구 소실이고 재동기화하면 자동 분류가 조용히 덮어쓴다. 아무도 못 알아챈다.


def test_empty_source_never_prunes_documents(db, settings, monkeypatch):
    """소스가 0건을 주면 한 건도 지우지 않고 상태를 error 로 남긴다."""
    _patch(monkeypatch, [_doc("p1", "A"), _doc("p2", "B")])
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    _patch(monkeypatch, [])  # 오류가 아니다 — 200 OK 에 빈 목록
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    assert get_by_page_id(db, "p1") is not None
    assert get_by_page_id(db, "p2") is not None
    assert state.status == SYNC_ERROR
    assert state.pruned_count == 0
    assert "0건" in (state.error or "")


def test_empty_source_preserves_manual_classification(db, settings, monkeypatch):
    """수동 분류가 살아남는가 — Notion 에 없는 값이라 지워지면 되돌릴 방법이 없다."""
    _patch(monkeypatch, [_doc("p1", "A")])
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    row = get_by_page_id(db, "p1")
    row.classification_manual = True
    row.document_type = "손으로 고친 종류"
    db.commit()

    _patch(monkeypatch, [])
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    survived = get_by_page_id(db, "p1")
    assert survived is not None
    assert survived.classification_manual is True
    assert survived.document_type == "손으로 고친 종류"


def test_mass_document_deletion_is_refused(db, settings, monkeypatch):
    """절반을 넘게 지우려 하면 막는다."""
    docs = [_doc(f"p{i}", f"문서{i}") for i in range(1, 11)]
    _patch(monkeypatch, docs)
    sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    _patch(monkeypatch, docs[:3])  # 10 → 3 (70% 삭제 시도)
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    assert db.query(DocumentCache).count() == 10
    assert state.status == SYNC_ERROR
    assert "70%" in (state.error or "")


def test_relation_failure_is_reported_not_swallowed(db, settings, monkeypatch):
    """relation 조회가 실패하면 상태가 `ok` 로 남으면 안 된다 (C4).

    맵이 비면 `classify([], [], title)` 로 떨어져 **전 문서의 문서종류·업무분야·기술태그가
    한 번에 '기타' 로 바뀐다**. 예전에는 그런데도 status=ok, error=null 이었다 —
    다음 성공 동기화가 되돌리지만 그 사이 필터가 전부 무너지고 아무도 이유를 모른다.
    """
    monkeypatch.setattr(notion_docs, "fetch_documents_schema", lambda o, s: {})
    monkeypatch.setattr(
        notion_docs, "resolve_relation_maps",
        # 실제 함수와 같은 모양으로 실패를 보고한다.
        lambda o, s, sch, failures=None: (failures.append(notion_docs.PROP_TYPE)
                                          if failures is not None else None) or {},
    )
    monkeypatch.setattr(notion_docs, "query_all_documents", lambda o, s: ([_doc("p1", "A")], False))

    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()

    assert state.status == SYNC_ERROR, "relation 실패가 'ok' 로 보고됐다"
    assert "분류" in (state.error or ""), f"무엇이 잘못됐는지 안 적혀 있다: {state.error}"
    # 문서 자체는 들어와야 한다 — 분류만 못 한 것이지 목록이 사라지면 안 된다.
    assert get_by_page_id(db, "p1") is not None
