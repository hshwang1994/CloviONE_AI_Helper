"""화면에서 넣을 수 있는 비밀 값의 **전부** (계획 2.3).

## 왜 이름을 코드에 박아 두는가

비밀 값은 `SECRETS_DIR` 아래 파일 하나로 산다(`app/core/secret_refs.py`). 운영 설치에서 그
디렉터리는 root:clovirassist 0750 이고 웹은 쓸 수 없어서, 쓰기는 root 로 도는 특권 헬퍼가
대신 한다(`app/sysops/actions_secrets.py`). 그 헬퍼가 **아무 이름**이나 받으면 웹을 뚫은
사람이 헬퍼를 통해 `/etc/clovirassist/secrets` 아래 임의 파일을 만들 수 있다. 그래서 헬퍼는
이 표에 있는 이름만 쓴다. 웹의 검증은 사용자에게 빠른 오류를 주려는 것이고, 믿는 경계는
헬퍼 쪽의 같은 검사다(`app/sysops/router.py` 머리말과 같은 원칙).

## 사람이 넣는 값과 제품이 넣는 값

`user_writable=False` 인 칸은 관리자 API 로 쓸 수 없다. ChatGPT 계정 연결 정보는 OAuth
흐름이 서버 안에서 만들어 저장하는 값이라, 사람이 붙여 넣을 이유가 없고 붙여 넣게 두면
검증되지 않은 토큰 묶음이 들어온다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.errors import ValidationAppError

KIND_TEXT = "text"
KIND_JSON = "json"

SLOT_SMTP_PASSWORD = "smtp.password"
SLOT_ANTHROPIC_API_KEY = "ai.anthropic.api_key"
SLOT_OPENAI_API_KEY = "ai.openai.api_key"
SLOT_OPENAI_CHATGPT = "ai.openai.chatgpt"


@dataclass(frozen=True)
class SecretSlot:
    name: str
    label: str
    kind: str
    max_bytes: int
    user_writable: bool


SECRET_SLOTS: dict[str, SecretSlot] = {
    slot.name: slot
    for slot in (
        SecretSlot(SLOT_SMTP_PASSWORD, "메일(SMTP) 비밀번호", KIND_TEXT, 1024, True),
        SecretSlot(SLOT_ANTHROPIC_API_KEY, "Anthropic API 키", KIND_TEXT, 1024, True),
        SecretSlot(SLOT_OPENAI_API_KEY, "OpenAI API 키", KIND_TEXT, 1024, True),
        SecretSlot(SLOT_OPENAI_CHATGPT, "ChatGPT 계정 연결 정보", KIND_JSON, 16384, False),
    )
}


class UnknownSecretSlotError(ValidationAppError):
    code = "unknown_secret_slot"
    default_message = "저장할 수 없는 비밀 값 이름입니다."


def get_slot(name: object) -> SecretSlot:
    if not isinstance(name, str) or name not in SECRET_SLOTS:
        raise UnknownSecretSlotError()
    return SECRET_SLOTS[name]


def normalize_value(slot: SecretSlot, value: object) -> str:
    """저장할 값을 검사하고 다듬는다. **오류 문구에 값을 절대 싣지 않는다.**

    값은 앞뒤 공백을 떼고 저장한다(`FileSecretReferenceProvider.get` 이 읽을 때도 뗀다).
    텍스트 칸에 줄바꿈이나 NUL 이 있으면 거절한다 - 붙여 넣다 딸려 온 줄바꿈은 API 키를
    조용히 틀리게 만들고, 그 실패는 인증 거부로만 드러나 원인을 찾기 어렵다.
    """
    if not isinstance(value, str):
        raise ValidationAppError("비밀 값은 문자열이어야 합니다.")
    text = value.strip()
    if not text:
        raise ValidationAppError("빈 값은 저장하지 않습니다.")
    if len(text.encode("utf-8")) > slot.max_bytes:
        raise ValidationAppError(f"{slot.label}이(가) 너무 깁니다.")
    if "\x00" in text:
        raise ValidationAppError(f"{slot.label}에 쓸 수 없는 문자가 들어 있습니다.")
    if slot.kind == KIND_TEXT and ("\n" in text or "\r" in text):
        raise ValidationAppError(f"{slot.label}에는 줄바꿈이 들어갈 수 없습니다.")
    if slot.kind == KIND_JSON:
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise ValidationAppError(f"{slot.label} 형식이 올바르지 않습니다.") from exc
        if not isinstance(parsed, dict):
            raise ValidationAppError(f"{slot.label} 형식이 올바르지 않습니다.")
    return text


def user_slots() -> list[SecretSlot]:
    return [slot for slot in SECRET_SLOTS.values() if slot.user_writable]
