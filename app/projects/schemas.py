"""프로젝트 입력 스키마 (경계 검증, 불변 규칙: 외부 데이터 불신).

`extra='forbid'` 로 예상 못한 필드를 거절한다. 특히 **`progress_pct` 와 `health_score` 는
입력에 없다** — 둘 다 앱이 계산하는 값이고, 클라이언트가 넣을 수 있게 두면 화면이 자기가
보고 싶은 숫자를 써 넣을 수 있다. 그러면 "앱이 다시 계산한다"는 이 subsystem 의 전제가
그 자리에서 무너진다(계산이 틀렸을 때보다 나쁘다 — 틀린 줄도 모른다).

부분 수정(`ProjectUpdate`)은 **준 필드만** 바꾼다. `None` 을 "지우기"로 쓰려면 준 것과 안 준
것을 구별해야 하므로 `model_fields_set` 을 서비스가 읽는다.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from app.projects.models import (
    MILESTONE_PLANNED,
    MILESTONE_STATUSES,
    PROJECT_ACTIVE,
    PROJECT_STATUSES,
)

MAX_NAME = 200
MAX_GOAL = 20000
MAX_SHORT_TEXT = 200
# 정렬 순번의 상한. 컬럼은 Integer 라 큰 값도 들어가지만, 화면이 손으로 정하는 순서에
# 10만 같은 값이 오면 그건 순서가 아니라 입력 사고다. 경계에서 막는다.
MAX_SORT_ORDER = 9999


def _stripped(value):
    return value.strip() if isinstance(value, str) else value


def _iso_date_or_none(value):
    """ISO 'YYYY-MM-DD' 만 받는다.

    문자열로 저장하는 컬럼이라(모델 docstring) 형식이 섞이면 **비교가 조용히 어긋난다** —
    '2026/08/06' 은 예외를 내지 않고 그냥 정렬에서 엉뚱한 자리에 간다. 경계에서 잘라야
    나중에 화면이 이유 없이 이상해지지 않는다.
    """
    value = _stripped(value)
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from None


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # `code` 는 **여기 없다** (D-282). Project Code 는 서버가 짓고 사람은 못 고친다 —
    # 요청 본문에 실려 오면 `extra="forbid"` 가 422 로 막는다.
    #
    # 조용히 무시하지 않는 이유: 무시하면 클라이언트는 자기가 보낸 코드가 들어갔다고
    # 믿고, 그 믿음은 화면에 다른 코드가 뜰 때까지 안 깨진다.
    status: str = PROJECT_ACTIVE
    dept_id: str | None = None
    owner_user_id: str | None = None
    starts_on: str | None = None
    ends_on: str | None = None
    goal: str | None = None
    biz_type: str | None = None
    product: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = _stripped(v)
        if not v:
            raise ValueError("프로젝트 이름을 입력하세요.")
        if len(v) > MAX_NAME:
            raise ValueError(f"프로젝트 이름은 {MAX_NAME}자 이하여야 합니다.")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = _stripped(v)
        if v not in PROJECT_STATUSES:
            raise ValueError("허용되지 않은 프로젝트 상태입니다.")
        return v

    @field_validator("starts_on", "ends_on")
    @classmethod
    def _dates(cls, v):
        return _iso_date_or_none(v)

    @field_validator("goal")
    @classmethod
    def _goal(cls, v):
        if v is None:
            return None
        if len(v) > MAX_GOAL:
            raise ValueError(f"목표는 {MAX_GOAL}자 이하여야 합니다.")
        return v

    @field_validator("biz_type", "product")
    @classmethod
    def _short_text(cls, v):
        v = _stripped(v)
        if v in (None, ""):
            return None
        if len(v) > MAX_SHORT_TEXT:
            raise ValueError(f"{MAX_SHORT_TEXT}자 이하여야 합니다.")
        return v


class ProjectUpdate(ProjectCreate):
    """부분 수정 — 준 필드만 바꾼다.

    `name` 을 optional 로 되돌린다. 상속으로 검증 규칙을 그대로 물려받으면서 '필수'만
    푸는 것이라, 규칙이 두 벌이 되지 않는다.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    status: str | None = None
    # 여기 `notion_status` 가 있었다. 고치면 그대로 Notion 에 push 하려고 받던 값인데, 그
    # push 가 없어져 지금은 아무 데도 안 가는 칸이다. 응답에서도 뺐다.
    # 낙관적 잠금 (S6). 편집을 시작할 때 받은 `version` 을 그대로 돌려보낸다 — 그 사이
    # 누가 먼저 저장했으면 409 로 막힌다. 안 보내면 예전처럼 덮어쓴다(구버전 클라이언트
    # 호환). 저장되는 값이 아니라 **비교용**이라 EDITABLE_FIELDS 에 없다.
    #
    # 예전 이름은 `base_notion_version` 이었고 값은 해시였다. 이름과 타입이 함께 바뀐
    # 이유는 `app/projects/service.py::ensure_not_changed` 에 있다 — 옛 이름을 남겨 두면
    # 옛 클라이언트가 해시를 보내고 서버가 그것을 정수로 읽으려다 조용히 통과한다.
    base_version: int | None = None

    # `ProjectCreate` 에는 위 두 필드가 없다. 새로 만드는 프로젝트는 Notion 페이지가 아직
    # 없으므로 밀어 넣을 상태도, 충돌할 앞사람도 없다.

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if v is None:
            return None
        v = _stripped(v)
        if not v:
            raise ValueError("프로젝트 이름을 입력하세요.")
        if len(v) > MAX_NAME:
            raise ValueError(f"프로젝트 이름은 {MAX_NAME}자 이하여야 합니다.")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is None:
            return None
        v = _stripped(v)
        if v not in PROJECT_STATUSES:
            raise ValueError("허용되지 않은 프로젝트 상태입니다.")
        return v


