"""티켓 활동 이력은 **권한을 먼저 보고, 보여 줄 것만 보여 준다** (S18 · W8).

계획서가 티켓 상세를 두고 «이 페이지 최대 정보 공백» 이라고 적은 것이 활동 이력이다 —
상태·담당자·마감 변경이 전부 감사 로그에 남는데 화면에는 없었다. 그 기록을 티켓 열람자에게
열면서 두 가지가 함께 열리면 안 된다:

  * **범위 밖 티켓의 이력.** 「이력이 없다」가 아니라 「그 티켓이 없다」로 답해야 한다 —
    빈 이력을 돌려주면 그 티켓의 **존재**가 새어 나간다.
  * **감사 행의 운영 정보.** 클라이언트 IP·요청 id 는 감사 화면(권한이 좁다)의 것이다.
    이 경로가 그것을 실어 보내면 감사 화면의 권한 경계를 우회하는 뒷문이 된다.

여기서 확인하는 것은 그 둘과, 「바뀐 칸만 나간다」는 계약이다. 마지막은 성능이 아니라
읽힘의 문제다: 저장 한 번에 아홉 칸이 전부 나열되면 무엇이 바뀌었는지가 오히려 안 보인다.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration

CENSORED = ("client_ip", "request_id", "before_json", "after_json", "user_id")


def _audit(db, *, ticket_id: str, actor_id: str, action: str, before: dict, after: dict):
    from app.audit.models import AuditLog

    row = AuditLog(user_id=actor_id, action=action, object_type="notion_task",
                   object_id=ticket_id, before_json=json.dumps(before),
                   after_json=json.dumps(after), result="success",
                   client_ip="10.9.9.9", request_id="req-should-not-leak")
    db.add(row)
    db.commit()
    return row


def test_only_changed_fields_are_reported(client, login_as, db, make_ticket, make_user):
    csrf = login_as("system_admin")
    _ = csrf
    actor = make_user(email="history-actor@goodmit.co.kr", role="user",
                      display_name="김지훈")
    ticket = make_ticket(title="이력 시험 티켓")
    _audit(db, ticket_id=ticket.id, actor_id=actor.id, action="ticket.update",
           before={"status": "진행", "priority": "Normal", "due": "2026-08-20",
                   "assignees": [], "difficulty": "중", "est_wd": 1.5},
           after={"status": "완료", "priority": "Normal", "due": "2026-08-20",
                  "assignees": [], "difficulty": "중", "est_wd": 1.5})

    res = client.get("/api/tickets/%s/history" % ticket.id)
    assert res.status_code == 200, res.text[:400]
    items = res.json()["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["actor"] == "김지훈"
    assert entry["summary"]
    fields = [c["field"] for c in entry["changes"]]
    assert fields == ["status"], "안 바뀐 칸까지 실었다: %s" % fields
    assert entry["changes"][0]["from"] == "진행"
    assert entry["changes"][0]["to"] == "완료"


def test_operational_columns_never_leave_the_audit_table(
    client, login_as, db, make_ticket, make_user
):
    """**반례가 아니라 정면이다.** 이 검사가 없으면 감사 행을 통째로 실어도 통과한다."""
    login_as("system_admin")
    actor = make_user(email="history-actor2@goodmit.co.kr", role="user")
    ticket = make_ticket(title="검열 시험 티켓")
    _audit(db, ticket_id=ticket.id, actor_id=actor.id, action="ticket.update",
           before={"status": "진행"}, after={"status": "검증"})

    body = client.get("/api/tickets/%s/history" % ticket.id).text
    for name in CENSORED:
        assert name not in body, "%s 가 응답에 실렸다" % name
    assert "10.9.9.9" not in body
    assert "req-should-not-leak" not in body


def test_assignee_ids_become_names(client, login_as, db, make_ticket, make_user):
    """담당자는 **id 가 아니라 이름**으로 나간다 — UUID 는 사람이 읽을 수 있는 이력이 아니다."""
    login_as("system_admin")
    actor = make_user(email="history-actor3@goodmit.co.kr", role="user")
    target = make_user(email="history-target@goodmit.co.kr", role="user",
                       display_name="이서연")
    ticket = make_ticket(title="담당자 이력 티켓")
    _audit(db, ticket_id=ticket.id, actor_id=actor.id, action="ticket.update",
           before={"assignees": []}, after={"assignees": [target.id]})

    entry = client.get("/api/tickets/%s/history" % ticket.id).json()["items"][0]
    change = entry["changes"][0]
    assert change["field"] == "assignees"
    assert change["from"] == "없음"
    assert change["to"] == "이서연"
    assert target.id not in json.dumps(entry, ensure_ascii=False)


def test_out_of_scope_ticket_is_404_not_an_empty_history(
    client, login_as, db, make_ticket, make_user
):
    """범위 밖은 **404** 다. 빈 목록을 주면 그 티켓이 있다는 사실이 새어 나간다.

    소속을 판정할 수 없는 티켓(프로젝트가 없다)은 전역 관리자 말고는 아무에게도 안
    보인다 — 「판정할 수 없으면 닫는다」(0060). 일반 사용자에게는 그 티켓이 **없다**.
    """
    orphan = make_ticket(title="소속 없는 티켓")
    _audit(db, ticket_id=orphan.id, actor_id=None, action="ticket.update",
           before={"status": "진행"}, after={"status": "완료"})
    make_user(email="scoped-viewer@goodmit.co.kr", role="user")
    login_as("user", email="scoped-viewer@goodmit.co.kr")

    res = client.get("/api/tickets/%s/history" % orphan.id)
    assert res.status_code == 404, "%s %s" % (res.status_code, res.text[:300])
    assert "완료" not in res.text, "404 인데 이력 내용이 새어 나왔다"


def test_history_reads_names_in_one_go_not_per_row(
    client, login_as, db, make_ticket, make_user
):
    """이름을 행마다 조회하면 이력 50줄이 질의 50번이 된다 — 한 번에 모아 읽는다."""
    from sqlalchemy import event

    login_as("system_admin")
    actor = make_user(email="history-actor4@goodmit.co.kr", role="user")
    ticket = make_ticket(title="질의 수 시험 티켓")
    for i in range(12):
        _audit(db, ticket_id=ticket.id, actor_id=actor.id, action="ticket.update",
               before={"status": "진행"}, after={"status": "검증" if i % 2 else "완료"})

    seen: list[str] = []

    def _before(conn, cursor, statement, *a, **kw):  # noqa: ANN001, ARG001
        if " users" in statement and statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _before)
    try:
        res = client.get("/api/tickets/%s/history" % ticket.id)
    finally:
        event.remove(bind, "before_cursor_execute", _before)
    assert res.status_code == 200, res.text[:300]
    assert len(res.json()["items"]) == 12
    # 세션·권한 판정도 users 를 읽으므로 정확한 수를 못 박지 않는다 — «행 수만큼 늘지
    # 않는다» 만 본다. 행마다 읽으면 12를 넘는다.
    assert len(seen) <= 6, "이력 12줄에 users 질의 %d번" % len(seen)
