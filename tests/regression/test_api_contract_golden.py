"""THIS FILE IS THE API CONTRACT.

The JSON under ``tests/regression/golden/`` is the byte-for-byte response shape
that ``frontend/`` is built against. A diff here is never "just a test failure":
it means a shipped response changed. Any diff must be an **intentional** commit
that edits the golden file in the same change, with a message saying what moved
and why. Never regenerate the goldens to make a red build green.

Regenerating (only alongside a deliberate contract change)::

    UPDATE_GOLDEN=1 .venv/Scripts/python.exe -m pytest tests/regression/test_api_contract_golden.py

Determinism rules this module holds itself to:
  * users, Notion mappings and cached documents are inserted with **fixed**
    primary keys — never ``create_user``/``default=new_uuid``, whose UUID4 keys
    would leak into ``assignee_user_ids`` and churn the golden on every run;
  * the clock is frozen (``CONTRACT_NOW``), which pins ``generated_at`` on the
    monthly report and the default sprint window;
  * Notion rows come from ``tests/fakes/notion.FakeNotionTasksDB``, which reads
    the request body, so ``mine`` / ``unassigned`` / ``team`` genuinely differ
    (the URL-prefix-only ``FakeHTTP`` would have frozen three identical lists
    and called it a baseline).

Nothing in these payloads is normalised away — every field is frozen exactly as
served today.

Deliberate contract changes recorded here (each landed with its golden edit):
  * the raw ``assignees`` array (source people IDs) was **dropped** from
    ``/api/tickets/*``; ``assignee_user_ids`` / ``assignee_names`` carry the
    resolved values and nothing in ``frontend/`` ever read the raw array
    (``Chat.jsx`` has a same-named field from the *runner* payload — different
    shape, different endpoint);
  * every ticket now carries ``uid``, the internal ``ticket_cache`` UUID. ``id``
    deliberately stays the Notion page id — deep links, trash and audit all key
    on it. ``uid`` is ``null`` whenever a ticket was served live rather than
    from the mirror, which is exactly what these goldens exercise: they seed no
    ``ticket_cache``, so ``TICKET_SOURCE=notion_cache`` falls back to live and
    produces the identical payload to ``TICKET_SOURCE=notion`` (the kill switch
    is pinned by ``tests/regression/test_ticket_source_switch.py``);
  * ``developers[]`` rows gained ``user_id`` (keying developers by display name
    breaks on duplicate names) and ``/api/sprint/summary`` gained
    ``by_assignee``. ``unassigned`` stayed — the in-meeting triage flow uses it.
  * ``/api/tickets/{id}`` gained **``body_markdown``** and **``body_sync_error``**
    (ticket body editing, plan Phase 3 §E). Only the *detail* response changed;
    the list rows are untouched, because shipping every ticket's body inside a
    list payload would be pure weight.
    ``body_markdown`` is what the editor opens with: the canonical copy in
    ``ticket_cache.body_markdown`` when we have one, otherwise the source body
    read back through the same markdown rules
    (``notion_blocks.rendered_to_markdown``). Without it the editor would open
    empty and "save" would silently mean "delete the body". It is ``null`` when
    the body could not be read at all — an unknown body must not be spelled as
    an empty one. In ``tickets_detail__ok`` it is the round-tripped fixture
    body, and the ``[image]`` block is absent on purpose: an image has no
    markdown form, and writing the ``[image] 원본에서 확인`` placeholder back
    would turn the placeholder into real text in Notion.
    ``body_sync_error`` is non-null only in the state this feature's save order
    creates — canonical body stored, push to Notion failed. That save answers
    200 by design (the user's text is safe), so the screen needs this field to
    avoid pretending the two sides agree.
    ``body_is_local`` says whether ``body_markdown`` is our canonical copy or a
    read-back approximation of the source. Our body pipeline is plain markdown,
    so saving an approximation flattens inline formatting (bold, links) and
    drops blocks that have no markdown form. The editor warns about that — but
    only in the approximation case, because once a canonical copy exists the
    save is lossless and a permanent warning is a warning nobody reads.
  * ``/api/sprint/summary`` gained **``burndown``** (plan Phase 3 §F). It is a
    *due-date* burndown, not a historical one, and the shape says so: two series
    over one day axis — ``planned`` (est_wd still due on or after that day,
    cancelled excluded) and ``open`` (the same, minus what is already done). No
    completion timestamp exists anywhere: ``ticket_cache`` mirrors only Notion's
    created/last-edited times, and last-edited moves when a title is fixed.
    Reconstructing "remaining work per day" from that would be invention, so the
    payload carries only what the data supports and the screen labels the two
    lines with exactly those words.
    ``developers``/``by_assignee`` were **not** touched: ``developers[].est_all``
    is already the per-person workload the WD-balance chart draws, and shipping
    the same numbers under a second name guarantees that one day only one of the
    two gets fixed.
  * the three ticket **lists** (``/mine``, ``/unassigned``, ``/team``) gained the
    repository's standard page envelope: ``items`` / ``total`` / ``page`` /
    ``page_size`` (Z11 — a production mirror of 1,058 tickets used to ship in a
    single response and the screen filtered it in the browser). The rows did not
    move: ``items`` is the same array in the same order, and ``total`` is the
    count **after** the filters and **before** the page is cut, so a screen can
    say "N total, showing 1-20".
    ``tickets`` is kept as an alias of ``items`` on purpose — the shipped
    ``frontend/`` reads that key and this change is backend-scoped. Drop the
    alias in the same change that moves the screens onto ``items``.
    ``page_size`` defaults to ``app/core/pagination.py::DEFAULT_PAGE_SIZE``, so
    these goldens (seven rows at most) are one full page and the arrays stayed
    byte-identical to the previous contract.
  * ``/api/team-chat`` responses are not in these goldens (no Notion round trip),
    but note for the reader that the same plan step widened them —
    ``members[]`` gained ``last_read_seq``/``online`` and messages gained
    ``mentions_me``; those are pinned by ``tests/integration/test_team_chat_*``.
"""

