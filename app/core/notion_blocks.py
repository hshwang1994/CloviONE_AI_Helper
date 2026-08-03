"""가벼운 마크다운 → Notion 블록 변환(공용).

문서 본문(app/team_docs)과 티켓 설명(app/tickets)이 같은 규칙으로 서식을 렌더하도록 한 곳에
모은다. 프런트의 본문 편집기/미리보기(BodyEditor)와 규칙이 정확히 일치해야 사용자가 본 미리보기와
실제 저장 결과가 어긋나지 않는다.

인식 규칙:
- `---` / `___` / `***` (그 줄만) → 구분선(divider)
- `# ` / `## ` / `### ` → 제목 1/2/3
- `- ` / `* ` → 글머리 목록,  `1. ` 등 → 번호 목록
- 그 외 → 문단(빈 줄은 빈 문단 = 간격). 이모지/기호는 그대로 텍스트.
Notion children 상한(100)까지, 각 줄 1900자까지.
"""

from __future__ import annotations

import re

MAX_BLOCKS = 100
MAX_LINE_CHARS = 1900

_NUM_LINE = re.compile(r"^(\d+)\.\s+(.*)$")


def _rt_block(btype: str, text: str) -> dict:
    rt = [{"text": {"content": text[:MAX_LINE_CHARS]}}] if text.strip() else []
    return {"object": "block", "type": btype, btype: {"rich_text": rt}}


def markdown_to_blocks(body: str) -> list[dict]:
    lines = (body or "").split("\n")[:MAX_BLOCKS]
    out: list[dict] = []
    for ln in lines:
        s = ln.strip()
        if s in ("---", "___", "***"):
            out.append({"object": "block", "type": "divider", "divider": {}})
            continue
        if s.startswith("### "):
            out.append(_rt_block("heading_3", s[4:]))
            continue
        if s.startswith("## "):
            out.append(_rt_block("heading_2", s[3:]))
            continue
        if s.startswith("# "):
            out.append(_rt_block("heading_1", s[2:]))
            continue
        if s.startswith("- ") or s.startswith("* "):
            out.append(_rt_block("bulleted_list_item", s[2:]))
            continue
        m = _NUM_LINE.match(s)
        if m:
            out.append(_rt_block("numbered_list_item", m.group(2)))
            continue
        rt = [{"text": {"content": ln[:MAX_LINE_CHARS]}}] if ln.strip() else []
        out.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": rt}})
    return out


# ── 역방향: Notion 블록 → 마크다운 ────────────────────────────────────────────
# 본문 정본을 우리 DB(마크다운)에 두려면 지금 Notion에 있는 본문을 한 번은 마크다운으로 되읽어야
# 한다. markdown_to_blocks 가 만드는 블록 종류는 손실 없이 되돌아오고(왕복 안정), 우리가 만들지
# 않는 종류(to_do/quote/code)는 가장 가까운 마크다운으로 내린다. 그 밖의 블록(이미지·임베드 등)은
# 마크다운으로 표현할 수 없으므로 건너뛴다 — 온전한 열람은 원본 링크로.
_BLOCK_PREFIX = {
    "heading_1": "# ",
    "heading_2": "## ",
    "heading_3": "### ",
    "bulleted_list_item": "- ",
    "quote": "> ",
    "paragraph": "",
}


def _plain_text(container: dict) -> str:
    """rich_text 배열에서 글자만 뽑는다.

    Notion 응답은 plain_text 에, 우리가 만든 블록(markdown_to_blocks)은 text.content 에 글자를
    담는다 — 둘 다 읽어야 markdown → blocks → markdown 왕복이 성립한다.
    """
    parts: list[str] = []
    for seg in (container.get("rich_text") or []):
        if not isinstance(seg, dict):
            continue
        if seg.get("plain_text") is not None:
            parts.append(seg["plain_text"])
            continue
        text = seg.get("text")
        if isinstance(text, dict):
            parts.append(text.get("content") or "")
    return "".join(parts)


def blocks_to_markdown(blocks) -> str:
    """Notion 블록 목록을 가벼운 마크다운 한 덩어리로 되돌린다(markdown_to_blocks 의 역)."""
    lines: list[str] = []
    number = 0
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type") or ""
        raw = block.get(btype)
        container = raw if isinstance(raw, dict) else {}
        if btype != "numbered_list_item":
            number = 0  # 목록이 끊기면 번호를 1부터 다시 센다
        if btype == "divider":
            lines.append("---")
        elif btype == "numbered_list_item":
            number += 1
            lines.append(f"{number}. {_plain_text(container)}")
        elif btype == "to_do":
            mark = "x" if container.get("checked") else " "
            lines.append(f"- [{mark}] {_plain_text(container)}")
        elif btype == "code":
            lines.append("```")
            lines.append(_plain_text(container))
            lines.append("```")
        elif btype in _BLOCK_PREFIX:
            text = _plain_text(container)
            # 빈 문단은 마크다운에서도 빈 줄이다 — 접두사를 붙이면 '- ' 만 남은 줄이 생긴다.
            lines.append(f"{_BLOCK_PREFIX[btype]}{text}" if text else "")
        # 그 밖(image/embed/table…)은 마크다운으로 표현할 수 없어 건너뛴다.
    return "\n".join(lines)


# ── 렌더용 축약형 → 마크다운 ──────────────────────────────────────────────────
# 티켓·문서 상세 API 가 화면에 내려보내는 본문은 Notion 원본 블록이 아니라 축약형
# [{kind, text, checked?}] 이다(notion_write.fetch_page_blocks). 편집기를 열 때 그 본문을
# 되읽어야 하는데, 원본 블록을 다시 받아오려고 Notion 을 한 번 더 왕복하는 건 낭비다.
# 그래서 같은 규칙을 축약형에도 적용한다 — blocks_to_markdown 과 출력이 일치해야 한다.
#
# `unsupported`(이미지·표·컬럼…)는 **건너뛴다**. '[image] 원본에서 확인' 을 글자로 남기면
# 저장할 때 그 문구가 진짜 문단으로 Notion 에 써 넣어진다. 대신 그런 블록이 있었다는 사실은
# 호출측이 blocks 배열에서 직접 보고 사용자에게 경고한다(저장하면 원본에서 사라지므로).
_KIND_PREFIX = {
    "heading_1": "# ",
    "heading_2": "## ",
    "heading_3": "### ",
    "bulleted": "- ",
    "quote": "> ",
    # callout/toggle 은 마크다운에 대응이 없다 — 가장 가까운 문단으로 내린다.
    "callout": "",
    "toggle": "",
    "paragraph": "",
}


def rendered_to_markdown(items) -> str:
    """`[{kind, text, checked?}]`(fetch_page_blocks 출력) → 가벼운 마크다운."""
    lines: list[str] = []
    number = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") or ""
        text = item.get("text") or ""
        if kind != "numbered":
            number = 0  # 목록이 끊기면 번호를 1부터 다시 센다(blocks_to_markdown 과 동일)
        if kind == "divider":
            lines.append("---")
        elif kind == "numbered":
            number += 1
            lines.append(f"{number}. {text}")
        elif kind == "todo":
            lines.append(f"- [{'x' if item.get('checked') else ' '}] {text}")
        elif kind == "code":
            lines.append("```")
            lines.append(text)
            lines.append("```")
        elif kind in _KIND_PREFIX:
            lines.append(f"{_KIND_PREFIX[kind]}{text}" if text else "")
        # unsupported 및 알 수 없는 kind 는 건너뛴다.
    return "\n".join(lines)
