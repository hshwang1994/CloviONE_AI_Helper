"""프로젝트 주간 리포트 (#12) — 규칙 기반. **주 경계와 시간대가 이 파일의 본론이다.**

숫자를 세는 일 자체는 어렵지 않다. 이 기능이 조용히 틀리는 자리는 두 곳이고, 둘 다
"화면에는 그럴듯한 숫자가 떠 있다" 로 나타나기 때문에 아무도 신고하지 않는다.

1. **주 경계가 스프린트와 갈라지는 것.** 같은 화면 두 개가 서로 다른 주를 '이번 주'라고
   부르면 사용자는 둘 중 하나를 거짓말로 받아들인다. 그래서 여기서는 리포트의 창을
   `/api/sprint/summary` 가 내는 창과 **직접 맞대어** 본다. 상수를 두 곳에 적어 두고
   비교하면 두 상수가 함께 틀렸을 때 통과한다.

2. **KST 날짜를 UTC 타임스탬프와 비교하는 것(M4).** 주간 다이제스트가 실제로 이 결함을
   갖고 있다(`app/home/readers.py::documents_changed_since` 는 'YYYY-MM-DD' 라는 KST
   달력일을 Notion 이 준 UTC 문자열과 그대로 비교한다). KST 는 UTC+9 라 **월요일 오전
   9시 이전에 일어난 일은 UTC 로는 아직 일요일**이고, 그래서 월요일 아침에 고친 것이
   그 주에서 통째로 빠진다. 같은 실수를 여기서 되풀이하지 않는다.

   못박는 방법: 창의 **양쪽 끝**에 1시간 차이로 표본을 놓는다. 잘못된 비교로 바꾸면
   아래쪽 표본은 사라지고 위쪽 표본은 끼어든다 — 한 방향만 보면 우연히 통과할 수 있다.

LLM 은 아직 붙지 않았다. 그래서 `source` 는 항상 `rule` 이고 `llm_summary` 는 None 이다 -
자리는 있지만 없는 것을 있는 척 그리지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import (
    MILESTONE_DONE,
    MILESTONE_PLANNED,
    Project,
    ProjectMilestone,
    ProjectWeeklyReport,
)
from app.tickets.models import TicketCache
from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.integration

# UTC 로 2026-08-03 01:00 = KST 2026-08-03(월) 10:00. 클록은 naive UTC 를 준다.
NOW = datetime(2026, 8, 3, 1, 0, 0)
WEEK = "2026-08-03"          # 그 주 월요일 (KST 달력)
WEEK_END = "2026-08-10"      # 배타적 끝
PREV_WEEK = "2026-07-27"
NEXT_WEEK = "2026-08-10"

ALPHA_PAGE = "page-alpha"
BETA_PAGE = "page-beta"

BOSS_EMAIL = "prj-weekly@goodmit.co.kr"

# ── 시간대 표본 (전부 naive UTC — DB 에 그 형식으로 저장된다) ────────────────────
#
# KST 창은 [2026-08-03 00:00, 2026-08-10 00:00) 이고, 이를 UTC 로 옮기면
# [2026-08-02 15:00, 2026-08-09 15:00) 이다. 아래 세 표본은 그 두 경계를 1시간 간격으로
# 감싼다 — KST 날짜를 UTC 와 그대로 비교하면 아래 둘이 **반대로** 뒤집힌다.
MON_MORNING_UTC = datetime(2026, 8, 2, 23, 30)      # KST 08-03(월) 08:30 → 이번 주다
NEXT_MON_MORNING_UTC = datetime(2026, 8, 9, 23, 30)  # KST 08-10(월) 08:30 → 다음 주다
PREV_SUN_NIGHT_UTC = datetime(2026, 8, 2, 14, 0)     # KST 08-02(일) 23:00 → 지난 주다


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


def _ticket(db, *, uid, page_id, project_page, status, due, tid=None, est=None):
    db.add(TicketCache(
        id=uid,
        notion_page_id=page_id,
        notion_ticket_number=tid,
        org_id=DEFAULT_ORG_ID,
        title=f"작업 {tid}",
        status=status,
        due_date=due,
        est_wd=est,
        project_ids=join_names([project_page]),
        project_names="",
        assignee_notion_ids="",
        source="notion",
        synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    ))


def _milestone(db, *, mid, project_id, name, due_on, status, updated_at):
    db.add(ProjectMilestone(
        id=mid,
        project_id=project_id,
        name=name,
        due_on=due_on,
        status=status,
        sort_order=0,
        # 만든 시각은 창 밖으로 멀리 둔다 — '변화'가 created_at 으로 잡히면 안 된다.
        created_at=datetime(2026, 6, 1, 0, 0),
        updated_at=updated_at,
    ))


@pytest.fixture()
def world(db, make_user):
    boss = make_user(BOSS_EMAIL, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    db.commit()

    # 프로젝트 코드는 서버가 짓는 대문자 여섯 글자이고 `I`·`L`·`O` 가 없다 (D-282).
    # 이 파일은 코드 값을 되읽는 단언이 없으므로, 실패 메시지에서 어느 프로젝트인지
    # 바로 읽히도록 이름의 첫 글자를 여섯 번 쓴다. 모양이 정책과 갈라지면
    # `ck_projects_code_shape` 가 INSERT 를 거절해 시험이 시작도 못 한다.
    alpha = Project(
        name="알파", code="AAAAAA", org_id=DEFAULT_ORG_ID, notion_page_id=ALPHA_PAGE,
    )
    beta = Project(
        name="베타", code="BBBBBB", org_id=DEFAULT_ORG_ID, notion_page_id=BETA_PAGE,
    )
    portal_only = Project(name="포털 전용", code="PPPPPP", org_id=DEFAULT_ORG_ID)
    db.add_all([alpha, beta, portal_only])
    db.flush()

    # 알파 — 이번 주 완료 1, 진행 중 2(그중 이슈 1), 지연 1, 다음 주 1, 지난 주 완료 1, 취소 1
    _ticket(db, uid="w-101", page_id="wp-101", project_page=ALPHA_PAGE,
            status="완료", due="2026-08-05", tid=101, est=2)
    _ticket(db, uid="w-102", page_id="wp-102", project_page=ALPHA_PAGE,
            status="진행", due="2026-08-06", tid=102, est=3)
    _ticket(db, uid="w-103", page_id="wp-103", project_page=ALPHA_PAGE,
            status="이슈", due="2026-08-07", tid=103, est=1)
    _ticket(db, uid="w-104", page_id="wp-104", project_page=ALPHA_PAGE,
            status="진행", due="2026-07-30", tid=104, est=1)
    _ticket(db, uid="w-105", page_id="wp-105", project_page=ALPHA_PAGE,
            status="계획", due="2026-08-12", tid=105, est=5)
    _ticket(db, uid="w-106", page_id="wp-106", project_page=ALPHA_PAGE,
            status="완료", due="2026-07-29", tid=106, est=2)
    _ticket(db, uid="w-107", page_id="wp-107", project_page=ALPHA_PAGE,
            status="취소", due="2026-08-05", tid=107, est=9)

    # 베타 — 이번 주 완료 1, 진행 중 1
    _ticket(db, uid="w-201", page_id="wp-201", project_page=BETA_PAGE,
            status="완료", due="2026-08-04", tid=201, est=1)
    _ticket(db, uid="w-202", page_id="wp-202", project_page=BETA_PAGE,
            status="진행", due="2026-08-08", tid=202, est=1)

    _milestone(db, mid="ms-mon", project_id=alpha.id, name="월요일 오전에 고쳤다",
               due_on="2026-08-07", status=MILESTONE_PLANNED,
               updated_at=MON_MORNING_UTC)
    _milestone(db, mid="ms-next-mon", project_id=alpha.id, name="다음 주 월요일 오전에 고쳤다",
               due_on="2026-08-14", status=MILESTONE_PLANNED,
               updated_at=NEXT_MON_MORNING_UTC)
    _milestone(db, mid="ms-prev-sun", project_id=alpha.id, name="지난 주 일요일 밤에 고쳤다",
               due_on="2026-08-05", status=MILESTONE_DONE,
               updated_at=PREV_SUN_NIGHT_UTC)
    db.commit()
    return {"alpha": alpha.id, "beta": beta.id, "portal_only": portal_only.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS_EMAIL)}


def _get(client, path, headers):
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _tids(bucket) -> set[int]:
    return {item["tid"] for item in bucket["items"]}


# ── 1. 주 경계는 스프린트와 **같은 한 벌**이어야 한다 ────────────────────────────

def test_the_report_week_is_the_very_same_window_as_the_sprint(client, login_as, world):
    """리포트의 '이번 주'와 스프린트의 '이번 주'를 **직접 맞대어** 본다.

    상수를 두 곳에 적어 놓고 각각 비교하면 두 상수가 함께 틀렸을 때 통과한다. 두 응답을
    서로 비교해야 주 경계 계산이 두 벌이 된 순간을 잡을 수 있다.
    """
    headers = _hdr(login_as)
    sprint = _get(client, "/api/sprint/summary", headers)["window"]
    report = _get(client, "/api/projects/weekly-report", headers)["window"]

    assert (report["start"], report["end_exclusive"]) == (
        sprint["start"], sprint["end_exclusive"]
    ), f"리포트와 스프린트가 다른 주를 가리킨다: {report} vs {sprint}"
    # 그리고 그 창이 실제로 KST 월요일에서 시작하는지도 못박는다(둘 다 틀린 경우 방지).
    assert (report["start"], report["end_exclusive"]) == (WEEK, WEEK_END), report
    assert report["week_of"] == WEEK, report


# ── 2. KST 달력일 창 ↔ UTC 타임스탬프 (M4 와 같은 실수를 하지 않는다) ────────────

def test_a_monday_morning_change_belongs_to_that_week_not_the_previous_one(
    client, login_as, world
):
    """KST 월요일 08:30 에 고친 마일스톤은 **그 주**의 변화다.

    UTC 로는 아직 일요일 23:30 이라, KST 날짜를 그대로 비교하면 이 표본이 사라진다
    (M4 가 문서에서 겪고 있는 바로 그 증상).
    """
    body = _get(client, f"/api/projects/{world['alpha']}/weekly-report", _hdr(login_as))
    changed = {m["name"] for m in body["milestones"]["changed"]["items"]}

    assert "월요일 오전에 고쳤다" in changed, (
        f"월요일 오전(KST)에 고친 마일스톤이 그 주에서 빠졌다 - KST 날짜를 UTC 와 "
        f"그대로 비교하고 있다: {changed}"
    )
    assert "다음 주 월요일 오전에 고쳤다" not in changed, (
        f"다음 주 월요일 오전(KST) 변화가 이번 주로 새어 들어왔다: {changed}"
    )
    assert "지난 주 일요일 밤에 고쳤다" not in changed, (
        f"지난 주 일요일 밤(KST) 변화가 이번 주로 새어 들어왔다: {changed}"
    )
    assert body["milestones"]["changed"]["count"] == 1, body["milestones"]["changed"]


def test_the_next_monday_morning_change_shows_up_in_the_next_week(
    client, login_as, world
):
    """같은 표본이 **다음 주** 리포트에서는 보여야 한다.

    한 주에서 안 보이는 것만 확인하면 '아무 데도 안 보이는' 상태를 통과시킨다.
    """
    body = _get(
        client,
        f"/api/projects/{world['alpha']}/weekly-report?week={NEXT_WEEK}",
        _hdr(login_as),
    )
    changed = {m["name"] for m in body["milestones"]["changed"]["items"]}
    assert changed == {"다음 주 월요일 오전에 고쳤다"}, (
        f"다음 주 월요일 오전(KST) 변화가 그 주 리포트에도 없다: {changed}"
    )


# ── 3. 전주 / 이번 주 / 다음 주 이동 ────────────────────────────────────────────

def test_moving_a_week_moves_both_the_window_and_the_contents(client, login_as, world):
    """이동은 창만 옮기는 것이 아니다 - 내용도 함께 달라져야 한다.

    창 문자열만 보면 창은 옮겨 놓고 질의는 이번 주로 고정된 상태를 통과시킨다.
    """
    headers = _hdr(login_as)
    this_week = _get(client, f"/api/projects/{world['alpha']}/weekly-report", headers)
    assert this_week["window"]["prev_week"] == PREV_WEEK, this_week["window"]
    assert this_week["window"]["next_week"] == NEXT_WEEK, this_week["window"]
    assert _tids(this_week["done"]) == {101}, this_week["done"]

    prev = _get(
        client,
        f"/api/projects/{world['alpha']}/weekly-report"
        f"?week={this_week['window']['prev_week']}",
        headers,
    )
    assert prev["window"]["start"] == PREV_WEEK
    assert prev["window"]["end_exclusive"] == WEEK
    assert _tids(prev["done"]) == {106}, (
        f"지난 주로 옮겼는데 지난 주 완료가 안 나온다: {prev['done']}"
    )


def test_any_day_of_the_week_lands_on_that_weeks_monday(client, login_as, world):
    """주 중간 날짜를 줘도 그 주 월요일로 정규화된다(스프린트의 `week` 규약과 같다).

    **이번 주가 아닌 주**의 목요일을 준다. 이번 주 안의 날짜를 주면 파라미터를 통째로
    무시하는 구현도 통과한다 - 값이 달라지는 표본이어야 한다.
    """
    body = _get(
        client,
        f"/api/projects/{world['alpha']}/weekly-report?week=2026-07-30",
        _hdr(login_as),
    )
    assert body["window"]["week_of"] == PREV_WEEK, body["window"]
    assert body["window"]["start"] == PREV_WEEK
    assert body["window"]["end_exclusive"] == WEEK


# ── 4. 프로젝트별 / 전체 ────────────────────────────────────────────────────────

def test_a_single_project_report_sorts_this_week_into_the_five_sections(
    client, login_as, world
):
    """이번 주 완료 / 진행 중 / 지연 / 이슈 / 다음 주 계획.

    취소는 어느 칸에도 안 들어간다(진행률 계산과 같은 규칙 - 하기로 한 적 없는 일이다).
    """
    body = _get(client, f"/api/projects/{world['alpha']}/weekly-report", _hdr(login_as))

    assert _tids(body["done"]) == {101}, body["done"]
    assert _tids(body["in_progress"]) == {102, 103}, body["in_progress"]
    assert _tids(body["delayed"]) == {104}, body["delayed"]
    assert _tids(body["issues"]) == {103}, body["issues"]
    assert _tids(body["next_week"]) == {105}, body["next_week"]
    assert 107 not in (
        _tids(body["done"]) | _tids(body["in_progress"]) | _tids(body["next_week"])
    ), "취소한 티켓이 리포트에 실렸다"
    assert body["source"] == "rule"
    assert body["llm_summary"] is None, "아직 없는 LLM 요약을 있는 척 그렸다"


def test_the_overall_report_adds_up_the_projects_it_lists(client, login_as, world):
    """전체는 프로젝트별의 합이어야 한다.

    두 화면이 다른 숫자를 말하면 사용자는 어느 쪽도 안 믿는다. 그래서 합계를 상수로
    적지 않고 **프로젝트별 응답을 실제로 더해서** 맞대어 본다.
    """
    headers = _hdr(login_as)
    overall = _get(client, "/api/projects/weekly-report", headers)

    listed = {row["project_id"] for row in overall["projects"]}
    assert listed == {world["alpha"], world["beta"], world["portal_only"]}, listed

    expected = {"done": 0, "in_progress": 0, "delayed": 0, "issues": 0, "next_week": 0}
    for project_id in listed:
        one = _get(client, f"/api/projects/{project_id}/weekly-report", headers)
        for key in expected:
            expected[key] += one[key]["count"]

    assert {k: overall["totals"][k] for k in expected} == expected, (
        f"전체 합계가 프로젝트별의 합과 다르다: {overall['totals']} vs {expected}"
    )
    assert overall["totals"]["done"] == 2, overall["totals"]


def test_a_portal_only_project_is_not_reported_as_unlinkable(client, login_as, db, world):
    """새로 만든 프로젝트가 **「작업을 걸 수 없는 프로젝트」로 보고되지 않는다.**

    옛 세계에서는 외부 짝(`projects.notion_page_id`)이 있어야만 작업을 걸 수 있어서, 짝이
    없는 프로젝트는 0건이 아니라 "연결이 없다" 였다. 소속의 정본이 `tickets.project_uid` 로
    옮겨 온 뒤로는 어느 프로젝트에나 걸 수 있다. 그대로 두면 자체 DB 에서 만든 프로젝트가
    전부 「집계를 낼 수 없는 프로젝트」로 보고되어, 리포트가 0건인 이유를 잘못 설명한다.

    그래서 두 가지를 함께 본다: 비어 있을 때 그 안내가 **안 나오고**, 실제로 작업을 걸면
    그 작업이 집계에 **들어온다**. 뒤엣것이 없으면 "걸 수 있다"는 말이 빈말인지 알 수 없다.
    """
    from app.projects.weekly import NO_LINK_NOTE

    headers = _hdr(login_as)
    body = _get(client, f"/api/projects/{world['portal_only']}/weekly-report", headers)
    assert body["basis"]["tickets_linked"] is True, body["basis"]
    assert body["basis"]["sample_tickets"] == 0, body["basis"]
    assert body["done"]["count"] == 0
    assert NO_LINK_NOTE not in body["summary_md"], (
        f"작업을 걸 수 있는 프로젝트인데 걸 수 없다고 말한다: {body['summary_md']}"
    )

    # 자체 DB 축(`project_uid`)으로 한 건 건다 — 외부 짝은 여전히 없다.
    db.add(TicketCache(
        id="wk-portal-only-1",
        org_id=DEFAULT_ORG_ID,
        title="포털에서 만든 작업",
        status="완료",
        due_date=date(2026, 8, 5),
        project_uid=world["portal_only"],
        project_ids="",
        project_names="",
        assignee_notion_ids="",
        synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    ))
    db.commit()

    after = _get(client, f"/api/projects/{world['portal_only']}/weekly-report", headers)
    assert after["basis"]["sample_tickets"] == 1, after["basis"]
    assert after["done"]["count"] == 1, after["done"]


# ── 5. 범위 (§불변 1: 범위 밖은 404, 목록도 단건도 같은 판정) ────────────────────

def test_the_weekly_report_never_leaves_the_viewers_scope(client, login_as, db, world):
    """부서 범위 사용자에게 남의 팀 프로젝트는 전체에도 안 나오고 단건은 404 다."""
    from app.users.service import get_user_by_email

    mine = Department(name="내팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()
    db.get(Project, world["alpha"]).dept_id = mine.id
    db.get(Project, world["beta"]).dept_id = theirs.id
    db.get(Project, world["portal_only"]).dept_id = theirs.id
    db.commit()

    login_as("user", email="weekly-member@goodmit.co.kr")
    member = get_user_by_email(db, "weekly-member@goodmit.co.kr")
    member.department_id = mine.id
    member.org_id = DEFAULT_ORG_ID
    db.commit()
    login_as("user", email="weekly-member@goodmit.co.kr")

    overall = _get(client, "/api/projects/weekly-report", {})
    assert {row["project_id"] for row in overall["projects"]} == {world["alpha"]}, (
        f"남의 팀 프로젝트가 전체 리포트에 새어 나왔다: {overall['projects']}"
    )
    assert client.get(f"/api/projects/{world['beta']}/weekly-report").status_code == 404, (
        "범위 밖 프로젝트의 주간 리포트가 열린다"
    )


# ── 6. 저장 (규칙 기반, source='rule', 한 주에 한 행) ───────────────────────────

def test_generating_saves_one_rule_row_per_week(client, login_as, db, world):
    """`project_weekly_reports` 는 (프로젝트, 주) 에 한 행이다. 다시 만들면 덮어쓴다."""
    headers = _hdr(login_as)
    first = client.post(
        f"/api/projects/{world['alpha']}/weekly-report", headers=headers
    )
    assert first.status_code == 200, first.text
    saved = first.json()["saved"]
    assert saved["week_of"] == WEEK, saved
    assert saved["source"] == "rule", saved
    assert saved["summary_md"], "규칙이 만든 문장이 비어 있다"

    second = client.post(
        f"/api/projects/{world['alpha']}/weekly-report", headers=headers
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    rows = db.query(ProjectWeeklyReport).filter_by(project_id=world["alpha"]).all()
    assert len(rows) == 1, f"같은 주에 리포트가 {len(rows)}행 쌓였다"
    # 컬럼이 `date` 다 (S7 · P-14a). `WEEK` 는 주소·응답이 쓰는 문자열이라 그대로 둔다.
    assert rows[0].week_of == date.fromisoformat(WEEK)
    assert rows[0].source == "rule"


def test_a_saved_report_comes_back_with_the_facts(client, login_as, world):
    """저장된 문장은 그 주의 사실과 함께 나온다. 저장 전에는 `saved` 가 None 이다."""
    headers = _hdr(login_as)
    before = _get(client, f"/api/projects/{world['alpha']}/weekly-report", headers)
    assert before["saved"] is None

    client.post(f"/api/projects/{world['alpha']}/weekly-report", headers=headers)
    after = _get(client, f"/api/projects/{world['alpha']}/weekly-report", headers)
    assert after["saved"] is not None
    assert after["saved"]["source"] == "rule"
    # 다른 주를 보면 그 주에는 저장된 것이 없다(주마다 따로다).
    other = _get(
        client, f"/api/projects/{world['alpha']}/weekly-report?week={PREV_WEEK}", headers
    )
    assert other["saved"] is None, "지난 주 리포트에 이번 주 저장본이 붙어 나온다"


# ── §L 배선: 왜 규칙 요약인지 화면이 말한다 ─────────────────────────────────

def test_the_report_says_why_it_is_a_rule_summary(client, login_as, world):
    """🔴 이유를 안 주면 화면은 침묵하고, 사용자는 AI 요약이 고장 났다고 믿는다.

    기본값은 꺼짐(fail-closed)이므로 지금은 늘 안내가 붙는다.
    """
    body = _get(client, f"/api/projects/{world['alpha']}/weekly-report", _hdr(login_as))
    assert body["source"] == "rule", body
    assert body["llm_summary"] is None, "없는 요약을 있는 척했다"
    assert body["llm_notice"], f"왜 규칙 요약인지 말하지 않는다: {body}"
    assert body["summary_md"], "규칙 요약 자체가 비었다 - 안내만 있고 내용이 없다"


def test_opening_the_report_does_not_run_the_language_model(client, login_as, world, monkeypatch):
    """🔴 이 경로는 **화면을 여는 GET** 이다. CLI 왕복(수십 초)을 여기서 하면 안 된다."""
    from app.llm import provider as llm_provider

    called = {"n": 0}
    original = llm_provider.select_backend

    def _counted(*a, **k):
        called["n"] += 1
        return original(*a, **k)

    monkeypatch.setattr(llm_provider, "select_backend", _counted)
    _get(client, f"/api/projects/{world['alpha']}/weekly-report", _hdr(login_as))
    assert called["n"] == 0, "리포트를 여는 것만으로 LLM 백엔드를 만들었다"
