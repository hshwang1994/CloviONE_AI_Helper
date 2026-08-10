"""티켓 강제 재동기화 API — POST /api/tickets/sync (C7).

team_docs 의 POST /api/team-docs/sync 와 같은 패턴을 이식한 것이라, 시험도 그 파일
(tests/integration/test_team_docs_api.py::test_sync_requires_operator /
test_operator_sync_faults_gracefully_without_notion)과 같은 모양을 그대로 따른다.

지금까지는 이 버튼이 없어서 Notion 쪽이 깨졌다 복구돼도 다음 워커 틱까지 기다리는 것 말고는
방법이 없었다 — 이 파일은 그 버튼이 실제로 있고(권한 있는 사람만), 눌렀을 때 진짜 동기화
함수가 불리고(더미 응답이 아니라), 감사 로그가 남고, 두 번 동시에 못 누르는 것을 고정한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.audit.models import AuditLog
from app.tickets.models import SYNC_IDLE, SYNC_OK, TicketCache, TicketSyncState, SYNC_STATE_ID

pytestmark = pytest.mark.integration


def _headers(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf}


def test_ticket_sync_requires_operator(client, login_as):
    """일반 사용자는 못 누른다 — team_docs 와 같은 기준(MODERATOR_ROLES)."""
    csrf = login_as("user", email="ticketsync-user@goodmit.co.kr")
    r = client.post("/api/tickets/sync", headers=_headers(csrf))
    assert r.status_code == 403


def test_ticket_sync_requires_auth(client):
    assert client.post("/api/tickets/sync").status_code == 401


def test_operator_sync_actually_runs_and_faults_gracefully_without_notion(client, login_as, db):
    """운영자가 누르면 **진짜** sync_tickets 가 돈다 — team_docs 와 같은 이유로
    (fake_http 에 아무 경로도 등록돼 있지 않아) Notion 왕복이 실패하고, 그 실패가 조용히
    삼켜지지 않고 status='error' 로 응답에 드러난다.

    `TicketSyncState.last_run_at` 이 이 요청의 시각으로 바뀐 것을 직접 확인한다 — 라우터가
    더미 값을 돌려주는 게 아니라 실제로 `app/tickets/sync.py::sync_tickets` 를 거쳤다는
    증거다(마이그레이션 시드 행의 기본 status는 SYNC_IDLE 이라 'error' 로 바뀐 것 자체가
    실행 증거다).

    `db.expire_all()` 을 요청 뒤에 부르는 이유: `db` 픽스처 세션이 요청 **전에** 이미 이
    행을 한 번 읽었으므로(아래 `before`), SQLAlchemy 의 identity map 이 그 객체를 들고 있다.
    만료시키지 않으면 `db.get()` 이 DB 를 다시 안 보고 세션에 캐시된 옛 값(idle)을 그대로
    돌려줘서, 실제로는 커밋된 'error' 를 놓친 채로 통과해 버리는(또는 이번처럼 옛 값으로
    거짓 실패하는) 시험이 된다 — sqlite3로 파일을 직접 읽어 실제 커밋값이 'error' 인 것을
    먼저 확인한 뒤 알아낸 원인이다.
    """
    before = db.get(TicketSyncState, SYNC_STATE_ID)
    # 0023 마이그레이션이 싱글턴 행을 status='idle' 로 미리 심어 둔다 — None 이 아니다.
    assert before is not None and before.status == SYNC_IDLE

    csrf = login_as("operator", email="ticketsync-op@goodmit.co.kr")
    r = client.post("/api/tickets/sync", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync"]["status"] == "error"

    db.expire_all()
    state = db.get(TicketSyncState, SYNC_STATE_ID)
    assert state is not None
    assert state.status == "error"
    assert state.last_run_at is not None


def test_operator_sync_writes_audit_row(client, login_as, db):
    csrf = login_as("operator", email="ticketsync-audit@goodmit.co.kr")
    client.post("/api/tickets/sync", headers=_headers(csrf))

    rows = db.query(AuditLog).filter(AuditLog.action == "ticket.sync").all()
    assert len(rows) == 1
    assert rows[0].object_id == "tickets"
    assert rows[0].user_id is not None


def test_concurrent_trigger_is_rejected(client, login_as):
    """이미 진행 중인 동기화 위에 또 트리거하면 409 — 신경질적 더블클릭이 같은 Notion 왕복을
    두 번 돌리지 않는다(app/tickets/claim_lock.py 와 같은 논블로킹 잠금 관용)."""
    from app.tickets.router import _ticket_sync_lock

    csrf = login_as("operator", email="ticketsync-lock@goodmit.co.kr")
    held = _ticket_sync_lock.acquire(blocking=False)
    assert held, "잠금을 선점하지 못해 이 시험이 아무것도 증명하지 못한다"
    try:
        r = client.post("/api/tickets/sync", headers=_headers(csrf))
        assert r.status_code == 409
    finally:
        _ticket_sync_lock.release()

    # 잠금이 풀린 뒤에는 정상적으로 다시 돈다 — 이 시험이 락을 영구히 눌러 놓은 채 끝나지
    # 않는다는 것을 스스로 증명한다.
    r2 = client.post("/api/tickets/sync", headers=_headers(csrf))
    assert r2.status_code == 200


def _mirror_ready(db, settings) -> None:
    """GET /api/tickets/team 이 실시간 Notion 호출 대신 미러(캐시)를 읽게 한다
    (test_ticket_filters.py 의 같은 이름 헬퍼와 동일한 이유) — 이게 없으면 이 파일의
    fake_http 에 아무 경로도 없어 NotionNotConfiguredError/NotionQueryError 로 일찍
    반환되고, 그 두 예외 분기 다 `can_sync`를 안 실어 시험이 실제로 아무것도 못 본다.
    `_cache_ready`(repository_notion.py)는 성공 이력 + **캐시 행이 1건 이상**이어야
    참이 되므로(0건이면 신선해도 실시간으로 폴백) 더미 행을 하나 심는다."""
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    db.add(TicketCache(notion_page_id="page-cansync", title="더미", status="완료"))
    state = db.get(TicketSyncState, SYNC_STATE_ID)
    if state is None:
        state = TicketSyncState(id=SYNC_STATE_ID)
        db.add(state)
    state.status = SYNC_OK
    state.last_run_at = datetime(2026, 7, 14)
    state.last_success_at = datetime(2026, 7, 14)
    state.ticket_count = 1
    state.truncated = False
    state.error = None
    db.commit()


@pytest.mark.parametrize("role,expected", [
    ("user", False), ("auditor", False),
    ("operator", True), ("admin", True), ("system_admin", True),
])
def test_team_list_exposes_can_sync_per_role(client, login_as, db, settings, role, expected):
    """GET /api/tickets/team 의 can_sync (FN-03) — 화면이 이 필드를 보고 '지금 동기화'
    버튼을 켤지 판단한다(team_docs 의 can_sync 와 같은 이유, app/team_docs/router.py:134)."""
    _mirror_ready(db, settings)
    csrf = login_as(role, email=f"ticketsync-cansync-{role}@goodmit.co.kr")
    r = client.get("/api/tickets/team?active=false", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True and body["ok"] is True, body
    assert body["can_sync"] is expected
