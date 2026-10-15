"""AI 진실 하네스와 패러프레이즈 벤치의 순수 판정 (A10 · A7, D-570).

하네스는 랩에서 사람이 돌리는 스크립트라 시험이 그 자리를 대신하지 못한다. 대신 판정 함수가 맞는 쪽과 틀린 쪽을 둘 다 가르는지를
여기서 고정한다 — 수 대조가 「1,234」 의 「234」 를 맞았다고 하거나, env 파일 읽기가 요청하지 않은 비밀까지 들이면 하네스의 PASS 가
아무것도 증명하지 못한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bench import retrieval_paraphrase as bench
from scripts.ui_qa import ai_lab_common as common
from scripts.ui_qa import ai_lab_e2e as lab
from scripts.ui_qa import ai_truth_e2e as truth

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests" / "fixtures" / "ai_paraphrase_sample.json"

#: 도우미 도구 열일곱(서버 계약). 하네스가 기대하는 도구 이름은 이 안에 있어야 한다.
TOOLS = {
    "my_documents", "search_documents", "get_document", "search_workspace", "my_work", "get_ticket", "search_tickets",
    "search_projects", "get_project_summary", "project_activity", "my_approvals", "find_people", "recent_changes",
    "work_summary", "my_notifications", "my_activity", "sprint_meetings",
}


# ── 수 · 글 대조 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("text", "n", "expected"), [
    ("총 1,234건입니다.", 1234, True),
    ("총 1234건입니다.", 1234, True),
    ("12345건", 1234, False),
    ("1,234건", 234, False),
    ("진행률 12.5%", 12, False),
    ("(25건 중 10건)", 25, True),
    ("(25건 중 10건)", 10, True),
    ("3건, 12건", 12, True),
    ("0건입니다.", 0, True),
    ("10건", 1, False),
    ("티켓 45개를 맡고 있습니다.", 45, True),
    ("문서가 361건 있습니다.", 36, False),
])
def test_number_in_matches_the_number_and_only_the_number(text, n, expected):
    assert truth.number_in(text, n) is expected


def test_mask_emails_hides_the_local_part_and_is_idempotent():
    once = common.mask_emails("hshwang@goodmit.co.kr 와 a@b.co")
    assert once == "h****g@goodmit.co.kr 와 a****a@b.co"
    assert common.mask_emails(once) == once, "결과 파일 전체를 한 번 더 가려도 주소가 다시 바뀌면 안 된다"
    assert common.mask_emails("이메일 없음") == "이메일 없음"


def test_titles_mentioned_folds_case_and_spaces_and_reads_sources():
    sources = [{"type": "document", "title": "VMware  NSX 설계", "route": "/knowledge/d1"}]
    found = truth.titles_mentioned("vmware 운영 가이드를 보세요.", sources, ["VMware 운영 가이드", "vmware nsx 설계", "가", "없는 문서"])
    assert found == ["VMware 운영 가이드", "vmware nsx 설계"]


def test_route_ids_and_prefixes():
    sources = [
        {"type": "document", "route": "/knowledge/d-1?block=b9"},
        {"type": "ticket", "route": "/tickets/t-1"},
        {"type": "sprint", "route": "/sprint?team=a&sprint=s"},
        "not-a-dict",
    ]
    assert truth.route_id("/knowledge/d-1?block=b9", "/knowledge/") == "d-1"
    assert truth.route_id("/tickets/t-1", "/knowledge/") is None
    assert truth.source_ids(sources) == {"d-1"}
    assert truth.source_ids(sources, "/tickets/") == {"t-1"}
    assert truth.has_route(sources, "/sprint") and not truth.has_route(sources, "/projects/")


def test_keys_mentioned_does_not_match_inside_a_longer_key():
    answer = "ABCDEF-123 와 abcdef-7 을 보세요."
    assert truth.keys_mentioned(answer, ["ABCDEF-12", "ABCDEF-123", "ABCDEF-7"]) == ["ABCDEF-123", "ABCDEF-7"]


def test_phrase_detectors():
    assert truth.asks_which("어느 프로젝트를 말씀하시나요?")
    assert not truth.asks_which("프로젝트 두 개가 있습니다.")
    assert truth.searched_phrase("「우주 출장」으로 찾아봤지만 맞는 문서가 없습니다.")
    assert truth.searched_phrase("사내 문서에서 검색해 봤습니다.")
    assert not truth.searched_phrase("규정은 다음과 같습니다.")
    assert truth.not_found_phrase("그 문서는 찾지 못했습니다.")
    assert truth.percent_or_count("진행률은 42%입니다.") and truth.percent_or_count("완료 12건, 남은 3건")
    assert not truth.percent_or_count("잘 진행되고 있습니다.")


def test_count_not_done_treats_empty_status_as_open():
    items = [{"status": "완료"}, {"status": "취소"}, {"status": "진행"}, {"status": None}, {}, "x"]
    assert truth.count_not_done(items) == 3


def test_parse_only_accepts_numbers_and_ids():
    assert truth.parse_only(["q01", "8", "q15,3"]) == {"q01", "q08", "q15", "q03"}
    assert truth.parse_only(None) is None


def test_tools_satisfied_takes_any_alternative_as_a_subset():
    alts = (("project_activity",), ("search_documents", "search_tickets"))
    assert truth.tools_satisfied(["search_documents", "search_tickets", "get_ticket"], alts)
    assert truth.tools_satisfied(["project_activity"], alts)
    assert not truth.tools_satisfied(["search_documents"], alts)
    assert truth.tools_satisfied([], ())


# ── env 파일 ─────────────────────────────────────────────────────────────────


def test_read_env_file_returns_only_the_requested_keys(tmp_path):
    env = tmp_path / "qa.env"
    env.write_text(
        "# 주석은 건너뛴다\n"
        "export AI_TRUTH_EMAIL=persona@goodmit.co.kr\n"
        "AI_TRUTH_PASSWORD=\"p@ss word#1\"\n"
        "UI_QA_PASSWORD=never-read\n"
        "AI_TRUTH_OTHER_TITLE='다른 부서 문서'\n"
        "AI_TRUTH_AMBIGUOUS_PROJECT=하이 # 끝 주석\n"
        "BROKEN_LINE\n",
        encoding="utf-8",
    )
    got = common.read_env_file(env, truth.ENV_KEYS)
    assert got == {
        "AI_TRUTH_EMAIL": "persona@goodmit.co.kr",
        "AI_TRUTH_PASSWORD": "p@ss word#1",
        "AI_TRUTH_OTHER_TITLE": "다른 부서 문서",
        "AI_TRUTH_AMBIGUOUS_PROJECT": "하이",
    }
    assert "UI_QA_PASSWORD" not in got


def test_env_file_values_win_over_the_environment(tmp_path, monkeypatch):
    env = tmp_path / "qa.env"
    env.write_text("AI_TRUTH_EMAIL=file@goodmit.co.kr\n", encoding="utf-8")
    monkeypatch.setenv("AI_TRUTH_EMAIL", "env@goodmit.co.kr")
    monkeypatch.setenv("AI_TRUTH_PASSWORD", "from-env")
    creds = truth.resolve_credentials(str(env))
    assert creds["AI_TRUTH_EMAIL"] == "file@goodmit.co.kr"
    assert creds["AI_TRUTH_PASSWORD"] == "from-env"


def test_missing_credentials_exit_2_without_printing_them(monkeypatch, capsys, tmp_path):
    for key in truth.ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert truth.main(["--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "AI_TRUTH_EMAIL" in err and "@" not in err


# ── 황금 질문 표 ─────────────────────────────────────────────────────────────


def test_the_golden_questions_are_eighteen_with_known_tools():
    ids = [q.qid for q in truth.QUESTIONS]
    assert ids == [f"q{n:02d}" for n in range(1, 19)]
    for q in truth.QUESTIONS:
        for alt in q.expected:
            assert set(alt) <= TOOLS, (q.qid, alt)
        for name in ("phrase", "project_code", "ambiguous", "other_title"):
            assert ("{" + name + "}" in q.template) == (name in q.needs), (q.qid, name)
    assert [q.qid for q in truth.QUESTIONS if q.chat] == ["q17"]


def _answer(text, *, tools=(), sources=(), mode="tools", notice=None):
    return truth.Answer(text=text, structured={
        "mode": mode, "notice": notice,
        "tools": [{"name": n, "ok": True, "count": 1, "total": 1} for n in tools],
        "sources": list(sources),
    })


def _question(qid):
    return next(q for q in truth.QUESTIONS if q.qid == qid)


def test_evaluate_fails_search_only_and_chit_chat_tools():
    opts = truth.Options()
    meta = {"processing_status": "done"}
    chat = _answer("안녕하세요! 좋은 하루예요.", tools=["search_documents"])
    assert any("잡담" in f for f in truth.evaluate(_question("q17"), chat, meta, {}, opts))
    fallback = _answer("검색 결과입니다.", tools=["search"], mode="search_only")
    assert any("도구 모드" in f for f in truth.evaluate(_question("q18"), fallback, meta, {}, opts))
    good = _answer("SLA 는 서비스 수준 약속입니다.")
    assert truth.evaluate(_question("q18"), good, meta, {}, opts) == []


def test_open_ticket_check_needs_the_number_the_keys_and_a_ticket_source():
    facts = {"not_done": 3, "keys": ["ABCDEF-1", "ABCDEF-2", "ABCDEF-3"]}
    ok = _answer("미완료 티켓은 3건입니다. ABCDEF-1, ABCDEF-2 …", tools=["my_work"],
                 sources=[{"type": "ticket", "title": "t", "route": "/tickets/x"}])
    assert truth.check_q08(ok, facts) == []
    wrong = _answer("미완료 티켓은 10건입니다. ABCDEF-1", tools=["my_work"])
    failures = truth.check_q08(wrong, facts)
    assert len(failures) == 3
    none = _answer("담당하는 미완료 티켓이 없습니다.", tools=["my_work"])
    assert truth.check_q08(none, {"not_done": 0, "keys": []}) == []


def test_ambiguous_project_check_accepts_candidates_or_a_question_back():
    facts = {"projects": [{"code": "AAAAAA", "name": "가나 하이 1차"}, {"code": "BBBBBB", "name": "가나 하이 2차"}]}
    assert truth.check_q05(_answer("AAAAAA 와 BBBBBB 두 프로젝트가 있습니다."), facts) == []
    assert truth.check_q05(_answer("어느 프로젝트를 말씀하시는지 알려 주세요."), facts) == []
    assert truth.check_q05(_answer("그 프로젝트를 찾지 못했습니다."), facts)


def test_no_results_check():
    ok = _answer("「2031년 우주 출장」으로 사내 문서를 찾아봤지만 맞는 규정이 없습니다.", tools=["search_documents"],
                 notice="no_results")
    assert truth.check_q16(ok, {}) == []
    bad = _answer("그런 규정은 존재하지 않습니다.", tools=["search_documents"])
    assert len(truth.check_q16(bad, {})) == 3


def test_other_department_title_must_not_leak():
    title = "남의 부서 비밀 문서"
    leaked = _answer(f"{title}의 내용은 다음과 같습니다.",
                     sources=[{"type": "document", "title": title, "route": "/knowledge/d"}])
    assert len(truth.check_q15(leaked, {}, title=title)) == 2
    honest = _answer(f"「{title}」 문서는 찾지 못했습니다.")
    assert truth.check_q15(honest, {}, title=title) == []


def test_lab_harness_verdicts_fail_the_fallback_mode():
    assert lab.chat_verdict({"processing_status": "done"}, {"mode": "tools"}) == "PASS"
    assert lab.chat_verdict({"processing_status": "done"}, {"mode": "search_only"}) == "FAIL"
    assert lab.chat_verdict({"processing_status": "failed"}, {"mode": "tools"}) == "FAIL"
    assert lab.tools_verdict({"tools": "unsupported"}) == "FAIL"
    assert lab.tools_verdict({"tools": "ok"}) == "PASS"
    assert lab.tools_verdict({"tools": "unknown"}) == "SKIPPED"


# ── 패러프레이즈 벤치 ───────────────────────────────────────────────────────


def test_the_paraphrase_sample_has_six_well_formed_queries():
    queries = bench.load_queries(SAMPLE)
    assert len(queries) == 6
    assert len({q["id"] for q in queries}) == 6
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert all(set(item) == {"id", "question", "gold"} for item in raw)


@pytest.mark.parametrize("payload", [
    [],
    [{"id": "a", "question": "질문입니다", "gold": []}],
    [{"id": "a", "question": "질문입니다", "gold": ["x"]}, {"id": "a", "question": "또 질문", "gold": ["y"]}],
    [{"question": "질문입니다", "gold": ["x"]}],
])
def test_load_queries_rejects_bad_shapes(tmp_path, payload):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        bench.load_queries(path)


def test_score_reads_ranks_from_fabricated_rankings():
    rows = [
        (["a", "b", "c"], {"a"}),          # 1등
        (["x", "y", "z", "w", "b"], {"b"}),  # 5등
        (["x"] * 9 + ["g"], {"g"}),        # 10등
        (["x", "y"], {"q"}),               # 못 찾음
    ]
    got = bench.score(rows)
    assert got == {"n": 4, "recall@1": 0.25, "recall@5": 0.5, "mrr@10": round((1 + 0.2 + 0.1) / 4, 3)}
    assert bench.score([]) == {"n": 0, "recall@1": None, "recall@5": None, "mrr@10": None}
    assert bench.first_hit(["a", "b"], {"b", "c"}) == 2


def test_percentile_and_gold_resolution():
    assert bench.percentile([0.1, 0.2, 0.3, 0.4], 50) == 0.25
    assert bench.percentile([0.12], 90) == 0.12
    assert bench.percentile([], 50) is None
    uuid_a = "11111111-2222-3333-4444-555555555555"
    titles = {bench.norm("연차 휴가 신청 절차"): {"d1"}, bench.norm("다른 문서"): {"d2"}}
    assert bench.resolve_gold(["연차  휴가 신청 절차", uuid_a], titles, {uuid_a}) == {"d1", uuid_a}
    assert bench.resolve_gold(["모르는 제목", "99999999-2222-3333-4444-555555555555"], titles, {uuid_a}) == set()
