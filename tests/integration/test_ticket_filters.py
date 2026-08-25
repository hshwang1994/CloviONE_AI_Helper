"""티켓 목록의 **서버 필터 + 페이지네이션** (사용자 지적 #3, Z11, Z9).

## 무엇이 어긋나 있었나

`repository_notion.list_all` 은 `select(TicketCache)` 에 LIMIT 이 없었다. 운영 미러가
1,058건이므로 `/api/tickets/team` 한 번에 그 전부가 브라우저로 나갔고, 화면은 그걸 받아
**브라우저에서** 상태 하나로 걸렀다. 필터를 서버가 안 걸면 두 가지가 동시에 나쁘다:
응답이 무겁고(Z11), 화면이 고를 수 있는 조건이 받아 온 것 안으로 갇힌다.

## 이 파일이 고정하는 성질

  1. 필터마다 **실제로 걸린다** — 그리고 걸리지 말아야 할 것은 안 걸린다(오탐 방지).
     특히 다중값 열(`project_ids` / `assignee_notion_ids`)은 id 접두사 충돌이 나기 쉬워서
     `p1` 로 거를 때 `p10` 티켓이 따라오면 안 된다.
  2. **1페이지와 2페이지에 같은 티켓이 안 나온다** (Z9). 마감일과 티켓 번호가 **둘 다 비어
     있는** 행들이 그 시험대다 — 거기서 정렬이 전순서가 아니면 페이지 경계가 스캔 순서에
     좌우되고, 사용자에게는 "티켓이 사라졌다" 로 보인다.
  3. `total` 은 **필터 뒤·자르기 전** 값이다. 필터 앞의 수를 실으면 화면이 사용자가 세는
     것과 다른 말을 한다.
  4. 범위 판정이 **여전히 걸린다**. 필터와 페이지를 넣으면서 남의 팀 티켓이 새어 나오면
     그건 성능 개선이 아니라 유출이다.

## 왜 미러(ticket_cache)에 직접 심는가

목록 API 가 읽는 표가 그 표다. 여기서는 정렬 타이브레이커를 시험해야 해서 **id 를 손으로
정해야** 하고(동기화는 UUID 를 만든다), 대분류처럼 Notion 페이크의 행 빌더에 없는 열도
써야 한다. 실시간 경로와 미러 경로가 같은 답을 내는지는 마지막 시험이 따로 본다.

qa-contract-change: 「실시간 폴백 경로도 같은 답을 낸다」 시험이 미러가 비었을 때 소스를 직접 조회하던 두 번째 읽기 길을 확인했고 S14 가 그 길을 없앴다(D-284) — 답을 내는 길이 하나뿐이라 두 길이 어긋날 자리가 없으므로, 「두 길이 같다」 대신 「두 번째 길이 생기지 않았다」(신선도·동기화 블록이 응답에 없다)로 바꿔 적었다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.models_base import join_names
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import (
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketSyncState,
)

pytestmark = pytest.mark.integration

# 기본 FakeClock 과 같은 시각. 2026-07-14 는 **화요일**이라 그 주 월요일은 2026-07-13,
# 다음 주는 2026-07-20 부터다. 기한 버킷의 경계가 여기서 나온다.
NOW = datetime(2026, 7, 14, 0, 0, 0)
# 지남·이번 주·다음 주 어디에도 안 드는 마감일. 필터를 한 축씩 시험하려면 기본값이
# 다른 축에 걸리지 않아야 한다.
FAR = "2026-09-01"

NID_ME = "notion-me"
NID_MATE = "notion-mate"          # 같은 팀
NID_OTHER = "notion-other"        # 다른 팀
NID_GHOST = "notion-ghost"        # 앱 사용자로 해석되지 않는 담당자
# 접두사가 겹치는 짝 — 부분일치로 조립하면 여기서 틀린다.
NID_ME_LONG = "notion-me-2"
PROJ = "p1"
PROJ_LONG = "p10"


def _row(
    db,
    *,
    uid: str,
    page_id: str | None = None,
    tid: int | None = None,
    title: str = "티켓",
    status: str | None = "진행",
    due: str | None = None,
    priority: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    projects: tuple[str, ...] = (),
    project_uid: str | None = None,
    assignees: tuple[str, ...] = (),
    missing_at: datetime | None = None,
    act_wd: float | None = None,
    created_at: datetime | None = None,
) -> TicketCache:
    """`projects` 는 **외부 relation id**(필터 시험용)이고, `project_uid` 는 해석된
    **Portal 프로젝트 id**(범위 시험용)다. 0060 에서 범위를 정하는 것은 후자다."""
    row = TicketCache(
        id=uid,
        notion_page_id=page_id if page_id is not None else f"page-{uid}",
        org_id=DEFAULT_ORG_ID,
        notion_ticket_number=tid,
        url=f"https://www.notion.so/{uid}",
        title=title,
        status=status,
        due_date=due,
        priority=priority,
        difficulty=difficulty,
        category=category,
        project_ids=join_names(list(projects)),
        project_uid=project_uid,
        project_link=PROJECT_LINK_OK if project_uid else PROJECT_LINK_MISSING,
        project_names="",
        assignee_notion_ids=join_names(list(assignees)),
        notion_missing_at=missing_at,
        synced_at=NOW,
        created_at=created_at or NOW,
        updated_at=NOW,
        act_wd=act_wd,
    )
    db.add(row)
    return row


def _mirror_ready(db, count: int) -> None:
    """`_cache_ready` 가 참이 되게 동기화 상태를 채운다. 안 채우면 실시간으로 폴백해
    미러를 전혀 안 보고, 그러면 이 파일의 시험 대부분이 아무것도 증명하지 못한다."""
    state = db.get(TicketSyncState, SYNC_STATE_ID)
    if state is None:
        state = TicketSyncState(id=SYNC_STATE_ID)
        db.add(state)
    state.status = SYNC_OK
    state.last_run_at = NOW
    state.last_success_at = NOW
    state.ticket_count = count
    state.truncated = False
    state.error = None
    db.commit()


def _project_of(db, uid: str) -> str | None:
    """이미 심어 둔 티켓과 **같은 프로젝트**에 붙인다 — 새 프로젝트를 만들면 그 티켓만
    다른 소속이 되어, 확인하려던 것과 다른 이유로 목록에서 빠질 수 있다."""
    row = db.get(TicketCache, uid)
    return row.project_uid if row is not None else None


def _ids(payload) -> list[str]:
    return [t["id"] for t in payload["items"]]


@pytest.fixture()
def me(db, make_user, settings):
    """세션 사용자 + 같은 팀 동료 + 다른 팀 사람. 매핑은 전부 verified."""
    from app.org.models import Department

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    user = make_user("tf-me@goodmit.co.kr", role="user", display_name="나")
    mate = make_user("tf-mate@goodmit.co.kr", role="user", display_name="동료")
    other = make_user("tf-other@goodmit.co.kr", role="user", display_name="남")
    user.department_id = mine.id
    mate.department_id = mine.id
    other.department_id = theirs.id
    for u, nid in ((user, NID_ME), (mate, NID_MATE), (other, NID_OTHER)):
        db.add(UserNotionMapping(user_id=u.id, notion_user_id=nid, status=STATUS_VERIFIED))
    # 접두사가 겹치는 두 번째 소스 id 는 **아무 앱 사용자에게도** 붙이지 않는다.
    # 붙이면 그 티켓이 미할당 버킷에서 빠져 오탐 시험의 전제가 바뀐다.
    db.commit()
    # 시험이 프로젝트를 매달 자리. 부서 객체를 그대로 돌려주면 세션이 닫힌 뒤 접근에서
    # 터지므로 id 만 얹는다.
    user.mine_dept_id = mine.id
    user.theirs_dept_id = theirs.id
    return user


@pytest.fixture()
def admin(db, make_user, settings):
    """전역 범위 사용자 — 범위가 아니라 **필터**만 시험할 때 쓴다."""
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    return make_user("tf-admin@goodmit.co.kr", role="system_admin", display_name="관리자")


# ── 필터: 걸리는가 · 안 걸려야 할 것이 안 걸리는가 ────────────────────────────

@pytest.fixture()
def catalog(db, admin):
    """조건이 한 축씩만 다른 티켓 묶음. 필터 하나를 걸면 정확히 하나만 남아야 한다.

    마감은 **어느 기한 버킷에도 안 드는 날**(FAR)로 맞춘다. 기본 마감을 이번 주로 두면
    `due=this_week` 가 전부를 돌려주고, 그러면 그 시험은 "필터가 걸렸다" 를 증명하지 못한다.
    """
    _row(db, uid="a-status", title="상태", status="검증", due=FAR, tid=1)
    _row(db, uid="a-priority", title="우선순위", priority="높음", due=FAR, tid=2)
    _row(db, uid="a-difficulty", title="난이도", difficulty="5", due=FAR, tid=3)
    _row(db, uid="a-category", title="대분류", category="인프라", due=FAR, tid=4)
    _row(db, uid="a-project", title="프로젝트", projects=(PROJ,), due=FAR, tid=5)
    _row(db, uid="a-project-long", title="긴 프로젝트", projects=(PROJ_LONG,), due=FAR, tid=6)
    _row(db, uid="a-assignee", title="담당자", assignees=(NID_MATE,), due=FAR, tid=7)
    _row(db, uid="a-assignee-long", title="긴 담당자", assignees=(NID_ME_LONG,), due=FAR, tid=8)
    _row(db, uid="a-search", title="검색어가 들어간 제목", due=FAR, tid=9)
    _row(db, uid="a-overdue", title="지난 마감", due="2026-07-01", tid=10)
    _row(db, uid="a-this-week", title="이번 주", due="2026-07-16", tid=11)
    _row(db, uid="a-next-week", title="다음 주", due="2026-07-22", tid=12)
    db.commit()
    _mirror_ready(db, 12)


@pytest.mark.parametrize(
    "query,expected",
    [
        ("status=검증", ["page-a-status"]),
        ("priority=높음", ["page-a-priority"]),
        ("difficulty=5", ["page-a-difficulty"]),
        ("category=인프라", ["page-a-category"]),
        ("q=검색어", ["page-a-search"]),
        ("due=overdue", ["page-a-overdue"]),
        ("due=this_week", ["page-a-this-week"]),
        ("due=next_week", ["page-a-next-week"]),
    ],
)
def test_each_filter_actually_narrows_the_list(client, login_as, catalog, query, expected):
    login_as("system_admin", email="tf-admin@goodmit.co.kr")
    body = client.get(f"/api/tickets/team?active=false&{query}").json()
    assert body["ok"] is True, body
    assert _ids(body) == expected, f"{query} 가 서버에서 안 걸렸다"
    assert body["total"] == len(expected), "total 이 필터 뒤 값이 아니다"


def test_due_bucket_boundaries_are_the_calendar_week(client, login_as, db, admin):
    """경계를 못박는다. 기준일은 2026-07-14(화), 그 주 월요일은 2026-07-13 이다.

      * **지남** = 마감이 오늘보다 앞선 것. 오늘 마감은 아직 안 지났다.
      * **이번 주 / 다음 주** = 월요일에 시작하는 **달력 주**. 그래서 이번 주 월요일 마감은
        '지남' 이면서 동시에 '이번 주' 다 - 그 겹침은 결함이 아니라 두 질문이 다른 것이다
        ("늦었나?" 와 "언제 마감인가?"). 겹치는 것이 싫다고 이번 주를 오늘부터로 자르면
        "이번 주 마감" 목록에서 월요일 마감이 사라진다.
      * **마감이 없는 티켓은 어느 버킷에도 안 든다.** '지남' 에 넣으면 마감을 아직 안 정한
        일이 전부 지연으로 보인다.
    """
    _row(db, uid="b-old", due="2026-07-10", tid=1)           # 지난주 금요일 = 지남만
    _row(db, uid="b-monday", due="2026-07-13", tid=2)        # 이번 주 월요일 = 지남 + 이번 주
    _row(db, uid="b-today", due="2026-07-14", tid=3)         # 오늘 = 이번 주(지남 아님)
    _row(db, uid="b-sunday", due="2026-07-19", tid=4)        # 이번 주 마지막 날
    _row(db, uid="b-next", due="2026-07-20", tid=5)          # 다음 주 첫날
    _row(db, uid="b-far", due="2026-07-27", tid=6)           # 다다음 주 = 어느 버킷도 아님
    _row(db, uid="b-none", due=None, tid=7)
    db.commit()
    _mirror_ready(db, 7)
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    def ids(bucket: str) -> set[str]:
        return set(_ids(client.get(f"/api/tickets/team?active=false&due={bucket}").json()))

    overdue, this_week, next_week = ids("overdue"), ids("this_week"), ids("next_week")
    assert overdue == {"page-b-old", "page-b-monday"}
    assert this_week == {"page-b-monday", "page-b-today", "page-b-sunday"}
    assert next_week == {"page-b-next"}
    assert this_week & next_week == set(), "주 경계가 겹친다"
    assert "page-b-far" not in overdue | this_week | next_week
    assert "page-b-none" not in overdue | this_week | next_week


def test_multi_value_columns_match_whole_tokens_not_prefixes(client, login_as, catalog):
    """id 접두사 충돌 오탐 방지 — `p1` 로 거를 때 `p10` 이 따라오면 안 된다.

    `project_ids` / `assignee_notion_ids` 는 구분자로 감싸 이어 붙인 문자열이라, 부분일치로
    조립하면 조용히 남의 프로젝트 티켓이 섞인다. 그 오탐은 화면에서 눈에 안 띈다.
    """
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    body = client.get(f"/api/tickets/team?active=false&project_id={PROJ}").json()
    assert _ids(body) == ["page-a-project"], "프로젝트 필터가 접두사로 걸렸다"
    assert body["total"] == 1

    body = client.get(f"/api/tickets/team?active=false&project_id={PROJ_LONG}").json()
    assert _ids(body) == ["page-a-project-long"]


def test_search_is_a_literal_match_not_a_wildcard(client, login_as, catalog):
    """검색어의 `%` 는 글자다 — 와일드카드로 새면 한 글자가 전체 조회가 된다."""
    login_as("system_admin", email="tf-admin@goodmit.co.kr")
    body = client.get("/api/tickets/team?active=false&q=%25").json()
    assert body["total"] == 0, "검색어의 %가 LIKE 와일드카드로 샜다"
    assert _ids(body) == []


def test_assignee_filter_takes_app_user_ids_and_matches_whole_tokens(
    client, login_as, db, me, catalog
):
    """담당자 필터는 **앱 user_id** 로 받는다(§12.3). 소스 id 는 브라우저에 안 나간다."""
    from app.users.service import get_user_by_email

    mate = get_user_by_email(db, "tf-mate@goodmit.co.kr")
    login_as("system_admin", email="tf-admin@goodmit.co.kr")
    body = client.get(
        f"/api/tickets/team?active=false&assignee_user_id={mate.id}"
    ).json()
    assert _ids(body) == ["page-a-assignee"], "담당자 필터가 안 걸리거나 접두사로 걸렸다"

    # 소스 id 를 그대로 넣어도 통하면 안 된다 — 그러면 계약이 두 벌이 된다.
    body = client.get(
        f"/api/tickets/team?active=false&assignee_user_id={NID_MATE}"
    ).json()
    assert body["total"] == 0
    assert _ids(body) == []


def test_filters_still_hide_tickets_notion_lost_track_of(client, login_as, db, admin):
    """0043 소프트 프룬 가시성은 필터·페이지를 넣어도 그대로 지나야 한다."""
    _row(db, uid="c-alive", status="진행", due="2026-07-15", tid=1)
    _row(db, uid="c-missing", status="진행", due="2026-07-15", tid=2, missing_at=NOW)
    db.commit()
    _mirror_ready(db, 2)
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    body = client.get("/api/tickets/team?active=false&status=진행").json()
    assert _ids(body) == ["page-c-alive"]
    assert body["total"] == 1, "사라진 것으로 표시된 행이 total 에 남아 있다"


# ── 페이지네이션 ──────────────────────────────────────────────────────────────

@pytest.fixture()
def tied(db, admin):
    """마감일도 티켓 번호도 **없는** 티켓 넷. 정렬 타이브레이커가 없으면 순서가 스캔 순서다.

    id 를 일부러 **삽입 순서와 반대**로 준다. 그래야 `ORDER BY ... , id` 가 실제로 걸렸는지
    구별된다 - 타이브레이커가 없으면 SQLite 는 삽입(rowid) 순서를 그대로 돌려주므로
    두 결과가 눈에 보이게 달라진다.
    """
    for uid in ("t-4", "t-3", "t-2", "t-1"):
        _row(db, uid=uid, title=f"동률 {uid}", due=None, tid=None)
    db.commit()
    _mirror_ready(db, 4)


def test_pages_do_not_repeat_or_drop_rows_when_the_sort_key_ties(client, login_as, tied):
    """1페이지와 2페이지에 같은 티켓이 나오면 안 된다 (Z9).

    마감일과 티켓 번호가 둘 다 비면 예전 정렬 규칙은 두 행의 순서를 정하지 못한다. 그 상태의
    OFFSET 페이지네이션은 행을 반복하거나 빠뜨리고, 사용자에게는 '티켓이 사라졌다' 로 보인다.
    """
    login_as("system_admin", email="tf-admin@goodmit.co.kr")
    first = client.get("/api/tickets/team?active=false&page=1&page_size=2").json()
    second = client.get("/api/tickets/team?active=false&page=2&page_size=2").json()

    assert first["total"] == second["total"] == 4
    assert len(_ids(first)) == 2 and len(_ids(second)) == 2
    assert set(_ids(first)) & set(_ids(second)) == set(), "두 페이지에 같은 티켓이 나왔다"
    assert set(_ids(first)) | set(_ids(second)) == {
        "page-t-1", "page-t-2", "page-t-3", "page-t-4"
    }, "페이지를 이어 붙였는데 빠진 티켓이 있다"
    # 전순서가 실제로 걸렸는지 — 목록 API 기본은 created_at desc 라 같은 시각이면 id 내림차순이다.
    assert _ids(first) + _ids(second) == [
        "page-t-4", "page-t-3", "page-t-2", "page-t-1"
    ], "정렬이 스캔 순서에 좌우된다 - 타이브레이커가 없다"


def test_page_size_caps_the_response_and_total_counts_everything(client, login_as, db, admin):
    """Z11 — 한 응답에 미러 전량이 실리지 않는다."""
    for i in range(25):
        _row(db, uid=f"z-{i:02d}", tid=i, due="2026-07-15")
    db.commit()
    _mirror_ready(db, 25)
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    body = client.get("/api/tickets/team?active=false").json()
    assert body["total"] == 25
    assert body["page"] == 1 and body["page_size"] == 20
    assert len(body["items"]) == 20, "페이지 상한이 안 걸렸다"
    # 이미 나가 있는 화면이 읽는 별칭도 같은 목록이어야 한다.
    assert body["tickets"] == body["items"]


def test_total_is_the_count_after_filters_not_before(client, login_as, catalog):
    login_as("system_admin", email="tf-admin@goodmit.co.kr")
    everything = client.get("/api/tickets/team?active=false").json()
    filtered = client.get("/api/tickets/team?active=false&status=검증").json()
    assert everything["total"] == 12
    assert filtered["total"] == 1, "total 이 필터 앞의 수다"


# ── 범위 판정은 그대로 걸린다 ─────────────────────────────────────────────────

@pytest.fixture()
def scoped(db, me, make_project):
    """범위 표본 — **프로젝트가 소속을 정한다** (0060 §11).

    담당자 축이 아니다. 우리 팀 프로젝트의 티켓은 담당자가 누구든(해석이 안 되어도) 우리
    팀에 보이고, 남의 팀 프로젝트의 티켓은 우리 담당자가 끼어 있어도 안 보인다.
    """
    ours = make_project(name="우리팀 프로젝트", dept=me.mine_dept_id)
    theirs = make_project(name="남의팀 프로젝트", dept=me.theirs_dept_id)
    _row(db, uid="s-mine", title="우리팀", assignees=(NID_ME,), due="2026-07-15", tid=1,
         project_uid=ours.id)
    _row(db, uid="s-mate", title="동료", assignees=(NID_MATE,), due="2026-07-16", tid=2,
         project_uid=ours.id)
    _row(db, uid="s-theirs", title="남의팀", assignees=(NID_OTHER,), due="2026-07-17", tid=3,
         project_uid=theirs.id)
    _row(db, uid="s-both", title="같이", assignees=(NID_ME, NID_OTHER), due="2026-07-18", tid=4,
         project_uid=ours.id)
    _row(db, uid="s-ghost", title="미해석", assignees=(NID_GHOST,), due="2026-07-19", tid=5,
         project_uid=ours.id)
    # 소속 자체를 해석 못 한 티켓 — 전역 관리자 말고는 아무에게도 안 보인다(fail-closed).
    _row(db, uid="s-orphan", title="소속없음", assignees=(NID_ME,), due="2026-07-20", tid=6)
    db.commit()
    _mirror_ready(db, 6)


def test_team_list_still_stops_at_the_team_boundary(client, login_as, scoped):
    """필터·페이지를 넣어도 남의 팀 티켓은 안 나온다 (1순위 유출 #1).

    0060 에서 경계를 긋는 것은 **프로젝트**다. 그래서 확인할 것이 하나 늘었다: 담당자가
    누구인지는 목록에 아무 영향이 없어야 한다.
    """
    login_as("user", email="tf-me@goodmit.co.kr")
    body = client.get("/api/tickets/team?active=false&page_size=100").json()
    titles = {t["title"] for t in body["items"]}

    assert "우리팀" in titles and "동료" in titles
    assert "남의팀" not in titles, "범위 판정이 필터·페이지 뒤에서 새고 있다"
    assert "같이" in titles, "우리 팀 프로젝트 티켓이 담당자 때문에 사라졌다"
    assert "미해석" in titles, (
        "담당자를 앱 사용자로 해석 못 했다는 이유로 우리 팀 프로젝트 티켓이 사라졌다 — "
        "그건 소속 문제가 아니라 매핑 문제이고, 진단 화면이 다룬다(0060 §12)"
    )
    assert "소속없음" not in titles, "소속을 판정할 수 없는 티켓이 팀 목록에 새어 나왔다"
    assert body["total"] == len(body["items"]), (
        "total 이 범위 판정 앞의 수다 - 화면이 없는 페이지를 그리게 된다"
    )


def test_a_status_filter_cannot_widen_the_team_boundary(client, login_as, scoped):
    """필터를 걸어도 범위가 넓어지지 않는다 — 조건이 OR 로 조립되면 여기서 터진다."""
    login_as("user", email="tf-me@goodmit.co.kr")
    body = client.get("/api/tickets/team?active=false&status=진행&page_size=100").json()
    assert {t["title"] for t in body["items"]} == {"우리팀", "동료", "같이", "미해석"}


def test_unassigned_means_no_assignee_not_an_unresolved_one(client, login_as, scoped, db):
    """미할당 = **담당자가 없다**. 담당자 해석 실패는 미할당이 아니다 (0060 §12).

    예전에는 둘을 같은 버킷에 넣었다. 그래서 "이 일을 아무도 안 맡고 있다"(사람이 집어
    가야 함)와 "맡고 있는데 앱이 그 사람을 못 알아본다"(관리자가 매핑을 고쳐야 함)가
    한 화면에 섞였다. 둘은 **다른 사람이 다른 행동을 해야 하는** 다른 사건이고, 섞이면
    이미 담당자가 있는 티켓을 다른 사람이 집어 가는 일이 실제로 벌어진다.

    매핑 실패는 이제 정합성 오류로 진단 화면(`/api/admin/integrity`)이 목록으로 보여 준다.
    """
    _row(db, uid="s-none", title="진짜 미할당", assignees=(), due="2026-07-21", tid=7,
         project_uid=_project_of(db, "s-mine"))
    db.commit()
    _mirror_ready(db, 7)

    login_as("user", email="tf-me@goodmit.co.kr")
    body = client.get("/api/tickets/unassigned?page_size=100").json()
    ids = set(_ids(body))
    assert "page-s-none" in ids, "담당자가 없는 티켓이 미할당 버킷에 없다"
    assert "page-s-ghost" not in ids, (
        "담당자가 있는데 해석만 실패한 티켓이 미할당으로 분류됐다 — 남이 집어 갈 수 있다"
    )
    assert "page-s-mine" not in ids and "page-s-both" not in ids
    assert body["total"] == len(body["items"])


def test_unassigned_bucket_pages_without_repeating(client, login_as, db, me, make_project):
    """미할당은 파이썬 판정 뒤에 자른다 — 그 경로도 페이지가 겹치면 안 된다."""
    project = make_project(name="페이징 프로젝트", dept=me.mine_dept_id)
    for i in range(5):
        _row(db, uid=f"u-{i}", title=f"미할당 {i}", assignees=(), due=None, tid=None,
             project_uid=project.id)
    db.commit()
    _mirror_ready(db, 5)
    login_as("user", email="tf-me@goodmit.co.kr")

    first = client.get("/api/tickets/unassigned?page=1&page_size=2").json()
    second = client.get("/api/tickets/unassigned?page=2&page_size=2").json()
    assert first["total"] == second["total"] == 5, "total 이 판정 뒤 값이 아니다"
    assert set(_ids(first)) & set(_ids(second)) == set()
    # 목록 API 기본은 created_at desc 라 같은 시각이면 id 내림차순이다.
    assert _ids(first) + _ids(second) == ["page-u-4", "page-u-3", "page-u-2", "page-u-1"]


def test_my_tickets_are_paged_and_filtered_too(client, login_as, db, me):
    _row(db, uid="m-1", title="내 검증", status="검증", assignees=(NID_ME,), due="2026-07-15", tid=1)
    _row(db, uid="m-2", title="내 진행", status="진행", assignees=(NID_ME,), due="2026-07-16", tid=2)
    _row(db, uid="m-3", title="남의 것", status="검증", assignees=(NID_OTHER,), due="2026-07-17", tid=3)
    db.commit()
    _mirror_ready(db, 3)
    login_as("user", email="tf-me@goodmit.co.kr")

    body = client.get("/api/tickets/mine?status=검증").json()
    assert _ids(body) == ["page-m-1"], "내 티켓 목록에 서버 필터가 안 걸렸다"
    assert body["total"] == 1

    body = client.get("/api/tickets/mine?page=1&page_size=1").json()
    assert body["total"] == 2 and len(body["items"]) == 1


# ── 미러가 없어졌다: 「실시간 폴백」이라는 경로 자체가 없다 ─────────────────


def test_there_is_no_second_read_path_to_disagree_with(client, login_as, catalog):
    """🔴 예전에는 목록을 답하는 길이 **둘**이었다 — 미러가 비면(첫 기동·킬 스위치)
    실시간으로 소스를 조회했다. 그 두 길이 서로 다른 필터를 걸면 "필터를 걸었는데 전체가
    나왔다" 가 되고, 사용자는 그걸 알아챌 수 없다.

    S14 뒤로 길이 하나다(D-284). 그래서 여기서 지키는 것은 「두 길이 같은 답을 낸다」가
    아니라 **「두 번째 길이 생기지 않았다」**이다: 응답에 신선도 블록이 없어야 한다. 그
    블록은 「지금 보는 값이 사본이다」라는 말이고, 그 말이 돌아오면 사본을 채우는 길도
    함께 돌아왔다는 뜻이다.

    빈 세계에서 통과하지 않도록 **행이 있는 상태**로 확인한다 — 위 시험들이 심어 둔
    티켓이 실제로 답에 실린 뒤에 단언한다.
    """
    login_as("system_admin", email="tf-nolive@goodmit.co.kr")

    body = client.get("/api/tickets/team?active=false").json()
    assert body["ok"] is True, body
    assert body["total"] > 0, "티켓이 하나도 없는 세계라 아래 단언이 아무것도 안 본다"
    assert "sync" not in body, f"신선도 블록이 돌아왔다: {body.get('sync')!r}"
    assert "can_sync" not in body, "화면에 동기화 버튼을 다시 그리라고 말하고 있다"


def test_repeated_status_params_are_or_and_other_axes_are_and(client, login_as, catalog):
    """같은 축의 값끼리는 OR, 다른 축은 AND. 값 하나만 보내도 예전처럼 그 하나만 걸린다."""
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    one = client.get("/api/tickets/team?active=false&status=검증").json()
    assert _ids(one) == ["page-a-status"]

    both = client.get("/api/tickets/team?active=false&status=검증&status=진행").json()
    titles = {row["title"] for row in both["items"]}
    assert "상태" in titles
    assert both["total"] >= 2

    mixed = client.get(
        f"/api/tickets/team?active=false&status=진행&project_id={PROJ}"
    ).json()
    assert _ids(mixed) == ["page-a-project"]


def test_list_sort_uses_allowlist_and_defaults_to_created_at(client, login_as, db, admin):
    """화면이 보낸 컬럼명을 SQL 에 붙이지 않는다. 기본은 생성 최신이고, 같은 시각이면 id."""
    older = datetime(2026, 7, 1, 0, 0, 0)
    newer = datetime(2026, 7, 20, 0, 0, 0)
    _row(db, uid="s-old", title="옛글", tid=1, created_at=older, due=FAR)
    _row(db, uid="s-new", title="새글", tid=2, created_at=newer, due=FAR)
    db.commit()
    _mirror_ready(db, 2)
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    default = client.get("/api/tickets/team?active=false&q=글").json()
    assert [row["title"] for row in default["items"][:2]] == ["새글", "옛글"]
    assert default["items"][0]["created_at"]

    asc = client.get("/api/tickets/team?active=false&q=글&sort=created_at&order=asc").json()
    assert [row["title"] for row in asc["items"][:2]] == ["옛글", "새글"]

    bad = client.get("/api/tickets/team?active=false&q=글&sort=injected").json()
    assert [row["title"] for row in bad["items"][:2]] == ["새글", "옛글"]


def test_act_wd_zero_is_not_missing_and_null_is_missing(client, login_as, db, admin):
    """실제 WD 0 은 값이다. 없는 것과 같은 칸에 '-' 로 그리면 안 되므로 API 도 0 을 0 으로 준다."""
    _row(db, uid="w-zero", title="공수0", tid=1, act_wd=0, due=FAR)
    _row(db, uid="w-none", title="공수없음", tid=2, act_wd=None, due=FAR)
    db.commit()
    _mirror_ready(db, 2)
    login_as("system_admin", email="tf-admin@goodmit.co.kr")

    body = client.get("/api/tickets/team?active=false&q=공수").json()
    by_title = {row["title"]: row["act_wd"] for row in body["items"]}
    assert by_title["공수0"] == 0
    assert by_title["공수없음"] is None

