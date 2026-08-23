"""자체 DB 티켓 저장소 (`app/tickets/repository_native.py`) — S14.

## 이 파일이 고정하는 성질

  1. **읽기 답이 안 바뀐다.** 네 목록(내 티켓·미할당·전체·기간)이 Notion 구현체의
     미러 모드와 **같은 행을 같은 순서로** 돌려준다. 컷오버는 소스를 바꾸는 일이지
     목록을 바꾸는 일이 아니다 — 같은 데이터에서 다른 답이 나오면 그건 이관이 아니라
     사고다.
  2. **필터와 페이지가 자르기 전에 걸린다.** `total` 은 필터를 다 건 뒤·자르기 전
     건수다. 자른 뒤에 세면 화면이 "2건 중 3-4" 라는 말이 안 되는 문장을 쓴다.
  3. **새 티켓이 이름을 받는다.** `<CODE>-<SEQ>` 는 트리거가 파생시키고 앱은 그 컬럼을
     쓰지 않는다(D-195). 코드가 없는 프로젝트에서는 번호 없이 만들어진다.
  4. **딥링크가 둘 다 산다.** 이관해 온 티켓은 옛 page id 로, 자체 DB 에서 만든 티켓은
     자체 uuid 로 열린다. 모르는 값은 **거절한다** — 빈 티켓을 돌려주면 「없는 티켓」과
     「빈 티켓」이 같은 답이 되고, 사용자는 자기가 지운 줄 안다.
  5. **밖으로 한 번도 안 나간다.** import 로도(정적) 실행으로도(왕복 기록) 확인한다.
     0건이 「안 봤다」와 구별되도록 **같은 픽스처에서 Notion 구현체는 왕복을 남기는
     것**을 함께 본다.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime

import pytest

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import (
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    SOURCE_NATIVE,
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketSyncState,
)
from app.tickets.repository import PageSpec, TicketDraft, TicketFilters
from app.tickets.repository_native import NativeTicketRepository
from app.tickets.repository_notion import NotionTicketRepository

pytestmark = pytest.mark.integration

# 기본 FakeClock 과 같은 시각. 2026-07-14 는 화요일이라 그 주 월요일은 2026-07-13 이다.
NOW = datetime(2026, 7, 14, 0, 0, 0)
FAR = "2026-09-01"

NID_ME = "notion-me"
NID_MATE = "notion-mate"
PROJECT_PAGE = "proj-page-1"


def _row(
    db,
    *,
    uid: str,
    page_id: str | None = None,
    tid: int | None = None,
    title: str = "티켓",
    status: str | None = "진행",
    due: str | None = FAR,
    priority: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    projects: tuple[str, ...] = (),
    project_uid: str | None = None,
    assignees: tuple[str, ...] = (),
    missing_at: datetime | None = None,
    body: str | None = None,
) -> TicketCache:
    """미러 표에 티켓 한 건. 정렬 타이브레이커를 보려면 id 를 손으로 정해야 한다."""
    row = TicketCache(
        id=uid,
        notion_page_id=page_id if page_id is not None else f"page-{uid}",
        org_id=DEFAULT_ORG_ID,
        notion_ticket_number=tid,
        url=f"https://example.invalid/{uid}",
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
        body_markdown=body,
        synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    return row


def _mirror_ready(db, count: int) -> None:
    """Notion 구현체가 **미러로 답하게** 만든다.

    안 채우면 저쪽이 실시간 폴백으로 가고, 그러면 이 파일의 비교 시험이 「같은 답」이
    아니라 「Notion 페이크의 답」을 보게 된다 — 증명하려던 것과 다른 것이 검사된다.
    """
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


@pytest.fixture()
def native() -> NativeTicketRepository:
    return NativeTicketRepository(None, None)


@pytest.fixture()
def notion(app, settings) -> NotionTicketRepository:
    """비교 대상 — **미러 모드**의 Notion 구현체."""
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    return NotionTicketRepository(settings, app.state.outbound_client, use_cache=True)


@pytest.fixture()
def project(make_project):
    """코드가 있고 외부 짝도 있는 프로젝트. 코드는 제품 생성기가 짓는다(D-282)."""
    return make_project(name="네이티브 프로젝트", external_id=PROJECT_PAGE)


@pytest.fixture()
def catalog(db, project):
    """조건이 한 축씩만 다른 티켓 묶음 + 목록 갈래를 나누는 행들."""
    _row(db, uid="n-mine-1", tid=1, assignees=(NID_ME,), projects=(PROJECT_PAGE,),
         project_uid=project.id, due="2026-07-16")
    _row(db, uid="n-mine-2", tid=2, assignees=(NID_ME, NID_MATE), status="검증")
    _row(db, uid="n-mate", tid=3, assignees=(NID_MATE,), priority="높음")
    _row(db, uid="n-free-1", tid=4, assignees=())
    _row(db, uid="n-free-2", tid=5, assignees=(), difficulty="5", category="인프라")
    _row(db, uid="n-nodue", tid=None, due=None, assignees=())
    # 「소스에서 사라졌다」로 표시된 행 — 어느 목록에도 나오면 안 된다.
    _row(db, uid="n-missing", tid=6, assignees=(NID_ME,), missing_at=NOW)
    db.commit()
    _mirror_ready(db, 7)
    return project


def _ids(result) -> list[str]:
    return [t.page_id for t in result.tickets]


# ── 1. 읽기 답이 안 바뀐다 ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda repo, db: repo.list_by_assignee(db, assignee_id=NID_ME), id="mine"),
        pytest.param(lambda repo, db: repo.list_unassigned(db), id="unassigned"),
        pytest.param(lambda repo, db: repo.list_all(db), id="all"),
        pytest.param(
            lambda repo, db: repo.list_for_period(db, start="2026-07-13", end="2026-09-30"),
            id="period",
        ),
    ],
)
def test_the_four_lists_answer_exactly_what_the_mirror_answered(catalog, db, native, notion, call):
    """같은 데이터에서 같은 행이 같은 순서로 나온다."""
    mine = call(native, db)
    theirs = call(notion, db)
    assert _ids(mine) == _ids(theirs)
    assert mine.total == theirs.total
    assert mine.tickets == theirs.tickets


def test_the_missing_marker_still_hides_the_ticket(catalog, db, native):
    """「소스에서 사라졌다」로 표시된 행은 컷오버 뒤에도 목록에 안 돌아온다."""
    assert "page-n-missing" not in _ids(native.list_all(db))
    assert "page-n-missing" not in _ids(native.list_by_assignee(db, assignee_id=NID_ME))


def test_the_answer_says_it_is_not_a_copy(catalog, db, native):
    """정본으로 답했으므로 신선도를 싣지 않는다 — 화면의 「N분 전 동기화」 배지가 사라진다."""
    result = native.list_all(db)
    assert result.from_cache is False
    assert result.sync is None
    assert native.sync_state(db) is None


# ── 2. 필터와 페이지는 자르기 **전에** 걸린다 ─────────────────────────────────

def test_the_filter_runs_before_the_page_is_cut(catalog, db, native):
    """조건에 맞는 것이 하나뿐이면 total 도 1이다 — 필터가 페이지 뒤에 걸리면 6이 된다."""
    result = native.list_all(db, filters=TicketFilters(priority="높음"))
    assert _ids(result) == ["page-n-mate"]
    assert result.total == 1


def test_total_counts_before_truncation(catalog, db, native):
    """`total` 은 필터 뒤·자르기 전 건수다. 자른 뒤에 세면 2페이지에서 화면이 거짓말을 한다."""
    everything = native.list_all(db)
    assert everything.total == 6  # 사라짐 표시된 한 건은 빠진다

    first = native.list_all(db, page=PageSpec(offset=0, limit=2))
    second = native.list_all(db, page=PageSpec(offset=2, limit=2))
    assert len(first.tickets) == 2
    assert first.total == 6 and second.total == 6
    # 정렬이 전순서가 아니면 여기서 같은 행이 두 페이지에 나온다(Z9).
    assert set(_ids(first)).isdisjoint(_ids(second))


def test_the_scope_filter_still_closes(catalog, db, native):
    """빈 범위는 **아무것도 안 보인다**(fail-closed). 열리면 그건 성능 개선이 아니라 유출이다."""
    from app.tickets.repository import ProjectVisibility

    closed = ProjectVisibility(uids=frozenset(), page_ids=frozenset())
    result = native.list_all(db, filters=TicketFilters(project_any_of=closed))
    assert result.tickets == ()
    assert result.total == 0


# ── 3. 새 티켓이 이름을 받는다 ────────────────────────────────────────────────

def test_create_gives_the_new_ticket_its_canonical_name(db, native, project):
    """`<CODE>-<SEQ>`. 앱이 그 문자열을 쓰지 않는다 — 트리거가 파생시킨다(D-195)."""
    created = native.create(
        db,
        draft=TicketDraft(title="새 티켓", project_id=PROJECT_PAGE, description_markdown="본문"),
        now=NOW,
    )
    assert created.key == f"{project.code}-1"
    assert created.uid and created.page_id == created.uid  # 노션 페이지가 없다
    assert created.source == SOURCE_NATIVE
    assert created.status == "계획"  # 제품이 정한 기본 상태

    row = db.get(TicketCache, created.uid)
    assert row.seq == 1
    assert row.project_uid == project.id
    assert row.project_link == PROJECT_LINK_OK
    # 다음 티켓은 다음 번호를 받는다 — 채번기를 지났다는 증거다.
    again = native.create(db, draft=TicketDraft(title="두 번째", project_id=PROJECT_PAGE), now=NOW)
    assert again.key == f"{project.code}-2"


def test_create_without_a_project_code_leaves_the_ticket_unnamed(db, native, make_project):
    """코드가 없으면 **번호 없이** 만든다 — 채번 규칙 때문에 제품을 세우지 않는다.

    반례다: 위 시험이 「이름이 붙는다」만 보면 「언제나 붙는다」와 구별되지 않는다.
    """
    from app.projects.models import Project

    bare = make_project(name="코드 없는 프로젝트", external_id="proj-page-2")
    db.execute(
        Project.__table__.update().where(Project.id == bare.id).values(code=None)
    )
    db.commit()
    # 이 세션은 `expire_on_commit=False` 다(app/core/db.py). 커밋만 하면 위 Core UPDATE
    # 를 세션이 모른 채 옛 코드를 그대로 들고 있고, 그러면 채번기가 「코드가 있다」로
    # 보고 번호를 발급해 트리거가 그때서야 거절한다 — 시험이 보려던 갈래가 아니다.
    db.expire_all()

    created = native.create(db, draft=TicketDraft(title="이름 없는 티켓", project_id="proj-page-2"))
    assert created.key is None
    assert db.get(TicketCache, created.uid).seq is None


def test_create_refuses_an_empty_title(db, native, project):
    from app.core.errors import ValidationAppError

    with pytest.raises(ValidationAppError):
        native.create(db, draft=TicketDraft(title="   ", project_id=PROJECT_PAGE))


def test_update_applies_the_domain_keys(db, native, project):
    created = native.create(db, draft=TicketDraft(title="고칠 티켓", project_id=PROJECT_PAGE))
    updated = native.update(
        db,
        page_id=created.page_id,
        changes={
            "title": "고친 제목",
            "status": "진행",
            "priority": "높음",
            "difficulty": "3",
            "est_wd": 2.5,
            "act_wd": 1.0,
            "due_date": "2026-08-01",
            "start": "2026-07-20",
            "category": "인프라",
            "assignee_notion_ids": [NID_ME],
        },
        now=NOW,
    )
    assert updated.title == "고친 제목"
    assert updated.status == "진행"
    assert updated.priority == "높음"
    assert updated.difficulty == "3"
    assert updated.est_wd == 2.5 and updated.act_wd == 1.0
    assert updated.due == "2026-08-01" and updated.start == "2026-07-20"
    assert updated.category == "인프라"
    assert updated.assignee_ids == (NID_ME,)
    # 이름은 그대로다 — 편집이 티켓의 이름을 바꾸면 어제 공유한 링크가 죽는다.
    assert updated.key == created.key


def test_update_refuses_an_unknown_status(db, native, project):
    """모르는 상태를 막는 것이 어휘를 제품이 소유한다는 말의 실체다."""
    from app.core.errors import ValidationAppError

    created = native.create(db, draft=TicketDraft(title="상태 티켓", project_id=PROJECT_PAGE))
    with pytest.raises(ValidationAppError):
        native.update(db, page_id=created.page_id, changes={"status": "진행중"})


# ── 4. 딥링크 두 갈래 ────────────────────────────────────────────────────────

def test_get_answers_by_page_id_and_by_uuid(catalog, db, native):
    """옛 링크(page id)와 새 링크(uuid)가 같은 티켓을 연다."""
    by_page = native.get(db, page_id="page-n-mine-1")
    by_uuid = native.get(db, page_id="n-mine-1")
    assert by_page == by_uuid
    assert by_page.uid == "n-mine-1"
    assert native.get_live(db, page_id="n-mine-1") == by_page


def test_get_refuses_an_unknown_id(catalog, db, native):
    """반례 — 모르는 값에는 **빈 티켓이 아니라 오류**가 나와야 한다."""
    from app.core.errors import TicketNotFoundError

    with pytest.raises(TicketNotFoundError):
        native.get(db, page_id="page-does-not-exist")
    with pytest.raises(TicketNotFoundError):
        native.get_live(db, page_id="page-does-not-exist")


def test_local_uid_and_ensure_local(catalog, db, native):
    """댓글이 `tickets.id` 에 FK 로 걸려 있어서 이 둘이 필요하다.

    **없는 티켓을 만들어 내지 않는다** (S14). 미러 구현체는 행이 없으면 빈 행을 만들고
    넘어갔고, 그때는 다음 동기화가 그 행을 채웠다. 자체 DB 에는 그 「다음 동기화」가
    없으므로 빈 행은 **소속 없이 영구히** 남고, 소속이 없으면 범위 문이 닫는다 —
    방금 댓글을 단 사람이 그 순간부터 그 티켓을 못 연다. 오류는 안 난다.

    그래서 없는 티켓은 없다고 답한다. 반례로 「있는 티켓은 두 축 모두로 열린다」를 함께
    본다 — 그것이 없으면 이 단언은 「전부 거절한다」로도 통과한다.
    """
    from app.core.errors import TicketNotFoundError

    assert native.local_uid(db, page_id="page-n-mine-1") == "n-mine-1"
    assert native.local_uid(db, page_id="아무것도아님") is None

    # 있는 티켓 — 두 축 모두로 같은 행을 준다.
    assert native.ensure_local(db, page_id="page-n-mine-1", now=NOW) == "n-mine-1"
    assert native.ensure_local(db, page_id="n-mine-1", now=NOW) == "n-mine-1"

    # 없는 티켓 — 만들지 않고 거절한다.
    with pytest.raises(TicketNotFoundError):
        native.ensure_local(db, page_id="page-brand-new", now=NOW)
    assert native.local_uid(db, page_id="page-brand-new") is None


# ── 5. 본문 ──────────────────────────────────────────────────────────────────

def test_save_body_is_always_synced(catalog, db, native):
    """밀어 넣을 곳이 없으므로 「못 밀어 넣었다」는 상태가 없다."""
    result = native.save_body(db, page_id="page-n-mine-1", body_markdown="# 제목\n- 하나", now=NOW)
    assert result.synced is True
    assert result.sync_error is None
    assert result.uid == "n-mine-1"
    row = db.get(TicketCache, "n-mine-1")
    assert row.body_markdown == "# 제목\n- 하나"
    assert row.body_synced_at == NOW


def test_save_body_clears_a_stale_mismatch_banner(db, native, catalog):
    """컷오버 전에 적힌 「원본과 어긋났습니다」는 저장 한 번으로 사라져야 한다.

    어긋날 원본이 없어진 뒤에도 배너가 남으면 사용자는 고칠 수 없는 경고를 매번 본다.
    """
    row = db.get(TicketCache, "n-mine-2")
    row.body_sync_error = "Notion 반영 실패: ConnectError"
    db.flush()
    native.save_body(db, page_id="page-n-mine-2", body_markdown="다시 씁니다.", now=NOW)
    assert db.get(TicketCache, "n-mine-2").body_sync_error is None


def test_body_blocks_round_trip_to_the_same_markdown(db, native, catalog):
    """편집기가 다시 열었을 때 **저장한 그 글**이 나와야 한다."""
    from app.core.notion_blocks import rendered_to_markdown

    body = "# 제목\n문단입니다.\n- 하나\n- 둘\n1. 첫째\n---\n마지막 줄입니다."
    native.save_body(db, page_id="page-n-mine-1", body_markdown=body, now=NOW)
    blocks = native.body_blocks(db, page_id="page-n-mine-1")
    assert {b["kind"] for b in blocks} <= {
        "heading_1", "paragraph", "bulleted", "numbered", "divider",
    }
    assert rendered_to_markdown(blocks) == body


def test_body_blocks_of_an_empty_ticket_is_an_empty_list(db, native, catalog):
    assert native.body_blocks(db, page_id="page-n-free-1") == []


# ── 6. 보관처리 = 영구 삭제 ──────────────────────────────────────────────────

def test_archive_deletes_the_row(db, native, catalog):
    """자체 DB 에는 두 번째 휴지통이 없다 — 이 자리의 뜻은 이미 「되돌리지 않는다」다."""
    native.archive(db, page_id="page-n-free-1")
    assert db.get(TicketCache, "n-free-1") is None
    # 이미 없는 것을 지우는 것은 성공이다(지우는 것이 목적이므로).
    native.archive(db, page_id="page-n-free-1")


def test_archive_refuses_without_a_session(db, native, catalog):
    """반례 — 조용히 넘어가면 영구 삭제한 티켓이 다음 목록에서 되살아난다."""
    from app.core.errors import ValidationAppError

    with pytest.raises(ValidationAppError):
        native.archive(None, page_id="page-n-free-1")
    assert db.get(TicketCache, "n-free-1") is not None


# ── 7. 폼 옵션 ───────────────────────────────────────────────────────────────

def test_meta_statuses_come_from_the_product(db, native, catalog):
    """진행상태 어휘의 정본은 `app/work/workflow.py` 다 — 소스 스키마가 아니다."""
    from app.work import workflow

    meta = native.meta(db)
    assert list(meta.statuses) == [s.key for s in workflow.all_statuses()]
    # 우선순위·난이도는 아직 제품이 소유하지 못했다 — 지금 데이터에서 뽑는다.
    assert list(meta.priorities) == ["높음"]
    assert list(meta.difficulties) == ["5"]


def test_projects_uses_the_identifier_the_tickets_use(db, native, project, catalog):
    """티켓이 프로젝트를 부르는 이름과 **같은 축**이어야 화면 필터가 걸린다."""
    refs = native.projects(db)
    assert PROJECT_PAGE in [r.id for r in refs]
    picked = next(r for r in refs if r.id == PROJECT_PAGE)
    assert picked.name == "네이티브 프로젝트"
    # 그 id 를 그대로 필터에 넣으면 그 프로젝트의 티켓만 남는다.
    filtered = native.list_all(db, filters=TicketFilters(project_id=picked.id))
    assert _ids(filtered) == ["page-n-mine-1"]


# ── 8. 밖으로 한 번도 안 나간다 ──────────────────────────────────────────────

_FORBIDDEN_IMPORTS = ("notion_source", "notion_write", "notion_docs", "http_client", "httpx")


def test_the_module_does_not_import_any_outbound_module():
    """정적 — import 문 자체를 본다(지연 import 도 AST 에 남는다)."""
    path = pathlib.Path(__file__).resolve().parents[2] / "app" / "tickets" / "repository_native.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    offenders = [m for m in imported if any(bad in m for bad in _FORBIDDEN_IMPORTS)]
    assert offenders == [], offenders
    # 검사기 자기검증: 표본이 0이면 「위반이 없다」와 「아무것도 안 봤다」가 같아진다.
    assert len(imported) > 5


def test_the_repository_does_not_keep_the_outbound_client():
    """들고 있으면 언젠가 누군가 그걸로 한 번만 왕복한다."""
    sentinel = object()
    repo = NativeTicketRepository("settings", sentinel)
    assert sentinel not in vars(repo).values()


def test_no_request_leaves_the_process(catalog, db, native, fake_http, project):
    """실행 — 읽기·쓰기를 한 바퀴 돌리고 왕복 기록이 비어 있는지 본다."""
    native.list_all(db)
    native.list_unassigned(db)
    native.list_by_assignee(db, assignee_id=NID_ME)
    native.list_for_period(db, start="2026-07-01", end="2026-10-01")
    native.get(db, page_id="page-n-mine-1")
    native.get_live(db, page_id="page-n-mine-1")
    native.body_blocks(db, page_id="page-n-mine-1")
    native.meta(db)
    native.projects(db)
    native.sync_state(db)
    native.local_uid(db, page_id="page-n-mine-1")
    native.ensure_local(db, page_id="page-n-mine-1")
    made = native.create(db, draft=TicketDraft(title="왕복 없음", project_id=PROJECT_PAGE), now=NOW)
    native.update(db, page_id=made.page_id, changes={"status": "진행"}, now=NOW)
    native.save_body(db, page_id=made.page_id, body_markdown="본문", now=NOW)
    native.archive(db, page_id=made.page_id)

    assert fake_http.requests == []


def test_the_probe_can_actually_see_a_request(catalog, db, notion, fake_http):
    """반례 — 같은 픽스처에서 Notion 구현체는 왕복을 남긴다.

    이것이 없으면 위 시험의 「0건」이 「아무것도 안 봤다」와 구별되지 않는다.
    """
    from app.core.errors import NotionQueryError

    with pytest.raises(NotionQueryError):
        notion.get_live(db, page_id="page-n-mine-1")
    assert fake_http.requests != []
