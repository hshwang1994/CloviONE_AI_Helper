"""AI 기능마다 한 줄 — 프롬프트 화면의 정본 모양 (계획 A4, D-541).

관리자는 「행(버전)」이 아니라 「기능」으로 생각한다: 이 기능이 지금 어떤 지시문을 쓰는가, 고치는 중인 초안이 있는가,
최근에 실제로 쓰였는가. 그래서 화면은 사용처(기능)마다 한 줄이고, 행을 열면 지금 지시문 · 고정 틀 · 초안 · 버전 기록이
한 서랍에 있다. 연결 확인 사용처는 고칠 수 없는 관리 동작이라 목록에 없다. 은퇴한 사용처(질문 답변)도 없다.

## 상태 낱말

- 지시문의 생명주기는 **초안 · 적용 중 · 보관** 셋이다(정책과 같은 어휘, D-541). 「사용 중」은 발행 여부만 말했고 실제 호출과
  무관했다 — 30일 호출 0 인 「사용 중」이 생겼다.
- 기능 상태는 **켜짐 · 꺼짐 · AI 미연결** 이다. 「최근 30일 요청 0」의 까닭을 이 칸이 말한다(꺼진 기능은 요청이 없다).

## 쓰기는 기능 단위다

`PATCH /features/{slot}` 은 그 기능의 초안을 고친다 - 초안이 없으면 지금 지시문을 복사해 만든다. 발행 · 버리기 · 기본 제공으로
되돌리기도 기능 단위다. 버전의 이름은 그 기능의 발행본 이름을 잇는다(없으면 「{기능} 지시문」) - 그래야 버전 기록과 되돌리기가
한 줄기로 이어진다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts import catalog
from app.prompts.models import STATUS_DRAFT, STATUS_PUBLISHED, Prompt

#: 기능 → 그 기능을 켜고 끄는 설정 키. 문서 초안 · 주간 요약은 AI 사용(`ai_generation_enabled`) 하나에 기댄다.
FEATURE_FLAGS: dict[str, str] = {
    catalog.ASSISTANT: "chat_enabled",
    catalog.NARRATIVE: "assistant_narrative_enabled",
    catalog.QUIZ: "game_ai_enabled",
}
STATE_ON, STATE_OFF, STATE_AI_UNAVAILABLE = "on", "off", "ai_unavailable"
STATE_LABELS = {STATE_ON: "켜짐", STATE_OFF: "비활성화", STATE_AI_UNAVAILABLE: "AI 미연결"}
LIFECYCLE_LABELS = {"draft": "초안", "published": "적용 중", "archived": "보관"}


def feature_slots() -> tuple[catalog.PromptSlot, ...]:
    """화면의 줄 - 고칠 수 있고 은퇴하지 않은 사용처."""
    return tuple(slot for slot in catalog.live_slots() if slot.editable)


def feature_state(slot_key: str, *, values: dict, runtime_info: dict | None) -> tuple[str, str | None]:
    """기능 상태와 까닭 한 문장. AI 사용이 꺼졌거나 연결이 막혔으면 어떤 기능도 답을 만들지 않는다."""
    info = runtime_info or {}
    if not info.get("generation_enabled"):
        return STATE_OFF, "AI 사용이 비활성화되어 있어 이 기능이 답을 만들지 않습니다."
    if info.get("blocking"):
        return STATE_AI_UNAVAILABLE, "AI 연결을 쓸 수 없어 이 기능이 답을 만들지 않습니다."
    flag = FEATURE_FLAGS.get(slot_key)
    if flag and values.get(flag) is not True:
        return STATE_OFF, "이 기능이 비활성화되어 있어 요청이 없습니다."
    return STATE_ON, None


def published_row(db: Session, slot_key: str) -> Prompt | None:
    return db.execute(
        select(Prompt).where(Prompt.slot == slot_key, Prompt.status == STATUS_PUBLISHED).limit(1)
    ).scalar_one_or_none()


def draft_row(db: Session, slot_key: str) -> Prompt | None:
    """그 기능의 초안 - 가장 새 것 하나(초안이 여럿 남은 옛 데이터에서도 화면은 하나를 고친다)."""
    return db.execute(
        select(Prompt).where(Prompt.slot == slot_key, Prompt.status == STATUS_DRAFT)
        .order_by(Prompt.created_at.desc(), Prompt.version.desc()).limit(1)
    ).scalar_one_or_none()


def version_name(slot: catalog.PromptSlot, published: Prompt | None) -> str:
    """새 초안의 이름 - 발행본의 이름을 잇는다. 그래야 버전 기록과 되돌리기가 한 줄기다."""
    return published.name if published is not None else f"{slot.label} 지시문"


def _rate(calls: int, errors: int) -> int | None:
    """실패율(정수 백분율). 반올림은 사용 통계와 같은 한 곳(`usage.percent`)에서 한다. 요청이 없으면 모른다(None)."""
    from app.ai.usage import percent

    return percent(errors, calls)


def item(slot: catalog.PromptSlot, *, published: Prompt | None, draft: Prompt | None, usage: dict | None,
         values: dict, runtime_info: dict | None, names: dict) -> dict:
    """기능 한 줄. 서랍도 같은 값을 쓴다."""
    state, note = feature_state(slot.key, values=values, runtime_info=runtime_info)
    usage = usage or {}
    calls = int(usage.get("calls", 0))
    errors = int(usage.get("errors", 0))
    if published is not None:
        current = {
            "source": "admin", "id": published.id, "name": published.name, "version": published.version,
            "instruction": published.content, "label": f"관리자 작성 v{published.version}",
            "published_at": published.published_at.isoformat() if published.published_at else None,
        }
    else:
        current = {"source": "builtin", "id": None, "name": None, "version": None, "instruction": slot.instruction,
                   "label": "기본 제공", "published_at": None}
    draft_view = None
    if draft is not None:
        creator = names.get(draft.created_by, {}) if draft.created_by else {}
        draft_view = {
            "id": draft.id, "name": draft.name, "version": draft.version, "content": draft.content,
            "label": f"v{draft.version} 초안",
            "updated_at": (getattr(draft, "updated_at", None) or draft.created_at).isoformat(),
            "created_by_name": creator.get("display_name") or creator.get("email"),
        }
    return {
        "id": slot.key,
        "slot": slot.key,
        "label": slot.label,
        "description": slot.description,
        "feature_state": state,
        "feature_state_label": STATE_LABELS[state],
        "feature_note": note,
        "current": current,
        "draft": draft_view,
        # 「지시문 고치기」 칸의 처음 값 - 초안이 있으면 초안, 없으면 지금 지시문에서 시작한다.
        "content": draft.content if draft is not None else current["instruction"],
        "frame": {"role": slot.role, "format_line": slot.format_line, "grounding": slot.grounding},
        "calls_30d": calls,
        "errors_30d": errors,
        "failure_rate": _rate(calls, errors),
        "last_used_at": usage.get("last_at"),
    }


def build_items(db: Session, *, since: datetime, values: dict, runtime_info: dict | None, names_of) -> list[dict]:
    from app.ai import usage as usage_mod

    usage = usage_mod.slot_usage(db, since=since)
    slots = feature_slots()
    published = {slot.key: published_row(db, slot.key) for slot in slots}
    drafts = {slot.key: draft_row(db, slot.key) for slot in slots}
    names = names_of({d.created_by for d in drafts.values() if d is not None})
    return [
        item(slot, published=published[slot.key], draft=drafts[slot.key], usage=usage.get(slot.key), values=values,
             runtime_info=runtime_info, names=names)
        for slot in slots
    ]


def resolve_key(db: Session, key: str) -> str | None:
    """서랍을 여는 주소의 값 → 기능 키. 기능 키, `builtin:<기능>`, 그 기능의 버전 id 를 다 받는다(옛 딥링크)."""
    if key.startswith("builtin:"):
        key = key[len("builtin:"):]
    slot = catalog.SLOTS.get(key)
    if slot is not None:
        return key if slot in feature_slots() else None
    row = db.get(Prompt, key)
    if row is not None and row.slot and catalog.SLOTS.get(row.slot) in feature_slots():
        return row.slot
    return None