from __future__ import annotations

import difflib
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from app.core.security import hash_password
from app.notion_mapping.models import (
    SOURCE_MANUAL,
    STATUS_VERIFIED,
    UserNotionMapping,
)
from app.team_docs.models import (
    SYNC_STATE_ID,
    DocumentCache,
    DocumentFavorite,
    DocumentSyncState,
    join_names,
)
from app.users.models import User
from tests.fakes.clock import FakeClock
from tests.fakes.notion import (
    DEFAULT_PROJECTS_DB,
    FakeNotionTasksDB,
    project_row,
    task_row,
)

pytestmark = pytest.mark.regression

GOLDEN_DIR = Path(__file__).parent / "golden"

# Frozen "now": Tuesday 2026-07-14 09:00. Pins the monthly report's
# `generated_at` and the default sprint window (2026-07-13 .. 2026-07-20).
CONTRACT_NOW = datetime(2026, 7, 14, 9, 0, 0)
CONTRACT_PASSWORD = "Contract-Passw0rd!"
TOKEN_REF = "notion_report_token"

# ── fixed identities ─────────────────────────────────────────────────────────
U_ADMIN = "00000000-0000-4000-8000-00000000a001"
U_DEV = "00000000-0000-4000-8000-00000000a002"
U_NOMAP = "00000000-0000-4000-8000-00000000a003"
N_ADMIN = "notion-user-admin"
N_DEV = "notion-user-dev"
N_OUTSIDER = "notion-user-outsider"

SEED_USERS = (
    # (user_id, email, display_name, role, notion_user_id | None, mapping_id)
    (U_ADMIN, "contract-admin@goodmit.co.kr", "관리자 김", "admin", N_ADMIN,
     "00000000-0000-4000-8000-00000000b001"),
    (U_DEV, "contract-dev@goodmit.co.kr", "개발자 이", "user", N_DEV,
     "00000000-0000-4000-8000-00000000b002"),
    (U_NOMAP, "contract-nomap@goodmit.co.kr", "미연결 박", "user", None, None),
)

PROJ_ALPHA = "proj-alpha-0001"
PROJ_BETA = "proj-beta-0001"

