"""AI 도우미 대화 하네스의 순수 판정 (AI 채팅 개선 회차).

하네스는 랩에서 사람 계정으로 돌리는 스크립트라 시험이 그 자리를 대신하지 못한다. 대신 판정 조각이 맞는 견본과 틀린 견본을 둘 다
가르는지를 여기서 고정한다 — 「줄마다 작성자, 날짜」를 못 세거나 주의 경계를 UTC 로 자르면 랩의 PASS · FAIL 이 아무것도 증명하지 못한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.ui_qa import ai_chat_e2e as chat

REPEATED = (
    "황형섭님이 만든 문서는 총 361건입니다. 최근 수정순으로 10건을 보여드립니다.\n"
    "· Backup Crontab 황형섭, 2026-09-04\n"
    "· 보안 황형섭, 2026-09-04\n"
    "· 패키지 구성 황형섭, 2026-09-04\n"
)
CLEAN = "작성하신 문서는 총 361건입니다. 최근 수정한 문서 10건을 먼저 보여드릴게요."


def test_first_sentence_stops_at_the_first_ending():
    assert chat.first_sentence(CLEAN) == "작성하신 문서는 총 361건입니다."
    assert chat.first_sentence("안녕하세요\n무엇을 도와드릴까요?") == "안녕하세요\n"
    assert chat.first_sentence("") == ""


def test_repeated_meta_lines_counts_the_same_name_and_date_tail():
    assert chat.repeated_meta_lines(REPEATED) == 3
    assert chat.repeated_meta_lines(CLEAN) == 0
    # 이름이 다르면 같은 묶음이 아니다.
    mixed = "· 가 문서 김철수, 2026-09-04\n· 나 문서 이영희, 2026-09-05\n"
    assert chat.repeated_meta_lines(mixed) == 1


def test_relisted_counts_titles_of_four_or_more_letters():
    titles = ["Backup Crontab", "패키지 구성", "보안", "없는 제목입니다"]
    # 「보안」은 두 글자라 다른 낱말과 겹칠 수 있어 세지 않는다.
    assert chat.relisted(REPEATED, titles) == 2
    assert chat.relisted(CLEAN, titles) == 0


def test_week_start_is_monday_midnight_kst_as_naive_utc():
    # 2026-10-15(목) 09:00 UTC → 그 주 월요일 2026-10-12 00:00 KST = 2026-10-11 15:00 UTC.
    assert chat.week_start_utc(datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 11, 15, 0)
    # 월요일 새벽(KST 05:00 = 일요일 20:00 UTC)도 같은 월요일이다 — UTC 날짜로 자르면 지난주가 된다.
    assert chat.week_start_utc(datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 11, 15, 0)


def test_vmware_like_takes_the_synonym_family():
    assert chat.vmware_like("vSphere 8 업그레이드 절차")
    assert chat.vmware_like("ESXi 호스트 점검")
    assert not chat.vmware_like("쿠버네티스 노드 증설")


def test_reply_reads_blocks_only_when_the_build_has_them():
    old = chat.Reply(text="답", structured={"tools": [{"name": "my_documents"}]}, message_id="m1", seconds=1.0)
    assert not old.has_blocks_feature
    assert old.shown() == []
    new = chat.Reply(text="답", structured={"results": [
        {"id": "r1", "tool": "my_documents", "kind": "document", "shown": True, "items": [{"id": "d1", "title": "가"}]},
        {"id": "r2", "tool": "search_documents", "kind": "document", "shown": False, "items": []},
    ]}, message_id="m1", seconds=1.0)
    assert new.has_blocks_feature
    assert [b["id"] for b in new.shown()] == ["r1"]
    assert [b["id"] for b in new.shown("search_documents")] == []
    assert chat.block_titles(new.shown()[0]) == ["가"]


def test_doc_items_prefer_the_shown_block_over_sources():
    r = chat.Reply(text="", structured={
        "results": [{"id": "r1", "tool": "my_documents", "kind": "document", "shown": True,
                     "items": [{"id": "d1", "title": "블록 문서"}]}],
        "sources": [{"type": "document", "id": "d9", "route": "/knowledge/d9", "title": "출처 문서", "cited": True}],
    }, message_id="m", seconds=1.0)
    assert chat._doc_items_of(r) == [("d1", "블록 문서")]
    old = chat.Reply(text="", structured={"sources": [
        {"type": "document", "id": "d9", "route": "/knowledge/d9?block=b1", "title": "출처 문서", "cited": True},
        {"type": "document", "id": "d8", "route": "/knowledge/d8", "title": "안 쓴 문서", "cited": False},
    ]}, message_id="m", seconds=1.0)
    assert chat._doc_items_of(old) == [("d9", "출처 문서")]


def test_doc_items_read_ref_and_the_project_card_documents():
    """서버 블록의 항목 id 는 `ref` 다 — `id` 를 읽으면 빈 id 로 문서를 찾는다(랩 r22-chat-after B④). 보인 프로젝트 카드의
    연결 문서도 「보인 문서」다(E⑫ 「방금 찾은 문서 중 첫 번째」)."""
    r = chat.Reply(text="", structured={"results": [
        {"id": "r1", "tool": "search_documents", "kind": "document", "shown": True,
         "items": [{"ref": "d1", "title": "블록 문서"}]},
        {"id": "r2", "tool": "project_activity", "kind": "project_summary", "shown": True,
         "items": [{"ref": "p1", "name": "프로젝트", "documents": {"total": 8, "items": [{"ref": "d7", "title": "연결 문서"}]}}]},
    ]}, message_id="m", seconds=1.0)
    assert chat._doc_items_of(r) == [("d1", "블록 문서"), ("d7", "연결 문서")]


def test_page_titles_read_the_block_envelope():
    assert chat.page_titles({"block": {"items": [{"title": "가"}, {"title": "나"}]}}) == ["가", "나"]
    assert chat.page_titles({"items": [{"title": "옛 모양"}]}) == ["옛 모양"]
    assert chat.page_titles(None) == []


def test_cited_ticket_keys_count_as_mentioned():
    r = chat.Reply(text="파라미터 유실을 고쳤습니다.", structured={"sources": [
        {"type": "ticket", "id": "t1", "key": "SFVHJG-18", "route": "/tickets/t1", "cited": True},
        {"type": "ticket", "id": "t2", "key": "SFVHJG-6", "route": "/tickets/t2", "cited": False},
        {"type": "document", "id": "d1", "route": "/knowledge/d1", "cited": True},
    ]}, message_id="m", seconds=1.0)
    assert chat.cited_ticket_keys(r) == ["SFVHJG-18"]


def test_scenarios_cover_the_fourteen_questions():
    questions = [t.question for s in chat.SCENARIOS for t in s.turns]
    fixed = [q for q in questions if isinstance(q, str)]
    assert "내가 만든 문서" in fixed
    assert "다음 10개 보여줘." in fixed
    assert "방금 찾은 문서 중 첫 번째 문서 열어줘." in fixed
    assert "안녕." in fixed
    # 동적 질문 셋(겹치는 이름 · 후보 되묻기 답 · 프로젝트 코드)을 더해 열넷 + 되묻기 답 하나다.
    assert len(questions) == 15


def test_leaked_tool_names_and_ticket_keys():
    assert chat.leaked_tool_names("`search_documents`로 찾았으나 없었습니다.") == ["search_documents"]
    assert chat.leaked_tool_names("사내 문서에서 「우주 출장」을 찾았지만 없었습니다.") == []
    assert chat.KEY_RE.findall("SFVHJG-12 와 ZCYMPW-542 를 끝냈고 abc-1 은 아닙니다.") == ["SFVHJG-12", "ZCYMPW-542"]
    r = chat.Reply(text="", structured={"results": [{"id": "r1", "tool": "search_tickets", "kind": "ticket", "shown": True,
                                                     "items": [{"key": "SFVHJG-12"}, {"key": "SFVHJG-13"}]}]},
                   message_id="m", seconds=1.0)
    assert chat.shown_ticket_keys(r) == ["SFVHJG-12", "SFVHJG-13"]
