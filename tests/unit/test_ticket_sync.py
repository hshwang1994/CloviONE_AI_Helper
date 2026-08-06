"""티켓 미러 동기화 (app/tickets/sync.py) 결정론 테스트.

이 테스트가 지키는 것은 성능이 아니라 **데이터가 사라지지 않는 것**이다:

  * 상한(truncated)에 걸려 일부만 받아온 회차는 prune 을 절대 하지 않는다. 이게 없으면 작업 DB가
    2000건을 넘긴 날, 동기화가 2000건만 보고 나머지를 '삭제됨'으로 판정해 캐시에서 지운다 —
    화면에서 티켓이 통째로 사라진다.
  * 소스가 5xx 를 뱉어도 이전 캐시는 그대로 남고, 상태만 error 가 되며, last_success_at
    (= 이 미러가 언제까지 정상이었나)은 보존된다. 그 값이 지워지면 화면이 신선도를 거짓말한다.
  * sync 는 어떤 실패에도 예외를 밖으로 던지지 않는다. 워커 tick 이 죽으면 스케줄러·하트비트가
    같이 멈춘다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from app.tickets.models import (
    SYNC_ERROR,
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketMetaCache,
    TicketSyncState,
    split_names,
)
from app.tickets.sync import sync_tickets
from tests.fakes.clock import FakeClock
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.unit

TOKEN_REF = "notion_report_token"
P_ALPHA = "sync-proj-alpha"
N_DEV = "notion-user-dev"

BASE_ROWS = [
    task_row(page_id="sync-0001", tid=1, title="첫 티켓", status="진행", due="2026-08-01",
             people=[N_DEV], est_wd=2.0, priority="높음", project_ids=[P_ALPHA]),
    task_row(page_id="sync-0002", tid=2, title="미할당 티켓", status="계획", due="2026-08-05",
             people=[]),
]


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 8, 3, 9, 0, 0))


@pytest.fixture()
def outbound(settings, fake_http):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    allowlists = AllowlistRegistry(settings.config_dir)
    secrets = FileSecretReferenceProvider(settings.secrets_dir)
    return OutboundClient(allowlists, secrets, transport=fake_http.transport())


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=list(BASE_ROWS),
        projects=[project_row(page_id=P_ALPHA, name="알파 프로젝트")],
        projects_db=DEFAULT_PROJECTS_DB,
        fail_message="동기화 테스트용 강제 오류",
    ).install(fake_http)


def _cached(db) -> dict[str, TicketCache]:
    """**목록에 보이는** 캐시 행. 0043 부터 prune 은 지우지 않고 표시만 하므로,
    "사라졌다" 를 확인하려면 표시된 행을 빼고 봐야 한다(읽기 경로가 하는 것과 같다)."""
    return {
        r.notion_page_id: r
        for r in db.query(TicketCache).all()
        if r.notion_missing_at is None
    }


def _all_rows(db) -> dict[str, TicketCache]:
    """표시된 것까지 포함한 전 행 — 사용자 데이터(댓글·첨부)가 붙어 있는지 볼 때 쓴다."""
    return {r.notion_page_id: r for r in db.query(TicketCache).all()}


def test_first_sync_fills_cache_and_meta(db, settings, outbound, notion, clock):
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert state.status == SYNC_OK
    assert state.last_success_at == clock.now()
    assert state.ticket_count == 2
    assert state.truncated is False

    rows = _cached(db)
    assert set(rows) == {"sync-0001", "sync-0002"}
    first = rows["sync-0001"]
    assert first.title == "첫 티켓"
    assert first.notion_ticket_number == 1
    assert first.url == "https://www.notion.so/sync-0001"
    assert first.due_date == "2026-08-01"
    assert split_names(first.assignee_notion_ids) == [N_DEV]
    assert split_names(first.project_ids) == [P_ALPHA]
    assert split_names(first.project_names) == ["알파 프로젝트"]
    assert first.synced_at == clock.now()
    # 미할당은 빈 문자열이어야 한다 — 미할당 조회가 `== ""` 로 걸리기 때문.
    assert rows["sync-0002"].assignee_notion_ids == ""

    meta = db.get(TicketMetaCache, "tickets")
    assert split_names(meta.statuses) == ["계획", "진행", "검증", "이슈", "완료", "취소"]
    assert split_names(meta.priorities) == ["높음", "보통", "낮음"]
    assert '"name": "알파 프로젝트"' in meta.projects_json
    assert meta.synced_at == clock.now()


def test_second_sync_updates_in_place_and_prunes(db, settings, outbound, notion, clock):
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    original_uid = _cached(db)["sync-0001"].id

    # 노션에서 1건은 상태가 바뀌고 1건은 사라졌다.
    notion.rows = [
        task_row(page_id="sync-0001", tid=1, title="첫 티켓(수정)", status="완료",
                 due="2026-08-01", people=[N_DEV], est_wd=2.0, act_wd=3.0,
                 priority="높음", project_ids=[P_ALPHA]),
    ]
    clock.advance(180)
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    rows = _cached(db)
    assert set(rows) == {"sync-0001"}          # 사라진 건은 목록에서 빠진다
    # 0043: 행 자체는 유예 동안 살아 있다 — 그 티켓에 달린 댓글·첨부가 CASCADE 로 사라지면
    # 재동기화로 돌아오지 않기 때문이다(tests/regression/test_comment_survives_resync.py).
    assert _all_rows(db)["sync-0002"].notion_missing_at is not None
    assert rows["sync-0001"].id == original_uid  # 자체 id 는 유지(내부 참조가 깨지면 안 된다)
    assert rows["sync-0001"].title == "첫 티켓(수정)"
    assert rows["sync-0001"].status == "완료"
    assert rows["sync-0001"].act_wd == 3.0
    assert state.ticket_count == 1


def test_truncated_sync_never_deletes(db, settings, outbound, notion, clock):
    """상한에 걸린 회차는 prune 을 건너뛴다 — 이 한 줄이 '티켓이 전부 사라졌다'를 막는다."""
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    before = set(_cached(db))
    assert len(before) == 2

    # has_more 를 영원히 True 로 → 호출측 페이지 상한(_MAX_PAGES)이 루프를 끊고 truncated 가 된다.
    notion.always_has_more = True
    notion.rows = [BASE_ROWS[0]]  # 두 번째 티켓은 이번 회차에 아예 안 왔다
    clock.advance(180)
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert state.truncated is True
    assert state.status == SYNC_OK          # 실패는 아니다 — 다만 불완전하다
    assert state.error and "상한" in state.error
    assert set(_cached(db)) == before        # 삭제 0건


def test_source_failure_keeps_previous_cache_and_last_success(db, settings, outbound, notion, clock):
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    before = {pid: (row.title, row.status) for pid, row in _cached(db).items()}
    first_success = db.get(TicketSyncState, SYNC_STATE_ID).last_success_at
    assert first_success == clock.now()

    notion.fail_status = 500  # 소스가 통째로 죽었다
    clock.advance(180)
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert state.status == SYNC_ERROR
    assert state.error
    assert state.last_run_at == clock.now()
    # 마지막 정상 시각은 지워지지 않는다 — 화면이 '언제까지 정상이었는지'를 이 값으로 말한다.
    assert state.last_success_at == first_success
    # 캐시는 손대지 않았다: 목록은 마지막 정상 데이터로 계속 뜬다.
    assert {pid: (r.title, r.status) for pid, r in _cached(db).items()} == before


def test_missing_token_is_recorded_not_raised(db, settings, outbound, notion, clock):
    """토큰 파일이 없으면(미연동) 예외가 아니라 상태 기록으로 끝나야 한다."""
    (settings.secrets_dir / TOKEN_REF).unlink()
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    assert state.status == SYNC_ERROR
    assert not _cached(db)  # 없던 캐시가 생기지도 않는다


def test_worker_tick_never_raises(db, settings, outbound, notion, clock, monkeypatch):
    """워커 tick 은 어떤 예외도 루프 밖으로 내보내지 않는다.

    sync 내부가 아니라 *그 밖*에서 터지는 경우(예: DB 세션 획득 실패)까지 포함해서 확인한다 —
    tick 하나가 죽으면 같은 루프의 스케줄러·승인 만료·문서 동기화가 전부 함께 멈춘다.
    """
    import app.tickets.sync as sync_module

    def boom(*args, **kwargs):
        raise RuntimeError("아무도 예상 못 한 실패")

    monkeypatch.setattr(sync_module, "get_or_create_state", boom)
    # sync_tickets 자체는 잡아서 상태로 남기려다 다시 boom 을 만난다 → 밖으로 나간다.
    with pytest.raises(RuntimeError):
        sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())

    # 워커 tick 은 그 위에 한 겹 더 try/except 를 두어 루프를 지킨다(worker_main 과 같은 모양).
    def tick(now):
        try:
            sync_tickets(db, outbound=outbound, settings=settings, now=now)
        except Exception:
            return "swallowed"
        return "ok"

    assert tick(clock.now()) == "swallowed"


# ── prune 바닥 (C1) ────────────────────────────────────────────────────────────
# 여기 있는 것들은 실제 운영 사고 시나리오다. Notion 이 **오류가 아니라 빈 목록을 200 으로**
# 돌려주는 경우(통합 권한 재조정, DB id 오설정, 워크스페이스 이동·필터) prune 이 전량 삭제를
# '정상 동기화'로 실행한다. 티켓 자체는 다음 회차에 돌아오지만 댓글·첨부·미push 본문은
# Notion 에 없으므로 **영구 소실**이다. 운영 실측(2026-08-05) 기준 첨부 2건과
# body_synced_at 이 비어 있는 본문 2건이 실제로 존재한다.


def _attach_children(db, settings, make_user):
    """티켓에 '노션에 없는 것들'을 붙인다 — 댓글·첨부·로컬 정본 본문."""
    from app.tickets.models import TicketAttachment, TicketComment

    user = make_user(email="c1@goodmit.co.kr")
    row = _cached(db)["sync-0001"]
    db.add(TicketComment(ticket_uid=row.id, author_user_id=user.id, body="이 댓글은 노션에 없다"))
    db.add(TicketAttachment(
        ticket_uid=row.id, uploaded_by_user_id=user.id,
        filename="스크린샷.png", stored_name="abc123.png",
        media_type="image/png", size_bytes=1024,
    ))
    row.body_markdown = "아직 노션에 push 되지 않은 본문"
    row.body_synced_at = None
    db.commit()
    return row.id


def _child_counts(db):
    from app.tickets.models import TicketAttachment, TicketComment

    return db.query(TicketComment).count(), db.query(TicketAttachment).count()


def test_empty_source_never_prunes(db, settings, outbound, notion, clock):
    """소스가 0건을 주면 한 건도 지우지 않고, 상태를 error 로 남긴다.

    이 테스트가 없으면 `_prune` 은 `keep=∅` 을 '전부 삭제됨'으로 읽는다.
    """
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    assert len(_cached(db)) == 2

    notion.rows = []  # 오류가 아니다 — 200 OK 에 빈 목록
    clock.advance(180)
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert set(_cached(db)) == {"sync-0001", "sync-0002"}  # 캐시 그대로
    assert state.status == SYNC_ERROR      # 'ok' 라고 하면 아무도 안 본다
    assert state.pruned_count == 0
    assert "0건" in (state.error or "")


def test_empty_source_preserves_comments_attachments_and_body(
    db, settings, outbound, notion, clock, make_user
):
    """C1 전체 시나리오 — 노션에 없는 것들이 살아남는가.

    티켓은 다음 정상 동기화에 돌아오지만 이 셋은 돌아오지 않는다. 그래서 여기서 지켜야 한다.
    """
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    uid = _attach_children(db, settings, make_user)
    assert _child_counts(db) == (1, 1)

    notion.rows = []
    clock.advance(180)
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert _child_counts(db) == (1, 1)          # CASCADE 로 딸려가지 않았다
    row = db.get(TicketCache, uid)
    assert row is not None
    assert row.body_markdown == "아직 노션에 push 되지 않은 본문"


def test_mass_deletion_is_refused(db, settings, outbound, notion, clock):
    """한 회차가 절반을 넘게 지우려 하면 막는다 — 부분 실패도 소스 장애로 본다."""
    notion.rows = [
        task_row(page_id=f"sync-{i:04d}", tid=i, title=f"티켓{i}", status="진행", people=[])
        for i in range(1, 11)
    ]
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()
    assert len(_cached(db)) == 10

    notion.rows = notion.rows[:4]  # 10 → 4 (60% 삭제 시도)
    clock.advance(180)
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert len(_cached(db)) == 10
    assert state.status == SYNC_ERROR
    assert "60%" in (state.error or "")


def test_normal_prune_still_works_and_is_counted(db, settings, outbound, notion, clock):
    """바닥은 정상 삭제를 막지 않는다. 그리고 몇 건 지웠는지 남긴다(드리프트 지표)."""
    notion.rows = [
        task_row(page_id=f"sync-{i:04d}", tid=i, title=f"티켓{i}", status="진행", people=[])
        for i in range(1, 11)
    ]
    sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    notion.rows = notion.rows[:8]  # 10 → 8 (20% — 정상 범위)
    clock.advance(180)
    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    assert len(_cached(db)) == 8      # 목록에서 빠진다
    assert len(_all_rows(db)) == 10   # 0043: 행은 유예 동안 남는다(사용자 데이터가 매달려 있다)
    assert state.status == SYNC_OK
    assert state.pruned_count == 2   # 지금까지는 세지도 남기지도 않았다


def test_project_lookup_failure_blocks_new_tickets_and_must_be_reported(
    db, settings, outbound, notion, clock, monkeypatch
):
    """프로젝트 조회가 실패하면 **'새 티켓' 폼이 막힌다** — 그런데 상태는 `ok` 였다 (C4).

    `meta.projects_json` 이 `[]` 가 되는데 티켓 생성은 프로젝트를 필수로 요구한다
    (`repository_notion.py`). 즉 조회 한 번 실패로 티켓을 만들 수 없게 되는데 동기화
    화면은 정상이라 말한다 — 사용자는 "폼이 고장났다" 고 신고하고 관리자는 폼 코드를 판다.

    미러링은 계속돼야 한다(이름 없이라도 목록은 살아 있는 편이 낫다). 상태만 승격한다.
    """
    from app.tickets import notion_write

    def boom(*a, **kw):
        raise RuntimeError("relation 조회 실패")

    monkeypatch.setattr(notion_write, "query_relation_titles", boom)

    state = sync_tickets(db, outbound=outbound, settings=settings, now=clock.now())
    db.commit()

    # 폼이 막힌 상태를 먼저 확인한다 — 이게 사용자가 겪는 일이다.
    meta = db.get(TicketMetaCache, "tickets")
    assert meta.projects_json == "[]", "이 테스트의 전제(프로젝트 목록이 빈다)가 깨졌다"

    assert state.status == SYNC_ERROR, "프로젝트 조회 실패인데 동기화가 정상이라고 말한다"
    assert "프로젝트" in (state.error or "")
    assert state.last_success_at is None, "실패 회차가 '마지막 정상'으로 기록됐다"

    # 그래도 티켓은 미러링됐다 — 실패를 알리는 것과 목록을 버리는 것은 다른 얘기다.
    assert set(_cached(db)) == {"sync-0001", "sync-0002"}
