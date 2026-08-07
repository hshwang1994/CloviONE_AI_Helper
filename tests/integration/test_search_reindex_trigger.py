"""검색 인덱스 강제 재색인 API — POST /api/search/reindex (C7).

이 시험 파일은 **한 번도 티켓 동기화가 성공한 적 없는** 갓 만든 DB 위에서 돈다(다른 통합
시험처럼 매 테스트가 새 sqlite 파일을 받는다 — tests/conftest.py `db_path`). 그래서
`app/tickets/repository_notion.py::_cache_ready` 가 아직 캐시를 못 믿어 실시간 Notion 조회로
떨어지고, 이 테스트 환경(fake_http 에 아무 경로도 등록하지 않음)에서는 그 조회가 실패한다 —
team_docs/tickets 의 "faults gracefully without notion" 시험과 같은 모양으로, 여기서도
`status == "error"` 를 기대한다. 단 **게시판·사용자**는 로컬 DB만 읽으므로 티켓 쪽이 실패해도
그 두 유형은 정상적으로 색인된다(app/search/indexer.py::reindex_all 의 유형별 격리) — 그래서
이 파일은 '검색 재색인이 완전히 실패하지 않는다' 가 아니라 '방금 로그인한 사용자 자신이
실제로 인덱스에 들어갔다' 로 "진짜 돌았음"을 증명한다.
"""

from __future__ import annotations

import pytest

from app.audit.models import AuditLog
from app.observability.models import COMPONENT_SEARCH, SyncStatus

pytestmark = pytest.mark.integration


def _headers(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf}


def test_reindex_requires_operator(client, login_as):
    csrf = login_as("user", email="reindex-user@goodmit.co.kr")
    r = client.post("/api/search/reindex", headers=_headers(csrf))
    assert r.status_code == 403


def test_reindex_requires_auth(client):
    assert client.post("/api/search/reindex").status_code == 401


def test_operator_reindex_actually_runs(client, login_as, db):
    """더미 응답이 아니라 **진짜** reindex_all 이 돌았다는 것을, 이 요청이 만든 사용자 본인이
    검색 인덱스에 들어간 것으로 확인한다 — `app/search/indexer.py::_user_rows` 는 활성 사용자를
    전부 색인하므로, 방금 로그인한 운영자 자신이 그 안에 있어야 한다.

    전체 `status` 는 'error' 다(모듈 docstring 참조 — 이 DB는 티켓 동기화가 한 번도 성공한
    적이 없어 티켓 쪽이 실시간 Notion 조회로 떨어지고, 이 테스트 환경엔 그 응답이 없다).
    그래도 사용자 유형은 로컬 DB만 읽으므로 실패하지 않는다 — '완전 성공' 이 아니라 '진짜
    실행됐고 유형별 실패가 격리된다' 는 것을 이 비대칭 자체로 보여준다.
    """
    before = db.get(SyncStatus, COMPONENT_SEARCH)
    assert before is None

    csrf = login_as("operator", email="reindex-op@goodmit.co.kr")
    r = client.post("/api/search/reindex", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()["reindex"]
    assert body["status"] == "error"
    assert body["per_kind"].get("user", 0) >= 1
    assert body["item_count"] >= 1

    # `before` 조회가 없었으므로(행이 없어 identity map 에 캐시될 것도 없었다) 여기선 원래
    # 필요 없지만, 세션이 요청 뒤 값을 정말 다시 읽는다는 것을 명시적으로 보장해 둔다 —
    # tests/integration/test_ticket_sync_trigger.py 에서 이 생략이 실제로 거짓 실패를 냈다.
    db.expire_all()
    status = db.get(SyncStatus, COMPONENT_SEARCH)
    assert status is not None
    assert status.status == "error"
    assert status.last_run_at is not None

    # 인덱스에 실제로 행이 들어갔다는 것을 DB로 직접 본다(화면 응답 계약은 이 파일의 관심사가
    # 아니다 — GET /api/search 조회 시험은 따로 있다). `_user_rows` 는 활성 사용자 전부를
    # 색인하므로(ref_id=User.id) 방금 로그인한 운영자 자신이 정확히 한 행으로 잡혀 있어야 한다.
    from app.search.models import KIND_USER, SearchDocument
    from app.users.service import get_user_by_email

    operator = get_user_by_email(db, "reindex-op@goodmit.co.kr")
    assert operator is not None
    hit = db.query(SearchDocument).filter(
        SearchDocument.kind == KIND_USER, SearchDocument.ref_id == operator.id
    ).one_or_none()
    assert hit is not None


def test_operator_reindex_writes_audit_row(client, login_as, db):
    csrf = login_as("operator", email="reindex-audit@goodmit.co.kr")
    client.post("/api/search/reindex", headers=_headers(csrf))

    rows = db.query(AuditLog).filter(AuditLog.action == "search.reindex").all()
    assert len(rows) == 1
    assert rows[0].object_id == "search"
    assert rows[0].user_id is not None


def test_concurrent_trigger_is_rejected(client, login_as):
    """이미 진행 중인 재색인 위에 또 트리거하면 409 (같은 논블로킹 잠금 관용)."""
    from app.search.indexer import reindex_lock

    csrf = login_as("operator", email="reindex-lock@goodmit.co.kr")
    held = reindex_lock.acquire(blocking=False)
    assert held, "잠금을 선점하지 못해 이 시험이 아무것도 증명하지 못한다"
    try:
        r = client.post("/api/search/reindex", headers=_headers(csrf))
        assert r.status_code == 409
    finally:
        reindex_lock.release()

    r2 = client.post("/api/search/reindex", headers=_headers(csrf))
    assert r2.status_code == 200
