"""Work Domain 요청 스키마.

길이 상한을 전부 적는다 — 상한이 없는 문자열 필드는 그대로 DB 컬럼 길이 초과가 되고,
그 실패는 422 가 아니라 500 이다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.work.models import DECISION_KINDS, REL_KINDS, SPRINT_STATES

_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"


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
    to_position: str | None = Field(default=None, pattern="^(top|bottom)$")
    position_project_id: str | None = Field(default=None, max_length=36)
    position_q: str | None = Field(default=None, max_length=200)
    position_assignee_user_id: str | None = Field(default=None, max_length=36)
    position_mine: bool = False
    position_priority: str | None = Field(default=None, max_length=64)
    position_difficulty: str | None = Field(default=None, max_length=64)
    position_department_id: str | None = Field(default=None, max_length=36)
    position_signal: str | None = Field(default=None, pattern="^(blocked|overdue|issue)$")
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

