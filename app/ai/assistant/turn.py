"""AI 도우미 한 차례 — 준비 → `AiRuntime.converse` → 도우미 메시지의 글과 구조 (D-535 · D-537 · D-538).

준비는 셋이다: 권한과 기능 플래그로 거른 도구, 지난 완결 문답, 화면 대상(서버가 대화 주인의 권한으로 다시 읽은 것).
문맥 줄(오늘 날짜, 묻는 사람, 화면 길잡이)은 시스템 쪽에 실린다. 제공자를 부르고 도구를 돌리는 일은 런타임이 한다.

## 도우미 메시지의 구조

    {kind: "assistant", status, mode, sources[{type, id, title, route, where?, status?, key?}],
     tools[{name, label, ok, count, total, query?}], rounds, elapsed_ms, truncated, notice, model}

출처는 서버가 모은다(경로가 있는 항목만, 많아야 30개, 중복 없이). **답에 인용된 것이 먼저다**(D-569) — 답의 글에 그 경로 ·
id · 티켓 키가 있으면 앞으로, 나머지는 도구를 부른 순서다. 화면은 이 순서대로 그리고, 답 안의 링크는 이 목록의 경로와 같을
때만 링크가 된다. 사람은 출처가 아니다. ``tools[].total`` 은 목록 도구가 센 권한 안의 전체 수(못 셌거나 단건 도구면 null)이고
``count`` 는 돌려준 수다 — 화면의 「N건 중 M건」이 이 둘이다. ``notice`` 는 화면이 다르게 그릴
사실이다 - ``no_results``(도구가 아무것도 찾지 못했다, 정상 답이다), ``closed_without_answer``(찾은 자료로 닫았다).
「AI 를 쓸 수 없음」은 여기 오지 않는다 - 요청 자체가 409 다(채팅 라우터).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.assistant import catalog, history

MAX_SOURCES = 30
NOTICE_NO_RESULTS = "no_results"
NOTICE_CLOSED = "closed_without_answer"
#: 「찾았는데 없었다」를 말할 수 있는 도구 — 목록을 돌려주는 도구다. 하나라도 결과가 있으면 「찾지 못함」이 아니다.
_SEARCH_TOOLS = frozenset({"search_documents", "search_workspace", "search_tickets", "search_projects",
                           "find_people", "recent_changes", "my_work", "my_approvals", "search",
                           "my_documents", "my_notifications", "my_activity", "sprint_meetings"})
_WEEKDAYS = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")

#: 화면 길잡이 - 도우미가 쓰기 대신 안내할 경로. 화면이 이 경로를 앱 안 링크로 그린다.
ROUTE_GUIDE = (
    "화면 길잡이: 새 티켓은 /new-ticket, 내 티켓은 /my-tickets, 내 결재함은 /my-approvals, "
    "사내 문서는 /knowledge, 프로젝트는 /projects, 알림은 /notifications, 회차 회의는 /sprint 에서 다룹니다."
)


@dataclass(frozen=True)
class TurnReply:
    outcome: object
    text: str
    structured: dict

    @property
    def ok(self) -> bool:
        return bool(self.outcome.ok)


def context_lines(owner, *, today) -> tuple[str, ...]:
    """시스템 쪽 문맥 줄. 이름과 부서는 표시용이다(권한 판정에 쓰지 않는다)."""
    when = f"오늘은 {today.year}년 {today.month}월 {today.day}일 {_WEEKDAYS[today.weekday()]}입니다(한국 시간)."
    who = getattr(owner, "display_name", None) or "사용자"
    department = getattr(owner, "department", None)
    asker = f"묻는 사람은 {who}({department})입니다." if department else f"묻는 사람은 {who}입니다."
    return (when, asker, ROUTE_GUIDE)


def _screen_preload(target: dict | None, *, allowed: dict, env: catalog.ToolEnv):
    """화면 대상을 대화 주인의 권한으로 다시 읽는다. 못 읽으면 None - 화면이 보낸 값을 그대로 믿지 않는다."""
    if target is None:
        return None
    plan = {
        "ticket": ("get_ticket", catalog.TicketArgs, {"key": target["ref"]}),
        "project": ("get_project_summary", catalog.ProjectArgs, {"project": target["ref"]}),
        "document": ("get_document", catalog.DocumentArgs, {"ref": target["ref"]}),
    }[target["kind"]]
    tool = catalog.TOOLS[plan[0]]
    if plan[0] not in allowed:
        return None
    execution = catalog.run(tool, plan[1].model_validate(plan[2]), env)
    return execution if execution.ok else None


_KEY_SHAPE = re.compile(r"^[A-Za-z0-9-]{3,40}$")


#: 제목으로 인용을 알아보는 최소 길이 — 「회의록」 같은 짧은 제목은 답의 다른 말과 겹치므로 세지 않는다.
CITED_TITLE_MIN = 5


def _cited(source: dict, text: str) -> bool:
    """이 출처가 답의 글에 인용됐는가 — 경로(`?block=` 앞까지) · id · 티켓 키 · 결재 경로 · 다섯 글자 이상의 제목 중 하나가 글에 있다."""
    if not text:
        return False
    title = str(source.get("title") or "").strip()
    if len(title) >= CITED_TITLE_MIN and title in text:
        return True
    route = str(source.get("route") or "")
    base = route.split("?block=", 1)[0]
    if base and base in text:
        return True
    ident = str(source.get("id") or "")
    if len(ident) >= 8 and ident in text:
        return True
    key = source.get("key")
    if isinstance(key, str) and _KEY_SHAPE.match(key):
        if re.search(r"(?<![A-Za-z0-9-])" + re.escape(key) + r"(?![A-Za-z0-9-])", text):
            return True
    return False


def _sources(executions, text: str = "") -> list[dict]:
    """도구가 돌려준 출처를 모은다 — 경로가 있는 것만, 중복 없이, **답에 인용된 것 먼저**, 많아야 `MAX_SOURCES` 개.

    출처마다 `cited` 를 싣는다. 하나도 인용되지 않은 답(찾지 못함 · 뜻만 가까운 문서)은 화면이 「참고한 자료」가 아니라 접힌 「찾아본
    자료」로 보인다(P-133)."""
    out: list[dict] = []
    seen: set = set()
    for execution in executions:
        for source in getattr(execution, "sources", ()) or ():
            key = (source.get("type"), source.get("id"))
            if not source.get("route") or key in seen:
                continue
            seen.add(key)
            out.append({k: v for k, v in source.items() if v is not None})
    for source in out:
        source["cited"] = _cited(source, text)
    cited = [s for s in out if s["cited"]]
    rest = [s for s in out if not s["cited"]]
    return (cited + rest)[:MAX_SOURCES]


def _tools(executions) -> list[dict]:
    out = []
    for execution in executions:
        tool = catalog.TOOLS.get(execution.tool)
        label = tool.label if tool else "사내 자료 검색"
        # 전체 수는 목록 도구만 싣는다 — 단건 도구(티켓 보기 · 문서 읽기 · 진행 현황)의 「1건」은 화면에 뜻이 없다.
        total = getattr(execution, "total", None) if execution.tool in _SEARCH_TOOLS else None
        entry = {"name": execution.tool, "label": label, "ok": bool(execution.ok), "count": int(execution.count),
                 "total": total}
        if execution.query:
            entry["query"] = execution.query
        out.append(entry)
    return out


def _notice(outcome) -> str | None:
    if getattr(outcome, "closed_without_answer", False):
        return NOTICE_CLOSED
    searched = [e for e in outcome.executions if e.tool in _SEARCH_TOOLS and e.ok]
    if searched and all(e.count == 0 for e in searched) and not any(
        e.ok and e.count for e in outcome.executions if e.tool not in _SEARCH_TOOLS
    ):
        return NOTICE_NO_RESULTS
    return None


def run(db: Session, *, owner, user_message, conversation_id: str, runtime, env: catalog.ToolEnv, screen_context,
        today, job_id: str | None = None, progress=None) -> TurnReply:
    """한 차례를 돌린다. 예외를 올리지 않는 런타임 위에 서 있다 - 실패는 `outcome.status` 로 온다."""
    from app.ai.actions import ASSISTANT_CHAT
    from app.ai.runtime import TurnInput
    from app.authz.service import has_permission

    allowed = {tool.name: tool for tool in catalog.available_tools(
        can=lambda key: has_permission(db, owner, key), flag=env.flag,
    )}
    pairs = history.recent_pairs(db, conversation_id=conversation_id, before_seq=user_message.seq)
    preload = _screen_preload(history.screen_target(screen_context), allowed=allowed, env=env)
    question = user_message.content or ""
    turn = TurnInput(
        user_text=question,
        history=pairs,
        context_lines=context_lines(owner, today=today),
        preload=preload.content if preload is not None else None,
        tools=tuple(tool.spec() for tool in allowed.values()),
        execute=lambda call: catalog.execute(call, allowed=allowed, env=env, progress=progress),
        fallback=lambda: catalog.fallback_search(question, allowed=allowed, env=env),
        progress=progress,
    )
    outcome = runtime.converse(db, action_key=ASSISTANT_CHAT, actor=owner, turn=turn, job_id=job_id)
    executions = ([preload] if preload is not None else []) + list(outcome.executions)
    structured = {
        "kind": "assistant",
        "status": outcome.status,
        "mode": outcome.mode,
        "sources": _sources(executions, outcome.text or ""),
        "tools": _tools(outcome.executions),
        "rounds": outcome.rounds,
        "elapsed_ms": outcome.latency_ms,
        "truncated": bool(outcome.truncated),
        "notice": _notice(outcome) if outcome.ok else None,
        "model": outcome.model or None,
    }
    if preload is not None:
        structured["screen"] = {"kind": history.screen_target(screen_context)["kind"]}
    return TurnReply(outcome=outcome, text=outcome.text or "", structured=structured)


def progress_writer(db: Session, message, *, clock):
    """사용자 메시지의 진행 문구를 적고 **커밋한다** - 화면이 「처리 중」과 지금 하는 일을 본다(D-535).

    도구 사이에서 불린다. 그때 이 세션은 읽기만 했고(설정 · 지시문 · 정책) 잠근 것이 없다.
    """
    def write(label: str) -> None:
        try:
            current = json.loads(message.structured_payload_json) if message.structured_payload_json else {}
        except (TypeError, ValueError):
            current = {}
        if not isinstance(current, dict):
            current = {}
        now: datetime = clock.now()
        current["progress"] = {"label": label, "at": now.isoformat()}
        message.structured_payload_json = json.dumps(current, ensure_ascii=False)
        db.commit()

    return write
