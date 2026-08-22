"""Notion 의 **상위 작업** relation 이 실제로 미러되고, 리프 판정을 살린다.

## 왜 이 테스트가 필요했나

프로젝트 진행률을 앱이 다시 계산하는 이유는 셋이다:
  ① Notion 은 **취소를 완료로 센다**(status 그룹 `complete = [완료, 취소]`)
  ② **하위 작업이 부모와 이중 계산**된다
  ③ **예상 WD 가중이 무시**된다

①·③ 은 계산기만 고치면 되지만, ② 는 **부모가 누구인지 알아야** 한다. 그런데 진행률 계산기를
만든 시점에 `app/reports/notion_source.py` 의 파서가 상위 작업 relation 을 **읽지 않았다** —
그래서 표본 안에 부모로 지목된 작업이 하나도 없었고, **리프 판정이 아무 효과가 없었다.**

즉 계산기는 옳은데 **입력이 비어 있어서 Notion 과 똑같이 틀린 값**을 냈다. 순수 함수 테스트는
그 사실을 증명하지 못한다(X4 에서 배운 것과 같은 모양이다: 함수가 아니라 **배선**을 봐야 한다).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.tickets.models import TicketCache
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.integration

TOKEN_REF = "notion_report_token"
PARENT = "page-parent"
CHILD = "page-child"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    rows = [
        task_row(page_id=PARENT, tid=1, title="상위 작업", status="진행",
                 due="2026-09-01", people=[]),
        task_row(page_id=CHILD, tid=2, title="하위 작업", status="완료",
                 due="2026-09-01", people=[]),
    ]
    # 하위 작업이 상위를 가리킨다. `task_row` 가 이 속성을 안 만들면 여기서 직접 넣는다 —
    # 페이크가 실제 Notion 응답 모양을 흉내 내야 파서를 검사하는 뜻이 있다.
    rows[1]["properties"]["상위 작업"] = {"relation": [{"id": PARENT}]}
    return FakeNotionTasksDB(
        rows=rows,
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


def _sync(client, db):
    from app.tickets.sync import sync_tickets

    state = sync_tickets(
        db,
        outbound=client.app.state.outbound_client,
        settings=client.app.state.settings,
        now=datetime(2026, 8, 6, 9, 0, 0),
    )
    db.commit()
    return state


def _row(db, page_id):
    return db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()


def test_the_parent_relation_actually_reaches_the_mirror(client, settings, notion, db):
    """파서 → 동기화 → 컬럼까지 **끝에서 끝까지** 값이 도달하는가."""
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    _sync(client, db)
    db.expire_all()

    child = _row(db, CHILD)
    assert child is not None, "동기화가 안 됐다"
    assert child.parent_page_id == PARENT, (
        "상위 작업이 미러에 도달하지 않았다 — 리프 판정이 아무 효과가 없다"
    )
    assert _row(db, PARENT).parent_page_id is None, "부모에게 부모가 생겼다"

    # S6: 미러 컬럼은 **입력**이고 계층의 정본은 `ticket_relations` 다. 동기화가 그
    # 파생까지 돌지 않으면 진행률과 트리는 계층을 못 본다 — 컬럼만 확인하면 그 상태가
    # 초록으로 통과한다(이 파일이 처음 잡은 결함이 정확히 그 모양이었다).
    from app.work import relations

    parent_row = _row(db, PARENT)
    assert relations.parent_of(db, child.id) == parent_row.id, (
        "미러 컬럼은 찼는데 관계 표가 비어 있다 — 리프 판정이 아무 효과가 없다"
    )
    assert relations.parent_of(db, parent_row.id) is None, "부모에게 부모가 생겼다"


def test_the_leaf_rule_now_changes_the_number(client, settings, notion, db):
    """🔴 여기가 핵심이다 — **값이 실제로 달라져야** 리프 판정이 사는 것이다.

    부모(진행) + 자식(완료) 두 건에서:
      · 부모까지 세면  → 2건 중 1건 완료 = 50%
      · 리프만 세면    → 1건 중 1건 완료 = 100%
    두 값이 다르므로, 이 테스트는 리프 판정이 **실제로 적용됐는지**를 가른다.
    (입력이 비어 있으면 둘 다 50% 라 아무것도 증명하지 못한다.)
    """
    from app.projects.progress import compute_progress, task_from_ticket
    from app.work import relations

    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    _sync(client, db)
    db.expire_all()

    rows = db.execute(select(TicketCache)).scalars().all()
    # 제품이 쓰는 함수 그대로 만든다. 손으로 `Task(...)` 를 조립하면 축을 바꾸는 날
    # 이 시험만 옛 축으로 남아 초록을 찍는다.
    parents = relations.parent_map(db, [r.id for r in rows])
    tasks = [task_from_ticket(r, parents.get(r.id)) for r in rows]
    result = compute_progress(tasks)

    assert result.basis.parent_tasks_excluded == 1, (
        f"부모가 제외되지 않았다 — 미러가 비어 있다는 뜻이다: {result.basis}"
    )
    assert result.percent == 100.0, (
        f"리프만 세면 100% 여야 한다(부모까지 세면 50%): {result.percent} / {result.basis}"
    )
