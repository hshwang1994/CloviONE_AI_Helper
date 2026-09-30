"""정책 목록과 사용 통계가 실제로 걸린 호출을 센다 (계획 3.9 · 3.11, D-519).

못박는 성질:
1. 정책 목록은 종류, 적용 대상의 이름, 지금 걸리는가(`in_use`), 최근 30일에 걸린 호출 수를 준다. 종류로 거를 수 있다.
2. 「AI 사용 통계 > 정책」은 이름마다 한 줄이고, 걸린 호출 수는 AI 호출 기록에서 센다. 예전에는 스케줄이 이름을
   참조하는가를 셌고 언제나 「쓰이지 않음」이었다.
"""

from __future__ import annotations

import pytest

from tests.fakes.ai import ScriptedAdapter, install_runtime

pytestmark = pytest.mark.integration


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def test_the_list_and_the_stats_count_the_calls_a_policy_touched(app, client, login_as):
    csrf = login_as("system_admin")
    created = client.post("/api/admin/policies", json={
        "name": "질문 가리기", "kind": "data_protection", "applies_to": ["chat.answer", "workspace.ask"],
        "content": {},
    }, headers=_h(csrf)).json()["item"]
    assert (created["kind_label"], created["applies_to_labels"], created["in_use"]) == (
        "개인정보 가리기", ["채팅 답변", "작업 공간 질문"], False)
    client.post(f"/api/admin/policies/{created['id']}/transition", json={"status": "published"}, headers=_h(csrf))
    client.post("/api/admin/policies", json={"name": "짧은 답", "kind": "content", "applies_to": "*",
                                             "content": {"max_output_chars": 500}}, headers=_h(csrf))

    runtime = install_runtime(app, ScriptedAdapter(["답"]))
    for action in ("chat.answer", "workspace.ask", "home.narrative"):
        runtime.generate(None, action_key=action, data="010-1234-5678")

    listed = {i["name"]: i for i in client.get("/api/admin/policies").json()["items"]}
    assert (listed["질문 가리기"]["in_use"], listed["질문 가리기"]["calls_30d"]) == (True, 2)
    assert listed["짧은 답"]["calls_30d"] == 0, "발행하지 않은 정책이 걸렸다"
    only_content = client.get("/api/admin/policies", params={"kind": "content"}).json()["items"]
    assert [i["name"] for i in only_content] == ["짧은 답"]

    stats = {i["name"]: i for i in client.get("/api/admin/policies/usage/stats").json()["items"]}
    assert (stats["질문 가리기"]["applied"], stats["질문 가리기"]["published_version"]) == (2, 1)
    assert stats["질문 가리기"]["last_applied_at"] is not None
    assert (stats["짧은 답"]["applied"], stats["짧은 답"]["published_version"]) == (0, None)
