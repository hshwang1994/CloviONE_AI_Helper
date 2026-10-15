"""도구 결과 봉투 — 모델이 받는 모양 하나 (D-535 · 세기 계약).

  성공  {"ok": true, "tool", "total", "returned", "offset", "truncated", "items": [...], "note", …extra}
  실패  {"ok": false, "tool", "error", "message", …extra}

## `total` 은 권한 안의 정확한 수다

`total` 은 **그 도구가 보는 범위(대화 주인의 권한) 안에서 조건에 맞는 전체 건수**이고, `items` 는 그중 한 쪽
(`offset` 부터 `returned` 건)이다. 모델은 개수를 물으면 `total` 을 그대로 말하고 `items` 의 길이로 세지 않는다
(`app/llm/prompt.py::ASSISTANT_COUNT_RULE`). 세지 못했으면(시간 초과) `total` 은 `null` 이고 `note` 가 그 사실을 말한다 —
모르는 수를 돌려준 수로 꾸미지 않는다. `truncated` 는 「이 쪽 뒤에 더 있다」다.

실패 코드는 여섯이다. 범위 밖 대상은 없는 대상과 **같은** `not_found` 와 같은 문장이다 - 존재를 흘리지 않는다.
`ambiguous` 는 `extra={"candidates": [...]}` 로 후보를 싣는다 — 모델이 사용자에게 고르게 한다.
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

#: 「전체 수를 세지 못했다」(시간 초과)의 note. `total` 이 `null` 일 때 함께 간다.
TOTAL_UNKNOWN_NOTE = "전체 건수를 제때 세지 못해 total 이 비어 있습니다. 보인 항목만 사실로 말하고 전체 수는 말하지 마세요."

#: `total` 을 안 주면 items 의 길이다. `None` 을 **명시**하면 「세지 못했다」다 — 둘은 다른 사실이라 기본값을 따로 둔다.
AUTO = object()


@dataclass(frozen=True)
class Execution:
    """도구 한 번의 결과. ``content`` 는 봉투 JSON 이고, 나머지는 화면과 기록이 쓴다(모델에 가지 않는다)."""

    tool: str
    content: str
    ok: bool
    count: int = 0
    #: 권한 안의 전체 건수(화면의 「확인한 내용」이 「N건 중 M건」을 쓴다). 세지 못했으면 None.
    total: int | None = None
    #: 화면의 「확인한 내용」에 보일 검색어(있을 때만).
    query: str | None = None
    #: 화면의 「참고한 자료」 후보 - 서버가 만든 경로가 있는 항목만(`turn.py` 가 모아 중복을 걷는다).
    sources: tuple = field(default_factory=tuple)
    #: 서버가 검증한 인자(`catalog.execute` 가 단다). 결과 블록 · 쪽 넘기기 · 첫 답의 제목이 쓰고, 모델에는 가지 않는다.
    args: dict | None = None


def ok(tool: str, items: list, *, total=AUTO, truncated: bool | None = None, note: str | None = None,
       query: str | None = None, sources: tuple = (), offset: int = 0, extra: dict | None = None) -> Execution:
    """성공 봉투. ``total`` 을 안 주면 items 의 길이, ``None`` 이면 세지 못한 것이다(note 가 없으면 기본 문장을 단다).

    ``truncated`` 를 안 주면 「offset + returned < total」로 정한다.
    """
    returned = len(items)
    offset = max(0, int(offset or 0))
    if total is AUTO:
        count: int | None = returned
    else:
        count = None if total is None else int(total)
    if truncated is None:
        truncated = count is not None and offset + returned < count
    if count is None and not note:
        note = TOTAL_UNKNOWN_NOTE
    body = {"ok": True, "tool": tool, "total": count, "returned": returned, "offset": offset,
            "truncated": bool(truncated), "items": items, "note": note}
    for key, value in (extra or {}).items():
        body.setdefault(key, value)
    return Execution(tool=tool, content=json.dumps(body, ensure_ascii=False, default=str), ok=True,
                     count=returned, total=count, query=query, sources=tuple(sources))


def _dump(body) -> str:
    return json.dumps(body, ensure_ascii=False, default=str)


def _longest_text(node, *, floor: int):
    """봉투 안에서 가장 긴 글 칸 — (담은 것, 열쇠, 글). `floor` 자 이하만 남았으면 None."""
    best = None
    stack = [node]
    while stack:
        current = stack.pop()
        pairs = current.items() if isinstance(current, dict) else enumerate(current) if isinstance(current, list) else ()
        for key, value in pairs:
            if isinstance(value, str) and len(value) > floor and (best is None or len(value) > len(best[2])):
                best = (current, key, value)
            elif isinstance(value, (dict, list)):
                stack.append(value)
    return best


def fit(content: str, limit: int, *, cut_note: str) -> str:
    """봉투 글을 `limit` 자 안에 맞춘다 — **JSON 가운데를 자르지 않는다.**

    뒤 항목부터 덜어 내고 `returned` · `truncated` · `note` 를 고친다(모델이 offset 으로 이어 본다). 그래도 넘치면 가장 긴 글 칸을
    넘친 만큼 줄이고, 그래도 넘치면(봉투가 아닌 글) 앞부분만 싣고 `cut_note` 를 단다. 예전에는 늘 글자째 잘라 마지막 항목의 따옴표가
    열린 채로 모델에 갔다."""
    if len(content) <= limit:
        return content
    try:
        body = json.loads(content)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return content[: max(0, limit - len(cut_note) - 1)] + "\n" + cut_note
    items = body.get("items")
    dropped = 0
    text = _dump(body)
    if isinstance(items, list):
        while len(text) > limit and len(items) > 1:
            items.pop()
            dropped += 1
            body["returned"] = len(items)
            body["truncated"] = True
            text = _dump(body)
        if dropped:
            note = f"{cut_note} 뒤 항목 {dropped}개를 덜었습니다. offset 으로 이어서 볼 수 있습니다."
            body["note"] = f"{body['note']} {note}" if body.get("note") else note
            text = _dump(body)
    while len(text) > limit:
        found = _longest_text(body, floor=80)
        if found is None:
            break
        holder, key, value = found
        # 넘친 만큼만 줄인다 — 반으로 자르면 칸을 다 쓰지 않아 다음 결과의 몫(차례 예산)이 흔들린다.
        holder[key] = value[: max(40, len(value) - (len(text) - limit) - 8)].rstrip() + "…"
        if not dropped and "note" in body and cut_note not in str(body.get("note") or ""):
            body["note"] = f"{body['note']} {cut_note}" if body.get("note") else cut_note
        text = _dump(body)
    if len(text) > limit:
        return text[: max(0, limit - len(cut_note) - 1)] + "\n" + cut_note
    return text


def error(tool: str, code: str, message: str | None = None, *, query: str | None = None,
          extra: dict | None = None, sources: tuple = ()) -> Execution:
    """실패 봉투. ``sources`` 는 실패여도 도구가 권한 안에서 찾은 것(예: 이름이 겹친 프로젝트 후보)이다 — 답이 그 후보를
    링크로 걸면 화면이 그 경로를 출처로 확인해 링크로 그린다(없으면 글자로 남았다)."""
    body = {"ok": False, "tool": tool, "error": code, "message": message or MESSAGES[code]}
    for key, value in (extra or {}).items():
        body.setdefault(key, value)
    return Execution(tool=tool, content=json.dumps(body, ensure_ascii=False, default=str), ok=False, query=query,
                     sources=tuple(sources))
