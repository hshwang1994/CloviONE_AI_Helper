"""Workflow — 표시 Status 와 내부 Category 를 나누고, **Status 와 Signal 을 가른다** (§5.2 · D-349).

## 축이 둘이다

**Status 는 업무가 어디까지 왔는가**이고 티켓 하나가 정확히 하나를 갖는다:
계획 · 진행 중 · 검증 · 완료 · 보류 · 취소.

**Signal 은 그 진행에 무슨 일이 있는가**이고 동시에 여러 개가 켜질 수 있다:
이슈 있음 · 차단됨 · 지연.

둘을 한 컬럼에 섞으면 「진행 중인데 막혀 있다」를 적을 자리가 없다. 실제로 이
제품이 그랬다 — `이슈` 가 Status 였고, 그래서 이슈가 생긴 티켓은 자기가 어디까지
왔는지를 잃었다. 「백로그」도 Status 가 아니다. 그것은 위치이고
`tickets.sprint_id IS NULL` 이 답한다.

## 왜 Category 를 또 나누는가

화면에 보이는 말은 여섯이다.
집계가 알아야 하는 것은 넷이다: 시작 전 · 하는 중 · 끝남 · 접음.

둘을 한 컬럼으로 두면 「진행률」이 표시 어휘에 묶인다. 실제로 그 사고가 이 제품에
이미 있었다 — Notion 의 rollup 이 `complete = [완료, 취소]` 라서 **취소한 티켓을
완료로 셌다**(`app/projects/progress.py`). 표시 어휘가 하나 늘 때마다 집계를 다시
설계해야 하는 구조였다.

## 어휘의 정본은 이 파일이다

`ticket_statuses` 표는 이 목록의 **결과**다. 마이그레이션이 값을 심고
`tests/unit/test_work_domain_seed.py` 가 둘을 맞물린다 — S5 가 권한 표에 쓴 것과
같은 수법이고, 같은 이유다: 마이그레이션은 그 시점 스키마의 얼어붙은 스냅숏이라
코드를 import 하면 나중에 목록을 고치는 날 옛 마이그레이션의 뜻이 함께 바뀐다.

표가 따로 있어야 하는 이유는 조인이다. 칸반이 「하는 중인 것」을 물을 때 파이썬
사전을 SQL 에 실어 보낼 수는 없다.

## 네 표현을 한 객체가 든다

`_Status` 하나가 표시 이름·집계 갈래·열 순서·판에서의 자리를 함께 갖는다. 상태를
더하면 넷이 같이 생긴다 — 한쪽만 만들 수가 없다. S5 가 가시성 규칙에서 배운 모양
그대로다 (D-231): 같은 파일에 있다는 것만으로는 「한 곳」이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import case
from sqlalchemy.sql.elements import Case

from app.core.errors import ValidationAppError

# ── 집계 갈래 ────────────────────────────────────────────────────────────────
CAT_OPEN = "OPEN"
CAT_IN_PROGRESS = "IN_PROGRESS"
CAT_DONE = "DONE"
CAT_CANCELED = "CANCELED"
CATEGORIES: tuple[str, ...] = (CAT_OPEN, CAT_IN_PROGRESS, CAT_DONE, CAT_CANCELED)

# 끝난 것으로 세는 갈래. 「완료」와 「취소」는 **둘 다 끝났지만 같은 것이 아니다** —
# 진행률은 완료만 세고, 잔여 작업은 둘 다 뺀다.
TERMINAL_CATEGORIES: frozenset[str] = frozenset({CAT_DONE, CAT_CANCELED})


# ── 판에서의 자리 ────────────────────────────────────────────────────────────
#
# 여섯이 전부 열이 되면 판이 화면 폭을 넘고, 사용자가 매일 보는 넷이 매일 안 보는
# 둘 때문에 좁아진다. 자리는 셋이다.
BOARD_COLUMN = "column"      # 기본 실행 열
BOARD_COLLAPSED = "collapsed"  # 접힌 칸. 펴면 보인다
BOARD_HIDDEN = "hidden"      # 기본 판에서 숨는다. Filter/Archive 로만 본다


@dataclass(frozen=True, slots=True)
class _Status:
    """표시 Status 한 줄. **네 표현을 함께 든다.**"""

    key: str          # 저장값. 지금 데이터가 이 문자열이다
    label: str        # 화면에 쓰는 말. key 와 다를 수 있다 — 「진행」의 표시는 「진행 중」이다
    category: str     # 집계 갈래
    sort_order: int   # 칸반 열 순서. 화면마다 다시 정하면 두 화면이 다른 순서를 보인다
    is_default: bool  # 새 티켓의 시작 상태. 정확히 하나다
    board: str        # 판에서의 자리


# 저장값은 실측 어휘(INVENTORY 07 · `ticket_cache.status` 실데이터)를 그대로 쓴다.
# **표시 이름만 바꾼다** — `진행` 은 화면에서 `진행 중` 이다. 저장값을 옮기면 데이터
# 이관이 아니라 데이터 번역이 되고, 옛 링크·옛 필터·옛 감사 기록이 함께 갈린다.
#
# 「이슈」가 여기 없는 이유는 **그것이 업무 진행 단계가 아니기 때문**이다 (D-349).
# 이슈·차단·지연은 상태와 **직교하는 신호**라서 아래 절이 따로 든다 — 「진행 중이면서
# 이슈가 있다」가 표현 가능해야 하고, 한 컬럼으로는 그것을 못 적는다.
STATUSES: tuple[_Status, ...] = (
    _Status("계획", "계획", CAT_OPEN, 10, True, BOARD_COLUMN),
    _Status("진행", "진행 중", CAT_IN_PROGRESS, 20, False, BOARD_COLUMN),
    _Status("검증", "검증", CAT_IN_PROGRESS, 30, False, BOARD_COLUMN),
    _Status("완료", "완료", CAT_DONE, 40, False, BOARD_COLUMN),
    # 「보류」가 IN_PROGRESS 가 아니라 OPEN 인 이유: 의도적으로 멈춘 일이다. 진행으로
    # 세면 번다운이 안 내려가는데 이유가 안 보이고, 끝난 것으로 세면 남은 일이 사라진다.
    _Status("보류", "보류", CAT_OPEN, 50, False, BOARD_COLLAPSED),
    _Status("취소", "취소", CAT_CANCELED, 60, False, BOARD_HIDDEN),
)

_BY_KEY: dict[str, _Status] = {s.key: s for s in STATUSES}

DEFAULT_STATUS: str = next(s.key for s in STATUSES if s.is_default)


# ── Signal ───────────────────────────────────────────────────────────────────
#
# 셋의 출처가 서로 다르다. 그것이 이 절이 존재하는 이유다 — 「지연」을 컬럼으로 저장하면
# 어제 지연이던 티켓이 오늘 마감을 미뤄도 계속 지연으로 남고, 아무도 그 값을 지우러
# 오지 않는다.
SIGNAL_ISSUE = "issue"      # 사람이 켠다. 「문제가 있다」
SIGNAL_BLOCKED = "blocked"  # 사람이 켜거나 `blocks` 관계가 만든다. 「남이 끝나야 움직인다」
SIGNAL_OVERDUE = "overdue"  # **계산한다.** 저장하지 않는다
SIGNALS: tuple[str, ...] = (SIGNAL_ISSUE, SIGNAL_BLOCKED, SIGNAL_OVERDUE)

SIGNAL_LABEL: dict[str, str] = {
    SIGNAL_ISSUE: "이슈 있음",
    SIGNAL_BLOCKED: "차단됨",
    SIGNAL_OVERDUE: "지연",
}


def is_overdue(due_date: date | None, status: str | None, *, today: date) -> bool:
    """마감이 지났는데 안 끝났는가. **이 판정이 제품에 한 곳이다.**

    끝난 일은 마감이 지났어도 지연이 아니다 — 지난주에 끝낸 일이 오늘 빨갛게 뜨면
    그 색은 아무 행동도 요구하지 않고, 요구하지 않는 색은 곧 무시된다.
    """
    if due_date is None or is_terminal(status):
        return False
    return due_date < today


def signals_of(
    *,
    due_date: date | None,
    status: str | None,
    today: date,
    issue: bool = False,
    blocked: bool = False,
) -> tuple[str, ...]:
    """켜져 있는 신호 전부. 화면과 집계가 **같은 목록**을 본다."""
    out: list[str] = []
    if issue:
        out.append(SIGNAL_ISSUE)
    if blocked:
        out.append(SIGNAL_BLOCKED)
    if is_overdue(due_date, status, today=today):
        out.append(SIGNAL_OVERDUE)
    return tuple(out)


def all_statuses() -> tuple[_Status, ...]:
    """열 순서대로 전부. 칸반 열과 폼 드롭다운이 같은 순서를 본다."""
    return tuple(sorted(STATUSES, key=lambda s: s.sort_order))


def label_of(status: str | None) -> str:
    """화면에 쓸 말. 모르는 값은 **그대로 돌려준다** — 지어내지 않는다."""
    found = _BY_KEY.get(status or "")
    return found.label if found is not None else (status or "")


def board_placement(status: str | None) -> str:
    """이 상태가 판에서 어디에 서는가. 모르는 상태는 숨기지 않는다 — 안 보이는
    티켓은 아무도 못 고친다."""
    found = _BY_KEY.get(status or "")
    return found.board if found is not None else BOARD_COLUMN


def board_column_keys() -> tuple[str, ...]:
    """기본 실행 열 넷. 화면이 상태 이름을 적지 않게 한다."""
    return tuple(s.key for s in all_statuses() if s.board == BOARD_COLUMN)


def is_known(status: str | None) -> bool:
    return status in _BY_KEY


def category_of(status: str | None) -> str | None:
    """행 표현. 모르는 상태는 **`None`** 이다 — 임의로 OPEN 에 넣지 않는다.

    모르는 값을 OPEN 으로 뭉개면 화면은 정상으로 보이고 집계만 조용히 틀린다. 그
    부류가 이 저장소가 반복한 실수다(취소를 완료로 센 rollup). `None` 이면 칸반이
    별도 칸에 모아 보여 주고, 사람이 그것을 본다.
    """
    found = _BY_KEY.get(status or "")
    return found.category if found is not None else None


def category_sql(column) -> Case:
    """SQL 표현. `category_of` 와 **같은 표에서 만든다.**

    두 표현을 손으로 각각 적으면 상태를 하나 더한 날 한쪽만 고쳐진다 — 그러면
    목록은 새 상태를 알고 집계는 모른다. 그 어긋남은 오류를 내지 않는다.
    """
    return case(
        {s.key: s.category for s in STATUSES}, value=column, else_=None
    )


def is_terminal(status: str | None) -> bool:
    return category_of(status) in TERMINAL_CATEGORIES


def non_terminal_keys() -> tuple[str, ...]:
    """종료 갈래(DONE·CANCELED)가 아닌 상태 key. 화면이 상태명을 하드코딩하지 않게 한다.

    표에 없는 이름을 여기서 만들지 않는다. `STATUSES` 에 있는 것만, 그 갈래가
    종료가 아닌 것만 돌려준다.
    """
    return tuple(s.key for s in STATUSES if s.category not in TERMINAL_CATEGORIES)


def validate_transition(from_status: str | None, to_status: str | None) -> str:
    """옮길 수 있는가. **막는 것은 「모르는 상태」 하나뿐이다.**

    전이 행렬을 만들지 않는다. 지금 이 제품에는 그런 규칙이 없었고(상태 허용값이
    Notion 스키마 조회에서 왔다), 없던 제약을 여기서 새로 만들면 어제까지 되던
    변경이 오늘 거절된다 — 그 거절에는 근거가 없다.

    얻는 것은 어휘의 소유다. 지금까지는 오타 하나가 새 상태로 저장됐고 그 티켓은
    어느 칸반 열에도 안 나타났다.
    """
    target = (to_status or "").strip()
    if not is_known(target):
        raise ValidationAppError(f"모르는 티켓 상태입니다: {target or '(빈 값)'}")
    return target


def seed_rows() -> list[dict]:
    """마이그레이션이 심을 값. 시험이 이 목록과 표를 맞물린다."""
    return [
        {
            "key": s.key, "label": s.label, "category": s.category,
            "sort_order": s.sort_order, "is_default": s.is_default,
        }
        for s in all_statuses()
    ]