PROJECT_ROWS = [
    project_row(page_id=PROJ_ALPHA, name="알파 프로젝트"),
    project_row(page_id=PROJ_BETA, name="베타 프로젝트"),
]

# Chosen so the three list endpoints cannot possibly agree:
#   mine (people contains N_ADMIN) → 101, 102, 107
#   unassigned (people is_empty, active only) → 104
#   team active=true → 101, 103, 104, 107 ; team active=false → all seven
DETAIL_PAGE_ID = "page-0001"
TASK_ROWS = [
    task_row(page_id=DETAIL_PAGE_ID, tid=101, title="관리자 진행 티켓", status="진행",
             due="2026-07-10", people=[N_ADMIN], est_wd=2.0, difficulty="3",
             priority="높음", project_ids=[PROJ_ALPHA]),
    task_row(page_id="page-0002", tid=102, title="공동 담당 완료 티켓", status="완료",
             due="2026-07-15", people=[N_ADMIN, N_DEV], est_wd=1.5, act_wd=2.0,
             difficulty="5", priority="보통", project_ids=[PROJ_ALPHA]),
    task_row(page_id="page-0003", tid=103, title="개발자 검증 티켓", status="검증",
             due="2026-07-20", people=[N_DEV], est_wd=3.0, difficulty="1",
             priority="낮음", project_ids=[PROJ_BETA]),
    task_row(page_id="page-0004", tid=104, title="미할당 계획 티켓", status="계획",
             due="2026-07-25", people=[], est_wd=0.5, project_ids=[PROJ_BETA]),
    task_row(page_id="page-0005", tid=105, title="미할당 완료 티켓", status="완료",
             due="2026-06-30", people=[], est_wd=1.0, act_wd=1.0, difficulty="3",
             priority="보통"),
    task_row(page_id="page-0006", tid=106, title="외부 담당자 취소 티켓", status="취소",
             due="2026-08-05", people=[N_OUTSIDER], est_wd=1.0, priority="높음",
             project_ids=[PROJ_ALPHA]),
    task_row(page_id="page-0007", tid=107, title="마감 없는 이슈 티켓", status="이슈",
             people=[N_ADMIN]),
]

TASK_BLOCKS = {
    DETAIL_PAGE_ID: [
        {"object": "block", "type": "heading_2",
         "heading_2": {"rich_text": [{"type": "text", "plain_text": "배경"}]}},
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "plain_text": "본문 한 줄."}]}},
        {"object": "block", "type": "to_do",
         "to_do": {"rich_text": [{"type": "text", "plain_text": "할 일"}], "checked": True}},
        {"object": "block", "type": "divider", "divider": {}},
        {"object": "block", "type": "image", "image": {}},
    ],
}

SEED_DOCS = (
    # (page_id, title, extra column overrides)
    ("doc-0001", "보안 점검 보고서", {
        "document_type": "보고서", "work_field": "보안",
        "tech_tags": ["Docker", "Linux"], "project_names": ["알파 프로젝트"],
        "status": "완료", "priority": "높음", "owner": "관리자 김",
        "author_names": ["관리자 김"], "doc_date": "2026-07-01",
        "last_edited": "2026-07-05T00:00:00.000Z",
        "url": "https://www.notion.so/doc-0001",
        "original_url": "https://example.invalid/original/doc-0001",
        "source_url": "https://example.invalid/source/doc-0001",
        "has_files": True,
    }),
    ("doc-0002", "주간 회의록", {
        "document_type": "회의록", "work_field": "개발",
        "tech_tags": ["Python"], "project_names": ["베타 프로젝트"],
        "status": "진행", "priority": "보통", "owner": "개발자 이",
        "author_names": ["개발자 이"], "doc_date": "2026-07-08",
        "last_edited": "2026-07-09T00:00:00.000Z",
        "url": "https://www.notion.so/doc-0002",
    }),
    ("doc-0003", "보관 처리된 문서", {"archived": True,
                                "last_edited": "2026-06-01T00:00:00.000Z"}),
)
DOC_SYNCED_AT = datetime(2026, 7, 14, 8, 0, 0)


