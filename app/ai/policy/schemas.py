"""AI 정책의 종류와 규칙 (계획 3.9, D-519).

## 종류 셋

  approval         쓰기 작업 승인. 결과가 저장되는 액션(지금은 작업 공간의 문서 초안)을 저장 전에 승인에 올린다
  data_protection  개인정보 가리기. 제공자에 보내기 전의 입력과 받은 출력에서 이메일, 전화번호, 주민등록번호를 가린다
  content          응답 제한. 출력 글자 수를 줄이고 제품 밖 링크를 누를 수 없게 바꾼다

`legacy` 는 새로 만들 수 없는 종류다. 0041 이 옛 시드 정책의 원본을 이 종류로 보관했다 - 이력으로만 남는다.

## 규칙은 스키마로 검사한다

예전에는 정책 내용이 자유 JSON 이었고 아무것도 그것을 읽지 않았다. 이제 종류마다 규칙 칸이 정해져 있고, 모르는 칸은
거절한다(`extra="forbid"`). 발행되지 않은 정책은 적용되지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.authz import ROLE_AUDITOR, ROLE_ORDER
from app.core.errors import ValidationAppError

KIND_APPROVAL = "approval"
KIND_DATA_PROTECTION = "data_protection"
KIND_CONTENT = "content"
KIND_LEGACY = "legacy"
KINDS = (KIND_APPROVAL, KIND_DATA_PROTECTION, KIND_CONTENT)
KIND_LABELS = {
    KIND_APPROVAL: "쓰기 승인",
    KIND_DATA_PROTECTION: "개인정보 가리기",
    KIND_CONTENT: "응답 제한",
    KIND_LEGACY: "옛 형식",
}

ALL_ACTIONS = "*"
# 응답 제한의 글자 수 바닥. 이보다 짧으면 어떤 기능도 쓸 만한 답을 못 낸다.
MIN_OUTPUT_CHARS = 100

# 승인 없이 저장할 수 있는 역할로 고를 수 있는 값이다. 감사자는 쓰기를 하지 않으므로 빼고, 높은 역할부터 적는다.
# 역할 이름은 authz 의 순서표에서 가져온다(사본을 만들지 않는다).
APPROVABLE_ROLES = tuple(role for role in reversed(ROLE_ORDER) if role != ROLE_AUDITOR)


class _Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalRules(_Rules):
    write_requires_approval: bool = True
    auto_approve_roles: list[str] = Field(default_factory=list)

    @field_validator("auto_approve_roles")
    @classmethod
    def _roles(cls, value: list[str]) -> list[str]:
        unknown = [r for r in value if r not in APPROVABLE_ROLES]
        if unknown:
            raise ValueError("승인 없이 저장할 수 있는 역할에 알 수 없는 값이 있습니다.")
        return sorted(set(value), key=APPROVABLE_ROLES.index)


class DataProtectionRules(_Rules):
    mask_emails: bool = False
    mask_phone_numbers: bool = True
    mask_resident_registration_numbers: bool = True


def hard_max_output_chars() -> int:
    """응답 제한이 올릴 수 있는 가장 큰 값 - 어떤 액션의 코드 상한보다도 크지 않다."""
    from app.ai.actions import ACTIONS

    return max(a.max_output_chars for a in ACTIONS.values())


class ContentRules(_Rules):
    max_output_chars: int | None = None
    block_external_links: bool = False

    @field_validator("max_output_chars")
    @classmethod
    def _cap(cls, value: int | None) -> int | None:
        if value is None:
            return None
        top = hard_max_output_chars()
        if not MIN_OUTPUT_CHARS <= value <= top:
            raise ValueError(f"출력 글자 수는 {MIN_OUTPUT_CHARS}자에서 {top:,}자 사이로 정합니다.")
        return value


RULES = {KIND_APPROVAL: ApprovalRules, KIND_DATA_PROTECTION: DataProtectionRules, KIND_CONTENT: ContentRules}


def normalize_rules(kind: str, content) -> dict:
    """종류에 맞는 규칙으로 검사하고 빠진 칸을 기본값으로 채운다. 틀리면 422 로 까닭을 말한다."""
    if kind not in RULES:
        raise ValidationAppError("정책 종류를 고르세요.")
    if not isinstance(content, dict):
        raise ValidationAppError("정책 규칙은 JSON 객체여야 합니다.")
    try:
        return RULES[kind](**content).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0]
        if first.get("type") == "extra_forbidden":
            raise ValidationAppError(f"{KIND_LABELS[kind]} 정책에 없는 규칙입니다: {first['loc'][0]}") from None
        message = str(first.get("msg", "")).removeprefix("Value error, ")
        raise ValidationAppError(message or "정책 규칙이 올바르지 않습니다.") from None


def applicable_actions(kind: str) -> tuple[str, ...]:
    """이 종류가 붙을 수 있는 액션. 연결 확인은 관리 동작이라 어느 정책도 붙지 않는다. 승인은 결과가 저장되는 액션뿐이다.

    은퇴한 액션(이전 방식의 질문 답변 · 작업 공간 묻기)은 고를 수 없다(D-542) - 더는 부르는 곳이 없어 거기 건 정책은 아무
    일도 하지 않는다. 0044 가 옛 정책의 대상을 AI 도우미로 옮겼다.
    """
    from app.ai.actions import ACTIONS, CONNECTION_TEST

    keys = [k for k in ACTIONS if k != CONNECTION_TEST and not ACTIONS[k].retired]
    if kind == KIND_APPROVAL:
        keys = [k for k in keys if ACTIONS[k].supports_approval]
    return tuple(keys)


def normalize_applies_to(kind: str, value) -> list[str]:
    """적용 대상: 액션 키 목록이거나 `*`(이 종류가 붙을 수 있는 모든 액션). 글자 하나도 목록 하나로 받는다."""
    items = [value] if isinstance(value, str) else list(value or [])
    items = [str(v).strip() for v in items if str(v).strip()]
    if not items:
        raise ValidationAppError("정책을 적용할 기능을 고르세요.")
    if ALL_ACTIONS in items:
        return [ALL_ACTIONS]
    allowed = applicable_actions(kind)
    unknown = [v for v in items if v not in allowed]
    if unknown:
        raise ValidationAppError(f"{KIND_LABELS.get(kind, kind)} 정책을 적용할 수 없는 기능입니다: {', '.join(unknown)}")
    return sorted(set(items), key=list(allowed).index)
