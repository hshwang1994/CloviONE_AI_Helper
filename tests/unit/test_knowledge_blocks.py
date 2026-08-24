"""Block JSON 정본과 그 파생 (S7 · D-198).

## 여기서 확인하는 것 넷

1. **정본에서 파생 셋이 함께 나온다** — `derive()` 하나가 body·markdown·text 를 만든다.
2. **블록 id 는 안 바뀐다** — 그것이 「안정적 앵커」의 뜻이고, 인용이 그 값을 가리킨다.
3. **거절하는 것은 길이가 아니라 모양이다** — 옛 100줄·1900자 상한은 사라졌고(D-198),
   대신 모르는 노드·위험한 링크·과도한 중첩이 막힌다.
4. **diff 는 블록 단위다** — 줄바꿈만 바뀐 판이 전면 수정으로 보이면 안 된다.

각 단정에 **반대편**을 함께 둔다. 「거절한다」만 확인하면 전부 거절하는 구현도 통과하고,
그 구현에서는 아무도 글을 저장할 수 없다.
"""

from __future__ import annotations

import pytest

from app.knowledge import blocks

pytestmark = pytest.mark.unit


def _p(text, block_id=None, marks=None):
    node = {"type": "paragraph", "content": [{"type": "text", "text": text}]}
    if marks:
        node["content"][0]["marks"] = marks
    if block_id:
        node["attrs"] = {blocks.BLOCK_ID_ATTR: block_id}
    return node


def _doc(*nodes):
    return {"type": "doc", "content": list(nodes)}


# ── 파생 셋이 함께 나온다 ────────────────────────────────────────────────────


def test_derive_makes_body_markdown_and_text_from_one_canonical():
    derived = blocks.derive(_doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "회의록"}]},
        _p("본문 한 줄"),
    ))
    assert derived.markdown == "## 회의록\n\n본문 한 줄"
    assert derived.text == "회의록\n본문 한 줄"
    assert derived.body["content"][0]["type"] == "heading"


def test_markdown_keeps_nested_list_structure():
    """목록은 파생에서 가장 자주 깨지는 자리다 — 들여쓰기를 잃으면 평면 목록이 된다."""
    doc = _doc({
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [
                _p("바깥"),
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [_p("안쪽")]},
                ]},
            ]},
        ],
    })
    assert blocks.derive(doc).markdown == "- 바깥\n\n  - 안쪽"


def test_plain_text_drops_formatting_so_the_same_sentence_embeds_the_same():
    derived = blocks.derive(_doc(_p("굵게", marks=[{"type": "bold"}])))
    assert derived.markdown == "**굵게**"
    assert derived.text == "굵게"


# ── 블록 id 는 안정적 앵커다 ─────────────────────────────────────────────────


def test_existing_block_ids_survive_a_second_normalize():
    first = blocks.normalize(_doc(_p("가"), _p("나")))
    ids = blocks.block_ids(first)
    assert len(set(ids)) == 2

    # 두 번째 문단만 고쳐 다시 정규화한다 — 첫 문단의 앵커는 그대로여야 한다.
    edited = {"type": "doc", "content": [first["content"][0], dict(first["content"][1])]}
    edited["content"][1]["content"] = [{"type": "text", "text": "나 고침"}]
    again = blocks.block_ids(blocks.normalize(edited))
    assert again[0] == ids[0], "안 건드린 문단의 앵커가 바뀌었다 — 인용이 전부 끊긴다"
    assert again[1] == ids[1]


def test_duplicate_block_ids_get_a_fresh_one():
    """복사·붙여넣기가 만드는 흔한 상태다. 그대로 두면 인용 하나가 두 문단을 가리킨다."""
    ids = blocks.block_ids(blocks.normalize(_doc(_p("가", "same"), _p("나", "same"))))
    assert len(set(ids)) == 2, f"중복 앵커가 그대로 남았다: {ids}"
    assert "same" in ids, "먼저 나온 쪽은 자기 앵커를 지켜야 한다"


