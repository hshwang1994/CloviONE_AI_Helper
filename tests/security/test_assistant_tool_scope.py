"""🔴 AI 도우미의 도구는 대화 주인이 화면에서 볼 수 있는 것만 읽는다 (D-535 · D-567, CLAUDE.md §9.3 — 면제 없음).

도구 열일곱 개를 모두 **실제 서비스로** 돌린다. 보는 사람은 A-1 부서의 일반 사용자(`a1`)이고, 남의 것은 B-1 부서(`b1`)와
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
    found = _run(app, world["a1"], "search_tickets", scope="team")
    titles = [item["title"] for item in _body(found)["items"]]
    assert "B1 연차 비밀 업무" not in titles
    # 다른 부서 사람의 이름으로 걸러도 그 사람에게 닿지 않는다 - 그 이름의 사람이 보는 범위에 없다.
    by_name = _run(app, world["a1"], "search_tickets", scope="team", assignee_name="b1")
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


# ── 새 도구 다섯 + 넓힌 도구 (D-567) ────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def wider(app, db, world, make_project, make_ticket, make_space, make_knowledge_document, fake_clock):
    """새 도구들의 범위 세계 — a1 의 것과 b1 의 것이 같은 모양으로 나란히 있다."""
    from app.knowledge.models import DocumentComment
    from app.notifications.models import Notification
    from app.tickets.models import TicketComment
    from app.work.models import Sprint, SprintDecision, TicketActivity

    now = fake_clock.now()
    a1, b1 = world["a1"], world["b1"]
    space_a1 = make_space(name="A1 내 공간", dept=D_A1)
    space_b1 = make_space(name="B1 남의 공간", dept=D_B1)
    my_doc = make_knowledge_document(space=space_a1, title="A1 내가 쓴 운영 문서", text="운영 절차입니다.",
                                     created_by=a1, updated_at=now)
    # a1 이 만들었지만 지금은 볼 수 없는 공간에 있는 문서 — 목록에도 수에도 들면 안 된다.
    stray = make_knowledge_document(space=space_b1, title="B1 공간의 a1 문서", text="옮겨 간 기밀 본문입니다.",
                                    created_by=a1, updated_at=now)
    same_a1 = make_project(name="공용 이름 프로젝트 가", dept=D_A1)
    same_a = make_project(name="공용 이름 프로젝트 나", dept="ot-dept-a00000")
    same_b1 = make_project(name="공용 이름 프로젝트 다", dept=D_B1)
    body_mine = make_ticket(project=world["projects"]["a1"], title="A1 본문 티켓", body="공개 본문 구절이 여기 있습니다.",
                            assignees=[a1.id])
    body_theirs = make_ticket(project=world["projects"]["b1"], title="B1 본문 티켓", body="비밀 본문 구절이 여기 있습니다.")
    db.add_all([
        Notification(user_id=a1.id, type="ticket_assigned", title="티켓 배정: a1@goodmit.co.kr 님 확인",
                     body="a1 알림 본문", related_object_type="ticket", related_object_id=world["mine"].id,
                     created_at=now),
        Notification(user_id=a1.id, type="account_locked", title="계정 잠김", body="잠긴 계정이 있습니다.",
                     related_object_type="user", related_object_id=b1.id, created_at=now, audience="admin"),
        Notification(user_id=a1.id, type="chat_mentioned", title="누군가 회원님을 언급했습니다.",
                     body="방 이름: 채팅 비밀 대화 내용", related_object_type="chat_mention", related_object_id="room-1",
                     created_at=now),
        Notification(user_id=b1.id, type="ticket_assigned", title="B1 사람의 알림", body="b1 알림 본문",
                     related_object_type="ticket", related_object_id=world["theirs"].id, created_at=now),
    ])
    db.add_all([
        TicketActivity(id=str(uuid.uuid4()), ticket_id=world["mine"].id, actor_user_id=a1.id, kind="status",
                       field="status", from_value="계획", to_value="진행", created_at=now),
        # 다른 부서 프로젝트의 티켓에 남긴 활동 — 그 티켓을 지금 볼 수 없으므로 나오면 안 된다.
        TicketActivity(id=str(uuid.uuid4()), ticket_id=world["theirs"].id, actor_user_id=a1.id, kind="status",
                       field="status", from_value="계획", to_value="완료", created_at=now),
        TicketComment(ticket_uid=world["theirs"].id, author_user_id=a1.id, body="B1 티켓에 단 a1 댓글", created_at=now),
        TicketComment(ticket_uid=world["mine"].id, author_user_id=a1.id, body="A1 티켓에 단 a1 댓글", created_at=now),
        DocumentComment(document_id=stray.id, author_user_id=a1.id, body="B1 문서에 단 a1 댓글", created_at=now),
    ])
    db.flush()
    sprint_b1 = Sprint(name="B1 회차", department_id=D_B1, starts_on=now.date(), ends_on=now.date() + timedelta(days=13),
                       state="active")
    sprint_a1 = Sprint(name="A1 회차", department_id=D_A1, starts_on=now.date(), ends_on=now.date() + timedelta(days=13),
                       state="active")
    db.add_all([sprint_b1, sprint_a1])
    db.flush()
    db.add_all([
        SprintDecision(sprint_id=sprint_b1.id, kind="decision", body="B1 회의의 비밀 결정"),
        SprintDecision(sprint_id=sprint_a1.id, kind="decision", body="A1 회의 결정"),
        # a1 회차의 결정이 a1 이 못 보는 티켓을 가리킨다 — 결정 글은 보이되 티켓 이름 · 경로는 안 나온다.
        SprintDecision(sprint_id=sprint_a1.id, kind="action", body="B1 티켓을 확인합니다", ticket_id=world["theirs"].id),
    ])
    db.commit()
    index_service.run_once(db, gateway=GATEWAY, limit=100)
    db.commit()
    return {**world, "my_doc": my_doc, "stray": stray, "same": (same_a1, same_a, same_b1),
            "body_mine": body_mine, "body_theirs": body_theirs, "sprint_a1": sprint_a1, "sprint_b1": sprint_b1}


def test_my_documents_counts_only_visible_documents_i_created(app, wider):
    found = _run(app, wider["a1"], "my_documents")
    body = _body(found)
    titles = [item["title"] for item in body["items"]]
    assert "A1 내가 쓴 운영 문서" in titles
    assert "B1 공간의 a1 문서" not in titles and "기밀 본문" not in found.content
    assert body["total"] == len(titles) == 1, "볼 수 없는 공간의 문서가 수에 들었다"
    edited = _body(_run(app, wider["a1"], "my_documents", view="edited"))
    assert [i["title"] for i in edited["items"]] == ["A1 내가 쓴 운영 문서"]
    _no_identity(found, wider["a1"], wider["b1"])


def test_project_arguments_out_of_scope_look_missing_and_candidates_stay_in_scope(app, wider):
    b1_project = wider["projects"]["b1"]
    for tool in ("my_documents", "search_documents", "project_activity", "get_project_summary", "my_work"):
        args = {"project": b1_project.id}
        if tool == "search_documents":
            args["query"] = "운영"
        if tool == "my_work":
            args["view"] = "assigned"
        by_id = _body(_run(app, wider["a1"], tool, **args))
        args["project"] = b1_project.code
        by_code = _body(_run(app, wider["a1"], tool, **args))
        args["project"] = str(uuid.uuid4())
        missing = _body(_run(app, wider["a1"], tool, **args))
        assert by_id == by_code == missing, tool
        assert by_id["error"] == "not_found", tool
    ambiguous = _body(_run(app, wider["a1"], "project_activity", project="공용 이름 프로젝트"))
    assert ambiguous["error"] == "ambiguous"
    names = {c["name"] for c in ambiguous["candidates"]}
    assert names == {"공용 이름 프로젝트 가", "공용 이름 프로젝트 나"}, "보이지 않는 프로젝트가 후보에 섰다"
    assert "공용 이름 프로젝트 다" not in json.dumps(ambiguous, ensure_ascii=False)


def test_project_activity_of_my_project_is_built_from_visible_records(app, wider):
    found = _run(app, wider["a1"], "project_activity", project=wider["projects"]["a1"].id)
    item = _body(found)["items"][0]
    assert item["name"] == "a1 프로젝트"
    assert sum(item["tickets"]["status_counts"].values()) == item["tickets"]["total"]
    assert "B1 본문 티켓" not in found.content and "B1 연차 비밀 업무" not in found.content
    _no_identity(found, wider["a1"], wider["b1"])


def test_ticket_body_search_never_reaches_another_departments_ticket(app, wider):
    theirs = _body(_run(app, wider["a1"], "search_tickets", scope="team", query="비밀 본문 구절", match_body=True,
                        include_done=True))
    assert theirs["items"] == [] and theirs["total"] == 0
    mine = _body(_run(app, wider["a1"], "search_tickets", scope="team", query="공개 본문 구절", match_body=True))
    assert [i["title"] for i in mine["items"]] == ["A1 본문 티켓"]
    title_only = _body(_run(app, wider["a1"], "search_tickets", scope="team", query="공개 본문 구절"))
    assert title_only["items"] == [], "본문 찾기를 켜지 않았는데 본문이 걸렸다"


def test_my_notifications_are_only_mine_without_emails_user_ids_or_chat_text(app, wider):
    found = _run(app, wider["a1"], "my_notifications")
    body = _body(found)
    titles = [i["title"] for i in body["items"]]
    assert "B1 사람의 알림" not in titles and "b1 알림 본문" not in found.content
    assert body["total"] == 3 and body["unread_total"] == 3
    assert "(이메일 가림)" in found.content
    assert "/users?id=" not in found.content, "사람을 가리키는 경로가 실렸다"
    assert "채팅 비밀 대화 내용" not in found.content, "팀 채팅 대화가 도구 결과에 실렸다"
    _no_identity(found, wider["a1"], wider["b1"])


def test_my_activity_drops_what_i_can_no_longer_see(app, wider):
    found = _run(app, wider["a1"], "my_activity", days=30)
    text = found.content
    assert "A1 연차 정리" in text and "A1 티켓에 단 a1 댓글" in text
    assert "B1 연차 비밀 업무" not in text, "볼 수 없는 티켓의 활동이 나왔다"
    assert "B1 티켓에 단 a1 댓글" not in text and "B1 문서에 단 a1 댓글" not in text
    assert "B1 공간의 a1 문서" not in text
    body = _body(found)
    assert body["total"] == sum(body["totals"].values())
    _no_identity(found, wider["a1"], wider["b1"])


def test_sprint_meetings_never_open_another_teams_sprint_or_hidden_tickets(app, wider):
    default = _run(app, wider["a1"], "sprint_meetings")
    body = _body(default)
    assert body["sprint"]["name"] == "A1 회차"
    assert "B1 회의의 비밀 결정" not in default.content
    assert {i["body"] for i in body["items"]} == {"A1 회의 결정", "B1 티켓을 확인합니다"}
    assert all(i["ticket"] is None for i in body["items"]), "볼 수 없는 티켓의 경로가 회의록에 실렸다"
    assert "B1 연차 비밀 업무" not in default.content and wider["theirs"].id not in default.content
    named = _body(_run(app, wider["a1"], "sprint_meetings", sprint="B1 회차"))
    assert named["error"] == "not_found"
    _no_identity(default, wider["a1"], wider["b1"])


def test_document_level_search_counts_only_visible_documents(app, wider):
    found = _run(app, wider["a1"], "search_documents", query="연차")
    body = _body(found)
    assert [i["title"] for i in body["items"]] == ["A1 연차 안내"]
    assert body["total"] == body["total_documents"] == 1, "다른 부서 문서가 전체 수에 들었다"
    assert "B1 연차 비밀" not in found.content


def test_search_documents_mine_counts_only_my_visible_documents(app, wider):
    """「내 문서 중 …」(`mine`) — 묻는 사람이 만든 문서로 좁히되 권한 절은 그대로 먼저 걸린다. 내가 만들었지만 지금 볼 수 없는
    공간의 문서는 목록에도 수에도 없고, 남이 만든 보이는 문서도 빠진다. 사람을 고르는 인자는 없다(켜고 끄기뿐)."""
    mine = _body(_run(app, wider["a1"], "search_documents", query="문서", mine=True))
    assert [i["title"] for i in mine["items"]] == ["A1 내가 쓴 운영 문서"]
    assert mine["total"] == mine["total_documents"] == 1, "볼 수 없는 공간의 내 문서가 수에 들었다"
    others = _body(_run(app, wider["a1"], "search_documents", query="연차", mine=True))
    assert others["items"] == [] and others["total"] == 0, "남이 만든 문서가 내 문서로 나왔다"
    assert [i["title"] for i in _body(_run(app, wider["a1"], "search_documents", query="연차"))["items"]] == ["A1 연차 안내"]
    with pytest.raises(Exception):
        catalog.TOOLS["search_documents"].args.model_validate({"query": "문서", "mine": True, "author_id": wider["b1"].id})
