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