# ── 거절하는 것은 길이가 아니라 모양이다 ────────────────────────────────────


def test_a_very_long_document_is_accepted():
    """옛 코드는 100줄에서 저장을 거절했다. 그 수는 Notion API 상한이지 제품 규칙이
    아니었다 — 회의록 하나가 그 줄 수를 넘으면 저장이 안 됐다 (D-198)."""
    derived = blocks.derive(_doc(*[_p(f"{i}번째 줄") for i in range(500)]))
    assert len(derived.body["content"]) == 500
    assert derived.text.count("\n") == 499


def test_a_very_long_line_is_accepted():
    long_line = "가" * 5000
    assert blocks.derive(_doc(_p(long_line))).text == long_line


def test_an_unknown_node_type_is_rejected():
    """통과시키면 편집기가 못 그리는 값이 DB 에 들어가고, 그 문서는 매번 빈 화면이 된다."""
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "iframe", "attrs": {"src": "http://x"}}))


def test_a_list_item_cannot_sit_at_the_top_level():
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "listItem", "content": [_p("가")]}))


def test_deep_nesting_is_rejected_but_ordinary_nesting_is_not():
    def nest(depth):
        node = _p("바닥")
        for _ in range(depth):
            node = {"type": "blockquote", "content": [node]}
        return node

    blocks.normalize(_doc(nest(5)))  # 평범한 중첩은 통과한다
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc(nest(blocks.MAX_DEPTH + 2)))


@pytest.mark.parametrize("href", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "java\tscript:alert(1)",
    " javascript:alert(1) ",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
])
def test_dangerous_link_schemes_lose_the_mark_but_keep_the_words(href):
    """마크만 뗀다 — 저장을 거절하면 사용자가 방금 쓴 문단을 통째로 잃는다."""
    body = blocks.normalize(_doc(_p("눌러", marks=[{"type": "link", "attrs": {"href": href}}])))
    node = body["content"][0]["content"][0]
    assert node["text"] == "눌러", "글자까지 사라졌다"
    assert "marks" not in node, f"위험한 링크가 살아남았다: {href}"


@pytest.mark.parametrize("href", [
    "https://example.test/a",
    "http://example.test",
    "mailto:someone@example.test",
    "/knowledge/documents/abc",
    "#anchor",
])
def test_ordinary_links_survive(href):
    """반대편 — 여기서 실패하면 위 시험은 「전부 막는 구현」도 통과시킨다."""
    body = blocks.normalize(_doc(_p("눌러", marks=[{"type": "link", "attrs": {"href": href}}])))
    marks = body["content"][0]["content"][0].get("marks") or []
    assert [m["type"] for m in marks] == ["link"], f"정상 링크가 사라졌다: {href}"


# ── 멘션 ─────────────────────────────────────────────────────────────────────


def test_mentions_come_out_with_the_block_they_sit_in():
    """블록 id 가 함께 나와야 알림이 그 자리로 이동할 수 있다."""
    body = blocks.normalize(_doc(
        _p("첫 줄"),
        {"type": "paragraph", "content": [
            {"type": "text", "text": "확인 부탁 "},
            {"type": "mention", "attrs": {"kind": "user", "id": "u-1", "label": "황형섭"}},
        ]},
    ))
    found = blocks.extract_mentions(body)
    assert len(found) == 1
    block_id, kind, target = found[0]
    assert (kind, target) == ("user", "u-1")
    assert block_id == blocks.block_ids(body)[1], "멘션이 엉뚱한 블록에 붙었다"


def test_the_same_mention_twice_in_one_block_is_one_row():
    body = blocks.normalize(_doc({"type": "paragraph", "content": [
        {"type": "mention", "attrs": {"kind": "user", "id": "u-1", "label": "가"}},
        {"type": "text", "text": " 그리고 "},
        {"type": "mention", "attrs": {"kind": "user", "id": "u-1", "label": "가"}},
    ]}))
    assert len(blocks.extract_mentions(body)) == 1


