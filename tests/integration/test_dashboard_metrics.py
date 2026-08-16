"""업무 대시보드(GET /api/home/work-dashboard) — **시점·범위·0과 없음**을 못 박는다.

이 세 가지가 이 화면이 조용히 거짓말하는 자리다.

1. **시점** — 클록을 UTC 2026-08-02 23:00 에 세운다. KST 로는 2026-08-03(월) 08:00 이다.
   UTC 날짜로 주를 정하면 창이 [07-27, 08-03) 이 되어 **한 주가 통째로 밀린다**(M4).
   그래서 표본을 창의 **양쪽 끝**에 놓는다: 월요일(08-03) 마감이 이번 주에 들어오는지와
   다음 주 월요일(08-10) 마감이 안 끼는지를 함께 본다. 한쪽만 보면 반쪽만 고치고 통과한다.

2. **범위** — 프로젝트·마일스톤은 `app/projects/repository.py::list_in_scope` 하나를 지난다.
   여기서 조건을 다시 걸지 않는다(중복으로 걸면 두 벌이 갈라진다). 대신 **다른 조직의
   프로젝트가 실제로 안 나오는지**를 응답으로 확인한다.

3. **0과 없음** — 세 가지가 서로 다른 사실이다.
     * health_score 가 0    → 재 봤더니 나쁘다(차질에 든다)
     * health_score 가 null → 아직 한 번도 안 쟀다(차질이 아니다, '못 잼'으로 따로 센다)
     * 티켓 소스가 죽음      → 내 몫을 **모른다**(0건이 아니다 → mine 은 null)

   0 으로 뭉개면 화면에서 셋이 똑같아 보이고, 그럴듯해서 아무도 신고하지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.board.models import Post  # noqa: F401  (모델 등록 - 시드에서 쓰지 않아도 import 순서 고정)
from app.core.security import hash_password
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department, Organization
from app.projects.models import (
    MILESTONE_DONE,
    MILESTONE_PLANNED,
    PROJECT_ACTIVE,
    Project,
    ProjectHealthSnapshot,
    ProjectMilestone,
)
from app.tickets.models import (
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketSyncState,
    join_names,
)
from app.users.models import User
from tests.fakes.clock import FakeClock
from tests.fakes.notion import FakeNotionTasksDB

pytestmark = pytest.mark.integration

# UTC 2026-08-02 23:00 = KST 2026-08-03(월) 08:00. **날짜가 갈리는 순간**이다.
NOW = datetime(2026, 8, 2, 23, 0, 0)
TODAY = "2026-08-03"
WEEK = {"start": "2026-08-03", "end_exclusive": "2026-08-10"}
SYNCED_AT = datetime(2026, 8, 2, 22, 0, 0)

PASSWORD = "Dash-Passw0rd!"
TOKEN_REF = "notion_report_token"

U_ME = "00000000-0000-4000-8000-0000000d0001"
U_MATE = "00000000-0000-4000-8000-0000000d0002"
N_ME = "notion-user-dash-me"
N_MATE = "notion-user-dash-mate"
EMAIL = "dash-me@goodmit.co.kr"

DEPT_MINE = "00000000-0000-4000-8000-0000000dd001"
DEPT_OTHER = "00000000-0000-4000-8000-0000000dd002"
ORG_OTHER = "00000000-0000-4000-8000-0000000dd0ff"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    """행을 하나도 주지 않는다 — 실수로 실시간 경로를 타면 숫자가 0 이 되어 바로 드러난다."""
    return FakeNotionTasksDB(rows=[]).install(fake_http)


def _cache(uid, page, *, tid, title, status, due, people):
    return TicketCache(
        id=uid, notion_page_id=page, notion_ticket_number=tid,
        url=f"https://www.notion.so/{page}", title=title, status=status,
        due_date=due, est_wd=1.0, priority=None,
        project_ids="", project_names=join_names(["대시 프로젝트"]),
        assignee_notion_ids=join_names(people),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _project(pid, name, *, dept, org=DEFAULT_ORG_ID, score=None, notion_status=None):
    return Project(
        id=pid, name=name, code=None, status=PROJECT_ACTIVE,
        org_id=org, dept_id=dept, health_score=score, progress_pct=None,
        notion_status=notion_status,
        created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _milestone(mid, project_id, name, *, due_on, status):
    return ProjectMilestone(
        id=mid, project_id=project_id, name=name, due_on=due_on, status=status,
        sort_order=0, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _seed(db) -> None:
    org_other = Organization(id=ORG_OTHER, slug="dash-org-b", name="다른조직")
    db.add(org_other)
    db.flush()  # 부서가 이 조직을 외래키로 가리킨다 - 순서를 SQLAlchemy 에 맡기면 깨진다.
    db.add_all([
        Department(id=DEPT_MINE, name="대시 우리팀", org_id=DEFAULT_ORG_ID),
        Department(id=DEPT_OTHER, name="대시 남의팀", org_id=ORG_OTHER),
    ])
    db.flush()

    db.add(User(id=U_ME, email=EMAIL, display_name="대시 나", role="user", active=True,
                org_id=DEFAULT_ORG_ID, department_id=DEPT_MINE,
                password_hash=hash_password(PASSWORD), must_change_password=False))
    db.add(User(id=U_MATE, email="dash-mate@goodmit.co.kr", display_name="대시 동료",
                role="user", active=True, org_id=DEFAULT_ORG_ID, department_id=DEPT_MINE,
                password_hash=hash_password(PASSWORD), must_change_password=False))
    db.flush()
    for uid, nid, email in ((U_ME, N_ME, EMAIL), (U_MATE, N_MATE, "dash-mate@goodmit.co.kr")):
        db.add(UserNotionMapping(user_id=uid, notion_user_id=nid, notion_email=email,
                                 status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                                 last_verified_at=SYNCED_AT))

    # ── 티켓: 창의 양쪽 끝에 표본을 놓는다 ─────────────────────────────────────
    db.add_all([
        # 이번 주 창 [08-03, 08-10) 안 — 월요일 마감이 **아래쪽 경계**다.
        _cache("d-uid-1", "d-1", tid=1, title="이번 주 월요일 마감", status="진행",
               due="2026-08-03", people=[N_ME]),
        _cache("d-uid-2", "d-2", tid=2, title="이번 주 완료", status="완료",
               due="2026-08-09", people=[N_ME]),
        # **위쪽 경계** — 다음 주 월요일. 이번 주에 끼면 안 된다.
        _cache("d-uid-3", "d-3", tid=3, title="다음 주 월요일 마감", status="진행",
               due="2026-08-10", people=[N_ME]),
        # 지난 주(KST 일요일) — 지연이고, 추이의 07-27 주에 들어간다.
        _cache("d-uid-4", "d-4", tid=4, title="지난 주 일요일 마감", status="진행",
               due="2026-08-02", people=[N_ME]),
        _cache("d-uid-5", "d-5", tid=5, title="지난 주 완료", status="완료",
               due="2026-07-30", people=[N_ME]),
        # 남의 티켓 — 내 숫자에 섞이면 안 된다.
        _cache("d-uid-6", "d-6", tid=6, title="동료 것", status="진행",
               due="2026-08-03", people=[N_MATE]),
    ])
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = SYNC_OK
    state.last_run_at = SYNCED_AT
    state.last_success_at = SYNCED_AT
    state.ticket_count = 6
    state.truncated = False
    state.error = None
    state.updated_at = SYNCED_AT
    db.add(state)

    # ── 프로젝트: 0 / null / 차질 / 범위 밖 ───────────────────────────────────
    db.add_all([
        _project("prj-low", "점수 낮음", dept=DEPT_MINE, score=30),
        _project("prj-none", "아직 안 잼", dept=DEPT_MINE, score=None),
        _project("prj-zero", "0점", dept=DEPT_MINE, score=0),
        _project("prj-notion", "노션이 차질이라 함", dept=DEPT_MINE, score=100,
                 notion_status="차질"),
        _project("prj-other", "남의 조직", dept=DEPT_OTHER, org=ORG_OTHER, score=5),
    ])
    db.flush()
    db.add_all([
        # 기한이 오늘(KST 08-03)보다 **이전**이라 지연이다.
        _milestone("ms-late", "prj-low", "지난 기한", due_on="2026-08-02",
                   status=MILESTONE_PLANNED),
        # 기한이 **오늘**이면 아직 지연이 아니다(경계).
        _milestone("ms-today", "prj-low", "오늘 기한", due_on=TODAY,
                   status=MILESTONE_PLANNED),
        # 기한은 지났지만 끝났다 — 지연이 아니다.
        _milestone("ms-done", "prj-none", "끝난 것", due_on="2026-07-01",
                   status=MILESTONE_DONE),
        # 범위 밖 — 아무리 늦어도 안 보여야 한다.
        _milestone("ms-other", "prj-other", "남의 지연", due_on="2026-01-01",
                   status=MILESTONE_PLANNED),
    ])
    db.commit()


@pytest.fixture()
def work_client(client, db, settings, notion):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    _seed(db)
    response = client.post("/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def _work(client) -> dict:
    response = client.get("/api/home/work-dashboard")
    assert response.status_code == 200, response.text
    return response.json()


# ── 1. 시점 (M4) ─────────────────────────────────────────────────────────────

def test_window_follows_the_kst_calendar_day_on_monday_morning(work_client):
    """UTC 로 판정했다면 오늘은 08-02(일)이고 창은 [07-27, 08-03) 이 된다."""
    body = _work(work_client)
    assert body["today"] == TODAY
    assert body["window"] == WEEK


def test_this_week_takes_monday_and_leaves_next_monday_out(work_client):
    """창의 **양쪽 끝**. 한쪽만 보면 반쪽만 고치고 통과한다."""
    mine = _work(work_client)["mine"]
    # 아래쪽: 08-03(월) 마감이 들어온다. 위쪽: 08-10(다음 주 월) 마감은 안 낀다.
    assert mine["due_this_week"] == 2      # 08-03 + 08-09 (08-10 은 제외)
    assert mine["done_this_week"] == 1     # 그중 완료는 08-09 하나
    assert mine["open"] == 3               # 활성 = 08-03, 08-10, 08-02 (완료 2건 제외)
    assert mine["overdue"] == 1            # 08-02 마감이 오늘(08-03) 기준 지연


def test_completion_trend_walks_back_in_kst_weeks(work_client):
    trend = _work(work_client)["completion_trend"]
    assert [w["week_of"] for w in trend] == [
        "2026-07-13", "2026-07-20", "2026-07-27", "2026-08-03",
    ]
    by_week = {w["week_of"]: w for w in trend}
    # 07-27 주에는 07-30(완료)과 08-02(진행)이 들어간다 — 08-02 는 KST 로 일요일이다.
    assert by_week["2026-07-27"] == {"week_of": "2026-07-27", "assigned": 2, "done": 1}
    assert by_week["2026-08-03"] == {"week_of": "2026-08-03", "assigned": 2, "done": 1}
    assert by_week["2026-07-20"] == {"week_of": "2026-07-20", "assigned": 0, "done": 0}


def test_overdue_milestones_are_cut_at_the_kst_today_not_utc(work_client):
    overdue = _work(work_client)["milestones"]["overdue"]
    # 오늘이 UTC(08-02)로 판정됐다면 'ms-late'(기한 08-02)도 지연이 아니게 되어 0건이 된다.
    assert overdue["count"] == 1
    assert [m["id"] for m in overdue["items"]] == ["ms-late"]


# ── 2. 범위 ──────────────────────────────────────────────────────────────────

def test_other_orgs_projects_and_milestones_never_appear(work_client):
    body = _work(work_client)
    names = {p["name"] for p in body["projects"]["troubled"]["items"]}
    assert "남의 조직" not in names
    assert body["projects"]["in_scope"] == 4          # 남의 조직 1건 제외
    assert all(m["project_id"] != "prj-other" for m in body["milestones"]["overdue"]["items"])


# ── 3. 0 과 없음 ─────────────────────────────────────────────────────────────

def test_zero_is_a_measurement_but_null_is_not(work_client):
    projects = _work(work_client)["projects"]
    troubled = {p["project_id"] for p in projects["troubled"]["items"]}
    # 0점은 '재 봤더니 나쁘다' 라 차질이다. null 은 '아직 안 쟀다' 라 차질이 아니다.
    assert "prj-zero" in troubled
    assert "prj-none" not in troubled
    assert "prj-low" in troubled          # 30점
    assert "prj-notion" in troubled       # 점수는 100 이지만 노션이 차질이라 한다
    assert projects["troubled"]["count"] == 3
    # '못 잼' 을 0 으로 뭉개지 않고 따로 센다.
    assert projects["unscored"] == 1


def test_low_confidence_counts_partially_checked_projects_separately(work_client, db):
    """점수가 있어도 규칙을 다 재지 못했으면 `unscored`가 아니라 `low_confidence`로 센다(FN-42).

    `unscored`는 점수 자체가 없는 경우다(위 테스트) — 이건 다른 축이다: 점수는 있는데
    5개 규칙 중 일부만 판정됐다. 감점이 없으면 그 상태로도 만점처럼 보이므로, 화면이
    "다 재서 건강함"과 "몇 개만 재서 우연히 만점"을 구별하려면 이 수가 따로 있어야 한다.
    """
    # prj-low(30점) — 최근 스냅샷이 5개 규칙 중 2개만 checked. low_confidence에 잡힌다.
    db.add(ProjectHealthSnapshot(
        project_id="prj-low", week_of="2026-07-27", score=30,
        reasons_json=json.dumps({
            "score": 30, "reasons": [], "checked": ["task_overdue", "unassigned"], "unknown": [],
        }),
        created_at=SYNCED_AT,
    ))
    # prj-zero(0점) — 5개 다 checked. 점수는 나쁘지만 신뢰도는 낮지 않다 — low_confidence에
    # 안 잡혀야 차질(troubled)과 신뢰도가 서로 다른 축이라는 게 실제로 증명된다.
    db.add(ProjectHealthSnapshot(
        project_id="prj-zero", week_of="2026-07-27", score=0,
        reasons_json=json.dumps({
            "score": 0, "reasons": [], "checked": [
                "notion_trouble", "milestone_overdue", "task_overdue", "unassigned", "stale",
            ], "unknown": [],
        }),
        created_at=SYNCED_AT,
    ))
    # prj-notion(100점)은 일부러 스냅샷을 안 남긴다 — 워커가 아직 안 돈 상태를 흉내낸다.
    # "모른다"를 "신뢰도 낮음"으로 단정하면 안 되므로 low_confidence에 안 잡혀야 한다.
    db.commit()

    projects = _work(work_client)["projects"]
    assert projects["low_confidence"] == 1


def test_a_dead_ticket_source_says_unknown_not_zero(work_client, notion, db):
    """티켓을 못 읽으면 mine 은 **null** 이다. 0 으로 그리면 '할 일이 없다'는 거짓말이 된다."""
    db.query(TicketCache).delete()
    db.commit()
    notion.fail_status = 502
    body = _work(work_client)
    assert body["ok"] is True
    # 왜 비었는지를 블록이 스스로 말한다(configured 면 error, 아니면 message - 홈과 같은 어휘).
    assert body["tickets"]["ok"] is False
    assert body["tickets"].get("error") or body["tickets"].get("message")
    assert body["mine"] is None
    assert body["completion_trend"] is None
    # 프로젝트·마일스톤은 티켓과 다른 소스라 그대로 나와야 한다(§17.4 장애 격리).
    assert body["projects"]["in_scope"] == 4
    assert body["milestones"]["overdue"]["count"] == 1


def test_work_dashboard_requires_authentication(client):
    assert client.get("/api/home/work-dashboard").status_code == 401
