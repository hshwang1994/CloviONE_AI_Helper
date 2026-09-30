"""AI 사용 통계 API — `/api/admin/ai/usage` (계획 3.11, D-517).

못박는 성질:
1. 묶음마다 호출 수, 성공률, 막힘, 토큰, 평균 지연을 준다. 성공률은 제공자까지 간 호출(성공 + 실패) 가운데
   성공한 비율이고 반올림은 서버 한 곳(ROUND_HALF_UP)에서 한다. 막힌 호출은 따로 센다.
2. 사람으로 묶을 때는 내부 id 로 묶는다 - 이름이 같은 두 사람은 두 줄이고 이메일로 갈린다.
3. 날짜는 한국 시간으로 자른다. 기본 기간은 오늘을 끝으로 30일이고, 한 번에 366일까지 본다.
4. 호출 기록은 쪽으로 나뉘고 정렬 키는 정해진 것만 받는다. 질문과 답의 본문은 응답에 없다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.ai.models import AiUsageRecord

pytestmark = pytest.mark.integration


def _rec(db, *, when, user_id=None, action="chat.answer", status="ok", provider="anthropic", model="m-1",
         inp=None, out=None, latency=None, department_name=None) -> None:
    db.add(AiUsageRecord(
        id=str(uuid.uuid4()), created_at=when, actor_kind="user" if user_id else "system", user_id=user_id,
        action_key=action, status=status, provider=provider, model=model, input_tokens=inp, output_tokens=out,
        latency_ms=latency, department_name=department_name,
    ))


def _admin(login_as):
    return login_as("system_admin", email="usage-admin@goodmit.co.kr")


def test_grouping_by_feature_counts_success_blocked_and_tokens(client, login_as, db, fake_clock):
    _admin(login_as)
    now = fake_clock.now()
    for latency in (100, 300):
        _rec(db, when=now, action="chat.answer", inp=100, out=20, latency=latency)
    _rec(db, when=now, action="chat.answer", status="error")
    _rec(db, when=now, action="chat.answer", status="blocked_quota")
    _rec(db, when=now, action="workspace.ask", inp=50, out=5, latency=40)
    db.commit()

    body = client.get("/api/admin/ai/usage/stats").json()
    chat, ask = body["items"]
    assert (chat["key"], chat["label"]) == ("chat.answer", "채팅 답변"), "호출이 많은 묶음이 먼저 온다"
    assert (chat["calls"], chat["ok"], chat["errors"], chat["blocked"]) == (4, 2, 1, 1)
    assert chat["success_rate"] == 67, "2/3 은 66.67 이고 서버가 한 번 반올림한다"
    assert (chat["input_tokens"], chat["output_tokens"], chat["avg_latency_ms"]) == (200, 40, 200)
    assert (ask["calls"], ask["success_rate"]) == (1, 100)
    assert body["totals"]["calls"] == 5 and body["totals"]["success_rate"] == 75


def test_people_with_the_same_name_stay_two_rows(client, login_as, db, make_user, fake_clock):
    _admin(login_as)
    first = make_user("same-1@goodmit.co.kr", display_name="김민수")
    second = make_user("same-2@goodmit.co.kr", display_name="김민수")
    now = fake_clock.now()
    _rec(db, when=now, user_id=first.id)
    _rec(db, when=now, user_id=second.id)
    _rec(db, when=now, user_id=second.id)
    db.commit()

    items = client.get("/api/admin/ai/usage/stats", params={"group_by": "user"}).json()["items"]
    assert [(i["key"], i["label"], i["email"], i["calls"]) for i in items] == [
        (second.id, "김민수", "same-2@goodmit.co.kr", 2),
        (first.id, "김민수", "same-1@goodmit.co.kr", 1),
    ], "동명이인이 한 줄로 합쳐졌다"


def test_days_are_cut_at_korean_midnight(client, login_as, db, fake_clock):
    _admin(login_as)
    # 2026-07-13 15:30 UTC 는 한국 시간 07-14 00:30, 14:30 UTC 는 한국 시간 07-13 23:30 이다.
    _rec(db, when=datetime(2026, 7, 13, 15, 30))
    _rec(db, when=datetime(2026, 7, 13, 14, 30))
    db.commit()

    items = client.get("/api/admin/ai/usage/stats", params={"group_by": "day"}).json()["items"]
    assert sorted((i["key"], i["calls"]) for i in items) == [("2026-07-13", 1), ("2026-07-14", 1)]
    one_day = client.get("/api/admin/ai/usage/stats", params={"from": "2026-07-14", "to": "2026-07-14"}).json()
    assert one_day["totals"]["calls"] == 1, "하루 조건이 UTC 날짜로 잘렸다"


def test_the_default_range_is_thirty_days_ending_today(client, login_as, db, fake_clock):
    _admin(login_as)
    # 오늘은 한국 시간 2026-07-14 다. 30일의 첫날 06-15 0시는 UTC 06-14 15:00 이다.
    _rec(db, when=datetime(2026, 6, 14, 16, 0))
    _rec(db, when=datetime(2026, 6, 14, 14, 0))
    db.commit()

    body = client.get("/api/admin/ai/usage/stats").json()
    assert (body["from"], body["to"]) == ("2026-06-15", "2026-07-14")
    assert body["totals"]["calls"] == 1


@pytest.mark.parametrize("params", [
    {"from": "2026-07-14", "to": "2026-07-01"},
    {"from": "2025-07-01", "to": "2026-07-14"},
    {"group_by": "nope"},
])
def test_bad_ranges_and_groups_are_refused(client, login_as, params):
    _admin(login_as)
    reply = client.get("/api/admin/ai/usage/stats", params=params)
    assert reply.status_code == 422, reply.text


def test_records_are_paged_sorted_and_carry_no_text(client, login_as, db, make_user, fake_clock):
    _admin(login_as)
    person = make_user("records-person@goodmit.co.kr", display_name="기록 사람")
    now = fake_clock.now()
    for minutes, latency in ((3, 300), (2, 100), (1, 200)):
        _rec(db, when=now - timedelta(minutes=minutes), user_id=person.id, latency=latency)
    _rec(db, when=now - timedelta(minutes=10), action="system.connection_test", latency=50)
    db.commit()

    first = client.get("/api/admin/ai/usage/records", params={"page_size": 2}).json()
    assert first["total"] == 4 and len(first["items"]) == 2
    assert [i["latency_ms"] for i in first["items"]] == [200, 100], "기본은 최근 호출이 먼저다"
    assert set(first["items"][0]) == {
        "id", "created_at", "user_id", "user_name", "user_email", "department_name", "action_key", "action_label",
        "provider", "model", "status", "status_label", "error_code", "input_tokens", "output_tokens", "latency_ms",
        "prompt_slot", "prompt_version", "truncated",
    }, "호출 기록 응답의 칸이 바뀌었다 - 본문이 새어 나가지 않는지 먼저 본다"
    assert (first["items"][0]["user_name"], first["items"][0]["user_email"]) == ("기록 사람",
                                                                                  "records-person@goodmit.co.kr")

    by_latency = client.get("/api/admin/ai/usage/records", params={"sort": "latency_ms", "order": "asc"}).json()
    assert [i["latency_ms"] for i in by_latency["items"]] == [50, 100, 200, 300]
    assert by_latency["items"][0]["user_name"] == "시스템"
    unknown = client.get("/api/admin/ai/usage/records", params={"sort": "created_by"})
    assert unknown.status_code == 200 and [i["latency_ms"] for i in unknown.json()["items"]] == [200, 100, 300, 50]


def test_the_catalog_names_every_feature_and_result(client, login_as):
    from app.ai.actions import ACTIONS
    from app.ai.usage import STATUS_LABELS

    _admin(login_as)
    body = client.get("/api/admin/ai/usage/catalog").json()
    assert [a["key"] for a in body["actions"]] == list(ACTIONS)
    assert [s["key"] for s in body["statuses"]] == list(STATUS_LABELS)
