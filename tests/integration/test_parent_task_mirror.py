"""상위 작업 관계가 **관계 표까지 도달하고**, 리프 판정을 살린다.

## 왜 이 시험이 필요했나

프로젝트 진행률을 앱이 다시 계산하는 이유는 셋이다:
  ① 옛 소스는 **취소를 완료로 셌다**(status 그룹 `complete = [완료, 취소]`)
  ② **하위 작업이 부모와 이중 계산**된다
  ③ **예상 WD 가중이 무시**된다

①·③ 은 계산기만 고치면 되지만, ② 는 **부모가 누구인지 알아야** 한다. 그런데 진행률 계산기를
만든 시점에 상위 작업 relation 을 읽는 코드가 없었다 — 그래서 표본 안에 부모로 지목된 작업이
하나도 없었고, **리프 판정이 아무 효과가 없었다.** 계산기는 옳은데 **입력이 비어 있어서**
틀린 값을 냈다. 순수 함수 시험은 그 사실을 증명하지 못한다 — 함수가 아니라 **배선**을 봐야
한다.

## 지금 그 배선이 어디에 있는가

옛 소스에서 끌어오는 동기화는 사라졌다. `tickets.parent_page_id` 는 이관해 온 행이 달고
넘어온 **입력**으로 남아 있고, 계층의 정본은 `ticket_relations` 다. 그 둘을 잇는 자리가
`app/work/relations.py::sync_parent_links` 이고 이관 적재기가 그것을 부른다
(`app/migration/load.py`). 컬럼만 확인하면 관계 표가 빈 상태가 조용히 통과하므로 — 이 파일이
처음 잡은 결함이 정확히 그 모양이었다 — 여기서는 관계 표와 진행률까지 따라간다.
"""

from __future__ import annotations

import pytest

from app.work import relations

pytestmark = pytest.mark.integration

PARENT = "page-parent"
CHILD = "page-child"


@pytest.fixture()
def world(db, portal_project, make_ticket):
    """부모(진행) 한 건과 그것을 가리키는 자식(완료) 한 건."""
    parent = make_ticket(
        page_id=PARENT, project=portal_project, tid=1, title="상위 작업",
        status="진행", due="2026-09-01",
    )
    child = make_ticket(
        page_id=CHILD, project=portal_project, tid=2, title="하위 작업",
        status="완료", due="2026-09-01", parent_page_id=PARENT,
    )
    return {"parent": parent, "child": child}


def test_the_parent_relation_actually_reaches_the_relation_table(db, world):
    """입력 컬럼 → 파생기 → 관계 표까지 **끝에서 끝까지** 값이 도달하는가."""
    assert world["child"].parent_page_id == PARENT, "픽스처가 입력을 안 심었다"

    result = relations.sync_parent_links(db)
    db.commit()
    assert result["added"] == 1, f"관계가 하나도 안 생겼다: {result}"

    assert relations.parent_of(db, world["child"].id) == world["parent"].id, (
        "미러 컬럼은 찼는데 관계 표가 비어 있다 — 리프 판정이 아무 효과가 없다"
    )
    assert relations.parent_of(db, world["parent"].id) is None, "부모에게 부모가 생겼다"


def test_the_leaf_rule_now_changes_the_number(db, world):
    """🔴 여기가 핵심이다 — **값이 실제로 달라져야** 리프 판정이 사는 것이다.

    부모(진행) + 자식(완료) 두 건에서:
      · 부모까지 세면  → 2건 중 1건 완료 = 50%
      · 리프만 세면    → 1건 중 1건 완료 = 100%
    두 값이 다르므로, 이 시험은 리프 판정이 **실제로 적용됐는지**를 가른다.
    (입력이 비어 있으면 둘 다 50% 라 아무것도 증명하지 못한다.)
    """
    from app.projects.progress import compute_progress, task_from_ticket

    relations.sync_parent_links(db)
    db.commit()

    rows = [world["parent"], world["child"]]
    # 제품이 쓰는 함수 그대로 만든다. 손으로 `Task(...)` 를 조립하면 축을 바꾸는 날
    # 이 시험만 옛 축으로 남아 초록을 찍는다.
    parents = relations.parent_map(db, [r.id for r in rows])
    tasks = [task_from_ticket(r, parents.get(r.id)) for r in rows]
    result = compute_progress(tasks)

    assert result.basis.parent_tasks_excluded == 1, (
        f"부모가 제외되지 않았다 — 관계 표가 비어 있다는 뜻이다: {result.basis}"
    )
    assert result.percent == 100.0, (
        f"리프만 세면 100% 여야 한다(부모까지 세면 50%): {result.percent} / {result.basis}"
    )


def test_a_parent_that_is_not_in_the_mirror_creates_no_relation(db, portal_project, make_ticket):
    """**반례** — 가리키는 부모가 표에 없으면 관계를 만들지 않는다.

    없는 부모를 억지로 이으면 그 자식은 어느 목록에도 안 잡히는 고아가 되고, 그 사실은
    진행률이 이유 없이 낮게 나오는 것으로만 드러난다.
    """
    make_ticket(
        page_id="page-orphan", project=portal_project, tid=9, title="부모가 없는 하위",
        status="진행", parent_page_id="page-not-here",
    )
    result = relations.sync_parent_links(db)
    db.commit()
    assert result["added"] == 0, f"없는 부모에 관계를 만들었다: {result}"
