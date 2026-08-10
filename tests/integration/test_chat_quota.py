"""AI 사용 상한이 **메인 채팅에도** 걸린다 (X11).

문장 생성(`assistant`)과 문서 생성에는 상한을 걸면서 **정작 비용이 가장 큰 축인 AI 도우미
채팅만 상한 밖**이었다. 그래서 관리자 화면의 숫자가 아무도 막지 않는 값이었다 — 전역 상한
100 에 20명이 15회씩 쓰면 화면은 "300/100" 인데 **아무도 안 막힌다**.

두 가지를 함께 본다:

* **전송과 재시도 둘 다** 막히는가 — 한쪽만 막으면 '다시 시도' 를 눌러 우회한다
  (같은 우회를 레이트리미터에서 이미 한 번 겪었고, 그 주석이 코드에 남아 있다).
* **성공한 호출만 세는가** — 큐에 넣을 때 세면 러너가 죽은 날 사용자가 답을 못 받고 상한만
  잃고, 재시도 세 번이 한 답변에 세 번 세어진다. **우리 실패를 사용자에게 청구**하는 셈이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest


@pytest.fixture()
def capped(db, make_user):
    """하루 1회 상한이 걸린 사용자."""
    from app.quotas.models import AiQuota

    u = make_user("cap@goodmit.co.kr", role="user", display_name="상한사용자")
    db.add(AiQuota(
        scope_type="user", user_id=u.id, period="day", max_calls=1,
        created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 1),
    ))
    db.commit()
    return u


_seq = iter(range(1, 10_000))


def _send(client, csrf, conv_id, text="안녕"):
    return client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": text, "client_message_id": f"cli-msg-{next(_seq):04d}"},
        headers={"X-CSRF-Token": csrf},
    )


def _new_conversation(client, csrf):
    r = client.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 201, r.text
    return r.json()["conversation"]["id"]


def test_the_main_chat_is_inside_the_cap(client, login_as, db, capped):
    """상한을 다 쓴 사람은 채팅을 못 보낸다."""
    from app.observability.service import record_usage
    from app.quotas.service import EVENT_AI_CALL

    csrf = login_as("user", email="cap@goodmit.co.kr")
    conv = _new_conversation(client, csrf)

    # 이미 1회 쓴 상태로 만든다(상한 1).
    record_usage(
        db, event=EVENT_AI_CALL, user_id=capped.id, org_id=None,
        object_type="ai", object_id="chat_message", meta={"kind": "chat_message"},
        now=datetime.now(),
    )
    db.commit()

    r = _send(client, csrf, conv)
    assert r.status_code == 429, (
        f"상한을 다 썼는데 메인 채팅이 그대로 나갔다: {r.status_code} {r.text}"
    )


def test_retry_goes_through_the_same_door(client, login_as, db, capped):
    """한쪽만 막으면 '다시 시도' 로 우회한다 — 레이트리미터에서 이미 겪은 그 구멍이다."""
    from app.observability.service import record_usage
    from app.quotas.service import EVENT_AI_CALL

    csrf = login_as("user", email="cap@goodmit.co.kr")
    conv = _new_conversation(client, csrf)

    r = _send(client, csrf, conv)
    assert r.status_code == 202, f"상한 안인데 못 보낸다: {r.status_code} {r.text}"
    message_db_id = r.json()["message"]["id"]

    record_usage(
        db, event=EVENT_AI_CALL, user_id=capped.id, org_id=None,
        object_type="ai", object_id="chat_message", meta={"kind": "chat_message"},
        now=datetime.now(),
    )
    db.commit()

    r = client.post(
        f"/api/messages/{message_db_id}/retry", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 429, (
        f"'다시 시도' 로 상한을 우회했다: {r.status_code} {r.text}"
    )


def test_a_user_without_a_quota_row_is_not_capped(client, login_as, make_user):
    """fail-open — 상한 행이 없으면 아무 제한도 없다.

    이 규칙을 깨면 쿼터를 켠 적도 없는 곳에서 AI 가 통째로 막히고, 운영자는 원인을 찾느라
    한나절을 쓴다(`quotas/service.enforce` 의 docstring 이 못박아 놓은 계약이다).
    """
    make_user("nocap@goodmit.co.kr", role="user", display_name="무제한")
    csrf = login_as("user", email="nocap@goodmit.co.kr")
    conv = _new_conversation(client, csrf)

    r = _send(client, csrf, conv)
    assert r.status_code == 202, f"상한 행이 없는데 막혔다: {r.status_code} {r.text}"


def test_my_ai_quota_reports_this_users_own_usage(client, login_as, db, capped):
    """AI-44: 관리자 콘솔의 /api/ai-quotas*는 CONSOLE_READ_ROLES 전용이라 일반 사용자가
    자기 쿼터를 볼 방법이 없었다. 새 자기서비스 경로가 본인의 사용량·상한을 돌려준다."""
    from app.observability.service import record_usage
    from app.quotas.service import EVENT_AI_CALL

    csrf = login_as("user", email="cap@goodmit.co.kr")
    record_usage(
        db, event=EVENT_AI_CALL, user_id=capped.id, org_id=None,
        object_type="ai", object_id="chat_message", meta={"kind": "chat_message"},
        now=datetime.now(),
    )
    db.commit()

    r = client.get("/api/me/ai-quota", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    body = r.json()
    day = next(p for p in body["periods"] if p["period"] == "day")
    assert day["limit"] == 1
    assert day["used"] == 1


def test_my_ai_quota_does_not_require_admin_role(client, login_as, make_user):
    """관리자 전용 /api/ai-quotas*와 달리, 이 경로는 일반 user 역할도 접근 가능해야 한다
    (그게 이 항목의 요지 — 자기 것만 보는 자기서비스)."""
    make_user("nocap@goodmit.co.kr", role="user", display_name="무제한")
    csrf = login_as("user", email="nocap@goodmit.co.kr")
    r = client.get("/api/me/ai-quota", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_the_admin_screen_says_chat_is_enforced(client, login_as):
    """화면이 "어디에 상한이 걸리는가" 를 스스로 지어내지 않게 서버가 말해 준다.

    채팅을 상한 안에 넣고 이 목록을 안 고치면, 화면은 계속 **안 걸리는 두 가지만** 말한다.
    """
    login_as("system_admin")
    kinds = {e["kind"] for e in client.get("/api/admin/ai-quotas").json()["enforced_on"]}
    assert "chat_message" in kinds, (
        f"관리자 화면이 채팅에 상한이 걸린다는 사실을 말하지 않는다: {kinds}"
    )
