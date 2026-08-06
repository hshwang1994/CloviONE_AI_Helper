"""팀 채팅 입력 스키마 (경계 검증, extra=forbid).

**상한을 넘으면 자르지 않고 거부한다.** 예전에는 `v[:2000]`·`v[:200]`·`out[:50]` 으로 조용히
잘라 놓고 200 을 돌려줬다. 2,400자를 붙여넣은 사람은 잘린 줄 모르고, 60명을 초대한 사람은
50명만 초대된 줄 모른다 — 화면은 성공이라 말한다. 바로 옆 `board/schemas.py` 는 같은 종류의
입력을 "본문은 20000자 이하여야 합니다." 로 **거부**한다. 계약이 두 벌일 이유가 없고,
사용자 글자를 말없이 먹는 쪽이 틀렸다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

MAX_BODY = 2000
MAX_TITLE = 200
MAX_MEMBERS = 50


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    member_user_ids: list[str] = []

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("방 이름을 입력하세요.")
        if len(v) > MAX_TITLE:
            raise ValueError(f"방 이름은 {MAX_TITLE}자 이하여야 합니다.")
        return v

    @field_validator("member_user_ids")
    @classmethod
    def _members(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for x in v or []:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        if len(out) > MAX_MEMBERS:
            raise ValueError(f"한 번에 {MAX_MEMBERS}명까지 선택할 수 있습니다.")
        return out


class DirectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str

    @field_validator("user_id")
    @classmethod
    def _uid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("대화 상대를 선택하세요.")
        return v


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str
    client_message_id: str | None = None

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("메시지를 입력하세요.")
        if len(v) > MAX_BODY:
            raise ValueError(f"메시지는 {MAX_BODY}자 이하여야 합니다.")
        return v


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int = 0

    @field_validator("seq")
    @classmethod
    def _seq(cls, v: int) -> int:
        return max(0, int(v))


class RenameInput(BaseModel):
    """그룹 방 이름 변경. GroupCreate.title 과 같은 규칙을 쓴다(만들 때와 바꿀 때가 다르면
    만들 수 없는 이름으로 바꿀 수 있게 된다)."""

    model_config = ConfigDict(extra="forbid")
    title: str

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("방 이름을 입력하세요.")
        if len(v) > MAX_TITLE:
            raise ValueError(f"방 이름은 {MAX_TITLE}자 이하여야 합니다.")
        return v


class MembersInput(BaseModel):
    """멤버 초대(여러 명). 정원 검사는 서비스가 한다 — 기존 멤버 수를 알아야 판단할 수 있다."""

    model_config = ConfigDict(extra="forbid")
    user_ids: list[str] = []

    @field_validator("user_ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for x in v or []:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        if not out:
            raise ValueError("초대할 사람을 선택하세요.")
        if len(out) > MAX_MEMBERS:
            raise ValueError(f"한 번에 {MAX_MEMBERS}명까지 초대할 수 있습니다.")
        return out


class MemberInput(BaseModel):
    """멤버 하나를 가리키는 입력(내보내기·방장 넘기기)."""

    model_config = ConfigDict(extra="forbid")
    user_id: str

    @field_validator("user_id")
    @classmethod
    def _uid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("대상을 선택하세요.")
        return v
