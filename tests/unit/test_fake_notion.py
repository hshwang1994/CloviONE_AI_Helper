"""가짜 Notion 서버(tests/fakes/notion.py) 자신을 시험한다.

## 이 페이크가 지금 무엇을 위해 남아 있는가 (S14)

제품은 더 이상 Notion 을 부르지 않는다. 그래서 이 페이크가 응답할 일은 원칙적으로 한 번도
없고, 시험들은 정확히 그 「한 번도 없다」를 이 페이크로 확인한다 — 붙여 두고 계수기가 0 인지
본다. 계측기가 거짓말을 하면 그 확인이 통째로 무의미해지므로, 이 파일은 **계측기가 실제로
요청을 본다**를 양방향으로 못박는다: 아무도 안 부르면 0 이고, 한 번 부르면 1 이다.

## 무엇이 빠졌는가

`app/reports/notion_source.py` 를 지나던 시험 다섯 건이 사라졌다(페이지네이션·페이지 상한·
질의 실패·토큰 미설정·관계 제목). 그 모듈이 없어졌고, 같은 왕복을 할 앱 쪽 짝도 없다.
페이크 자신의 성질로 판정할 수 있는 것(페이지네이션·오류 응답·관계 DB 질의)은 페이크를
직접 불러 그대로 남기고, 앱의 오류 매핑에만 있던 것(토큰 미설정 → 「설정 안 됨」)은 남길
자리가 없어 함께 사라진다.

qa-contract-change: 앱의 Notion 질의 경로가 통째로 삭제돼 그 경로를 지나던 단언 다섯 건은 판정할 대상이 없다. 페이크 자신으로 판정 가능한 성질(페이지네이션·오류 응답·관계 DB 질의)은 페이크를 직접 호출해 유지하고, 계측기가 요청을 실제로 본다는 반례 확인을 새로 추가한다.
"""

from __future__ import annotations

import httpx
import pytest

from tests.fakes.notion import (
    DEFAULT_PROJECTS_DB,
    DEFAULT_TASKS_DB,
    PROP_DUE,
    PROP_PEOPLE,
    PROP_STATUS,
    PROP_TITLE,
    FakeNotionTasksDB,
    apply_sorts,
    match_filter,
    project_row,
    task_row,
)

pytestmark = pytest.mark.unit

A, B = "notion-a", "notion-b"

ROWS = [
    task_row(page_id="p1", tid=1, title="가", status="진행", due="2026-07-10", people=[A]),
    task_row(page_id="p2", tid=2, title="나", status="완료", due="2026-07-20", people=[A, B]),
    task_row(page_id="p3", tid=3, title="다", status="계획", due="2026-08-01", people=[]),
    task_row(page_id="p4", tid=4, title="라", status="이슈", due=None, people=[B]),
]


def _ids(rows) -> list[str]:
    return [r["id"] for r in rows]


def _select(flt) -> list[str]:
    return _ids([r for r in ROWS if match_filter(r, flt)])


def _query(fake_http, database_id: str, body: dict) -> httpx.Response:
    with httpx.Client(transport=fake_http.transport()) as http:
        return http.post(
            f"https://api.notion.com/v1/databases/{database_id}/query", json=body
        )


# ── filters ──────────────────────────────────────────────────────────────────

def test_people_contains_and_is_empty_select_different_rows():
    assert _select({"property": PROP_PEOPLE, "people": {"contains": A}}) == ["p1", "p2"]
    assert _select({"property": PROP_PEOPLE, "people": {"contains": B}}) == ["p2", "p4"]
    assert _select({"property": PROP_PEOPLE, "people": {"is_empty": True}}) == ["p3"]
    assert _select({"property": PROP_PEOPLE, "people": {"is_not_empty": True}}) == ["p1", "p2", "p4"]


def test_date_range_filter_is_half_open_and_skips_empty_dates():
    window = {"and": [
        {"property": PROP_DUE, "date": {"on_or_after": "2026-07-01"}},
        {"property": PROP_DUE, "date": {"before": "2026-08-01"}},
    ]}
    assert _select(window) == ["p1", "p2"]
    assert _select({"property": PROP_DUE, "date": {"is_not_empty": True}}) == ["p1", "p2", "p3"]
    assert _select({"property": PROP_DUE, "date": {"is_empty": True}}) == ["p4"]


def test_or_composition_and_status_equals():
    either = {"or": [
        {"property": PROP_STATUS, "status": {"equals": "완료"}},
        {"property": PROP_PEOPLE, "people": {"is_empty": True}},
    ]}
    assert _select(either) == ["p2", "p3"]


def test_no_filter_selects_everything():
    assert _select(None) == ["p1", "p2", "p3", "p4"]


