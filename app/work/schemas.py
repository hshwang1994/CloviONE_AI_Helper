"""Work Domain 요청 스키마.

길이 상한을 전부 적는다 — 상한이 없는 문자열 필드는 그대로 DB 컬럼 길이 초과가 되고,
그 실패는 422 가 아니라 500 이다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.work.models import KEY_STATES, REL_KINDS, SPRINT_STATES

_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"


class ProjectKeyAssign(BaseModel):
    """프로젝트에 Key 를 준다. 처음 주는 경우와 바꾸는 경우가 **다른 동작**이다."""

    key: str = Field(min_length=2, max_length=10)


class BoardMove(BaseModel):
    """카드 한 장의 이동. 셋 다 선택이고, 하나도 없으면 서비스가 거절한다.

    `base_version` 은 편집을 시작할 때 받은 값이다. 안 보내면 예전대로 동작한다 —
    새 계약을 강제해 기존 경로를 깨뜨리지 않는다.
    """

    to_status: str | None = Field(default=None, max_length=32)
    sprint_id: str | None = Field(default=None, max_length=36)
    # 「스프린트에서 뺀다」와 「스프린트를 안 건드린다」는 다른 요청이다. `sprint_id=null`
    # 하나로는 둘을 구별할 수 없어서 의도를 따로 받는다.
    set_sprint: bool = False
    before_id: str | None = Field(default=None, max_length=36)
    after_id: str | None = Field(default=None, max_length=36)
    reorder: bool = False
    base_version: int | None = Field(default=None, ge=1)


class SprintCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    starts_on: str = Field(pattern=_ISO_DATE)
    ends_on: str = Field(pattern=_ISO_DATE)
    project_id: str | None = Field(default=None, max_length=36)
    goal: str | None = Field(default=None, max_length=2000)


class SprintState(BaseModel):
    state: str = Field(pattern="^(" + "|".join(SPRINT_STATES) + ")$")


class SprintClose(BaseModel):
    """닫으면서 안 끝난 일을 어디로 옮길지. 비우면 어느 회차에도 안 들어간다."""

    target_sprint_id: str | None = Field(default=None, max_length=36)


class RelationCreate(BaseModel):
    to_ticket_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(pattern="^(" + "|".join(REL_KINDS) + ")$")


class WatchToggle(BaseModel):
    watching: bool


class ExceptionAssign(BaseModel):
    """예외 티켓의 소속을 사람이 정한다 — **그 순간 채번이 돈다** (D-197)."""

    project_id: str = Field(min_length=1, max_length=36)


class KeyStateFilter(BaseModel):
    state: str = Field(pattern="^(" + "|".join(KEY_STATES) + ")$")
