"""발행한 AI 정책이 실제 호출에 걸린다 (계획 3.9, D-519).

못박는 성질:
1. 개인정보 가리기가 발행돼 있으면 제공자가 받는 데이터에 전화번호와 주민등록번호가 없고, 받은 답에서도 가려진다.
2. 응답 제한은 제품 밖 링크를 누를 수 없게 하고, 액션의 상한보다 짧은 글자 수로 자른다(잘린 사실이 남는다).
   JSON 으로 답하는 퀴즈는 자르지 않고 실패로 처리한다.
3. 기능을 지정한 정책이 `*` 정책보다 먼저다. 같은 종류에서 같은 기능을 두 정책이 가리키면 발행이 409 로 막힌다.
4. 연결 확인에는 어떤 정책도 걸리지 않는다. 걸린 정책의 id 는 호출 기록에 남는다.
5. 옛 형식의 정책은 발행할 수 없다.

qa-contract-change: 은퇴한 기능(이전 방식의 질문 답변 `chat.answer` · 작업 공간 묻기 `workspace.ask`)을 정책 대상으로 고를 수 없게 되어
(D-542) 시험의 대상 기능을 살아 있는 기능(문서 초안 `workspace.draft` · 주간 요약 `report.weekly_summary`)으로 옮겼다. 응답 제한
정책의 글자 상한이 JSON 답을 막으면 오류 코드가 `policy_output_cap` 이고 사용 기록이 `blocked_policy` 다 — 모델 실패와 가른다.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.ai.models import AiUsageRecord
from tests.fakes.ai import ScriptedAdapter, install_runtime

pytestmark = pytest.mark.security


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _policy(client, csrf, *, name, kind, applies_to, content, publish=True):
    created = client.post("/api/admin/policies", json={
        "name": name, "kind": kind, "applies_to": applies_to, "content": content,
    }, headers=_h(csrf))
    assert created.status_code == 201, created.text
    item = created.json()["item"]
    if publish:
        reply = client.post(f"/api/admin/policies/{item['id']}/transition", json={"status": "published"},
                            headers=_h(csrf))
        assert reply.status_code == 200, reply.text
    return item


def _last(db) -> AiUsageRecord:
    db.expire_all()
    return db.execute(select(AiUsageRecord).order_by(AiUsageRecord.created_at.desc(), AiUsageRecord.id.desc())
                      ).scalars().first()


def test_personal_data_never_reaches_the_provider(app, client, login_as, db):
    csrf = login_as("system_admin")
    policy = _policy(client, csrf, name="개인정보 가리기", kind="data_protection", applies_to="*",
                     content={"mask_emails": True})
    adapter = ScriptedAdapter(["담당자는 010-9876-5432 입니다."])
    runtime = install_runtime(app, adapter)
    result = runtime.generate(None, action_key="workspace.draft",
                              data="고객 010-1234-5678, 주민번호 900101-1234567, 메일 a@b.co 를 확인해 주세요")
    sent = adapter.calls[-1]["user"]
    assert "010-1234-5678" not in sent and "900101-1234567" not in sent and "a@b.co" not in sent
    assert "[전화번호]" in sent and "[주민등록번호]" in sent and "[이메일]" in sent
    assert result.text == "담당자는 [전화번호] 입니다.", "받은 답에서 개인정보가 가려지지 않았다"
    assert json.loads(_last(db).policy_ids_json) == [policy["id"]]


def test_the_content_policy_neutralizes_links_and_trims(app, client, login_as):
    csrf = login_as("system_admin")
    _policy(client, csrf, name="출력 제한", kind="content", applies_to="workspace.draft",
            content={"max_output_chars": 120, "block_external_links": True})
    long_answer = "자세한 내용은 https://evil.example.com/a 에 있습니다. " + "가" * 300
    runtime = install_runtime(app, ScriptedAdapter([long_answer]))
    result = runtime.generate(None, action_key="workspace.draft", data="질문")
    assert result.ok and len(result.text) == 120 and result.output_truncated
    assert "https://" not in result.text and "evil.example.com/a" in result.text

    # 기능을 지정했으므로 다른 기능에는 걸리지 않는다.
    other = install_runtime(app, ScriptedAdapter([long_answer])).generate(None, action_key="report.weekly_summary",
                                                                         data="질문")
    assert "https://evil.example.com/a" in other.text


def test_a_json_answer_is_not_cut_it_fails(app, client, login_as):
    csrf = login_as("system_admin")
    _policy(client, csrf, name="짧게", kind="content", applies_to="*", content={"max_output_chars": 100})
    quiz = json.dumps([{"q": "문제" * 30, "options": ["가", "나"], "answer": 0}], ensure_ascii=False)
    result = install_runtime(app, ScriptedAdapter([quiz])).generate(None, action_key="game.quiz", data="{}")
    assert not result.ok and result.error_code == "policy_output_cap"
    from sqlalchemy import select

    from app.ai.models import AiUsageRecord

    with app.state.session_factory() as db:
        statuses = db.execute(select(AiUsageRecord.status).where(AiUsageRecord.action_key == "game.quiz")).scalars().all()
    assert statuses == ["blocked_policy"], "정책이 막은 호출을 모델 실패로 적었다"


def test_the_named_policy_wins_and_overlaps_are_refused(app, client, login_as):
    csrf = login_as("system_admin")
    _policy(client, csrf, name="모두 가리기", kind="data_protection", applies_to="*",
            content={"mask_phone_numbers": True})
    _policy(client, csrf, name="채팅은 그대로", kind="data_protection", applies_to="workspace.draft",
            content={"mask_phone_numbers": False, "mask_resident_registration_numbers": False})
    adapter = ScriptedAdapter(["답"])
    runtime = install_runtime(app, adapter)
    runtime.generate(None, action_key="workspace.draft", data="010-1234-5678")
    assert "010-1234-5678" in adapter.calls[-1]["user"], "기능을 지정한 정책이 먼저가 아니다"
    runtime.generate(None, action_key="report.weekly_summary", data="010-1234-5678")
    assert "[전화번호]" in adapter.calls[-1]["user"]

    second_star = _policy(client, csrf, name="또 모두", kind="data_protection", applies_to="*", content={},
                          publish=False)
    clash = client.post(f"/api/admin/policies/{second_star['id']}/transition", json={"status": "published"},
                        headers=_h(csrf))
    assert clash.status_code == 409 and "모두 가리기" in clash.json()["error"]["message"]
    same_action = _policy(client, csrf, name="채팅 또", kind="data_protection", applies_to="workspace.draft",
                          content={}, publish=False)
    clash = client.post(f"/api/admin/policies/{same_action['id']}/transition", json={"status": "published"},
                        headers=_h(csrf))
    assert clash.status_code == 409 and "채팅은 그대로" in clash.json()["error"]["message"]


def test_the_connection_test_is_never_touched(app, client, login_as, db):
    csrf = login_as("system_admin")
    _policy(client, csrf, name="모두 가리기", kind="data_protection", applies_to="*", content={})
    adapter = ScriptedAdapter(["확인"])
    runtime = install_runtime(app, adapter)
    with app.state.session_factory() as s:
        assert runtime.verify(s)["ok"] is True
    assert _last(db).policy_ids_json is None


def test_a_legacy_policy_cannot_be_published(app, client, login_as, db):
    from app.prompts.models import Policy

    csrf = login_as("system_admin")
    db.add(Policy(name="옛 정책", version=1, content_json='{"rules": {}}', kind="legacy", status="draft"))
    db.commit()
    row = db.execute(select(Policy).where(Policy.name == "옛 정책")).scalar_one()
    reply = client.post(f"/api/admin/policies/{row.id}/transition", json={"status": "published"},
                        headers=_h(csrf))
    assert reply.status_code == 422 and "옛 형식" in reply.json()["error"]["message"]
