"""오프보딩 API — 미리보기 → 실행 → **되돌리기**를 실제 HTTP 경로에서 고정한다 (Phase 6).

계획서가 이 그룹의 최우선으로 지목한 항목이고, 잘못 누르면 사람 하나의 업무가 통째로 남에게
넘어가고 계정이 잠긴다. 그래서 여기서 못박는 것은 "동작한다"가 아니라 **"되돌아온다"**다:

  * 실행 후 티켓을 **다시 읽어** 담당자가 실제로 바뀌었는지 본다(응답만 믿지 않는다).
  * 되돌린 뒤에도 **다시 읽어** 원래 담당자로 돌아왔는지 본다.
  * 12건 중 일부가 실패하면 실패 건수가 응답에 그대로 나온다(부분 실패를 숨기지 않는다).
  * 순서가 계약이다: 티켓을 먼저 옮기고 계정을 비활성화한다. 반대로 하면 비활성 사용자가
    '앱이 모르는 외부 담당자'로 보여 쓰기 경로가 그를 보존해 버려 티켓이 안 옮겨진다.

티켓은 **자체 DB**(`tickets` 표)에 있다. S14 로 정본이 그리로 옮겨 왔고, 오프보딩이 지키는
네 가지는 티켓이 어디 저장되든 같아야 하는 것들이라 새 정본 위에서 그대로 확인한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.models_base import join_names, split_names
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.offboarding.models import OffboardingRun, OffboardingTicketMove
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.users.models import User
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

LEAVER_NID = "notion-leaver"
SUCCESSOR_NID = "notion-successor"
OUTSIDER_NID = "notion-outsider"


@pytest.fixture()
def tickets(db, make_project):
    """퇴사자가 3건을 갖고 있고, 그중 한 건은 다른 사람과 공동 담당이다.

    공동 담당 건이 중요하다 — 담당자 목록을 통째로 덮어쓰면 같이 일하던 사람이 조용히 빠진다.

    세 건 다 `notion_page_id` 를 갖고 있다 — 이관해 온 티켓의 모습이고, 오프보딩 화면이
    당분간 다루는 티켓이 전부 그것이다(옛 딥링크가 계속 사는 쪽이다). 담당자는 자체 DB
    에서도 소스 user id 로 저장되므로(`tickets.assignee_notion_ids`), `people` 픽스처의
    매핑이 있어야 「이 티켓은 퇴사자 것」이 성립한다.
    """
    project = make_project(name="알파", external_id="proj-1")
    for page_id, tid, title, due, holders in (
        ("page-1", 101, "혼자 담당 A", "2026-09-01", [LEAVER_NID]),
        ("page-2", 102, "혼자 담당 B", "2026-09-02", [LEAVER_NID]),
        ("page-3", 103, "공동 담당", "2026-09-03", [LEAVER_NID, OUTSIDER_NID]),
    ):
        db.add(TicketCache(
            notion_page_id=page_id, org_id=DEFAULT_ORG_ID, notion_ticket_number=tid,
            title=title, status="진행", due_date=due,
            project_ids=join_names(["proj-1"]), project_uid=project.id,
            project_link=PROJECT_LINK_OK, project_names=join_names([project.name]),
            assignee_notion_ids=join_names(holders),
        ))
    db.commit()
    return project


@pytest.fixture()
def people(db, make_user):
    """퇴사자·후임·외부 담당자 + 담당자 매핑. 관리자는 별도로 로그인한다."""
    made = {}
    for key, email, nid, name in (
        ("leaver", "leaver@goodmit.co.kr", LEAVER_NID, "퇴사자"),
        ("successor", "successor@goodmit.co.kr", SUCCESSOR_NID, "후임"),
        ("outsider", "outsider@goodmit.co.kr", OUTSIDER_NID, "공동담당"),
    ):
        user = make_user(email=email, role="user", display_name=name)
        db.add(UserNotionMapping(
            id=f"map-{key}", user_id=user.id, notion_user_id=nid,
            status=STATUS_VERIFIED, source=SOURCE_MANUAL,
        ))
        made[key] = user
    db.commit()
    return {k: v.id for k, v in made.items()}


@pytest.fixture()
def admin(client, make_user, db):
    make_user(email="boss@goodmit.co.kr", role="system_admin", display_name="관리자")
    response = client.post(
        "/login", json={"email": "boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _assignee_ids(db, page_id: str) -> list[str]:
    """티켓 행에서 **직접** 읽는다 — API 응답이 아니라 저장된 실제 상태를 본다.

    요청이 커밋한 값을 보려면 시험 세션이 들고 있는 사본을 먼저 버려야 한다.
    """
    db.expire_all()
    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()
    if row is None:
        raise AssertionError(f"{page_id} 행이 없다")
    return split_names(row.assignee_notion_ids)


# ── 미리보기 ──────────────────────────────────────────────────────────────────

def test_preview_lists_the_tickets_the_leaver_actually_holds(client, admin, people, tickets):
    body = client.get(f"/api/admin/offboarding/preview/{people['leaver']}").json()

    assert body["notion_mapped"] is True
    assert body["ticket_count"] == 3
    assert {t["tid"] for t in body["tickets"]} == {101, 102, 103}
    assert body["tickets_error"] is None
    # 후임 후보에 퇴사자 본인은 없다.
    candidate_ids = {c["user_id"] for c in body["successor_candidates"]}
    assert people["successor"] in candidate_ids
    assert people["leaver"] not in candidate_ids


def test_preview_reports_a_ticket_lookup_failure_instead_of_showing_an_empty_list(
    client, admin, people, tickets, monkeypatch
):
    """티켓 조회가 죽은 순간 목록이 빈 채로 뜨면 관리자는 '티켓이 없구나' 하고 실행해 버린다.

    자체 DB 로 옮겨 와도 조회가 실패할 수 있다(잠금·타임아웃·연결 끊김). 실패하는 것은
    막을 수 없지만 **실패를 빈 목록으로 위장하는 것**은 막아야 해서, 저장소가 터지는
    상황을 만들어 그 답이 어떻게 나오는지 본다.
    """
    def _boom(*args, **kwargs):
        raise RuntimeError("티켓 표를 읽지 못했다")

    monkeypatch.setattr(client.app.state.repositories.tickets, "list_by_assignee", _boom)
    body = client.get(f"/api/admin/offboarding/preview/{people['leaver']}").json()

    assert body["ticket_count"] == 0
    assert body["tickets_error"], "실패를 빈 목록으로 위장했다"


def test_preview_checklist_flags_a_missing_notion_link(client, admin, make_user, db):
    plain = make_user(email="nomap@goodmit.co.kr", role="user", display_name="미연결")
    db.commit()
    body = client.get(f"/api/admin/offboarding/preview/{plain.id}").json()

    checks = {c["key"]: c for c in body["onboarding"]}
    assert checks["notion"]["ok"] is False
    assert body["notion_mapped"] is False


# ── 실행 ──────────────────────────────────────────────────────────────────────

def _run(client, csrf, user_id, **body):
    return client.post(
        f"/api/admin/offboarding/run/{user_id}", json=body,
        headers={"X-CSRF-Token": csrf},
    )


def test_run_moves_tickets_and_then_deactivates(client, admin, people, tickets, db):
    response = _run(
        client, admin, people["leaver"],
        ticket_page_ids=["page-1", "page-2", "page-3"],
        successor_user_id=people["successor"], deactivate=True, archive=False,
    )
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert run["status"] == "completed"
    assert (run["ticket_total"], run["ticket_moved"], run["ticket_failed"]) == (3, 3, 0)
    assert run["deactivated"] is True

    # ✅ 응답이 아니라 **저장소를 다시 읽어** 확인한다.
    assert _assignee_ids(db, "page-1") == [SUCCESSOR_NID]
    assert _assignee_ids(db, "page-2") == [SUCCESSOR_NID]
    # 공동 담당자는 그대로 남아 있어야 한다(덮어쓰기 금지).
    assert set(_assignee_ids(db, "page-3")) == {OUTSIDER_NID, SUCCESSOR_NID}

    db.expire_all()
    assert db.get(User, people["leaver"]).active is False


def test_run_without_a_successor_leaves_the_tickets_unassigned(client, admin, people, tickets, db):
    response = _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"], deactivate=False,
    )
    assert response.status_code == 200, response.text
    assert _assignee_ids(db, "page-1") == []


def test_partial_failure_is_reported_not_hidden(client, admin, people, tickets):
    """3건 중 없는 페이지 하나가 섞이면 '2건 성공 1건 실패'로 보여야 한다."""
    response = _run(
        client, admin, people["leaver"],
        ticket_page_ids=["page-1", "page-does-not-exist", "page-2"],
        successor_user_id=people["successor"], deactivate=False,
    )
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert run["status"] == "partial"
    assert (run["ticket_moved"], run["ticket_failed"]) == (2, 1)
    statuses = {m["ticket_page_id"]: m["status"] for m in response.json()["moves"]}
    assert statuses["page-does-not-exist"] == "failed"
    assert statuses["page-1"] == "moved"


def test_the_order_is_tickets_then_deactivation(client, admin, people, tickets, db):
    """순서가 뒤집히면 티켓이 **조용히 안 옮겨진다**(모듈 docstring의 이유).

    비활성 사용자는 담당자 해석에서 빠져 '앱이 모르는 외부 담당자'가 되고, 쓰기 경로가
    그런 담당자를 보존하도록 되어 있기 때문이다. 결과로 그것을 못박는다: 비활성화까지 한
    실행에서도 담당자는 실제로 바뀌어 있어야 한다.
    """
    _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"],
        successor_user_id=people["successor"], deactivate=True, archive=True,
    )
    assert LEAVER_NID not in _assignee_ids(db, "page-1")
    db.expire_all()
    leaver = db.get(User, people["leaver"])
    assert leaver.active is False and leaver.archived_at is not None


def test_cannot_offboard_yourself(client, admin, db):
    me = db.execute(
        select(User).where(User.email == "boss@goodmit.co.kr")
    ).scalar_one()
    response = _run(client, admin, me.id, ticket_page_ids=[], deactivate=True)
    assert response.status_code == 409, response.text


def test_unknown_fields_are_rejected(client, admin, people):
    """오타가 조용히 무시되면 '비활성화까지 했다'고 믿는데 계정은 열려 있게 된다."""
    response = _run(client, admin, people["leaver"], deactive=True)
    assert response.status_code == 422, response.text


# ── 되돌리기 ──────────────────────────────────────────────────────────────────

def test_undo_restores_both_the_tickets_and_the_account(client, admin, people, tickets, db):
    run_id = _run(
        client, admin, people["leaver"],
        ticket_page_ids=["page-1", "page-3"],
        successor_user_id=people["successor"], deactivate=True, archive=True,
    ).json()["run"]["id"]

    # 실행 직후 상태를 먼저 확인해 둔다(되돌리기가 진짜로 무언가를 되돌리는지 보려면 필요).
    assert _assignee_ids(db, "page-1") == [SUCCESSOR_NID]

    response = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "undone"
    assert response.json()["revert_failed"] == 0

    # ✅ 다시 읽어 확인 — 티켓이 원래 담당자에게 돌아왔다.
    assert _assignee_ids(db, "page-1") == [LEAVER_NID]
    assert set(_assignee_ids(db, "page-3")) == {LEAVER_NID, OUTSIDER_NID}

    db.expire_all()
    leaver = db.get(User, people["leaver"])
    assert leaver.active is True and leaver.archived_at is None


def test_undo_only_restores_what_this_run_actually_changed(client, admin, people, db):
    """원래 비활성이던 계정을 되돌리기가 활성으로 만들면 **없던 권한을 주는** 셈이 된다."""
    db.get(User, people["leaver"]).active = False
    db.commit()

    run_id = _run(
        client, admin, people["leaver"], ticket_page_ids=[], deactivate=True,
    ).json()["run"]["id"]
    # 이미 비활성이었으므로 이 실행은 계정을 '바꾸지 않았다'.
    with client.app.state.session_factory() as session:
        assert session.get(OffboardingRun, run_id).deactivated is False

    client.post(f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin})
    db.expire_all()
    assert db.get(User, people["leaver"]).active is False


def test_undo_twice_is_refused(client, admin, people, tickets):
    run_id = _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"],
        successor_user_id=people["successor"], deactivate=False,
    ).json()["run"]["id"]
    first = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert second.status_code == 409, second.text


def test_partially_failed_undo_can_be_retried_until_it_fully_succeeds(
    client, admin, people, tickets, db
):
    """UA-14: undone_at은 실패 여부와 무관하게 찍혔었다 — REVERTIBLE_MOVES가
    revert_failed를 재시도 대상으로 넣어 둔 것(되돌리기 재시도를 의도한 설계)과 모순돼,
    일부가 실패하면 그 실패한 티켓은 후임자에게 영구히 남았다(같은 run으로 다시
    undo()를 부르면 무조건 409 "이미 되돌린 실행입니다").

    되돌리기 중 한 건만 실패하게 만드는 방법으로 **휴지통**을 쓴다. 자체 DB 에서 「지금
    그 티켓에는 쓸 수 없다」의 실제 모습이 그것이고(`ensure_not_trashed`), 사람이 되돌려
    놓을 수 있는 상태라 재시도까지 한 흐름에서 볼 수 있다.
    """
    run_id = _run(
        client, admin, people["leaver"],
        ticket_page_ids=["page-1", "page-2"],
        successor_user_id=people["successor"], deactivate=False,
    ).json()["run"]["id"]

    # page-1을 휴지통에 넣어 되돌리기 중 그 건만 실패하게 만든다.
    trashed = client.post("/api/tickets/page-1/trash", headers={"X-CSRF-Token": admin})
    assert trashed.status_code == 200, trashed.text
    items = client.get("/api/trash").json()["items"]
    trash_id = next(i["id"] for i in items if i["notion_page_id"] == "page-1")

    first = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert first.status_code == 200, first.text
    assert first.json()["run"]["status"] == "undo_partial"
    assert first.json()["revert_failed"] == 1
    assert first.json()["run"]["undone_at"] is None, (
        "부분 실패인데 undone_at이 찍혔다 — 이러면 재시도가 영구히 막힌다"
    )
    # page-2는 이미 되돌아왔어야 한다(부분 실패가 성공한 건까지 덮으면 안 된다).
    assert _assignee_ids(db, "page-2") == [LEAVER_NID]
    # 실패한 건은 후임자에게 남아 있다 — 그래서 재시도가 필요하다(실패가 진짜였다는 증거이기도 하다).
    assert _assignee_ids(db, "page-1") == [SUCCESSOR_NID]

    # page-1을 복구하고 같은 run으로 다시 되돌린다 — 예전엔 여기서 409였다.
    restored = client.post(
        f"/api/trash/{trash_id}/restore", headers={"X-CSRF-Token": admin}
    )
    assert restored.status_code == 200, restored.text
    second = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert second.status_code == 200, second.text
    assert second.json()["run"]["status"] == "undone"
    assert second.json()["revert_failed"] == 0
    assert second.json()["run"]["undone_at"] is not None
    assert _assignee_ids(db, "page-1") == [LEAVER_NID]

    # 이제 정말로 완전히 되돌렸으니 세 번째 시도는 예전과 같이 거부돼야 한다.
    third = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert third.status_code == 409, third.text


def test_a_second_run_while_one_is_still_open_is_refused(client, admin, people, tickets):
    """UA-15: run_offboarding()은 대상에게 이미 열린(안 되돌린) 실행이 있는지 확인하지
    않았다 — 더블클릭·새로고침으로 두 번 실행되면 두 번째 실행의 before_user_ids가 이미
    첫 번째 실행이 넣은 후임을 "원래 담당자"로 기록해 되돌리기 계약이 깨진다."""
    first = _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"],
        successor_user_id=people["successor"], deactivate=False,
    )
    assert first.status_code == 200, first.text

    second = _run(
        client, admin, people["leaver"], ticket_page_ids=["page-2"],
        successor_user_id=people["successor"], deactivate=False,
    )
    assert second.status_code == 409, second.text


def test_a_new_run_is_allowed_once_the_previous_one_is_undone(client, admin, people, tickets):
    """오탐 방지 — 이전 실행을 되돌렸으면 같은 대상을 다시 오프보딩할 수 있어야 한다."""
    run_id = _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"],
        successor_user_id=people["successor"], deactivate=False,
    ).json()["run"]["id"]
    undo = client.post(
        f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin}
    )
    assert undo.status_code == 200, undo.text

    again = _run(
        client, admin, people["leaver"], ticket_page_ids=["page-2"],
        successor_user_id=people["successor"], deactivate=False,
    )
    assert again.status_code == 200, again.text


def test_the_open_run_dedup_is_also_a_real_db_constraint(db, people):
    """migration 0056의 부분 유일 인덱스 자체를 직접 확인한다 — 서비스 계층의 사전 확인은
    거의 동시에 오는 두 요청을 못 잡을 수 있어서(빠른 경로), DB 제약이 최종 방어선이다."""
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    from app.offboarding.models import OffboardingRun

    now = datetime(2026, 8, 11, 0, 0, 0)
    db.add(OffboardingRun(
        user_id=people["leaver"], actor_user_id=people["successor"],
        created_at=now, updated_at=now,
    ))
    db.commit()

    db.add(OffboardingRun(
        user_id=people["leaver"], actor_user_id=people["successor"],
        created_at=now, updated_at=now,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_move_rows_record_the_assignees_from_before_the_move(
    client, admin, people, tickets, db
):
    """되돌리기의 입력이 되는 값이다 — 여기가 비면 되돌리기는 아무것도 복원하지 못한다."""
    _run(
        client, admin, people["leaver"], ticket_page_ids=["page-3"],
        successor_user_id=people["successor"], deactivate=False,
    )
    move = db.execute(select(OffboardingTicketMove)).scalars().one()
    assert set(split_names(move.before_user_ids)) == {people["leaver"], people["outsider"]}
    assert set(split_names(move.after_user_ids)) == {people["successor"], people["outsider"]}


# ── 목록 ──────────────────────────────────────────────────────────────────────

def test_runs_are_listed_with_names(client, admin, people, tickets):
    _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"],
        successor_user_id=people["successor"], deactivate=False,
    )
    body = client.get("/api/admin/offboarding").json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["user_name"] == "퇴사자"
    assert row["successor_name"] == "후임"
    assert row["actor_name"] == "관리자"


# ── C3: 장부가 외부 부작용보다 먼저 사라지지 않는다 ─────────────────────────────

def _raise_lock(*a, **kw):
    raise RuntimeError("계정 보관 중 DB 잠금")


def test_the_ledger_survives_a_failure_in_the_account_step(
    client, admin, people, tickets, db, monkeypatch
):
    """계정 단계에서 실패해도 **이미 옮긴 티켓 기록은 남아야 한다** (C3).

    전에는 전부 한 트랜잭션이었다. `get_db` 는 예외가 나면 요청 세션을 통째로 롤백하므로
    ③④(계정 처리)에서 실패하면 — 권한 검사, DB 잠금, 100건 처리 중 타임아웃 —
    **재배정은 남고 로컬 기록은 전부 사라졌다.**

    그러면 관리자는 티켓이 옮겨진 줄 모르고, `undo()` 의 입력(`before_user_ids`)도 함께
    사라져 **되돌릴 방법이 없다.** 되돌릴 수 있다는 것이 이 모듈의 약속 넷 중 하나인데,
    실패 한 번이 그 약속을 조용히 취소했다.
    """
    from app.offboarding import service as off_service

    monkeypatch.setattr(off_service, "archive_user", _raise_lock)

    response = _run(
        client, admin, people["leaver"],
        ticket_page_ids=["page-1", "page-2"],
        successor_user_id=people["successor"], deactivate=False, archive=True,
    )
    assert response.status_code >= 500, f"터뜨린 실행이 성공했다: {response.status_code}"

    # 티켓은 실제로 바뀌었다 — 건별로 커밋했으므로 요청 롤백이 되돌려 주지 않는다.
    assert _assignee_ids(db, "page-1") == [SUCCESSOR_NID]

    # ✅ **새 세션**으로 읽는다. 요청 세션의 롤백을 견뎠는지가 요점이다.
    with client.app.state.session_factory() as session:
        runs = session.query(OffboardingRun).all()
        assert len(runs) == 1, "실행 기록이 통째로 사라졌다 — 무슨 일이 있었는지 알 수 없다"
        run = runs[0]
        assert run.status == "running", (
            f"끝까지 못 간 실행이 '{run.status}' 로 남았다 — 다 했다고 거짓말한다"
        )

        moves = session.query(OffboardingTicketMove).filter_by(run_id=run.id).all()
        assert len(moves) == 2, f"이동 기록이 {len(moves)}건만 남았다"
        assert {m.status for m in moves} == {"moved"}
        # 되돌리기의 입력이 살아 있어야 한다 — 이게 없으면 복구가 불가능하다.
        assert all(m.before_user_ids for m in moves), "직전 담당자 기록이 사라졌다"


def test_an_interrupted_run_can_still_be_undone(
    client, admin, people, tickets, db, monkeypatch
):
    """장부가 남아 있으므로 **중단된 실행도 되돌릴 수 있다** — 그게 남기는 이유다."""
    from app.offboarding import service as off_service

    monkeypatch.setattr(off_service, "archive_user", _raise_lock)
    _run(
        client, admin, people["leaver"], ticket_page_ids=["page-1"],
        successor_user_id=people["successor"], deactivate=False, archive=True,
    )
    monkeypatch.undo()

    with client.app.state.session_factory() as session:
        run_id = session.query(OffboardingRun).one().id

    r = client.post(f"/api/admin/offboarding/{run_id}/undo", headers={"X-CSRF-Token": admin})
    assert r.status_code == 200, r.text
    assert _assignee_ids(db, "page-1") == [LEAVER_NID], "되돌리기가 원상복구하지 못했다"
