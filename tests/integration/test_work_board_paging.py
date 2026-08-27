"""판·백로그 — 범위(scope)와 커서 페이징 (REAUDIT §8.1 · §8.5).

## 이 파일이 확인하는 것

1. `scope` 계약 — `execution`(기본, 완료·취소 제외) · `all`(포함) · `sprint`(필수 인자).
2. 열 커서 페이징 — 커서를 끝까지 따라가면 받은 카드 수 == `total`, 중복 0 · 누락 0.
   서버가 자르기 전에 센 값이 `total` 이어야 한다(옛 `BOARD_COLUMN_LIMIT` 는 200에서
   그냥 잘랐다).
3. 백로그 커서 페이징 — 같은 성질.
4. 「맨 위로/맨 아래로」— 화면에 없는 카드도 옮길 수 있다.
5. `GET /api/work/sprints` 의 `active` — 오늘에 걸린 활성 회차만 `true`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work.models import Sprint

pytestmark = pytest.mark.security

BOSS = "board-paging-boss@goodmit.co.kr"


@pytest.fixture()
def paging_world(db, make_user):
    dept = Department(name="페이징팀", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()

    boss = make_user(BOSS, role="admin", display_name="페이징팀장")
    boss.department_id = dept.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = dept.id
    db.commit()

    project = work_codes.insert_with_code(
        db, Project(name="페이징 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=dept.id, notion_page_id="pg-proj"),
    )
    db.commit()
    return {"project": project}


def _make_tickets(db, project, *, count, status, prefix, rank_start=0):
    rows = []
    for i in range(count):
        row = Ticket(
            title=f"{prefix}-{i}", notion_page_id=f"{prefix}-page-{i}", project_uid=project.id,
            project_link=PROJECT_LINK_OK, status=status, org_id=DEFAULT_ORG_ID,
            source="notion", notion_ticket_number=1000 + rank_start + i, seq=1000 + rank_start + i,
            board_rank=rank_start + i, backlog_rank=rank_start + i,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    for row in rows:
        db.refresh(row)
    db.commit()
    return rows


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS)}


def _all_board_column_keys(client, headers, *, project_id, status_key, page_limit=10, scope=None):
    """커서를 끝까지 따라가며 그 열의 카드 key 전부를 모은다. 페이지 수 상한(안전핀)도 잰다."""
    keys: list[str] = []
    cursor = None
    pages = 0
    while True:
        pages += 1
        assert pages < 1000, "커서가 끝나지 않는다 — 무한 루프"
        params = {"project_id": project_id, "limit": page_limit}
        if scope:
            params["scope"] = scope
        if cursor:
            params["cursor"] = cursor
        r = client.get(f"/api/work/board/columns/{status_key}", params=params, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        keys.extend(c["key"] for c in body["cards"])
        cursor = body["next_cursor"]
        if not cursor:
            return keys, body["total"]


class TestScopeContract:
    def test_execution_excludes_done_and_cancelled(self, client, login_as, db, paging_world):
        project = paging_world["project"]
        _make_tickets(db, project, count=3, status="계획", prefix="open", rank_start=0)
        _make_tickets(db, project, count=2, status="완료", prefix="done", rank_start=10)
        _make_tickets(db, project, count=1, status="취소", prefix="cancel", rank_start=20)
        headers = _hdr(login_as)

        body = client.get(
            "/api/work/board", params={"project_id": project.id}, headers=headers,
        ).json()
        assert body["scope"] == "execution"
        assert body["summary"]["total"] == 3, body["summary"]
        done_col = next(c for c in body["columns"] if c["key"] == "완료")
        assert done_col["total"] == 0

    def test_all_includes_done_and_cancelled(self, client, login_as, db, paging_world):
        project = paging_world["project"]
        _make_tickets(db, project, count=3, status="계획", prefix="open2", rank_start=0)
        _make_tickets(db, project, count=2, status="완료", prefix="done2", rank_start=10)
        _make_tickets(db, project, count=1, status="취소", prefix="cancel2", rank_start=20)
        headers = _hdr(login_as)

        body = client.get(
            "/api/work/board", params={"project_id": project.id, "scope": "all"}, headers=headers,
        ).json()
        assert body["scope"] == "all"
        assert body["summary"]["total"] == 6, body["summary"]

    def test_unknown_scope_is_rejected(self, client, login_as, paging_world):
        headers = _hdr(login_as)
        r = client.get(
            "/api/work/board",
            params={"project_id": paging_world["project"].id, "scope": "everything"},
            headers=headers,
        )
        assert r.status_code == 422, r.text

    def test_scope_sprint_requires_sprint_id(self, client, login_as, paging_world):
        headers = _hdr(login_as)
        r = client.get(
            "/api/work/board",
            params={"project_id": paging_world["project"].id, "scope": "sprint"},
            headers=headers,
        )
        assert r.status_code in (400, 422), r.text


class TestColumnPaging:
    def test_cursor_to_the_end_matches_total_no_dup_no_gap(self, client, login_as, db, paging_world):
        project = paging_world["project"]
        rows = _make_tickets(db, project, count=23, status="계획", prefix="plan")
        headers = _hdr(login_as)

        # 첫 쪽은 board() 자체에서(작은 column_page_size 로 잘라, 여러 쪽이 실제로 필요하게 한다).
        first = client.get(
            "/api/work/board",
            params={"project_id": project.id, "column_page_size": 5}, headers=headers,
        ).json()
        col = next(c for c in first["columns"] if c["key"] == "계획")
        assert col["total"] == 23, col
        assert len(col["cards"]) == 5, "첫 쪽이 상한을 안 지켰다"
        assert col["next_cursor"], "23건인데 다음 쪽이 없다고 한다"

        seen = [c["key"] for c in col["cards"]]
        cursor = col["next_cursor"]
        pages = 1
        while cursor:
            pages += 1
            assert pages < 100
            r = client.get(
                "/api/work/board/columns/계획",
                params={"project_id": project.id, "limit": 5, "cursor": cursor},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            page = r.json()
            seen.extend(c["key"] for c in page["cards"])
            assert page["total"] == 23
            cursor = page["next_cursor"]

        expected = {t.canonical_key for t in rows}
        assert set(seen) == expected, f"누락/불일치: {expected - set(seen)}"
        assert len(seen) == len(set(seen)) == 23, "중복이 있다"

    def test_moving_someone_elses_project_column_is_empty_not_a_leak(
        self, client, login_as, db, make_user, paging_world,
    ):
        """§8.5 D-202 — 다음 쪽 요청도 범위 절이 상한보다 먼저다. 남의 프로젝트로
        `project_id` 를 바꿔도 커서로 카드가 새지 않는다(그 프로젝트 필터 자체가 이
        사람에게는 빈 결과를 낸다 — `test_work_board_scope.py` 의 반례와 같은 축)."""
        other_dept = Department(name="다른팀", org_id=DEFAULT_ORG_ID)
        db.add(other_dept)
        db.commit()
        other_project = work_codes.insert_with_code(
            db, Project(name="남의 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=other_dept.id,
                         notion_page_id="other-proj"),
        )
        _make_tickets(db, other_project, count=5, status="계획", prefix="theirs")
        headers = _hdr(login_as)
        r = client.get(
            "/api/work/board/columns/계획",
            params={"project_id": other_project.id, "limit": 5}, headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["cards"] == [] and body["total"] == 0, f"남의 프로젝트 카드가 샜다: {body}"


class TestBacklogPaging:
    def test_cursor_to_the_end_matches_total_no_dup_no_gap(self, client, login_as, db, paging_world):
        project = paging_world["project"]
        rows = _make_tickets(db, project, count=17, status="계획", prefix="bl")
        headers = _hdr(login_as)

        seen: list[str] = []
        cursor = None
        pages = 0
        total = None
        while True:
            pages += 1
            assert pages < 100
            params = {"project_id": project.id, "limit": 4}
            if cursor:
                params["cursor"] = cursor
            r = client.get("/api/work/backlog", params=params, headers=headers)
            assert r.status_code == 200, r.text
            body = r.json()
            total = body["total"]
            seen.extend(it["key"] for it in body["items"])
            cursor = body["next_cursor"]
            if not cursor:
                break

        assert total == 17
        expected = {t.canonical_key for t in rows}
        assert set(seen) == expected
        assert len(seen) == len(set(seen)) == 17


class TestMoveToPosition:
    def test_move_to_top_and_bottom_without_loading_the_whole_backlog(
        self, client, login_as, db, paging_world,
    ):
        project = paging_world["project"]
        rows = _make_tickets(db, project, count=10, status="계획", prefix="pos", rank_start=100)
        headers = _hdr(login_as)
        target = rows[5]  # 화면에 안 보여도(쪽을 하나만 받아도) 옮길 수 있어야 한다.

        r = client.post(
            f"/api/work/board/{target.id}/move",
            json={
                "reorder": True, "to_position": "top",
                "position_project_id": project.id,
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text

        listing = client.get(
            "/api/work/backlog", params={"project_id": project.id, "limit": 20}, headers=headers,
        ).json()
        assert listing["items"][0]["key"] == target.canonical_key, (
            f"맨 위로 보냈는데 첫 줄이 아니다: {[i['key'] for i in listing['items']]}"
        )

        r = client.post(
            f"/api/work/board/{target.id}/move",
            json={
                "reorder": True, "to_position": "bottom",
                "position_project_id": project.id,
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text
        listing = client.get(
            "/api/work/backlog", params={"project_id": project.id, "limit": 20}, headers=headers,
        ).json()
        assert listing["items"][-1]["key"] == target.canonical_key, (
            f"맨 아래로 보냈는데 마지막 줄이 아니다: {[i['key'] for i in listing['items']]}"
        )


class TestActiveSprintFlag:
    def test_only_the_sprint_covering_today_and_active_is_marked(
        self, client, login_as, db, paging_world, fake_clock, settings,
    ):
        # `uq_sprints_active` 는 (org, project) 당 활성 회차를 하나로 막는다 — 그래서
        # "기간은 지났지만 state=active" 시나리오는 **다른 프로젝트**에 둔다.
        #
        # 서버의 "오늘"은 앱의 `fake_clock`(고정 2026-07-14)을 KST 로 읽은 값이다 —
        # 이 시험의 파이썬 프로세스가 도는 실제 날짜(`date.today()`)와 다르다. 그 값으로
        # 회차 기간을 잡지 않으면 "오늘에 걸린 회차"가 실제로는 안 걸린다.
        from app.home.service import local_today

        project = paging_world["project"]
        other_project = work_codes.insert_with_code(
            db, Project(name="둘째 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=project.dept_id,
                        notion_page_id="second-proj"),
        )
        today = local_today(settings, fake_clock.now())
        active = Sprint(
            name="이번 회차", project_id=project.id, org_id=DEFAULT_ORG_ID,
            starts_on=today - timedelta(days=2), ends_on=today + timedelta(days=2), state="active",
        )
        planned_but_covers_today = Sprint(
            name="계획만 된 회차", project_id=project.id, org_id=DEFAULT_ORG_ID,
            starts_on=today - timedelta(days=1), ends_on=today + timedelta(days=1), state="planned",
        )
        active_but_past = Sprint(
            name="지난 활성 회차", project_id=other_project.id, org_id=DEFAULT_ORG_ID,
            starts_on=today - timedelta(days=20), ends_on=today - timedelta(days=10), state="active",
        )
        db.add_all([active, planned_but_covers_today, active_but_past])
        db.commit()

        headers = _hdr(login_as)
        body = client.get("/api/work/sprints", headers=headers).json()
        by_name = {s["name"]: s["active"] for s in body["sprints"]}
        assert by_name["이번 회차"] is True
        assert by_name["계획만 된 회차"] is False, "state=planned 인데 활성으로 표시됐다"
        assert by_name["지난 활성 회차"] is False, "기간이 지났는데 활성으로 표시됐다"