def test_unsupported_filter_is_loud_not_silently_true():
    with pytest.raises(NotImplementedError):
        match_filter(ROWS[0], {"property": PROP_TITLE, "rich_text": {"equals": "가"}})


# ── sorts ────────────────────────────────────────────────────────────────────

def test_sorts_ascending_descending_and_empties_last():
    asc = [{"property": PROP_DUE, "direction": "ascending"}]
    desc = [{"property": PROP_DUE, "direction": "descending"}]
    assert _ids(apply_sorts(ROWS, asc)) == ["p1", "p2", "p3", "p4"]
    assert _ids(apply_sorts(ROWS, desc)) == ["p3", "p2", "p1", "p4"]


# ── pagination / failure modes, driven against the fake itself ───────────────

def _many(count: int) -> list[dict]:
    return [task_row(page_id=f"m{i:03d}", tid=i, title=f"티켓 {i}", status="진행",
                     due=f"2026-07-{(i % 28) + 1:02d}") for i in range(count)]


def test_pagination_walks_every_page(fake_http):
    fake = FakeNotionTasksDB(rows=_many(7), page_size=3).install(fake_http)
    seen: list[str] = []
    cursor = None
    for _ in range(5):
        body = {"start_cursor": cursor} if cursor else {}
        payload = _query(fake_http, DEFAULT_TASKS_DB, body).json()
        seen.extend(r["id"] for r in payload["results"])
        cursor = payload["next_cursor"]
        if not payload["has_more"]:
            break
    assert len(seen) == 7
    assert len(fake.queries) == 3                       # 3 + 3 + 1
    assert fake.queries[1]["start_cursor"] == "fake-cursor-3"


def test_always_has_more_mode_never_says_done(fake_http):
    """끝났다고 절대 말하지 않는 서버 — 루프를 끊는 것은 언제나 **부르는 쪽**이어야 한다."""
    FakeNotionTasksDB(rows=_many(2), page_size=2, always_has_more=True).install(fake_http)
    cursor = None
    for _ in range(4):
        body = {"start_cursor": cursor} if cursor else {}
        payload = _query(fake_http, DEFAULT_TASKS_DB, body).json()
        assert payload["has_more"] is True
        assert len(payload["results"]) == 2
        assert payload["next_cursor"] != cursor
        cursor = payload["next_cursor"]


def test_failure_mode_answers_an_error_status(fake_http):
    FakeNotionTasksDB(rows=_many(2), fail_status=500).install(fake_http)
    response = _query(fake_http, DEFAULT_TASKS_DB, {})
    assert response.status_code == 500
    assert response.json()["object"] == "error"


def test_relation_titles_come_from_the_projects_database(fake_http):
    FakeNotionTasksDB(
        rows=[], projects=[project_row(page_id="pr1", name="알파"),
                           project_row(page_id="pr2", name="베타")],
    ).install(fake_http)
    payload = _query(fake_http, DEFAULT_PROJECTS_DB, {}).json()
    assert [r["id"] for r in payload["results"]] == ["pr1", "pr2"]


# ── 계측기가 정말로 요청을 본다 ────────────────────────────────────────────────

def test_an_uncalled_fake_records_nothing_and_a_called_one_records_the_call(fake_http):
    """반례 확인이다 — 이것이 없으면 「왕복이 없다」는 단언 전부가 공짜로 초록이 된다."""
    fake = FakeNotionTasksDB(rows=_many(1)).install(fake_http)
    assert fake.queries == []
    assert fake_http.requests == []

    _query(fake_http, DEFAULT_TASKS_DB, {})

    assert len(fake.queries) == 1
    assert len(fake_http.requests) == 1


# ── the FakeHTTP hook stays additive ─────────────────────────────────────────

def test_handler_declines_unknown_paths_and_prefix_routes_still_win(fake_http):
    """A registered handler must not swallow URLs it does not serve."""
    FakeNotionTasksDB(rows=[]).install(fake_http)
    fake_http.on("https://api.notion.com/v1/users", json_body={"results": ["prefix route"]})

    with httpx.Client(transport=fake_http.transport()) as http:
        # served by the body-aware handler
        schema = http.get(f"https://api.notion.com/v1/databases/{DEFAULT_TASKS_DB}")
        assert schema.json()["object"] == "database"
        # declined by it, so the plain prefix route answers — unchanged behaviour
        assert http.get("https://api.notion.com/v1/users").json() == {"results": ["prefix route"]}


def test_plain_fake_http_is_untouched_when_no_handler_registered(fake_http):
    fake_http.on("https://example.invalid/a", json_body={"ok": 1})
    with httpx.Client(transport=fake_http.transport()) as http:
        assert http.get("https://example.invalid/a/b").json() == {"ok": 1}
        assert http.get("https://elsewhere.invalid/").status_code == 502
