"""요청 문자열 위생 — DB 가 담지 못하는 문자와 공백뿐인 이름 (XB-04 · S-01 · S-08).

## 왜 요청 경계에서 막는가

PostgreSQL 의 `text` 는 NUL(`U+0000`)을 담지 못한다. 그래서 `{"name": "a\\u0000b"}` 같은
요청은 스키마·라우터·서비스를 전부 지나 psycopg 가 `DataError` 를 던지는 자리에서 처음
막히고, 그 예외를 잡는 곳이 없어 관리자가 보는 것은 「Internal server error」 500 이다.
무엇이 틀렸는지 말해 주지 않으니 관리자는 같은 요청을 몇 번이고 다시 보낸다. 사람이
손으로 NUL 을 넣지는 않지만 붙여넣기·CSV 가져오기·외부 연동 페이로드로는 실제로
들어온다 — 그래서 경계는 화면이 아니라 서버다.

**정상 유니코드는 그대로 통과한다.** 한글도 이모지도 PostgreSQL 이 담는 문자다. 여기서
거절하는 것은 「저장할 수 없는 문자」 하나뿐이고, 그 판단은 저장소 경로 스키마가
`[^\\x00]` 으로 이미 하고 있던 것과 같다(`app/storage/schemas.py`) — 그 판단이 한 곳에만
있어서 나머지 쓰기 API 가 전부 500 이었다.

## 이름은 검증한 형태로 저장한다

`Field(min_length=1)` 은 strip 하기 전 길이를 본다. 그래서 「   」는 검증을 지나고, 저장
직전의 `strip()` 이 그것을 빈 문자열로 만든다 — 검증이 본 문자열과 저장되는 문자열이
갈라진다. 그 끝은 DB CHECK 위반 500(저장소 이름)이거나 제목이 빈 공지다.
`clean_required_text()` 는 정규화와 검증을 같은 자리에서 해서 그 틈을 없앤다.
`app/org/service.py::normalize_name` 이 부서·직책에서 쓰는 규칙과 같은 규칙이다.
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping

from pydantic import BaseModel, model_validator

from app.core.errors import ValidationAppError

#: PostgreSQL 의 text 가 담지 못하는 유일한 문자.
NUL = "\x00"


def has_final_consonant(word: str) -> bool:
    """마지막 글자에 받침이 있는가. 조사를 고르는 유일한 기준이다."""
    last = (word or "").strip()[-1:]
    if not last:
        return False
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:  # 한글 음절 — 종성 인덱스가 0 이면 받침이 없다
        return (code - 0xAC00) % 28 != 0
    return True  # 한글이 아니면(영문·숫자·기호) 보수적으로 받침이 있는 쪽으로 읽는다


def object_particle(word: str) -> str:
    """받침에 맞는 목적격 조사(을/를). 「제목을」·「저장소 이름을」·「메모를」.

    「을(를)」 같은 괄호 표기를 쓰지 않는다 — 화면 문구는 완전한 한 문장이어야 한다
    (CLAUDE.md §10). 같은 규칙을 `app/core/scope.py::_topic_particle` 이 은/는에 쓰고
    있고, 받침을 보는 계산은 그 둘이 같다(`has_final_consonant`).
    """
    return "을" if has_final_consonant(word) else "를"


#: 화면이 그 칸을 부르는 이름. 사용자에게 가는 문장에는 **이 이름**을 쓴다.
#:
#: API 필드 이름은 우리끼리 쓰는 말이다. 「title 값에 …」 이라고 답하면 사용자는 화면에서
#: 「제목」이라고 적힌 칸과 그 영문 키를 스스로 이어야 한다 — 붙여넣기 한 번으로 막힌
#: 사람에게 시킬 일이 아니다. `app/backups/router.py` 가 「문구에 내부 키 이름을 적지
#: 않는다 — 화면의 버튼 이름 그대로 말한다」로 이미 적어 둔 규칙이다.
#:
#: 모르는 칸은 **이름 없이** 답한다(`nul_message` 의 기본 문장). 모르는 키를 그대로 싣느니
#: 한 칸 덜 말하는 편이 낫다. 모델마다 다르게 부르는 칸은 그 모델이 `nul_field_labels` 로
#: 덮는다 — `NulFreeModel` 을 새로 상속하는 요청 모델은 자기 칸 이름을 여기나 그쪽에 적는다.
FIELD_LABELS: dict[str, str] = {
    # 공지 (`app/announcements/router.py`)
    "title": "제목",
    "body": "내용",
    "level": "중요도",
    "audience": "대상",
    "link_url": "링크 주소",
    "link_label": "링크 문구",
    # 저장소 설정 (`app/storage/schemas.py`)
    "name": "이름",
    "base_path": "경로",
    "mount_point": "마운트 지점",
    "source": "원본",
    "options": "마운트 옵션",
    "credentials_ref": "인증 정보 이름",
}


def field_label(field: str | None, labels: Mapping[str, str] | None = None) -> str | None:
    """이 칸을 화면이 뭐라고 부르는가. 모르면 ``None``."""
    if not field:
        return None
    if labels and field in labels:
        return labels[field]
    return FIELD_LABELS.get(field)


def has_nul(value: Any) -> bool:
    """`value` 안 어딘가에 NUL 이 있는가. 목록·사전 안까지 본다."""
    if isinstance(value, str):
        return NUL in value
    if isinstance(value, dict):
        return any(has_nul(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(has_nul(item) for item in value)
    return False


def nul_message(
    field: str | None = None, *, labels: Mapping[str, str] | None = None
) -> str:
    """NUL 을 거절할 때 사용자에게 가는 문장. 무엇을 하면 되는지까지 적는다.

    `field` 는 API 필드 이름이고, 문장에 실리는 것은 그 칸의 **화면 이름**이다
    (`FIELD_LABELS`, 모델이 넘긴 `labels` 가 우선한다). 이름을 모르는 칸은 칸을 빼고
    답한다 — 사용자가 읽을 문장에 내부 키가 새는 것보다 낫다.
    """
    label = field_label(field, labels)
    subject = f"{label} 칸에" if label else "입력값에"
    return (
        f"{subject} 저장할 수 없는 문자가 들어 있습니다. "
        "보이지 않는 제어문자를 지운 뒤 다시 보내 주세요."
    )


class NulFreeModel(BaseModel):
    """모든 문자열 필드에서 NUL 을 거절하는 요청 모델의 바탕.

    필드마다 검증기를 붙이지 않는 이유는 하나다 — 필드는 계속 늘어나고, 늘어난 필드에
    검증기를 붙이는 것을 잊으면 그 필드만 다시 500 이 된다. 모델 진입 시점에 원본
    payload 를 한 번 훑으면 **이 모델이 받는 모든 문자열**이 같은 규칙을 지난다.

    Pydantic 이 잡아 주는 `ValueError` 로 올린다 — 그러면 응답은 422 이고, 문구는
    `app/core/errors.py::_validation_error_message_ko` 가 `ctx.error` 에서 그대로 꺼내
    `error.details[].msg` 로 나간다(화면은 `frontend/src/lib/api.js` 가 그 사유를 토스트에
    싣는다). 어느 칸인지를 문장에 담는 이유는 CSV·연동처럼 값이 여러 칸인 요청에서 어느
    칸이 문제인지 알아야 고칠 수 있기 때문이다 — 담는 것은 **화면 이름**이다
    (`FIELD_LABELS`). 그 토스트를 읽는 사람은 API 필드 이름을 본 적이 없다.
    """

    #: 이 모델이 쓰는 칸 이름(필드 → 화면 이름). 공용 표(`FIELD_LABELS`)보다 우선한다 —
    #: 같은 키를 화면마다 다르게 부르는 경우가 실제로 있다.
    nul_field_labels: ClassVar[dict[str, str]] = {}

    @model_validator(mode="before")
    @classmethod
    def _reject_nul_in_any_string(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field, value in data.items():
                if has_nul(value):
                    raise ValueError(nul_message(str(field), labels=cls.nul_field_labels))
        elif has_nul(data):
            raise ValueError(nul_message())
        return data


def clean_required_text(value: str | None, *, subject: str) -> str:
    """앞뒤 공백을 뗀 값. 남는 글자가 없으면 422 로 거절한다.

    `subject` 는 「저장소 이름」·「제목」처럼 사용자가 화면에서 읽는 이름이다. 부르는
    쪽이 이 결과를 그대로 저장해야 검증한 형태와 저장 형태가 갈라지지 않는다.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        # 조사는 받침을 보고 붙인다 — 「을(를)」 같은 괄호 표기는 화면 문구가 완전한 한
        # 문장이어야 한다는 규칙(CLAUDE.md §10)을 어긴다.
        raise ValidationAppError(f"{subject}{object_particle(subject)} 입력해야 합니다.")
    return cleaned
