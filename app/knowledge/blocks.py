"""Block JSON — 문서 본문의 **정본**이고, 파생을 만드는 유일한 자리다 (D-198).

## 왜 Markdown 이 아니라 노드 트리인가

    인용 위치   블록 id 가 안정적 앵커다. Markdown 만으로는 「이 문장의 출처」를 못 가리킨다
    버전 diff   노드 단위 비교가 줄 단위 비교보다 정확하다 — 줄바꿈만 바뀐 판이 전면 수정으로 안 보인다
    검색·임베딩 파생 Plain Text 를 pg_trgm · FTS · 임베딩에 넣는다
    편집기 교체 ProseMirror 스키마는 공개 표준이다. HTML 을 정본으로 두면 편집기에 묶인다

## 파생을 여기서만 만드는 이유

`document_versions` 에는 정본(`body`) 옆에 `body_markdown`·`body_text` 가 함께 있다.
저장하는 이유는 검색 색인이 질의 시각에 본문을 다시 만들 수 없기 때문이고, 저장하는
순간 **갈라질 수 있는 값**이 된다. 두 곳에서 만들면 같은 판이 화면과 검색에서 다른 글이
되고, 그 어긋남은 「검색해도 안 나오는 문서」로만 드러난다 — 아무도 신고하지 않는다.

그래서 `derive()` 하나만 그 셋을 함께 만들고, 다른 파일이 파생 컬럼에 값을 넣는지는
`scripts/check_domain_single_source.py` 가 확인한다.

## 길이로 거절하지 않는다

옛 코드에는 `MAX_BLOCKS = 100` · `MAX_LINE_CHARS = 1900` 이 있었고 그것을 넘는 본문은
**저장 자체가 거절**됐다. 그 두 수는 Notion API 의 한 번 요청 상한이지 이 제품의 규칙이
아니었다 — 회의록 하나가 100줄을 넘으면 저장이 안 됐다. 자체 DB 에는 다 들어간다.

거절하는 것은 길이가 아니라 **모양**이다: 모르는 노드 종류, 위험한 링크, 그리고 파서가
스스로를 지킬 수 없는 깊이. 셋 다 길면 나쁜 것이 아니라 틀린 것이다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EMPTY_DOC",
    "BlockError",
    "Derived",
    "empty_doc",
    "from_plain_text",
    "normalize",
    "derive",
    "to_markdown",
    "to_text",
    "extract_mentions",
    "diff",
    "block_ids",
    "iter_block_text",
]


class BlockError(ValueError):
    """본문의 모양이 틀렸다. 길어서가 아니라 **읽을 수 없어서**다."""


# ── 스키마 ───────────────────────────────────────────────────────────────────
#
# TipTap StarterKit 과 공식 MIT 확장(`extension-image`·`extension-table`)이 내는 노드
# 그대로다. Pro extension 은 상용 라이선스라 쓰지 않는다(D-198). 목록에 없는 종류는
# **거절한다** — 통과시키면 편집기가 못 그리는 값이 DB 에 들어가고, 그 문서는 열 때마다
# 빈 화면이 된다.
#
# `image` 와 `table` 은 S14 에서 들어왔다. 그 전에는 스키마에 자리가 없어서 이관이 원본
# 이미지 49블록과 표 93개를 `[원본에서 확인: image]` 같은 **글자**로 바꿔 넣었고, 표
# 셀의 31,310자는 어디에도 남지 않았다.
BLOCK_NODES: frozenset[str] = frozenset({
    "paragraph", "heading", "bulletList", "orderedList", "blockquote",
    "codeBlock", "horizontalRule", "image", "table",
})
# 블록 안에서만 나오는 구조 노드. 최상위에 오면 편집기가 못 그린다.
NESTED_NODES: frozenset[str] = frozenset({
    "listItem", "tableRow", "tableHeader", "tableCell",
})
INLINE_NODES: frozenset[str] = frozenset({"text", "hardBreak", "mention"})
KNOWN_NODES = BLOCK_NODES | NESTED_NODES | INLINE_NODES

# 구조 노드가 **어디에 올 수 있는가**. 종류만 맞고 자리가 틀린 값은 편집기가 못 그린다 —
# `tableCell` 이 표 밖에 떠 있거나 `table` 이 문단을 직접 품으면 ProseMirror 는 그 문서를
# 통째로 버린다. 그래서 두 방향을 함께 강제한다: 자식이 부모를 고르고(`NODE_PARENTS`),
# 부모가 자식을 고른다(`NODE_CHILDREN`). 한쪽만 보면 반대쪽 모양이 그대로 통과한다.
NODE_PARENTS: dict[str, frozenset[str]] = {
    "listItem": frozenset({"bulletList", "orderedList"}),
    "tableRow": frozenset({"table"}),
    "tableHeader": frozenset({"tableRow"}),
    "tableCell": frozenset({"tableRow"}),
}
NODE_CHILDREN: dict[str, frozenset[str]] = {
    "bulletList": frozenset({"listItem"}),
    "orderedList": frozenset({"listItem"}),
    "table": frozenset({"tableRow"}),
    "tableRow": frozenset({"tableHeader", "tableCell"}),
}
TABLE_CELL_NODES: frozenset[str] = frozenset({"tableHeader", "tableCell"})

MARKS: frozenset[str] = frozenset({"bold", "italic", "strike", "code", "link"})

# 링크가 가리킬 수 있는 것. 목록에 없으면 **마크를 떼고 글자만 남긴다** — 저장을 통째로
# 거절하면 사용자가 방금 쓴 글을 잃는다. `javascript:` 가 이 목록에 없는 이유는 설명이
# 필요 없다.
SAFE_LINK_SCHEMES: frozenset[str] = frozenset({"http", "https", "mailto"})

# 이미지가 가리킬 수 있는 것. 링크보다 좁다.
#
#   * `mailto:` 는 그림이 아니다.
#   * `data:` 는 뺀다 — `data:image/svg+xml` 은 그림처럼 보이지만 스크립트를 품을 수 있고,
#     본문 바이트를 DB 에 통째로 싣는 길이기도 하다. 이미지 바이트는 우리 첨부 저장소에
#     넣고 `src` 는 우리 엔드포인트를 가리킨다(D4).
#
# 스킴이 없는 상대 주소(`/api/attachments/…`)는 통과한다 — 우리 첨부가 바로 그 모양이다.
SAFE_IMAGE_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")

# 파서가 자기를 지킬 수 있는 깊이. 목록 안의 목록 안의 목록…은 실제로 쓰이지만
# 스물몇 겹은 사람이 만든 것이 아니다. 이것은 길이 제한이 아니라 재귀 방어다.
MAX_DEPTH = 24

# 최상위 블록에 붙는 안정적 앵커의 속성 이름. 인용이 이 값을 가리킨다.
BLOCK_ID_ATTR = "blockId"

MENTION_KINDS: frozenset[str] = frozenset({"user", "document", "ticket"})

EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": []}


def empty_doc() -> dict[str, Any]:
    """빈 본문 **새 사전**. 상수를 그대로 주면 부르는 쪽이 그것을 고친다."""
    return {"type": "doc", "content": []}


def from_plain_text(text: str) -> dict[str, Any]:
    """줄글 → 본문. **AI 초안이 문서가 되는 자리다** (S10).

    여기 두는 이유는 이 파일이 「본문을 만드는 유일한 자리」이기 때문이다. 부르는 쪽이
    `{"type": "paragraph", ...}` 를 직접 조립하면 노드 이름을 아는 곳이 하나 늘고,
    스키마가 바뀌는 날 그쪽만 낡는다.

    **마크다운으로 읽지 않는다.** 모델이 낸 글에 `#` 이나 `**` 가 섞여 있어도 그것을
    제목이나 굵은 글씨로 해석하지 않는다 — 해석하려면 마크다운 파서가 필요하고, 그
    파서는 모델이 반쯤 만든 표를 만나는 순간 사람이 쓴 적 없는 구조를 만든다. 초안은
    문단으로만 들어오고, 꾸미는 것은 사람이 편집기에서 한다.

    빈 줄은 문단을 나누고 문단 자체로는 안 남는다. 연달아 친 빈 줄이 그대로 남으면
    편집기에 빈 문단이 줄줄이 생긴다.
    """
    body = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [part.strip() for part in body.split("\n\n")]
    content = [
        {"type": "paragraph", "content": [{"type": "text", "text": part}]}
        for part in paragraphs if part
    ]
    return {"type": "doc", "content": content} if content else empty_doc()


@dataclass(frozen=True)
class Derived:
    """한 판을 이루는 셋. **함께** 만들어야 갈라지지 않는다."""

    body: dict[str, Any]
    markdown: str
    text: str


# ── 정규화 ───────────────────────────────────────────────────────────────────


def normalize(doc: Any, *, id_factory=None, carry_from: Any = None) -> dict[str, Any]:
    """검사하고, 최상위 블록에 안정적 id 를 붙여 돌려준다.

    **원본을 고치지 않는다.** 부르는 쪽이 넘긴 사전을 제자리에서 바꾸면, 저장이
    실패했을 때 그 사전을 다시 쓰는 코드가 반쯤 정규화된 값을 보게 된다.

    이미 있는 `blockId` 는 **그대로 둔다** — 그것이 「안정적 앵커」의 뜻이다. 판이
    바뀌어도 안 건드린 문단의 인용은 계속 같은 곳을 가리켜야 한다.

    ## `carry_from` — id 를 안 돌려주는 클라이언트를 위한 폴백

    앵커의 주인은 편집기다. TipTap 은 `attrs` 를 그대로 들고 있다가 저장할 때 돌려주므로
    우리 화면은 이 폴백을 안 탄다. 그런데 **그러지 않는 부르는 쪽이 있다**:

      * API 를 직접 쓰는 도구 — 본문을 만들어 보내지 우리가 준 것을 되돌려보내지 않는다
      * **S13 마이그레이션** — 매 회차 Notion 응답에서 본문을 새로 만든다

    폴백이 없으면 그런 저장마다 앵커가 전부 새로 발급되고, 그러면 (1) 내용이 똑같은
    재실행이 판을 계속 쌓고 (2) 한 문단만 고친 판의 차이가 「전부 지우고 전부 새로 씀」이
    된다. 둘 다 오류가 아니라서 아무도 신고하지 않는다.

    그래서 **id 가 없는 블록에는 앞판의 같은 자리 앵커를 물려준다.** 한계는 분명하다 —
    가운데에 한 문단을 끼워 넣으면 뒤가 한 칸씩 밀려 전부 「고쳐짐」으로 보인다. 그것을
    감수하는 이유는, id 를 돌려주는 클라이언트는 이 경로를 아예 안 타고 안 돌려주는
    쪽에는 자리 말고 기댈 것이 없기 때문이다.
    """
    make_id = id_factory or (lambda: uuid.uuid4().hex)
    carried = block_ids(carry_from) if isinstance(carry_from, dict) else ()

    if not isinstance(doc, dict):
        raise BlockError("본문은 객체여야 합니다.")
    if doc.get("type") != "doc":
        raise BlockError("본문의 최상위 종류는 doc 여야 합니다.")

    content = doc.get("content", [])
    if content is None:
        content = []
    if not isinstance(content, list):
        raise BlockError("본문의 content 는 목록이어야 합니다.")

    # 들어온 본문이 이미 쓰고 있는 앵커. 물려줄 때 이것과 부딪히면 안 된다.
    incoming = {
        (n.get("attrs") or {}).get(BLOCK_ID_ATTR)
        for n in content
        if isinstance(n, dict)
    }

    seen: set[str] = set()
    blocks: list[dict[str, Any]] = []
    for index, node in enumerate(content):
        block = _normalize_node(node, depth=1, top=True)
        attrs = dict(block.get("attrs") or {})
        block_id = attrs.get(BLOCK_ID_ATTR)
        if not isinstance(block_id, str) or not block_id:
            # 앞판의 같은 자리 앵커를 물려받는다(위 docstring). 이미 쓰이고 있는
            # 값이면 물려주지 않는다 — 인용 하나가 두 문단을 가리키게 된다.
            candidate = carried[index] if index < len(carried) else None
            if candidate and candidate not in seen and candidate not in incoming:
                block_id = candidate
        # 중복 id 는 새로 준다. 복사·붙여넣기가 만드는 흔한 상태이고, 그대로 두면
        # 인용 하나가 두 문단을 가리킨다.
        if not isinstance(block_id, str) or not block_id or block_id in seen:
            block_id = make_id()
        seen.add(block_id)
        attrs[BLOCK_ID_ATTR] = block_id
        block["attrs"] = attrs
        blocks.append(block)

    return {"type": "doc", "content": blocks}


def _normalize_node(
    node: Any, *, depth: int, top: bool = False, parent: str | None = None,
) -> dict[str, Any]:
    if depth > MAX_DEPTH:
        raise BlockError(f"본문이 {MAX_DEPTH}겹보다 깊게 중첩됐습니다.")
    if not isinstance(node, dict):
        raise BlockError("본문의 각 노드는 객체여야 합니다.")

    kind = node.get("type")
    if not isinstance(kind, str) or kind not in KNOWN_NODES:
        raise BlockError(f"모르는 노드 종류입니다: {kind!r}")
    if top and kind not in BLOCK_NODES:
        raise BlockError(f"{kind} 는 최상위에 올 수 없습니다.")

    allowed_parents = NODE_PARENTS.get(kind)
    if allowed_parents is not None and parent not in allowed_parents:
        raise BlockError(f"{kind} 는 {'/'.join(sorted(allowed_parents))} 안에만 올 수 있습니다.")
    allowed_children = NODE_CHILDREN.get(parent or "")
    if allowed_children is not None and kind not in allowed_children:
        raise BlockError(f"{parent} 안에는 {'/'.join(sorted(allowed_children))} 만 올 수 있습니다.")

    out: dict[str, Any] = {"type": kind}

    attrs = node.get("attrs")
    if isinstance(attrs, dict) and attrs:
        out["attrs"] = _normalize_attrs(kind, attrs)
    elif kind == "mention":
        raise BlockError("멘션에는 attrs 가 있어야 합니다.")
    elif kind == "image":
        raise BlockError("이미지에는 src 가 있어야 합니다.")

    if kind == "text":
        value = node.get("text")
        if not isinstance(value, str):
            raise BlockError("text 노드에는 text 가 있어야 합니다.")
        out["text"] = value
        marks = _normalize_marks(node.get("marks"))
        if marks:
            out["marks"] = marks
        return out

    children = node.get("content")
    if children is None:
        return out
    if not isinstance(children, list):
        raise BlockError(f"{kind} 의 content 는 목록이어야 합니다.")
    out["content"] = [_normalize_node(c, depth=depth + 1, parent=kind) for c in children]
    return out


def _normalize_attrs(kind: str, attrs: dict) -> dict[str, Any]:
    out = {k: v for k, v in attrs.items() if v is not None}

    if kind == "heading":
        level = out.get("level", 1)
        if not isinstance(level, int) or not 1 <= level <= 6:
            raise BlockError("제목 수준은 1..6 이어야 합니다.")
        out["level"] = level
    elif kind == "mention":
        mention_kind = out.get("kind")
        target = out.get("id")
        if mention_kind not in MENTION_KINDS:
            raise BlockError(f"모르는 멘션 종류입니다: {mention_kind!r}")
        if not isinstance(target, str) or not target.strip():
            raise BlockError("멘션에는 대상 id 가 있어야 합니다.")
        out["id"] = target.strip()
        label = out.get("label")
        out["label"] = label.strip() if isinstance(label, str) else ""
    elif kind == "codeBlock":
        language = out.get("language")
        out["language"] = language.strip() if isinstance(language, str) else ""
    elif kind == "image":
        # 링크와 달리 **거절한다.** 링크는 마크를 떼도 사용자가 쓴 글자가 남지만, 이미지는
        # `src` 가 전부라 뗄 것이 없다. 조용히 버리면 본문이 쓴 사람의 뜻과 달라진 것을
        # 아무도 모르고, 그냥 두면 편집기가 깨진 그림 상자를 그린다. 편집기는 이런 값을
        # 만들지 않으므로 여기 걸리는 것은 잘못 만든 클라이언트나 공격이다.
        src = _safe_href(out.get("src"), schemes=SAFE_IMAGE_SCHEMES)
        if src is None:
            raise BlockError("이미지 주소가 없거나 허용하지 않는 스킴입니다.")
        out["src"] = src
        alt = out.get("alt")
        # `alt` 는 없어도 빈 문자열로 둔다 — 파생 평문이 그 값을 읽고, 없는 키를 매번
        # 확인하게 하면 읽는 쪽마다 기본값을 새로 정한다.
        out["alt"] = alt.strip() if isinstance(alt, str) else ""
        title = out.get("title")
        if isinstance(title, str) and title.strip():
            out["title"] = title.strip()
        else:
            out.pop("title", None)
    elif kind in TABLE_CELL_NODES:
        for name in ("colspan", "rowspan"):
            span = out.get(name, 1)
            if isinstance(span, bool) or not isinstance(span, int) or span < 1:
                raise BlockError("표 칸의 colspan 과 rowspan 은 1 이상의 정수여야 합니다.")
            out[name] = span
        widths = out.get("colwidth")
        if widths is not None:
            if not isinstance(widths, list) or not widths or not all(
                isinstance(w, int) and not isinstance(w, bool) and w > 0 for w in widths
            ):
                raise BlockError("표 칸의 colwidth 는 양의 정수 목록이어야 합니다.")
            out["colwidth"] = list(widths)
    return out


def _normalize_marks(marks: Any) -> list[dict[str, Any]]:
    if marks is None:
        return []
    if not isinstance(marks, list):
        raise BlockError("marks 는 목록이어야 합니다.")

    out: list[dict[str, Any]] = []
    for mark in marks:
        if not isinstance(mark, dict):
            raise BlockError("각 mark 는 객체여야 합니다.")
        kind = mark.get("type")
        if kind not in MARKS:
            raise BlockError(f"모르는 서식입니다: {kind!r}")
        if kind != "link":
            out.append({"type": kind})
            continue
        href = (mark.get("attrs") or {}).get("href")
        safe = _safe_href(href)
        if safe is None:
            # 마크만 뗀다 — 글자는 남는다. 저장을 거절하면 사용자가 방금 쓴 문단을 잃고,
            # 무엇 때문에 거절됐는지도 화면에서 알기 어렵다.
            continue
        out.append({"type": "link", "attrs": {"href": safe}})
    return out


def _safe_href(href: Any, *, schemes: frozenset[str] = SAFE_LINK_SCHEMES) -> str | None:
    """허용한 스킴이면 그대로, 아니면 `None`.

    스킴이 없는 값(`/docs/1`, `#anchor`)은 **상대 주소**라 통과시킨다 — 같은 제품 안의
    링크가 그 모양이다. 앞뒤 공백과 제어문자를 먼저 턴다: `java\\tscript:` 같은 값이
    브라우저에서는 스킴으로 읽히기 때문이다.

    이미지 `src` 도 이 함수를 쓴다. 허용 목록만 좁히고(`SAFE_IMAGE_SCHEMES`) 스킴을 읽는
    규칙은 하나로 둔다 — 두 벌로 나누면 `java\\tscript:` 같은 우회를 한쪽만 막는 날이 온다.
    """
    if not isinstance(href, str):
        return None
    cleaned = "".join(ch for ch in href if ord(ch) > 0x20 or ch == " ").strip()
    if not cleaned:
        return None
    match = _SCHEME_RE.match(cleaned)
    if match is None:
        return cleaned
    return cleaned if match.group(1).lower() in schemes else None


# ── 파생 ─────────────────────────────────────────────────────────────────────


def derive(doc: Any, *, id_factory=None, carry_from: Any = None) -> Derived:
    """정본 하나에서 저장할 셋을 **함께** 만든다. 이 파일 밖에서 부르는 유일한 입구다."""
    body = normalize(doc, id_factory=id_factory, carry_from=carry_from)
    return Derived(body=body, markdown=to_markdown(body), text=to_text(body))


def to_markdown(doc: dict[str, Any]) -> str:
    """사람이 읽고 다른 도구가 받아 가는 형태. **정본이 아니다.**"""
    parts: list[str] = []
    for block in doc.get("content") or []:
        rendered = _block_markdown(block, depth=0)
        if rendered:
            parts.append(rendered)
    return "\n\n".join(parts)


def to_text(doc: dict[str, Any]) -> str:
    """검색·임베딩이 읽는 형태. 서식이 없어야 같은 문장이 같은 벡터가 된다."""
    lines: list[str] = []
    for block in doc.get("content") or []:
        _block_text(block, lines)
    return "\n".join(line for line in lines if line.strip())


def _block_markdown(node: dict[str, Any], *, depth: int, ordinal: int = 1) -> str:
    kind = node.get("type")
    children = node.get("content") or []

    if kind == "paragraph":
        return _inline_markdown(children)
    if kind == "heading":
        level = int((node.get("attrs") or {}).get("level", 1))
        return f"{'#' * level} {_inline_markdown(children)}"
    if kind == "horizontalRule":
        return "---"
    if kind == "image":
        attrs = node.get("attrs") or {}
        return f"![{attrs.get('alt') or ''}]({attrs.get('src') or ''})"
    if kind == "table":
        return _table_markdown(node)
    if kind == "codeBlock":
        language = (node.get("attrs") or {}).get("language") or ""
        body = "".join(c.get("text", "") for c in children if c.get("type") == "text")
        return f"```{language}\n{body}\n```"
    if kind == "blockquote":
        inner = "\n\n".join(
            filter(None, (_block_markdown(c, depth=depth) for c in children))
        )
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
    if kind in ("bulletList", "orderedList"):
        return _list_markdown(node, depth=depth)
    if kind == "listItem":
        return "\n\n".join(
            filter(None, (_block_markdown(c, depth=depth) for c in children))
        )
    return _inline_markdown(children)


def _list_markdown(node: dict[str, Any], *, depth: int) -> str:
    """목록 하나. **자기 깊이만큼 들여쓰지 않는다.**

    중첩은 부모 항목의 「이어지는 줄」 들여쓰기가 이미 만든다. 여기서 한 번 더 들여쓰면
    두 겹이 되고, 세 겹부터는 마크다운 파서가 그 줄을 코드 블록으로 읽는다. 그 실수는
    화면에서 「왜 목록이 회색 상자가 됐지」로 나타나 원인을 찾기 어렵다.
    """
    ordered = node.get("type") == "orderedList"
    lines: list[str] = []
    for index, item in enumerate(node.get("content") or [], start=1):
        marker = f"{index}." if ordered else "-"
        body = _block_markdown(item, depth=depth + 1, ordinal=index)
        if not body:
            lines.append(marker)
            continue
        rows = body.split("\n")
        lines.append(f"{marker} {rows[0]}")
        # 이어지는 줄은 표식 너비만큼 들여쓴다. 안 하면 다음 줄이 목록에서 빠져나온다.
        # 빈 줄에는 안 붙인다 — 공백만 있는 줄은 눈에 안 보이는 차이를 diff 에 만든다.
        indent = " " * (len(marker) + 1)
        lines.extend(f"{indent}{row}" if row else "" for row in rows[1:])
    return "\n".join(lines)


def _table_markdown(node: dict[str, Any]) -> str:
    """표 하나를 GitHub 파이프 표로.

    구분선(`| --- |`)은 **첫 줄 뒤에 무조건 넣는다.** 그 줄이 없으면 어떤 마크다운
    렌더러도 이 덩어리를 표로 읽지 않고 파이프가 그대로 보이는 문단이 된다 — 머리줄이
    없는 표(첫 줄이 `tableHeader` 가 아닌 표)라도 표로 보이는 쪽이 낫다.

    칸 수는 가장 넓은 줄에 맞춘다. 병합된 칸(`colspan`) 때문에 줄마다 칸 수가 다를 수
    있고, 짧은 줄을 그대로 두면 렌더러가 표 전체를 어긋나게 그린다. 병합 자체는 파이프
    표에 없는 개념이라 옮기지 못한다 — 그래서 정본은 파이프 표가 아니라 노드 트리다.
    """
    rows = [
        r for r in (node.get("content") or [])
        if isinstance(r, dict) and r.get("type") == "tableRow"
    ]
    grid = [
        [_cell_markdown(c) for c in (row.get("content") or []) if isinstance(c, dict)]
        for row in rows
    ]
    grid = [cells for cells in grid if cells]
    if not grid:
        return ""

    width = max(len(cells) for cells in grid)
    lines: list[str] = []
    for index, cells in enumerate(grid):
        lines.append("| " + " | ".join([*cells, *[""] * (width - len(cells))]) + " |")
        if index == 0:
            lines.append("| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def _cell_markdown(cell: dict[str, Any]) -> str:
    """칸 하나의 글. **한 줄로 접는다** — 파이프 표의 칸은 줄바꿈을 담지 못한다.

    파이프는 `\\|` 로 escape 한다. 안 하면 칸 안의 글자 하나가 칸 경계가 되어 그 줄부터
    표가 밀린다.
    """
    parts = [
        _block_markdown(child, depth=0)
        for child in (cell.get("content") or []) if isinstance(child, dict)
    ]
    return " ".join(" ".join(parts).replace("|", r"\|").split())


def _inline_markdown(nodes: list[Any]) -> str:
    out: list[str] = []
    for node in nodes:
        kind = node.get("type")
        if kind == "hardBreak":
            out.append("\n")
            continue
        if kind == "mention":
            attrs = node.get("attrs") or {}
            out.append(f"@{attrs.get('label') or attrs.get('id')}")
            continue
        if kind != "text":
            out.append(_inline_markdown(node.get("content") or []))
            continue

        piece = node.get("text", "")
        marks = {m.get("type"): m for m in (node.get("marks") or [])}
        # `code` 를 가장 안쪽에 둔다 — 코드 안에서는 다른 서식이 글자 그대로 보인다.
        if "code" in marks:
            piece = f"`{piece}`"
        if "bold" in marks:
            piece = f"**{piece}**"
        if "italic" in marks:
            piece = f"*{piece}*"
        if "strike" in marks:
            piece = f"~~{piece}~~"
        if "link" in marks:
            href = (marks["link"].get("attrs") or {}).get("href", "")
            piece = f"[{piece}]({href})"
        out.append(piece)
    return "".join(out)


def _block_text(node: dict[str, Any], lines: list[str]) -> None:
    kind = node.get("type")
    children = node.get("content") or []
    if kind in ("bulletList", "orderedList", "blockquote", "listItem"):
        for child in children:
            _block_text(child, lines)
        return
    if kind == "horizontalRule":
        return
    if kind == "image":
        # 그림에서 글자로 남는 것은 `alt` 뿐이다. 없으면 아무 줄도 안 남긴다 — 빈 줄은
        # 검색에 아무것도 안 주면서 인용의 앞뒤 문맥만 벌린다.
        alt = str((node.get("attrs") or {}).get("alt") or "").strip()
        if alt:
            lines.append(alt)
        return
    if kind == "table":
        _table_text(node, lines)
        return
    lines.append(_inline_text(children))


def _table_text(node: dict[str, Any], lines: list[str]) -> None:
    """표의 **셀 글자를 전부** 남긴다. 이 함수가 그 글자가 검색과 임베딩에 닿는 유일한 길이다.

    칸 사이를 탭으로 벌리는 이유는, 그냥 이어 붙이면 이웃한 두 칸의 글자가 한 낱말로
    붙어 버리기 때문이다 — 「가」와 「나」가 「가나」가 되면 어느 쪽으로 검색해도 안 나온다.
    줄바꿈은 표 줄을 나누는 데만 쓴다.
    """
    for row in node.get("content") or []:
        if not isinstance(row, dict):
            continue
        cells: list[str] = []
        for cell in row.get("content") or []:
            if not isinstance(cell, dict):
                continue
            inner: list[str] = []
            for child in cell.get("content") or []:
                if isinstance(child, dict):
                    _block_text(child, inner)
            cells.append(" ".join(line.strip() for line in inner if line.strip()))
        row_text = "\t".join(cells)
        if row_text.strip():
            lines.append(row_text)


def _inline_text(nodes: list[Any]) -> str:
    out: list[str] = []
    for node in nodes:
        kind = node.get("type")
        if kind == "text":
            out.append(node.get("text", ""))
        elif kind == "hardBreak":
            out.append(" ")
        elif kind == "mention":
            attrs = node.get("attrs") or {}
            out.append(str(attrs.get("label") or attrs.get("id") or ""))
        else:
            out.append(_inline_text(node.get("content") or []))
    return "".join(out)


# ── 멘션 ─────────────────────────────────────────────────────────────────────


def extract_mentions(doc: dict[str, Any]) -> tuple[tuple[str, str, str], ...]:
    """`(블록 id, 대상 종류, 대상 id)` — **정규화된** 본문에서만 부른다.

    블록 id 를 함께 내는 것이 요점이다. 「이 문서가 나를 언급한다」가 아니라 「이 문단이
    나를 언급한다」여야 알림에서 그 자리로 이동할 수 있다.

    같은 블록이 같은 사람을 두 번 언급해도 한 번만 낸다 — 표의 유일 제약과 같은 키다.
    """
    found: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for block in doc.get("content") or []:
        block_id = (block.get("attrs") or {}).get(BLOCK_ID_ATTR)
        if not isinstance(block_id, str) or not block_id:
            continue
        for kind, target in _walk_mentions(block):
            key = (block_id, kind, target)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return tuple(found)


def _walk_mentions(node: dict[str, Any]):
    if node.get("type") == "mention":
        attrs = node.get("attrs") or {}
        kind, target = attrs.get("kind"), attrs.get("id")
        if kind in MENTION_KINDS and isinstance(target, str) and target:
            yield kind, target
        return
    for child in node.get("content") or []:
        if isinstance(child, dict):
            yield from _walk_mentions(child)


def iter_block_text(doc: dict[str, Any]):
    """`(블록 id, 종류, 글)` 을 최상위 블록 순서대로.

    `to_text()` 는 문서 전체를 한 덩어리로 준다. 색인은 그것으로 부족하다 — 인용이
    「이 문서 어딘가」가 아니라 **「이 블록」**을 가리켜야 하기 때문이다(D-198).
    그래서 같은 규칙으로 블록마다 끊어서 준다.

    이 함수가 `app/ai/` 가 아니라 여기 있는 이유: TipTap 노드 이름과 블록 앵커의 뜻을
    아는 자리는 이 파일 하나다. 색인 쪽에 같은 지식을 다시 적으면 노드를 하나 늘리는
    날 한쪽만 고치게 되고, 그때 그 블록은 **검색에서만 조용히 사라진다.**
    """
    for block in doc.get("content") or []:
        block_id = (block.get("attrs") or {}).get(BLOCK_ID_ATTR)
        if not isinstance(block_id, str) or not block_id:
            continue
        lines: list[str] = []
        _block_text(block, lines)
        text = "\n".join(line for line in lines if line.strip())
        yield block_id, str(block.get("type") or ""), text


def block_ids(doc: dict[str, Any]) -> tuple[str, ...]:
    """최상위 블록의 앵커를 순서대로."""
    out: list[str] = []
    for block in doc.get("content") or []:
        block_id = (block.get("attrs") or {}).get(BLOCK_ID_ATTR)
        if isinstance(block_id, str) and block_id:
            out.append(block_id)
    return tuple(out)


# ── 판 사이의 차이 ───────────────────────────────────────────────────────────

CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_CHANGED = "changed"
CHANGE_MOVED = "moved"


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """두 판의 차이를 **블록 단위**로.

    ## 왜 줄 단위가 아닌가

    줄 단위 비교는 문단 하나를 두 줄로 나누기만 해도 「그 줄이 지워지고 두 줄이 생겼다」로
    본다. 블록 id 는 편집해도 유지되므로, 같은 문단을 고친 것과 새 문단을 넣은 것이
    구별된다 — 그것이 Block JSON 을 정본으로 고른 이유 중 하나다(D-198).

    `moved` 를 따로 내는 이유도 같다. 문단 순서만 바꾼 판을 「전부 지우고 전부 새로 씀」
    으로 보여 주면, 사람이 그 화면에서 실제 변경을 못 찾는다.

    돌려주는 순서는 **새 판의 순서**다. 지워진 블록은 옛 판에서의 자리에 끼워 넣는다 —
    옛 판 순서로 따로 모아 두면 어디서 사라졌는지 읽는 사람이 다시 맞춰야 한다.
    """
    old_blocks = {b: n for b, n in _by_id(old)}
    new_blocks = {b: n for b, n in _by_id(new)}
    old_order = list(old_blocks)
    new_order = list(new_blocks)
    new_index = {b: i for i, b in enumerate(new_order)}

    out: list[dict[str, Any]] = []
    # 지워진 블록을 옛 판 자리에 끼우려면 「그 앞의 살아남은 블록」을 알아야 한다.
    removed_after: dict[str | None, list[str]] = {}
    anchor: str | None = None
    for block_id in old_order:
        if block_id in new_blocks:
            anchor = block_id
        else:
            removed_after.setdefault(anchor, []).append(block_id)

    def _emit_removed(after: str | None) -> None:
        for block_id in removed_after.pop(after, []):
            out.append({
                "block_id": block_id,
                "change": CHANGE_REMOVED,
                "before": to_text({"type": "doc", "content": [old_blocks[block_id]]}),
                "after": "",
            })

    _emit_removed(None)
    # 옛 판에서 살아남은 블록들의 상대 순서. 새 판의 순서와 어긋나는 자리가 `moved` 다.
    survivors = [b for b in old_order if b in new_blocks]
    kept = set(_longest_increasing(( new_index[b] for b in survivors ), survivors))

    for block_id in new_order:
        node = new_blocks[block_id]
        if block_id not in old_blocks:
            out.append({
                "block_id": block_id,
                "change": CHANGE_ADDED,
                "before": "",
                "after": to_text({"type": "doc", "content": [node]}),
            })
            continue
        before_node = old_blocks[block_id]
        if before_node != node:
            change = CHANGE_CHANGED
        elif block_id not in kept:
            change = CHANGE_MOVED
        else:
            _emit_removed(block_id)
            continue
        out.append({
            "block_id": block_id,
            "change": change,
            "before": to_text({"type": "doc", "content": [before_node]}),
            "after": to_text({"type": "doc", "content": [node]}),
        })
        _emit_removed(block_id)

    # 앵커가 새 판에서도 사라진 경우가 남을 수 있다(연속으로 지워진 꼬리).
    for leftovers in removed_after.values():
        for block_id in leftovers:
            out.append({
                "block_id": block_id,
                "change": CHANGE_REMOVED,
                "before": to_text({"type": "doc", "content": [old_blocks[block_id]]}),
                "after": "",
            })
    return out


def _by_id(doc: dict[str, Any]):
    for block in doc.get("content") or []:
        block_id = (block.get("attrs") or {}).get(BLOCK_ID_ATTR)
        if isinstance(block_id, str) and block_id:
            yield block_id, block


def _longest_increasing(values, labels) -> list[str]:
    """가장 긴 증가 부분수열에 **남는** 라벨들.

    순서가 바뀐 블록을 최소로 고르기 위한 것이다. 이 수열 밖에 있는 것만 `moved` 라
    부르면, 문단 하나를 위로 끌었을 때 그 하나만 옮겨진 것으로 보인다 — 나머지 전부가
    옮겨졌다고 말하는 화면은 읽을 수 없다.
    """
    values = list(values)
    labels = list(labels)
    if not values:
        return []
    # tails[k] = 길이 k+1 인 증가 수열의 마지막 값이 될 수 있는 최솟값의 인덱스
    tails: list[int] = []
    prev: list[int | None] = [None] * len(values)
    for i, value in enumerate(values):
        low, high = 0, len(tails)
        while low < high:
            mid = (low + high) // 2
            if values[tails[mid]] < value:
                low = mid + 1
            else:
                high = mid
        prev[i] = tails[low - 1] if low > 0 else None
        if low == len(tails):
            tails.append(i)
        else:
            tails[low] = i

    out: list[str] = []
    cursor: int | None = tails[-1]
    while cursor is not None:
        out.append(labels[cursor])
        cursor = prev[cursor]
    out.reverse()
    return out