def test_an_unknown_mention_kind_is_rejected():
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "paragraph", "content": [
            {"type": "mention", "attrs": {"kind": "server", "id": "10.0.0.1"}},
        ]}))


# ── diff 는 블록 단위다 ──────────────────────────────────────────────────────


def test_identical_documents_have_no_changes():
    doc = blocks.normalize(_doc(_p("가"), _p("나")))
    assert blocks.diff(doc, doc) == []


def test_editing_one_paragraph_reports_one_change_not_a_rewrite():
    old = blocks.normalize(_doc(_p("가"), _p("나"), _p("다")))
    new = {"type": "doc", "content": [
        old["content"][0],
        {**old["content"][1], "content": [{"type": "text", "text": "나 고침"}]},
        old["content"][2],
    ]}
    changes = blocks.diff(old, blocks.normalize(new))
    assert [c["change"] for c in changes] == [blocks.CHANGE_CHANGED]
    assert changes[0]["before"] == "나"
    assert changes[0]["after"] == "나 고침"


def test_reordering_paragraphs_is_a_move_not_delete_plus_insert():
    """순서만 바꾼 판을 「전부 지우고 전부 새로 씀」으로 보여 주면 사람이 그 화면에서
    실제 변경을 못 찾는다."""
    old = blocks.normalize(_doc(_p("가"), _p("나"), _p("다")))
    new = {"type": "doc", "content": [old["content"][2], old["content"][0], old["content"][1]]}
    changes = blocks.diff(old, blocks.normalize(new))
    assert [c["change"] for c in changes] == [blocks.CHANGE_MOVED]
    assert changes[0]["after"] == "다"


def test_added_and_removed_blocks_are_reported_in_place():
    old = blocks.normalize(_doc(_p("가"), _p("나"), _p("다")))
    new = {"type": "doc", "content": [old["content"][0], _p("새 문단"), old["content"][2]]}
    changes = blocks.diff(old, blocks.normalize(new))
    kinds = [(c["change"], c["before"] or c["after"]) for c in changes]
    assert (blocks.CHANGE_ADDED, "새 문단") in kinds
    assert (blocks.CHANGE_REMOVED, "나") in kinds


def test_splitting_a_paragraph_does_not_look_like_a_full_rewrite():
    """줄 단위 비교라면 「한 줄 삭제 + 두 줄 추가」로 보인다. 블록 id 가 그것을 구별한다."""
    old = blocks.normalize(_doc(_p("가나다")))
    kept = old["content"][0]
    new = blocks.normalize({"type": "doc", "content": [
        {**kept, "content": [{"type": "text", "text": "가"}]},
        _p("나다"),
    ]})
    changes = blocks.diff(old, new)
    assert sorted(c["change"] for c in changes) == [blocks.CHANGE_ADDED, blocks.CHANGE_CHANGED]


# ── id 를 안 돌려주는 클라이언트 (carry_from) ───────────────────────────────


def test_a_client_that_drops_ids_keeps_the_anchors_by_position():
    """앵커의 주인은 편집기다. 그러지 않는 부르는 쪽(도구 · S13 마이그레이션)을 위해
    **앞판의 같은 자리 앵커를 물려준다** — 없으면 내용이 같은 재실행이 판을 계속 쌓는다."""
    old = blocks.normalize(_doc(_p("가"), _p("나")))
    again = blocks.normalize(_doc(_p("가"), _p("나")), carry_from=old)
    assert blocks.block_ids(again) == blocks.block_ids(old)
    assert again == old, "내용이 같은 재실행이 다른 본문을 만들었다"


def test_carry_over_makes_a_one_paragraph_edit_look_like_an_edit():
    old = blocks.normalize(_doc(_p("가"), _p("나")))
    new = blocks.normalize(_doc(_p("가"), _p("나 고침")), carry_from=old)
    changes = blocks.diff(old, new)
    assert [c["change"] for c in changes] == [blocks.CHANGE_CHANGED]


