"""THIS FILE IS THE API CONTRACT.

The JSON under ``tests/regression/golden/`` is the byte-for-byte response shape
that ``frontend/`` is built against. A diff here is never "just a test failure":
it means a shipped response changed. Any diff must be an **intentional** commit
that edits the golden file in the same change, with a message saying what moved
and why. Never regenerate the goldens to make a red build green.

Regenerating (only alongside a deliberate contract change)::

    UPDATE_GOLDEN=1 .venv/Scripts/python.exe -m pytest tests/regression/test_api_contract_golden.py

qa-contract-replaced-by: tests/regression/test_ticket_source_switch.py

That file froze the ``TICKET_SOURCE`` kill switch: it booted the same seed under
``notion_cache`` and ``notion`` and demanded byte-identical payloads, then
checked both against these goldens. The setting is gone (S14) and there is one
implementation left, so "the two modes agree" is a sentence about nothing. Its
second half — the served payload matches the committed contract — is what this
module does on every run, and it now does it over the path that ships.

Determinism rules this module holds itself to:
  * users, mappings, projects, tickets and cached documents are inserted with
    **fixed** primary keys — never ``create_user``/``default=new_uuid``, whose
    UUID4 keys would leak into ``assignee_user_ids`` / ``uid`` / ``project_uid``
    and churn the golden on every run;
  * the clock is frozen (``CONTRACT_NOW``), which pins ``generated_at`` on the
    monthly report and the default sprint window;
  * the seeded ticket rows are chosen so ``mine`` / ``unassigned`` / ``team``
    genuinely differ — a frozen contract in which three lists happen to be
    identical describes nothing.

Nothing in these payloads is normalised away — every field is frozen exactly as
served today.

Deliberate contract changes recorded here (each landed with its golden edit):
  * the raw ``assignees`` array (source people IDs) was **dropped** from
    ``/api/tickets/*``; ``assignee_user_ids`` / ``assignee_names`` carry the
    resolved values and nothing in ``frontend/`` ever read the raw array
    (``Chat.jsx`` has a same-named field from the *runner* payload — different
    shape, different endpoint);
  * every ticket carries ``uid``, the internal row UUID. ``id`` deliberately
    stays the imported page id — deep links, trash and audit all key on it.
  * ``developers[]`` rows gained ``user_id`` (keying developers by display name
    breaks on duplicate names) and ``/api/sprint/summary`` gained
    ``by_assignee``. ``unassigned`` stayed — the in-meeting triage flow uses it.
  * ``/api/tickets/{id}`` gained **``body_markdown``** and **``body_sync_error``**
    (ticket body editing, plan Phase 3 §E). Only the *detail* response changed;
    the list rows are untouched, because shipping every ticket's body inside a
    list payload would be pure weight.
    ``body_markdown`` is what the editor opens with. It is ``null`` when the
    body could not be read at all — an unknown body must not be spelled as an
    empty one.
    ``body_is_local`` says whether ``body_markdown`` is our canonical copy or a
    read-back approximation. Since S14 there is only one record, so it is
    ``true`` for every ticket that has a body at all.
  * every ticket carries ``key`` — the canonical display name
    ``<PROJECT_CODE>-<SEQ>`` derived by the DB trigger (S14 · D-282). It is
    ``null`` for a ticket that has no number yet, which is the case throughout
    these goldens: the seeded rows carry the imported ticket number but no
    server-allocated sequence. The field exists because the screens used to
    build the name themselves by prefixing ``tid`` with ``"GIT-"``; once the old
    codes are discarded (D-283) that string names nothing.
  * ``/api/sprint/summary`` gained **``burndown``** (plan Phase 3 §F). It is a
    *due-date* burndown, not a historical one, and the shape says so: two series
    over one day axis — ``planned`` (est_wd still due on or after that day,
    cancelled excluded) and ``open`` (the same, minus what is already done). No
    completion timestamp exists anywhere, so the payload carries only what the
    data supports and the screen labels the two lines with exactly those words.
  * the three ticket **lists** (``/mine``, ``/unassigned``, ``/team``) gained the
    repository's standard page envelope: ``items`` / ``total`` / ``page`` /
    ``page_size`` (Z11 — a production mirror of 1,058 tickets used to ship in a
    single response and the screen filtered it in the browser). The rows did not
    move: ``items`` is the same array in the same order, and ``total`` is the
    count **after** the filters and **before** the page is cut.
    ``tickets`` is kept as an alias of ``items`` on purpose — the shipped
    ``frontend/`` reads that key. Drop the alias in the same change that moves
    the screens onto ``items``.
  * ``/api/tickets/team`` gained **``can_sync``** (FN-03 — the sync trigger button
    had no frontend caller; ``TeamTickets.jsx`` reads this to decide whether to
    render it). ``/mine`` and ``/unassigned`` were **not** touched.
    S14 **removed it again**, from ``/api/tickets/team`` and ``/api/team-docs``
    alike, along with ``/api/team-docs``'s ``sync`` block: there is no mirror to
    refresh, so the button has nothing to trigger and the freshness block has
    nothing to report. Leaving either would have the screen offer an action that
    does nothing and a badge that ages forever.
  * 🔴 **S14 — the goldens now describe the only path there is.** Every payload
    here used to be captured three times: configured-and-healthy, token-missing,
    and source-returned-an-error. Those last two states came from a second
    record living behind an HTTP call. There is no such call any more, so the
    two extra captures could only be produced by faking a failure the product
    cannot have — a frozen contract for an unreachable state is worse than no
    contract, because a screen written against it will never be exercised.
    ``<name>__not_configured.json`` and ``<name>__query_error.json`` were
    deleted; ``<name>__ok.json`` stays under the same name.
    The response **keys** did not move: the routers still answer
    ``configured: true`` / ``ok: true`` on this path, so ``frontend/`` reads the
    same fields it always did. Three values did change, and each is the record
    telling the truth rather than the mirror hedging: ``uid`` is now the real
    row id instead of ``null``, ``project_uid`` is filled for a ticket whose
    project resolved, and the list responses carry no ``sync`` block at all
    (there is nothing that can go stale, and a "synced N minutes ago" badge
    would age forever).
  * 🔴 **S14 A3 — the imported Notion URL is gone from every payload.** Tickets
    dropped ``url``; documents dropped ``url`` / ``original_url`` /
    ``source_url``; trash rows dropped ``url``; the monthly report's per-ticket
    rows dropped ``url``; the WBS nodes dropped ``url``. All 110 documents and
    all 1,133 tickets carried an ``app.notion.com`` address, and since the
    record moved to this server that address opens a copy nobody edits any
    more. A screen that offers it as "the original" sends the reader to the one
    place today's edit is missing. The columns stay in the database as an import
    trace; only the exposure is gone.
  * 🔴 **S14 A3 — the ticket and document detail dropped ``body_is_local`` and
    ``body_sync_error``, and the body ``PUT`` dropped ``synced``.** All three
    described a state that only exists when the record lives in two places:
    "saved here, could not push there". There is nowhere to push, so the save is
    always lossless and there is nothing to disagree with. Every imported
    document row still reads ``body_is_local = false``, so leaving the field
    would have the editor warn on all 110 of them about formatting it does not
    actually lose.
  * 🔴 **S14 A3 — the project payload dropped its six import traces**
    (``notion_page_id``, ``notion_progress_pct``, ``notion_status``,
    ``notion_missing_at``, ``notion_synced_at``, ``notion_sync_error``), and
    ``notion_status`` left ``EDITABLE_FIELDS`` with them. Nothing writes those
    columns any more, so the values froze at import time and the screens turned
    them into a badge and a banner that no user action could ever clear.
"""

