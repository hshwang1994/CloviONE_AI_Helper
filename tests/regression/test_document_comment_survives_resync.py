"""문서가 **한 회차 사라졌다 돌아와도** 댓글이 살아 있어야 한다 (사용자 지적 #9).

## 왜 이 파일이 티켓 것을 본떴는가

`tests/regression/test_comment_survives_resync.py` 가 티켓에서 정확히 이 사건을 기록했다.
티켓이 Notion 응답에서 한 회차 빠지면(페이지네이션 흔들림, 필터, 일시 권한 문제 - 전부
HTTP 200 이다) prune 이 캐시 행을 지우고, `ticket_comments` 의 `ON DELETE CASCADE` 가 댓글과
첨부를 **함께** 지웠다. 그 회차의 sync 상태는 `ok` 였다. 그래서 0043 이 소프트 프룬을 도입해
지우는 대신 표시하도록 고쳤다.

문서 댓글을 새로 만들면서 같은 함정이 그대로 열려 있다:
`app/team_docs/sync.py::_prune` 은 **지금도 진짜로 지운다**(문서 쪽에는 `notion_missing_at`
같은 표시가 없다). 그래서 `document_comments` 는 CASCADE 를 쓰지 않고 `notion_page_id` 를
조회 키로, `document_id` 를 `ON DELETE SET NULL` 다리로 두었다(0047, `models.py` 참조).

**이 파일은 그 선택이 실제로 값을 하는지 확인한다.** 되돌리면(예: FK 를 CASCADE 로 바꾸면)
`test_the_comment_survives_a_missing_round` 가 빨개진다.

## 🔴 헛것을 피하려고 한 것

  * **네트워크 실패가 대신 막지 않게** 한다. `notion_docs` 를 monkeypatch 해서 소스가
    **정상 200 으로 목록을 돌려주는** 상태를 만든다. 예외가 나면 `sync_documents` 가 통째로
    롤백해 prune 자체가 일어나지 않고, 그러면 "댓글이 살아남았다" 는 아무 뜻이 없다.
    그래서 회차마다 **sync 상태가 ok 이고 캐시 행이 실제로 사라졌는지** 먼저 확인한다.
  * **바닥에 걸려 prune 이 거부되지 않게** 채움 문서를 넉넉히 둔다(`core/sync_prune.py` 의
    빈 결과 바닥과 낙폭 50% 바닥). 두 건만 두면 한 건이 빠져도 낙폭이 넘어 prune 이 거부되고,
    재현하려는 상황 자체가 일어나지 않는다.
  * 마지막에는 **화면이 보는 층**(HTTP 엔드포인트)까지 확인한다. 표에 행이 남아 있는 것과
    사용자가 그 댓글을 다시 보는 것은 다른 사건이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.models_base import utcnow
from app.team_docs import comments as doc_comments
from app.team_docs import notion_docs, sync
from app.team_docs.models import SYNC_OK, DocumentCache, DocumentComment

pytestmark = pytest.mark.regression

KEEP = "doc-keep"     # 늘 소스 응답에 있는 문서
GHOST = "doc-ghost"   # 한 회차 빠졌다가 돌아오는 문서

BODY = "이 댓글이 살아남아야 한다"

RELMAPS = {
    notion_docs.PROP_TYPE: {"t1": "계약서"},
    notion_docs.PROP_CATEGORY: {"c1": "영업"},
    notion_docs.PROP_PROJECT: {"pr1": "프로젝트X"},
}


def _doc(pid: str, title: str) -> dict:
    return {
        "notion_page_id": pid, "url": f"https://notion/{pid}", "title": title,
        "last_edited": "2026-07-01T00:00:00.000Z", "created_time": "2026-06-01T00:00:00.000Z",
        "type_ids": ["t1"], "category_ids": ["c1"], "project_ids": ["pr1"],
        "status": "활성", "priority": "높음", "author_names": [], "author_notion_ids": [],
        "owner": "", "doc_date": None, "orig_date": None, "original_url": None,
        "source_url": None, "memo": "", "notion_favorite": False,
        "archived": False, "has_files": False,
    }


def _rows(*, include_ghost: bool) -> list[dict]:
    """낙폭 바닥(`MAX_DROP_RATIO`)에 걸리지 않도록 채움 문서를 넉넉히 둔다."""
    rows = [_doc(f"doc-f{i:03d}", f"채움{i}") for i in range(20)]
    rows.append(_doc(KEEP, "남는 문서"))
    if include_ghost:
        rows.append(_doc(GHOST, "사라졌다 오는 문서"))
    return rows


def _source(monkeypatch, docs: list[dict]) -> None:
    """소스가 **정상 200 으로** 이 목록을 돌려주는 상태."""
    monkeypatch.setattr(notion_docs, "fetch_documents_schema", lambda o, s: {})
    monkeypatch.setattr(notion_docs, "resolve_relation_maps",
                        lambda o, s, sch, failures=None: RELMAPS)
    monkeypatch.setattr(notion_docs, "query_all_documents", lambda o, s: (docs, False))


def _sync(db, settings):
    state = sync.sync_documents(db, outbound=None, settings=settings, now=utcnow())
    db.commit()
    db.expire_all()
    return state


def _cache_row(db, page_id: str) -> DocumentCache | None:
    return db.execute(
        select(DocumentCache).where(DocumentCache.notion_page_id == page_id)
    ).scalar_one_or_none()


def _comments(db, page_id: str) -> list[DocumentComment]:
    return list(db.execute(
        select(DocumentComment).where(DocumentComment.notion_page_id == page_id)
    ).scalars().all())


@pytest.fixture()
def synced(db, settings, monkeypatch):
    """한 번 동기화해 캐시를 채운다."""
    _source(monkeypatch, _rows(include_ghost=True))
    state = _sync(db, settings)
    assert state.status == SYNC_OK, f"준비 단계 동기화가 실패했다: {state.error!r}"
    assert _cache_row(db, GHOST) is not None
    return state


@pytest.fixture()
def author(db, make_user):
    user = make_user("docsync@goodmit.co.kr", role="user", display_name="댓글작성자")
    db.commit()
    return user


def _attach_comment(db, page_id: str, user) -> str:
    row = _cache_row(db, page_id)
    assert row is not None, f"{page_id} 가 캐시에 없다 - 동기화가 안 됐다"
    created = doc_comments.create_comment(
        db, page_id=page_id, document_id=row.id, author=user, body=BODY, now=utcnow()
    )
    db.commit()
    return created.id


def test_a_plain_resync_keeps_comments(db, settings, monkeypatch, synced, author):
    """평범한 재동기화로 댓글이 사라지면 그건 훨씬 큰 문제다 - 먼저 이것부터 확인한다."""
    _attach_comment(db, KEEP, author)

    _source(monkeypatch, _rows(include_ghost=True))
    state = _sync(db, settings)
    assert state.status == SYNC_OK, state.error

    left = _comments(db, KEEP)
    assert len(left) == 1, "평범한 재동기화로 댓글이 사라졌다"
    assert left[0].body == BODY


def test_the_comment_survives_a_missing_round(db, settings, monkeypatch, synced, author):
    """🔴 **이 파일의 본론.**

    문서가 한 회차 빠지면 prune 이 캐시 행을 지운다. 그때 댓글이 CASCADE 로 딸려 나가면
    돌아와도 되살아날 것이 남지 않는다 - 티켓에서 실제로 일어난 일이다.
    """
    comment_id = _attach_comment(db, GHOST, author)

    # 한 회차 사라진다. 오류가 아니라 **정상 200 에 목록만 짧다.**
    _source(monkeypatch, _rows(include_ghost=False))
    state = _sync(db, settings)

    # 전제 확인 - prune 이 실제로 일어났는가. 여기가 무너지면 아래 단정은 아무 뜻이 없다.
    assert state.status == SYNC_OK, (
        f"prune 이 바닥에 걸려 거부됐다 - 재현하려는 상황이 일어나지 않았다: {state.error!r}"
    )
    assert state.pruned_count == 1, f"지운 건수가 1 이 아니다: {state.pruned_count}"
    assert _cache_row(db, GHOST) is None, "캐시 행이 안 지워졌다 - 재현 상황이 아니다"

    # 본론.
    surviving = _comments(db, GHOST)
    assert len(surviving) == 1, (
        "문서가 한 회차 사라지자 댓글이 함께 지워졌다. "
        "티켓에서 CASCADE 로 겪은 그 사건과 같다(0043, 0047 참조)."
    )
    assert surviving[0].id == comment_id and surviving[0].body == BODY
    # FK 는 SET NULL 이다 - 그래서 캐시 행 DELETE 가 실패하지 않았고(위 status ok),
    # 다리만 끊겼다. 조회 키는 page id 라 댓글 자체는 온전하다.
    assert surviving[0].document_id is None, (
        f"캐시 행이 사라졌는데 document_id 가 남아 있다: {surviving[0].document_id!r}"
    )


def test_the_comment_comes_back_with_the_document(db, settings, monkeypatch, synced, author):
    """돌아온 뒤가 진짜 확인이다. `_upsert` 는 **새 UUID 로** 캐시 행을 만든다."""
    _attach_comment(db, GHOST, author)

    _source(monkeypatch, _rows(include_ghost=False))
    _sync(db, settings)
    assert _cache_row(db, GHOST) is None

    _source(monkeypatch, _rows(include_ghost=True))
    state = _sync(db, settings)
    assert state.status == SYNC_OK, state.error

    back = _cache_row(db, GHOST)
    assert back is not None, "문서가 안 돌아왔다"
    rows = _comments(db, GHOST)
    assert len(rows) == 1, "문서는 돌아왔는데 댓글이 없다"
    assert rows[0].body == BODY
    # 새 캐시 행의 id 는 예전과 다르다. 그런데도 댓글이 붙어 있는 이유가 page id 키다 -
    # 티켓에서 '결정적 UUID' 로 고치려다 실패한 그 지점이 여기서는 애초에 생기지 않는다.
    assert rows[0].document_id != back.id or rows[0].document_id is None


def test_the_user_sees_the_comment_again_through_the_api(
    client, login_as, db, settings, monkeypatch, synced, author
):
    """표에 행이 남은 것과 **사용자가 다시 보는 것**은 다른 사건이다.

    사라진 동안에는 404 가 맞다 - 문서 자체가 포탈에서 안 보이므로 댓글 조회도 없는 문서와
    같은 답을 해야 한다(범위 규칙과 같은 자리). 돌아오면 그대로 다시 보여야 한다.
    """
    _attach_comment(db, GHOST, author)
    hdr = {"X-CSRF-Token": login_as("user", email="docsync@goodmit.co.kr")}

    before = client.get(f"/api/team-docs/{GHOST}/comments", headers=hdr)
    assert before.status_code == 200, before.text
    assert [c["body"] for c in before.json()["comments"]] == [BODY]

    _source(monkeypatch, _rows(include_ghost=False))
    _sync(db, settings)
    gone = client.get(f"/api/team-docs/{GHOST}/comments", headers=hdr)
    assert gone.status_code == 404, (
        f"소스에서 사라진 문서의 댓글이 그대로 열린다: {gone.status_code}"
    )

    _source(monkeypatch, _rows(include_ghost=True))
    _sync(db, settings)
    after = client.get(f"/api/team-docs/{GHOST}/comments", headers=hdr)
    assert after.status_code == 200, after.text
    assert [c["body"] for c in after.json()["comments"]] == [BODY], (
        "문서가 돌아왔는데 사용자 화면에는 댓글이 없다"
    )
