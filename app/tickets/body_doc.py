"""티켓 본문의 정본을 **문서와 같은 것**으로 만든다.

## 왜 이 파일이 생겼나

티켓의 「설명」과 문서의 본문은 편집기가 다른 것이 아니라 **자료가 달랐다.** 문서는
ProseMirror 문서(Block JSON)를 정본으로 두고 마크다운·평문을 파생시키는데
(`app/knowledge/blocks.py`), 티켓은 마크다운 문자열이 정본이라 굵게·기울임·표·이미지를
담을 자리가 아예 없었다. 그래서 티켓 쪽 편집기는 아이콘 툴바를 달 수 없었다 —
단추를 두면 눌러서 쓴 것이 저장할 곳이 없어 **조용히 사라진다.**

이제 티켓도 같은 정본을 쓴다. `tickets.body_doc` 이 그 자리이고, 예전부터 있던
`tickets.body_markdown` 은 **파생값으로 남는다** — 검색·AI 문맥·목록 미리보기가 이미
그 칸을 읽고 있어서, 그것을 없애면 이번 변경과 상관없는 자리가 함께 깨진다.

## 옛 본문은 읽을 때 옮긴다

마이그레이션이 전량을 옮기지 않는다. 옛 행은 `body_doc` 이 비어 있고, 읽을 때
`doc_from_markdown` 을 지나 편집기가 아는 모양이 된다. 사용자가 한 번 저장하면 그
행의 정본이 doc 으로 바뀐다. 전량 백필을 안 하는 이유는 하나다 — 옮기는 코드가
틀렸을 때 되돌릴 수 있어야 하고, 원문이 `body_markdown` 에 그대로 남아 있어야 그것이 된다.

## 옛 마크다운이 표현할 수 있던 것만 옮긴다

`app/core/notion_blocks.py::markdown_to_blocks` 가 내는 여덟 종류가 전부다(문단·제목
1~3·글머리·번호·체크·인용·코드·구분선). 그 파서를 다시 쓰지 않고 **그대로 지난다** —
「`# ` 이 제목인가」를 두 곳에서 판단하면 한쪽만 고쳐진 날 미리보기와 저장 결과가 달라진다.
"""

from __future__ import annotations

from typing import Any

from app.core.notion_blocks import markdown_to_blocks
from app.knowledge import blocks as block_schema

#: 옛 블록 종류 → ProseMirror 노드. 목록에 없는 것은 **문단으로 눕힌다** — 사용자가 친
#: 글자는 어떤 경우에도 안 사라진다(그 파서는 목록 밖 종류를 만들지 않지만, 만드는 날이
#: 오면 여기서 조용히 버리는 것보다 문단으로 남는 편이 낫다).
_HEADING_LEVEL = {"heading_1": 1, "heading_2": 2, "heading_3": 3}
_LIST_OF = {"bulleted_list_item": "bulletList", "numbered_list_item": "orderedList"}


def _plain(block: dict) -> str:
    payload = block.get(block.get("type") or "") or {}
    return "".join(
        (item.get("text") or {}).get("content") or "" for item in payload.get("rich_text") or []
    )


def _text_content(text: str) -> list[dict[str, Any]]:
    """빈 문단에는 `content` 를 안 준다 — 빈 `text` 노드는 ProseMirror 가 거절한다."""
    return [{"type": "text", "text": text}] if text else []


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": _text_content(text)}


def doc_from_markdown(markdown: str | None) -> dict[str, Any]:
    """옛 마크다운 본문 → 편집기가 아는 문서. 빈 본문은 **빈 문서**다.

    빈 문자열을 파서에 넣으면 빈 문단 하나가 나오고(`"".split("\n")` 이 `[""]` 이라서),
    그러면 본문을 한 번도 안 쓴 티켓이 편집기에서 빈 줄 하나를 갖고 열린다.
    """
    if not (markdown or "").strip():
        return block_schema.empty_doc()

    content: list[dict[str, Any]] = []
    # 연달아 오는 글머리·번호·체크는 **한 목록**으로 묶는다. 한 줄에 목록 하나를 만들면
    # 편집기에서 항목마다 다른 목록이 되어 들여쓰기와 번호가 매 줄 처음부터 다시 센다.
    open_list: dict[str, Any] | None = None
    open_kind: str | None = None

    def _close():
        nonlocal open_list, open_kind
        if open_list is not None:
            content.append(open_list)
        open_list, open_kind = None, None

    for block in markdown_to_blocks(markdown):
        btype = block.get("type") or ""
        if btype == "divider":
            _close()
            content.append({"type": "horizontalRule"})
            continue
        text = _plain(block)
        # 빈 줄은 **문단이 아니라 구분자**다. 그 파서는 줄 하나를 블록 하나로 만들기
        # 때문에 문단 사이의 빈 줄이 빈 문단으로 남는데, 편집기에서 그것은 사용자가 친
        # 적 없는 빈 줄이 된다. 목록 사이의 빈 줄도 마찬가지로 목록을 끊지 않는다.
        if btype == "paragraph" and not text.strip():
            continue
        if btype in _LIST_OF:
            kind = _LIST_OF[btype]
            if open_kind != kind:
                _close()
                open_list, open_kind = {"type": kind, "content": []}, kind
            open_list["content"].append({"type": "listItem", "content": [_paragraph(text)]})
            continue
        if btype == "to_do":
            if open_kind != "taskList":
                _close()
                open_list, open_kind = {"type": "taskList", "content": []}, "taskList"
            checked = bool((block.get("to_do") or {}).get("checked"))
            open_list["content"].append(
                {"type": "taskItem", "attrs": {"checked": checked}, "content": [_paragraph(text)]}
            )
            continue
        _close()
        if btype in _HEADING_LEVEL:
            content.append({
                "type": "heading",
                "attrs": {"level": _HEADING_LEVEL[btype]},
                "content": _text_content(text),
            })
        elif btype == "quote":
            content.append({"type": "blockquote", "content": [_paragraph(text)]})
        elif btype == "code":
            content.append({
                "type": "codeBlock",
                "attrs": {"language": ""},
                "content": _text_content(text),
            })
        else:
            content.append(_paragraph(text))
    _close()
    return {"type": "doc", "content": content}


def derive(doc: Any, *, carry_from: Any = None) -> block_schema.Derived:
    """저장할 셋(문서 · 마크다운 · 평문)을 **함께** 만든다.

    문서와 **같은 함수**를 지난다. 노드 종류·마크·링크 스킴 검증이 그 안에 있으므로
    티켓 쪽에서 규칙을 다시 쓰지 않는다 — 규칙이 두 벌이면 한쪽만 고쳐지는 날이 온다.
    """
    return block_schema.derive(doc, carry_from=carry_from)
