"""정책은 살아 있는 기능에만 걸고, 옛 형식은 목록에서 숨기며, 승인 정책은 실제로 걸릴 때만 센다 (계획 A5, D-542).

못박는 성질:
1. 은퇴한 기능(이전 방식의 질문 답변 · 작업 공간 묻기)은 정책의 적용 대상으로 고를 수 없다(422). AI 도우미는 고를 수 있다.
2. 옛 형식(`legacy`) 원본은 기본 목록에 없고 `include_legacy=true` 또는 종류 조건 `legacy` 로만 보인다.
3. 쓰기 승인 정책은 문서 초안 호출의 사용 기록에 **이 사람에게 승인이 필요할 때만** 남는다. 예전에는 초안을 만들 때마다
   승인 정책 id 가 실려 「최근 30일 적용」이 부풀었다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from tests.fakes.ai import ScriptedAdapter, install_runtime

pytestmark = pytest.mark.integration


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def test_retired_actions_cannot_be_targets(client, login_as):
    csrf = login_as("system_admin")
    for target in ("chat.answer", "workspace.ask"):
        reply = client.post("/api/admin/policies", json={
            "name": "옛 기능 정책", "kind": "data_protection", "applies_to": [target], "content": {},
        }, headers=_h(csrf))
        assert reply.status_code == 422, target
    ok = client.post("/api/admin/policies", json={
        "name": "도우미 가리기", "kind": "data_protection", "applies_to": ["assistant.chat"], "content": {},
    }, headers=_h(csrf))
    assert ok.status_code == 201, ok.text


def test_legacy_rows_are_hidden_by_default(client, login_as, db):
    from app.prompts.models import Policy

    csrf = login_as("system_admin")
    db.add(Policy(id=str(uuid.uuid4()), name="옛 정책 원본", version=1, kind="legacy", applies_to_json="[]",
                  content_json=json.dumps({"rules": []}), status="archived", created_at=datetime(2026, 9, 1)))
    db.commit()
    client.post("/api/admin/policies", json={"name": "새 정책", "kind": "content", "applies_to": "*",
                                             "content": {"max_output_chars": 500}}, headers=_h(csrf))
    names = [i["name"] for i in client.get("/api/admin/policies").json()["items"]]
    assert "새 정책" in names and "옛 정책 원본" not in names
    with_legacy = [i["name"] for i in client.get("/api/admin/policies", params={"include_legacy": "true"}).json()["items"]]
    assert "옛 정책 원본" in with_legacy
    only_legacy = [i["name"] for i in client.get("/api/admin/policies", params={"kind": "legacy"}).json()["items"]]
    assert only_legacy == ["옛 정책 원본"]


def test_the_approval_policy_counts_only_when_it_was_applied(app, client, login_as):
    from app.ai.models import AiUsageRecord
    from app.ai.policy import engine as policy_engine

    csrf = login_as("system_admin")
    created = client.post("/api/admin/policies", json={
        "name": "초안 승인", "kind": "approval", "applies_to": ["workspace.draft"],
        "content": {"write_requires_approval": True, "auto_approve_roles": []},
    }, headers=_h(csrf)).json()["item"]
    assert client.post(f"/api/admin/policies/{created['id']}/transition", json={"status": "published"},
                       headers=_h(csrf)).status_code == 200
    with app.state.session_factory() as db:
        assert policy_engine.resolve(db, "workspace.draft").ids() == [], "승인 정책은 호출 정책 목록에 들지 않는다"

    runtime = install_runtime(app, ScriptedAdapter(["초안"]))
    runtime.generate(None, action_key="workspace.draft", data="본문")
    runtime.generate(None, action_key="workspace.draft", data="본문", extra_policy_ids=(created["id"],))
    with app.state.session_factory() as db:
        recorded = [json.loads(r or "[]") for r in db.execute(
            select(AiUsageRecord.policy_ids_json).where(AiUsageRecord.action_key == "workspace.draft")
            .order_by(AiUsageRecord.created_at)).scalars()]
    assert sorted(len(ids) for ids in recorded) == [0, 1] and [created["id"]] in recorded
    listed = {i["name"]: i for i in client.get("/api/admin/policies").json()["items"]}
    assert listed["초안 승인"]["applied_30d"] == 1


def test_the_summary_line_counts_applied_rules_and_waiting_migrations(client, login_as, db):
    from app.prompts.models import Policy

    csrf = login_as("system_admin")
    assert client.get("/api/admin/policies/summary").json()["sentence"].startswith("지금 적용 중인 규칙이 없습니다")
    created = client.post("/api/admin/policies", json={
        "name": "도우미 가리기", "kind": "data_protection", "applies_to": ["assistant.chat", "workspace.draft"],
        "content": {"mask_phone_numbers": True},
    }, headers=_h(csrf)).json()["item"]
    client.post(f"/api/admin/policies/{created['id']}/transition", json={"status": "published"}, headers=_h(csrf))
    origin = str(uuid.uuid4())
    db.add(Policy(id=str(uuid.uuid4()), name="옮긴 초안", version=1, kind="content", applies_to_json='["*"]',
                  content_json="{}", status="draft", migrated_from_id=origin, created_at=datetime(2026, 9, 1)))
    db.commit()
    summary = client.get("/api/admin/policies/summary").json()
    assert (summary["published"], summary["features"], summary["migrated_drafts"]) == (1, 2, 1)
    assert summary["sentence"] == "적용 중인 규칙 1개가 AI 기능 2개에 걸려 있습니다."
    assert summary["by_kind"]["data_protection"] == 1 and summary["by_kind"]["approval"] == 0
