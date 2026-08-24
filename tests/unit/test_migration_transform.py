"""소스의 모양이 우리 도메인의 모양으로 **정확히** 바뀌는가 (S13).

qa-contract-change: 옛 정책은 소스 `티켓 ID` 의 접두사(`GIT`)를 이름의 근거로 삼아 파서가 `legacy_prefix` 를 함께 돌려줬고 이 파일이 그 값을 못박고 있었다. 지금은 프로젝트 코드를 서버가 짓고 접두사는 이름의 근거가 아니므로(D-282) 파서가 그 키를 더 내지 않는다 — 없는 키를 재는 단언은 성립하지 않아 지웠고, 같은 속성의 `number` 는 재번호 순서로 여전히 쓰이므로 그 단언은 그대로 남겼다.

여기 있는 표본은 전부 실제 Notion 응답의 모양이다. 파서를 응답 없이 시험하면
「우리가 상상한 응답」만 확인하게 된다.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from app.knowledge import blocks as block_mod
from app.migration import transform
from app.migration.source_notion import NotionSourceError
from app.work import models as work_models

pytestmark = pytest.mark.unit


def _rich(text: str, **annotations) -> dict:
    return {
        "plain_text": text,
        "text": {"content": text},
        "annotations": {
            "bold": False, "italic": False, "strikethrough": False,
            "underline": False, "code": False, **annotations,
        },
        "href": annotations.pop("href", None) if "href" in annotations else None,
    }


TASK_ROW = {
    "id": "262c5c5a-0000-0000-0000-000000000001",
    "url": "https://www.notion.so/task-1",
    "created_time": "2026-01-02T03:04:05.000Z",
    "last_edited_time": "2026-08-20T10:11:12.000Z",
    "archived": False,
    "properties": {
        "제목": {"type": "title", "title": [_rich("포털 로그인 개선")]},
        "티켓 ID": {"type": "unique_id", "unique_id": {"prefix": "GIT", "number": 142}},
        "진행상태": {"type": "status", "status": {"name": "진행"}},
        "우선순위": {"type": "select", "select": {"name": "높음"}},
        "난이도": {"type": "select", "select": {"name": "3"}},
        "예상 WD": {"type": "number", "number": 2.5},
        "실제 WD": {"type": "number", "number": 3},
        "시작일": {"type": "date", "date": {"start": "2026-08-01"}},
        "마감일": {"type": "date", "date": {"start": "2026-08-15"}},
        "대분류": {"type": "rich_text", "rich_text": [_rich("인증")]},
        "티켓 담당자": {"type": "people", "people": [
            {"id": "user-1", "name": "임승환",
             "person": {"email": "shim@goodmit.co.kr", "email_verified": True}},
        ]},
        "프로젝트": {"type": "relation", "relation": [{"id": "project-page-1"}]},
        "상위 작업": {"type": "relation", "relation": [{"id": "parent-page-1"}]},
        "파일과 미디어": {"type": "files", "files": [
            {"name": "ddl.sql", "file": {"url": "https://s3.example/ddl.sql"}},
            {"name": "설계", "external": {"url": "https://sharepoint.example/doc"}},
        ]},
    },
}


# ── 작업 ─────────────────────────────────────────────────────────────────────


def test_a_task_row_lands_in_ticket_columns():
    parsed = transform.parse_task(TASK_ROW)
    assert parsed["title"] == "포털 로그인 개선"
    # 이 번호는 이름이 아니라 **재번호를 매기는 순서**다. 순서를 잃으면 소스에서 먼저
    # 만든 작업이 뒤로 밀려, 옮긴 뒤의 티켓 번호가 소스와 다른 차례로 붙는다.
    assert parsed["notion_ticket_number"] == 142
    assert parsed["status"] == "진행"
    assert parsed["priority"] == "높음"
    assert parsed["difficulty"] == "3"
    assert parsed["est_wd"] == 2.5
    assert parsed["act_wd"] == 3
    assert parsed["category"] == "인증"
    assert parsed["assignee_notion_ids"] == ["user-1"]
    assert parsed["project_ids"] == ["project-page-1"]
    assert parsed["parent_page_id"] == "parent-page-1"


def test_dates_arrive_as_dates_not_strings():
    """문자열을 그대로 넘기면 적재가 500 을 낸다 (D-248)."""
    parsed = transform.parse_task(TASK_ROW)
    assert parsed["start_date"] == date(2026, 8, 1)
    assert parsed["due_date"] == date(2026, 8, 15)
    assert parsed["notion_created_time"] == datetime(2026, 1, 2, 3, 4, 5)
    assert parsed["notion_last_edited"] == datetime(2026, 8, 20, 10, 11, 12)


def test_a_second_parent_is_dropped_but_counted():
    row = {**TASK_ROW, "properties": {
        **TASK_ROW["properties"],
        "상위 작업": {"type": "relation", "relation": [{"id": "a"}, {"id": "b"}]},
    }}
    parsed = transform.parse_task(row)
    assert parsed["parent_page_id"] == "a"
    assert parsed["parent_count"] == 2, "몇 개였는지를 잃으면 「하나였다」와 구별이 안 된다"


def test_missing_properties_do_not_explode():
    parsed = transform.parse_task({"id": "x", "properties": {}})
    assert parsed["title"] == ""
    assert parsed["project_ids"] == []
    assert parsed["due_date"] is None


# ── 첨부 ─────────────────────────────────────────────────────────────────────


def test_attachments_are_found_in_every_files_property():
    """속성 이름을 고정하면 실측의 `첨부파일 `(끝 공백)을 놓친다."""
    row = {"id": "page-1", "properties": {
        "첨부파일 ": {"type": "files", "files": [
            {"name": "a.pdf", "file": {"url": "https://s3.example/a"}}]},
        "파일과 미디어": {"type": "files", "files": [
            {"name": "b.pdf", "file": {"url": "https://s3.example/b"}}]},
    }}
    found = transform.attachments_of(row)
    assert [item.name for item in found] == ["a.pdf", "b.pdf"]
    assert [item.legacy_id for item in found] == ["page-1:0", "page-1:1"]


def test_an_external_link_is_marked_not_downloaded():
    """바깥 링크는 바이트가 Notion 에 없다. 실패로 세면 「이관이 깨졌다」로 보인다."""
    found = transform.attachments_of(TASK_ROW)
    hosted = [item for item in found if item.hosted]
    external = [item for item in found if not item.hosted]
    assert [item.name for item in hosted] == ["ddl.sql"]
    assert [item.name for item in external] == ["설계"]


def test_attachment_ids_are_stable_across_runs():
    """임시 URL 은 매 조회마다 바뀐다 — 키로 쓰면 재실행마다 파일이 새로 생긴다."""
    first = transform.attachments_of(TASK_ROW)
    second = transform.attachments_of(TASK_ROW)
    assert [i.legacy_id for i in first] == [i.legacy_id for i in second]


# ── 본문 블록 → Block JSON (D-198) ───────────────────────────────────────────


def _block(btype: str, text: str = "", **extra) -> dict:
    return {"id": f"b-{btype}", "type": btype,
            btype: {"rich_text": [_rich(text)] if text else [], **extra}}


def _table_row(*cells: str) -> dict:
    """Notion `table_row` 하나. 셀은 rich_text 목록의 목록이다(실측 모양 그대로)."""
    return {"id": "b-row", "type": "table_row",
            "table_row": {"cells": [[_rich(cell)] if cell else [] for cell in cells]}}


def _image_block(block_id: str, url: str, caption: str) -> dict:
    return {"id": block_id, "type": "image",
            "image": {"caption": [_rich(caption)] if caption else [],
                      "type": "file", "file": {"url": url}}}


def _external_image_block(block_id: str, url: str) -> dict:
    return {"id": block_id, "type": "image",
            "image": {"caption": [], "type": "external", "external": {"url": url}}}


def test_headings_lists_code_and_dividers_all_survive():
    doc = transform.notion_blocks_to_doc([
        _block("heading_2", "배경"),
        _block("paragraph", "한 문단."),
        _block("bulleted_list_item", "첫째"),
        _block("bulleted_list_item", "둘째"),
        _block("code", "SELECT 1;", language="sql"),
        _block("divider"),
    ])
    kinds = [node["type"] for node in doc["content"]]
    assert kinds == [
        "heading", "paragraph", "bulletList", "codeBlock", "horizontalRule"
    ]
    assert doc["content"][0]["attrs"]["level"] == 2
    assert len(doc["content"][2]["content"]) == 2, "연속한 목록 항목은 한 목록이다"
    assert doc["content"][3]["attrs"]["language"] == "sql"


def test_the_result_passes_the_product_schema():
    """`blocks.normalize` 가 거절하면 문서 한 건이 통째로 안 들어간다."""
    doc = transform.notion_blocks_to_doc([
        _block("heading_1", "제목"),
        _block("numbered_list_item", "하나"),
        _block("quote", "인용"),
        _block("to_do", "할 일", checked=True),
        _block("toggle", "접힘"),
        _block("callout", "알림"),
    ])
    normalized = block_mod.normalize(doc)
    assert normalized["content"], "빈 본문이 나왔다"
    for node in normalized["content"]:
        assert node["type"] in block_mod.BLOCK_NODES


def test_an_unsupported_block_leaves_a_trace_instead_of_vanishing():
    """정말 못 옮기는 것은 **사람이 읽는 한 문장**으로 남는다 (S14).

    옛 회차는 `[원본에서 확인: child_database]` 를 넣었다. 그것은 두 가지를 한꺼번에
    틀린다: 내부 타입 이름을 사용자에게 보여 주고, 이미지·표처럼 **옮길 수 있는 것**까지
    글자로 바꿔 버렸다. 지금은 정말 못 옮기는 것만 여기 온다.
    """
    doc = transform.notion_blocks_to_doc([_block("child_database")])
    text = block_mod.to_text(block_mod.normalize(doc))
    assert "원본에서 확인" not in text, "내부 타입 이름이 사용자에게 보인다"
    assert "child_database" not in text
    assert text.strip() == "원본에만 있는 내용입니다."


def test_a_table_keeps_every_cell_and_marks_its_header():
    """표 셀의 글자가 남는가. 실측에서 이 자리가 31,310자를 통째로 잃던 곳이다."""
    table = _block("table", table_width=2, has_column_header=True, has_row_header=False)
    table["_children"] = [
        _table_row("항목", "값"),
        _table_row("메모리", "16GB"),
    ]
    doc = transform.notion_blocks_to_doc([table])
    assert [node["type"] for node in doc["content"]] == ["table"]
    rows = doc["content"][0]["content"]
    assert [cell["type"] for cell in rows[0]["content"]] == ["tableHeader", "tableHeader"]
    assert [cell["type"] for cell in rows[1]["content"]] == ["tableCell", "tableCell"]
    assert rows[0]["content"][0]["attrs"] == {
        "colspan": 1, "rowspan": 1, "colwidth": None,
    }
    text = block_mod.to_text(block_mod.normalize(doc))
    for word in ("항목", "값", "메모리", "16GB"):
        assert word in text, f"«{word}» 가 사라졌다"


def test_a_row_header_table_marks_the_first_column():
    table = _block("table", table_width=2, has_column_header=False, has_row_header=True)
    table["_children"] = [_table_row("이름", "값")]
    doc = transform.notion_blocks_to_doc([table])
    kinds = [cell["type"] for cell in doc["content"][0]["content"][0]["content"]]
    assert kinds == ["tableHeader", "tableCell"]


def test_an_empty_cell_still_holds_one_paragraph():
    """빈 셀에 문단이 없으면 ProseMirror 가 그 표를 통째로 버린다 (D3)."""
    table = _block("table", table_width=2, has_column_header=False, has_row_header=False)
    table["_children"] = [_table_row("있음", "")]
    doc = transform.notion_blocks_to_doc([table])
    empty = doc["content"][0]["content"][0]["content"][1]
    assert empty["content"] == [{"type": "paragraph"}]
    block_mod.normalize(doc)


def test_an_image_becomes_a_node_pointing_at_our_endpoint():
    """이미지는 노드가 되고 `src` 는 **우리 주소**다 (D3 · D4)."""
    block = _image_block("b-img", "https://prod-files-secure.s3.example/x.png", "설계도")
    doc = transform.notion_blocks_to_doc(
        [block], media_urls={"b-img": "/api/knowledge/attachments/att-1/content"}
    )
    assert doc["content"][0] == {
        "type": "image",
        "attrs": {
            "src": "/api/knowledge/attachments/att-1/content",
            "alt": "설계도", "title": None,
        },
    }
    block_mod.normalize(doc)


def test_an_image_never_carries_the_notion_signed_url():
    """서명 주소는 한 시간이면 죽는다. 남기면 화면에 깨진 그림만 남는다 (D4)."""
    signed = "https://prod-files-secure.s3.us-west-2.amazonaws.com/x.png?X-Amz-Expires=3600"
    doc = transform.notion_blocks_to_doc([_image_block("b-img", signed, "")])
    assert "prod-files-secure" not in json.dumps(doc, ensure_ascii=False)
    text = block_mod.to_text(block_mod.normalize(doc))
    assert text.strip() == "원본에만 있는 이미지입니다."


def test_a_lost_image_keeps_its_caption():
    doc = transform.notion_blocks_to_doc([_image_block("b-img", "https://x/y.png", "회로도")])
    text = block_mod.to_text(block_mod.normalize(doc))
    assert "회로도" in text


def test_a_file_block_becomes_a_readable_link():
    block = {
        "id": "b-file", "type": "file",
        "file": {"caption": [], "name": "규격서.pdf",
                 "file": {"url": "https://prod-files-secure.s3.example/spec.pdf"}},
    }
    doc = transform.notion_blocks_to_doc(
        [block], media_urls={"b-file": "/api/knowledge/attachments/att-2/content"}
    )
    node = doc["content"][0]
    assert node["type"] == "paragraph"
    assert node["content"][0]["text"] == "규격서.pdf"
    assert node["content"][0]["marks"] == [
        {"type": "link", "attrs": {"href": "/api/knowledge/attachments/att-2/content"}}
    ]


def test_heading_four_keeps_its_own_level():
    """`heading_4` 를 3 으로 낮추면 바로 위 제목과 같은 층이 된다 — 위계가 사라진다."""
    doc = transform.notion_blocks_to_doc([_block("heading_4", "전환 절차")])
    assert doc["content"][0]["type"] == "heading"
    assert doc["content"][0]["attrs"]["level"] == 4
    assert "전환 절차" in block_mod.to_text(block_mod.normalize(doc))


def test_structural_blocks_leave_no_placeholder():
    """컬럼과 동기화 블록은 **자기 글자가 없다.** 자리표시자는 군더더기다."""
    column = _block("column")
    column["_children"] = [_block("paragraph", "왼쪽 글")]
    wrapper = _block("column_list")
    wrapper["_children"] = [column]
    doc = transform.notion_blocks_to_doc([wrapper])
    assert [node["type"] for node in doc["content"]] == ["paragraph"]
    assert block_mod.to_text(block_mod.normalize(doc)).strip() == "왼쪽 글"


def test_media_is_collected_from_nested_blocks():
    """실측에서 이미지는 토글과 컬럼 안에 들어 있다. 최상위만 보면 조용히 빠진다."""
    inner = _image_block("b-inner", "https://x/a.png", "")
    toggle = _block("toggle", "접힘")
    toggle["_children"] = [inner]
    found = transform.media_of("page-1", [toggle, _image_block("b-top", "https://x/b.png", "")])
    assert [item.block_id for item in found] == ["b-inner", "b-top"]
    assert [item.legacy_id for item in found] == ["block:b-inner", "block:b-top"]
    assert [item.name for item in found] == ["a.png", "b.png"]


def test_a_data_uri_external_image_is_treated_as_ours_to_move():
    """🔴 「외부」인데 실제로는 이미지가 그 자리에 그대로 박혀 있는 경우다 (data: URI).

    실측: 1,235쪽 중 1건. 진짜 외부 링크가 아니라 내려받을 곳이 없는 바이트라, 링크
    문단으로 그대로 남기면(`hosted=False` 취급) 그 data: 문자열이 본문에 남고
    `blocks.py` 가 허용하지 않는 스킴이라 **문서 전체**를 거절한다. 그래서 `hosted=True`
    로 다뤄야 `_body_media` 가 우리 저장소로 옮기는 갈래를 탄다.
    """
    url = "data:image/png;base64,iVBORw0KGgo="
    found = transform.media_of("page-1", [_external_image_block("b-data", url)])
    assert len(found) == 1
    assert found[0].hosted is True, "data URI 를 진짜 외부 링크로 잘못 분류했다"
    assert found[0].url == url


def test_a_real_external_link_is_left_as_a_link_not_moved():
    """오탐 방지 — 진짜 http(s) 외부 링크는 여전히 hosted=False 다.

    위 시험이 조건 없이 hosted=True 로 만들면 이 시험이 잡는다. 진짜 외부 이미지는
    바이트가 우리 것이 아니므로 링크 문단으로 남아야 한다(D4).
    """
    found = transform.media_of(
        "page-1", [_external_image_block("b-ext", "https://example.com/a.png")]
    )
    assert found[0].hosted is False


def test_media_bytes_decodes_a_data_uri_without_reaching_the_network():
    """`data:` URI 는 `fetch` 를 안 부르고 그 자리에서 디코드한다.

    `OutboundClient` 는 http/https 만 받는다 — data: URI 를 그대로 넘기면 허용 목록에서
    거절된다. 그래서 fetch 콜백을 아예 안 태우는지를 직접 확인한다.
    """
    import base64

    payload = b"\x89PNG\r\n\x1a\n"
    url = "data:image/png;base64," + base64.b64encode(payload).decode()

    def _boom(_url):
        raise AssertionError("data: URI 인데 네트워크로 나갔다")

    assert transform.media_bytes(url, _boom) == payload


def test_media_bytes_still_uses_fetch_for_real_urls():
    """오탐 방지 — data: 가 아니면 여전히 `fetch` 를 부른다."""
    calls = []

    def _fetch(url):
        calls.append(url)
        return b"bytes"

    assert transform.media_bytes("https://example.com/a.png", _fetch) == b"bytes"
    assert calls == ["https://example.com/a.png"]


def test_media_bytes_rejects_a_malformed_data_uri():
    """깨진 base64 를 조용히 삼키지 않는다 — 사람이 읽을 사유가 있어야 한다."""
    with pytest.raises(NotionSourceError):
        transform.media_bytes("data:image/png;base64,not-valid-base64!!!", lambda u: b"")


def test_media_ids_are_stable_across_runs():
    """서명 URL 은 매 조회마다 바뀐다 — 키로 쓰면 재실행이 같은 이미지를 또 받는다."""
    block = _image_block("b-img", "https://x/a.png?X-Amz-Date=1", "")
    again = _image_block("b-img", "https://x/a.png?X-Amz-Date=2", "")
    assert (transform.media_of("p", [block])[0].legacy_id
            == transform.media_of("p", [again])[0].legacy_id)


def test_nested_list_items_keep_their_children():
    parent = _block("bulleted_list_item", "부모")
    parent["has_children"] = True
    parent["_children"] = [_block("bulleted_list_item", "자식")]
    doc = block_mod.normalize(transform.notion_blocks_to_doc([parent]))
    rendered = block_mod.to_text(doc)
    assert "부모" in rendered and "자식" in rendered


def test_marks_and_links_survive():
    seg = _rich("굵게", bold=True)
    link = {"plain_text": "링크", "text": {"content": "링크"},
            "annotations": {"bold": False, "italic": False, "strikethrough": False,
                            "code": False},
            "href": "https://example.com/a"}
    doc = transform.notion_blocks_to_doc([
        {"id": "b", "type": "paragraph", "paragraph": {"rich_text": [seg, link]}}
    ])
    markdown = block_mod.to_markdown(block_mod.normalize(doc))
    assert "**굵게**" in markdown
    assert "https://example.com/a" in markdown


def test_an_empty_paragraph_does_not_become_an_empty_block():
    doc = transform.notion_blocks_to_doc([_block("paragraph"), _block("paragraph", "글")])
    assert len(doc["content"]) == 1


# ── Migration Exception 분류 (U11 · D-197) ───────────────────────────────────


def test_a_resolved_single_relation_gets_a_number():
    verdict = transform.classify_ticket_exception(
        project_ids=["p1"], resolved_project_id="uuid-1", notion_missing=False
    )
    assert not verdict.excepted


@pytest.mark.parametrize(
    "ids,resolved,missing,reason",
    [
        (["p1", "p2"], None, False, work_models.EXC_AMBIGUOUS),
        ([], None, False, work_models.EXC_MISSING),
        (["p1"], None, False, work_models.EXC_UNRESOLVED),
        (["p1"], "uuid-1", True, work_models.EXC_SOURCE_MISSING),
    ],
)
def test_every_reason_has_its_own_shape(ids, resolved, missing, reason):
    verdict = transform.classify_ticket_exception(
        project_ids=ids, resolved_project_id=resolved, notion_missing=missing
    )
    assert verdict.reason == reason
    assert verdict.excepted


def test_source_missing_wins_over_the_relation_question():
    """이미 없는 것의 프로젝트 관계를 따지는 것은 판정이 아니라 추측이다."""
    verdict = transform.classify_ticket_exception(
        project_ids=["p1", "p2"], resolved_project_id=None, notion_missing=True
    )
    assert verdict.reason == work_models.EXC_SOURCE_MISSING


# ── 재채번 (D-196) ───────────────────────────────────────────────────────────


def test_numbers_follow_the_old_ticket_number():
    assigned = transform.assign_sequences(
        existing={},
        candidates=[("c", 300, "c"), ("a", 100, "a"), ("b", 200, "b")],
    )
    assert assigned == {"a": 1, "b": 2, "c": 3}


def test_a_ticket_that_already_has_a_number_keeps_it():
    """`canonical_key` 는 외부 식별자다. 움직이면 어제 공유한 링크가 다른 티켓을 연다."""
    assigned = transform.assign_sequences(
        existing={"a": 7}, candidates=[("a", 100, "a"), ("b", 50, "b")]
    )
    assert assigned["a"] == 7
    assert assigned["b"] == 8, "새 티켓은 뒤에 붙는다 — 앞에 끼우면 기존 번호가 밀린다"


def test_rerunning_gives_the_same_numbers():
    candidates = [("a", 100, "a"), ("b", 200, "b"), ("c", None, "c")]
    first = transform.assign_sequences(existing={}, candidates=candidates)
    second = transform.assign_sequences(existing=first, candidates=candidates)
    assert first == second


def test_tickets_without_an_old_number_go_last():
    assigned = transform.assign_sequences(
        existing={}, candidates=[("z", None, "z"), ("a", 500, "a")]
    )
    assert assigned == {"a": 1, "z": 2}


# ── 공간 주소 ────────────────────────────────────────────────────────────────


def test_space_slug_is_deterministic_and_url_safe():
    first = transform.space_slug(owner_kind="department", owner_id="ab-12")
    second = transform.space_slug(owner_kind="department", owner_id="ab-12")
    assert first == second
    assert first.replace("-", "").isalnum()
    assert len(first) <= 64
