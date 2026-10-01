"""AI 사용 통계의 기간 · 검색 · 지표 한 줄 (계획 A6, D-543).

못박는 성질:
1. 기간은 프리셋(오늘 · 7일 · 30일 · 이번 달)이거나 직접 고른 두 날짜다(한국 시간, 서버 시계). 비우면 30일이고, 응답이 그 기간을
   문장으로 말한다(`range_label`). 날짜만 오면 직접 선택이다(옛 주소와 저장된 뷰).
2. 지표 한 줄(`totals`)은 같은 조건의 합계 한 벌이다: 요청 · 성공률 · 실패 · 정책 차단 · 한도 초과 · 토큰 · 평균 응답 · 마지막.
   정책 차단과 한도 초과는 따로 센다(「막힘」 하나로 뭉치지 않는다).
3. 검색어는 사람 이름 · 이메일이나 기능 이름에 맞는 기록이다 - 쪽을 넘겨도 같은 조건이다(브라우저가 행을 훑지 않는다).
4. 호출 기록 행은 도구 이름 · 라운드 · 모드를 싣는다(인자와 결과는 없다).
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def seeded(db, make_user, fake_clock):
    from app.ai.models import AiUsageRecord

    alice = make_user("usage-alice@goodmit.co.kr", role="user", display_name="앨리스")
    bob = make_user("usage-bob@goodmit.co.kr", role="user", display_name="밥")
    now = fake_clock.now()
    rows = [
        (alice.id, "assistant.chat", "ok", 0, 100, ["search_documents", "my_work"], 3),
        (alice.id, "assistant.chat", "error", 1, 300, [], 1),
        (bob.id, "assistant.chat", "blocked_policy", 2, None, [], None),
        (bob.id, "workspace.draft", "blocked_quota", 3, None, [], None),
        (bob.id, "workspace.draft", "ok", 20, 200, [], None),
        (alice.id, "workspace.draft", "ok", 45, 50, [], None),
    ]
    for user_id, action, status, days_ago, latency, tools, rounds in rows:
        db.add(AiUsageRecord(
            id=str(uuid.uuid4()), created_at=now - timedelta(days=days_ago), actor_kind="user", user_id=user_id,
            action_key=action, status=status, latency_ms=latency, input_tokens=10, output_tokens=5,
            tool_names_json=json.dumps(tools) if tools else None, tool_calls=len(tools) or None, rounds=rounds,
            mode="tools" if tools else None,
        ))
    db.commit()
    return {"alice": alice.id, "bob": bob.id}


def test_period_presets_and_the_range_sentence(client, login_as, seeded):
    login_as("system_admin")
    default = client.get("/api/admin/ai/usage/stats").json()
    assert default["period"] == "30d" and default["range_label"].startswith("기간은 ") and default["range_label"].endswith("까지입니다.")
    assert default["totals"]["calls"] == 5, "30일 밖의 기록을 셌다"
    seven = client.get("/api/admin/ai/usage/stats", params={"period": "7d"}).json()
    assert seven["totals"]["calls"] == 4
    today = client.get("/api/admin/ai/usage/stats", params={"period": "today"}).json()
    assert today["range_label"].endswith("하루입니다.")
    custom = client.get("/api/admin/ai/usage/stats", params={"from": default["from"], "to": default["to"]}).json()
    assert custom["period"] == "custom" and custom["totals"]["calls"] == 5
    assert client.get("/api/admin/ai/usage/stats", params={"period": "year"}).status_code == 422


def test_the_metric_line_splits_policy_and_quota_blocks(client, login_as, seeded):
    login_as("system_admin")
    totals = client.get("/api/admin/ai/usage/stats", params={"period": "30d"}).json()["totals"]
    assert (totals["calls"], totals["ok"], totals["errors"]) == (5, 2, 1)
    assert (totals["blocked_policy"], totals["blocked_quota"]) == (1, 1)
    assert totals["success_rate"] == 67 and totals["avg_latency_ms"] == 200
    assert totals["input_tokens"] == 50 and totals["last_at"] is not None
    by_action = {i["key"]: i for i in client.get("/api/admin/ai/usage/stats", params={"period": "30d"}).json()["items"]}
    assert (by_action["assistant.chat"]["blocked_policy"], by_action["workspace.draft"]["blocked_quota"]) == (1, 1)


def test_search_matches_people_and_feature_names_on_the_server(client, login_as, seeded):
    login_as("system_admin")
    by_name = client.get("/api/admin/ai/usage/records", params={"period": "30d", "q": "앨리스"}).json()
    assert by_name["total"] == 2 and {i["user_id"] for i in by_name["items"]} == {seeded["alice"]}
    by_email = client.get("/api/admin/ai/usage/stats", params={"period": "30d", "q": "usage-bob"}).json()
    assert by_email["totals"]["calls"] == 3
    by_feature = client.get("/api/admin/ai/usage/records", params={"period": "30d", "q": "문서 초안"}).json()
    assert {i["action_key"] for i in by_feature["items"]} == {"workspace.draft"}
    nothing = client.get("/api/admin/ai/usage/records", params={"period": "30d", "q": "없는사람%_"}).json()
    assert nothing["total"] == 0, "검색어의 와일드카드가 그대로 먹혔다"


def test_records_carry_tool_names_rounds_and_mode(client, login_as, seeded):
    login_as("system_admin")
    items = client.get("/api/admin/ai/usage/records", params={"period": "today"}).json()["items"]
    row = next(i for i in items if i["tool_names"])
    assert row["tool_names"] == ["search_documents", "my_work"] and row["rounds"] == 3 and row["mode"] == "tools"
    assert row["tools_label"] == "사내 문서 검색, 내 업무"
    catalog = client.get("/api/admin/ai/usage/catalog").json()
    assert [p["key"] for p in catalog["periods"]] == ["today", "7d", "30d", "month", "custom"]
    assert [v["key"] for v in catalog["views"]] == ["action", "user", "department", "model"]
    retired = {a["key"]: a["retired"] for a in catalog["actions"]}
    assert retired["chat.answer"] is True and retired["assistant.chat"] is False
