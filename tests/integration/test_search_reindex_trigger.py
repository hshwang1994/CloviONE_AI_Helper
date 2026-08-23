"""검색 인덱스 강제 재색인 API — POST /api/search/reindex (C7).

이 시험 파일은 **티켓이 한 건도 없는** 갓 만든 DB 위에서 돈다(`real_db` 표시가 있어 매
테스트가 전용 PostgreSQL 데이터베이스를 받는다 — tests/conftest.py `db_url`). 티켓 색인은
자체 DB 표를 읽고 그 표가 비어 있을 뿐이므로 **성공한다** — 0건은 사고가 아니라 사실이고,
그래서 전체 결과도 `ok` 다.

S14 전에는 같은 자리에서 `status == "error"` 를 기대했다. 그때는 티켓 저장소가 미러를 아직
못 믿으면 실시간 Notion 조회로 떨어졌고(`app/tickets/repository_notion.py::_cache_ready`),
이 테스트 환경(fake_http 에 아무 경로도 등록하지 않음)에서는 그 조회가 반드시 실패했기
때문이다. 자체 DB 소스에는 그 폴백이 없어서 실패할 바깥 구간 자체가 사라졌다.

유형 하나가 죽어도 나머지는 색인된다는 격리(app/search/indexer.py::reindex_all)는 여기서
보지 않는다. `tests/unit/test_search_indexer.py::test_a_dead_ticket_source_keeps_the_existing_ticket_index`
가 소스를 직접 고장 내며 그 성질만 보고 있어서, 여기서 같은 것을 환경 사정으로 한 번 더
확인하면 시험이 무엇을 지키는지가 흐려진다. 이 파일이 증명하는 것은 하나다 — 더미 응답이
아니라 진짜 `reindex_all` 이 돌았고, 그 증거로 방금 로그인한 사용자 자신이 인덱스에 들어가
있다.
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

    전체 `status` 는 'ok' 다(모듈 docstring 참조 — 자체 DB 소스에는 실패할 바깥 구간이 없다).
    티켓이 0건이라는 것은 실패가 아니므로 `per_kind['ticket']` 이 0 이어도 결과는 성공이고,
    사용자 유형에 최소 한 행이 잡히는 것이 이 재색인이 실제로 일한 증거다.
    """
    before = db.get(SyncStatus, COMPONENT_SEARCH)
    assert before is None

    csrf = login_as("operator", email="reindex-op@goodmit.co.kr")
    r = client.post("/api/search/reindex", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()["reindex"]
    assert body["status"] == "ok"
    # 사유 칸도 함께 본다. 지금은 상태값과 같은 곳에서 나오지만(reindex_all 의 errors 목록),
    # 화면과 운영 대시보드가 실제로 읽어 사람에게 보여주는 것은 이 칸이라 둘이 갈라지면
    # 사용자에게는 사유만 보인다.
    assert body["error"] is None
    assert body["per_kind"].get("user", 0) >= 1
    assert body["item_count"] >= 1

    # `before` 조회가 없었으므로(행이 없어 identity map 에 캐시될 것도 없었다) 여기선 원래
    # 필요 없지만, 세션이 요청 뒤 값을 정말 다시 읽는다는 것을 명시적으로 보장해 둔다 —
    # tests/integration/test_ticket_sync_trigger.py 에서 이 생략이 실제로 거짓 실패를 냈다.
    db.expire_all()
    status = db.get(SyncStatus, COMPONENT_SEARCH)
    assert status is not None
    assert status.status == "ok"
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
