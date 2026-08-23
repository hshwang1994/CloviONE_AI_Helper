"""검색 인덱서 — 무엇을 담고, **언제 안 건드리고**, 소스가 죽으면 어떻게 되는가.

인덱서에서 조용히 깨지기 쉬운 세 가지를 못박는다:
  1. 소스 하나(Notion)가 죽었을 때 **그 유형의 기존 인덱스를 지우지 않는다.** 빈 목록을
     prune 에 흘리면 소스 장애가 곧바로 '검색 결과 소멸'로 번진다(티켓 sync 의 truncated
     함정과 같은 모양이다 — PLAN C4).
  2. 내용이 안 바뀐 행은 UPDATE 하지 않는다. external content FTS5 는 UPDATE 트리거에서
     인덱스를 지웠다 다시 넣으므로, 매 틱마다 전 행을 건드리면 인덱스를 통째로 다시 쓴다.
  3. 문서 작성자는 NAMES_SEP(\\x1f) 로 이어져 있다. 콤마로 자르면 소유자 해석이 조용히
     0명이 되고, 부서 관리자에게 문서가 통째로 안 보인다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.board.models import Post
from app.core.models_base import join_names
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.search.indexer import reindex_all
from app.search.models import (
    KIND_BOARD,
    KIND_DOCUMENT,
    KIND_TICKET,
    KIND_USER,
    SearchDocument,
    split_owner_ids,
)
from app.team_docs.models import DocumentCache
from app.tickets.models import SYNC_STATE_ID, TicketCache, TicketSyncState

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 9, 0, 0)
LATER = NOW + timedelta(minutes=5)
NOTION_ID = "notion-idx-1"


@pytest.fixture()
def seeded(db, make_user):
    author = make_user(email="idx-author@goodmit.co.kr", display_name="인덱스작성자")
    db.commit()
    db.add(UserNotionMapping(
        user_id=author.id, notion_user_id=NOTION_ID,
        status=STATUS_VERIFIED, source=SOURCE_MANUAL, last_verified_at=NOW,
    ))

    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status, state.last_run_at, state.last_success_at, state.ticket_count = "ok", NOW, NOW, 1
    db.add(state)
    db.add(TicketCache(
        id="idx-tc-1", notion_page_id="idx-page-1", notion_ticket_number=901,
        title="인덱싱 대상 티켓", status="진행", due_date="2026-08-10",
        url="https://www.notion.so/idx-page-1",
        project_names=join_names(["클로비 프로젝트"]),
        assignee_notion_ids=join_names([NOTION_ID]),
        body_markdown="본문에 배포 스크립트 이야기",
        synced_at=NOW, created_at=NOW, updated_at=NOW,
    ))
    db.add(DocumentCache(
        notion_page_id="idx-doc-1", title="인덱싱 대상 문서",
        author_names=join_names(["인덱스작성자"]), owner="인덱스작성자",
        memo="문서 메모 내용", synced_at=NOW, last_edited="2026-08-01",
    ))
    db.add(Post(
        id="idx-post-1", author_user_id=author.id, category="notice",
        title="인덱싱 대상 게시글", body="게시글 본문", created_at=NOW, updated_at=NOW,
    ))
    db.commit()
    return {"author_id": author.id}


def _run(db, app, now=NOW):
    result = reindex_all(
        db, tickets=app.state.repositories.tickets,
        documents=app.state.repositories.documents, now=now,
    )
    db.commit()
    return result


def _by_kind(db, kind) -> list[SearchDocument]:
    return list(
        db.execute(select(SearchDocument).where(SearchDocument.kind == kind))
        .scalars().all()
    )


# ── 무엇을 담는가 ────────────────────────────────────────────────────────────


def test_indexes_all_four_kinds(db, app, seeded):
    result = _run(db, app)
    assert result.status == "ok", result.error
    kinds = dict(result.per_kind)
    assert kinds[KIND_TICKET] == 1
    assert kinds[KIND_DOCUMENT] == 1
    assert kinds[KIND_BOARD] == 1
    assert kinds[KIND_USER] >= 1


def test_a_normal_sized_corpus_is_not_marked_truncated(db, app, seeded):
    """상한(MAX_ROWS_PER_KIND)에 한참 못 미치면 `truncated` 는 False 로 남아야 한다 —
    잘림 검출 자체가 오탐(off-by-one 등)으로 항상 True 를 뱉지 않는지 확인한다."""
    result = _run(db, app)
    assert result.truncated is False


def test_a_kind_over_the_per_kind_cap_reports_truncated(db, app, seeded, monkeypatch):
    """🔴 회귀: 한 유형이라도 `MAX_ROWS_PER_KIND` 에서 잘리면 `IndexResult.truncated` 가
    True 여야 한다. 예전에는 이 값이 어디서도 True 로 설정되지 않아서, 코퍼스가 상한을
    넘는 날 수천 건이 검색에서 조용히 빠져도 API 응답·감사 로그·운영 대시보드
    (`app/search/reindex_router.py`, `app/worker_main.py::mirror_sync_status`) 모두
    `truncated:false` 라고 답했다."""
    from app.search import indexer

    monkeypatch.setattr(indexer, "MAX_ROWS_PER_KIND", 0)
    result = _run(db, app)
    assert result.truncated is True, "잘렸는데도 truncated 가 False 로 나왔다"


def test_ticket_row_carries_route_url_and_resolved_owner(db, app, seeded):
    _run(db, app)
    row = _by_kind(db, KIND_TICKET)[0]
    assert row.ref_id == "idx-page-1"
    assert row.route == "/tickets/idx-page-1"
    assert row.url == "https://www.notion.so/idx-page-1"
    assert "GIT-901" in row.body and "배포 스크립트" in row.body
    # **앱 user_id 로 해석해서** 담는다 — 원본 Notion id 를 넣으면 범위 판정이 못 한다.
    assert split_owner_ids(row.owner_user_ids) == (seeded["author_id"],)
    assert NOTION_ID not in row.owner_user_ids


def test_document_owner_is_resolved_through_the_names_separator(db, app, seeded):
    """`author_names` 는 콤마가 아니라 \\x1f 로 이어져 있다(회귀)."""
    _run(db, app)
    row = _by_kind(db, KIND_DOCUMENT)[0]
    assert split_owner_ids(row.owner_user_ids) == (seeded["author_id"],)
    assert "\x1f" not in row.body, "구분자가 본문에 그대로 새어 나갔다"


def test_user_row_never_contains_the_email(db, app, seeded):
    _run(db, app)
    rows = _by_kind(db, KIND_USER)
    assert rows, "사용자가 인덱싱되지 않았다"
    assert all("@" not in (row.body or "") for row in rows)


def test_board_row_points_at_the_post_route(db, app, seeded):
    _run(db, app)
    row = _by_kind(db, KIND_BOARD)[0]
    assert row.route == "/board/idx-post-1"


def test_user_row_routes_to_a_parameter_the_screen_actually_reads(db, app, seeded):
    """사용자 화면은 `?q=` 만 이해한다. `?user=<id>` 를 보내면 필터 없는 전체 목록이 뜬다 —
    눌렀는데 아무 일도 안 한 것처럼 보이는 '되는 척' 이다(회귀)."""
    from urllib.parse import parse_qs, urlparse

    _run(db, app)
    row = next(r for r in _by_kind(db, KIND_USER) if r.title == "인덱스작성자")
    parsed = urlparse(row.route)
    assert parsed.path == "/users"
    assert parse_qs(parsed.query).get("q") == ["인덱스작성자"]


# ── 언제 안 건드리는가 ───────────────────────────────────────────────────────


def test_a_second_run_with_no_changes_does_not_touch_rows(db, app, seeded):
    """FTS 인덱스를 매 틱 통째로 다시 쓰지 않는다는 증거."""
    _run(db, app)
    before = {row.id: row.indexed_at for row in db.execute(select(SearchDocument)).scalars()}
    db.expire_all()

    _run(db, app, now=LATER)
    after = {row.id: row.indexed_at for row in db.execute(select(SearchDocument)).scalars()}
    assert after == before, "내용이 그대로인데 indexed_at 이 갱신됐다"


def test_a_changed_title_is_reindexed(db, app, seeded):
    _run(db, app)
    post = db.get(Post, "idx-post-1")
    post.title = "제목을 바꾼 게시글"
    db.commit()

    _run(db, app, now=LATER)
    row = _by_kind(db, KIND_BOARD)[0]
    assert row.title == "제목을 바꾼 게시글"
    assert row.indexed_at == LATER


def test_a_deleted_source_row_is_pruned(db, app, seeded):
    _run(db, app)
    assert _by_kind(db, KIND_BOARD)
    post = db.get(Post, "idx-post-1")
    post.deleted_at = NOW
    db.commit()

    _run(db, app, now=LATER)
    assert _by_kind(db, KIND_BOARD) == []


# ── 소스가 죽었을 때 ─────────────────────────────────────────────────────────


@pytest.mark.notion_source
def test_a_dead_notion_ticket_source_keeps_the_existing_ticket_index(db, app, seeded):
    """PLAN C4 와 같은 함정: 빈 목록을 prune 에 흘리면 장애가 데이터 소멸이 된다.

    **미러 경로 전용이다** (S14). 「미러가 한 번도 성공한 적 없다」는 상태를 만들어
    저장소를 실시간(미설정 → 예외)으로 보내는 방식인데, 자체 DB 경로에는 그 상태가
    아예 없다 — 표가 정본이라 「아직 안 찼다」가 성립하지 않는다. 같은 성질을 자체 DB
    에서 보는 시험은 바로 아래에 있다.
    """
    _run(db, app)
    assert len(_by_kind(db, KIND_TICKET)) == 1

    # 미러를 '한 번도 성공한 적 없음'으로 되돌리면 저장소가 실시간(미설정 → 예외)으로 간다.
    state = db.get(TicketSyncState, SYNC_STATE_ID)
    state.last_success_at = None
    db.commit()

    result = _run(db, app, now=LATER)
    assert result.status == "error" and "ticket" in (result.error or "")
    assert len(_by_kind(db, KIND_TICKET)) == 1, "소스 장애로 티켓 검색이 통째로 사라졌다"
    # 다른 유형은 계속 인덱싱된다(장애 격리).
    assert _by_kind(db, KIND_BOARD)


def test_a_dead_ticket_source_keeps_the_existing_ticket_index(db, app, seeded):
    """같은 성질을 **자체 DB 경로**에서 본다 (S14).

    자체 DB 라고 소스가 안 죽는 것이 아니다 — 질의가 실패하면 목록은 여전히 「없다」로
    보이고, 그 빈 목록을 prune 에 흘리면 장애 한 번에 티켓 검색이 통째로 사라진다.
    그것이 PLAN C4 가 이름 붙인 함정이고, 소스가 바뀐다고 없어지지 않는다.

    실패를 저장소 **경계**에서 만든다. 표를 지우면 「없다」가 사실이 되어 prune 이 옳게
    도는 것이라, 그때의 초록은 이 시험이 보려는 것과 정반대다.
    """
    _run(db, app)
    assert len(_by_kind(db, KIND_TICKET)) == 1

    class _DeadTickets:
        def __getattr__(self, name):
            def _boom(*a, **kw):
                raise RuntimeError("ticket source is down")
            return _boom

    result = reindex_all(
        db, tickets=_DeadTickets(),
        documents=app.state.repositories.documents, now=LATER,
    )
    db.commit()
    assert result.status == "error" and "ticket" in (result.error or "")
    assert len(_by_kind(db, KIND_TICKET)) == 1, "소스 장애로 티켓 검색이 통째로 사라졌다"
    assert _by_kind(db, KIND_BOARD)


def test_reindex_never_raises(db, app):
    """워커 틱이 죽으면 스케줄러·하트비트까지 함께 멈춘다 — 예외는 밖으로 나가지 않는다."""

    class Exploding:
        def list_all(self, _db):
            raise RuntimeError("소스가 폭발했다")

        def list_documents(self, _db, **_kwargs):
            raise RuntimeError("소스가 폭발했다")

    result = reindex_all(db, tickets=Exploding(), documents=Exploding(), now=NOW)
    assert result.status == "error"
    assert "RuntimeError" in (result.error or "")