# ── golden plumbing ──────────────────────────────────────────────────────────

def _canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def assert_golden(name: str, payload) -> None:
    """Compare against the frozen contract, or rewrite it when UPDATE_GOLDEN=1."""
    path = GOLDEN_DIR / f"{name}.json"
    actual = _canonical(payload)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
        return
    assert path.is_file(), (
        f"missing golden {path.name}. If this endpoint/state is new, review the "
        f"payload and commit it with UPDATE_GOLDEN=1."
    )
    expected = path.read_text(encoding="utf-8")
    if expected == actual:
        return
    diff = "\n".join(difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile=f"golden/{path.name} (committed contract)",
        tofile=f"golden/{path.name} (this run)",
        lineterm="",
    ))
    pytest.fail(
        f"API contract drift in {path.name}.\n"
        f"If this change is intended, commit the updated golden in the SAME change "
        f"(UPDATE_GOLDEN=1). Otherwise the response regressed.\n\n{diff}"
    )


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_clock():
    """Override the session-wide fake clock so this module's `now` is pinned."""
    return FakeClock(CONTRACT_NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=TASK_ROWS, projects=PROJECT_ROWS, blocks=TASK_BLOCKS,
        projects_db=DEFAULT_PROJECTS_DB,
        fail_message="계약 테스트용 강제 오류",
    ).install(fake_http)


def _write_token(settings) -> None:
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")


def _seed_users(db) -> None:
    for uid, email, name, role, _notion_id, _mapping_id in SEED_USERS:
        db.add(User(
            id=uid, email=email, display_name=name, role=role, active=True,
            password_hash=hash_password(CONTRACT_PASSWORD), must_change_password=False,
        ))
    db.flush()  # users must land before the mappings that reference them (FK)
    for uid, email, _name, _role, notion_id, mapping_id in SEED_USERS:
        if not notion_id:
            continue
        db.add(UserNotionMapping(
            id=mapping_id, user_id=uid, notion_user_id=notion_id,
            notion_email=email, status=STATUS_VERIFIED, source=SOURCE_MANUAL,
            last_verified_at=DOC_SYNCED_AT,
        ))
    db.commit()


def _seed_documents(db) -> None:
    for page_id, title, over in SEED_DOCS:
        fields = dict(over)
        for key in ("tech_tags", "project_names", "author_names"):
            if key in fields:
                fields[key] = join_names(fields[key])
        db.add(DocumentCache(
            id=f"cache-{page_id}", notion_page_id=page_id, title=title,
            synced_at=DOC_SYNCED_AT, **fields,
        ))
    db.add(DocumentFavorite(id="fav-0001", user_id=U_ADMIN,
                            notion_page_id="doc-0001", created_at=DOC_SYNCED_AT))
    # The single sync-state row may already exist (migration seed) — pin it either way.
    state = db.get(DocumentSyncState, SYNC_STATE_ID)
    if state is None:
        state = DocumentSyncState(id=SYNC_STATE_ID)
        db.add(state)
    state.status = "ok"
    state.last_run_at = DOC_SYNCED_AT
    state.last_success_at = DOC_SYNCED_AT
    state.doc_count = 2
    state.error = None
    state.updated_at = DOC_SYNCED_AT
    db.commit()


