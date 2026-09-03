"""Confluence ADF → 우리 본문(ProseMirror Block JSON) (문서 개편 14~20번).

## 왜 이 변환이 짧은가

Atlassian Document Format 은 이미 ProseMirror 계열이다 — `doc`·`paragraph`·`text`·
`bulletList`·`listItem`·`table` 이 우리 스키마(`app/knowledge/blocks.py`)와 같은 낱말을
쓴다. 그래서 이 파일이 하는 일은 파싱이 아니라 **어휘 맞추기**다. 저장 포맷(storage
XHTML)을 골랐다면 매크로가 섞인 마크업 파서를 새로 들여야 했고, 그 파서가 틀리는
자리는 본문이 잘린 채로 조용히 들어온다 — 이 회차가 고치려는 바로 그 사고다.

## 못 옮기는 것은 **버리지 않고 말한다**

ADF 에는 우리 스키마에 없는 노드가 있다(`panel`·`status`·`expand`·매크로 `extension`).
그 자리를 조용히 지우면 원본보다 짧은 문서가 되고, 그것이 이 회차가 고치는 결함의
모양이다. 그래서 **글자를 가진 것은 글자를 건지고**, 글자가 없는 장식만 버린다.

## 미리보기 카드도 내용이다

`inlineCard`·`blockCard`·`embedCard` 는 링크의 미리보기다(실측 203+1+3개). 주소를 버리면
「여기 무언가 있었다」가 사라지므로 **링크 문단**으로 남긴다. `mediaSingle`/`media`/
`mediaGroup`/`mediaInline` 은 본문 이미지이고(976+21+4개), 첨부로 옮긴 뒤 우리 주소로
바꾼다 — 원본 주소는 인증이 필요해 본문에 남기면 깨진 그림만 보인다.

## 표는 우리 규약대로 다시 짓는다

빈 셀은 **빈 문단 하나**를 갖는다. 문단을 안 넣으면 ProseMirror 가 그 셀을 빈 칸이
아니라 잘못된 모양으로 읽는다(`transform.py::_table` 과 같은 규약).
"""

from __future__ import annotations

from typing import Any

from app.migration.transform import (
    _link_paragraph,
    _list_item,
    _paragraph,
)

__all__ = [
    "MEDIA_NODES",
    "adf_to_doc",
    "adf_media_ids",
    "adf_plain_text",
]

#: 바이트를 가리키는 노드. 첨부로 옮긴 뒤 `media_urls` 로 주소를 받는다.
MEDIA_NODES = frozenset({"media", "mediaInline"})

#: 자기 자신은 아무 자리도 안 차지하고 자식만 이어 붙이는 노드. 자리표시자를 남기면
#: 군더더기다 — 「여기 레이아웃 칸이 있었다」는 옮겨진 글 어디에도 필요하지 않다.
_TRANSPARENT = frozenset({
    "layoutSection", "layoutColumn", "expand", "nestedExpand",
    "bodiedExtension", "mediaSingle", "mediaGroup", "caption",
})

_HEADING_MAX = 6

#: 못 옮긴 자리에 남기는 말. **내부 타입 이름을 사용자에게 보여 주지 않는다.**
_LOST_MEDIA = "원본에만 있는 이미지입니다."
_LOST_BLOCK = "원본에만 있는 내용입니다."

#: ADF 마크 → 우리 마크. 없는 것은 **글자만 남기고 마크를 뗀다**(저장을 거절하지 않는다).
_MARKS = {
    "strong": "bold",
    "em": "italic",
    "strike": "strike",
    "code": "code",
    "underline": "underline",
}