class MilestoneCreate(BaseModel):
    """마일스톤 입력. 프로젝트와 **같은 경계 규칙**을 쓴다.

    `project_id` 를 본문으로 안 받는다. 경로(`/api/projects/{project_id}/milestones`)가
    이미 정하고 있고, 본문에서도 받으면 둘이 어긋났을 때 어느 쪽이 이기는지 코드마다
    답이 달라진다 - 그리고 본문 쪽이 이기는 순간 범위 게이트를 지나온 의미가 사라진다.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    due_on: str | None = None
    status: str = MILESTONE_PLANNED
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = _stripped(v)
        if not v:
            raise ValueError("마일스톤 이름을 입력하세요.")
        if len(v) > MAX_NAME:
            raise ValueError(f"마일스톤 이름은 {MAX_NAME}자 이하여야 합니다.")
        return v

    @field_validator("due_on")
    @classmethod
    def _due_on(cls, v):
        return _iso_date_or_none(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = _stripped(v)
        if v not in MILESTONE_STATUSES:
            raise ValueError("허용되지 않은 마일스톤 상태입니다.")
        return v

    @field_validator("sort_order")
    @classmethod
    def _sort_order(cls, v: int) -> int:
        if v < 0 or v > MAX_SORT_ORDER:
            raise ValueError(f"정렬 순번은 0 이상 {MAX_SORT_ORDER} 이하여야 합니다.")
        return v


class MilestoneUpdate(MilestoneCreate):
    """부분 수정 - 준 필드만 바꾼다. 검증 규칙은 상속으로 물려받아 두 벌이 되지 않는다."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    status: str | None = None
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if v is None:
            return None
        v = _stripped(v)
        if not v:
            raise ValueError("마일스톤 이름을 입력하세요.")
        if len(v) > MAX_NAME:
            raise ValueError(f"마일스톤 이름은 {MAX_NAME}자 이하여야 합니다.")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is None:
            return None
        v = _stripped(v)
        if v not in MILESTONE_STATUSES:
            raise ValueError("허용되지 않은 마일스톤 상태입니다.")
        return v

    @field_validator("sort_order")
    @classmethod
    def _sort_order(cls, v):
        if v is None:
            return None
        if v < 0 or v > MAX_SORT_ORDER:
            raise ValueError(f"정렬 순번은 0 이상 {MAX_SORT_ORDER} 이하여야 합니다.")
        return v
