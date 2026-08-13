"""UA-17: 이상 탐지가 감사 로그 diff 본문(before_json/after_json)을 안 읽는데도
`select(AuditLog)`로 그 컬럼까지 통째로 실어 왔다 — 30일 창에서 설정·사용자 변경 diff가
큰 설치는 그만큼 낭비다. 다섯 규칙이 실제로 읽는 여섯 컬럼만 고르도록 고친 뒤, 그 사실을
나가는 SQL 문자열 자체로 확인한다(파이썬 쪽 판단만 믿지 않는다)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import event

from app.audit import anomalies
from app.audit.models import AuditLog

pytestmark = pytest.mark.unit

AT = datetime(2026, 7, 13, 12, 0, 0)


def test_detect_selects_only_the_columns_the_rules_read(db, make_user):
    user = make_user("audit-col-check@goodmit.co.kr")
    db.add(AuditLog(
        user_id=user.id, action="test.action", object_type="x",
        result="success", created_at=AT,
    ))
    db.commit()

    captured: list[str] = []
    engine = db.get_bind()

    def _capture(conn, cursor, statement, parameters, context, executemany):
        if "audit_logs" in statement and statement.strip().upper().startswith("SELECT"):
            captured.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        result = anomalies.detect(db, now=AT, actor_ids=None)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert result["scanned"] == 1  # 배선이 실제로 이 행을 봤는지(엉뚱한 창을 잡아 0건이면 아래 단언이 공허해진다)

    # 창 안 전체를 보는 메인 조회(비교 구간 기준 질의는 원래도 user_id/action 두 컬럼뿐이라 대상이 아니다).
    main_queries = [q for q in captured if "created_at >=" in q.lower() or "created_at > " in q.lower()]
    assert main_queries, f"메인 조회를 못 찾았다: {captured}"
    main_query = main_queries[0]

    assert "before_json" not in main_query
    assert "after_json" not in main_query
    for expected_col in ("user_id", "action", "result", "created_at", "object_type", "object_id"):
        assert expected_col in main_query, f"{expected_col}이 SELECT 목록에 없다: {main_query}"


def test_detect_still_works_correctly_with_the_narrower_select(db, make_user):
    """컬럼만 줄었지 판정 결과는 그대로여야 한다 — row가 여전히 .user_id/.action처럼
    속성으로 읽히는지(Row도 ORM 인스턴스와 같은 방식으로 접근된다)를 실제 소견으로 확인."""
    user = make_user("audit-col-check-2@goodmit.co.kr")
    # FAILURE_BURST_THRESHOLD(5)를 넘기는 실패 6건.
    for i in range(6):
        db.add(AuditLog(
            user_id=user.id, action="test.fail", object_type="x",
            result="failed", created_at=AT,
        ))
    db.commit()

    result = anomalies.detect(db, now=AT, actor_ids=None)
    kinds = {f["kind"] for f in result["findings"] if f["actor_id"] == user.id}
    assert "failure_burst" in kinds
