"""정책 목록이 실제로 걸린 호출을 센다 (계획 A5, D-519 · D-542).

qa-contract-change: 「AI 사용 통계 > 정책」 경로(`/api/admin/policies/usage/stats`)를 걷었다 — 같은 수를 정책 목록의 「최근 30일 적용」
(`applied_30d` · `last_applied_at`)이 보인다(D-542). 그 수는 이제 성공한 요청과 정책이 막은 요청만 센다(실패한 호출은 세지 않는다).
옛 형식 정책은 목록 기본에서 숨긴다.

못박는 성질:
1. 정책 목록은 종류, 적용 대상의 이름, 지금 걸리는가(`in_use`), 최근 30일에 실제로 걸린 요청 수와 마지막 시각을 준다. 종류로
   거를 수 있다. 실패한 호출은 세지 않는다.
2. 옛 형식(`legacy`) 원본은 기본 목록에 없고 `include_legacy=true` 로만 보인다.
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
        "name": "질문 가리기", "kind": "data_protection", "applies_to": ["workspace.draft", "report.weekly_summary"],
        "content": {},
    }, headers=_h(csrf)).json()["item"]
    assert (created["kind_label"], created["applies_to_labels"], created["in_use"]) == (
        "개인정보 가리기", ["작업 공간 문서 초안", "프로젝트 주간 요약"], False)
    client.post(f"/api/admin/policies/{created['id']}/transition", json={"status": "published"}, headers=_h(csrf))
    client.post("/api/admin/policies", json={"name": "짧은 답", "kind": "content", "applies_to": "*",
                                             "content": {"max_output_chars": 500}}, headers=_h(csrf))

    runtime = install_runtime(app, ScriptedAdapter(["답"]))
    for action in ("workspace.draft", "report.weekly_summary", "home.narrative"):
        runtime.generate(None, action_key=action, data="010-1234-5678")

    listed = {i["name"]: i for i in client.get("/api/admin/policies").json()["items"]}
    assert (listed["질문 가리기"]["in_use"], listed["질문 가리기"]["calls_30d"]) == (True, 2)
    assert listed["짧은 답"]["calls_30d"] == 0, "발행하지 않은 정책이 걸렸다"
    only_content = client.get("/api/admin/policies", params={"kind": "content"}).json()["items"]
    assert [i["name"] for i in only_content] == ["짧은 답"]

    assert listed["질문 가리기"]["applied_30d"] == 2 and listed["질문 가리기"]["last_applied_at"] is not None
    assert (listed["짧은 답"]["applied_30d"], listed["짧은 답"]["last_applied_at"]) == (0, None)
    assert listed["질문 가리기"]["status_label"] == "적용 중" and listed["짧은 답"]["status_label"] == "초안"

    # 실패한 호출은 정책이 결과에 닿지 않았다 - 「최근 30일 적용」에 세지 않는다.
    from app.ai.providers import base

    failing = install_runtime(app, ScriptedAdapter([base.failure(base.ERROR_TRANSIENT, "timeout")]))
    failing.generate(None, action_key="workspace.draft", data="010-1234-5678")
    again = {i["name"]: i for i in client.get("/api/admin/policies").json()["items"]}
    assert again["질문 가리기"]["applied_30d"] == 2, "실패한 호출을 적용으로 셌다"
    assert client.get("/api/admin/policies/usage/stats").status_code in (404, 422), "걷은 통계 경로가 살아 있다"
