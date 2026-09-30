"""사용처의 지시문을 고르고, 발행할 지시문을 검사한다 (계획 3.8, D-518).

## 고르기

AI 런타임이 호출마다 `resolve(db, 사용처)` 를 부른다. 그 사용처에 발행한 프롬프트가 있으면 그 내용을, 없으면 기본 제공
지시문(`catalog.py`)을 쓴다. 한 번의 짧은 색인 조회라 따로 기억해 두지 않는다 - 발행한 순간부터 다음 호출이 새
지시문을 쓴다. 조회가 실패하거나 저장된 내용이 검사를 통과하지 못하면 기본 제공으로 돌아간다(답이 멈추는 쪽보다
낫다). 어느 쪽을 썼는지는 호출 기록에 남는다(`prompt_source`, `prompt_version`, `prompt_id`).

## 검사

발행할 지시문은 비어 있지 않고, 4,000자를 넘지 않고, 줄바꿈과 탭 말고는 제어 문자가 없고, 데이터 구분자의 모양
(`<<<CLOVI_DATA:` 등)을 담지 않아야 한다. 구분자 모양이 지시문에 있으면 데이터 블록의 경계가 흐려진다. 사용처는
정해져 있어야 하고 바꿀 수 있는 사용처여야 한다(연결 확인은 바꿀 수 없다).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts import catalog
from app.core.errors import ValidationAppError
from app.llm import prompt as frame

logger = logging.getLogger("app.ai.prompts")

SOURCE_BUILTIN = "builtin"
SOURCE_ADMIN = "admin"
MAX_INSTRUCTION_CHARS = 4000


@dataclass(frozen=True)
class ResolvedPrompt:
    """한 호출이 쓸 지시문과 그 출처."""

    slot: catalog.PromptSlot
    instruction: str
    source: str
    version: int | None = None
    prompt_id: str | None = None
    name: str | None = None


def builtin(slot_key: str) -> ResolvedPrompt:
    slot = catalog.get_slot(slot_key)
    return ResolvedPrompt(slot=slot, instruction=slot.instruction, source=SOURCE_BUILTIN)


def instruction_problems(text) -> list[str]:
    """발행할 수 없는 까닭. 비어 있으면 발행할 수 있다."""
    if not isinstance(text, str) or not text.strip():
        return ["지시문이 비어 있습니다."]
    found: list[str] = []
    if len(text) > MAX_INSTRUCTION_CHARS:
        found.append(f"지시문은 {MAX_INSTRUCTION_CHARS:,}자를 넘을 수 없습니다.")
    if any(not (c in "\n\t" or c.isprintable()) for c in text):
        found.append("지시문에 줄바꿈과 탭 말고는 제어 문자를 쓸 수 없습니다.")
    if frame.contains_marker(text):
        found.append("지시문에 데이터 구분자의 모양을 쓸 수 없습니다.")
    return found


def slot_problem(slot_key) -> str | None:
    """사용처 값이 틀린 까닭. 비어 있는 값은 여기서 막지 않는다(초안은 사용처 없이 둘 수 있다)."""
    if slot_key is None or slot_key == "":
        return None
    slot = catalog.SLOTS.get(slot_key)
    if slot is None:
        return "알 수 없는 사용처입니다."
    if not slot.editable:
        return f"{slot.label} 지시문은 바꿀 수 없습니다."
    return None


def validate_for_publish(slot_key, content) -> None:
    """발행 직전 검사. 틀리면 422 로 까닭을 말한다."""
    if not slot_key:
        raise ValidationAppError("발행하려면 사용처를 먼저 고르세요.")
    problem = slot_problem(slot_key)
    if problem:
        raise ValidationAppError(problem)
    found = instruction_problems(content)
    if found:
        raise ValidationAppError(found[0])


def resolve(db: Session | None, slot_key: str) -> ResolvedPrompt:
    """이 사용처가 지금 쓸 지시문. 예외를 올리지 않는다."""
    slot = catalog.get_slot(slot_key)
    if db is None or not slot.editable:
        return builtin(slot_key)
    from app.prompts.models import STATUS_PUBLISHED, Prompt

    try:
        row = db.execute(
            select(Prompt).where(Prompt.slot == slot_key, Prompt.status == STATUS_PUBLISHED).limit(1)
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001 - 지시문을 못 읽어도 답은 나가야 한다
        logger.exception("사용처 %s 의 발행본을 읽지 못해 기본 제공 지시문을 쓴다", slot_key)
        return builtin(slot_key)
    if row is None:
        return builtin(slot_key)
    if instruction_problems(row.content):
        # 발행 검사를 지난 내용만 발행된다. 여기 닿았다면 손으로 고친 행이다 - 조용히 쓰지 않는다.
        logger.warning("사용처 %s 의 발행본(%s v%s)이 검사를 통과하지 못해 기본 제공 지시문을 쓴다",
                       slot_key, row.name, row.version)
        return builtin(slot_key)
    return ResolvedPrompt(slot=slot, instruction=row.content.strip(), source=SOURCE_ADMIN, version=row.version,
                          prompt_id=row.id, name=row.name)
