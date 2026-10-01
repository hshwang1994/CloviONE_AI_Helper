"""도구 결과 봉투 — 모델이 받는 모양 하나 (D-535).

  성공  {"ok": true, "tool", "total", "truncated", "items": [...], "note"}
  실패  {"ok": false, "tool", "error", "message"}

실패 코드는 여섯이다. 범위 밖 대상은 없는 대상과 **같은** `not_found` 와 같은 문장이다 - 존재를 흘리지 않는다.
런타임은 이 글을 개인정보 가리기 → 글자 상한 → 난스 칸 순서로 감싸 제공자에 보낸다(`app/ai/runtime.py`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

ERROR_INVALID_ARGUMENTS = "invalid_arguments"
ERROR_NOT_FOUND = "not_found"
ERROR_AMBIGUOUS = "ambiguous"
ERROR_UNAVAILABLE = "unavailable"
ERROR_TOO_MANY_CALLS = "too_many_calls"
ERROR_BUDGET_EXHAUSTED = "budget_exhausted"

MESSAGES: dict[str, str] = {
    ERROR_INVALID_ARGUMENTS: "도구 인자가 형식에 맞지 않습니다.",
    ERROR_NOT_FOUND: "찾지 못했습니다.",
    ERROR_AMBIGUOUS: "같은 이름이 여럿이라 하나로 정하지 못했습니다.",
    ERROR_UNAVAILABLE: "지금은 이 도구를 쓸 수 없습니다.",
    ERROR_TOO_MANY_CALLS: "한 번의 답에 부를 수 있는 도구 수를 넘었습니다. 지금까지 찾은 자료로 답하세요.",
    ERROR_BUDGET_EXHAUSTED: "한 번의 답에 실을 수 있는 자료의 양을 넘었습니다. 지금까지 찾은 자료로 답하세요.",
}


@dataclass(frozen=True)
class Execution:
    """도구 한 번의 결과. ``content`` 는 봉투 JSON 이고, 나머지는 화면과 기록이 쓴다(모델에 가지 않는다)."""

    tool: str
    content: str
    ok: bool
    count: int = 0
    #: 화면의 「확인한 내용」에 보일 검색어(있을 때만).
    query: str | None = None
    #: 화면의 「참고한 자료」 후보 - 서버가 만든 경로가 있는 항목만(`turn.py` 가 모아 중복을 걷는다).
    sources: tuple = field(default_factory=tuple)


def ok(tool: str, items: list, *, total: int | None = None, truncated: bool = False, note: str | None = None,
       query: str | None = None, sources: tuple = ()) -> Execution:
    body = {"ok": True, "tool": tool, "total": len(items) if total is None else int(total),
            "truncated": bool(truncated), "items": items, "note": note}
    return Execution(tool=tool, content=json.dumps(body, ensure_ascii=False, default=str), ok=True,
                     count=len(items), query=query, sources=tuple(sources))


def error(tool: str, code: str, message: str | None = None, *, query: str | None = None) -> Execution:
    body = {"ok": False, "tool": tool, "error": code, "message": message or MESSAGES[code]}
    return Execution(tool=tool, content=json.dumps(body, ensure_ascii=False), ok=False, query=query)
