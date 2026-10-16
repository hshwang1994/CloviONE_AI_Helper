# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""AI 도우미의 세기 계약 — `total` 은 권한 안의 정확한 전체 수이고 쪽은 안정하다 (D-567).

「문서 6개」 같은 틀린 수의 원인은 둘이었다: 문서 검색이 조각을 돌려주고 그 수를 `total` 로 냈다, 그리고 목록 도구가 한 쪽의 길이를
전체 수처럼 보였다. 여기서 지키는 것:

* 목록 도구의 `total` 은 화면과 같은 함수 · 같은 조건의 정확한 수다 — 「내 문서」는 문서 화면의 `mine=true`, 「내 업무」는 「내 티켓」,
  알림은 벨의 숫자와 같다
* `offset` 으로 넘긴 쪽은 겹치지도 빠지지도 않는다
* 문서 검색은 문서 하나에 한 줄이고 `total_documents` 가 문서 수다. 세지 못하면(시간 초과) `total` 은 `null` 이고 그렇다고 말한다
* 프로젝트 진행 현황의 상태별 수는 끝낸 것 · 취소한 것까지 전 상태이고 휴지통은 빠진다
* 결과 한 칸은 런타임의 칸 상한 안이다(잘린 JSON 을 모델에 주지 않는다)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.ai import runtime as runtime_mod
from app.ai.assistant import catalog, results
from app.ai.gateway import contract
from app.ai.index import service as index_service
from tests.fixtures.org_tree import D_A1, org_tree, people, resources  # noqa: F401 — fixture 재수출

pytestmark = pytest.mark.integration

GATEWAY = contract.Gateway(enabled=True, embed_adapter=None)
PASSWORD_LOGIN_EMAIL = "a1@goodmit.co.kr"


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


def _index(db):
    index_service.run_once(db, gateway=GATEWAY, limit=200)
    db.commit()


# ── 내 문서 ──────────────────────────────────────────────────────────────────


def test_my_documents_total_matches_the_documents_screen_and_pages_are_stable(
    app, db, client, login_as, people, make_space, make_knowledge_document, fake_clock,
):
    a1 = people["a1"]
    space = make_space(name="A1 문서함", dept=D_A1)
    now = fake_clock.now()
    for index in range(25):
        make_knowledge_document(space=space, title=f"내 문서 {index:02d}", text=f"본문 {index}", created_by=a1,
                                updated_at=now - timedelta(minutes=index % 7))
    make_knowledge_document(space=space, title="남이 쓴 문서", text="본문", created_by=people["a2"], updated_at=now)
    db.commit()

    pages = [_body(_run(app, a1, "my_documents", offset=offset)) for offset in (0, 10, 20)]
    assert [p["total"] for p in pages] == [25, 25, 25]
    assert [p["returned"] for p in pages] == [10, 10, 5]
    assert [p["truncated"] for p in pages] == [True, True, False]
    assert [p["offset"] for p in pages] == [0, 10, 20]
    seen = [item["ref"] for page in pages for item in page["items"]]
    assert len(seen) == len(set(seen)) == 25, "쪽 사이에서 문서가 겹치거나 빠졌다"
    assert "남이 쓴 문서" not in json.dumps(pages, ensure_ascii=False)
    first = pages[0]["items"][0]
    assert set(first) >= {"ref", "title", "author", "updated_at", "created_at", "space", "project", "excerpt",
                          "comments", "route"}
    assert first["author"] == "a1" and first["route"].startswith("/knowledge/")

    login_as("user", email=PASSWORD_LOGIN_EMAIL)
    screen = client.get("/api/knowledge/documents", params={"mine": "true", "limit": 1}).json()
    assert screen["total"] == pages[0]["total"], "도구의 「내 문서」 수가 문서 화면의 내 문서 수와 다르다"


