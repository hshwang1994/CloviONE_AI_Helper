"""검색 인덱스 강제 재색인 API — POST /api/search/reindex (C7).

이 시험 파일은 **한 번도 티켓 동기화가 성공한 적 없는** 갓 만든 DB 위에서 돈다(`real_db` 표시가
있어 매 테스트가 전용 PostgreSQL 데이터베이스를 받는다 — tests/conftest.py `db_url`). 그래서
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

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


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
    """이미 진행 중인 재색인 위에 또 트리거하면 409 (같은 논블로킹 잠금 관용).

    qa-contract-change: 잠금이 프로세스 안의 threading.Lock 에서 DB advisory lock 으로 바뀌어(D-192) 선점 방법을 별도 커넥션으로 옮겼다. 확인하는 계약(선점 중이면 409, 놓으면 200)은 그대로이고, 오히려 워커가 여럿일 때도 성립하는 형태로 강해졌다.

    옛 `threading.Lock()` 은 이 시험 프로세스 안에서만 성립해서, 워커를 늘리면 잠금이
    N벌이 되어 아무것도 막지 못했다. advisory lock 은 **DB 가 들고 있으므로** 다른
    커넥션에서 선점할 수 있고, 여기서는 그 성질을 그대로 써서 잠금을 쥔 채 요청을 보낸다.
    """
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.core.advisory_lock import GLOBAL_KEY, NS_SEARCH_REINDEX

    csrf = login_as("operator", email="reindex-lock@goodmit.co.kr")

    # 요청이 쓰는 커넥션과 **다른** 커넥션에서 잠근다. 요청 세션에 걸면 잠긴 구간 안의
    # 커밋 하나가 잠금을 조용히 풀어서, 이 시험이 아무것도 증명하지 못한다.
    engine = client.app.state.engine
    holder = Session(bind=getattr(engine, "engine", engine))
    try:
        held = holder.execute(
            text("SELECT pg_try_advisory_xact_lock(:ns, :key)"),
            {"ns": NS_SEARCH_REINDEX, "key": GLOBAL_KEY},
        ).scalar()
        assert held is True, "잠금을 선점하지 못해 이 시험이 아무것도 증명하지 못한다"

        r = client.post("/api/search/reindex", headers=_headers(csrf))
        assert r.status_code == 409
    finally:
        # 커밋이 아니라 롤백이다. 트랜잭션이 끝나면서 잠금이 함께 풀린다.
        holder.rollback()
        holder.close()

    r2 = client.post("/api/search/reindex", headers=_headers(csrf))
    assert r2.status_code == 200
