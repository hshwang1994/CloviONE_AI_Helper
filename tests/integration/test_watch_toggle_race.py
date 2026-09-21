"""관찰하기를 동시에 N 번 눌러도 전부 200 이고 관찰자 행은 하나다 (P4 · B-2).

`watch` 는 재실행 안전이다 — 이미 그 상태면 아무것도 안 한다. 그런데 켜기는 「이미 있나」를 읽고 나서 넣으므로,
동시에 온 같은 요청 둘이 둘 다 「없다」를 보고 늦은 삽입이 기본 키(`ticket_watchers_pkey`)에 부딪혔다. 그 위반은
요청 경계의 안전망까지 가서 「같은 항목이 이미 있어」 409 가 됐다 — 관찰하기를 두 번 누른 사람에게 오류를 보인 셈이다.
이제 늦은 삽입은 SAVEPOINT 안에서 지고 「바뀐 것 없음」(200 · `changed: false`)으로 답한다.

끄기는 행 하나를 지우는 문장 하나다. 동시에 N 번 끄면 먼저 지운 하나만 `changed: true` 이고 나머지는 지울 것이
없다(`false`) — 예전의 ORM 객체 삭제는 동시에 끈 요청 모두에 「바뀌었다」고 답했다(여덟 중 여덟).

이 파일은 전용 DB 가 필요하다(D-190).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.work import service as work_service
from app.work.models import TicketWatcher
from tests.fixtures.race import Window, fire, hold_after, statuses

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

N = 8


@pytest.fixture()
def ticket(make_ticket, portal_project):
    return make_ticket(project=portal_project, title="관찰할 티켓")


def _watchers(db, ticket_id: str) -> int:
    db.rollback()   # 다른 연결이 커밋한 것을 새 트랜잭션에서 본다
    return db.execute(
        select(func.count()).select_from(TicketWatcher).where(TicketWatcher.ticket_id == ticket_id)
    ).scalar_one()


def _hold_after_watcher_lookup(monkeypatch, window: Window) -> None:
    """「이미 관찰 중인가」를 읽은 **뒤에** 문 앞에서 기다리게 한다 — N 개가 모두 「아니다」를 본 뒤에 넣는다."""
    real_get = OrmSession.get

    def held(self, entity, ident, *args, **kwargs):
        found = real_get(self, entity, ident, *args, **kwargs)
        if entity is TicketWatcher:
            window.wait()
        return found

    monkeypatch.setattr(OrmSession, "get", held)


def test_watching_n_times_at_once_is_one_row_and_all_200(client, login_as, db, ticket, monkeypatch):
    csrf = login_as("system_admin")
    window = Window(N)
    _hold_after_watcher_lookup(monkeypatch, window)

    responses = fire(N, lambda _i: client.post(
        f"/api/work/tickets/{ticket.id}/watch", json={"watching": True}, headers={"X-CSRF-Token": csrf},
    ))

    assert window.opened, "요청들이 확인 뒤에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert codes == [200] * N, [(c, getattr(r, "text", r)) for c, r in zip(codes, responses)]
    assert [r.json()["changed"] for r in responses].count(True) == 1
    assert all(r.json()["watching"] is True for r in responses)
    assert _watchers(db, ticket.id) == 1


def test_unwatching_n_times_at_once_leaves_no_row_and_all_200(client, login_as, db, ticket, monkeypatch):
    csrf = login_as("system_admin")
    first = client.post(
        f"/api/work/tickets/{ticket.id}/watch", json={"watching": True}, headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200 and first.json()["changed"] is True, first.text
    # 끄기에는 사전 검사가 없다 — 요청들이 티켓을 읽은 뒤(끄기 바로 앞)에서 만나게 해 N 개가 한꺼번에 지우러 간다.
    window = Window(N)
    hold_after(monkeypatch, work_service, "load_ticket_in_scope_or_404", window)

    responses = fire(N, lambda _i: client.post(
        f"/api/work/tickets/{ticket.id}/watch", json={"watching": False}, headers={"X-CSRF-Token": csrf},
    ))

    assert window.opened, "요청들이 끄기 앞에서 만나지 못했다 — 경합을 재현하지 못했다"
    codes = statuses(responses)
    assert codes == [200] * N, [(c, getattr(r, "text", r)) for c, r in zip(codes, responses)]
    assert [r.json()["changed"] for r in responses].count(True) == 1
    assert _watchers(db, ticket.id) == 0


def test_watching_twice_in_a_row_is_a_no_op(client, login_as, db, ticket):
    """반례 — 순서대로 두 번 켜도 둘째는 200 · `changed: false` 다(재실행 안전)."""
    csrf = login_as("system_admin")
    url = f"/api/work/tickets/{ticket.id}/watch"
    one = client.post(url, json={"watching": True}, headers={"X-CSRF-Token": csrf})
    two = client.post(url, json={"watching": True}, headers={"X-CSRF-Token": csrf})
    assert (one.status_code, one.json()["changed"]) == (200, True), one.text
    assert (two.status_code, two.json()["changed"]) == (200, False), two.text
    assert _watchers(db, ticket.id) == 1