from __future__ import annotations

import difflib
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from app.core.models_base import join_names as names
from app.core.security import hash_password
from app.notion_mapping.models import (
    SOURCE_MANUAL,
    STATUS_VERIFIED,
    UserNotionMapping,
)
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.team_docs.models import (
    SYNC_STATE_ID,
    DocumentCache,
    DocumentSyncState,
    join_names,
)
from app.tickets.models import PROJECT_LINK_OK, PROJECT_LINK_UNRESOLVED, TicketCache
from app.users.models import User
from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.regression

GOLDEN_DIR = Path(__file__).parent / "golden"

# Frozen "now": Tuesday 2026-07-14 09:00. Pins the monthly report's
# `generated_at` and the default sprint window (2026-07-13 .. 2026-07-20).
CONTRACT_NOW = datetime(2026, 7, 14, 9, 0, 0)
CONTRACT_PASSWORD = "Contract-Passw0rd!"

# ── fixed identities ─────────────────────────────────────────────────────────
U_ADMIN = "00000000-0000-4000-8000-00000000a001"
U_DEV = "00000000-0000-4000-8000-00000000a002"
U_NOMAP = "00000000-0000-4000-8000-00000000a003"
N_ADMIN = "notion-user-admin"
N_DEV = "notion-user-dev"
N_OUTSIDER = "notion-user-outsider"

