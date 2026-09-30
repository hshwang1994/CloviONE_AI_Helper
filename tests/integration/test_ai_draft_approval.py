"""쓰기 승인 정책 — 작업 공간의 AI 초안을 문서로 저장하기 전에 승인을 받는다 (계획 3.9, D-519).

못박는 성질:
1. 쓰기 승인 정책이 발행돼 있으면 초안 저장은 문서 대신 승인 요청을 만든다. 초안 본문은 승인 요청이 아니라 AI 초안
   행에 있다.
2. 승인하면 요청한 사람의 이름으로 `source_type=AI` 문서가 생긴다. 거절하면 아무것도 생기지 않는다.
3. 승인 없이 저장할 수 있는 역할이면 곧바로 문서가 생긴다. 정책이 초안뿐이면(발행 전) 아무것도 걸리지 않는다.
4. 승인하는 순간 요청자의 권한을 다시 본다 - 그 사이 계정이 비활성이 되면 승인이 409 로 막히고 문서는 없다.
5. 초안 미리 보기는 요청한 사람과 그 승인을 볼 수 있는 사람만 연다. 다른 사람에게는 없는 것과 같다(404).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.ai.models import AiActionRequest
from app.knowledge.models import SOURCE_AI, Document
from tests.integration.test_ai_router import Generator, _install, seeded  # noqa: F401 - 픽스처를 이 모듈에 건다

pytestmark = pytest.mark.integration

REQUESTER = "draft-requester@goodmit.co.kr"
ADMIN = "draft-admin@goodmit.co.kr"


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _publish_approval_policy(client, login_as, *, auto_approve_roles=(), publish=True):
    csrf = login_as("system_admin", email=ADMIN)
    created = client.post("/api/admin/policies", json={
        "name": "AI 문서 승인", "kind": "approval", "applies_to": "workspace.draft",
        "content": {"write_requires_approval": True, "auto_approve_roles": list(auto_approve_roles)},
    }, headers=_h(csrf))
    assert created.status_code == 201, created.text
    policy = created.json()["item"]
    if publish:
        done = client.post(f"/api/admin/policies/{policy['id']}/transition", json={"status": "published"},
                           headers=_h(csrf))
        assert done.status_code == 200, done.text
    return policy


def _draft(client, csrf, space_id, title="승인할 초안"):
    reply = client.post("/api/ai/documents", json={
        "space_id": space_id, "title": title, "instruction": "연차 규정을 정리해 주세요",
    }, headers=_h(csrf))
    assert reply.status_code == 200, reply.text
    return reply.json()


def _documents(db) -> int:
    db.expire_all()
    return int(db.execute(select(func.count()).select_from(Document).where(Document.source_type == SOURCE_AI))
               .scalar_one())


def test_a_draft_under_the_policy_becomes_an_approval_and_then_a_document(client, app, login_as, db, seeded):
    _publish_approval_policy(client, login_as)
    _install(app, generate=Generator(text="승인 뒤 문서가 될 초안입니다."))
    csrf = login_as("user", email=REQUESTER)
    body = _draft(client, csrf, seeded["space"].id)
    assert body["document"] is None and body["approval"]["status"] == "pending"
    assert _documents(db) == 0

    db.expire_all()
    pending = db.get(AiActionRequest, body["approval"]["request_id"])
    assert pending.output_text == "승인 뒤 문서가 될 초안입니다." and pending.document_id is None

    admin = login_as("system_admin", email=ADMIN)
    approved = client.post(f"/api/admin/approvals/{body['approval']['id']}/approve", json={},
                           headers=_h(admin))
    assert approved.status_code == 200, approved.text
    db.expire_all()
    made = db.get(AiActionRequest, pending.id)
    document = db.get(Document, made.document_id)
    assert document.source_type == SOURCE_AI and document.title == "승인할 초안"
    from app.users.service import get_user_by_email

    assert document.created_by == get_user_by_email(db, REQUESTER).id, "문서는 요청한 사람의 이름으로 생긴다"


def test_a_rejected_draft_leaves_nothing(client, app, login_as, db, seeded):
    _publish_approval_policy(client, login_as)
    _install(app, generate=Generator())
    body = _draft(client, login_as("user", email=REQUESTER), seeded["space"].id)
    admin = login_as("system_admin", email=ADMIN)
    rejected = client.post(f"/api/admin/approvals/{body['approval']['id']}/reject", json={"comment": "아니요"},
                           headers=_h(admin))
    assert rejected.status_code == 200, rejected.text
    assert _documents(db) == 0


def test_an_auto_approved_role_and_an_unpublished_policy_write_directly(client, app, login_as, db, seeded):
    _publish_approval_policy(client, login_as, auto_approve_roles=["user"])
    _install(app, generate=Generator())
    body = _draft(client, login_as("user", email=REQUESTER), seeded["space"].id, title="바로 저장")
    assert body["document"] is not None and "approval" not in body
    assert _documents(db) == 1


def test_a_draft_policy_does_not_apply_yet(client, app, login_as, db, seeded):
    _publish_approval_policy(client, login_as, publish=False)
    _install(app, generate=Generator())
    body = _draft(client, login_as("user", email=REQUESTER), seeded["space"].id)
    assert body["document"] is not None, "발행하지 않은 정책이 걸렸다"


def test_approval_rechecks_the_requester_at_that_moment(client, app, login_as, db, seeded):
    from app.users.service import get_user_by_email

    _publish_approval_policy(client, login_as)
    _install(app, generate=Generator())
    body = _draft(client, login_as("user", email=REQUESTER), seeded["space"].id)
    requester = get_user_by_email(db, REQUESTER)
    requester.active = False
    db.commit()

    admin = login_as("system_admin", email=ADMIN)
    refused = client.post(f"/api/admin/approvals/{body['approval']['id']}/approve", json={}, headers=_h(admin))
    assert refused.status_code == 409, refused.text
    assert "활성" in refused.json()["error"]["message"]
    assert _documents(db) == 0
    approval = client.get(f"/api/admin/approvals/{body['approval']['id']}").json()["approval"]
    assert approval["status"] == "pending", "막힌 승인이 상태를 바꿨다"


def test_only_the_requester_and_approvers_can_read_the_draft(client, app, login_as, db, seeded):
    _publish_approval_policy(client, login_as)
    _install(app, generate=Generator(text="남에게 보이면 안 되는 초안"))
    body = _draft(client, login_as("user", email=REQUESTER), seeded["space"].id)
    path = f"/api/approvals/ai-drafts/{body['approval']['request_id']}"

    own = client.get(path)
    assert own.status_code == 200 and own.json()["item"]["output_text"] == "남에게 보이면 안 되는 초안"
    login_as("user", email="draft-stranger@goodmit.co.kr")
    assert client.get(path).status_code == 404
    login_as("system_admin", email=ADMIN)
    seen = client.get(path).json()["item"]
    assert (seen["approval_status"], seen["requester_name"]) == ("pending", "테스트 사용자")
