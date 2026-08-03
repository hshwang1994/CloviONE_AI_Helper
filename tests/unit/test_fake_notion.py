"""Tests for the body-aware Notion fake (tests/fakes/notion.py).

The golden contract in tests/regression/test_api_contract_golden.py is only
worth anything if the fake underneath it really reads the request body. These
tests pin that: filters select, sorts order, pagination pages, the
always-has-more mode truncates, and registering a body-aware handler leaves the
existing prefix routing of FakeHTTP untouched.

The pagination/truncation cases drive the *real* app code path — a genuine
OutboundClient over the fake transport into notion_source — rather than calling
the fake directly, so the page cap being exercised is the app's own.
"""

from __future__ import annotations

import pytest

from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from app.reports import notion_source
from tests.fakes.notion import (
    DEFAULT_TASKS_DB,
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


# ── filters ──────────────────────────────────────────────────────────────────

def test_people_contains_and_is_empty_select_different_rows():
    assert _select({"property": notion_source.PROP_PEOPLE, "people": {"contains": A}}) == ["p1", "p2"]
    assert _select({"property": notion_source.PROP_PEOPLE, "people": {"contains": B}}) == ["p2", "p4"]
    assert _select({"property": notion_source.PROP_PEOPLE, "people": {"is_empty": True}}) == ["p3"]
    assert _select({"property": notion_source.PROP_PEOPLE, "people": {"is_not_empty": True}}) == ["p1", "p2", "p4"]


def test_date_range_filter_is_half_open_and_skips_empty_dates():
    # Exactly the filter query_tasks_for_period builds for a calendar month.
    july = {"and": [
        {"property": notion_source.PROP_DUE, "date": {"on_or_after": "2026-07-01"}},
        {"property": notion_source.PROP_DUE, "date": {"before": "2026-08-01"}},
    ]}
    assert _select(july) == ["p1", "p2"]          # p3 is 08-01 (end is exclusive), p4 has no due
    assert _select({"property": notion_source.PROP_DUE, "date": {"is_not_empty": True}}) == ["p1", "p2", "p3"]
    assert _select({"property": notion_source.PROP_DUE, "date": {"is_empty": True}}) == ["p4"]


def test_or_composition_and_status_equals():
    flt = {"or": [
        {"property": notion_source.PROP_STATUS, "status": {"equals": "완료"}},
        {"property": notion_source.PROP_PEOPLE, "people": {"is_empty": True}},
    ]}
    assert _select(flt) == ["p2", "p3"]


def test_no_filter_selects_everything():
    assert _select(None) == ["p1", "p2", "p3", "p4"]


def test_unsupported_filter_is_loud_not_silently_true():
    with pytest.raises(NotImplementedError):
        match_filter(ROWS[0], {"property": notion_source.PROP_TITLE, "rich_text": {"equals": "가"}})


# ── sorts ────────────────────────────────────────────────────────────────────

def test_sorts_ascending_descending_and_empties_last():
    asc = [{"property": notion_source.PROP_DUE, "direction": "ascending"}]
    desc = [{"property": notion_source.PROP_DUE, "direction": "descending"}]
    assert _ids(apply_sorts(ROWS, asc)) == ["p1", "p2", "p3", "p4"]
    # p4 has no due date: empty sorts last in *both* directions, as Notion does.
    assert _ids(apply_sorts(ROWS, desc)) == ["p3", "p2", "p1", "p4"]


# ── pagination / truncation, through the real app code path ──────────────────

@pytest.fixture()
def outbound(settings, fake_http):
    return OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
        transport=fake_http.transport(),
    )


@pytest.fixture()
def token(settings):
    (settings.secrets_dir / settings.notion_report_token_ref).write_text("t", encoding="utf-8")


def _many(count: int) -> list[dict]:
    return [task_row(page_id=f"m{i:03d}", tid=i, title=f"티켓 {i}", status="진행",
                     due=f"2026-07-{(i % 28) + 1:02d}") for i in range(count)]


def test_pagination_walks_every_page(settings, fake_http, outbound, token):
    fake = FakeNotionTasksDB(rows=_many(7), page_size=3).install(fake_http)
    rows = notion_source.query_all_tasks(outbound, settings)
    assert len(rows) == 7
    assert len(fake.queries) == 3                       # 3 + 3 + 1
    assert fake.queries[1]["start_cursor"] == "fake-cursor-3"


def test_always_has_more_mode_stops_at_the_callers_page_cap(settings, fake_http, outbound, token):
    """A server that never says 'done' must be cut off by notion_source._MAX_PAGES."""
    FakeNotionTasksDB(rows=_many(2), page_size=2, always_has_more=True).install(fake_http)
    rows = notion_source.query_all_tasks(outbound, settings)
    assert len(rows) == 2 * notion_source._MAX_PAGES


def test_failure_mode_maps_to_a_query_error(settings, fake_http, outbound, token):
    FakeNotionTasksDB(rows=_many(2), fail_status=500).install(fake_http)
    with pytest.raises(notion_source.NotionQueryError):
        notion_source.query_all_tasks(outbound, settings)


def test_missing_token_maps_to_not_configured(settings, fake_http, outbound):
    FakeNotionTasksDB(rows=_many(2)).install(fake_http)  # no token file written
    with pytest.raises(notion_source.NotionNotConfiguredError):
        notion_source.query_all_tasks(outbound, settings)


def test_relation_titles_come_from_the_projects_database(settings, fake_http, outbound, token):
    from app.tickets import notion_write

    FakeNotionTasksDB(
        rows=[], projects=[project_row(page_id="pr1", name="알파"),
                           project_row(page_id="pr2", name="베타")],
    ).install(fake_http)
    names = notion_write.query_relation_titles(outbound, settings, "projects-db-0001")
    assert names == [{"id": "pr1", "name": "알파"}, {"id": "pr2", "name": "베타"}]


# ── the FakeHTTP hook stays additive ─────────────────────────────────────────

def test_handler_declines_unknown_paths_and_prefix_routes_still_win(fake_http):
    """A registered handler must not swallow URLs it does not serve."""
    FakeNotionTasksDB(rows=[]).install(fake_http)
    fake_http.on("https://api.notion.com/v1/users", json_body={"results": ["prefix route"]})

    import httpx

    with httpx.Client(transport=fake_http.transport()) as http:
        # served by the body-aware handler
        schema = http.get(f"https://api.notion.com/v1/databases/{DEFAULT_TASKS_DB}")
        assert schema.json()["object"] == "database"
        # declined by it, so the plain prefix route answers — unchanged behaviour
        assert http.get("https://api.notion.com/v1/users").json() == {"results": ["prefix route"]}


def test_plain_fake_http_is_untouched_when_no_handler_registered(fake_http):
    import httpx

    fake_http.on("https://example.invalid/a", json_body={"ok": 1})
    with httpx.Client(transport=fake_http.transport()) as http:
        assert http.get("https://example.invalid/a/b").json() == {"ok": 1}
        assert http.get("https://elsewhere.invalid/").status_code == 502