@pytest.fixture()
def contract_client(client, db, notion):
    """Authenticated client over a fully seeded, fully deterministic app."""
    _seed_users(db)
    _seed_documents(db)
    response = client.post(
        "/login",
        json={"email": "contract-admin@goodmit.co.kr", "password": CONTRACT_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture(params=["ok", "not_configured", "query_error"])
def notion_state(request, settings, notion) -> str:
    """(a) configured + healthy, (b) token missing, (c) Notion returns an error."""
    state = request.param
    if state != "not_configured":
        _write_token(settings)          # (b) is precisely "no token file"
    if state == "query_error":
        notion.fail_status = 500
    return state


# Every Notion-backed read endpoint, with the exact query string that is frozen.
# `/api/sprint/summary` is the real path (there is no bare `/api/sprint`); the
# period on the monthly report is pinned so the golden never depends on "today".
NOTION_ENDPOINTS = [
    ("tickets_mine", "/api/tickets/mine"),
    ("tickets_unassigned", "/api/tickets/unassigned"),
    ("tickets_team_active", "/api/tickets/team?active=true"),
    ("tickets_team_all", "/api/tickets/team?active=false"),
    ("tickets_meta", "/api/tickets/meta"),
    ("tickets_projects", "/api/tickets/projects"),
    ("tickets_detail", f"/api/tickets/{DETAIL_PAGE_ID}"),
    ("sprint_summary", "/api/sprint/summary"),
    ("dev_monthly", "/api/admin/reports/dev-monthly?period=2026-07"),
]


@pytest.mark.parametrize("name,path", NOTION_ENDPOINTS, ids=[n for n, _ in NOTION_ENDPOINTS])
def test_notion_backed_endpoint_contract(contract_client, notion_state, name, path):
    """Freeze every Notion-backed read in all three states.

    All three states answer 200 by design — these routers translate a missing
    token into ``configured:false`` and a Notion failure into ``ok:false`` so the
    screen can render an explanation instead of an error page.
    """
    response = contract_client.get(path)
    assert response.status_code == 200, response.text
    assert_golden(f"{name}__{notion_state}", response.json())


# ── team docs ────────────────────────────────────────────────────────────────
# `/api/team-docs` has no (b) "not configured" or (c) "Notion error" state: the
# list is served entirely from the local mirror (DocumentCache) precisely so it
# survives Notion being down (§17.4). The only thing that varies with Notion
# health is the sync/staleness block, so that is what the third case freezes.

def test_team_docs_list_contract(contract_client):
    response = contract_client.get("/api/team-docs")
    assert response.status_code == 200, response.text
    assert_golden("team_docs_list__ok", response.json())


def test_team_docs_filtered_contract(contract_client):
    response = contract_client.get("/api/team-docs?work_field=개발")
    assert response.status_code == 200, response.text
    assert_golden("team_docs_list__filtered", response.json())


def test_team_docs_stale_sync_contract(contract_client, db):
    """Same list, but the mirror is stale and the last sync failed."""
    state = db.get(DocumentSyncState, SYNC_STATE_ID)
    state.status = "error"
    state.last_run_at = datetime(2026, 7, 14, 8, 30, 0)
    state.last_success_at = datetime(2026, 7, 10, 8, 0, 0)
    state.error = "Notion 조회에 실패했습니다."
    db.commit()
    response = contract_client.get("/api/team-docs")
    assert response.status_code == 200, response.text
    assert_golden("team_docs_list__sync_error", response.json())


# ── the fake must actually read the body ─────────────────────────────────────

def test_fake_is_body_aware_three_queries_three_row_sets(contract_client, settings, notion):
    """mine / unassigned / team must come back *different* from the same fake.

    This is the guard on the golden itself: with the URL-prefix-only FakeHTTP all
    three of these return byte-identical lists, and the frozen contract would be
    describing a bug in the test harness rather than the app.
    """
    _write_token(settings)

    def tids(path: str) -> list[int]:
        body = contract_client.get(path).json()
        assert body["ok"] is True, body
        return [t["tid"] for t in body["tickets"]]

    mine = tids("/api/tickets/mine")
    unassigned = tids("/api/tickets/unassigned")
    team_active = tids("/api/tickets/team?active=true")
    team_all = tids("/api/tickets/team?active=false")

    assert mine == [101, 102, 107]            # people contains me, due ascending
    assert unassigned == [104]                # people is_empty, terminal dropped
    assert team_active == [101, 103, 104, 107]
    assert team_all == [105, 101, 102, 103, 104, 106, 107]
    assert len({tuple(mine), tuple(unassigned), tuple(team_active), tuple(team_all)}) == 4

    # …and the differences come from filters the fake actually parsed.
    filters = [q.get("filter") for q in notion.queries]
    assert {"property": "티켓 담당자", "people": {"contains": N_ADMIN}} in filters
    assert {"property": "티켓 담당자", "people": {"is_empty": True}} in filters
    assert None in filters                    # the unfiltered team query
