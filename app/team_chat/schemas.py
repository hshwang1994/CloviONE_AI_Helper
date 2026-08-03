"""팀 채팅 입력 스키마 (경계 검증, extra=forbid)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


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
        return v[:200]

    @field_validator("member_user_ids")
    @classmethod
    def _members(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for x in v or []:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out[:50]


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
        return v[:2000]


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
        return v[:200]


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
        return out[:50]


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
