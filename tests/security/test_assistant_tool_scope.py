"""🔴 AI 도우미의 도구는 대화 주인이 화면에서 볼 수 있는 것만 읽는다 (D-535, CLAUDE.md §9.3 — 면제 없음).

도구 열두 개를 모두 **실제 서비스로** 돌린다. 보는 사람은 A-1 부서의 일반 사용자(`a1`)이고, 남의 것은 B-1 부서(`b1`)와
다른 조직의 것이다. 확인 지점은 **도구가 돌려준 결과 JSON** 이다 - 모델에 실리는 글이 바로 그것이다(D-202 의 문맥 단계).

  * 목록 도구: 범위 밖 항목이 결과에 없다
  * 단건 도구: 범위 밖 대상은 **없는 대상과 같은 오류 · 같은 문장**이다(존재를 흘리지 않는다)
  * 어느 결과에도 이메일 · 역할 · 내부 사용자 id 가 없다
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

from app.ai.assistant import catalog
from app.ai.gateway import contract
from app.ai.index import service as index_service
from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    D_A1,
    D_B1,
    org_tree,
    people,
    resources,
)

pytestmark = pytest.mark.integration

GATEWAY = contract.Gateway(enabled=True, embed_adapter=None)


@pytest.fixture()
def world(app, db, people, resources, make_ticket, make_space, make_knowledge_document, make_user, fake_clock):
    from app.approvals.models import APPROVAL_PENDING, Approval
    from app.org.models import Organization
    from app.search.indexer import reindex_all

    now = fake_clock.now()
    a1, b1 = people["a1"], people["b1"]
    projects = resources["projects"]
    mine = make_ticket(project=projects["a1"], title="A1 연차 정리", assignees=[a1.id], due=now.date().isoformat())
    theirs = make_ticket(project=projects["b1"], title="B1 연차 비밀 업무", assignees=[b1.id])
    space_a1 = make_space(name="A1 공간", dept=D_A1)
    space_b1 = make_space(name="B1 공간", dept=D_B1)
    doc_a1 = make_knowledge_document(space=space_a1, title="A1 연차 안내", text="연차 신청은 사흘 전에 합니다.",
                                     updated_at=now)
    doc_b1 = make_knowledge_document(space=space_b1, title="B1 연차 비밀", text="연차 보상 비밀 조항입니다.",
                                     updated_at=now)
    other_org = Organization(slug="tool-org-b", name="다른조직")
    db.add(other_org)
    db.flush()
    stranger = make_user("stranger@goodmit.co.kr", role="user", display_name="연차담당 외부인")
    stranger.org_id = other_org.id
    db.add(Approval(
        id=str(uuid.uuid4()), request_type="schedule.enable", object_type="schedule", object_id="s-1",
        requested_by=b1.id, status=APPROVAL_PENDING, request_payload_json="{}", requested_at=now,
        expires_at=now + timedelta(hours=48),
    ))
    db.commit()
    index_service.run_once(db, gateway=GATEWAY, limit=100)
    reindex_all(db, tickets=app.state.repositories.tickets, now=now)
    db.commit()
    return {"a1": a1, "b1": b1, "mine": mine, "theirs": theirs, "doc_a1": doc_a1, "doc_b1": doc_b1,
            "projects": projects, "stranger": stranger}


def _run(app, user, name, **args):
    tool = catalog.TOOLS[name]
    env = catalog.ToolEnv(
        session_factory=app.state.session_factory, user_id=user.id, settings=app.state.settings,
        outbound=app.state.outbound_client, gateway=GATEWAY, settings_cache=app.state.settings_cache,
        now=app.state.clock.now(),
    )
    return catalog.run(tool, tool.args.model_validate(args), env)


def _body(execution) -> dict:
    return json.loads(execution.content)


def _no_identity(execution, *people_rows) -> None:
    """결과에 이메일 · 역할 · 내부 사용자 id 가 없다."""
    text = execution.content
    assert "@goodmit.co.kr" not in text
    assert '"role"' not in text and "system_admin" not in text
    for person in people_rows:
        assert person.id not in text


# ── 목록 도구 ────────────────────────────────────────────────────────────────


def test_document_search_never_returns_another_departments_document(app, world):
    found = _run(app, world["a1"], "search_documents", query="연차")
    titles = [item["title"] for item in _body(found)["items"]]
    assert "A1 연차 안내" in titles, "검색이 돌지 않으면 이 시험은 아무것도 증명하지 못한다"
    assert "B1 연차 비밀" not in titles
    assert "비밀 조항" not in found.content
    _no_identity(found, world["a1"], world["b1"])


def test_workspace_search_stays_inside_the_scope(app, world):
    found = _run(app, world["a1"], "search_workspace", query="연차", kinds=None)
    titles = [item["title"] for item in _body(found)["items"]]
    assert "A1 연차 정리" in titles
    assert "B1 연차 비밀 업무" not in titles and "B1 연차 비밀" not in titles
    _no_identity(found, world["a1"], world["b1"])


def test_my_work_is_only_my_own_tickets(app, world):
    found = _run(app, world["a1"], "my_work", view="assigned", include_done=None)
    titles = [item["title"] for item in _body(found)["items"]]
    assert titles == ["A1 연차 정리"]
    _no_identity(found, world["a1"], world["b1"])


def test_team_tickets_do_not_include_another_departments(app, world):
    found = _run(app, world["a1"], "search_tickets", scope="team", query=None, status=None, due=None, project=None,
                 assignee_name=None)
    titles = [item["title"] for item in _body(found)["items"]]
    assert "B1 연차 비밀 업무" not in titles
    # 다른 부서 사람의 이름으로 걸러도 그 사람에게 닿지 않는다 - 그 이름의 사람이 보는 범위에 없다.
    by_name = _run(app, world["a1"], "search_tickets", scope="team", query=None, status=None, due=None,
                   project=None, assignee_name="b1")
    assert _body(by_name)["ok"] is False and _body(by_name)["error"] == "not_found"


def test_projects_out_of_scope_are_absent(app, world):
    found = _run(app, world["a1"], "search_projects", scope="all", query=None, status=None, trouble_only=None)
    names = [item["name"] for item in _body(found)["items"]]
    assert "a1 프로젝트" in names
    assert "b1 프로젝트" not in names


def test_my_approvals_do_not_show_other_peoples_requests(app, world):
    todo = _run(app, world["a1"], "my_approvals", box="todo")
    assert _body(todo)["items"] == []
    requested = _run(app, world["a1"], "my_approvals", box="requested")
    assert _body(requested)["items"] == []
    _no_identity(todo, world["a1"], world["b1"])


def test_find_people_stays_inside_the_organization(app, world):
    found = _run(app, world["a1"], "find_people", query="연차담당")
    assert _body(found)["items"] == []
    same_org = _run(app, world["a1"], "find_people", query="b1")
    assert [p["name"] for p in _body(same_org)["items"]] == ["b1"]
    assert set(_body(same_org)["items"][0]) == {"name", "department", "title"}
    _no_identity(same_org, world["a1"], world["b1"], world["stranger"])


def test_recent_changes_list_only_visible_documents(app, world):
    found = _run(app, world["a1"], "recent_changes", days=7, kinds=["documents"])
    titles = [item["title"] for item in _body(found)["items"]]
    assert "A1 연차 안내" in titles
    assert "B1 연차 비밀" not in titles


def test_the_work_summary_is_built_from_my_scope(app, world):
    found = _run(app, world["a1"], "work_summary", period="today")
    assert "B1 연차 비밀 업무" not in found.content
    _no_identity(found, world["b1"])


# ── 단건 도구: 범위 밖 = 없는 것 (같은 문장) ──────────────────────────────────


def test_reading_another_departments_ticket_looks_exactly_like_a_missing_one(app, world):
    hidden = _run(app, world["a1"], "get_ticket", key=world["theirs"].id)
    missing = _run(app, world["a1"], "get_ticket", key=str(uuid.uuid4()))
    junk = _run(app, world["a1"], "get_ticket", key="ZZZZZZ-999")
    assert _body(hidden) == _body(missing) == _body(junk)
    assert _body(hidden)["error"] == "not_found"
    mine = _run(app, world["a1"], "get_ticket", key=world["mine"].id)
    assert _body(mine)["items"][0]["title"] == "A1 연차 정리"


def test_reading_another_departments_document_looks_exactly_like_a_missing_one(app, world):
    hidden = _run(app, world["a1"], "get_document", ref=world["doc_b1"].id)
    missing = _run(app, world["a1"], "get_document", ref=str(uuid.uuid4()))
    assert _body(hidden) == _body(missing)
    assert "비밀 조항" not in hidden.content
    mine = _run(app, world["a1"], "get_document", ref=world["doc_a1"].id)
    assert "사흘 전에" in _body(mine)["items"][0]["text"]


def test_another_departments_project_summary_looks_exactly_like_a_missing_one(app, world):
    hidden = _run(app, world["a1"], "get_project_summary", project=world["projects"]["b1"].id)
    by_name = _run(app, world["a1"], "get_project_summary", project="b1 프로젝트")
    missing = _run(app, world["a1"], "get_project_summary", project=str(uuid.uuid4()))
    assert _body(hidden) == _body(by_name) == _body(missing)
    mine = _run(app, world["a1"], "get_project_summary", project=world["projects"]["a1"].id)
    assert _body(mine)["items"][0]["name"] == "a1 프로젝트"


def test_a_user_who_lost_access_gets_nothing(app, world, db):
    """대화 주인이 보관되면 도구는 아무것도 읽지 않는다(도구마다 사람을 다시 읽는다)."""
    world["a1"].archived_at = app.state.clock.now()
    db.commit()
    found = _run(app, world["a1"], "my_work", view="assigned", include_done=None)
    assert _body(found)["error"] == "unavailable"