SEED_USERS = (
    # (user_id, email, display_name, role, source user id | None, mapping_id)
    (U_ADMIN, "contract-admin@goodmit.co.kr", "관리자 김", "admin", N_ADMIN,
     "00000000-0000-4000-8000-00000000b001"),
    (U_DEV, "contract-dev@goodmit.co.kr", "개발자 이", "user", N_DEV,
     "00000000-0000-4000-8000-00000000b002"),
    (U_NOMAP, "contract-nomap@goodmit.co.kr", "미연결 박", "user", None, None),
)

# Imported page ids of the two projects, and the fixed Portal row ids they map to.
PROJ_ALPHA = "proj-alpha-0001"
PROJ_BETA = "proj-beta-0001"
# A third external id with **no Portal row** — the "we cannot tell which project
# this ticket belongs to" state (`project_link != ok`), which one seeded ticket is in.
PROJ_ORPHAN = "proj-orphan-0001"

SEED_PROJECTS = (
    ("00000000-0000-4000-8000-00000000c001", PROJ_ALPHA, "알파 프로젝트"),
    ("00000000-0000-4000-8000-00000000c002", PROJ_BETA, "베타 프로젝트"),
)
PROJECT_UID = {external: uid for uid, external, _name in SEED_PROJECTS}
PROJECT_NAME = {external: name for _uid, external, name in SEED_PROJECTS}

# Chosen so the three list endpoints cannot possibly agree:
#   mine (assignee contains N_ADMIN) → 101, 102, 107
#   unassigned (no assignee, active only) → 104
#   team active=true → 101, 103, 104, 107 ; team active=false → all seven
DETAIL_PAGE_ID = "page-0001"
# 상세 골든이 얼어붙이는 본문. 체크박스 줄은 **일부러** 둔다 — 우리 본문 파이프라인에는
# 체크박스 노드가 없어서(D-198) 그 줄은 `[x]` 를 글자로 가진 글머리 항목이 된다. 이관해 온
# 본문에 실제로 있는 모양이라, 골든이 그 결과를 그대로 적어 두는 편이 화면을 만드는 사람에게
# 정직하다. 「보기 이상하니 고친다」로 표본을 바꾸면 그 사실이 계약에서 사라진다.
DETAIL_BODY = "## 배경\n본문 한 줄.\n- [x] 할 일\n---"

