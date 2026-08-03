"""마크다운 ↔ Notion 블록 어댑터 (app/core/notion_blocks.py).

본문 정본을 우리 DB(마크다운)에 두려면 지금 Notion 에 있는 본문을 한 번은 마크다운으로 되읽어야
한다. 그래서 필요한 성질은 하나다: **우리가 만든 블록은 손실 없이 되돌아온다.** 왕복이 깨지면
본문 이관 때 문서가 조용히 뭉개진다.
"""

from __future__ import annotations

import pytest

from app.core.notion_blocks import (
    blocks_to_markdown,
    markdown_to_blocks,
    rendered_to_markdown,
)

pytestmark = pytest.mark.unit

# markdown_to_blocks 가 인식하는 문법 전부 + 빈 줄(간격).
SOURCE = "\n".join([
    "# 제목 1",
    "## 제목 2",
    "### 제목 3",
    "본문 문단입니다.",
    "",
    "- 글머리 하나",
    "- 글머리 둘",
    "1. 번호 하나",
    "2. 번호 둘",
    "---",
    "마지막 문단 🙂",
])


def test_markdown_survives_a_round_trip():
    assert blocks_to_markdown(markdown_to_blocks(SOURCE)) == SOURCE


def test_numbering_restarts_after_a_non_list_block():
    md = "1. 하나\n2. 둘\n문단\n1. 다시 하나"
    assert blocks_to_markdown(markdown_to_blocks(md)) == md


def test_reads_notion_response_shape_not_just_our_own():
    """Notion 응답은 plain_text 에, 우리가 만든 블록은 text.content 에 글자를 담는다."""
    blocks = [
        {"object": "block", "type": "heading_2",
         "heading_2": {"rich_text": [{"type": "text", "plain_text": "배경"}]}},
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "plain_text": "본문 한 줄."}]}},
        {"object": "block", "type": "to_do",
         "to_do": {"rich_text": [{"type": "text", "plain_text": "할 일"}], "checked": True}},
        {"object": "block", "type": "quote",
         "quote": {"rich_text": [{"type": "text", "plain_text": "인용"}]}},
        {"object": "block", "type": "divider", "divider": {}},
    ]
    assert blocks_to_markdown(blocks) == "## 배경\n본문 한 줄.\n- [x] 할 일\n> 인용\n---"


def test_unrepresentable_blocks_are_skipped_not_mangled():
    """이미지·임베드는 마크다운으로 못 옮긴다 — 자리표시 쓰레기를 남기느니 건너뛴다."""
    blocks = [
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "plain_text": "앞"}]}},
        {"object": "block", "type": "image", "image": {}},
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "plain_text": "뒤"}]}},
    ]
    assert blocks_to_markdown(blocks) == "앞\n뒤"


def test_empty_input_is_empty_output():
    assert blocks_to_markdown([]) == ""
    assert blocks_to_markdown(None) == ""


# ── 렌더용 축약형 → 마크다운 ────────────────────────────────────────────────
# 티켓 상세 API 가 화면에 주는 본문은 원본 블록이 아니라 [{kind, text, checked?}] 다. 본문
# 편집기를 그 값으로 여는데, 두 변환기가 조금이라도 다르면 "열었다가 그대로 저장"만 해도
# 본문이 바뀐다. 그래서 같은 입력에 대해 두 함수가 **같은 결과**를 내는지 나란히 고정한다.

def _rendered(blocks):
    """원본 블록을 fetch_page_blocks 가 내는 축약형으로 바꾼다(같은 매핑)."""
    kinds = {"bulleted_list_item": "bulleted", "numbered_list_item": "numbered",
             "to_do": "todo"}
    out = []
    for b in blocks:
        btype = b["type"]
        container = b.get(btype) or {}
        item = {"kind": kinds.get(btype, btype),
                "text": "".join(s.get("plain_text") or s.get("text", {}).get("content", "")
                                for s in (container.get("rich_text") or []))}
        if btype == "to_do":
            item["checked"] = bool(container.get("checked"))
        out.append(item)
    return out


def test_rendered_form_produces_the_same_markdown_as_the_raw_blocks():
    blocks = markdown_to_blocks(SOURCE)
    assert rendered_to_markdown(_rendered(blocks)) == blocks_to_markdown(blocks) == SOURCE


def test_rendered_numbering_restarts_after_a_non_list_block():
    md = "1. 하나\n2. 둘\n문단\n1. 다시 하나"
    assert rendered_to_markdown(_rendered(markdown_to_blocks(md))) == md


def test_rendered_todo_and_divider():
    items = [
        {"kind": "heading_2", "text": "배경"},
        {"kind": "paragraph", "text": "본문 한 줄."},
        {"kind": "todo", "text": "할 일", "checked": True},
        {"kind": "todo", "text": "안 한 일", "checked": False},
        {"kind": "quote", "text": "인용"},
        {"kind": "divider", "text": ""},
    ]
    assert rendered_to_markdown(items) == (
        "## 배경\n본문 한 줄.\n- [x] 할 일\n- [ ] 안 한 일\n> 인용\n---"
    )


def test_unsupported_placeholder_never_becomes_text():
    """'[image] 원본에서 확인' 을 글자로 남기면 저장할 때 그 문구가 진짜 본문이 된다."""
    items = [
        {"kind": "paragraph", "text": "앞"},
        {"kind": "unsupported", "text": "[image] 원본에서 확인"},
        {"kind": "paragraph", "text": "뒤"},
    ]
    assert rendered_to_markdown(items) == "앞\n뒤"


def test_rendered_empty_input_is_empty_output():
    assert rendered_to_markdown([]) == ""
    assert rendered_to_markdown(None) == ""
