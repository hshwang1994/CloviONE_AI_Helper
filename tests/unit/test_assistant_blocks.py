"""도구 결과 블록 · 이어지는 질문의 기억 · 첫 답의 의도 제목 — `app/ai/assistant/blocks.py` (AI 채팅 개선 회차).

화면은 모델이 쓴 마크다운 목록 대신 서버가 고른 칸만 그린다. 여기서 못박는 것:
- 블록은 종류별 허용 칸만 싣는다(발췌 · 본문은 싣지 않는다). `shown` 은 모델이 준 `show` 이고 `args` 에서 빠진다.
- `list_route` 는 서버가 만든 앱 안 상대 경로다(`/` 로 시작, 스킴 · `//` 없음). 화면이 없는 보기는 None 이다.
- 기억은 상한 안에서 오래된 차례 · 뒤 항목부터 덜어 낸다.
- 의도 제목은 도구와 검증된 인자로 짓고, 인자의 마크다운 · 제어 문자를 걷는다.
"""

from __future__ import annotations

import json

from app.ai.assistant import blocks, results


def _ok(tool, items, *, args=None, total=None, offset=0):
    from dataclasses import replace

    execution = results.ok(tool, items, total=len(items) if total is None else total, offset=offset)
    return replace(execution, args=args or {})


DOCS = [{"ref": f"d{i}", "title": f"문서 {i}", "author": "황형섭", "updated_at": "2026-09-04T00:00:00",
         "space": "굿모닝아이텍", "excerpt": "본문 발췌" * 30, "comments": 2, "route": f"/knowledge/d{i}"} for i in range(12)]


def test_a_shown_list_becomes_a_compact_block():
    [block] = blocks.build([_ok("my_documents", DOCS, args={"show": True, "sort": "recent"}, total=361)], owner_id="u1")
    assert block["id"] == "r1" and block["kind"] == "document" and block["shown"] is True
    assert block["args"] == {"sort": "recent"}, "show 는 인자에서 빠진다"
    assert block["total"] == 361 and block["returned"] == 12 and block["offset"] == 0
    assert len(block["items"]) == blocks.MAX_ITEMS
    assert set(block["items"][0]) == {"ref", "title", "author", "updated_at", "space", "route"}
    assert block["sort"] == "recent" and block["sort_options"] == ["recent", "created", "title"]
    assert block["list_route"] == "/knowledge?author=u1&sort=recent"


def test_unshown_and_failed_calls():
    failed = results.error("my_documents", results.ERROR_NOT_FOUND)
    built = blocks.build([failed, _ok("search_documents", DOCS[:2], args={"query": "vmware"})], owner_id="u1")
    assert [b["shown"] for b in built] == [False]
    assert built[0]["list_route"] == "/knowledge?q=vmware"
    assert blocks.build([_ok("get_document", DOCS[:1])], owner_id="u1") == [], "블록이 없는 도구"


def test_list_routes_are_relative_app_paths():
    cases = {
        ("my_documents", json.dumps({"view": "edited"})): None,
        ("my_documents", json.dumps({"query": "a&b=c"})): "/knowledge?author=u1&sort=recent&q=a%26b%3Dc",
        ("search_documents", json.dumps({"query": "nsx", "mine": True})): "/knowledge?q=nsx&author=u1",
        ("my_work", json.dumps({"view": "assigned"})): "/my-tickets",
        ("search_tickets", json.dumps({"scope": "unassigned"})): "/unassigned",
        ("search_projects", json.dumps({"scope": "mine"})): "/projects",
        ("get_project_summary", json.dumps({"project": "x"})): None,
    }
    for (tool, raw), expected in cases.items():
        route = blocks.list_route(tool, json.loads(raw), "u1")
        assert route == expected, (tool, route)
        if route:
            assert route.startswith("/") and not route.startswith("//") and "://" not in route


def test_project_summary_card_keeps_the_numbers_not_the_reports():
    item = {"ref": "p1", "code": "SFVHJG", "name": "SK하이닉스", "status": "진행", "route": "/projects/p1",
            "progress": {"percent": 82.8, "counted_tasks": 29, "done_tasks": 24},
            "health": {"score": 68, "reasons": [{"label": "지연 티켓", "detail": "긴 설명"}]},
            "tickets": {"total": 29, "open": 5, "overdue_open": 1, "blocked": 0, "status_counts": {"완료": 24}},
            "recent_completed": [{"key": "SFVHJG-1", "title": "끝낸 일", "completed_at": "2026-10-01", "route": "/tickets/t1",
                                  "status": "완료"}],
            "weekly_reports": [{"summary": "긴 주간 리포트"}], "members": [{"name": "누구"}]}
    [block] = blocks.build([_ok("project_activity", [item], args={"project": "SFVHJG", "show": True})], owner_id="u1")
    card = block["items"][0]
    assert block["kind"] == "project_summary" and block["shown"]
    assert card["progress"]["percent"] == 82.8 and card["health"] == {"score": 68, "reasons": ["지연 티켓"]}
    assert card["recent_completed"] == [{"key": "SFVHJG-1", "title": "끝낸 일", "completed_at": "2026-10-01",
                                         "route": "/tickets/t1"}]
    assert "weekly_reports" not in card and "members" not in card


def test_same_call_twice_is_one_block_and_blocks_are_capped():
    same = _ok("my_documents", DOCS[:1], args={"show": True})
    assert len(blocks.build([same, same], owner_id="u1")) == 1
    many = [_ok("search_documents", DOCS[:1], args={"query": f"q{i}"}) for i in range(7)]
    assert len(blocks.build(many, owner_id="u1")) == blocks.MAX_BLOCKS


def test_shown_keys_map_kinds_to_source_types():
    built = blocks.build([
        _ok("my_documents", DOCS[:2], args={"show": True}),
        _ok("search_tickets", [{"ref": "t1", "key": "A-1", "title": "티켓", "route": "/tickets/t1"}],
            args={"scope": "team"}),
    ], owner_id="u1")
    assert blocks.shown_keys(built) == {("document", "d0"), ("document", "d1")}


def test_memory_keeps_numbers_refs_and_fits_the_budget():
    built = blocks.build([_ok("my_documents", DOCS, args={"show": True}, total=361, offset=10)], owner_id="u1")
    [entry] = blocks.memory_entry(built, turn=-1)
    assert entry["args"] == {} and entry["total"] == 361 and entry["offset"] == 10
    assert entry["items"][0] == {"n": 11, "ref": "d0", "title": "문서 0", "updated_at": "2026-09-04T00:00:00"}
    text = blocks.memory_text([entry] * 6, limit=900)
    assert len(text) <= 900 and json.loads(text)
    assert blocks.memory_text([]) is None


def test_intent_titles_from_tools_and_arguments():
    def title(tool, **args):
        return blocks.intent_title([_ok(tool, [], args=args)])

    assert title("my_work", view="assigned") == "내 담당 티켓 조회"
    assert title("my_documents") == "내 문서 조회"
    assert title("my_documents", query="VMware") == "내 문서 중 VMware 검색"
    assert title("project_activity", project="SK하이닉스") == "SK하이닉스 프로젝트 현황"
    assert title("search_documents", query="NSX 자동화", mine=True) == "내 문서 중 NSX 자동화 문서 검색"
    assert title("project_activity", project="[x](javascript:1) **굵게**\n다음") == "x javascript:1 굵게 다음 프로젝트 현황"
    assert blocks.intent_title([]) is None
    assert blocks.intent_title([_ok("get_document", [], args={"ref": "d1"})]) is None
