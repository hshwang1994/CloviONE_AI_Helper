"""Work Domain 요청 스키마.

길이 상한을 전부 적는다 — 상한이 없는 문자열 필드는 그대로 DB 컬럼 길이 초과가 되고,
그 실패는 422 가 아니라 500 이다.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

from app.core.errors import ValidationAppError
from app.work.models import DECISION_KINDS, REL_KINDS, SPRINT_STATES

_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"

# ── 판 · 열 · 백로그의 조건 (D-497) ─────────────────────────────────────────

#: 신호 필터의 어휘. 값은 서비스가 다시 본다(`app/work/service.py::SIGNALS`).
SIGNAL_PATTERN = "^(blocked|overdue|issue)$"

#: 여러 값을 받는 축의 값 하나 길이. id 는 uuid 이고, 우선순위 · 난이도는 컬럼 길이다.
ID_MAX_LENGTH = 36
VALUE_MAX_LENGTH = 64

#: 한 축에 고를 수 있는 값의 수. 티켓 목록과 같은 수다(`app/tickets/schemas.py::_clean_list`).
MAX_FILTER_VALUES = 40


def filter_values(raw, *, max_length: int) -> tuple[str, ...]:
    """여러 값 축 하나를 튜플로 편다. 값 하나(`?priority=높음`)도 한 칸짜리 튜플이다.

    빈 값은 조건이 아니다 — 화면이 고르기 칸을 비우면 `?priority=` 로 온다. 같은 값은 한 번만
    센다. 너무 긴 값과 너무 많은 값은 **거절한다**(`ValueError` → 422). 티켓 목록처럼 조용히
    버리면 그 축의 값이 전부 버려진 날 조건이 통째로 사라져, 거른 줄 알았던 목록이 전부 열린다.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("필터 값은 문자열이어야 합니다.")
        text = item.strip()
        if not text:
            continue
        if len(text) > max_length:
            raise ValueError(f"필터 값은 {max_length}자까지 받을 수 있습니다.")
        if text not in out:
            out.append(text)
    if len(out) > MAX_FILTER_VALUES:
        raise ValueError(f"한 조건에는 값을 {MAX_FILTER_VALUES}개까지 고를 수 있습니다.")
    return tuple(out)


@dataclass(frozen=True, slots=True)
class BoardFilterQuery:
    """판 · 열 · 백로그 · 이동 위치 계산이 받는 **화면의 조건 한 벌**(아직 해석 전이다).

    네 입구가 이 한 모양을 쓴다. GET 셋은 질의 문자열에서(`board_filter_query`), 이동은 본문의
    `position_*` 에서(`BoardMove.position_query`) 같은 필드를 채운다 — 입구마다 조건을 따로
    적으면 한 곳에 축 하나가 빠진 날 그 입구만 다른 집합을 보고, 그 어긋남은 오류가 아니라
    순서가 틀린 화면으로만 드러난다.

    프로젝트 · 담당자 · 우선순위 · 난이도는 **값이 여러 개**여도 된다. 같은 축의 값끼리는 OR,
    축 사이는 AND 다(티켓 목록과 같은 규칙). 담당자는 앱 user_id 로 받고 서버가 해석한다(§12.3).
    """

    project_id: tuple[str, ...] = ()
    assignee_user_id: tuple[str, ...] = ()
    mine: bool = False
    priority: tuple[str, ...] = ()
    difficulty: tuple[str, ...] = ()
    est_wd_min: float | None = None
    est_wd_max: float | None = None
    q: str | None = None
    signal: str | None = None
    blocked_only: bool = False
    department_id: str | None = None