def test_carry_over_never_hands_out_an_id_the_incoming_document_already_uses():
    """물려준 앵커가 들어온 본문의 다른 블록과 겹치면 인용 하나가 두 문단을 가리킨다."""
    old = blocks.normalize(_doc(_p("가"), _p("나")))
    first_id = blocks.block_ids(old)[0]
    # 두 번째 블록이 첫 블록의 앵커를 명시로 들고 왔다 — 자리 물려주기가 그것과 겹친다.
    new = blocks.normalize(_doc(_p("가"), _p("나", first_id)), carry_from=old)
    ids = blocks.block_ids(new)
    assert len(set(ids)) == 2, f"중복 앵커가 생겼다: {ids}"
    assert ids[1] == first_id, "명시로 들고 온 앵커가 밀려났다"


def test_an_explicit_id_always_beats_the_carried_one():
    old = blocks.normalize(_doc(_p("가"), _p("나")))
    new = blocks.normalize(_doc(_p("가", "mine"), _p("나")), carry_from=old)
    assert blocks.block_ids(new)[0] == "mine"


# ── 이미지와 표 (S14) ────────────────────────────────────────────────────────
#
# 스키마에 자리가 없던 동안 이관은 원본의 이미지와 표를 `[원본에서 확인: image]` 같은
# **글자**로 바꿔 넣었고, 표 셀의 31,310자는 어디에도 남지 않았다. 여기서 확인하는 것은
# 셋이다: 그 두 종류가 정본에 들어온다 · 자리가 틀리면 거절한다 · **셀 글자가 파생 평문에
# 전부 남는다**(그것이 검색과 임베딩에 닿는 유일한 길이다).


def _cell(text, kind="tableCell", **attrs):
    """표 칸 하나. attrs 는 D3 계약 그대로 `colspan`·`rowspan`·`colwidth` 다."""
    node = {
        "type": kind,
        "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None, **attrs},
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    if not text:
        # 빈 칸은 빈 문단 하나를 갖는다(D3).
        node["content"] = [{"type": "paragraph"}]
    return node


def _row(*cells):
    return {"type": "tableRow", "content": list(cells)}


def _table(*rows):
    return {"type": "table", "content": list(rows)}


def _image(src, alt="", title=None):
    return {"type": "image", "attrs": {"src": src, "alt": alt, "title": title}}


def test_an_image_survives_from_notion_shape_to_markdown_and_text():
    """이관이 만드는 모양(D3) 그대로 넣어 파생 셋을 함께 확인한다."""
    derived = blocks.derive(_doc(_image("/api/attachments/abc.png", alt="구성도")))
    node = derived.body["content"][0]
    assert node["type"] == "image"
    assert node["attrs"]["src"] == "/api/attachments/abc.png"
    assert node["attrs"]["alt"] == "구성도"
    assert node["attrs"][blocks.BLOCK_ID_ATTR], "이미지가 인용 앵커를 못 받았다"
    assert derived.markdown == "![구성도](/api/attachments/abc.png)"
    assert derived.text == "구성도"


def test_an_image_without_alt_leaves_no_empty_line_in_the_plain_text():
    """빈 줄은 검색에 아무것도 안 주면서 인용의 앞뒤 문맥만 벌린다."""
    derived = blocks.derive(_doc(_p("앞"), _image("/api/attachments/x.png"), _p("뒤")))
    assert derived.markdown == "앞\n\n![](/api/attachments/x.png)\n\n뒤"
    assert derived.text == "앞\n뒤"


@pytest.mark.parametrize("src", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "java\tscript:alert(1)",
    " javascript:alert(1) ",
    "data:image/svg+xml,<svg onload=alert(1)>",
    "vbscript:msgbox(1)",
    "mailto:someone@example.test",
])
def test_an_image_with_a_scheme_we_do_not_allow_is_rejected(src):
    """링크는 마크만 떼면 글자가 남지만 이미지는 `src` 가 전부라 뗄 것이 없다.
    `data:` 도 막는다 — `data:image/svg+xml` 은 그림처럼 보이지만 스크립트를 품는다."""
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc(_image(src)))


