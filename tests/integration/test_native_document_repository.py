"""문서 저장소의 자체 DB 구현 (S14). **나가는 호출 없이 화면이 요구하는 답을 낸다.**

S14 가 소스를 자체 DB 로 바꿨고, 그다음 Notion 모듈이 전부 사라졌다. 이 파일은 그 결과
남은 구현체가 두 가지를 동시에 만족하는지만 본다.

1. **답이 맞다.** 목록·상세가 어떤 필터에 어떤 문서를 내놓는지 여기에 값으로 적어 둔다.
   컷오버 때는 같은 성질을 Notion 구현체와 1:1 로 비교해 증명했지만 그 짝은 이제 없다 —
   비교만 남기면 둘 다 빈 목록을 내도 통과하므로, 처음부터 함께 적어 두던 기대값이
   그대로 판정 근거가 된다.
2. **나가지 않는다.** 본문·프로젝트 목록·생성·보관처리는 Notion 을 부르던 넷이다. 자체 DB
   구현이 그중 하나라도 아직 부르고 있으면 그 화면이 죽는다. 모듈 소스(정적)와 실제
   호출(동적) 양쪽에서 못박는다.

본문 렌더 규칙이 프런트 편집기와 갈라지지 않는지도 함께 본다 — 그 규칙의 정본은
`app/core/notion_blocks.py` 이고, 자체 구현은 그 상한(Notion API 의 100 블록·1900 자)만
빼고 같아야 한다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.errors import AppError, NotFoundError
from app.core.notion_blocks import markdown_to_blocks, rendered_to_markdown
from app.knowledge import blocks as kblocks
from app.knowledge import versions
from app.knowledge.models import VSRC_MIGRATION, Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.team_docs import repository_native, service
from app.team_docs.models import DocumentCache
from app.team_docs.repository_iface import DocumentRepository
from app.team_docs.repository_native import (
    NativeArchiveNeedsSessionError,
    NativeDocumentRepository,
)

pytestmark = pytest.mark.integration


class Boom:
    """만지기만 해도 터지는 아웃바운드 대역.

    "Notion 을 안 부른다" 를 요청 기록이 비었는지로만 확인하면, 클라이언트를 붙들고
    있다가 어느 분기에서만 부르는 코드는 그 분기를 안 지나는 시험에서 초록으로 통과한다.
    속성 접근 자체를 실패로 만들면 그 분기가 있다는 사실이 바로 드러난다.
    """

    def __getattr__(self, name: str):
        raise AssertionError(f"자체 DB 저장소가 아웃바운드 클라이언트를 만졌습니다: {name}")


@pytest.fixture()
def native(settings) -> NativeDocumentRepository:
    return NativeDocumentRepository(settings, Boom())



def _filters(**over) -> dict:
    base = dict(
        search=None, doc_type_f=None, work_field_f=None, project_f=None, tech_f=None,
        sort="recent", offset=0, limit=50,
    )
    base.update(over)
    return base


def _space(db) -> KnowledgeSpace:
    row = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="옮겨 온 문서", slug="migrated",
        owner_kind="organization",
    )
    db.add(row)
    db.flush()
    return row


def _migrated(db, *, page_id: str, body: str) -> Document:
    """S13 이 만들어 두는 상태를 그대로 만든다 — 다리는 `legacy_page_id` 다.

    판을 `versions.snapshot` 으로 쌓는 이유는 그것이 판을 만드는 유일한 입구이기 때문이다
    (D-198). 여기서 `DocumentVersion` 을 직접 만들면 시험만 통과하는 상태를 만들어 놓고
    제품 경로를 검사한 척하게 된다.
    """
    document = Document(space_id=_space(db).id, title="옮겨 온 문서", legacy_page_id=page_id)
    db.add(document)
    db.flush()
    versions.snapshot(
        db, document, kblocks.from_plain_text(body),
        author_id=None, source=VSRC_MIGRATION, reindex=False,
    )
    db.flush()
    return document


# ── 0) 계약 자체 ─────────────────────────────────────────────────────────────


def test_it_covers_the_protocol_with_the_declared_signatures():
    """`DocumentRepository` 가 선언한 일곱을 다 갖고, 인자 이름까지 선언과 같다.

    예전에는 Notion 구현체와 서로 맞춰 봤다. 그쪽이 사라진 지금 기준은 인터페이스 자신이고,
    그것이 원래 맞는 기준이다 — 구현이 하나뿐이어도 계약은 계약이다.

    메서드가 하나 빠지면 그 화면만 500 이 되고, 인자 이름이 하나 다르면 키워드로 부르는
    호출부에서만 깨진다. 둘 다 그 화면을 연 사람에게만 드러난다.
    """
    declared = set(DocumentRepository.__protocol_attrs__)
    assert declared, "Protocol 이 선언한 메서드를 못 읽었다 - 검사가 헛돌고 있다"

    def surface(cls) -> dict[str, list[str]]:
        return {
            name: list(inspect.signature(getattr(cls, name)).parameters)
            for name in declared
        }

    assert declared <= set(dir(NativeDocumentRepository))
    assert surface(NativeDocumentRepository) == surface(DocumentRepository)


# ── 1) 목록·상세가 어떤 필터에 무엇을 내놓는가 ───────────────────────────────


def test_the_list_answers_the_documents_each_filter_asks_for(db, native, make_document):
    """필터마다 나와야 하는 문서를 값으로 적어 둔다.

    필터가 아무 일도 안 하면 검색어를 바꿔도 세 건이 그대로 나오므로, 검색 두 갈래가
    서로 다른 부분집합을 내는 것까지 함께 본다.
    """
    make_document(page_id="doc-a", title="설계 문서", org_wide=True)
    make_document(page_id="doc-b", title="회의록", org_wide=True)
    make_document(page_id="doc-c", title="설계 검토", org_wide=True, status="초안")

    cases = (
        (_filters(), {"doc-a", "doc-b", "doc-c"}),
        (_filters(sort="title"), {"doc-a", "doc-b", "doc-c"}),
        (_filters(search="설계"), {"doc-a", "doc-c"}),
        (_filters(search="회의"), {"doc-b"}),
    )
    for filters, expected in cases:
        rows, total = native.list_documents(db, **filters)
        assert {r.notion_page_id for r in rows} == expected, filters
        assert total == len(expected), filters

    # 총계는 **자르기 전** 건수다. 자른 뒤에 세면 화면이 "2건 중 3-4" 라고 쓴다.
    rows, total = native.list_documents(db, **_filters(limit=2))
    assert len(rows) == 2 and total == 3


def test_get_answers_the_row_and_says_nothing_for_a_miss(db, native, make_document):
    """단건은 그 행을 그대로 돌려주고, **없는 문서에는 `None`** 이다.

    없는 문서에 빈 행을 돌려주면 404 가 떠야 할 자리에 빈 화면이 뜬다.
    """
    row = make_document(page_id="doc-a", title="가 문서", org_wide=True)

    assert native.get(db, page_id="doc-a") is row
    assert native.get(db, page_id="없는-문서") is None


# ── 2) 본문은 저장된 것을 읽는다 ─────────────────────────────────────────────


def test_the_body_comes_from_the_stored_markdown(db, native, make_document):
    """포털 정본(`document_cache.body_markdown`)이 있으면 그것을 렌더한다."""
    row = make_document(page_id="doc-body", title="본문 있는 문서", org_wide=True)
    row.body_markdown = "# 제목\n\n- 하나\n1. 둘\n---\n마지막 문단"
    db.flush()

    assert native.body_blocks(db, page_id="doc-body") == [
        {"kind": "heading_1", "text": "제목"},
        {"kind": "paragraph", "text": ""},
        {"kind": "bulleted", "text": "하나"},
        {"kind": "numbered", "text": "둘"},
        {"kind": "divider", "text": ""},
        {"kind": "paragraph", "text": "마지막 문단"},
    ]


def test_a_document_never_edited_in_the_portal_reads_the_migrated_version(
    db, native, make_document
):
    """정본이 NULL 이면 S13 이 옮긴 판을 읽는다. **이 경로가 없으면 본문이 사라진다.**

    포털에서 한 번도 안 고친 문서는 `body_markdown` 이 NULL 이고, 그 본문의 유일한 사본은
    이관이 지식 도메인에 쌓아 둔 판이다. 다리는 `documents.legacy_page_id` 다.
    """
    make_document(page_id="doc-migrated", title="옮겨 온 문서", org_wide=True)
    _migrated(db, page_id="doc-migrated", body="옮겨 온 본문\n\n두 번째 문단")

    assert native.body_blocks(db, page_id="doc-migrated") == [
        {"kind": "paragraph", "text": "옮겨 온 본문"},
        {"kind": "paragraph", "text": ""},
        {"kind": "paragraph", "text": "두 번째 문단"},
    ]


def test_the_portal_canon_wins_over_the_migrated_version(db, native, make_document):
    """둘 다 있으면 포털 정본이 이긴다 — 이관 뒤에 고친 글이 옛 판에 덮이면 안 된다."""
    row = make_document(page_id="doc-both", title="둘 다 있는 문서", org_wide=True)
    _migrated(db, page_id="doc-both", body="옛 본문")
    row.body_markdown = "새로 고친 본문"
    db.flush()

    assert native.body_blocks(db, page_id="doc-both") == [
        {"kind": "paragraph", "text": "새로 고친 본문"}
    ]


def test_an_unknown_page_id_is_not_an_empty_body(db, native):
    """**반례.** 없는 문서를 빈 본문으로 답하면 편집기가 빈 칸으로 열리고, 그 저장은
    없는 문서를 만드는 시도가 된다. 모르는 것은 모른다고 답한다."""
    with pytest.raises(NotFoundError):
        native.body_blocks(db, page_id="doc-없음")


def test_a_document_with_no_body_anywhere_renders_empty(db, native, make_document):
    """아는 문서인데 본문이 어디에도 없으면 그때는 정말로 빈 본문이다."""
    make_document(page_id="doc-empty", title="본문 없는 문서", org_wide=True)

    assert native.body_blocks(db, page_id="doc-empty") == []


# ── 3) 프로젝트 목록은 projects 표에서 온다 ──────────────────────────────────


def test_project_names_come_from_the_projects_table(db, native, make_project):
    """생성 폼이 고를 수 있는 이름은 우리 프로젝트 표의 이름이다(문서 유무와 무관하다)."""
    make_project(name="나중 프로젝트")
    make_project(name="가나다 프로젝트")

    assert native.project_names(db) == ["가나다 프로젝트", "나중 프로젝트"]


def test_archived_projects_are_not_offered(db, native, make_project):
    """보관한 프로젝트는 뺀다. 지운 프로젝트에 새 문서를 붙이면 그 문서가 아무 데도 안 보인다."""
    from app.core.models_base import utcnow

    keep = make_project(name="살아 있는 프로젝트")
    gone = make_project(name="보관한 프로젝트")
    gone.archived_at = utcnow()
    db.flush()

    assert native.project_names(db) == [keep.name]


def test_the_same_name_is_offered_once(db, native, make_project):
    """이름은 유일하지 않다. 같은 이름이 두 줄로 보이면 사용자는 고를 수가 없다."""
    make_project(name="같은 이름")
    make_project(name="같은 이름")

    assert native.project_names(db) == ["같은 이름"]


# ── 4) 생성은 기존 캐시 경로가 그대로 받는다 ─────────────────────────────────


def test_create_returns_a_page_the_existing_caching_path_accepts(
    db, native, make_user, fake_clock
):
    """`create` 가 돌려준 dict 를 `service.cache_created_document` 가 그대로 소화한다.

    라우터를 안 고치는 것이 이 구현체의 계약이다 — 라우터는 오늘도
    `repo.create(...) → service.cache_created_document(page=...)` 순서로 부른다.
    """
    author = make_user(email="native-create@goodmit.co.kr")
    page = native.create(
        db, title="새 문서", status="초안", priority="보통", owner="담당자",
        memo="메모", body="첫 줄\n둘째 줄", project_names=["가나다 프로젝트"],
        author_id=None,
    )
    assert set(page) == {"id", "url", "created_time", "last_edited_time"}

    row = service.cache_created_document(
        db, page=page, title="새 문서", document_type="회의록", work_field="개발",
        tech_tags=["Python"], project_names=["가나다 프로젝트"], status="초안",
        priority="보통", owner="담당자", memo="메모", now=fake_clock.now(),
        author_name=author.display_name, creator=author,
    )

    # 캐시 경로가 만든 행이 **같은 행**이다(page id 로 다시 찾는다). 두 행이 되면 목록에
    # 같은 문서가 두 번 뜨고, 그중 하나에만 본문이 들어 있다.
    assert row.notion_page_id == page["id"]
    assert db.execute(
        select(DocumentCache).where(DocumentCache.notion_page_id == page["id"])
    ).scalars().all() == [row]

    # 본문은 생성 때 쓴다 — 캐시 경로는 본문을 안 건드리므로 여기서 안 쓰면 사라진다.
    assert row.body_markdown == "첫 줄\n둘째 줄"
    assert native.body_blocks(db, page_id=page["id"]) == [
        {"kind": "paragraph", "text": "첫 줄"},
        {"kind": "paragraph", "text": "둘째 줄"},
    ]
    # 캐시 경로가 채우는 칸도 그대로 채워진다(소속·분류·시각).
    assert row.document_type == "회의록" and row.classification_manual is True
    assert row.last_edited is not None and row.created_time is not None
    assert native.get(db, page_id=page["id"]) is row


def test_a_created_document_shows_up_in_the_list(db, native, make_user, fake_clock):
    """만든 문서가 목록에 바로 뜬다 — 그것이 캐시 경로가 존재하는 이유다."""
    author = make_user(email="native-create-list@goodmit.co.kr")
    page = native.create(
        db, title="목록에 뜰 문서", status=None, priority=None, owner="", memo="",
        body="", project_names=[], author_id=None,
    )
    service.cache_created_document(
        db, page=page, title="목록에 뜰 문서", document_type=None, work_field=None,
        tech_tags=[], project_names=[], status=None, priority=None, owner="", memo="",
        now=fake_clock.now(), author_name=author.display_name, creator=author,
    )

    rows, total = native.list_documents(db, **_filters())
    assert [r.notion_page_id for r in rows] == [page["id"]] and total == 1
    # 빈 본문은 NULL 이 아니라 빈 문자열이다 - 자체 DB 에서는 이 칸이 정본이라
    # NULL(「포털에서 고친 적이 없다」)이 만들어진 적 없는 상태를 뜻하게 된다.
    assert rows[0].body_markdown == ""


# ── 5) 본문 저장 ─────────────────────────────────────────────────────────────


def test_save_body_persists_and_carries_no_push_state(db, native, make_document, fake_clock):
    """자체 DB 에는 어긋날 상대가 없어 「밀어 넣지 못했다」는 상태 자체가 없다.

    예전에는 이 시험이 `result.synced is True and result.sync_error is None` 을 단언했다.
    「언제나 참인 필드가 참이다」는 아무것도 막지 못하고, 응답에 실려 나가는 동안 화면이
    그것을 보고 없는 실패 갈래(「원본에 반영하지 못했습니다」 배너와 재시도 버튼)를
    되살린다. 지금은 필드가 아예 없다 — 되살리면 이 시험이 빨개진다.
    """
    make_document(page_id="doc-save", title="저장할 문서", org_wide=True)

    result = native.save_body(
        db, page_id="doc-save", body_markdown="새 본문", now=fake_clock.now()
    )
    assert hasattr(result, "synced") is False, result
    assert hasattr(result, "sync_error") is False, result
    assert result.body_markdown == "새 본문"

    row = native.get(db, page_id="doc-save")
    assert row.body_markdown == "새 본문"
    assert row.body_synced_at == fake_clock.now()
    assert native.body_blocks(db, page_id="doc-save") == [
        {"kind": "paragraph", "text": "새 본문"}
    ]


def test_save_body_clears_a_stale_sync_error(db, native, make_document, fake_clock):
    """Notion 시절에 남은 「원본 반영 실패」 배너를 지운다.

    원본이 없어진 뒤에도 그 문구가 남아 있으면 사용자는 고칠 방법이 없는 경고를 계속 본다.
    """
    row = make_document(page_id="doc-stale", title="어긋난 문서", org_wide=True)
    row.body_sync_error = "Notion 반영 실패: TimeoutError"
    db.flush()

    native.save_body(db, page_id="doc-stale", body_markdown="고친 본문", now=fake_clock.now())

    assert native.get(db, page_id="doc-stale").body_sync_error is None


def test_saving_a_body_the_repository_cannot_find_is_not_found(db, native, fake_clock):
    """**반례.** 없는 문서에 저장하면 조용히 만들지 않고 없다고 답한다."""
    with pytest.raises(NotFoundError):
        native.save_body(db, page_id="doc-없음", body_markdown="본문", now=fake_clock.now())


# ── 6) 보관처리 ──────────────────────────────────────────────────────────────


def test_archive_hides_the_row_without_deleting_it(db, native, make_document):
    """자체 DB 에서 보관처리는 `archived` 를 세우는 일이다 - 행은 남는다.

    지우면 그 문서의 댓글·즐겨찾기·최근 열람이 가리키는 곳이 사라지고 되돌릴 수 없다.
    """
    make_document(page_id="doc-archive", title="보관할 문서", org_wide=True)

    native.archive(db, page_id="doc-archive")

    rows, total = native.list_documents(db, **_filters())
    assert rows == [] and total == 0
    assert native.get(db, page_id="doc-archive").archived is True


def test_archiving_an_unknown_page_is_not_an_error(db, native):
    """보관기간이 끝난 항목을 치우는 경로가 부른다. 원본이 이미 없는 것은 할 일이 끝난 것이다."""
    native.archive(db, page_id="doc-없음")


def test_archive_without_a_session_fails_loudly(native):
    """**반례.** 세션 없이 조용히 통과하면 사용자가 지운 문서가 목록에 되살아난다.

    휴지통 영구삭제 경로(`app/trash/service.py::_archive_notion`)는 오늘 `db=None` 을
    넘긴다. 그 자리는 S14 배선이 고쳐야 하고, 고치기 전까지는 실패하는 편이 안전하다 -
    실패하면 휴지통 행이 남아 문서는 계속 안 보인다.
    """
    with pytest.raises(NativeArchiveNeedsSessionError):
        native.archive(None, page_id="doc-archive")


# ── 7) 나가는 호출이 없다 ────────────────────────────────────────────────────


def test_the_module_imports_nothing_notion_shaped():
    """정적. 모듈이 import 하는 이름 어디에도 notion 도 outbound 도 없다.

    `scripts/static_checks.sh` 의 경계 검사는 세 모듈 이름만 본다. 여기서는 이 파일
    하나에 대해 **더 좁게** 본다 - 자체 DB 구현체는 소스 특화 모듈을 하나도 몰라야 한다.
    """
    source = Path(inspect.getsourcefile(repository_native)).read_text(encoding="utf-8")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported.extend(f"{node.module or ''}.{alias.name}" for alias in node.names)

    assert imported, "import 를 하나도 못 찾았다 - 검사가 파일을 잘못 읽고 있다"
    offenders = [name for name in imported if "notion" in name or "outbound" in name]
    assert offenders == [], offenders


def test_no_method_touches_the_outbound_client(
    db, native, fake_http, make_document, make_user, fake_clock, make_project
):
    """동적. 여섯 메서드를 전부 지나가도 요청이 한 건도 안 나간다.

    `Boom` 이 속성 접근에서 터지므로 "붙들고 있다가 어느 분기에서만 부르는" 코드도 잡힌다.
    """
    before = len(fake_http.requests)
    make_document(page_id="doc-net", title="망 시험 문서", org_wide=True)
    make_project(name="망 시험 프로젝트")
    author = make_user(email="native-net@goodmit.co.kr")

    native.list_documents(db, **_filters())
    native.get(db, page_id="doc-net")
    native.body_blocks(db, page_id="doc-net")
    native.project_names(db)
    native.save_body(db, page_id="doc-net", body_markdown="본문", now=fake_clock.now())
    page = native.create(
        db, title="새 문서", status=None, priority=None, owner="", memo="", body="본문",
        project_names=["망 시험 프로젝트"], author_id=None,
    )
    service.cache_created_document(
        db, page=page, title="새 문서", document_type=None, work_field=None, tech_tags=[],
        project_names=["망 시험 프로젝트"], status=None, priority=None, owner="", memo="",
        now=fake_clock.now(), author_name=author.display_name, creator=author,
    )
    native.archive(db, page_id="doc-net")

    assert len(fake_http.requests) == before, [
        str(r.url) for r in fake_http.requests[before:]
    ]


def test_the_repository_does_not_keep_the_client(native):
    """붙들고 있지 않다는 것까지 본다 - 붙들면 언젠가 부른다."""
    assert vars(native) == {}


# ── 8) 본문 렌더 규칙이 편집기와 갈라지지 않는다 ─────────────────────────────

# `markdown_to_blocks` 가 내는 블록 종류 → 화면 축약형의 kind. 이 표는 시험 쪽에만 있다 -
# 제품 코드가 저 함수를 안 부르는 이유(아래 두 시험)를 지키면서도 규칙이 같은지는 봐야 한다.
_TYPE_TO_KIND = {
    "divider": "divider",
    "heading_1": "heading_1",
    "heading_2": "heading_2",
    "heading_3": "heading_3",
    "bulleted_list_item": "bulleted",
    "numbered_list_item": "numbered",
    "paragraph": "paragraph",
}

_SAMPLE_LINES = (
    "# 제목", "## 소제목", "### 작은 제목", "#제목아님", "####넷은 제목이 아니다",
    "- 항목", "* 별표 항목", "-붙은 하이픈", "  - 들여쓴 항목",
    "1. 첫째", "10. 열째", "1.점만", "- ", "# ",
    "---", "___", "***", "----",
    "그냥 문단", "  들여쓴 문단", "", "   ", "> 인용은 문단이다", "```",
)


def _kind_from_notion_block(block: dict) -> dict:
    btype = block["type"]
    container = block[btype]
    text = "".join(
        seg["text"]["content"] for seg in (container.get("rich_text") or [])
    )
    return {"kind": _TYPE_TO_KIND[btype], "text": text}


def test_every_line_is_classified_exactly_like_the_shared_markdown_rules():
    """줄 분류가 `app/core/notion_blocks.py` 와 한 줄도 다르지 않다.

    그 규칙은 프런트 편집기 미리보기(BodyEditor)가 쓰는 규칙이기도 하다. 여기서 갈라지면
    사용자가 미리보기에서 본 것과 저장 뒤에 보는 것이 달라진다.

    한 줄씩이 아니라 **본문 한 덩어리로** 비교한다. 빈 줄은 줄 사이에 있을 때만 문단 간격이고,
    한 줄짜리 본문으로 떼어 놓으면 아래 시험이 다루는 다른 상태(본문 자체가 없다)와 겹친다.
    """
    body = "\n".join(_SAMPLE_LINES)
    expected = [_kind_from_notion_block(b) for b in markdown_to_blocks(body)]
    assert len(expected) == len(_SAMPLE_LINES), "표본이 상한(100 블록)에 걸렸다"
    assert repository_native.markdown_to_items(body) == expected


def test_an_absent_body_is_not_one_empty_paragraph():
    """본문이 없는 것과 빈 문단 하나는 다르다.

    공유 함수는 빈 문자열에도 문단 블록을 하나 만든다 — Notion 페이지에는 「블록이 없는
    본문」을 표현할 방법이 없기 때문이다. 화면 축약형에는 있다: 빈 목록이 그것이고,
    편집기가 그것을 되읽으면 다시 빈 본문이 된다.
    """
    assert repository_native.markdown_to_items("") == []
    assert repository_native.markdown_to_items(None) == []
    assert rendered_to_markdown(repository_native.markdown_to_items("")) == ""


def test_the_render_round_trips_through_the_shared_reader():
    """렌더한 것을 편집기가 되읽으면 원래 마크다운이다(`rendered_to_markdown` 의 역)."""
    body = "# 제목\n\n- 하나\n- 둘\n1. 첫째\n---\n마지막 문단"
    assert rendered_to_markdown(repository_native.markdown_to_items(body)) == body


def test_a_long_body_is_not_truncated_the_way_the_notion_call_would_be():
    """**반례.** 공유 함수를 그대로 부르면 안 되는 이유다.

    `markdown_to_blocks` 는 Notion API 의 상한 둘(한 번에 100 블록, 한 줄 1900 자)을 함께
    들고 있다. 그것을 화면 렌더에 쓰면 저장된 글이 101 번째 줄부터 사라지고 긴 문단이
    잘리는데, 편집기는 정본을 그대로 열어 전문을 보여 준다 - 사용자에게는 "읽기 화면에서만
    글이 없어진다" 로 보인다.
    """
    body = "\n".join(f"{index} 번째 줄" for index in range(150))
    items = repository_native.markdown_to_items(body)
    assert len(items) == 150
    assert len(markdown_to_blocks(body)) == 100  # 상한이 실재한다(검사가 헛돌지 않는다)

    long_line = "가" * 2500
    assert repository_native.markdown_to_items(long_line)[0]["text"] == long_line


# ── 9) 격리 계약: 본문 실패는 메타를 안 죽인다 ───────────────────────────────


def test_the_body_failure_stays_an_app_error(db, native):
    """상세 라우터가 본문만 격리할 수 있어야 한다 - 그 격리는 `AppError` 를 잡는다."""
    with pytest.raises(AppError):
        native.body_blocks(db, page_id="doc-없음")


# ── 10) 화면이 실제로 이 구현체 위에서 돈다 ──────────────────────────────────


@pytest.fixture()
def native_wired(app, settings):
    """앱에 배선된 문서 저장소를 자체 DB 구현체로 바꿔 끼운다.

    저장소가 단위로 맞는 것과 **화면이 도는 것**은 다른 말이다. 라우터·서비스는 응답을
    자기 손으로 만들고(`_doc_view`·`body_view`), 그 사이에 낙관적 잠금과 범위 판정이
    있다. 여기까지 지나 봐야 소스를 바꾼 날 화면이 그대로인지 알 수 있다.

    선택기(`app/core/source_registry.py`)를 안 건드리는 이유는 그 배선이 S14 의 일이라서다 -
    이 시험은 배선이 아니라 **배선된 다음의 동작**을 본다.
    """
    from dataclasses import replace

    app.state.repositories = replace(
        app.state.repositories, documents=NativeDocumentRepository(settings, Boom())
    )


def test_the_document_screens_run_on_this_repository_without_notion(
    client, login_as, db, make_document, make_project, native_wired, fake_http
):
    """상세 → 본문 저장 → 새 문서 만들기 → 프로젝트 목록이 요청 한 건 없이 다 된다."""
    csrf = login_as("user", email="native-e2e@goodmit.co.kr")
    row = make_document(page_id="doc-e2e", title="상세 문서", org_wide=True)
    row.body_markdown = "# 제목\n본문"
    db.commit()
    make_project(name="자체 DB 프로젝트")
    before = len(fake_http.requests)

    detail = client.get("/api/team-docs/doc-e2e")
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["blocks_error"] is None
    assert data["blocks"] == [
        {"kind": "heading_1", "text": "제목"},
        {"kind": "paragraph", "text": "본문"},
    ]
    assert data["body_markdown"] == "# 제목\n본문"
    # 상세는 `body_is_local` 을 더 이상 안 싣는다 - 정본이 한 곳뿐이라 근사치라는 상태가 없다.
    assert "body_is_local" not in data

    # 저장은 편집 시작 시점의 지문을 그대로 돌려보낸다(낙관적 잠금이 그대로 산다).
    saved = client.put(
        "/api/team-docs/doc-e2e/body",
        json={"body_markdown": "고친 본문", "base_version": data["body_version"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 200, saved.text
    # 저장 응답에 push 상태가 없다 - 밀어 넣을 원본이 없어 「못 밀어 넣었다」가 성립하지 않는다.
    assert "synced" not in saved.json()
    assert "body_sync_error" not in saved.json()

    # 낡은 지문으로 다시 저장하면 여전히 409 다 - 자체 DB 라고 잠금이 사라지지 않는다.
    stale = client.put(
        "/api/team-docs/doc-e2e/body",
        json={"body_markdown": "덮어쓰기", "base_version": data["body_version"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert stale.status_code == 409, stale.text

    created = client.post(
        "/api/team-docs",
        json={
            "title": "새로 만든 문서", "document_type": "회의록", "work_field": "개발",
            "tech_tags": ["Python"], "project": "자체 DB 프로젝트", "status": "초안",
            "priority": "보통", "owner": "담당자", "memo": "메모", "body": "첫 줄",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text
    new_id = created.json()["document"]["id"]
    assert client.get(f"/api/team-docs/{new_id}").json()["blocks"] == [
        {"kind": "paragraph", "text": "첫 줄"}
    ]

    projects = client.get("/api/team-docs/projects")
    assert projects.status_code == 200, projects.text
    assert "자체 DB 프로젝트" in projects.json()["projects"]

    assert len(fake_http.requests) == before, [
        str(r.url) for r in fake_http.requests[before:]
    ]
