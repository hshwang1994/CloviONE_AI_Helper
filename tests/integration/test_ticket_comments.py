"""티켓 댓글 API (PLAN Phase 3 §E) — 권한과 삭제 가시성을 실제 HTTP 경로에서 고정한다.

여기서 못박는 것:
  * 댓글은 `ticket_cache.id`(자체 UUID)에 걸린다. Notion page id 로 부르는 URL 과 저장 키가
    다르다는 뜻이라, 그 해석이 실제로 되는지 라우터 경유로 확인한다.
  * **남의 댓글은 못 지운다**(403). 운영자군은 지울 수 있고, 수정은 작성자 본인만 — 운영자도
    남의 문장을 고쳐 쓸 수는 없다.
  * 삭제는 soft-delete 이고 목록에 **툼스톤으로 남는다**. 행이 그냥 사라지면 이미 목록을 받아
    둔 클라이언트는 자기 화면이 낡았는지조차 알 수 없다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.tickets.models import TicketCache, TicketComment
from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.integration

PAGE_ID = "page-c001"
TOKEN_REF = "notion_report_token"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[task_row(page_id=PAGE_ID, tid=501, title="댓글 달 티켓", status="진행",
                       due="2026-09-01", people=[])],
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def api(client, settings, notion, make_user, portal_project):
    """Notion 토큰이 있고 페이크가 붙은 앱 + 로그인 헬퍼."""
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")

    def _login(email: str, *, role: str = "user", name: str = "사람"):
        from app.users.service import get_user_by_email

        # 존재 확인 세션을 **먼저 닫고** 만든다. 열어 둔 채로 만들면, 그 세션이 닫힐 때
        # 자기가 연 savepoint 로 되감으면서 방금 만든 사용자까지 함께 지운다.
        with client.app.state.session_factory() as db:
            missing = get_user_by_email(db, email) is None
        if missing:
            make_user(email=email, role=role, display_name=name)
        response = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
        assert response.status_code == 200, response.text
        return response.json()["csrf_token"]

    return _login


def _post(client, csrf, path, body):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf})


def test_comment_lands_on_the_ticket_cache_uuid_not_the_page_id(client, api, db):
    csrf = api("a@goodmit.co.kr", name="가")
    r = _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "첫 댓글"})
    assert r.status_code == 200, r.text
    assert [c["body"] for c in r.json()["comments"]] == ["첫 댓글"]

    cache = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == PAGE_ID)
    ).scalar_one()
    comment = db.execute(select(TicketComment)).scalars().one()
    # FK 는 우리 자체 UUID 다 — Notion page id 가 아니다(0023 티켓 캐시의 존재 이유).
    assert comment.ticket_uid == cache.id
    assert comment.ticket_uid != PAGE_ID


def test_listing_needs_no_notion_round_trip(client, api, notion):
    """댓글 목록은 자주 열린다 — 여기서 외부 왕복이 생기면 상세 화면이 통째로 느려진다."""
    csrf = api("a@goodmit.co.kr", name="가")
    _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "댓글"})
    before = len(notion.queries) + len(notion.patched)

    r = client.get(f"/api/tickets/{PAGE_ID}/comments")

    assert r.status_code == 200
    assert len(r.json()["comments"]) == 1
    assert len(notion.queries) + len(notion.patched) == before


def test_unknown_ticket_lists_empty_without_creating_a_row(client, api, db):
    """GET 이 쓰기를 하면 안 된다 — 존재하지 않는 티켓을 열어도 캐시 행이 생기지 않는다."""
    api("a@goodmit.co.kr", name="가")
    r = client.get("/api/tickets/page-does-not-exist/comments")
    assert r.status_code == 200
    assert r.json()["comments"] == []
    assert db.execute(select(TicketCache)).scalars().all() == []


def test_unknown_ticket_lists_empty_people_too(client, api):
    """빈 댓글 목록과 함께 people도 빈 묶음이어야 한다 — 누락이 아니라 자리는 있다."""
    api("a@goodmit.co.kr", name="가")
    r = client.get("/api/tickets/page-does-not-exist/comments")
    assert r.json()["people"] == {}


# ── 신원(people) ─────────────────────────────────────────────────────────────
# 사용자 지시(#13/#8): "게시글과 댓글에는 작성자의 부서·팀·직책을 함께 표시한다" —
# 게시판(app/board/router.py::_people_of, tests/integration/test_board_people_payload.py)은
# 이미 답한다. 여기서는 티켓 댓글도 같은 people 묶음을 실어 보내는지만 고정한다 — 조립 자체
# (조직명·사진 지문 등)는 core/people.py 쪽 테스트가 이미 검증했다.

def test_comment_authors_carry_department_and_title(client, api, db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department, JobTitle
    from app.users.service import get_user_by_email

    csrf = api("id-author@goodmit.co.kr", name="아이디작성자")
    dept = Department(name="인프라팀", org_id=DEFAULT_ORG_ID)
    jt = JobTitle(name="수석", org_id=DEFAULT_ORG_ID)
    db.add_all([dept, jt])
    db.flush()
    me = get_user_by_email(db, "id-author@goodmit.co.kr")
    me.department_id = dept.id
    me.title_id = jt.id
    db.commit()

    r = _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "댓글"})
    person = r.json()["people"][me.id]
    assert person["dept"] == "인프라팀", f"부서가 안 실린다: {person}"
    assert person["title"] == "수석", f"직책이 안 실린다: {person}"


def test_listing_carries_people_too(client, api, db):
    """쓰기 응답만이 아니라 GET 목록도 같은 묶음을 실어야 새로고침에도 신원을 안다."""
    from app.users.service import get_user_by_email

    csrf = api("id-list@goodmit.co.kr", name="아이디목록")
    _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "댓글"})

    listing = client.get(f"/api/tickets/{PAGE_ID}/comments").json()
    me = get_user_by_email(db, "id-list@goodmit.co.kr")
    assert me.id in listing["people"], f"목록 응답에 people 이 없다: {listing.keys()}"


# ── 권한 ─────────────────────────────────────────────────────────────────────

def test_another_user_cannot_delete_my_comment(client, api):
    mine = api("a@goodmit.co.kr", name="가")
    created = _post(client, mine, f"/api/tickets/{PAGE_ID}/comments", {"body": "내 댓글"})
    comment_id = created.json()["comment_id"]

    other = api("b@goodmit.co.kr", name="나")  # 로그인 전환
    r = client.delete(f"/api/tickets/comments/{comment_id}", headers={"X-CSRF-Token": other})

    assert r.status_code == 403, r.text
    listing = client.get(f"/api/tickets/{PAGE_ID}/comments").json()["comments"]
    assert listing[0]["deleted"] is False and listing[0]["body"] == "내 댓글"


def test_another_user_cannot_edit_my_comment(client, api):
    mine = api("a@goodmit.co.kr", name="가")
    comment_id = _post(
        client, mine, f"/api/tickets/{PAGE_ID}/comments", {"body": "내 댓글"}
    ).json()["comment_id"]

    other = api("b@goodmit.co.kr", name="나")
    r = client.patch(f"/api/tickets/comments/{comment_id}",
                     json={"body": "바꿔치기"}, headers={"X-CSRF-Token": other})

    assert r.status_code == 403, r.text


def test_operator_can_delete_but_not_edit_someone_elses_comment(client, api):
    """지우는 것(중재)과 고쳐 쓰는 것(위조)은 다르다 — 운영자에게도 후자는 없다."""
    mine = api("a@goodmit.co.kr", name="가")
    comment_id = _post(
        client, mine, f"/api/tickets/{PAGE_ID}/comments", {"body": "내 댓글"}
    ).json()["comment_id"]

    op = api("op@goodmit.co.kr", role="operator", name="운영")
    edited = client.patch(f"/api/tickets/comments/{comment_id}",
                          json={"body": "위조"}, headers={"X-CSRF-Token": op})
    assert edited.status_code == 403, edited.text

    removed = client.delete(f"/api/tickets/comments/{comment_id}",
                            headers={"X-CSRF-Token": op})
    assert removed.status_code == 200, removed.text
    assert removed.json()["comments"][0]["deleted"] is True


def test_author_can_edit_and_delete_their_own(client, api):
    csrf = api("a@goodmit.co.kr", name="가")
    comment_id = _post(
        client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "처음"}
    ).json()["comment_id"]

    edited = client.patch(f"/api/tickets/comments/{comment_id}",
                          json={"body": "고침"}, headers={"X-CSRF-Token": csrf})
    assert edited.status_code == 200, edited.text
    assert edited.json()["comments"][0]["body"] == "고침"

    removed = client.delete(f"/api/tickets/comments/{comment_id}",
                            headers={"X-CSRF-Token": csrf})
    assert removed.status_code == 200


# ── soft-delete 가시성 ───────────────────────────────────────────────────────

def test_order_is_insertion_order_even_when_timestamps_tie(client, api):
    """시계가 멈춘 테스트에서는 created_at 이 전부 같다 — 그때 순서를 UUID 로 깨면 목록이
    매 실행마다 뒤집힌다(무작위). 운영에서도 같은 순간에 달린 두 댓글의 앞뒤가 뒤바뀐다."""
    csrf = api("a@goodmit.co.kr", name="가")
    bodies = [f"댓글 {i}" for i in range(1, 8)]
    for body in bodies:
        _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": body})

    listing = client.get(f"/api/tickets/{PAGE_ID}/comments").json()["comments"]

    assert [c["body"] for c in listing] == bodies
    # 같은 시각인지 확인 — 이 성질이 없으면 위 단언이 우연히 통과한 것이다.
    assert len({c["created_at"] for c in listing}) == 1


def test_deleted_comment_stays_in_the_list_as_a_tombstone(client, api, db):
    csrf = api("a@goodmit.co.kr", name="가")
    comment_id = _post(
        client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "지울 댓글"}
    ).json()["comment_id"]
    _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "남을 댓글"})

    client.delete(f"/api/tickets/comments/{comment_id}", headers={"X-CSRF-Token": csrf})
    listing = client.get(f"/api/tickets/{PAGE_ID}/comments").json()["comments"]

    # 사라지지 않는다 — 사라지면 이미 목록을 받아 둔 클라이언트가 삭제를 알 수 없다.
    assert [c["deleted"] for c in listing] == [True, False]
    tombstone = listing[0]
    assert tombstone["body"] == ""          # 지운 내용은 다시 내려보내지 않는다
    assert tombstone["deleted_at"]
    assert tombstone["can_edit"] is False and tombstone["can_delete"] is False
    # 행은 남아 있다(감사·복구 여지).
    assert db.get(TicketComment, comment_id).deleted_at is not None


def test_a_deleted_comment_cannot_be_edited_back_to_life(client, api):
    csrf = api("a@goodmit.co.kr", name="가")
    comment_id = _post(
        client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "지울 댓글"}
    ).json()["comment_id"]
    client.delete(f"/api/tickets/comments/{comment_id}", headers={"X-CSRF-Token": csrf})

    r = client.patch(f"/api/tickets/comments/{comment_id}",
                     json={"body": "부활"}, headers={"X-CSRF-Token": csrf})

    assert r.status_code == 404, r.text


def test_deleting_twice_is_idempotent(client, api):
    csrf = api("a@goodmit.co.kr", name="가")
    comment_id = _post(
        client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "댓글"}
    ).json()["comment_id"]
    first = client.delete(f"/api/tickets/comments/{comment_id}",
                          headers={"X-CSRF-Token": csrf})
    second = client.delete(f"/api/tickets/comments/{comment_id}",
                           headers={"X-CSRF-Token": csrf})

    assert first.status_code == 200 and second.status_code == 200
    assert (first.json()["comments"][0]["deleted_at"]
            == second.json()["comments"][0]["deleted_at"])


# ── 입력 검증 · CSRF ─────────────────────────────────────────────────────────

def test_empty_comment_is_rejected(client, api):
    csrf = api("a@goodmit.co.kr", name="가")
    r = _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "   "})
    assert r.status_code == 422, r.text


def test_write_without_csrf_is_refused(client, api):
    api("a@goodmit.co.kr", name="가")
    r = client.post(f"/api/tickets/{PAGE_ID}/comments", json={"body": "댓글"})
    assert r.status_code == 403, r.text


def test_anonymous_cannot_read_comments(client, notion):
    r = client.get(f"/api/tickets/{PAGE_ID}/comments")
    assert r.status_code == 401


# ── 티켓이 Notion 에서 사라졌을 때 ───────────────────────────────────────────

def test_pruning_a_ticket_does_not_wedge_the_mirror(client, api, db, settings, fake_clock):
    """FK 가 걸린 댓글이 남아 있으면 캐시 행 DELETE 가 실패하고, sync 는 예외를 통째로
    삼키므로 티켓 미러가 조용히 멈춘다. ON DELETE CASCADE 로 그 함정을 막는다.

    `keep` 에 **다른 티켓을 남긴다** — 예전에는 `keep=set()` 으로 이 상황을 만들었지만
    이제 그건 `core.sync_prune` 의 바닥이 거부한다(소스가 0건이면 소스를 의심한다).
    여기서 확인하려는 것은 '정상적으로 한 건이 사라졌을 때 댓글이 DELETE 를 막지 않는가' 다.
    """
    from app.tickets.models import TicketCache as _TC
    from app.tickets import sync

    csrf = api("a@goodmit.co.kr", name="가")
    _post(client, csrf, f"/api/tickets/{PAGE_ID}/comments", {"body": "댓글"})
    assert db.execute(select(TicketComment)).scalars().all()

    survivor = _TC(notion_page_id="still-there", title="남는 티켓")
    db.add(survivor)
    db.flush()

    from datetime import datetime, timedelta

    from app.core.retention import MISSING_TICKET_GRACE_DAYS, purge_missing_tickets

    marked_at = datetime(2026, 8, 6, 9, 0)
    sync._prune(db, keep={"still-there"}, now=marked_at)  # 이 티켓만 Notion 에서 사라진 상황
    db.flush()

    # 0043: prune 은 **표시만** 한다 — 댓글은 그대로 살아 있다(한 회차 깜빡임이면 돌아온다).
    marked = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == PAGE_ID)
    ).scalar_one()
    assert marked.notion_missing_at == marked_at
    assert db.execute(select(TicketComment)).scalars().all(), "표시 단계에서 댓글이 사라졌다"

    # 유예를 넘기면 그때 진짜로 지운다. **이 테스트의 원래 목적이 여기로 옮겨왔다** —
    # FK 가 걸린 댓글이 남아 있어도 그 DELETE 가 실패하지 않아야 한다(실패하면 정리가
    # 조용히 멈춘다). 그걸 CASCADE 가 막아 준다.
    purge_missing_tickets(db, now=marked_at + timedelta(days=MISSING_TICKET_GRACE_DAYS + 1))
    db.flush()

    remaining = db.execute(select(TicketCache)).scalars().all()
    assert [r.notion_page_id for r in remaining] == ["still-there"]
    assert db.execute(select(TicketComment)).scalars().all() == []  # CASCADE 로 함께 정리