def board_filter_query(
    project_id: list[str] | None = Query(default=None),
    # 담당자는 **앱 user_id** 로 받는다. 브라우저는 원본 소스 토큰을 절대 모른다(§12.3) —
    # 해석은 서버가 한다.
    assignee_user_id: list[str] | None = Query(default=None),
    mine: bool = Query(default=False),
    priority: list[str] | None = Query(default=None),
    difficulty: list[str] | None = Query(default=None),
    # 예상 WD 범위는 양 끝을 포함한다(티켓 목록과 같은 뜻). NaN · 무한대는 범위가 아니라 422 다.
    est_wd_min: float | None = Query(default=None, allow_inf_nan=False),
    est_wd_max: float | None = Query(default=None, allow_inf_nan=False),
    q: str | None = Query(default=None, max_length=200),
    signal: str | None = Query(default=None, pattern=SIGNAL_PATTERN),
    blocked_only: bool = Query(default=False),
    department_id: str | None = Query(default=None, max_length=36),
) -> BoardFilterQuery:
    """GET 세 곳(판 · 열 · 백로그)의 조건 — FastAPI 의존성이다. 값 하나만 보내도 예전처럼 걸린다."""
    try:
        return BoardFilterQuery(
            project_id=filter_values(project_id, max_length=ID_MAX_LENGTH),
            assignee_user_id=filter_values(assignee_user_id, max_length=ID_MAX_LENGTH),
            mine=mine,
            priority=filter_values(priority, max_length=VALUE_MAX_LENGTH),
            difficulty=filter_values(difficulty, max_length=VALUE_MAX_LENGTH),
            est_wd_min=est_wd_min,
            est_wd_max=est_wd_max,
            q=q,
            signal=signal,
            blocked_only=blocked_only,
            department_id=department_id,
        )
    except ValueError as exc:
        raise ValidationAppError(str(exc)) from exc


def _as_value_list(value):
    """`position_*` 여러 값 칸의 입구 — 문자열 하나(옛 화면)는 한 칸짜리 목록이 된다."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return value


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
    # 판에서 옮겼는가, 백로그에서 옮겼는가. 두 목록의 순서는 **다른 컬럼**이라
    # (`tickets.board_rank` · `backlog_rank`) 어느 줄에서 끈 것인지를 화면이 말해야 한다 —
    # 안 말하면 판에서 옮긴 것이 백로그 순서를 흐트러뜨린다.
    on_board: bool = False
    # 화면에 없는 카드 기준 이동(§8.5) — "맨 위로"·"맨 아래로". `before_id`/`after_id`
    # 는 그 카드가 이미 받아 온 쪽에 있어야 쓸 수 있는데, 181행 중 맨 끝으로 보낼 때
    # 그 자리의 이웃은 아직 안 받아 왔을 수 있다. `position_*` 는 "지금 화면이 보는
    # 백로그"와 같은 조건을 다시 태워, 서버가 카드를 안 끌어오고도 목표 순위를 잰다.
    #
    # 이름은 `BoardFilterQuery` 의 필드 앞에 `position_` 을 붙인 것이다 — 한 필드도 빠지면
    # 안 된다(`position_query` 가 이름으로 옮긴다). 여러 값 넷은 목록을 받고, 옛 화면이
    # 보내는 문자열 하나도 그대로 받는다.
    to_position: str | None = Field(default=None, pattern="^(top|bottom)$")
    position_project_id: tuple[str, ...] = ()
    position_q: str | None = Field(default=None, max_length=200)
    position_assignee_user_id: tuple[str, ...] = ()
    position_mine: bool = False
    position_priority: tuple[str, ...] = ()
    position_difficulty: tuple[str, ...] = ()
    position_est_wd_min: float | None = Field(default=None, allow_inf_nan=False)
    position_est_wd_max: float | None = Field(default=None, allow_inf_nan=False)
    position_department_id: str | None = Field(default=None, max_length=36)
    position_signal: str | None = Field(default=None, pattern=SIGNAL_PATTERN)
    position_blocked_only: bool = False
    base_version: int | None = Field(default=None, ge=1)

    @field_validator(
        "position_project_id", "position_assignee_user_id",
        "position_priority", "position_difficulty",
        mode="before",
    )
    @classmethod
    def _wrap_single_value(cls, value):
        return _as_value_list(value)

    @field_validator("position_project_id", "position_assignee_user_id")
    @classmethod
    def _id_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return filter_values(value, max_length=ID_MAX_LENGTH)

    @field_validator("position_priority", "position_difficulty")
    @classmethod
    def _enum_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return filter_values(value, max_length=VALUE_MAX_LENGTH)

    def position_query(self) -> BoardFilterQuery:
        """`position_*` → 목록과 **같은 모양**의 조건. 필드 이름으로 옮기므로 목록 조건에 새 축이
        생기면 여기에 짝(`position_<이름>`)이 없는 순간 이 줄이 실패한다 — 조용히 빠지지 않는다."""
        return BoardFilterQuery(**{
            spec.name: getattr(self, f"position_{spec.name}") for spec in fields(BoardFilterQuery)
        })


class SprintCreate(BaseModel):
    """회차 하나 — **팀의 회차**다 (D-482). `department_id` 가 그 팀(`org_units.id`)이고
    필수다. 프로젝트 칸은 없다 — 프로젝트는 회차의 소유자가 아니라 티켓의 필터다."""

    name: str = Field(min_length=1, max_length=120)
    starts_on: str = Field(pattern=_ISO_DATE)
    ends_on: str = Field(pattern=_ISO_DATE)
    department_id: str = Field(min_length=1, max_length=36)
    goal: str | None = Field(default=None, max_length=2000)


class SprintUpdate(BaseModel):
    """고칠 수 있는 칸만. **보낸 칸만 바뀐다**(`exclude_unset`).

    `state` 는 여기 없다 — `/state`·`/close` 두 엔드포인트가 소유한다(전이 규칙이 그쪽에
    있다). `department_id` 는 **팀 미정(레거시) 회차에 팀을 정해 주는** 칸이다 — 이미 팀이
    있는 회차의 팀은 바꿀 수 없다(담긴 티켓의 자격이 통째로 깨진다).
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    starts_on: str | None = Field(default=None, pattern=_ISO_DATE)
    ends_on: str | None = Field(default=None, pattern=_ISO_DATE)
    goal: str | None = Field(default=None, max_length=2000)
    department_id: str | None = Field(default=None, max_length=36)


