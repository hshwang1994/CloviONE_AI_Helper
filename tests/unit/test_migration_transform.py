"""소스의 모양이 우리 도메인의 모양으로 **정확히** 바뀌는가 (S13).

qa-contract-change: 옛 정책은 소스 `티켓 ID` 의 접두사(`GIT`)를 이름의 근거로 삼아 파서가 `legacy_prefix` 를 함께 돌려줬고 이 파일이 그 값을 못박고 있었다. 지금은 프로젝트 코드를 서버가 짓고 접두사는 이름의 근거가 아니므로(D-282) 파서가 그 키를 더 내지 않는다 — 없는 키를 재는 단언은 성립하지 않아 지웠고, 같은 속성의 `number` 는 재번호 순서로 여전히 쓰이므로 그 단언은 그대로 남겼다.

여기 있는 표본은 전부 실제 Notion 응답의 모양이다. 파서를 응답 없이 시험하면
「우리가 상상한 응답」만 확인하게 된다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.knowledge import blocks as block_mod
from app.migration import transform
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
    """표·이미지를 지우면 **그 자리가 있었다는 사실**까지 사라진다."""
    doc = transform.notion_blocks_to_doc([_block("table"), _block("image")])
    text = block_mod.to_text(block_mod.normalize(doc))
    assert "원본에서 확인" in text
    assert "table" in text and "image" in text


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
