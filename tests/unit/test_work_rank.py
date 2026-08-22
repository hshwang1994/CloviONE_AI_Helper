"""Backlog 순서 — 전체 재번호 없이 사이에 끼워 넣는다 (§5.2).

## 왜 순수 함수를 따로 보는가

`between` 은 두 이웃 사이의 값을 정하는 산수다. 이 값이 틀리면 카드가 엉뚱한 자리에
앉는데, **화면은 정상으로 보인다**(순서가 하나 어긋났을 뿐이다). 그래서 눈으로는 못 잡고,
DB 를 태우는 시험으로도 못 잡는다 — 그쪽은 「어딘가에 들어갔다」까지만 본다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.work import rank

pytestmark = pytest.mark.unit


def test_the_first_item_gets_the_step():
    assert rank.between(None, None) == rank.STEP


def test_appending_goes_after_the_last():
    assert rank.between(Decimal(1024), None) == Decimal(2048)


def test_prepending_goes_before_the_first():
    assert rank.between(None, Decimal(1024)) == Decimal(0)


def test_inserting_lands_exactly_between():
    assert rank.between(Decimal(1024), Decimal(2048)) == Decimal(1536)


def test_repeated_inserts_in_the_same_gap_keep_working():
    """같은 자리에 계속 끼워 넣어도 **값이 겹치지 않는다.**

    부동소수였다면 50번쯤에서 두 이웃이 같은 값이 되고, 그 순간 순서가 굳어 버린다 —
    사용자는 카드를 끄는데 자리가 안 바뀌는 것을 본다.
    """
    low, high = Decimal(0), Decimal(1024)
    seen = set()
    for _ in range(60):
        mid = rank.between(low, high)
        assert low < mid < high, f"중점이 두 이웃 사이에 없다: {low} < {mid} < {high}"
        assert mid not in seen, "같은 값이 두 번 나왔다"
        seen.add(mid)
        high = mid


def test_deep_values_are_flagged_for_rebalance():
    """자리수가 깊어지면 **다시 매기라고 말한다.**

    무한 정밀도라 계산 자체는 계속 되지만, 값이 사람이 못 읽을 만큼 길어지고 비교
    비용도 는다. 드물게 한 번 전체를 다시 매기는 것과 매번 다시 매기는 것은 다른 일이다.
    """
    shallow = Decimal("1536.5")
    assert not rank.needs_rebalance(shallow)

    deep = Decimal("1." + "0" * (rank.MAX_SCALE + 1) + "1")
    assert rank.needs_rebalance(deep)
    assert not rank.needs_rebalance(None)


def test_out_of_order_neighbours_do_not_silently_swap():
    """부르는 쪽이 순서를 뒤집어 주면 **조용히 고치지 않는다.**

    고쳐 주면 어느 쪽이 맞는지 모른 채 목록이 흔들린다. 위쪽 기준으로 뒤에 붙여
    적어도 결정적으로 만든다.
    """
    assert rank.between(Decimal(2048), Decimal(1024)) == Decimal(2048) + rank.STEP


def test_equal_neighbours_do_not_produce_a_duplicate():
    """두 이웃이 같은 값이면(재조정 전의 낡은 목록) 그 값을 그대로 쓰지 않는다."""
    same = Decimal(1024)
    assert rank.between(same, same) != same