def test_edited_view_and_the_migrated_author_note(app, db, people, make_space, make_knowledge_document, fake_clock):
    from app.knowledge import versions
    from app.knowledge.models import Document

    a1, a2 = people["a1"], people["a2"]
    space = make_space(name="A1 함께 쓰는 곳", dept="ot-dept-a00000")
    theirs = make_knowledge_document(space=space, title="a2 가 만들고 a1 이 고친 문서", text="처음 글", created_by=a2)
    versions.snapshot(db, theirs, {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "a1 이 고친 글"}]}]}, author_id=a1.id)
    mine = make_knowledge_document(space=space, title="a1 이 만든 문서", text="글", created_by=a1)
    migrated = make_knowledge_document(space=space, title="옮겨 온 옛 문서", text="옛 글")
    migrated_row = db.get(Document, migrated.id)
    migrated_row.legacy_author_name = "a1"
    db.commit()

    authored = _body(_run(app, a1, "my_documents"))
    assert [i["title"] for i in authored["items"]] == ["a1 이 만든 문서"] and authored["total"] == 1
    assert "이관 문서 1건은 이 수에 넣지 않았습니다" in authored["note"]
    edited = _body(_run(app, a1, "my_documents", view="edited", sort="title"))
    assert {i["title"] for i in edited["items"]} == {"a1 이 만든 문서", "a2 가 만들고 a1 이 고친 문서"}
    assert edited["total"] == 2
    assert mine.id in {i["ref"] for i in edited["items"]}


# ── 문서 검색은 문서 단위 ────────────────────────────────────────────────────


def test_one_document_with_many_chunks_is_one_result_and_one_document(app, db, people, make_space,
                                                                     make_knowledge_document):
    space = make_space(name="A1 규정", dept=D_A1)
    paragraphs = [f"연차 규정 {n}절은 " + ("연차를 쓰는 순서와 절차를 자세히 설명합니다. " * 30) for n in range(5)]
    body = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs]}
    document = make_knowledge_document(space=space, title="연차 규정 전문", body=body)
    db.commit()
    _index(db)
    from sqlalchemy import func, select

    from app.ai.models import DocumentChunk

    chunks = db.execute(select(func.count()).where(DocumentChunk.document_id == document.id)).scalar_one()
    assert chunks >= 3, "반례가 서지 않는다 — 조각이 여럿이어야 문서 단위를 가른다"

    found = _body(_run(app, people["a1"], "search_documents", query="연차 절차"))
    assert [i["ref"] for i in found["items"]] == [document.id]
    assert found["total"] == found["total_documents"] == 1 and found["returned"] == 1
    assert found["truncated"] is False


def test_document_search_pages_by_document(app, db, people, make_space, make_knowledge_document):
    space = make_space(name="A1 보안 문서함", dept=D_A1)
    for index in range(9):
        make_knowledge_document(space=space, title=f"보안 점검 기록 {index}", text=f"보안 점검 {index}회차 결과입니다.")
    db.commit()
    _index(db)
    first = _body(_run(app, people["a1"], "search_documents", query="보안 점검"))
    assert first["total"] == 9 and first["returned"] == 8 and first["truncated"] is True
    second = _body(_run(app, people["a1"], "search_documents", query="보안 점검", offset=8))
    assert second["returned"] == 1 and second["offset"] == 8 and second["truncated"] is False
    refs = [i["ref"] for i in first["items"]] + [i["ref"] for i in second["items"]]
    assert len(set(refs)) == 9
    assert first["keywords"] == ["보안", "점검"] and "documents_with_every_word" in first


def test_a_count_that_times_out_is_null_and_says_so(app, db, people, make_space, make_knowledge_document, monkeypatch):
    """세기가 문 상한(3초)에 걸리면 `total` 은 `null` 이다 — 보인 수로 꾸미지 않는다. 목록은 그대로 나가고 세션은 산다."""
    from sqlalchemy import func

    from app.ai.retrieval import query as query_mod

    space = make_space(name="A1 느린 문서함", dept=D_A1)
    make_knowledge_document(space=space, title="휴가 안내", text="휴가 신청은 사흘 전에 합니다.")
    db.commit()
    _index(db)
    monkeypatch.setattr(query_mod, "trgm_condition_for",
                        lambda *a, **k: func.pg_sleep(5).is_not(None))
    found = _body(_run(app, people["a1"], "search_documents", query="휴가 신청"))
    assert found["ok"] is True
    assert found["total"] is None and found["total_documents"] is None
    assert results.TOTAL_UNKNOWN_NOTE in found["note"]
    assert [i["title"] for i in found["items"]] == ["휴가 안내"]


# ── 티켓 ─────────────────────────────────────────────────────────────────────


