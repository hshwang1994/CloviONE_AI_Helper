"""주간 헬스 스냅샷을 **주기 실행이 실제로 부른다**.

## 왜 이 파일이 필요한가

`app/projects/health.py` 와 `POST /{project_id}/health/snapshot` 은 이미 있었다. 그런데
그 엔드포인트를 부르는 것은 **사람뿐**이었다. 즉 아무도 손으로 누르지 않으면 이력이 한 줄도
안 쌓이고, 화면의 추세선은 영원히 빈 상태로 그럴듯하게 떠 있다. 빈 추세선은 "이 프로젝트는
계속 건강했다" 처럼 보이지 "아무도 안 쟀다" 처럼 보이지 않는다.

## 여기서 못 박는 다섯 가지

1. 주기 실행이 돌면 이력이 **실제로 생긴다**(순수 함수가 맞는 것과 배선이 이어진 것은
   다른 사건이다. 이 저장소는 그 차이로 이미 여러 번 속았다).
2. **두 번 돌려도 행이 두 줄이 안 된다.** `(project_id, week_of)` 가 유일하므로 재실행이
   행을 쌓으면 추세선이 '계산을 몇 번 돌렸나' 를 그리게 된다.
3. `score` 가 None 인 프로젝트는 **한 줄도 안 적는다.** 스냅샷 점수 열이 NOT NULL 이라
   0이든 100이든 적으면 거짓말이고, 몇 주 뒤 추세선에서 진짜 값과 구별되지 않는다.
4. 한 프로젝트가 터져도 **나머지는 저장된다.**
5. 그 실패가 **결과에 보인다.** 로그만 남기고 삼키면 아무도 모른다(이 저장소에는
   "백업 실패를 로그만 남기고 삼킨다" 는 미해결 항목이 이미 있다).

## 시각 표본을 왜 이렇게 잡는가

`NOW` 는 naive UTC 로 2026-08-02 23:30 이고 KST 로는 08-03(월) 08:30 이다. 판정 기준일을
UTC 로 뽑으면 '08-02'(일)가 되어 스냅샷이 **지난 주 칸**에 들어간다. 그 상태로도 이력은
쌓이므로 화면은 멀쩡해 보이고, 다음 주 값이 지난 주 칸을 덮어써야 비로소 이상해진다.
그래서 여기서는 저장된 `week_of` 를 직접 본다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project, ProjectHealthSnapshot, ProjectMilestone
from app.tickets.models import TicketCache

pytestmark = pytest.mark.integration

# naive UTC. KST 로는 2026-08-03(월) 08:30 이므로 그 주 월요일은 '2026-08-03' 이다.
NOW = datetime(2026, 8, 2, 23, 30, 0)
KST_TODAY = "2026-08-03"
WEEK = "2026-08-03"


@pytest.fixture()
def fake_clock():
    from tests.fakes.clock import FakeClock

    return FakeClock(NOW)


def _project(db, name, *, notion_page_id=None, notion_status=None, archived_at=None):
    row = Project(
        name=name, org_id=DEFAULT_ORG_ID, notion_page_id=notion_page_id,
        notion_status=notion_status, archived_at=archived_at,
        created_at=NOW, updated_at=NOW,
    )
    db.add(row)
    db.flush()
    return row


def _overdue_milestone(db, project):
    """기한이 한참 지난 마일스톤 하나 - 이것만 있어도 점수가 **나온다**(None 이 아니다)."""
    db.add(ProjectMilestone(
        project_id=project.id, name="1차 릴리스", due_on="2000-01-01",
    ))
    db.flush()


def _ticket(db, *, uid, project_page, due, assignee=""):
    db.add(TicketCache(
        id=uid, notion_page_id=uid, org_id=DEFAULT_ORG_ID, title=f"작업 {uid}",
        status="진행", due_date=due, project_ids=join_names([project_page]),
        project_names="", assignee_notion_ids=assignee, source="notion",
        synced_at=NOW, created_at=NOW, updated_at=NOW,
    ))
    db.flush()


def _snapshots(db, project_id=None):
    stmt = select(ProjectHealthSnapshot)
    if project_id is not None:
        stmt = stmt.where(ProjectHealthSnapshot.project_id == project_id)
    return list(db.execute(stmt).scalars().all())


# ── 스윕 자체 ────────────────────────────────────────────────────────────────

def test_the_sweep_writes_history_for_every_project_it_could_score(db, settings):
    """**배선 확인.** 스냅샷 함수가 맞아도 아무도 안 부르면 이력은 0줄이다."""
    from app.projects.service import record_health_snapshots

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    beta = _project(db, "베타", notion_page_id="page-beta")
    _overdue_milestone(db, alpha)
    _ticket(db, uid="t-1", project_page="page-beta", due="2000-02-01")
    db.commit()

    assert _snapshots(db) == [], "아직 아무도 안 불렀는데 이력이 있다"

    result = record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()

    assert result.recorded == 2, f"두 프로젝트를 못 적었다: {result.as_dict()}"
    assert result.failed == 0, f"실패가 있다: {result.as_dict()}"
    saved = {r.project_id: r for r in _snapshots(db)}
    assert set(saved) == {alpha.id, beta.id}, "이력이 안 쌓였다(추세선이 영원히 빈다)"
    for row in saved.values():
        assert row.week_of == WEEK, (
            f"판정 기준일이 KST 가 아니다 - 월요일 오전 9시 이전 저장이 지난 주 칸에 들어갔다: "
            f"{row.week_of}"
        )
        assert row.score is not None
        assert row.reasons_json and row.reasons_json != "[]", (
            "점수만 남기고 이유를 안 남겼다 - 6주 뒤에 왜 그 점수였는지 아무도 못 답한다"
        )


def test_running_the_sweep_twice_does_not_add_a_second_row_for_the_week(db, settings):
    """재실행이 행을 쌓으면 '주간 이력' 이 아니라 '실행 로그' 가 된다."""
    from app.projects.service import record_health_snapshots

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    _overdue_milestone(db, alpha)
    db.commit()

    record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()
    second = record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()

    rows = _snapshots(db, alpha.id)
    assert len(rows) == 1, f"같은 주에 {len(rows)}줄이 쌓였다: {[r.week_of for r in rows]}"
    assert second.recorded == 1, "두 번째 회차가 아무 일도 안 한 것처럼 보고한다"


def test_a_project_with_nothing_to_measure_is_skipped_not_scored_zero(db, settings):
    """잴 것이 없는 프로젝트는 **한 줄도 안 적는다.** 0도 100도 거짓말이다."""
    from app.projects.service import record_health_snapshots

    blank = _project(db, "포털 전용")           # 마일스톤도 작업도 노션 상태도 없다
    scored = _project(db, "알파", notion_page_id="page-alpha")
    _overdue_milestone(db, scored)
    db.commit()

    result = record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()

    assert _snapshots(db, blank.id) == [], (
        "잴 것이 없는 프로젝트에 점수를 적었다 - 추세선에서 진짜 값과 구별되지 않는다"
    )
    assert result.skipped == 1, f"건너뛴 것을 안 세고 있다: {result.as_dict()}"
    assert result.recorded == 1, f"점수를 낼 수 있는 프로젝트까지 빠뜨렸다: {result.as_dict()}"
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(Project, blank.id).health_score is None, (
        "점수를 낼 수 없는데 캐시 열에 값을 써 넣었다"
    )


def test_one_exploding_project_does_not_stop_the_rest(db, settings, monkeypatch):
    """한 건이 터져도 나머지는 저장된다. 전부 아니면 전무는 이력에서 가장 나쁜 선택이다."""
    from app.projects import service

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    boom = _project(db, "터지는 프로젝트", notion_page_id="page-boom")
    omega = _project(db, "오메가", notion_page_id="page-omega")
    for p in (alpha, boom, omega):
        _overdue_milestone(db, p)
    db.commit()

    real = service.project_health

    def _explode(db_, project, *, today):
        if project.id == boom.id:
            raise RuntimeError("이 프로젝트에서만 터진다")
        return real(db_, project, today=today)

    monkeypatch.setattr(service, "project_health", _explode)

    result = service.record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()

    saved = {r.project_id for r in _snapshots(db)}
    assert saved == {alpha.id, omega.id}, (
        f"한 건이 터지자 나머지까지 사라졌다: {saved}"
    )
    assert result.recorded == 2 and result.failed == 1, result.as_dict()


def test_a_half_written_failure_is_not_committed_with_everyone_else(
    db, settings, monkeypatch
):
    """터진 프로젝트가 세션에 남긴 **반쪽짜리 쓰기**가 남의 커밋에 얹혀 저장되면 안 된다.

    이게 try/except 만으로는 안 되는 이유다. 예외를 잡아도 그 프로젝트가 이미 더럽혀 놓은
    행은 세션에 그대로 남아 있고, 다음 프로젝트를 처리하며 일어나는 autoflush 나 마지막
    커밋에 **묻어서 함께 저장된다.** 결과는 최악의 모양이다: 회차는 '실패' 라고 보고했는데
    화면에는 그 실패한 계산의 점수가 떠 있다. 그래서 프로젝트마다 SAVEPOINT 를 잡는다.
    """
    from app.projects import service

    boom = _project(db, "터지는 프로젝트", notion_page_id="page-boom")
    omega = _project(db, "오메가", notion_page_id="page-omega")
    for p in (boom, omega):
        _overdue_milestone(db, p)
    db.commit()

    real = service.project_health

    def _dirty_then_explode(db_, project, *, today):
        if project.id == boom.id:
            # 실패 직전까지 이 행을 이미 건드려 놓은 상태를 만든다.
            project.health_score = 999
            raise RuntimeError("반쯤 쓰고 터졌다")
        return real(db_, project, today=today)

    monkeypatch.setattr(service, "project_health", _dirty_then_explode)

    result = service.record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()

    assert result.failed == 1
    assert db.get(Project, boom.id).health_score is None, (
        "실패한 회차의 반쪽짜리 값이 커밋됐다 - 회차는 실패라는데 화면엔 점수가 떠 있다"
    )
    assert db.get(Project, omega.id).health_score is not None, (
        "롤백이 남의 프로젝트까지 되돌렸다"
    )


def test_the_failure_is_visible_in_the_result_not_only_in_the_log(
    db, settings, monkeypatch
):
    """로그만 남기고 삼키면 아무도 모른다 - 어느 프로젝트가 왜 실패했는지 결과가 말한다."""
    from app.projects import service

    boom = _project(db, "터지는 프로젝트", notion_page_id="page-boom")
    _overdue_milestone(db, boom)
    db.commit()

    def _explode(db_, project, *, today):
        raise RuntimeError("표본이 이상하다")

    monkeypatch.setattr(service, "project_health", _explode)

    result = service.record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()

    assert result.failed == 1
    assert result.failures, "실패 건수만 세고 무엇이 실패했는지는 안 남겼다"
    failure = result.failures[0]
    assert failure.project_id == boom.id
    assert "표본이 이상하다" in failure.error, (
        f"왜 실패했는지가 결과에 없다: {failure.error}"
    )
    # 요약 문자열도 사람이 읽을 수 있어야 한다(운영 화면이 그대로 보여 준다).
    assert "터지는 프로젝트" in result.error_summary()


def test_the_sweep_leaves_updated_at_alone_when_the_score_did_not_move(db, settings):
    """주기 잡이 회차마다 전 프로젝트의 `updated_at` 을 덮으면 목록 정렬이 무너진다.

    목록은 `updated_at DESC` 로 정렬한다(repository.list_in_scope). 스냅샷 잡이 한 시간마다
    전 프로젝트를 건드리면 그 정렬이 사실상 id 순이 되고, **사용자가 방금 고친 프로젝트가
    맨 위에 오지 않는다.** 원인이 정렬 코드에 없어서 아무도 못 찾는다
    (app/projects/sync.py::_upsert 가 같은 함정을 기록한다).
    """
    from app.projects.service import record_health_snapshots

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    _overdue_milestone(db, alpha)
    db.commit()

    record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    after_first = db.get(Project, alpha.id).updated_at

    later = datetime(2026, 8, 3, 23, 30, 0)
    record_health_snapshots(db, today=KST_TODAY, now=later)
    db.commit()
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()

    assert db.get(Project, alpha.id).updated_at == after_first, (
        "점수가 그대로인데 갱신 시각을 덮었다 - 목록 정렬이 회차마다 무너진다"
    )


def test_archived_projects_do_not_grow_new_history(db, settings):
    """보관은 소프트 삭제다. 이력은 남기되 **새 점은 안 찍는다.**"""
    from app.projects.service import record_health_snapshots

    gone = _project(db, "보관된 프로젝트", notion_page_id="page-gone", archived_at=NOW)
    _overdue_milestone(db, gone)
    db.commit()

    result = record_health_snapshots(db, today=KST_TODAY, now=NOW)
    db.commit()

    assert _snapshots(db, gone.id) == [], "보관된 프로젝트에 새 점을 찍었다"
    assert result.recorded == 0 and result.skipped == 0 and result.failed == 0


# ── 워커 배선 ────────────────────────────────────────────────────────────────

class _StubWorker:
    """`Worker` 에서 이 배선이 쓰는 것은 `tick_callbacks` 하나뿐이다."""

    def __init__(self) -> None:
        self.tick_callbacks: list = []


def test_the_worker_tick_records_history_and_respects_its_interval(
    db, app, settings, fake_clock
):
    """**주기 실행이 이력을 만든다** - 이 파일의 본론이다.

    간격도 함께 본다: 틱은 워커 루프가 초당 여러 번 부르므로, 간격을 안 지키면 이 잡이
    루프를 통째로 잡아먹는다.
    """
    from app.worker_main import register_health_snapshot_tick

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    _overdue_milestone(db, alpha)
    db.commit()

    worker = _StubWorker()
    register_health_snapshot_tick(
        worker, app.state.session_factory, settings, interval=3600.0,
    )
    assert len(worker.tick_callbacks) == 1, "워커에 틱이 안 붙었다"
    tick = worker.tick_callbacks[0]

    tick(fake_clock.now())
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    rows = _snapshots(db, alpha.id)
    assert len(rows) == 1, f"주기 실행이 이력을 안 만들었다: {rows}"
    assert rows[0].week_of == WEEK

    # 같은 분에 여러 번 불려도 한 번만 돈다(그리고 행이 늘지 않는다).
    fake_clock.advance(5)
    tick(fake_clock.now())
    fake_clock.advance(5)
    tick(fake_clock.now())
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert len(_snapshots(db, alpha.id)) == 1, "재실행이 행을 쌓았다"


def test_the_worker_tick_records_the_run_where_a_human_can_see_it(
    db, app, settings, fake_clock, monkeypatch
):
    """돌았는지, 무엇을 못 했는지를 운영 화면이 읽는 표에 남긴다.

    로그만 남기면 "이 잡이 도는가?" 에 아무도 답할 수 없다. `sync_status` 는 관리자 화면이
    이미 읽는 표다(GET /api/system/status 의 `components`).
    """
    from app.observability.models import (
        COMPONENT_PROJECT_HEALTH,
        SYNC_ERROR,
        SYNC_OK,
        SyncStatus,
    )
    from app.projects import service
    from app.worker_main import run_health_snapshot_sweep

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    blank = _project(db, "포털 전용")
    _overdue_milestone(db, alpha)
    db.commit()
    assert blank.id  # 건너뛴 한 건이 결과에 세어져야 한다

    run_health_snapshot_sweep(app.state.session_factory, settings, fake_clock.now())

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    row = db.get(SyncStatus, COMPONENT_PROJECT_HEALTH)
    assert row is not None, "돌고도 아무 자국을 안 남겼다 - 사람이 확인할 방법이 없다"
    assert row.status == SYNC_OK
    assert row.last_success_at == fake_clock.now()
    assert row.item_count == 1, f"기록한 건수가 안 보인다: {row.item_count}"
    detail = row.detail_json or ""
    assert '"recorded": 1' in detail, f"기록 건수를 안 남겼다: {detail}"
    assert '"skipped": 1' in detail, (
        f"건너뛴 건수를 안 남겼다 - '잴 것이 없어 안 적었다' 와 '적을 게 없었다' 가 "
        f"화면에서 같아진다: {detail}"
    )
    assert '"failed": 0' in detail, f"실패 건수를 안 남겼다: {detail}"

    # 이제 실패시킨다 - 실패는 반드시 표에 남아야 한다.
    def _explode(db_, project, *, today):
        raise RuntimeError("표본이 이상하다")

    monkeypatch.setattr(service, "project_health", _explode)
    fake_clock.advance(3600)
    run_health_snapshot_sweep(app.state.session_factory, settings, fake_clock.now())

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    row = db.get(SyncStatus, COMPONENT_PROJECT_HEALTH)
    assert row.status == SYNC_ERROR, "실패했는데 화면에는 정상으로 보인다"
    assert row.error and "알파" in row.error, f"무엇이 실패했는지 안 적혔다: {row.error}"
    assert row.last_success_at != fake_clock.now(), (
        "실패 회차가 '마지막 정상 실행' 시각을 덮었다"
    )


def test_a_run_that_dies_outright_still_leaves_a_mark(
    db, app, settings, fake_clock, monkeypatch
):
    """회차가 **통째로** 터진 경우가 가장 조용하다 - 한 줄도 안 적히니 아무 자국이 없다.

    그리고 지난 회차의 건수를 0으로 덮지 않는다: "이번에 못 쟀다" 와 "이번엔 0건이었다" 는
    다른 사실이고, 덮어 버리면 화면에서 둘을 구별할 방법이 사라진다.
    """
    from app.observability.models import COMPONENT_PROJECT_HEALTH, SYNC_ERROR, SyncStatus
    from app.projects import service
    from app.worker_main import run_health_snapshot_sweep

    alpha = _project(db, "알파", notion_page_id="page-alpha")
    _overdue_milestone(db, alpha)
    db.commit()

    # 먼저 정상 회차 한 번 - 이 건수가 살아남아야 한다.
    run_health_snapshot_sweep(app.state.session_factory, settings, fake_clock.now())
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(SyncStatus, COMPONENT_PROJECT_HEALTH).item_count == 1

    def _boom(*_a, **_kw):
        raise RuntimeError("스윕이 통째로 죽었다")

    monkeypatch.setattr(service, "record_health_snapshots", _boom)
    fake_clock.advance(3600)
    assert run_health_snapshot_sweep(
        app.state.session_factory, settings, fake_clock.now()
    ) is None

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    row = db.get(SyncStatus, COMPONENT_PROJECT_HEALTH)
    assert row.status == SYNC_ERROR, "통째로 죽었는데 화면에는 정상으로 남아 있다"
    assert "스윕이 통째로 죽었다" in (row.error or ""), f"원인이 안 남았다: {row.error}"
    assert row.item_count == 1, (
        f"지난 회차 건수를 0으로 덮었다 - '못 쟀다' 가 '0건이었다' 로 바뀐다: {row.item_count}"
    )
    assert row.last_run_at == fake_clock.now(), "마지막 시도 시각이 안 움직였다"


def test_the_worker_tick_never_raises_into_the_worker_loop(settings, fake_clock):
    """이 잡의 실패가 다른 잡을 죽이면 안 된다(retention, 백업 틱과 같은 규약).

    세션 팩토리 자체를 터뜨린다 - DB 가 잠겨 있거나 파일이 사라진 상황이다. 그때 예외가
    워커 루프로 올라가면 스케줄러도, 동기화도, 잡 처리도 함께 멈춘다.
    """
    import app.worker_main as worker_main

    def _boom(*_a, **_kw):
        raise RuntimeError("세션 팩토리가 죽었다")

    worker = _StubWorker()
    worker_main.register_health_snapshot_tick(worker, _boom, settings, interval=3600.0)
    worker.tick_callbacks[0](fake_clock.now())


def test_main_actually_registers_the_tick():
    """위 테스트들이 헛것이 되지 않도록 - `main()` 이 실제로 이 틱을 등록하는지 본다.

    `main()` 은 시그널 핸들러와 리스를 잡고 무한 루프를 도는 함수라 테스트에서 부를 수 없다.
    그래서 등록 한 줄이 있는지를 소스에서 확인한다(tests/unit/test_search_no_hot_path.py 가
    같은 방법을 쓴다). 이 한 줄이 빠지면 위 테스트는 전부 통과하면서 **운영에서는 아무 일도
    일어나지 않는다** - 이 과제가 고치려는 결함이 정확히 그것이다.
    """
    import inspect

    from app import worker_main

    source = inspect.getsource(worker_main.main)
    assert "register_health_snapshot_tick(" in source, (
        "워커가 주간 헬스 스냅샷 틱을 등록하지 않는다 - 이력은 손으로 부를 때만 쌓인다"
    )