SEED_TICKETS = (
    # (row_id, page_id, tid, title, status, due, assignees, est, act, difficulty,
    #  priority, external project id)
    ("00000000-0000-4000-8000-00000000d001", DETAIL_PAGE_ID, 101, "관리자 진행 티켓",
     "진행", "2026-07-10", [N_ADMIN], 2.0, None, "3", "높음", PROJ_ALPHA),
    ("00000000-0000-4000-8000-00000000d002", "page-0002", 102, "공동 담당 완료 티켓",
     "완료", "2026-07-15", [N_ADMIN, N_DEV], 1.5, 2.0, "5", "보통", PROJ_ALPHA),
    ("00000000-0000-4000-8000-00000000d003", "page-0003", 103, "개발자 검증 티켓",
     "검증", "2026-07-20", [N_DEV], 3.0, None, "1", "낮음", PROJ_BETA),
    ("00000000-0000-4000-8000-00000000d004", "page-0004", 104, "미할당 계획 티켓",
     "계획", "2026-07-25", [], 0.5, None, None, None, PROJ_BETA),
    ("00000000-0000-4000-8000-00000000d005", "page-0005", 105, "미할당 완료 티켓",
     "완료", "2026-06-30", [], 1.0, 1.0, "3", "보통", PROJ_ORPHAN),
    ("00000000-0000-4000-8000-00000000d006", "page-0006", 106, "외부 담당자 취소 티켓",
     "취소", "2026-08-05", [N_OUTSIDER], 1.0, None, None, "높음", PROJ_ALPHA),
    ("00000000-0000-4000-8000-00000000d007", "page-0007", 107, "마감 없는 이슈 티켓",
     "이슈", None, [N_ADMIN], None, None, None, None, PROJ_ALPHA),
)

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
def notion(fake_http):
    """A fake Notion server with nothing in it — a counterexample instrument.

    이 계약이 고정하는 응답은 전부 우리 표에서 나온다. 어느 경로가 다시 바깥을 읽기
    시작하면 티켓 한 건 없는 이 작업 DB 가 그 사실을 드러낸다. 페이크를 안 붙이면 그
    회귀는 골든이 그대로 통과하는 방식으로 조용히 지나간다.
    """
    from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB

    return FakeNotionTasksDB(
        rows=[], projects=[], projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


def _seed_users(db) -> None:
    for uid, email, name, role, _source_id, _mapping_id in SEED_USERS:
        db.add(User(
            id=uid, email=email, display_name=name, role=role, active=True,
            password_hash=hash_password(CONTRACT_PASSWORD), must_change_password=False,
        ))
    db.flush()  # users must land before the mappings that reference them (FK)
    for uid, email, _name, _role, source_id, mapping_id in SEED_USERS:
        if not source_id:
            continue
        db.add(UserNotionMapping(
            id=mapping_id, user_id=uid, notion_user_id=source_id,
            notion_email=email, status=STATUS_VERIFIED, source=SOURCE_MANUAL,
            last_verified_at=DOC_SYNCED_AT,
        ))
    db.commit()


def _seed_projects(db) -> None:
    for uid, external, name in SEED_PROJECTS:
        db.add(Project(id=uid, name=name, org_id=DEFAULT_ORG_ID, notion_page_id=external))
    db.commit()


def _seed_tickets(db) -> None:
    """The seven rows the ticket contract is captured over.

    ``project_link`` is what decides whether a ticket has a resolvable owner
    (0060). Six rows resolve; ``page-0005`` points at a project that has no
    Portal row, so it stays ``unresolved`` — that state is part of the frozen
    contract (``project_uid: null``) and it exists in the imported data.
    """
    for (row_id, page_id, tid, title, status, due, assignees, est, act,
         difficulty, priority, external) in SEED_TICKETS:
        resolved = external in PROJECT_UID
        db.add(TicketCache(
            id=row_id, notion_page_id=page_id, org_id=DEFAULT_ORG_ID,
            notion_ticket_number=tid, url=f"https://www.notion.so/{page_id}",
            title=title, status=status, due_date=due,
            est_wd=est, act_wd=act, difficulty=difficulty, priority=priority,
            project_ids=names([external]),
            project_names=names([PROJECT_NAME[external]] if resolved else []),
            project_uid=PROJECT_UID.get(external),
            project_link=PROJECT_LINK_OK if resolved else PROJECT_LINK_UNRESOLVED,
            assignee_notion_ids=names(assignees),
            body_markdown=DETAIL_BODY if page_id == DETAIL_PAGE_ID else None,
            synced_at=DOC_SYNCED_AT, created_at=DOC_SYNCED_AT, updated_at=DOC_SYNCED_AT,
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
    # 즐겨찾기 씨앗은 여기 없다 (S14 · C2) — 그 축은 정본 문서로 옮겨 갔고 이 골든이 재는
    # 미러 목록 응답에는 더 이상 `is_favorite` 이 없다.
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
    _seed_projects(db)
    _seed_tickets(db)
    _seed_documents(db)
    response = client.post(
        "/login",
        json={"email": "contract-admin@goodmit.co.kr", "password": CONTRACT_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


# Every ticket-backed read endpoint, with the exact query string that is frozen.
# `/api/sprint/summary` is the real path (there is no bare `/api/sprint`); the
# period on the monthly report is pinned so the golden never depends on "today".
READ_ENDPOINTS = [
    ("tickets_mine", "/api/tickets/mine"),
    ("tickets_unassigned", "/api/tickets/unassigned"),
    ("tickets_team_active", "/api/tickets/team?active=true"),
    ("tickets_team_all", "/api/tickets/team?active=false"),
    ("tickets_meta", "/api/tickets/meta"),
    # ⚠️ `/api/tickets/projects` 는 0060 부터 **Portal 을 읽는다** — 프로젝트는 티켓의
    # 소속을 정하므로 그 목록의 정본이 외부일 수 없다.
    ("tickets_projects", "/api/tickets/projects"),
    ("tickets_detail", f"/api/tickets/{DETAIL_PAGE_ID}"),
    ("sprint_summary", "/api/sprint/summary"),
    ("dev_monthly", "/api/admin/reports/dev-monthly?period=2026-07"),
]


@pytest.mark.parametrize("name,path", READ_ENDPOINTS, ids=[n for n, _ in READ_ENDPOINTS])
def test_read_endpoint_contract(contract_client, name, path):
    """Freeze every ticket-backed read.

    There is one state to capture. The token-missing and source-error captures
    are gone with the source itself — see the S14 entry in the module docstring.
    """
    response = contract_client.get(path)
    assert response.status_code == 200, response.text
    assert_golden(f"{name}__ok", response.json())


# ── team docs ────────────────────────────────────────────────────────────────
# `/api/team-docs` is served entirely from the local table. Its third capture —
# "the same list while the last sync failed" — is gone with the sync: the
# response no longer carries a `sync` block at all, so that golden was a
# byte-for-byte copy of `__ok` and froze nothing. The sync-state row is still
# seeded, because the contract now includes the fact that its contents do **not**
# reach the response.

def test_team_docs_list_contract(contract_client):
    response = contract_client.get("/api/team-docs")
    assert response.status_code == 200, response.text
    assert_golden("team_docs_list__ok", response.json())


def test_team_docs_filtered_contract(contract_client):
    response = contract_client.get("/api/team-docs?work_field=개발")
    assert response.status_code == 200, response.text
    assert_golden("team_docs_list__filtered", response.json())


def test_a_failed_sync_row_no_longer_reaches_the_response(contract_client, db):
    """장부에 실패가 적혀 있어도 목록은 그 사실을 나르지 않는다.

    이 시험이 없으면 「신선도 블록이 사라졌다」는 골든 하나가 우연히 그렇게 나온 것인지,
    정말로 어떤 상태에서도 안 나가는 것인지 구별되지 않는다. 실패한 동기화 행을 남겨 두고
    같은 응답을 다시 받아 본다.
    """
    state = db.get(DocumentSyncState, SYNC_STATE_ID)
    state.status = "error"
    state.last_run_at = datetime(2026, 7, 14, 8, 30, 0)
    state.last_success_at = datetime(2026, 7, 10, 8, 0, 0)
    state.error = "문서 동기화에 실패했습니다."
    db.commit()
    body = contract_client.get("/api/team-docs").json()
    assert "sync" not in body
    assert "can_sync" not in body
    assert [d["title"] for d in body["items"]] == ["주간 회의록", "보안 점검 보고서"]


# ── the sample must actually make the three lists differ ─────────────────────

def test_three_lists_three_row_sets(contract_client):
    """mine / unassigned / team must come back *different* from the same data.

    This is the guard on the golden itself: if the filters stopped being applied
    all three would be byte-identical, and the frozen contract would be
    describing a broken query rather than the app.
    """
    def tids(path: str) -> list[int]:
        body = contract_client.get(path).json()
        assert body["ok"] is True, body
        return [t["tid"] for t in body["tickets"]]

    mine = tids("/api/tickets/mine")
    unassigned = tids("/api/tickets/unassigned")
    team_active = tids("/api/tickets/team?active=true")
    team_all = tids("/api/tickets/team?active=false")

    assert mine == [101, 102, 107]            # assignee contains me, due ascending
    assert unassigned == [104]                # no assignee, terminal dropped
    assert team_active == [101, 103, 104, 107]
    assert team_all == [105, 101, 102, 103, 104, 106, 107]
    assert len({tuple(mine), tuple(unassigned), tuple(team_active), tuple(team_all)}) == 4


def test_the_frozen_payloads_needed_no_outbound_call(contract_client, fake_http):
    """반례 확인 — 이 계약이 정말 우리 표만 읽고 만들어졌는가.

    계측기가 0 을 세는지 확인하려면 그 계측기가 1 도 셀 수 있어야 한다. 그 검증은
    `tests/unit/test_fake_notion.py` 가 따로 한다.
    """
    for _name, path in READ_ENDPOINTS:
        assert contract_client.get(path).status_code == 200
    contract_client.get("/api/team-docs")
    assert fake_http.requests == [], (
        f"골든을 만드는 동안 바깥으로 나간 요청이 있다: "
        f"{[str(r.url) for r in fake_http.requests]}"
    )