@pytest.fixture()
def tickets_world(db, people, resources, make_ticket, make_project, fake_clock):
    from app.trash.models import TrashItem

    now = fake_clock.now()
    a1 = people["a1"]
    project = resources["projects"]["a1"]
    other = make_project(name="a1 두 번째 프로젝트", dept=D_A1)
    rows = {
        "plan": make_ticket(project=project, title="계획 티켓", status="계획", assignees=[a1.id], body="평범한 본문"),
        "doing": make_ticket(project=project, title="진행 티켓", status="진행", assignees=[a1.id]),
        "done": make_ticket(project=project, title="끝낸 티켓", status="완료", assignees=[a1.id]),
        "cancel": make_ticket(project=project, title="취소 티켓", status="취소", assignees=[a1.id]),
        "hold": make_ticket(project=project, title="보류 티켓", status="보류"),
        "trashed": make_ticket(project=project, title="버린 티켓", status="진행", assignees=[a1.id]),
        "elsewhere": make_ticket(project=other, title="다른 프로젝트 티켓", status="진행", assignees=[a1.id]),
    }
    rows["done"].completed_at = now - timedelta(days=2)
    rows["cancel"].completed_at = now - timedelta(days=45)
    db.add(TrashItem(item_type="ticket", notion_page_id=rows["trashed"].id, title="버린 티켓",
                     deleted_by_user_id=a1.id, deleted_by_name="a1", deleted_at=now))
    db.commit()
    return {"rows": rows, "project": project, "other": other, "a1": a1}


def test_ticket_search_counts_every_status_when_asked(app, tickets_world):
    a1 = tickets_world["a1"]
    active = _body(_run(app, a1, "search_tickets", scope="team", project=tickets_world["project"].id))
    assert {i["title"] for i in active["items"]} == {"계획 티켓", "진행 티켓", "보류 티켓"}
    assert active["total"] == 3, "휴지통 티켓이나 끝난 티켓이 미완료 수에 들었다"
    everything = _body(_run(app, a1, "search_tickets", scope="team", project=tickets_world["project"].id,
                            include_done=True))
    assert everything["total"] == 5
    closed = _body(_run(app, a1, "search_tickets", scope="team", statuses=["완료", "취소"],
                        project=tickets_world["project"].id))
    assert {i["title"] for i in closed["items"]} == {"끝낸 티켓", "취소 티켓"} and closed["total"] == 2
    recent = _body(_run(app, a1, "search_tickets", scope="team", completed_within_days=7,
                        project=tickets_world["project"].id))
    assert [i["title"] for i in recent["items"]] == ["끝낸 티켓"] and recent["total"] == 1
    ordered = _body(_run(app, a1, "search_tickets", scope="team", include_done=True, sort="completed",
                         project=tickets_world["project"].id))
    assert [i["title"] for i in ordered["items"]][:2] == ["끝낸 티켓", "취소 티켓"]
    page = _body(_run(app, a1, "search_tickets", scope="team", include_done=True, sort="created",
                      project=tickets_world["project"].id, offset=4))
    assert page["returned"] == 1 and page["offset"] == 4 and page["truncated"] is False


def test_my_work_with_a_project_equals_the_my_tickets_screen(app, client, login_as, tickets_world):
    a1 = tickets_world["a1"]
    project = tickets_world["project"]
    tool = _body(_run(app, a1, "my_work", view="assigned", include_done=True, project=project.id))
    login_as("user", email=PASSWORD_LOGIN_EMAIL)
    screen = client.get("/api/tickets/mine", params={"project_id": project.id}).json()
    assert tool["total"] == screen["total"] == 4
    open_only = _body(_run(app, a1, "my_work", view="assigned", project=project.id))
    assert {i["title"] for i in open_only["items"]} == {"계획 티켓", "진행 티켓"} and open_only["total"] == 2
    both = _body(_run(app, a1, "my_work", view="assigned"))
    assert both["total"] == 3, "다른 프로젝트의 미완료 티켓까지 세야 한다"


