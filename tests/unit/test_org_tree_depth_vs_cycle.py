"""UA-21: `build_rows()`가 깊이 상한(MAX_DEPARTMENT_DEPTH=32) 절단과 **진짜 순환**을
같은 `cycle: true`로 뭉뚱그렸다. 둘 다 "루트에서 안 닿음"이라는 같은 증상을 내지만 원인은
전혀 다르다 — 순환은 데이터가 실제로 망가진 것(부모를 고쳐야 함), 32단보다 깊은 트리는
그냥 화면이 평평하게 펴서 보여줄 방법이 없을 뿐인 **정상 데이터**다. 정상 데이터에
"상위 관계 오류" 배지를 붙이고 부모를 고치라고 안내하면 관리자가 멀쩡한 부서를 건드리게
된다.
"""

from __future__ import annotations

import pytest

from app.core.org_tree import MAX_DEPARTMENT_DEPTH
from app.org.models import Department
from app.org.tree import build_rows

pytestmark = pytest.mark.unit


def test_a_tree_deeper_than_the_depth_cap_is_not_reported_as_a_cycle(db):
    # 상한(32)보다 확실히 깊은 사슬 — 각 부서의 parent가 바로 앞 부서다. 순환은 전혀 없다.
    chain_length = MAX_DEPARTMENT_DEPTH + 5
    rows = []
    parent_id = None
    for i in range(chain_length):
        row = Department(id=f"deep-{i}", name=f"부서{i}", parent_id=parent_id)
        rows.append(row)
        parent_id = row.id
    db.add_all(rows)
    db.commit()

    result = build_rows(db, rows)
    cycled = [r for r in result if r["cycle"]]
    assert not cycled, f"순환이 없는데 cycle: true가 붙은 행이 있다: {cycled}"
    assert len(result) == chain_length, "깊이 상한 때문에 일부 부서가 통째로 빠졌다"


def test_a_genuine_cycle_is_still_reported_as_a_cycle(db):
    # a → b → a. 실제로 자기 자신에게 돌아온다 — 이건 진짜 순환이어야 한다.
    # parent_id는 실제 외래키라 두 행을 동시에 서로 가리키게 insert할 수 없다 — 먼저
    # 순환 없이 만든 뒤 UPDATE로 순환을 낸다(실제로 순환이 생길 수 있는 유일한 경로와 같다).
    a = Department(id="cyc-a", name="A팀", parent_id=None)
    b = Department(id="cyc-b", name="B팀", parent_id="cyc-a")
    db.add_all([a, b])
    db.commit()
    a.parent_id = "cyc-b"
    db.commit()

    result = build_rows(db, [a, b])
    by_id = {r["id"]: r for r in result}
    assert by_id["cyc-a"]["cycle"] is True, "진짜 순환인데 cycle: true가 안 붙었다"
    assert by_id["cyc-b"]["cycle"] is True, "진짜 순환인데 cycle: true가 안 붙었다"


def test_mixed_world_distinguishes_deep_from_cyclic(db):
    """같은 호출 안에 깊은 정상 트리와 진짜 순환이 섞여 있어도 서로 다른 판정을 받는다."""
    chain_length = MAX_DEPARTMENT_DEPTH + 3
    deep_rows = []
    parent_id = None
    for i in range(chain_length):
        row = Department(id=f"mix-deep-{i}", name=f"깊은부서{i}", parent_id=parent_id)
        deep_rows.append(row)
        parent_id = row.id
    a = Department(id="mix-cyc-a", name="순환A", parent_id=None)
    b = Department(id="mix-cyc-b", name="순환B", parent_id="mix-cyc-a")
    all_rows = deep_rows + [a, b]
    db.add_all(all_rows)
    db.commit()
    a.parent_id = "mix-cyc-b"
    db.commit()

    result = build_rows(db, all_rows)
    by_id = {r["id"]: r for r in result}
    assert not any(by_id[row.id]["cycle"] for row in deep_rows), "깊은 정상 트리가 순환으로 잘못 표시됐다"
    assert by_id["mix-cyc-a"]["cycle"] is True
    assert by_id["mix-cyc-b"]["cycle"] is True
