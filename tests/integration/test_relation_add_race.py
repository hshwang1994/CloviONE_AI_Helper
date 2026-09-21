"""같은 관계 잇기가 동시에 N 번 와도 관계는 하나이고 전부 200 이다 (P4 · B-2).

`relations.add` 는 재실행 안전이다 — 이미 있으면 그 행을 돌려준다. 그런데 「이미 있나」를 읽고 나서 넣으므로, 같은
요청 둘이 둘 다 「없다」를 보고 늦은 삽입이 유일 인덱스(`uq_trel_edge` — 하위 작업이면 `uq_trel_single_parent` 도)에
부딪혔다. 그 위반은 요청 경계의 안전망까지 가서 일반 문장의 409 가 됐다. 이제 늦은 삽입은 SAVEPOINT 안에서 지고 먼저
들어간 행을 다시 읽는다 — 같은 관계면 200(재실행), 같은 티켓에 **다른** 상위 작업이 먼저 들어갔으면 사전 검사와 같은
문장의 409 다.

이 파일은 전용 DB 가 필요하다(D-190).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import DUPLICATE_WRITE_MESSAGE
from app.work import relations as relations_mod
from app.work.models import REL_RELATES_TO, REL_SUBTASK_OF, TicketRelation
from tests.fixtures.race import Window, fire, hold_after, messages, statuses

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

N = 8


@pytest.fixture()
def tickets(make_ticket, portal_project):
    return {
        key: make_ticket(project=portal_project, title=f"관계 티켓 {key}")
        for key in ("a", "b", "c")
    }


def _edges(db, **where) -> list[TicketRelation]:
    db.rollback()   # 다른 연결이 커밋한 것을 새 트랜잭션에서 본다
    stmt = select(TicketRelation)
    for column, value in where.items():
        stmt = stmt.where(getattr(TicketRelation, column) == value)
    return db.execute(stmt).scalars().all()


def _post(client, csrf, ticket_id: str, to_id: str, kind: str):
    return client.post(
        f"/api/work/tickets/{ticket_id}/relations",
        json={"to_ticket_id": to_id, "kind": kind},
        headers={"X-CSRF-Token": csrf},
    )


@pytest.mark.parametrize("kind", [REL_RELATES_TO, REL_SUBTASK_OF])
def test_the_same_relation_n_times_at_once_is_one_row_and_all_200(
    client, login_as, db, tickets, monkeypatch, kind,
):
    a, b = tickets["a"], tickets["b"]
    csrf = login_as("system_admin")
    window = Window(N)
    hold_after(monkeypatch, relations_mod, "_edge", window)

    responses = fire(N, lambda _i: _post(client, csrf, a.id, b.id, kind))

    assert window.opened, "요청들이 확인 뒤에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert codes == [200] * N, [(c, getattr(r, "text", r)) for c, r in zip(codes, responses)]
    assert len(_edges(db, kind=kind)) == 1
    # 모든 응답이 같은 관계 하나를 말한다 — 진 요청도 먼저 들어간 행을 돌려받았다.
    assert all(
        [(x["kind"], x["ticket_id"]) for x in r.json()["relations"]] == [(kind, b.id)]
        for r in responses
    )


def test_two_parents_at_once_leave_one_parent_and_the_rest_hear_the_parent_sentence(
    client, login_as, db, tickets, monkeypatch,
):
    """하위 작업의 상위는 하나다. 반은 B 를, 반은 C 를 상위로 동시에 고르면 하나만 들어간다 — 이긴 상위와 같은 것을
    고른 요청은 200(재실행)이고, 다른 상위를 고른 요청은 사전 검사와 같은 문장의 409 다."""
    a, b, c = tickets["a"], tickets["b"], tickets["c"]
    csrf = login_as("system_admin")
    window = Window(N)
    hold_after(monkeypatch, relations_mod, "_edge", window)
    parents = [b.id if i % 2 == 0 else c.id for i in range(N)]

    responses = fire(N, lambda i: _post(client, csrf, a.id, parents[i], REL_SUBTASK_OF))

    assert window.opened, "요청들이 확인 뒤에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert all(code in (200, 201, 409) for code in codes), codes
    rows = _edges(db, kind=REL_SUBTASK_OF, from_ticket_id=a.id)
    assert len(rows) == 1, [r.to_ticket_id for r in rows]
    winner = rows[0].to_ticket_id
    for parent, code in zip(parents, codes):
        assert code == (200 if parent == winner else 409), (parent, winner, codes)
    conflicts = messages(responses, 409)
    assert conflicts == [relations_mod.PARENT_TAKEN] * (N // 2), conflicts
    assert DUPLICATE_WRITE_MESSAGE not in conflicts, "경합이 요청 경계의 안전망까지 갔다"