def test_this_week_on_a_monday_dawn_is_the_same_week_for_the_screen_and_the_tool(app, db, client, login_as, people, resources,
                                                                                 make_ticket, fake_clock):
    """KST 월요일 05:00(= UTC 일요일 20:00)에도 「내 티켓」의 이번 주와 AI `my_work` 의 이번 주가 같은 달력 주다(P-139).
    화면은 UTC 날짜로 주를 나눠 이 시각에 지난주를 「이번 주」로 셌다."""
    a1 = people["a1"]
    project = resources["projects"]["a1"]
    fake_clock.advance(seconds=-28 * 3600)  # 2026-07-14 00:00 UTC → 2026-07-12(일) 20:00 UTC = 2026-07-13(월) 05:00 KST
    make_ticket(project=project, title="지난 일요일 마감", status="진행", assignees=[a1.id], due="2026-07-12")
    make_ticket(project=project, title="월요일 마감", status="진행", assignees=[a1.id], due="2026-07-13")
    make_ticket(project=project, title="이번 주 일요일 마감", status="진행", assignees=[a1.id], due="2026-07-19")
    db.commit()
    tool = _body(_run(app, a1, "my_work", view="due_this_week"))
    login_as("user", email=PASSWORD_LOGIN_EMAIL)
    screen = client.get("/api/tickets/mine", params={"due": "this_week"}).json()
    expected = {"월요일 마감", "이번 주 일요일 마감"}
    assert {i["title"] for i in tool["items"]} == expected
    assert {t["title"] for t in screen["items"]} == expected, "화면이 지난주를 이번 주로 셌다"


def test_my_work_completed_this_week_is_the_kst_calendar_week(app, db, people, resources, make_ticket, fake_clock):
    """「이번 주에 끝낸 내 티켓」은 월요일 0시(KST)부터 끝낸 것이다. 업무 요약의 「이번 주 완료」는 이번 주가 마감인 일 중
    끝낸 것이라 다른 수다 — 랩(2026-10-15)에서 이번 주에 하나 끝냈는데 요약을 보고 0건이라고 답했다."""
    a1 = people["a1"]
    project = resources["projects"]["a1"]
    now = fake_clock.now()  # 2026-07-14(화) 00:00 UTC = 09:00 KST
    rows = {
        "monday": make_ticket(project=project, title="월요일 새벽 끝냄", status="완료", assignees=[a1.id]),
        "today": make_ticket(project=project, title="오늘 끝냄", status="완료", assignees=[a1.id], due="2026-08-30"),
        "sunday": make_ticket(project=project, title="지난 일요일 밤 끝냄", status="완료", assignees=[a1.id]),
        "open": make_ticket(project=project, title="아직 진행", status="진행", assignees=[a1.id]),
    }
    rows["monday"].completed_at = datetime(2026, 7, 12, 15, 30)   # 월 00:30 KST
    rows["today"].completed_at = now - timedelta(hours=1)          # 화 08:00 KST — 마감은 다음 달이다
    rows["sunday"].completed_at = datetime(2026, 7, 12, 14, 30)   # 일 23:30 KST — 지난주
    db.commit()
    week = _body(_run(app, a1, "my_work", view="assigned", completed="this_week"))
    assert {i["title"] for i in week["items"]} == {"월요일 새벽 끝냄", "오늘 끝냄"} and week["total"] == 2
    recent = _body(_run(app, a1, "my_work", view="assigned", completed_within_days=1))
    assert {i["title"] for i in recent["items"]} == {"오늘 끝냄"}
    both = _body(_run(app, a1, "my_work", view="assigned", completed="this_week", completed_within_days=30))
    assert both["total"] == 2, "둘 다 주면 더 좁은 쪽이다"


def test_project_activity_counts_every_status_and_skips_the_trash(app, db, tickets_world, make_space,
                                                                  make_knowledge_document, fake_clock):
    from app.knowledge import service as knowledge
    from app.projects.models import ProjectWeeklyReport

    project = tickets_world["project"]
    space = make_space(name="a1 프로젝트 문서", project=project)
    for index in range(8):
        make_knowledge_document(space=space, title=f"프로젝트 문서 {index}", text="설계 내용입니다.")
    db.add(ProjectWeeklyReport(project_id=project.id, week_of=fake_clock.now().date(), summary_md="주간 요약. " * 400))
    db.commit()
    found = _run(app, tickets_world["a1"], "project_activity", project=project.code)
    item = _body(found)["items"][0]
    counts = item["tickets"]["status_counts"]
    assert counts == {"계획": 1, "보류": 1, "완료": 1, "진행": 1, "취소": 1}
    assert sum(counts.values()) == item["tickets"]["total"] == 5, "휴지통 티켓이 진행 현황에 들었다"
    assert item["tickets"]["open"] == 3
    assert [t["title"] for t in item["recent_completed"]] == ["끝낸 티켓"]
    _rows, doc_total = knowledge.list_documents(db, tickets_world["a1"], project_id=project.id, limit=1)
    assert item["documents"]["total"] == doc_total == 8 and len(item["documents"]["items"]) == 6
    assert len(item["weekly_reports"][0]["summary"]) <= 1200
    assert len(found.content) <= runtime_mod.TOOL_RESULT_CHARS, "결과가 런타임의 칸 상한을 넘어 잘린다"


