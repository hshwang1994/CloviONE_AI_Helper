"""프로젝트가 섞인 판·백로그에서도 **놓은 자리가 그대로 순위**다 (B5).

## 이 파일이 태어난 이유

rank 는 전역 수직선인데(`_rank_keyset_page` 가 프로젝트 파티션 없이 값으로 정렬)
이웃 조회(`rank.neighbours`)만 **옮기는 카드의 프로젝트**로 좁혀 있었다 — 단일
프로젝트 화면을 겨눈 설계다. 프로젝트 필터가 「전체」인 판·백로그에서 타 프로젝트
카드 옆에 놓으면 이웃이 (None, None) 이 되어 카드가 맨 뒤로 떨어졌다. 놓은 자리와
무관하게, 오류 한 줄 없이. 서버 주석(service.py)이 이 결함을 알고 「맨 위/맨
아래」 경로만 우회해 둔 상태였다 — 드래그 경로가 남아 있었다.

이웃 id 는 클라이언트 입력이므로 **가시성 범위**로 읽는다 — 범위 밖 id 는 미존재와
같은 모양(이웃 없음 → 맨 뒤 폴백)으로 떨어져 순위도 존재도 새지 않는다. 그 음성
시험은 `tests/security/test_work_board_scope.py` 쪽에 있다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes

pytestmark = pytest.mark.integration

BOSS = "mixed-rank-boss@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    """프로젝트 둘, 백로그 넉 장 — 순위가 서로 얽혀 있다: a1(100) b1(200) b2(300) a2(400)."""
    boss = make_user(BOSS, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    db.commit()

    def project(name, page):
        return work_codes.insert_with_code(
            db, Project(name=name, org_id=DEFAULT_ORG_ID, notion_page_id=page)
        )

    alpha = project("알파", "mixed-proj-a")
    beta = project("베타", "mixed-proj-b")

    def ticket(n, proj, rank):
        row = Ticket(
            title=f"티켓 {n}", notion_page_id=f"mixed-page-{n}", project_uid=proj.id,
            project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
            source="notion", notion_ticket_number=n, seq=n,
            backlog_rank=Decimal(rank),
        )
        db.add(row)
        db.flush()
        return row

    a1 = ticket(1, alpha, 100)
    b1 = ticket(2, beta, 200)
    b2 = ticket(3, beta, 300)
    a2 = ticket(4, alpha, 400)
    db.commit()
    return {"boss": boss, "alpha": alpha, "beta": beta, "a1": a1, "b1": b1, "b2": b2, "a2": a2}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS)}


def _move(client, login_as, ticket_id, body):
    return client.post(
        f"/api/work/board/{ticket_id}/move", json=body, headers=_hdr(login_as)
    )


def _backlog_order(client, login_as):
    body = client.get("/api/work/backlog?limit=50", headers=_hdr(login_as)).json()
    return [row["title"] for row in body["items"]]


def test_dropping_between_two_foreign_cards_lands_exactly_there(client, login_as, db, world):
    """🔴 타 프로젝트 카드 둘 사이에 놓으면 **그 사이**다 — 맨 뒤가 아니다."""
    r = _move(
        client, login_as, world["a1"].id,
        {"reorder": True, "before_id": world["b1"].id, "after_id": world["b2"].id,
         "base_version": 1},
    )
    assert r.status_code == 200, r.text
    db.commit()
    db.expire_all()
    placed = db.get(Ticket, world["a1"].id).backlog_rank
    assert Decimal(200) < placed < Decimal(300), f"이웃 사이가 아니다: {placed}"
    assert _backlog_order(client, login_as) == ["티켓 2", "티켓 1", "티켓 3", "티켓 4"]


def test_dropping_beside_a_mixed_pair_lands_exactly_there(client, login_as, db, world):
    """이웃이 한쪽만 타 프로젝트여도 같다 — 반쪽 좁히기(150 같은 어긋난 값)가 아니다."""
    # a2(400) 를 b1(200) 과 b2(300) 사이로 — 옛 코드는 b1·b2 둘 다 남의 프로젝트라
    # (None, None) → 자기 프로젝트 맨 뒤(500)로 보냈다.
    r = _move(
        client, login_as, world["a2"].id,
        {"reorder": True, "before_id": world["b1"].id, "after_id": world["b2"].id,
         "base_version": 1},
    )
    assert r.status_code == 200, r.text
    db.commit()
    db.expire_all()
    placed = db.get(Ticket, world["a2"].id).backlog_rank
    assert Decimal(200) < placed < Decimal(300), f"이웃 사이가 아니다: {placed}"
    assert _backlog_order(client, login_as) == ["티켓 1", "티켓 2", "티켓 4", "티켓 3"]


def test_same_project_reorder_still_works(client, login_as, db, world):
    """반례 — 단일 프로젝트 화면의 드래그(같은 프로젝트 이웃)는 그대로 정확하다."""
    # a1(100) 을 a2(400) 뒤로.
    r = _move(
        client, login_as, world["a1"].id,
        {"reorder": True, "before_id": world["a2"].id, "after_id": None,
         "base_version": 1},
    )
    assert r.status_code == 200, r.text
    db.commit()
    db.expire_all()
    placed = db.get(Ticket, world["a1"].id).backlog_rank
    assert placed > Decimal(400), f"뒤가 아니다: {placed}"
    assert _backlog_order(client, login_as) == ["티켓 2", "티켓 3", "티켓 4", "티켓 1"]


def test_top_and_bottom_ignore_unranked_rows(client, login_as, db, world):
    """「맨 아래」는 값 있는 마지막 카드의 **뒤**다 — 순위 없는 행이 섞여 있어도.

    옛 전량 로드는 NULLS LAST 의 마지막 행(NULL)을 읽어 STEP 근처 값을 만들었다 —
    자리 겹침 후보였다. MIN/MAX 는 NULL 을 무시한다.
    """
    unranked = Ticket(
        title="티켓 9", notion_page_id="mixed-page-9", project_uid=world["alpha"].id,
        project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
        source="notion", notion_ticket_number=9, seq=9,
    )
    db.add(unranked)
    db.commit()

    r = _move(
        client, login_as, world["a1"].id,
        {"reorder": True, "to_position": "bottom", "base_version": 1},
    )
    assert r.status_code == 200, r.text
    db.commit()
    db.expire_all()
    placed = db.get(Ticket, world["a1"].id).backlog_rank
    assert placed > Decimal(400), f"값 있는 마지막(400) 뒤가 아니다: {placed}"
