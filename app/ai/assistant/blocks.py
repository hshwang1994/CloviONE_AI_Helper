"""도구 결과 블록 — 답 아래 목록 · 카드로 그릴 서버 구조, 이어지는 질문의 기억, 첫 답의 의도 제목 (AI 채팅 개선 회차).

예전에는 화면이 모델이 쓴 마크다운 목록을 다시 읽어 그렸다. 「- [제목](route) 작성자, 수정일」 을 줄마다 되풀이했고, 제목에 괄호가
든 문서는 링크가 깨졌으며, 열 건 뒤로는 이어 볼 길이 없었다. 지금은 도구가 돌려준 봉투에서 화면이 쓸 칸만 골라 답에 싣는다.

- 성공한 목록 · 현황 도구 호출마다 블록 하나다(답당 `MAX_BLOCKS`, 항목 `MAX_ITEMS`). 종류마다 허용한 칸만 싣는다 — 발췌 · 본문 ·
  이메일은 싣지 않는다(답은 폴링마다 다시 읽히고, 블록은 그 사람이 그때 볼 수 있던 것의 사본이다 — 출처와 같은 등급).
- `shown` 은 모델이 그 호출에 `show=true` 를 준 것이다. 화면은 보인 블록만 그리고, 나머지는 이어지는 질문의 기억에만 쓴다 —
  답을 찾으려고 살펴본 검색(D-581 의 「찾아본 자료」)이 목록으로 서지 않는다.
- `list_route` 는 서버가 만든 앱 안 상대 경로(전체 목록 화면)이고 모델에 가지 않는다. 화면은 허용한 접두로 다시 확인한다.
- `args` 는 서버가 검증한 인자 그대로다. 쪽 넘기기(`paging.py`)가 이것을 다시 검증해 `offset` · `sort` 만 바꿔 돈다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urlencode

from app.ai.assistant import readers

MAX_BLOCKS = 4
MAX_ITEMS = 10
TITLE_CHARS = 120
#: 프로젝트 현황 카드에 서는 연결 문서 줄 수 — 도구가 싣는 만큼(최근 수정 여섯)이다.
SUMMARY_DOCUMENTS = 6
#: 기억에 싣는 제목 길이와 기억 전체의 글자 상한(앞 두 차례).
MEMORY_TITLE_CHARS = 60
MEMORY_TURNS = 2
MEMORY_CHARS = 2500

#: 도구 → 블록 종류. 여기 없는 도구(문서 읽기 · 티켓 보기 · 통합 검색 · 사람 찾기 · 요약 등)는 블록이 없다.
KINDS: dict[str, str] = {
    "my_documents": "document",
    "search_documents": "document",
    "my_work": "ticket",
    "search_tickets": "ticket",
    "search_projects": "project",
    "my_approvals": "approval",
    "my_notifications": "notification",
    "my_activity": "activity",
    "project_activity": "project_summary",
    "get_project_summary": "project_summary",
}

#: `show` 인자를 받는 도구 — 블록이 있는 도구와 같다.
SHOWABLE = frozenset(KINDS)

#: 종류마다 화면이 쓰는 칸. 발췌(`excerpt` · `text`) · 본문(`body`)은 싣지 않는다.
FIELDS: dict[str, tuple[str, ...]] = {
    "document": ("ref", "title", "author", "legacy_author", "updated_at", "space", "where", "project", "route"),
    "ticket": ("ref", "key", "title", "status", "priority", "due", "project", "assignees", "blocked", "completed_at",
               "route"),
    "project": ("ref", "code", "name", "status", "progress_pct", "health_score", "my_role", "route"),
    "approval": ("ref", "title", "type", "requester", "status", "created_at", "expires_at", "overdue", "route"),
    "notification": ("ref", "title", "read", "created_at", "route"),
    "activity": ("kind", "at", "action", "title", "key", "route"),
}

#: 화면에서 고를 수 있는 정렬(인자 모델이 받는 값 그대로). 없으면 정렬을 바꿀 수 없다.
SORT_OPTIONS: dict[str, tuple[str, ...]] = {
    "my_documents": ("recent", "created", "title"),
    "my_work": readers.TICKET_SORTS,
    "search_tickets": readers.TICKET_SORTS,
}

_NAME_STRIP = re.compile(r"[\[\]()*_`#<>|~]")


def _clip(value, limit: int):
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def _envelope(execution) -> dict | None:
    try:
        body = json.loads(execution.content)
    except (TypeError, ValueError):
        return None
    return body if isinstance(body, dict) and body.get("ok") else None


def _summary_item(item: dict) -> dict:
    """프로젝트 현황 카드 — 진행률 · 건강 · 상태별 수 · 최근 끝낸 일 다섯."""
    tickets = item.get("tickets") or {}
    out = {k: item.get(k) for k in ("ref", "code", "name", "status", "owner", "starts_on", "ends_on", "window_days",
                                    "route") if item.get(k) is not None}
    if isinstance(item.get("progress"), dict):
        out["progress"] = {k: item["progress"].get(k) for k in ("percent", "counted_tasks", "done_tasks")}
    elif item.get("progress_pct") is not None:
        out["progress"] = {"percent": item.get("progress_pct")}
    health = item.get("health") if isinstance(item.get("health"), dict) else {}
    if health or item.get("health_score") is not None:
        out["health"] = {"score": health.get("score", item.get("health_score")),
                         "reasons": [_clip(r.get("label"), 40) for r in (health.get("reasons") or [])[:3]
                                     if isinstance(r, dict) and r.get("label")]}
    if tickets:
        out["tickets"] = {k: tickets.get(k) for k in ("total", "open", "overdue_open", "blocked", "status_counts")}
    done = [r for r in (item.get("recent_completed") or []) if isinstance(r, dict)][:5]
    if done:
        out["recent_completed"] = [_with_ref(r, {k: _clip(r.get(k), TITLE_CHARS)
                                                 for k in ("key", "title", "completed_at", "route")}) for r in done]
        out["recent_completed_total"] = item.get("recent_completed_total")
    documents = item.get("documents") if isinstance(item.get("documents"), dict) else {}
    doc_rows = [d for d in (documents.get("items") or []) if isinstance(d, dict) and d.get("route")][:SUMMARY_DOCUMENTS]
    if doc_rows:
        out["documents"] = {
            "total": documents.get("total"),
            "items": [_with_ref(d, {k: _clip(d.get(k), TITLE_CHARS) for k in ("title", "updated_at", "route")})
                      for d in doc_rows],
        }
    return out


def _with_ref(row: dict, kept: dict) -> dict:
    """카드에 선 줄의 출처 id — 「보인 것」 표시와 참고 자료 판의 겹침 빼기가 쓴다(`shown_keys`)."""
    if row.get("ref"):
        kept["ref"] = str(row["ref"])
    return kept


def _items(kind: str, items) -> list[dict]:
    rows = [i for i in items or [] if isinstance(i, dict)][:MAX_ITEMS]
    if kind == "project_summary":
        return [_summary_item(i) for i in rows[:1]]
    fields = FIELDS[kind]
    out = []
    for row in rows:
        kept = {k: _clip(row.get(k), TITLE_CHARS) for k in fields if row.get(k) not in (None, "", [])}
        if kept.get("route") or kind == "activity":
            out.append(kept)
    return out


def list_route(tool: str, args: dict, owner_id: str | None) -> str | None:
    """그 목록의 전체를 볼 화면 — 서버가 만든 앱 안 상대 경로. 같은 조건을 받는 화면이 없으면 None 이다."""
    if tool == "my_documents":
        if (args.get("view") or "authored") != "authored" or not owner_id:
            return None
        query = {"author": owner_id, "sort": args.get("sort") or "recent"}
        if args.get("query"):
            query["q"] = args["query"]
        return "/knowledge?" + urlencode(query)
    if tool == "search_documents":
        query = {"q": args.get("query") or ""}
        if args.get("mine") and owner_id:
            query["author"] = owner_id
        return "/knowledge?" + urlencode(query)
    if tool == "my_work":
        return "/my-tickets"
    if tool == "search_tickets":
        return "/unassigned" if args.get("scope") == "unassigned" else "/team-tickets"
    if tool == "search_projects":
        return "/projects"
    if tool == "my_approvals":
        return "/my-approvals"
    if tool == "my_notifications":
        return "/notifications"
    if tool == "my_activity":
        return "/activity"
    return None


def build(executions, *, owner_id: str | None) -> list[dict]:
    """한 차례의 블록 — 성공한 목록 · 현황 호출마다 하나, 부른 순서대로, 많아야 `MAX_BLOCKS`. 같은 호출이 두 번이면 하나다."""
    out: list[dict] = []
    seen: set[str] = set()
    for execution in executions:
        kind = KINDS.get(getattr(execution, "tool", ""))
        if kind is None or not getattr(execution, "ok", False):
            continue
        body = _envelope(execution)
        if body is None:
            continue
        args = dict(getattr(execution, "args", None) or {})
        shown = bool(args.pop("show", False))
        signature = json.dumps([execution.tool, args], ensure_ascii=False, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        items = _items(kind, body.get("items"))
        if not items and kind == "project_summary":
            continue
        block = {
            "id": f"r{len(out) + 1}",
            "tool": execution.tool,
            "kind": kind,
            "shown": shown,
            "args": args,
            "total": body.get("total"),
            "offset": int(body.get("offset") or 0),
            "returned": int(body.get("returned") or 0),
            "truncated": bool(body.get("truncated")),
            "items": items,
        }
        if execution.tool in SORT_OPTIONS:
            block["sort"] = args.get("sort") or SORT_OPTIONS[execution.tool][0]
            block["sort_options"] = list(SORT_OPTIONS[execution.tool])
        route = list_route(execution.tool, args, owner_id)
        if route:
            block["list_route"] = route
        out.append(block)
        if len(out) >= MAX_BLOCKS:
            break
    return out


def shown_keys(blocks) -> set[tuple[str, str]]:
    """보인 블록 항목의 (종류, id) — 출처에서 「보인 것」을 표시하고 참고 자료 판에서 겹침을 뺀다."""
    kind_to_type = {"document": "document", "ticket": "ticket", "project": "project", "approval": "approval",
                    "project_summary": "project"}
    out: set[tuple[str, str]] = set()
    for block in blocks or ():
        if not block.get("shown"):
            continue
        source_type = kind_to_type.get(block.get("kind"))
        if source_type is None:
            continue
        for item in block.get("items") or ():
            if item.get("ref"):
                out.add((source_type, str(item["ref"])))
            if block.get("kind") == "project_summary":
                # 카드 안에 선 끝낸 일 · 연결 문서도 화면에 보인 자료다.
                for row in item.get("recent_completed") or ():
                    if row.get("ref"):
                        out.add(("ticket", str(row["ref"])))
                for row in (item.get("documents") or {}).get("items") or ():
                    if row.get("ref"):
                        out.add(("document", str(row["ref"])))
    return out


# ── 이어지는 질문의 기억 ──────────────────────────────────────────────────────────────────────────────────────


def memory_entry(blocks, *, turn: int) -> list[dict]:
    """앞 차례 한 번의 블록을 기억 꼴로 — 도구 · 인자 · 수 · 쪽 · 항목 번호와 ref · 제목(60자) · 날짜 · 키."""
    out = []
    for block in blocks or ():
        items = []
        for n, item in enumerate(block.get("items") or (), start=1):
            entry = {"n": n + int(block.get("offset") or 0), "ref": item.get("ref"),
                     "title": _clip(item.get("title") or item.get("name"), MEMORY_TITLE_CHARS)}
            for key in ("key", "updated_at", "completed_at", "status"):
                if item.get(key):
                    entry[key] = item[key]
            items.append({k: v for k, v in entry.items() if v is not None})
        out.append({"turn": turn, "tool": block.get("tool"), "shown": bool(block.get("shown")),
                    "args": block.get("args") or {}, "total": block.get("total"), "offset": block.get("offset"),
                    "returned": block.get("returned"), "items": items})
    return out


def memory_text(entries: list[dict], *, limit: int = MEMORY_CHARS) -> str | None:
    """기억을 한 칸의 글로. 넘치면 오래된 차례 · 뒤 항목부터 덜어 낸다. 비면 None(싣지 않는다)."""
    entries = [dict(e, items=list(e.get("items") or [])) for e in entries]
    if not entries:
        return None
    while True:
        text = json.dumps(entries, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return text
        longest = max(entries, key=lambda e: len(e["items"]))
        if len(longest["items"]) > 3:
            longest["items"].pop()
        elif len(entries) > 1:
            entries.pop(0)
        else:
            return text[:limit]


# ── 첫 답의 의도 제목 ─────────────────────────────────────────────────────────────────────────────────────────

INTENT_TITLE_CHARS = 40
_MY_WORK_TITLES = {
    "assigned": "내 담당 티켓 조회",
    "requested": "내가 요청한 티켓 조회",
    "watching": "지켜보는 티켓 조회",
    "due_this_week": "이번 주 마감 티켓 조회",
    "overdue": "마감 지난 티켓 조회",
}
_APPROVAL_TITLES = {"todo": "결재할 문서 확인", "requested": "올린 결재 확인", "done": "결재한 문서 확인"}


def _name(value) -> str:
    """인자에서 온 이름 — 제어 문자 · 마크다운 기호를 걷고 공백 하나로, 20자까지."""
    text = "".join(" " if unicodedata.category(ch)[0] in ("C", "Z") else ch for ch in str(value or ""))
    text = " ".join(_NAME_STRIP.sub(" ", text).split())
    return _clip(text, 20) or ""


def intent_title(executions) -> str | None:
    """첫 답에서 쓴 도구와 검증된 인자로 짓는 제목 — 「내 담당 티켓 조회」 · 「SK하이닉스 프로젝트 현황」. 모델을 부르지 않는다.

    도구를 쓰지 않았거나 이름을 지을 수 없는 도구뿐이면 None 이다(첫 질문을 다듬은 제목을 그대로 둔다)."""
    for execution in executions:
        tool = getattr(execution, "tool", "")
        args = getattr(execution, "args", None) or {}
        query = _name(args.get("query"))
        if tool == "my_documents":
            base = "내가 고친 문서" if args.get("view") == "edited" else "내 문서"
            return _clip(f"{base} 중 {query} 검색" if query else f"{base} 조회", INTENT_TITLE_CHARS)
        if tool == "my_work":
            return _MY_WORK_TITLES.get(args.get("view"), "내 티켓 조회")
        if tool in ("project_activity", "get_project_summary") and _name(args.get("project")):
            return _clip(f"{_name(args.get('project'))} 프로젝트 현황", INTENT_TITLE_CHARS)
        if tool == "search_documents" and query:
            return _clip(f"{'내 문서 중 ' if args.get('mine') else ''}{query} 문서 검색", INTENT_TITLE_CHARS)
        if tool == "search_tickets":
            subject = _name(args.get("project")) or query
            return _clip(f"{subject} 티켓 검색" if subject else "팀 티켓 조회", INTENT_TITLE_CHARS)
        if tool == "search_projects":
            return "내 프로젝트 조회" if args.get("scope") == "mine" else (
                _clip(f"{query} 프로젝트 검색", INTENT_TITLE_CHARS) if query else "프로젝트 조회")
        if tool == "my_approvals":
            return _APPROVAL_TITLES.get(args.get("box"), "결재함 확인")
        if tool == "my_notifications":
            return "안 읽은 알림 확인" if args.get("unread_only") else "알림 확인"
        if tool == "my_activity":
            return "내 최근 활동"
        if tool == "sprint_meetings":
            return "스프린트 회의 결정"
    return None
