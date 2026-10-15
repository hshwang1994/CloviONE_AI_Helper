"""🔴 AI 도우미의 도구는 읽기만 한다 — 구조로 (D-535).

  * 도구는 `SET TRANSACTION READ ONLY` 안에서 돈다: 쓰려는 도구는 DB 가 거절하고 결과는 `unavailable`, 아무것도 남지 않는다
  * 등록된 도구는 전부 읽기 전용이고 쓰기 동사 이름이 없다
  * 도구 패키지는 팀 채팅 메시지 · DM 모델을 들이지 않는다(다른 사람의 대화를 읽을 길 자체가 없다)
  * 어떤 도구 스키마에도 사람 · id · 이메일 인자가 없다
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.ai.assistant import catalog, results
from tests.fakes.assistant import tool_env
from tests.fixtures.org_tree import org_tree, people, resources  # noqa: F401 — fixture 재수출

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "app" / "ai" / "assistant"


class _NoArgs(BaseModel):
    pass


def test_a_tool_that_tries_to_write_is_refused_and_leaves_nothing(app, db, make_user):
    from app.notifications.models import Notification

    user = make_user("ro@goodmit.co.kr", role="user", display_name="읽기")
    db.commit()

    def writer(ctx, args):
        ctx.db.add(Notification(user_id=ctx.user.id, type="system", title="몰래 쓴 알림", body="",
                                created_at=ctx.now))
        ctx.db.flush()
        return results.ok("writer", [])

    rogue = catalog.Tool("writer", "쓰기", "쓰고 있습니다.", "시험용", _NoArgs, {}, writer)
    outcome = catalog.run(rogue, _NoArgs(), tool_env(app, user))
    assert (outcome.ok, '"unavailable"' in outcome.content) == (False, True)
    db.expire_all()
    left = db.execute(select(Notification).where(Notification.title == "몰래 쓴 알림")).scalars().all()
    assert left == []


def test_the_read_only_transaction_is_really_read_only(app, db, make_user):
    """도구가 받는 세션의 트랜잭션 자체가 읽기 전용이다 - 도구 코드의 선의에 기대지 않는다."""
    from sqlalchemy import text

    user = make_user("ro2@goodmit.co.kr", role="user", display_name="읽기2")
    db.commit()
    seen: dict = {}

    def probe(ctx, args):
        seen["mode"] = ctx.db.execute(text("SHOW transaction_read_only")).scalar_one()
        seen["timeout"] = ctx.db.execute(text("SHOW statement_timeout")).scalar_one()
        return results.ok("probe", [])

    catalog.run(catalog.Tool("probe", "확인", "확인합니다.", "시험용", _NoArgs, {}, probe), _NoArgs(),
                tool_env(app, user))
    assert seen == {"mode": "on", "timeout": "3s"}


def test_every_registered_tool_is_read_only_with_a_read_verb():
    write_verbs = ("create", "update", "delete", "remove", "send", "write", "approve", "reject", "assign", "set_")
    assert len(catalog.REGISTRY) == 17
    for tool in catalog.REGISTRY:
        assert tool.read_only is True
        assert not tool.name.startswith(write_verbs), tool.name


def test_no_tool_argument_can_name_a_person_or_an_id_of_one():
    banned = {"user_id", "user", "email", "owner", "owner_id", "requester_id", "assignee_id", "person_id", "as_user"}
    for tool in catalog.REGISTRY:
        names = set(tool.spec().parameters["properties"]) | set(tool.args.model_fields)
        assert not names & banned, (tool.name, names & banned)


def test_the_assistant_package_does_not_import_chat_message_models():
    """팀 채팅 메시지 · DM, 다른 사람의 AI 대화는 도구로 열지 않는다 - 들일 길 자체를 두지 않는다."""
    forbidden = ("app.team_chat.models", "app.chat.models", "app.dm")
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = ",".join(alias.name for alias in node.names)
            if module and any(module.startswith(name) for name in forbidden):
                pytest.fail(f"{path.name} 가 {module} 를 들인다")
        source = path.read_text(encoding="utf-8")
        assert "TeamChatMessage" not in source and "ChatMessage(" not in source


@pytest.fixture()
def reader_world(db, people, resources, make_ticket, make_space, make_knowledge_document, fake_clock):
    from tests.fixtures.org_tree import D_A1

    a1 = people["a1"]
    make_ticket(project=resources["projects"]["a1"], title="읽기 시험 티켓", assignees=[a1.id], body="본문 구절입니다.")
    space = make_space(name="읽기 시험 공간", dept=D_A1)
    make_knowledge_document(space=space, title="읽기 시험 문서", text="운영 절차를 적습니다.", created_by=a1,
                            updated_at=fake_clock.now())
    db.commit()
    return {"a1": a1, "project": resources["projects"]["a1"]}


@pytest.mark.parametrize("name,arguments", [
    ("my_documents", {"view": "edited", "sort": "title", "updated_within_days": 30}),
    ("search_documents", {"query": "운영 절차", "offset": 0}),
    ("my_work", {"view": "assigned", "sort": "completed", "statuses": ["진행", "완료"], "updated_within_days": 30}),
    ("search_tickets", {"scope": "team", "query": "본문 구절", "match_body": True, "completed_within_days": 30,
                        "sort": "updated"}),
    ("project_activity", {"project": "PROJECT", "days": 60}),
    ("my_notifications", {"unread_only": True, "days": 30}),
    ("my_activity", {"days": 30, "kinds": ["tickets", "documents", "comments"]}),
    ("sprint_meetings", {}),
])
def test_every_new_tool_completes_inside_the_read_only_transaction(app, reader_world, name, arguments):
    """새 도구가 읽기 전용 세션에서 끝까지 돈다 — 숨은 쓰기(열람 기록 같은)가 있으면 DB 가 거절해 `unavailable` 이 된다."""
    args = {k: (reader_world["project"].id if v == "PROJECT" else v) for k, v in arguments.items()}
    tool = catalog.TOOLS[name]
    outcome = catalog.run(tool, tool.args.model_validate(args), tool_env(app, reader_world["a1"]))
    assert outcome.ok, outcome.content