# ── 알림 · 활동 ──────────────────────────────────────────────────────────────


def test_unread_total_matches_the_bell(app, db, client, login_as, people, fake_clock):
    from app.notifications.models import Notification

    a1 = people["a1"]
    now = fake_clock.now()
    db.add_all([
        Notification(user_id=a1.id, type="ticket_assigned", title=f"알림 {i}", created_at=now - timedelta(hours=i),
                     read_at=now if i == 0 else None)
        for i in range(13)
    ])
    db.commit()
    first = _body(_run(app, a1, "my_notifications"))
    assert first["total"] == 13 and first["returned"] == 10 and first["truncated"] is True
    assert [i["title"] for i in first["items"]][:2] == ["알림 0", "알림 1"]
    unread = _body(_run(app, a1, "my_notifications", unread_only=True))
    assert unread["total"] == 12
    login_as("user", email=PASSWORD_LOGIN_EMAIL)
    bell = client.get("/api/notifications/unread-count").json()
    assert first["unread_total"] == unread["unread_total"] == bell["unread"] == 12


def test_my_activity_is_newest_first_inside_the_window(app, db, people, resources, make_ticket, fake_clock):
    from app.work.models import TicketActivity

    a1 = people["a1"]
    now = fake_clock.now()
    ticket = make_ticket(project=resources["projects"]["a1"], title="활동 티켓", assignees=[a1.id])
    for days, kind in ((1, "status"), (3, "created"), (20, "status")):
        db.add(TicketActivity(id=str(uuid.uuid4()), ticket_id=ticket.id, actor_user_id=a1.id, kind=kind,
                              field="status" if kind == "status" else None, from_value="계획", to_value="진행",
                              created_at=now - timedelta(days=days)))
    db.commit()
    week = _body(_run(app, a1, "my_activity", days=7, kinds=["tickets"]))
    assert week["total"] == 2 and week["totals"] == {"tickets": 2}
    assert [i["action"] for i in week["items"]] == ["상태를 계획에서 진행으로 바꿨습니다.", "티켓을 추가했습니다."]
    month = _body(_run(app, a1, "my_activity", days=30, kinds=["tickets"]))
    assert month["total"] == 3


# ── 칸 상한 ──────────────────────────────────────────────────────────────────


def test_a_full_document_search_page_fits_the_runtime_cell(app, db, people, make_space, make_knowledge_document):
    space = make_space(name="A1 긴 문서함", dept=D_A1)
    for index in range(10):
        make_knowledge_document(space=space, title=f"긴 운영 문서 {index}",
                                text=("운영 절차를 길게 설명하는 문장입니다. " * 60) + f" {index}")
    db.commit()
    _index(db)
    found = _run(app, people["a1"], "search_documents", query="운영 절차")
    body = _body(found)
    assert body["returned"] == 8
    assert len(found.content) <= runtime_mod.TOOL_RESULT_CHARS, len(found.content)
    assert all(len(item["text"]) >= 120 for item in body["items"]), "발췌를 바닥 아래로 줄였다"


def test_the_result_budget_is_below_the_runtime_cell():
    from app.ai.assistant import readers

    assert readers.RESULT_BUDGET_CHARS < runtime_mod.TOOL_RESULT_CHARS


def test_get_document_carries_people_place_tags_and_comments_inside_the_cell(app, db, people, make_space,
                                                                           make_knowledge_document, fake_clock):
    from app.knowledge.models import DocumentComment

    a1, a2 = people["a1"], people["a2"]
    space = make_space(name="A 공용 문서함", dept="ot-dept-a00000")
    long_text = "\n\n".join(f"{n}번 문단은 운영 절차의 한 부분을 길게 설명합니다. " * 12 for n in range(30))
    document = make_knowledge_document(space=space, title="긴 운영 문서", text=long_text, created_by=a2,
                                       tag_names=["운영", "절차"])
    now = fake_clock.now()
    for n in range(5):
        db.add(DocumentComment(document_id=document.id, author_user_id=a1.id, body=f"{n}번째 의견입니다. " * 40,
                               created_at=now - timedelta(minutes=n)))
    db.add(DocumentComment(document_id=document.id, author_user_id=a1.id, body="지운 의견", created_at=now,
                           deleted_at=now))
    db.commit()
    found = _run(app, a1, "get_document", ref=document.id)
    item = _body(found)["items"][0]
    assert item["author"] == "a2" and item["where"] == "A 공용 문서함"
    assert set(item["tags"]) == {"운영", "절차"}
    assert item["comments_total"] == 5 and len(item["recent_comments"]) == 3
    assert item["recent_comments"][0]["text"].startswith("0번째 의견")
    assert item["truncated"] is True and len(item["text"]) >= 500
    assert len(found.content) <= runtime_mod.TOOL_RESULT_CHARS, len(found.content)
    assert "지운 의견" not in found.content


