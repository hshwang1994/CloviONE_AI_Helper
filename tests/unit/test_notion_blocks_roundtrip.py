"""마크다운 ↔ Notion 블록 어댑터 (app/core/notion_blocks.py).

본문 정본을 우리 DB(마크다운)에 두려면 지금 Notion 에 있는 본문을 한 번은 마크다운으로 되읽어야
한다. 그래서 필요한 성질은 하나다: **우리가 만든 블록은 손실 없이 되돌아온다.** 왕복이 깨지면
본문 이관 때 문서가 조용히 뭉개진다.
"""

from __future__ import annotations

import pytest

from app.core.notion_blocks import blocks_to_markdown, markdown_to_blocks

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