@pytest.mark.parametrize("src", [
    "https://example.test/a.png",
    "http://example.test/a.png",
    "/api/knowledge/attachments/abc",
])
def test_ordinary_image_sources_survive(src):
    """반대편 — 여기서 실패하면 위 시험은 「전부 막는 구현」도 통과시킨다."""
    body = blocks.normalize(_doc(_image(src)))
    assert body["content"][0]["attrs"]["src"] == src


def test_an_image_without_a_source_is_rejected():
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "image"}))
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc(_image("   ")))


def test_a_table_becomes_a_github_pipe_table():
    derived = blocks.derive(_doc(_table(
        _row(_cell("이름", "tableHeader"), _cell("값", "tableHeader")),
        _row(_cell("가"), _cell("나")),
    )))
    assert derived.markdown == "\n".join([
        "| 이름 | 값 |",
        "| --- | --- |",
        "| 가 | 나 |",
    ])
    table = derived.body["content"][0]
    assert table["type"] == "table"
    assert table["attrs"][blocks.BLOCK_ID_ATTR], "표가 인용 앵커를 못 받았다"


def test_every_character_in_every_cell_reaches_the_plain_text():
    """**글자 수로** 확인한다. 표 셀의 글자가 검색과 임베딩에 닿는 길은 이것 하나뿐이고,
    한 칸이라도 빠지면 그 문서는 「검색해도 안 나온다」로만 드러난다 — 아무도 신고하지 않는다."""
    cells = ["담당자", "마감일", "김철수", "2026-08-24", "박영희", "다음 주 화요일"]
    derived = blocks.derive(_doc(_table(
        _row(_cell(cells[0], "tableHeader"), _cell(cells[1], "tableHeader")),
        _row(_cell(cells[2]), _cell(cells[3])),
        _row(_cell(cells[4]), _cell(cells[5])),
    )))
    for text in cells:
        assert text in derived.text, f"셀 글자가 파생 평문에서 사라졌다: {text}"
    # 칸 사이 구분자(탭)와 줄 구분자(줄바꿈) 말고는 셀 글자가 전부다 — 한 글자도 안 빠지고
    # 한 글자도 안 늘었다.
    body = derived.text.replace("\t", "").replace("\n", "")
    assert len(body) == sum(len(t) for t in cells)


def test_cells_do_not_get_glued_into_one_word():
    """이어 붙이면 「가」와 「나」가 「가나」가 되어 어느 쪽으로 검색해도 안 나온다."""
    derived = blocks.derive(_doc(_table(_row(_cell("가"), _cell("나")))))
    assert "가나" not in derived.text
    assert derived.text == "가\t나"


def test_a_pipe_inside_a_cell_does_not_break_the_table():
    """escape 하지 않으면 칸 안의 글자 하나가 칸 경계가 되어 그 줄부터 표가 밀린다."""
    derived = blocks.derive(_doc(_table(_row(_cell("가|나"), _cell("다")))))
    assert derived.markdown.splitlines()[0] == r"| 가\|나 | 다 |"
    assert derived.text == "가|나\t다", "평문에는 escape 가 남으면 안 된다"


def test_a_short_row_is_padded_so_the_table_does_not_skew():
    """병합된 칸 때문에 줄마다 칸 수가 다를 수 있다. 짧은 줄을 그대로 두면 렌더러가
    표 전체를 어긋나게 그린다."""
    derived = blocks.derive(_doc(_table(
        _row(_cell("가"), _cell("나"), _cell("다")),
        _row(_cell("라", colspan=2)),
    )))
    rows = derived.markdown.splitlines()
    assert rows[1] == "| --- | --- | --- |"
    assert rows[-1] == "| 라 |  |  |"


def test_an_empty_cell_keeps_its_place_and_leaves_no_text():
    derived = blocks.derive(_doc(_table(_row(_cell("가"), _cell("")))))
    assert derived.markdown.splitlines()[0] == "| 가 |  |"
    assert derived.text == "가\t"


