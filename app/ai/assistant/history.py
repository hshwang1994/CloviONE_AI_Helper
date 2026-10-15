"""지난 문답과 화면 대상 (D-535).

## 지난 문답

이 차례 앞의 **완결 쌍**(사람 메시지 + 그 답)만 싣는다 - 실패한 사람 메시지, 안내 메시지(`error_notice`), 지운 메시지는
뺀다. 제공자는 차례가 번갈아야 받는다(Anthropic). 최근 여섯 쌍까지, 한쪽 글은 1,200자, 합계 6,000자까지이고 넘으면 오래된
쌍부터 버린다. 개인정보 가리기는 런타임이 정책대로 건다(`AiRuntime.converse`).

## 화면 대상

서랍이 보낸 화면 문맥(`{kind, ref, label}`)은 사용자가 고칠 수 있는 값이다. 그래서 서버가 **대화 주인의 권한으로 다시
읽은** 대상만 싣는다 - 같은 도구 함수(`get_ticket` · `get_project_summary` · `get_document`)를 같은 READ ONLY
트랜잭션으로 부른다. 못 읽으면(없거나 범위 밖) 아무것도 싣지 않는다.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

HISTORY_PAIRS = 6
SIDE_CHARS = 1200
HISTORY_CHARS = 6000

SCREEN_KINDS = ("ticket", "project", "document")
_REF = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _payload(message) -> dict:
    raw = message.structured_payload_json
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def recent_pairs(db: Session, *, conversation_id: str, before_seq: int, pairs: int = HISTORY_PAIRS,
                 side_chars: int = SIDE_CHARS, total_chars: int = HISTORY_CHARS) -> tuple[tuple[str, str], ...]:
    """(사람, 도우미) 완결 쌍 - 오래된 것부터."""
    from app.conversations.models import PROC_DONE, ROLE_ASSISTANT_MSG, ROLE_USER_MSG, Message

    rows = db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id, Message.deleted_at.is_(None), Message.seq < before_seq,
        ).order_by(Message.seq.desc()).limit(pairs * 6)
    ).scalars().all()
    rows = list(reversed(rows))
    answers: dict[str, str] = {}
    for row in rows:
        if row.role != ROLE_ASSISTANT_MSG or not row.message_id.startswith("a-") or "-fail-" in row.message_id:
            continue
        if _payload(row).get("error_notice"):
            continue
        # `a-{사람 메시지 id}-{잡 id}` - 잡 id 는 하이픈이 든 uuid 라 앞쪽 id 를 뒤에서 자르지 않고 앞에서 맞춘다.
        answers.setdefault(row.message_id, row.content or "")
    out: list[tuple[str, str]] = []
    for row in rows:
        if row.role != ROLE_USER_MSG or row.processing_status != PROC_DONE or not (row.content or "").strip():
            continue
        prefix = f"a-{row.message_id}-"
        # 사람 메시지 id 에도 하이픈이 들 수 있다 - 뒤가 정확히 잡 id(36자)인 것만 그 답이다.
        reply = next((text for key, text in answers.items()
                      if key.startswith(prefix) and len(key) == len(prefix) + 36), None)
        if reply and reply.strip():
            out.append((row.content.strip()[:side_chars], reply.strip()[:side_chars]))
    out = out[-pairs:]
    while out and sum(len(q) + len(a) for q, a in out) > total_chars:
        out.pop(0)
    return tuple(out)


def recent_results(db: Session, *, conversation_id: str, before_seq: int) -> str | None:
    """앞 차례들(많아야 `blocks.MEMORY_TURNS`)이 쓴 목록 · 현황 도구와 보인 목록 — 이어지는 질문의 기억(한 칸의 JSON 글).

    지난 문답은 글자만 가서(`recent_pairs`) 「다음 10개」 「그중 VMware」 「첫 번째 문서」가 무엇을 가리키는지 모델이 글에서
    추측해야 했다. 블록(도구 · 검증한 인자 · total · offset · 항목 번호 · ref · 제목)을 그대로 실어 그 추측을 없앤다. 제목은 남이 쓴
    글이라 **데이터 칸**으로 간다(런타임이 가리고 난스 칸에 넣는다). 실패 · 안내 · 지운 답은 뺀다. 블록이 없으면 None 이다."""
    from app.ai.assistant import blocks
    from app.conversations.models import ROLE_ASSISTANT_MSG, Message

    rows = db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id, Message.deleted_at.is_(None), Message.seq < before_seq,
            Message.role == ROLE_ASSISTANT_MSG,
        ).order_by(Message.seq.desc()).limit(blocks.MEMORY_TURNS * 4)
    ).scalars().all()
    entries: list[dict] = []
    turns = 0
    for row in rows:
        if not row.message_id.startswith("a-") or "-fail-" in row.message_id:
            continue
        payload = _payload(row)
        found = [b for b in payload.get("results") or [] if isinstance(b, dict)]
        if payload.get("error_notice") or not found:
            continue
        turns += 1
        entries = blocks.memory_entry(found, turn=-turns) + entries
        if turns >= blocks.MEMORY_TURNS:
            break
    return blocks.memory_text(entries)


def screen_target(raw) -> dict | None:
    """화면 문맥의 모양만 본다. 옛 문자열(화면 이름)은 받고 버린다 - 대상이 없다."""
    if not isinstance(raw, dict):
        return None
    kind, ref = raw.get("kind"), raw.get("ref")
    if kind not in SCREEN_KINDS or not isinstance(ref, str) or not _REF.match(ref):
        return None
    label = raw.get("label") if isinstance(raw.get("label"), str) else ""
    return {"kind": kind, "ref": ref, "label": label[:40]}