def _text_node(text: str, marks: list[dict] | None = None) -> dict:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _inline(nodes) -> list[dict]:
    """ADF 인라인 → 우리 인라인. 링크와 굵기·기울임·취소선·코드·밑줄을 옮긴다."""
    out: list[dict] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        kind = node.get("type")
        if kind == "text":
            text = node.get("text")
            if not isinstance(text, str) or not text:
                continue
            marks: list[dict] = []
            for mark in node.get("marks") or []:
                if not isinstance(mark, dict):
                    continue
                name = mark.get("type")
                if name == "link":
                    href = ((mark.get("attrs") or {}).get("href") or "").strip()
                    if href:
                        marks.append({"type": "link", "attrs": {"href": href}})
                elif name in _MARKS:
                    marks.append({"type": _MARKS[name]})
            out.append(_text_node(text, marks))
        elif kind == "hardBreak":
            out.append({"type": "hardBreak"})
        elif kind == "emoji":
            # 이모지는 **글자다.** 노드를 버리면 문장에서 한 글자가 사라진다.
            attrs = node.get("attrs") or {}
            symbol = attrs.get("text") or attrs.get("shortName") or ""
            if symbol:
                out.append(_text_node(str(symbol)))
        elif kind in ("status", "date"):
            # 상태 알약과 날짜 알약. 우리 스키마에 그 노드가 없으므로 **글자로** 남긴다.
            attrs = node.get("attrs") or {}
            label = attrs.get("text") or attrs.get("timestamp") or ""
            if label:
                out.append(_text_node(str(label)))
        elif kind == "inlineCard":
            # 링크 미리보기. 주소를 버리면 「여기 무언가 있었다」가 사라진다.
            href = ((node.get("attrs") or {}).get("url") or "").strip()
            if href:
                out.append(_text_node(href, [{"type": "link", "attrs": {"href": href}}]))
        elif kind == "mention":
            # 우리 `mention` 은 우리 사용자 id 를 가리킨다 — 남의 시스템 id 를 넣으면
            # 그 자리는 「없는 사람」이 된다. 이름만 글자로 남긴다.
            name = (node.get("attrs") or {}).get("text") or ""
            if name:
                out.append(_text_node(str(name).lstrip("@")))
        elif kind in MEDIA_NODES:
            continue  # 블록 층에서 다룬다
        else:
            nested = _inline(node.get("content"))
            out.extend(nested)
    return out


def _cell(node: dict, media_urls: dict) -> dict:
    kind = "tableHeader" if node.get("type") == "tableHeader" else "tableCell"
    inner = _blocks(node.get("content"), media_urls)
    if not inner:
        # 빈 셀에도 문단 하나가 있어야 한다 — 위 머리말의 규약.
        inner = [{"type": "paragraph"}]
    return {
        "type": kind,
        "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None},
        "content": inner,
    }


def _table(node: dict, media_urls: dict) -> dict | None:
    rows: list[dict] = []
    for row in node.get("content") or []:
        if not isinstance(row, dict) or row.get("type") != "tableRow":
            continue
        cells = [
            _cell(c, media_urls)
            for c in (row.get("content") or [])
            if isinstance(c, dict) and c.get("type") in ("tableHeader", "tableCell")
        ]
        if cells:
            rows.append({"type": "tableRow", "content": cells})
    return {"type": "table", "content": rows} if rows else None


def _media(node: dict, media_urls: dict) -> list[dict]:
    """이미지 하나. 주소를 못 받았으면 **자리표시자 문단**을 남긴다."""
    attrs = node.get("attrs") or {}
    key = str(attrs.get("id") or attrs.get("url") or "")
    src = media_urls.get(key)
    alt = str(attrs.get("alt") or "")
    if src:
        return [{"type": "image", "attrs": {"src": src, "alt": alt, "title": None}}]
    return [_paragraph(_LOST_MEDIA)]


