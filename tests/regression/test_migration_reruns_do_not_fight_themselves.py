"""한 값에 주인이 둘이면 **두 번째 회차에서 터진다** (S13).

## 이 시험이 고정하는 결함

Dry Run 을 두 번 돌렸더니 두 번째가 죽었다:

    ticket has a sequence number but no project
    CONTEXT: PL/pgSQL function tickets_set_canonical_key()

표 복사가 `tickets.project_uid` 를 소스 값(NULL)으로 **다시 썼는데** `seq` 는 1회차가
매긴 값이 남아 있었다. 0003 의 트리거가 그 조합을 거절한 것이다 — 트리거는 옳았고
틀린 것은 「같은 컬럼을 두 단계가 쓴다」였다.

`projects.code` 는 같은 결함인데 **오류를 안 낸다.** 소스에서 22건 전부 NULL 이라
2회차 복사가 1회차에 붙인 Project Key 를 조용히 지운다. 그때 이미 발급된
`canonical_key` 는 근거를 잃고, 아무도 그 사실을 모른다.

그래서 목록을 코드로 못박는다.
"""

from __future__ import annotations

import pytest

from app.migration import plan

pytestmark = pytest.mark.regression


def test_the_columns_a_later_stage_owns_are_named():
    """목록이 비면 이 시험이 아무것도 안 지킨다 (D-213)."""
    assert plan.DERIVED_COLUMNS, "뒤 단계가 주인인 컬럼 목록이 비었다"
    assert ("projects", "code") in plan.DERIVED_COLUMNS
    assert ("ticket_cache", "project_uid") in plan.DERIVED_COLUMNS
    assert ("ticket_cache", "project_link") in plan.DERIVED_COLUMNS


def test_each_one_carries_a_reason():
    for (table, column), reason in plan.DERIVED_COLUMNS.items():
        assert reason.strip(), f"{table}.{column} 에 이유가 없다"


def test_those_columns_exist_in_the_target_unlike_dropped_ones():
    """**`DROPPED_COLUMNS` 와 다른 것**임을 못박는다.

    저쪽은 「대상에 그 컬럼이 없다」이고 이쪽은 「있는데 복사가 안 쓴다」다. 둘을
    한 목록에 섞으면 다음 사람이 「대상에 있는데 왜 여기 있지」 하며 지운다.
    """
    tables = plan.load_order()
    for source_table, column in plan.DERIVED_COLUMNS:
        target = plan.RENAMED_TABLES.get(source_table, source_table)
        assert target in tables
        from app.core.models_base import Base

        assert column in Base.metadata.tables[target].columns, (
            f"{target}.{column} 이 대상에 없다 — 그러면 DROPPED_COLUMNS 쪽이다"
        )


def test_dropped_columns_really_are_absent_from_the_target():
    """반대 방향도 본다."""
    from app.core.models_base import Base

    for source_table, column in plan.DROPPED_COLUMNS:
        target = plan.RENAMED_TABLES.get(source_table, source_table)
        assert column not in Base.metadata.tables[target].columns, (
            f"{target}.{column} 이 대상에 있다 — 그러면 DERIVED_COLUMNS 쪽이다"
        )


def test_the_two_lists_do_not_overlap():
    assert not (set(plan.DROPPED_COLUMNS) & set(plan.DERIVED_COLUMNS))
