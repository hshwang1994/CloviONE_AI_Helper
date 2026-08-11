"""프로젝트 Notion 양방향 동기화 (app/projects/sync.py).

이 파일이 지키는 것은 넷이다. 넷 다 "동작이 느리다" 가 아니라 **사람이 이미 한 일이 사라지지
않는다** 쪽이다.

  1. **소스가 빈 목록을 200 으로 주는 날.** 통합 권한 재조정·DB id 오설정·워크스페이스 이동은
     전부 HTTP 200 에 빈 결과다. 바닥이 없으면 그 회차가 전 프로젝트를 '삭제됨'으로 판정하고,
     지우면 CASCADE 로 마일스톤·주간 리포트·헬스 이력·참여자가 함께 사라진다. 넷 다 Notion 에
     없으므로 **재동기화로 돌아오지 않는다.**
  2. **예외가 밖으로 나가지 않는다.** 워커 tick 이 죽으면 같은 루프의 스케줄러·하트비트·문서
     동기화가 함께 멈춘다. 프로젝트 하나 때문에 앱의 배경 작업 전부가 서는 것이다.
  3. **못 읽었으면 못 읽었다고 말한다.** relation 을 못 따라가 프로젝트를 하나도 못 가져온
     회차를 `ok` 로 적으면, 화면은 '정상 동기화' 라고 말하는데 목록이 비어 있다. 사용자는
     "프로젝트 화면이 고장났다" 고 신고하고 관리자는 프로젝트 코드를 판다.
  4. **두 진행률이 나란히 나온다.** Notion 의 rollup 은 취소한 티켓을 완료로 세므로 앱 계산값과
     다른 것이 **정상**이다. 한쪽만 보이면 사용자는 "포털이 틀렸다"고 결론 내리고, 그러면
     정확한 쪽을 안 보게 된다.

그리고 쓰기(포털 → Notion): 저장이 실제 Notion 호출을 만드는지, 두 사람이 동시에 고쳤을 때
나중 사람이 앞사람 변경을 조용히 덮어쓰지 않는지.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.models_base import split_names
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import (
    PROJECT_SYNC_STATE_ID,
    SYNC_ERROR,
    SYNC_OK,
    Project,
    ProjectMilestone,
    ProjectSyncState,
    ProjectWeeklyReport,
)
from app.projects.sync import sync_projects
from app.tickets.models import TicketCache
from tests.fakes.clock import FakeClock
from tests.fakes.notion import (
    DEFAULT_PROJECTS_DB,
    PROJ_PROP_PERIOD,
    PROJ_PROP_STATUS,
    PROJ_PROP_TITLE,
    FakeNotionProjectsDB,
    FakeNotionTasksDB,
    project_page,
)

pytestmark = pytest.mark.integration

TOKEN_REF = "notion_report_token"
BOSS_EMAIL = "prj-sync@goodmit.co.kr"
NOW = datetime(2026, 8, 6, 9, 0, 0)

PAGE_ALPHA = "notion-proj-alpha"
PAGE_BETA = "notion-proj-beta"

BASE_PAGES = [
    project_page(
        page_id=PAGE_ALPHA, title="알파 프로젝트", status="진행 중",
        start="2026-07-01", end="2026-09-30", biz_type="SI", product="클라우드",
        # Notion 은 30% 라고 말한다(0..1 비율로 온다).
        project_progress=0.3,
    ),
    project_page(
        page_id=PAGE_BETA, title="베타 프로젝트", status="백로그", start="2026-08-01",
    ),
]


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture()
def outbound(settings, fake_http):
    from app.core.allowlist import AllowlistRegistry
    from app.core.http_client import OutboundClient
    from app.core.secret_refs import FileSecretReferenceProvider

    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    return OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
        transport=fake_http.transport(),
    )


@pytest.fixture()
def tasks(fake_http) -> FakeNotionTasksDB:
    """작업 DB 페이크. 프로젝트 DB id 는 **여기 relation 을 따라가서** 찾는다.

    설정값이 아니라 relation 을 따라가는 것이 설계다(app/projects/notion_source.py) -
    두 id 가 같은 DB 에서 왔다는 것이 구조적으로 보장돼야 진행률이 이어진다.
    """
    return FakeNotionTasksDB(rows=[], projects_db=DEFAULT_PROJECTS_DB).install(fake_http)


@pytest.fixture()
def notion(fake_http, tasks) -> FakeNotionProjectsDB:
    return FakeNotionProjectsDB(
        pages=[dict(p) for p in BASE_PAGES],
        fail_message="동기화 테스트용 강제 오류",
    ).install(fake_http)


def _projects(db) -> dict[str, Project]:
    return {p.notion_page_id: p for p in db.query(Project).all() if p.notion_page_id}


def _sync(db, settings, outbound, clock) -> ProjectSyncState:
    state = sync_projects(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    return state


def _login_global_admin(client, login_as, db) -> str:
    """전역 범위 관리자로 로그인하고 CSRF 토큰을 돌려준다.

    전역으로 올리는 이유: 동기화가 만든 프로젝트는 `dept_id` 가 비어 있고, 부서 없는
    프로젝트는 부서 범위 사용자에게 안 보인다(repository.py 의 규칙). 범위를 안 올리면
    이 파일의 API 테스트가 전부 404 로 끝나는데, 그건 이 테스트가 보려는 것이 아니다.
    """
    from app.users.service import get_user_by_email

    token = login_as("admin", email=BOSS_EMAIL)
    boss = get_user_by_email(db, BOSS_EMAIL)
    boss.admin_scope = "global"
    db.commit()
    return token


# ── 읽기: Notion → 앱 ─────────────────────────────────────────────────────────


def test_first_sync_mirrors_projects_without_touching_app_only_fields(
    db, settings, outbound, notion, clock
):
    """첫 회차. 미러 컬럼은 채우고 **앱 정본 컬럼은 건드리지 않는다.**"""
    state = _sync(db, settings, outbound, clock)

    assert state.status == SYNC_OK
    assert state.last_success_at == clock.now()
    assert state.project_count == 2

    rows = _projects(db)
    assert set(rows) == {PAGE_ALPHA, PAGE_BETA}
    alpha = rows[PAGE_ALPHA]
    assert alpha.name == "알파 프로젝트"
    assert alpha.starts_on == "2026-07-01"
    assert alpha.ends_on == "2026-09-30", "기간의 끝 날짜가 유실됐다(date range 를 하루로 읽었다)"
    assert alpha.biz_type == "SI"
    assert alpha.product == "클라우드"
    # 진행 상태는 **원문 그대로**. 앱 status 어휘로 뭉개면 '차질' 이 표현되지 않는다.
    assert alpha.notion_status == "진행 중"
    assert alpha.notion_progress_pct == 30.0, "0..1 비율을 퍼센트로 안 바꿨다"
    assert alpha.notion_synced_at == clock.now()

    # 앱이 계산하는 값은 동기화가 손대지 않는다. NULL 은 '아직 계산 안 함' 이라는 뜻이고,
    # 여기에 Notion 숫자를 받아 적으면 취소한 티켓을 완료로 센 값이 앱의 정본이 된다.
    assert alpha.progress_pct is None
    assert alpha.health_score is None
    assert alpha.dept_id is None


def test_the_app_number_and_the_notion_number_both_come_out(
    client, login_as, db, settings, outbound, notion, clock
):
    """**두 값이 다를 때 둘 다 실려 나오는가.**

    Notion 은 30% 라고 말하고 앱은 취소를 빼고 다시 세어 다른 숫자를 낸다. 이 화면의 목적이
    그 차이를 **설명**하는 것이라, 한쪽만 실려 나오면 사용자는 어느 쪽도 못 믿는다.
    """
    _sync(db, settings, outbound, clock)
    alpha = _projects(db)[PAGE_ALPHA]

    # 완료 1건(3WD) + 진행 1건(7WD) + 취소 1건(90WD). 앱은 취소를 분자·분모에서 함께 뺀다.
    for uid, page, status, est in (
        ("t-done", "tk-1", "완료", 3.0),
        ("t-open", "tk-2", "진행", 7.0),
        ("t-cancelled", "tk-3", "취소", 90.0),
    ):
        db.add(TicketCache(
            id=uid, notion_page_id=page, org_id=DEFAULT_ORG_ID, title="작업",
            status=status, est_wd=est,
            project_ids="\x1f" + PAGE_ALPHA + "\x1f", project_names="",
            assignee_notion_ids="", source="notion",
            synced_at=NOW, created_at=NOW, updated_at=NOW,
        ))
    db.commit()

    token = _login_global_admin(client, login_as, db)

    body = client.get(
        f"/api/projects/{alpha.id}/progress", headers={"X-CSRF-Token": token}
    ).json()

    assert body["percent"] == 30.0, f"앱 계산값이 3/(3+7) 이 아니다: {body}"
    assert body["notion_percent"] == 30.0

    # 여기서부터가 이 테스트의 요점이다. 취소를 하나 더 만들면 **앱만** 숫자가 움직인다.
    db.get(TicketCache, "t-open").status = "취소"
    db.commit()

    body = client.get(
        f"/api/projects/{alpha.id}/progress", headers={"X-CSRF-Token": token}
    ).json()
    assert body["percent"] == 100.0, "취소를 분모에서 안 뺐다"
    assert body["notion_percent"] == 30.0, (
        "Notion 값이 앱 계산값을 따라 움직였다 - 둘은 서로 다른 사실이어야 한다"
    )
    assert body["percent"] != body["notion_percent"]

    detail = client.get(
        f"/api/projects/{alpha.id}", headers={"X-CSRF-Token": token}
    ).json()["project"]
    assert detail["notion_progress_pct"] == 30.0, (
        "상세 응답에 Notion 진행률이 없다 - 화면이 두 숫자를 나란히 못 그린다"
    )
    assert detail["notion_status"] == "진행 중"


def test_empty_source_never_prunes_and_says_so(db, settings, outbound, notion, clock):
    """소스가 0건을 주면 한 건도 표시하지 않고, 상태를 error 로 남긴다."""
    _sync(db, settings, outbound, clock)
    assert len(_projects(db)) == 2

    notion.pages = []  # 오류가 아니다 - 200 OK 에 빈 목록
    clock.advance(600)
    state = _sync(db, settings, outbound, clock)

    rows = _projects(db)
    assert set(rows) == {PAGE_ALPHA, PAGE_BETA}
    assert all(r.notion_missing_at is None for r in rows.values()), (
        "빈 응답 한 번에 전 프로젝트가 'Notion 에 없음'으로 표시됐다"
    )
    assert state.status == SYNC_ERROR, "'ok' 라고 하면 아무도 안 본다"
    assert state.pruned_count == 0
    assert "0건" in (state.error or "")


def test_empty_source_preserves_milestones_and_weekly_reports(
    db, settings, outbound, notion, clock
):
    """프로젝트에 매달린 **앱에만 있는 데이터**가 살아남는가.

    프로젝트를 지우면 CASCADE 로 마일스톤과 주간 리포트가 함께 사라지는데, 둘 다 Notion 에
    없으므로 다음 정상 동기화로 돌아오지 않는다. 주간 리포트는 특히 '그때 무엇을 보고 그렇게
    판단했는가'의 기록이라 재계산으로도 복구되지 않는다.
    """
    _sync(db, settings, outbound, clock)
    alpha = _projects(db)[PAGE_ALPHA]
    db.add(ProjectMilestone(project_id=alpha.id, name="1차 납품", due_on="2026-08-20"))
    db.add(ProjectWeeklyReport(
        project_id=alpha.id, week_of="2026-08-03",
        summary_md="이번 주에 사람이 직접 쓴 판단", generated_at=NOW,
    ))
    db.commit()

    notion.pages = []
    clock.advance(600)
    _sync(db, settings, outbound, clock)

    assert db.query(ProjectMilestone).count() == 1
    assert db.query(ProjectWeeklyReport).count() == 1
    assert db.get(Project, alpha.id) is not None


def test_mass_deletion_is_refused(db, settings, outbound, notion, clock):
    """한 회차가 절반을 넘게 지우려 하면 막는다 - 부분 실패도 소스 장애로 본다."""
    notion.pages = [
        project_page(page_id=f"notion-proj-{i:02d}", title=f"프로젝트{i}", status="진행 중")
        for i in range(1, 11)
    ]
    _sync(db, settings, outbound, clock)
    assert len(_projects(db)) == 10

    notion.pages = notion.pages[:4]  # 10 → 4 (60% 를 지우려 한다)
    clock.advance(600)
    state = _sync(db, settings, outbound, clock)

    assert all(r.notion_missing_at is None for r in _projects(db).values())
    assert state.status == SYNC_ERROR
    assert "60%" in (state.error or "")


def test_normal_prune_marks_but_never_deletes(db, settings, outbound, notion, clock):
    """바닥은 정상 삭제를 막지 않는다. 다만 **표시할 뿐 지우지 않는다.**

    그리고 티켓과 갈리는 지점: 표시된 프로젝트는 목록에서 **감추지 않는다**. 감추면 Notion 이
    한 회차 깜빡인 순간 포털의 마일스톤·주간 리포트가 화면에서 통째로 사라진다.
    """
    notion.pages = [
        project_page(page_id=f"notion-proj-{i:02d}", title=f"프로젝트{i}", status="진행 중")
        for i in range(1, 11)
    ]
    _sync(db, settings, outbound, clock)

    # 사라질 프로젝트에 **앱에만 있는 것**을 붙여 둔다. 하드 삭제면 CASCADE 로 함께 죽는다.
    doomed = _projects(db)["notion-proj-10"]
    db.add(ProjectMilestone(project_id=doomed.id, name="검수", due_on="2026-09-01"))
    db.add(ProjectWeeklyReport(
        project_id=doomed.id, week_of="2026-08-03",
        summary_md="사람이 쓴 판단", generated_at=NOW,
    ))
    db.commit()

    notion.pages = notion.pages[:8]  # 10 → 8 (20% - 정상 범위)
    clock.advance(600)
    state = _sync(db, settings, outbound, clock)

    rows = _projects(db)
    assert len(rows) == 10, "프로젝트 행이 지워졌다 - 앱 정본과 그 자식들이 함께 사라진다"
    marked = [p for p in rows.values() if p.notion_missing_at is not None]
    assert len(marked) == 2
    assert marked[0].notion_missing_at == clock.now()
    assert state.status == SYNC_OK
    assert state.pruned_count == 2
    # 여기가 소프트 프룬의 값이다. 이 둘은 Notion 에 없어서 재동기화로 돌아오지 않는다.
    assert db.query(ProjectMilestone).count() == 1
    assert db.query(ProjectWeeklyReport).count() == 1


def test_a_returning_project_loses_its_missing_mark(db, settings, outbound, notion, clock):
    """다음 회차에 돌아오면 아무 일도 없었던 것이 된다."""
    _sync(db, settings, outbound, clock)
    notion.pages = [dict(p) for p in BASE_PAGES if p["id"] != PAGE_BETA]
    clock.advance(600)
    _sync(db, settings, outbound, clock)
    assert _projects(db)[PAGE_BETA].notion_missing_at is not None, (
        "이 테스트의 전제(한 건이 사라져 표시된다)가 깨졌다"
    )

    notion.pages = [dict(p) for p in BASE_PAGES]
    clock.advance(600)
    _sync(db, settings, outbound, clock)
    assert _projects(db)[PAGE_BETA].notion_missing_at is None


def test_truncated_sync_never_marks(db, settings, outbound, notion, clock):
    """상한에 걸린 회차는 prune 을 건너뛴다 - 못 받아온 것과 삭제된 것은 다르다."""
    _sync(db, settings, outbound, clock)

    notion.always_has_more = True
    notion.pages = [dict(BASE_PAGES[0])]  # 두 번째는 이번 회차에 아예 안 왔다
    clock.advance(600)
    state = _sync(db, settings, outbound, clock)

    assert state.truncated is True
    assert state.status == SYNC_OK  # 실패는 아니다 - 다만 불완전하다
    assert "상한" in (state.error or "")
    assert _projects(db)[PAGE_BETA].notion_missing_at is None


def test_source_failure_keeps_the_mirror_and_last_success(
    db, settings, outbound, notion, clock
):
    """소스가 5xx 를 뱉어도 이전 값은 그대로 남고 '마지막 정상' 시각이 보존된다."""
    _sync(db, settings, outbound, clock)
    before = {pid: (p.name, p.notion_status) for pid, p in _projects(db).items()}
    first_success = db.get(ProjectSyncState, PROJECT_SYNC_STATE_ID).last_success_at

    notion.fail_status = 500
    clock.advance(600)
    state = _sync(db, settings, outbound, clock)

    assert state.status == SYNC_ERROR
    assert state.error
    assert state.last_run_at == clock.now()
    # 이 값이 지워지면 화면이 신선도를 거짓말한다.
    assert state.last_success_at == first_success
    assert {pid: (p.name, p.notion_status) for pid, p in _projects(db).items()} == before


def test_missing_project_relation_is_promoted_to_sync_error(
    db, settings, outbound, notion, tasks, clock
):
    """relation 을 못 따라가면 프로젝트를 하나도 못 가져온다 - 그때 `ok` 라고 하면 안 된다.

    티켓 쪽 C4 와 같은 이유다: 화면은 '정상 동기화' 라고 말하는데 프로젝트 목록이 비어 있다.
    사용자는 "프로젝트 화면이 고장났다" 고 신고하고 관리자는 프로젝트 코드를 판다.

    그리고 **prune 을 절대 안 돈다** - 못 읽은 것을 '삭제됨' 으로 표시하면 이미 있던 프로젝트
    전부에 "Notion 짝 없음" 배지가 붙는다.
    """
    _sync(db, settings, outbound, clock)
    assert len(_projects(db)) == 2

    # 작업 DB 에서 프로젝트 relation 속성이 사라졌다(이름 변경·속성 삭제).
    schema = dict(tasks.schema)
    schema.pop("프로젝트", None)
    tasks.schema = schema

    clock.advance(600)
    state = _sync(db, settings, outbound, clock)

    assert state.status == SYNC_ERROR, "프로젝트를 하나도 못 읽었는데 정상이라고 말한다"
    assert "프로젝트" in (state.error or "")
    assert all(p.notion_missing_at is None for p in _projects(db).values()), (
        "못 읽은 회차가 기존 프로젝트를 'Notion 에 없음'으로 표시했다"
    )


def test_missing_token_is_recorded_not_raised(db, settings, outbound, notion, clock):
    """토큰 파일이 없으면(미연동) 예외가 아니라 상태 기록으로 끝나야 한다."""
    (settings.secrets_dir / TOKEN_REF).unlink()
    state = _sync(db, settings, outbound, clock)
    assert state.status == SYNC_ERROR
    assert not _projects(db), "없던 프로젝트가 생기지도 않는다"


def test_worker_tick_never_raises(db, settings, outbound, notion, clock, monkeypatch):
    """워커 tick 은 어떤 예외도 루프 밖으로 내보내지 않는다.

    tick 하나가 죽으면 같은 루프의 스케줄러·하트비트·문서 동기화가 전부 함께 멈춘다.
    """
    import app.projects.sync as sync_module

    def boom(*args, **kwargs):
        raise RuntimeError("아무도 예상 못 한 실패")

    monkeypatch.setattr(sync_module.notion_source, "query_all_projects_paged", boom)

    # 조회가 통째로 터져도 sync 는 예외를 밖으로 내보내지 않고 상태에만 적는다.
    state = sync_projects(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    assert state.status == SYNC_ERROR
    assert state.error


def test_a_no_op_sync_does_not_bump_updated_at(db, settings, outbound, notion, clock):
    """아무것도 안 바뀐 회차가 `updated_at` 을 찍으면 목록 정렬이 매 회차 뒤섞인다.

    정렬이 `updated_at DESC` 라(repository.list_in_scope) 회차마다 찍으면 '최근 갱신' 이
    아무 뜻도 없게 되고, 사용자가 방금 고친 프로젝트가 맨 위에 안 온다.
    """
    _sync(db, settings, outbound, clock)
    before = _projects(db)[PAGE_ALPHA].updated_at

    clock.advance(600)
    _sync(db, settings, outbound, clock)
    assert _projects(db)[PAGE_ALPHA].updated_at == before

    notion.pages[0]["properties"][PROJ_PROP_TITLE]["title"] = [
        {"type": "text", "plain_text": "알파 프로젝트(이름 변경)"}
    ]
    clock.advance(600)
    _sync(db, settings, outbound, clock)
    row = _projects(db)[PAGE_ALPHA]
    assert row.name == "알파 프로젝트(이름 변경)"
    assert row.updated_at == clock.now(), "실제로 바뀐 회차인데 갱신 시각이 안 찍혔다"


# ── 쓰기: 앱 → Notion ─────────────────────────────────────────────────────────


@pytest.fixture()
def portal(client, login_as, db, settings, outbound, notion, clock):
    """동기화를 한 번 돌려 놓고, 전역 관리자로 로그인한 상태를 만든다."""
    _sync(db, settings, outbound, clock)
    token = _login_global_admin(client, login_as, db)
    project = _projects(db)[PAGE_ALPHA]
    detail = client.get(
        f"/api/projects/{project.id}", headers={"X-CSRF-Token": token}
    ).json()["project"]
    return {"token": token, "id": project.id, "view": detail}


def _patched_props(notion) -> dict:
    assert notion.patched, "포털에서 저장했는데 Notion 호출이 하나도 없다"
    return notion.patched[-1][1].get("properties") or {}


def test_editing_in_the_portal_pushes_to_notion(client, db, notion, portal):
    """이름·상태·기간을 고치면 그 값이 실제로 Notion 으로 나간다."""
    r = client.patch(
        f"/api/projects/{portal['id']}",
        json={
            "name": "알파 프로젝트(포털에서 고침)",
            "notion_status": "차질",
            "starts_on": "2026-07-05",
            "ends_on": "2026-10-31",
            "base_notion_version": portal["view"]["notion_version"],
        },
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()["project"]
    assert body["notion_sync_error"] is None, f"push 가 실패했다: {body['notion_sync_error']}"

    props = _patched_props(notion)
    assert notion.patched[-1][0] == PAGE_ALPHA
    assert props[PROJ_PROP_TITLE]["title"][0]["text"]["content"] == "알파 프로젝트(포털에서 고침)"
    assert props[PROJ_PROP_STATUS]["status"]["name"] == "차질"
    # 기간은 date range 다. `end` 를 안 보내면 저장 한 번에 종료일이 조용히 지워진다.
    assert props[PROJ_PROP_PERIOD]["date"] == {"start": "2026-07-05", "end": "2026-10-31"}


def test_what_the_portal_pushed_survives_the_next_sync(
    client, db, settings, outbound, notion, clock, portal
):
    """**양방향이 서로를 되돌리지 않는가.**

    push 와 읽기가 서로 다른 속성을 쓰면(예: 쓰기는 `제목`, 읽기는 `이름`) 저장은 성공하고
    다음 동기화가 조용히 옛 이름으로 되돌린다. 사용자에게는 "저장이 가끔 풀린다" 로 보이고,
    그 사이 아무 오류도 안 난다 - 두 이름이 다르다는 것을 아무도 모른다.
    """
    r = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "포털이 정한 이름", "notion_status": "차질",
              "base_notion_version": portal["view"]["notion_version"]},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert r.status_code == 200, r.text

    clock.advance(600)
    _sync(db, settings, outbound, clock)

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    row = db.get(Project, portal["id"])
    assert row.name == "포털이 정한 이름", "다음 동기화가 포털의 저장을 되돌렸다"
    assert row.notion_status == "차질"


def test_a_second_saver_is_stopped_instead_of_overwriting_the_first(
    client, db, notion, portal
):
    """두 사람이 같은 폼을 열어 두면 나중 사람이 앞사람 변경을 조용히 덮어쓴다.

    양쪽 다 성공 화면을 보기 때문에 아무도 무엇이 사라졌는지 모른다. 그래서 막는다.
    """
    stale_version = portal["view"]["notion_version"]

    first = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "앞사람이 저장한 이름", "base_notion_version": stale_version},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert first.status_code == 200, first.text
    calls_after_first = len(notion.patched)

    second = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "뒷사람이 저장한 이름", "base_notion_version": stale_version},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert second.status_code == 409, (
        f"앞사람 변경을 조용히 덮어썼다: {second.status_code} {second.text}"
    )

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(Project, portal["id"]).name == "앞사람이 저장한 이름"
    assert len(notion.patched) == calls_after_first, (
        "충돌인데 Notion 까지 밀어 넣었다 - 로컬만 막고 저쪽은 덮어썼다"
    )


def test_a_fresh_version_lets_the_second_save_through(client, db, notion, portal):
    """잠금이 정상 저장까지 막으면 안 된다 - 새로고침한 사람은 통과해야 한다."""
    first = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "첫 저장", "base_notion_version": portal["view"]["notion_version"]},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert first.status_code == 200, first.text

    second = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "새로고침 뒤 저장",
              "base_notion_version": first.json()["project"]["notion_version"]},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert second.status_code == 200, second.text
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(Project, portal["id"]).name == "새로고침 뒤 저장"


def test_a_status_notion_does_not_know_is_refused_before_it_is_sent(
    client, db, notion, portal
):
    """Notion 에 없는 상태값은 저쪽에 보내지 않는다.

    그냥 보내면 Notion 이 400 을 주고 우리는 그것을 502 로 올린다. 화면에는 "Notion 응답
    오류" 가 뜨는데 원인은 사용자가 고른 값 하나다 - 아무도 자기 입력을 의심하지 않는다.
    """
    before = len(notion.patched)
    r = client.patch(
        f"/api/projects/{portal['id']}",
        json={"notion_status": "이런 상태는 노션에 없다",
              "base_notion_version": portal["view"]["notion_version"]},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert r.status_code == 200, r.text
    error = r.json()["project"]["notion_sync_error"]
    assert error and "진행 상태" in error, f"이유를 우리 말로 안 알려 준다: {error}"
    assert len(notion.patched) == before, "모르는 값을 그대로 Notion 에 보냈다"


def test_a_push_failure_does_not_roll_back_what_the_user_typed(
    client, db, notion, portal
):
    """Notion 이 죽어도 사용자가 방금 고친 값은 남는다. 다만 '저장됨' 이라고만 하지 않는다."""
    notion.patch_status = 500

    r = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "노션이 죽은 동안 고친 이름",
              "base_notion_version": portal["view"]["notion_version"]},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()["project"]
    assert body["name"] == "노션이 죽은 동안 고친 이름"
    assert body["notion_sync_error"], "반영 실패를 화면이 말할 방법이 없다"

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    row = db.get(Project, portal["id"])
    assert row.name == "노션이 죽은 동안 고친 이름", "Notion 장애 때문에 사용자 입력이 사라졌다"
    assert row.notion_sync_error


def test_a_portal_only_project_is_never_pushed(client, login_as, db, notion, portal):
    """Notion 짝이 없는 프로젝트는 밀어 넣을 곳이 없다 - 실패로 표시하지도 않는다."""
    hdr = {"X-CSRF-Token": portal["token"]}
    created = client.post(
        "/api/projects", json={"name": "포털 전용"}, headers=hdr
    ).json()["project"]
    before = len(notion.patched)

    r = client.patch(
        f"/api/projects/{created['id']}", json={"name": "이름만 고침"}, headers=hdr
    )
    assert r.status_code == 200, r.text
    assert r.json()["project"]["notion_sync_error"] is None
    assert len(notion.patched) == before


def test_editing_only_app_fields_does_not_call_notion(client, db, notion, portal):
    """목표만 고친 저장이 외부 왕복 세 번을 만들면 안 된다."""
    before = len(notion.patched)
    r = client.patch(
        f"/api/projects/{portal['id']}",
        json={"goal": "노션에는 없는 앱 전용 목표"},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert r.status_code == 200, r.text
    assert len(notion.patched) == before

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(Project, portal["id"]).goal == "노션에는 없는 앱 전용 목표"


def test_the_owner_is_not_wiped_when_the_portal_cannot_resolve_them(
    client, db, settings, outbound, notion, clock, portal
):
    """담당자를 앱 사용자로 해석 못 하면 **원래 값을 그대로 되돌려 보낸다.**

    빈 목록을 보내면 저쪽 담당자가 지워진다. 포털에 매핑이 없는 사람이 담당자인 프로젝트를
    포털에서 한 번 저장했다고 저쪽 담당자가 사라지면, 그건 우리가 모른다는 이유로 지운 것이다.
    """
    row = db.get(Project, portal["id"])
    row.notion_owner_ids = "\x1f" + "notion-person-not-in-portal" + "\x1f"
    row.owner_user_id = None
    db.commit()

    r = client.patch(
        f"/api/projects/{portal['id']}",
        json={"name": "담당자는 안 건드림"},
        headers={"X-CSRF-Token": portal["token"]},
    )
    assert r.status_code == 200, r.text

    props = _patched_props(notion)
    people = props.get("담당자(정)", {}).get("people") or []
    assert [p["id"] for p in people] == ["notion-person-not-in-portal"], (
        f"모르는 담당자를 지워 버렸다: {people}"
    )


def test_sync_does_not_wipe_the_owner_it_cannot_resolve(
    db, settings, outbound, notion, clock
):
    """읽기 쪽도 같다 - 해석 안 되는 담당자 때문에 기존 소유자를 지우지 않는다."""
    notion.pages = [
        project_page(page_id=PAGE_ALPHA, title="알파", status="진행 중",
                     owner=["notion-person-not-in-portal"]),
    ]
    _sync(db, settings, outbound, clock)
    row = _projects(db)[PAGE_ALPHA]
    assert row.owner_user_id is None
    # 원문은 잃지 않는다 - 나중에 그 사람이 포털에 매핑되면 그때 이어진다.
    assert split_names(row.notion_owner_ids) == ["notion-person-not-in-portal"]