class SprintState(BaseModel):
    state: str = Field(pattern="^(" + "|".join(SPRINT_STATES) + ")$")


class SprintClose(BaseModel):
    """닫으면서 안 끝난 일을 어디로 옮길지. 비우면 어느 회차에도 안 들어간다."""

    target_sprint_id: str | None = Field(default=None, max_length=36)


class DecisionCreate(BaseModel):
    """회의록 한 줄 (지시 4).

    비우는 칸이 셋이다(`ticket_id` · `assignee_user_id` · `due_date`). 회의 중에 다 안
    정해지기 때문이다 — 필수로 만들면 「담당자 미정」인 결정을 적을 수 없고, 그러면
    사람들은 그 결정을 아예 안 적는다.
    """

    kind: str = Field(pattern="^(" + "|".join(DECISION_KINDS) + ")$")
    body: str = Field(min_length=1, max_length=2000)
    ticket_id: str | None = Field(default=None, max_length=36)
    assignee_user_id: str | None = Field(default=None, max_length=36)
    due_date: str | None = Field(default=None, pattern=_ISO_DATE)


class DecisionUpdate(BaseModel):
    """고칠 수 있는 칸만. **보낸 칸만 바뀐다**(`exclude_unset`).

    `kind` 가 여기 없는 것은 일부러다. 「결정」을 「할 일」로 바꾸는 것은 고치기가 아니라
    다른 줄을 쓰는 것이고, 그렇게 바뀌면 회의록을 나중에 읽는 사람이 그때 무슨 말이
    오갔는지 알 수 없다.
    """

    body: str | None = Field(default=None, min_length=1, max_length=2000)
    assignee_user_id: str | None = Field(default=None, max_length=36)
    due_date: str | None = Field(default=None, pattern=_ISO_DATE)
    done: bool | None = None


class RelationCreate(BaseModel):
    to_ticket_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(pattern="^(" + "|".join(REL_KINDS) + ")$")


class WatchToggle(BaseModel):
    watching: bool


class ExceptionAssign(BaseModel):
    """예외 티켓의 소속을 사람이 정한다 — **그 순간 채번이 돈다** (D-197)."""

    project_id: str = Field(min_length=1, max_length=36)

