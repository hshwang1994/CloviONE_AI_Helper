"""Backlog 순서 — 전체 재번호 없이 사이에 끼워 넣는다 (§5.2).

## 왜 정수 순번이 아닌가

100건짜리 백로그에서 맨 아래 항목을 맨 위로 끌면 정수 순번은 **99행을 갱신**한다.
그 갱신이 한 트랜잭션이라 다른 사람의 드래그와 부딪히고, 부딪히면 순서가 뒤섞인다.
소수를 쓰면 **한 행만** 갱신한다 — 두 이웃 사이에는 언제나 중점이 있기 때문이다.

## 자리수는 무한하지 않다

`numeric` 은 정밀도를 지정하지 않으면 임의 정밀도지만, 같은 자리에 계속 끼워 넣으면
소수 자리가 한 번에 하나씩 는다. 50번쯤 넘어가면 값이 사람이 못 읽을 만큼 길어지고
비교 비용도 는다. 그래서 자리수가 `MAX_SCALE` 을 넘으면 그 목록만 재조정한다 —
**드물게 한 번 전체를 다시 매기는 것**과 **매번 전체를 다시 매기는 것**은 다른 일이다.

## `priority` 와 다른 축이다

우선순위는 "얼마나 급한가", 순서는 "다음에 무엇을 하는가"다. 「높음」 세 건의 선후는
우선순위가 답하지 못하고, 그 답이 없으면 스탠드업에서 매번 다시 정하게 된다.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

# 새 항목 사이의 기본 간격. 2의 거듭제곱이라 중점이 딱 떨어진다 — 1024 사이에
# 10번을 끼워 넣어도 소수점이 안 생긴다.
STEP = Decimal(1024)

# 소수 자리가 이만큼 깊어지면 그 목록을 다시 매긴다. 40 이면 같은 자리에 40번
# 연속으로 끼워 넣은 것이고, 실제로 그런 백로그는 재조정이 필요한 상태다.
MAX_SCALE = 40

# 중점을 정확히 계산할 만큼의 유효자릿수. 2로 나누는 것은 십진에서 항상 끝나므로
# 넉넉하면 반올림이 일어나지 않는다.
_PRECISION = 200


def _scale(value: Decimal) -> int:
    """소수 자리 수. `Decimal.as_tuple().exponent` 가 음수면 그 절댓값이다."""
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def between(before: Decimal | None, after: Decimal | None) -> Decimal:
    """두 이웃 사이의 값. 한쪽이 없으면 끝에 붙인다.

    `before` 는 위 항목(더 작은 값), `after` 는 아래 항목(더 큰 값)이다. 둘 다 없으면
    목록이 비어 있다는 뜻이라 첫 값을 준다.
    """
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        if before is None and after is None:
            return STEP
        if before is None:
            return Decimal(after) - STEP
        if after is None:
            return Decimal(before) + STEP
        low, high = Decimal(before), Decimal(after)
        if low >= high:
            # 부르는 쪽이 순서를 뒤집어 줬다. 조용히 고치지 않고 위쪽 기준으로 붙인다 —
            # 조용히 고치면 어느 쪽이 맞는지 모른 채 목록이 흔들린다.
            return low + STEP
        return (low + high) / 2


def needs_rebalance(value: Decimal | None) -> bool:
    """이 값이 너무 깊은가."""
    return value is not None and _scale(Decimal(value)) > MAX_SCALE


def neighbours(
    db: Session, *, project_id: str | None, before_id: str | None, after_id: str | None
) -> tuple[Decimal | None, Decimal | None]:
    """드롭 위치의 두 이웃 값. 이웃이 아직 순위가 없으면 `None` 이다.

    `project_id` 는 이웃이 **같은 목록** 것인지 확인하는 데 쓴다 — 다른 프로젝트의
    티켓을 이웃으로 주면 두 백로그의 순위 공간이 섞인다.
    """
    def _rank_of(ticket_id: str | None) -> Decimal | None:
        if not ticket_id:
            return None
        row = db.execute(
            sa_text(
                "SELECT backlog_rank FROM tickets "
                "WHERE id = :tid AND project_uid IS NOT DISTINCT FROM :pid"
            ),
            {"tid": ticket_id, "pid": project_id},
        ).scalar_one_or_none()
        return Decimal(row) if row is not None else None

    return _rank_of(before_id), _rank_of(after_id)


def append_rank(db: Session, *, project_id: str | None) -> Decimal:
    """이 목록의 맨 뒤 값. 비어 있으면 첫 값."""
    last = db.execute(
        sa_text(
            "SELECT MAX(backlog_rank) FROM tickets "
            "WHERE project_uid IS NOT DISTINCT FROM :pid"
        ),
        {"pid": project_id},
    ).scalar_one_or_none()
    return between(Decimal(last) if last is not None else None, None)


def rebalance(db: Session, *, project_id: str | None) -> int:
    """이 목록의 순위를 `STEP` 간격으로 다시 매긴다. **순서는 그대로다.**

    `row_number()` 로 현재 순서를 그대로 읽어 곱하기만 한다. 순위가 없던 행
    (`NULL`)은 뒤로 간다 — 그것이 지금 목록에서 보이는 순서이기도 하다.
    """
    return db.execute(
        sa_text(
            "UPDATE tickets t SET backlog_rank = ordered.rank_value FROM ("
            "  SELECT id, (row_number() OVER ("
            "    ORDER BY backlog_rank NULLS LAST, created_at, id"
            "  ))::numeric * :step AS rank_value"
            "  FROM tickets"
            "  WHERE project_uid IS NOT DISTINCT FROM :pid"
            ") ordered WHERE t.id = ordered.id"
        ),
        {"pid": project_id, "step": STEP},
    ).rowcount


def place(
    db: Session,
    *,
    project_id: str | None,
    before_id: str | None,
    after_id: str | None,
) -> Decimal:
    """드롭 위치의 순위 값. 필요하면 **먼저 재조정하고 다시 계산한다.**

    재조정 뒤에 다시 읽는 것이 중요하다 — 재조정은 이웃들의 값을 바꾸므로, 바꾸기
    전에 계산한 중점은 이제 다른 자리를 가리킨다.
    """
    low, high = neighbours(
        db, project_id=project_id, before_id=before_id, after_id=after_id
    )
    if low is None and high is None:
        # 이웃이 하나도 없다 — 빈 칸에 놓았거나, 이웃이 아직 순위를 못 받았다.
        # 그때 `between(None, None)` 은 언제나 같은 값(`STEP`)을 주므로 목록에 이미
        # 있는 카드와 겹친다. 겹친 순위는 제약 위반이 아니라 **순서가 흔들리는 상태**라
        # 아무도 신고하지 않는다 — 맨 뒤에 붙인다.
        return append_rank(db, project_id=project_id)
    value = between(low, high)
    if not needs_rebalance(value):
        return value
    rebalance(db, project_id=project_id)
    low, high = neighbours(
        db, project_id=project_id, before_id=before_id, after_id=after_id
    )
    return between(low, high)
