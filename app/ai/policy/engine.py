"""AI 요청에 적용할 정책을 고르고 적용한다 (계획 3.9, D-519).

## 한 요청에는 종류마다 한 정책만 답한다

  1. 이 액션을 이름으로 지정한 발행본
  2. 없으면 `*`(모든 기능) 발행본
  3. 없으면 코드 기본값(아무 정책도 걸리지 않음)

병합하지 않는다 - 「더 엄격한 값」을 섞으면 채팅용 `*` 정책이 초안의 한도를 몰래 낮추거나, 기능을 지정한 정책이
기본값보다 느슨해지지 못한다. 대신 **발행할 때** 겹침을 막는다: 같은 종류에서 같은 기능을 지정한 발행본이 이미
있거나, `*` 발행본이 이미 있으면 409 와 겹치는 정책 이름을 준다(`overlaps`). 그래서 1과 2는 언제나 하나씩이다.

## 어디서 적용하는가

  개인정보 가리기   AI 런타임이 제공자에 보내기 전의 입력(질문과 검색된 문맥)과 받은 출력(`app/ai/runtime.py`)
  응답 제한         AI 런타임이 받은 출력 - 제품 밖 링크를 누를 수 없게 하고 액션의 글자 상한 안에서 더 줄인다
  쓰기 승인         결과를 저장하는 자리(작업 공간 초안 저장, `app/ai/router.py`) - 저장 대신 승인 요청을 만든다

적용된 정책의 id 는 호출 기록에 남는다(`ai_usage_records.policy_ids_json`). 연결 확인에는 어느 정책도 걸리지 않는다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.policy import masking
from app.ai.policy.schemas import (
    ALL_ACTIONS,
    KIND_APPROVAL,
    KIND_CONTENT,
    KIND_DATA_PROTECTION,
    KINDS,
)

logger = logging.getLogger("app.ai.policy")


@dataclass(frozen=True)
class ResolvedPolicy:
    id: str
    name: str
    version: int
    kind: str
    rules: dict


@dataclass(frozen=True)
class PolicySet:
    """한 액션에 지금 걸리는 정책들. 종류마다 하나이거나 없다."""

    approval: ResolvedPolicy | None = None
    data_protection: ResolvedPolicy | None = None
    content: ResolvedPolicy | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def ids(self) -> list[str]:
        """호출 기록에 남길 정책 - 이 호출에 **실제로 걸린** 것(D-542). 승인 정책은 빠진다: 승인은 호출이 아니라 결과를
        저장하는 길에 걸리고, 이 사람에게 승인이 필요할 때만 부른 쪽이 `extra_policy_ids` 로 더한다. 예전에는 초안을 만들
        때마다 승인 정책 id 가 실려 「최근 30일 적용」이 부풀었다."""
        return [p.id for p in (self.data_protection, self.content) if p is not None]

    def mask(self, text: str) -> str:
        """개인정보 가리기(입력과 출력에 똑같이 쓴다)."""
        rules = self.data_protection.rules if self.data_protection else None
        if not rules:
            return text
        masked, _ = masking.mask(
            text, emails=rules.get("mask_emails", False), phones=rules.get("mask_phone_numbers", False),
            rrns=rules.get("mask_resident_registration_numbers", False),
        )
        return masked

    def limit_links(self, text: str, *, allowed_hosts: set[str]) -> str:
        rules = self.content.rules if self.content else None
        if not rules or not rules.get("block_external_links"):
            return text
        neutral, _ = masking.neutralize_links(text, allowed_hosts=allowed_hosts)
        return neutral

    def output_cap(self, action_cap: int) -> int:
        """출력 글자 수 상한 - 액션의 코드 상한보다 커지지 않는다."""
        rules = self.content.rules if self.content else None
        limit = rules.get("max_output_chars") if rules else None
        return min(action_cap, limit) if limit else action_cap


NONE = PolicySet()


def _applies(policy_applies_to: list[str], action_key: str) -> tuple[bool, bool]:
    """(이 액션을 지정했는가, `*` 인가)."""
    return action_key in policy_applies_to, ALL_ACTIONS in policy_applies_to


def _targets(row) -> list[str]:
    try:
        value = json.loads(row.applies_to_json or "[]")
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _rules(row) -> dict:
    try:
        value = json.loads(row.content_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def resolve(db: Session | None, action_key: str) -> PolicySet:
    """이 액션에 지금 걸리는 정책. 읽지 못하면 아무것도 걸지 않고 로그를 남긴다 - 답이 멈추는 쪽보다 낫다."""
    from app.ai.actions import CONNECTION_TEST

    if db is None or action_key == CONNECTION_TEST:
        return NONE
    from app.prompts.models import STATUS_PUBLISHED, Policy

    try:
        rows = db.execute(
            select(Policy).where(Policy.status == STATUS_PUBLISHED, Policy.kind.in_(KINDS))
            .order_by(Policy.published_at.desc(), Policy.id)
        ).scalars().all()
    except Exception:  # noqa: BLE001
        logger.exception("AI 정책을 읽지 못해 이번 호출에는 정책을 걸지 않는다")
        return NONE
    chosen: dict[str, ResolvedPolicy] = {}
    for kind in KINDS:
        specific = wildcard = None
        for row in rows:
            if row.kind != kind:
                continue
            named, star = _applies(_targets(row), action_key)
            if named and specific is None:
                specific = row
            elif star and wildcard is None:
                wildcard = row
        row = specific or wildcard
        if row is not None:
            chosen[kind] = ResolvedPolicy(id=row.id, name=row.name, version=row.version, kind=kind,
                                          rules=_rules(row))
    return PolicySet(approval=chosen.get(KIND_APPROVAL), data_protection=chosen.get(KIND_DATA_PROTECTION),
                     content=chosen.get(KIND_CONTENT))


def overlaps(db: Session, *, kind: str, applies_to: list[str], name: str) -> list[str]:
    """이 종류와 적용 대상으로 발행하면 겹치는 발행본의 이름. 같은 이름(옛 버전)은 발행하면 보관되므로 세지 않는다."""
    from app.prompts.models import STATUS_PUBLISHED, Policy

    rows = db.execute(
        select(Policy).where(Policy.status == STATUS_PUBLISHED, Policy.kind == kind, Policy.name != name)
    ).scalars().all()
    wanted = set(applies_to)
    clash = []
    for row in rows:
        theirs = set(_targets(row))
        both_star = ALL_ACTIONS in wanted and ALL_ACTIONS in theirs
        same_action = bool((wanted - {ALL_ACTIONS}) & (theirs - {ALL_ACTIONS}))
        if both_star or same_action:
            clash.append(row.name)
    return sorted(set(clash))


def approval_needed(db: Session, *, action_key: str, user) -> ResolvedPolicy | None:
    """이 사람이 이 액션의 결과를 저장하려면 승인이 필요한가. 필요하면 그 정책을 돌려준다."""
    policy = resolve(db, action_key).approval
    if policy is None or not policy.rules.get("write_requires_approval", True):
        return None
    if getattr(user, "role", None) in (policy.rules.get("auto_approve_roles") or []):
        return None
    return policy


def check_publishable(db: Session, row) -> None:
    """정책 한 버전을 발행해도 되는가. 틀리면 422(형식) 또는 409(겹침)로 까닭을 말한다."""
    from app.ai.policy.schemas import KIND_LEGACY, normalize_applies_to, normalize_rules
    from app.core.errors import ConflictError, ValidationAppError

    if row.kind == KIND_LEGACY or row.kind not in KINDS:
        raise ValidationAppError("옛 형식의 정책은 발행할 수 없습니다. 새 정책을 만들어 규칙을 옮기세요.")
    normalize_rules(row.kind, _rules(row))
    targets = normalize_applies_to(row.kind, _targets(row))
    clash = overlaps(db, kind=row.kind, applies_to=targets, name=row.name)
    if clash:
        raise ConflictError(
            "같은 기능에 같은 종류의 정책이 이미 발행돼 있습니다: " + ", ".join(clash)
            + ". 그 정책을 보관하거나 적용 대상을 바꾸세요."
        )