def test_my_projects_screen_filter_and_the_tool_agree(app, db, client, login_as, people, resources, make_project):
    """`/api/projects?mine=true` 는 진실 하네스의 정본이다 — 도구의 「내 프로젝트」와 같은 조건 · 같은 수여야 한다."""
    from app.projects.models import ProjectMember

    a1 = people["a1"]
    member_of = resources["projects"]["a1"]
    owned = make_project(name="a1 이 담당하는 프로젝트", dept=D_A1)
    owned.owner_user_id = a1.id
    db.add(ProjectMember(project_id=member_of.id, user_id=a1.id, role="member"))
    db.commit()
    tool = _body(_run(app, a1, "search_projects", scope="mine"))
    login_as("user", email=PASSWORD_LOGIN_EMAIL)
    screen = client.get("/api/projects", params={"mine": "true"}).json()
    everything = client.get("/api/projects").json()
    assert {p["name"] for p in screen["items"]} == {i["name"] for i in tool["items"]} == {"a1 프로젝트",
                                                                                         "a1 이 담당하는 프로젝트"}
    assert screen["total"] == tool["total"] == 2
    assert everything["total"] > screen["total"], "mine 이 아무것도 거르지 않는다"


class _BlindEmbed(contract.EmbedAdapter):
    """모든 글을 같은 벡터로 — 의미 검색 레인이 낱말과 상관없이 문서를 낸다(「뜻으로만 찾은 문서」를 만드는 반례)."""

    def __init__(self):
        from app.ai import catalog as ai_catalog

        self.name, self.model, self.dim = "blind", ai_catalog.DEFAULT_EMBEDDING_MODEL_ID, ai_catalog.VECTOR_DIM

    def capability(self):
        return contract.available(contract.CAP_EMBED, model=self.model)

    def embed(self, texts, *, kind="passage"):
        one = tuple([1.0] + [0.0] * (self.dim - 1))
        return contract.EmbedResult(status=contract.STATUS_OK, model=self.model, dim=self.dim,
                                    vectors=tuple(one for _ in texts))


def test_documents_found_only_by_meaning_are_inside_the_total(app, db, people, make_space, make_knowledge_document):
    """의미 검색이 낱말 없는 문서를 찾으면 그 문서도 `total` 에 든다 — 보인 줄이 언제나 전체 수 안에 있다(「6건 중 8건」이 없다)."""
    gateway = contract.Gateway(enabled=True, embed_adapter=_BlindEmbed())
    space = make_space(name="A1 혼합 문서함", dept=D_A1)
    make_knowledge_document(space=space, title="연차 안내", text="연차 신청은 사흘 전에 합니다.")
    for index in range(3):
        make_knowledge_document(space=space, title=f"관계없는 글 {index}", text=f"점심 메뉴 {index}번을 적습니다.")
    db.commit()
    index_service.run_once(db, gateway=gateway, limit=50)
    db.commit()
    tool = catalog.TOOLS["search_documents"]
    env = catalog.ToolEnv(session_factory=app.state.session_factory, user_id=people["a1"].id,
                          settings=app.state.settings, outbound=app.state.outbound_client, gateway=gateway,
                          settings_cache=app.state.settings_cache, now=app.state.clock.now())
    found = _body(catalog.run(tool, tool.args.model_validate({"query": "연차 신청"}), env))
    assert found["semantic"] is True
    assert found["returned"] == 4, "의미 검색 레인이 돌지 않으면 이 시험은 아무것도 가르지 않는다"
    assert found["total"] == 4 and found["total_documents"] == 4
    assert found["documents_with_every_word"] == 1
    assert "뜻이 가까워 찾은 문서 3건" in found["note"]