def test_a_table_and_an_image_sit_next_to_ordinary_blocks():
    """반대편 — 새 노드를 들이면서 옛 노드가 밀려나지 않는다."""
    derived = blocks.derive(_doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "표"}]},
        _table(_row(_cell("가"))),
        _image("/api/x.png", alt="그림"),
        _p("끝"),
    ))
    assert derived.text == "표\n가\n그림\n끝"
    assert [b["type"] for b in derived.body["content"]] == [
        "heading", "table", "image", "paragraph",
    ]


def test_table_text_is_indexed_per_block_too():
    """인용은 「이 문서 어딘가」가 아니라 「이 블록」을 가리켜야 한다(D-198)."""
    body = blocks.normalize(_doc(_p("앞"), _table(_row(_cell("가"), _cell("나")))))
    rows = list(blocks.iter_block_text(body))
    assert [kind for _, kind, _ in rows] == ["paragraph", "table"]
    assert rows[1][2] == "가\t나"


# ── 자리가 틀린 표 노드는 거절한다 ──────────────────────────────────────────
#
# 종류만 맞고 자리가 틀린 값은 ProseMirror 가 그 문서를 통째로 버린다 — 화면에는 오류가
# 아니라 **빈 본문**이 뜨고, DB 에는 멀쩡한 값이 들어 있어서 원인을 찾기 어렵다.


@pytest.mark.parametrize("bad", [
    {"type": "tableRow", "content": []},
    {"type": "tableCell", "content": [_p("가")]},
    {"type": "tableHeader", "content": [_p("가")]},
])
def test_table_parts_cannot_sit_at_the_top_level(bad):
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc(bad))


def test_a_cell_cannot_sit_directly_in_a_table():
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "table", "content": [_cell("가")]}))


def test_a_table_cannot_hold_a_paragraph_directly():
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "table", "content": [_p("가")]}))


def test_a_row_cannot_hold_another_row():
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc(_table(_row(_row(_cell("가"))))))


def test_a_list_item_cannot_sit_inside_a_quote():
    """같은 규칙이 옛 노드에도 걸린다 — 목록 항목의 부모는 목록뿐이다."""
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc({"type": "blockquote", "content": [
            {"type": "listItem", "content": [_p("가")]},
        ]}))


def test_a_cell_holds_blocks_so_a_list_inside_a_table_is_fine():
    """반대편 — 칸 안에는 블록이 온다(D3). 여기서 실패하면 위 거절들은 표를 통째로
    막는 구현도 통과시킨다."""
    derived = blocks.derive(_doc(_table(_row({
        "type": "tableCell",
        "attrs": {"colspan": 1, "rowspan": 1},
        "content": [{"type": "bulletList", "content": [
            {"type": "listItem", "content": [_p("하나")]},
            {"type": "listItem", "content": [_p("둘")]},
        ]}],
    }))))
    assert "하나" in derived.text and "둘" in derived.text
    assert derived.markdown.splitlines()[0] == "| - 하나 - 둘 |"


@pytest.mark.parametrize("attrs", [
    {"colspan": 0},
    {"rowspan": -1},
    {"colspan": "2"},
    {"colspan": True},
    {"colwidth": ["120"]},
    {"colwidth": 120},
])
def test_broken_cell_attributes_are_rejected(attrs):
    with pytest.raises(blocks.BlockError):
        blocks.normalize(_doc(_table(_row({
            "type": "tableCell", "attrs": attrs, "content": [_p("가")],
        }))))


def test_ordinary_cell_attributes_survive():
    """반대편 — 병합된 칸과 열 너비는 편집기가 실제로 보내는 값이다."""
    body = blocks.normalize(_doc(_table(_row({
        "type": "tableCell",
        "attrs": {"colspan": 2, "rowspan": 3, "colwidth": [120, 240]},
        "content": [_p("가")],
    }))))
    attrs = body["content"][0]["content"][0]["content"][0]["attrs"]
    assert (attrs["colspan"], attrs["rowspan"], attrs["colwidth"]) == (2, 3, [120, 240])