def _blocks(nodes, media_urls: dict) -> list[dict]:
    out: list[dict] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        kind = node.get("type")
        children = node.get("content")

        if kind == "paragraph":
            inline = _inline(children)
            # 빈 문단은 넣지 않는다 — 간격용 빈 블록이 흔하고, 그대로 옮기면 편집기에
            # 빈 문단이 줄줄이 남는다. 다만 그 문단이 이미지만 품고 있었으면 다르다.
            media = [c for c in (children or [])
                     if isinstance(c, dict) and c.get("type") in MEDIA_NODES]
            if inline:
                out.append({"type": "paragraph", "content": inline})
            for item in media:
                out.extend(_media(item, media_urls))
        elif kind == "heading":
            level = (node.get("attrs") or {}).get("level")
            level = level if isinstance(level, int) and 1 <= level <= _HEADING_MAX else 2
            out.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": _inline(children) or [],
            })
        elif kind in ("bulletList", "orderedList"):
            items: list[dict] = []
            for raw in children or []:
                if not isinstance(raw, dict) or raw.get("type") != "listItem":
                    continue
                inner = _blocks(raw.get("content"), media_urls)
                # 첫 문단은 항목의 글자, 나머지는 그 아래 내용이다.
                head = inner[0] if inner and inner[0].get("type") == "paragraph" else None
                rest = inner[1:] if head is not None else inner
                items.append(_list_item((head or {}).get("content") or [], rest))
            if items:
                out.append({"type": kind, "content": items})
        elif kind == "taskList":
            items = []
            for raw in children or []:
                if not isinstance(raw, dict) or raw.get("type") != "taskItem":
                    continue
                done = (raw.get("attrs") or {}).get("state") == "DONE"
                inline = _inline(raw.get("content"))
                # 우리 `taskItem` 은 체크 상태를 attrs 로 든다.
                items.append({
                    "type": "taskItem",
                    "attrs": {"checked": bool(done)},
                    "content": [{"type": "paragraph", "content": inline}] if inline
                               else [{"type": "paragraph"}],
                })
            if items:
                out.append({"type": "taskList", "content": items})
        elif kind == "decisionList":
            # 우리 스키마에 결정 목록이 없다. **글머리 목록으로 내린다** — 지우면
            # 「무엇을 정했는가」가 통째로 사라진다.
            items = []
            for raw in children or []:
                if not isinstance(raw, dict):
                    continue
                inline = _inline(raw.get("content"))
                if inline:
                    items.append(_list_item(inline, []))
            if items:
                out.append({"type": "bulletList", "content": items})
        elif kind == "blockquote":
            inner = _blocks(children, media_urls)
            if inner:
                out.append({"type": "blockquote", "content": inner})
        elif kind == "panel":
            # 안내 상자. 우리 스키마에 없으므로 인용으로 내린다 — 글자는 남는다.
            inner = _blocks(children, media_urls)
            if inner:
                out.append({"type": "blockquote", "content": inner})
        elif kind == "codeBlock":
            language = str((node.get("attrs") or {}).get("language") or "")
            text = "".join(
                c.get("text", "") for c in (children or [])
                if isinstance(c, dict) and c.get("type") == "text"
            )
            out.append({
                "type": "codeBlock",
                "attrs": {"language": language},
                "content": [_text_node(text)] if text else [],
            })
        elif kind == "rule":
            out.append({"type": "horizontalRule"})
        elif kind == "table":
            built = _table(node, media_urls)
            if built is not None:
                out.append(built)
        elif kind in MEDIA_NODES:
            out.extend(_media(node, media_urls))
        elif kind in ("blockCard", "embedCard"):
            href = ((node.get("attrs") or {}).get("url") or "").strip()
            if href:
                out.append(_link_paragraph(href, href))
        elif kind in ("extension", "inlineExtension"):
            # 매크로. 우리가 그릴 수 없지만 **그 자리에 무언가 있었다**는 것은 사실이다.
            # 글자를 가진 자식이 있으면 건지고, 없으면 한 줄로 말한다.
            inner = _blocks(children, media_urls)
            out.extend(inner if inner else [_paragraph(_LOST_BLOCK)])
        elif kind == "placeholder":
            continue  # 「여기에 입력하세요」 — 원본에도 내용이 아니다
        elif kind in _TRANSPARENT:
            out.extend(_blocks(children, media_urls))
        else:
            inner = _blocks(children, media_urls)
            if inner:
                out.extend(inner)
            else:
                inline = _inline(children)
                if inline:
                    out.append({"type": "paragraph", "content": inline})
    return out


def adf_to_doc(adf: dict | None, *, media_urls: dict | None = None) -> dict:
    """ADF 문서 → 우리 본문. **정규화는 부르는 쪽이 한다**(`blocks.normalize`)."""
    content = _blocks((adf or {}).get("content"), media_urls or {})
    return {"type": "doc", "content": content}


def adf_media_ids(adf: dict | None) -> list[str]:
    """본문이 가리키는 첨부 식별자 전부. 순서를 지킨다 — 같은 그림이 두 번 나오면
    두 자리 다 같은 주소를 받아야 한다."""
    found: list[str] = []
    seen: set[str] = set()

    def walk(nodes) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            if node.get("type") in MEDIA_NODES:
                attrs = node.get("attrs") or {}
                key = str(attrs.get("id") or attrs.get("url") or "")
                if key and key not in seen:
                    seen.add(key)
                    found.append(key)
            walk(node.get("content"))

    walk((adf or {}).get("content"))
    return found


def adf_plain_text(adf: dict | None) -> str:
    """본문의 글자만. 대조(원본보다 짧아졌는가)를 재는 자리가 쓴다."""
    parts: list[str] = []

    def walk(nodes) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            walk(node.get("content"))

    walk((adf or {}).get("content"))
    return "".join(parts)
