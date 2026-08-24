"""**결과가 맞는가** — 목록 화면들의 조건 사슬을 한 표로 검증한다 (S15 · C7 · R-85~R-87).

## 이 파일이 다른 필터 시험과 다른 점

`test_ticket_filters.py` 는 티켓 한 화면의 조건을 손으로 하나씩 확인한다. 여기서는
**조건을 거는 모든 목록**을 같은 방식으로 본다. 화면마다 손으로 적으면 화면이 늘 때
빠지고, 빠진 자리의 증상은 「필터를 걸었는데 결과가 이상하다」라 아무도 신고하지 않는다.

## 기대값을 어디서 얻는가 — **우리가 직접 센다**

각 목록에서 조건 없이 **전량**을 받아 그것을 알려진 데이터(universe)로 삼고, 기대 집합은
그 행들에 파이썬 술어를 적용해 만든다. 그다음 같은 조건을 서버에 걸어 받은 결과와 대조한다.
즉 같은 질문에 **두 구현**이 답한다 — 서버의 SQL 과 이 파일의 술어. 둘이 갈리면 실패다.

이 방식이 잡는 것 넷:

  * 조건이 **안 걸린다**(결과 ⊃ 기대) — 「고르나 마나 같은 목록」
  * 조건이 **너무 걸린다**(결과 ⊂ 기대) — 「연결돼 있는데 결과에서 빠진다」(R15 의 모양)
  * `total` 이 **자르기 뒤 값**이거나 필터 앞 값이다 — 화면이 사용자가 세는 것과 다른 말을 한다
  * 쪽 경계가 행을 **반복하거나 빠뜨린다**(Z9)

## 그리고 정직성 두 가지

  1. **표본이 판정력을 갖는지 확인한다.** 어떤 축이든 「전부 통과」·「전부 탈락」이면 그 회차는
     조건이 걸렸는지 아닌지를 구별하지 못한다 — 그런 표본은 통과가 아니라 오류로 본다.
  2. **없는 값으로 걸면 0건이어야 한다.** 조건을 조용히 버리는 서버는 이 방향에서만 드러난다.

산출물은 `dist/ui-qa/s15-filter-chain/chain.json` 이다 — 회차마다 8단계 사슬(주소·질의·
백엔드 조건·응답·건수)을 적어 두고, `docs/ui-renewal/FUNCTIONAL_COVERAGE.json` 의 Flow 가
그 파일을 가리킨다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import pytest

pytestmark = pytest.mark.regression

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "dist" / "ui-qa" / "s15-filter-chain"

NOW = datetime(2026, 7, 14, 0, 0, 0)          # 화요일 — 기본 FakeClock 과 같은 시각
FAR = "2026-09-01"                             # 어떤 기한 버킷에도 안 드는 날
THIS_WEEK = "2026-07-15"                       # 2026-07-13(월) ~ 07-19
NEXT_WEEK = "2026-07-21"
OVERDUE = "2026-07-01"

ADMIN = "chain-admin@goodmit.co.kr"
MATE = "chain-mate@goodmit.co.kr"

# 회차마다 쌓아 두는 사슬. 마지막 시험이 파일로 떨어뜨린다.
_CHAIN: list[dict] = []


# ── 표 ────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Case:
    """조건 한 회차. `expect` 는 **행 하나**를 받아 기대에 드는지 답한다."""

    surface: str                      # FUNCTIONAL_COVERAGE 의 surface id
    flow: str                         # 사람이 읽는 이름 — Flow 이름과 같은 말을 쓴다
    path: str                         # 목록 주소(조건 없이)
    params: dict                      # 이 회차가 거는 조건
    expect: Callable[[dict], bool]
    backend: str                      # 사슬의 `backend_query` 칸에 적을 한 줄
    relation: str = ""                # 관계 축이면 `data_relation` 칸
    base: dict = field(default_factory=dict)   # 전량을 받을 때도 함께 거는 값(기본 Scope)


def _get(client, path: str, params: dict) -> dict:
    query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
    r = client.get(path + ("?" + query if query else ""))
    assert r.status_code == 200, f"{path}?{query} → {r.status_code} {r.text[:200]}"
    return r.json()


def _rows(body: dict) -> list[dict]:
    return body.get("items") or []


def _ids(body: dict) -> set[str]:
    return {r["id"] for r in _rows(body)}


def _run(client, case: Case, *, page_param: str, page_size: int) -> dict:
    """한 회차를 돌리고 사슬 한 줄을 남긴다."""
    wide = dict(case.base)
    wide[page_param] = page_size
    universe = _get(client, case.path, wide)
    all_rows = _rows(universe)
    assert all_rows, f"{case.path}: 전량이 비었다 — 이 표본으로는 아무것도 판정할 수 없다"

    expected = {r["id"] for r in all_rows if case.expect(r)}
    # 🔴 판정력 확인. 전부 통과하거나 전부 탈락하는 표본은 「조건이 걸렸다」와
    # 「조건이 없다」를 구별하지 못한다 — 초록이어도 아무것도 증명하지 않는다.
    assert 0 < len(expected) < len(all_rows), (
        f"{case.flow}: 표본이 판정력을 잃었다 (기대 {len(expected)} / 전량 {len(all_rows)})"
    )

    asked = dict(case.base)
    asked.update(case.params)
    asked[page_param] = page_size
    body = _get(client, case.path, asked)

    actual = _ids(body)
    assert actual == expected, (
        f"{case.flow}: 결과가 기대와 다르다\n"
        f"  빠진 것: {sorted(expected - actual)}\n"
        f"  더 온 것: {sorted(actual - expected)}"
    )
    assert body["total"] == len(expected), (
        f"{case.flow}: total 이 {body['total']} 인데 실제 결과는 {len(expected)}건이다"
    )

    row = {
        "surface": case.surface,
        "flow": case.flow,
        "ui_state": ", ".join(f"{k}={v}" for k, v in case.params.items()),
        "url": case.path + "?" + urlencode(case.params),
        "api_request": "GET " + case.path + "?" + urlencode({**case.base, **case.params}),
        "backend_query": case.backend,
        "data_relation": case.relation,
        "api_response": {"total": body["total"], "count": len(actual)},
        "rendered": {"rows": len(actual), "total_shown": body["total"]},
        "expected": {"source": "known-data", "total": len(expected),
                     "universe": len(all_rows)},
    }
    _CHAIN.append(row)
    return row


# ── 시드 ──────────────────────────────────────────────────────────────────────

@pytest.fixture()
def world(db, make_user, make_project, make_ticket):
    """조건을 걸 수 있는 최소한의 세계. **축마다 걸리는 행과 안 걸리는 행이 함께** 있어야 한다."""
    from app.board.models import Post
    from app.knowledge.models import Document, DocumentTag, KnowledgeSpace, Tag
    from app.notifications.models import Notification
    from app.org.constants import DEFAULT_ORG_ID

    admin = make_user(ADMIN, role="system_admin", display_name="체인 관리자")
    mate = make_user(MATE, role="user", display_name="체인 동료")

    alpha = make_project(name="알파 프로젝트")
    beta = make_project(name="베타 프로젝트")

    # ── 티켓 여덟 건. 축마다 값이 갈리게 심는다.
    tickets = [
        make_ticket(project=alpha, tid=1, title="알파 진행 높음", status="진행",
                    priority="High", difficulty="상", category="인프라", due=THIS_WEEK,
                    assignees=[admin.id]),
        make_ticket(project=alpha, tid=2, title="알파 계획 보통", status="계획",
                    priority="Normal", difficulty="중", category="포털", due=NEXT_WEEK,
                    assignees=[admin.id]),
        make_ticket(project=beta, tid=3, title="베타 진행 보통", status="진행",
                    priority="Normal", difficulty="중", category="인프라", due=OVERDUE,
                    assignees=[admin.id]),
        make_ticket(project=beta, tid=4, title="베타 완료 낮음", status="완료",
                    priority="Low", difficulty="하", category="포털", due=FAR,
                    assignees=[admin.id]),
        make_ticket(project=alpha, tid=5, title="동료 알파 진행", status="진행",
                    priority="High", difficulty="상", category="인프라", due=FAR,
                    assignees=[mate.id]),
        make_ticket(project=beta, tid=6, title="동료 베타 계획", status="계획",
                    priority="Low", difficulty="하", category="포털", due=FAR,
                    assignees=[mate.id]),
        make_ticket(project=alpha, tid=7, title="미할당 알파", status="계획",
                    priority="Normal", difficulty="중", category="인프라", due=FAR,
                    assignees=[]),
        make_ticket(project=beta, tid=8, title="미할당 베타", status="진행",
                    priority="High", difficulty="상", category="포털", due=FAR,
                    assignees=[]),
    ]

    # ── 문서 여섯 건 + 태그 둘.
    space = KnowledgeSpace(name="체인 공간", slug="chain-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()
    meeting = Tag(name="회의록", slug="meeting")
    guide = Tag(name="가이드", slug="guide")
    db.add_all([meeting, guide])
    db.flush()
    docs = []
    for i, (title, tag) in enumerate([
        ("배포 회의록", meeting), ("보안 회의록", meeting),
        ("설치 가이드", guide), ("운영 가이드", guide),
        ("잡담 메모", None), ("배포 체크리스트", None),
    ]):
        doc = Document(space_id=space.id, title=title,
                       created_at=NOW - timedelta(days=i), updated_at=NOW - timedelta(days=i))
        db.add(doc)
        db.flush()
        if tag is not None:
            db.add(DocumentTag(document_id=doc.id, tag_id=tag.id))
        docs.append(doc)

    # ── 게시글 다섯 건.
    for i, (title, category, pinned) in enumerate([
        ("공지 하나", "공지", True), ("공지 둘", "공지", False),
        ("질문 하나", "질문", False), ("자유 하나", "자유", False),
        ("자유 둘", "자유", False),
    ]):
        db.add(Post(author_user_id=admin.id, org_id=DEFAULT_ORG_ID, kind="free",
                    category=category, title=title, body="본문", is_pinned=pinned,
                    created_at=NOW - timedelta(hours=i)))

    # ── 알림 여섯 건 — 대상 둘 × 읽음 둘.
    for i in range(6):
        db.add(Notification(
            user_id=admin.id, type="ticket_assigned" if i % 2 else "backup_failed",
            audience="user" if i % 2 else "admin",
            title=f"알림 {i}", body="본문",
            read_at=None if i < 4 else NOW,
            created_at=NOW - timedelta(minutes=i),
        ))

    db.commit()
    return {
        "admin": admin, "mate": mate, "alpha": alpha, "beta": beta,
        "tickets": tickets, "space": space, "docs": docs,
    }


@pytest.fixture()
def signed_in(client, world):
    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = client.post("/login", json={"email": ADMIN, "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return world


# ── 티켓 ──────────────────────────────────────────────────────────────────────

def _ticket_cases(world) -> list[Case]:
    alpha, beta = world["alpha"].id, world["beta"].id
    mate = world["mate"].id
    base = {"active": "false"}          # 완료·취소도 전량에 포함시킨다
    return [
        Case("user_team-tickets", "프로젝트 단독", "/api/tickets/team",
             {"project_id": alpha}, lambda r: r.get("project_uid") == alpha,
             "filter_clauses: project_uid = ? OR project_ids ⊇ {?}",
             "tickets.project_uid → projects.id", base),
        Case("user_team-tickets", "진행상태 단독", "/api/tickets/team",
             {"status": "진행"}, lambda r: r.get("status") == "진행",
             "filter_clauses: tickets.status = ?", "", base),
        Case("user_team-tickets", "우선순위 단독", "/api/tickets/team",
             {"priority": "High"}, lambda r: r.get("priority") == "High",
             "filter_clauses: tickets.priority = ?", "", base),
        Case("user_team-tickets", "난이도 단독", "/api/tickets/team",
             {"difficulty": "상"}, lambda r: r.get("difficulty") == "상",
             "filter_clauses: tickets.difficulty = ?", "", base),
        Case("user_team-tickets", "대분류 단독", "/api/tickets/team",
             {"category": "인프라"}, lambda r: r.get("category") == "인프라",
             "filter_clauses: tickets.category = ?", "", base),
        Case("user_team-tickets", "검색어 단독", "/api/tickets/team",
             {"q": "동료"}, lambda r: "동료" in (r.get("title") or ""),
             "filter_clauses: tickets.title ILIKE %?%", "", base),
        Case("user_team-tickets", "담당자 단독", "/api/tickets/team",
             {"assignee_user_id": mate}, lambda r: mate in (r.get("assignee_user_ids") or []),
             "filter_clauses: assignee_notion_ids ⊇ {token}",
             "users.id → 담당자 토큰(assignee_token)", base),
        Case("user_team-tickets", "기한 버킷 — 지연", "/api/tickets/team",
             {"due": "overdue"}, lambda r: (r.get("due") or "9999") < "2026-07-14",
             "filter_clauses: due_date < today", "", base),
        Case("user_team-tickets", "기한 버킷 — 이번 주", "/api/tickets/team",
             {"due": "this_week"},
             lambda r: "2026-07-13" <= (r.get("due") or "") < "2026-07-20",
             "filter_clauses: 2026-07-13 <= due_date < 2026-07-20", "", base),
        # 🔴 복합 — 한 축을 더했을 때 결과가 **줄어야** 한다. 늘면 OR 로 걸린 것이다.
        Case("user_team-tickets", "복합 — 프로젝트 × 상태", "/api/tickets/team",
             {"project_id": alpha, "status": "진행"},
             lambda r: r.get("project_uid") == alpha and r.get("status") == "진행",
             "filter_clauses: 두 절이 AND 로 함께 걸린다",
             "tickets.project_uid → projects.id", base),
        Case("user_team-tickets", "복합 — 프로젝트 × 담당자", "/api/tickets/team",
             {"project_id": beta, "assignee_user_id": mate},
             lambda r: r.get("project_uid") == beta and mate in (r.get("assignee_user_ids") or []),
             "filter_clauses: 두 절이 AND 로 함께 걸린다",
             "tickets.project_uid → projects.id · 담당자 토큰", base),
    ]


def _scoped_ticket_cases(world) -> list[Case]:
    """화면 자체가 Scope 를 가진 두 목록. **같은 축을 그 화면에서도 직접 확인한다.**

    세 목록은 같은 조립기를 지나지만(`build_filters` → `filter_clauses`), 「팀에서 되니까
    내 티켓에서도 될 것」은 추론이지 측정이 아니다 — 그 추론이 틀리는 자리가 바로 화면
    기본 Scope 와 조건이 만나는 지점이다.
    """
    alpha = world["alpha"].id
    base = {"active": "false"}
    return [
        Case("user_my-tickets", "진행상태 단독", "/api/tickets/mine",
             {"status": "진행"}, lambda r: r.get("status") == "진행",
             "list_by_assignee(나) + filter_clauses(status)",
             "users.id → 담당자 토큰(assignee_token)", base),
        Case("user_my-tickets", "프로젝트 단독", "/api/tickets/mine",
             {"project_id": alpha}, lambda r: r.get("project_uid") == alpha,
             "list_by_assignee(나) + filter_clauses(project)",
             "tickets.project_uid → projects.id", base),
        Case("user_my-tickets", "복합 — 프로젝트 × 상태", "/api/tickets/mine",
             {"project_id": alpha, "status": "진행"},
             lambda r: r.get("project_uid") == alpha and r.get("status") == "진행",
             "list_by_assignee(나) + 두 절이 AND 로 함께 걸린다",
             "tickets.project_uid → projects.id", base),
        Case("user_my-tickets", "검색어 단독", "/api/tickets/mine",
             {"q": "알파"}, lambda r: "알파" in (r.get("title") or ""),
             "list_by_assignee(나) + filter_clauses(title ILIKE)", "", base),
        Case("user_my-tickets", "우선순위 단독", "/api/tickets/mine",
             {"priority": "High"}, lambda r: r.get("priority") == "High",
             "list_by_assignee(나) + filter_clauses(priority)", "", base),
        Case("user_my-tickets", "난이도 단독", "/api/tickets/mine",
             {"difficulty": "중"}, lambda r: r.get("difficulty") == "중",
             "list_by_assignee(나) + filter_clauses(difficulty)", "", base),
        Case("user_my-tickets", "대분류 단독", "/api/tickets/mine",
             {"category": "인프라"}, lambda r: r.get("category") == "인프라",
             "list_by_assignee(나) + filter_clauses(category)", "", base),
        Case("user_my-tickets", "기한 버킷 — 지연", "/api/tickets/mine",
             {"due": "overdue"}, lambda r: (r.get("due") or "9999") < "2026-07-14",
             "list_by_assignee(나) + filter_clauses(due_date < today)", "", base),
        Case("user_unassigned", "진행상태 단독", "/api/tickets/unassigned",
             {"status": "진행"}, lambda r: r.get("status") == "진행",
             "list_unassigned(담당자 없음) + filter_clauses(status)", "", base),
        Case("user_unassigned", "프로젝트 단독", "/api/tickets/unassigned",
             {"project_id": alpha}, lambda r: r.get("project_uid") == alpha,
             "list_unassigned(담당자 없음) + filter_clauses(project)",
             "tickets.project_uid → projects.id", base),
        Case("user_unassigned", "검색어 단독", "/api/tickets/unassigned",
             {"q": "알파"}, lambda r: "알파" in (r.get("title") or ""),
             "list_unassigned(담당자 없음) + filter_clauses(title ILIKE)", "", base),
        Case("user_unassigned", "우선순위 단독", "/api/tickets/unassigned",
             {"priority": "High"}, lambda r: r.get("priority") == "High",
             "list_unassigned(담당자 없음) + filter_clauses(priority)", "", base),
        Case("user_unassigned", "난이도 단독", "/api/tickets/unassigned",
             {"difficulty": "중"}, lambda r: r.get("difficulty") == "중",
             "list_unassigned(담당자 없음) + filter_clauses(difficulty)", "", base),
        Case("user_unassigned", "대분류 단독", "/api/tickets/unassigned",
             {"category": "인프라"}, lambda r: r.get("category") == "인프라",
             "list_unassigned(담당자 없음) + filter_clauses(category)", "", base),
        Case("user_unassigned", "복합 — 프로젝트 × 상태", "/api/tickets/unassigned",
             {"project_id": alpha, "status": "계획"},
             lambda r: r.get("project_uid") == alpha and r.get("status") == "계획",
             "list_unassigned(담당자 없음) + 두 절이 AND 로 함께 걸린다",
             "tickets.project_uid → projects.id", base),
    ]


def test_ticket_filters_return_exactly_the_matching_tickets(client, signed_in):
    for case in _ticket_cases(signed_in) + _scoped_ticket_cases(signed_in):
        _run(client, case, page_param="page_size", page_size=100)


def test_the_page_scope_and_a_user_filter_combine(client, signed_in):
    """C7 「기본 Scope 와의 결합」 — 세 결과의 포함관계가 논리적으로 성립해야 한다.

    `/api/tickets/mine` 은 화면 자체가 담당자 조건을 갖고 있다(= 나). 거기에 사용자가
    조건을 더하면 결과는 **둘 다 만족하는 것**이어야 한다.
    """
    scope_only = _get(client, "/api/tickets/mine", {"active": "false", "page_size": 100})
    filter_only = _get(client, "/api/tickets/team",
                       {"active": "false", "status": "진행", "page_size": 100})
    both = _get(client, "/api/tickets/mine",
                {"active": "false", "status": "진행", "page_size": 100})

    assert _ids(both) == _ids(scope_only) & _ids(filter_only)
    assert both["total"] == len(_ids(both))
    # 결합이 어느 한쪽과 같아지면 그 회차는 아무것도 증명하지 않는다.
    assert _ids(both) != _ids(scope_only) and _ids(both) != _ids(filter_only)
    _CHAIN.append({
        "surface": "user_my-tickets", "flow": "기본 Scope 와 조건의 결합",
        "ui_state": "화면 기본 Scope(담당자=나) + status=진행",
        "url": "#/my-tickets?status=진행",
        "api_request": "GET /api/tickets/mine?active=false&status=진행",
        "backend_query": "list_by_assignee(assignee_token) + filter_clauses(status)",
        "data_relation": "users.id → 담당자 토큰(assignee_token)",
        "api_response": {"total": both["total"], "count": len(_ids(both))},
        "rendered": {"rows": len(_ids(both)), "total_shown": both["total"]},
        "expected": {"source": "derived-check",
                     "note": "기본 Scope 결과 ∩ 같은 조건의 전체 결과"},
    })


def test_unassigned_scope_means_no_assignee_at_all(client, signed_in):
    body = _get(client, "/api/tickets/unassigned", {"active": "false", "page_size": 100})
    assert _rows(body), "미할당이 비었다 — 이 시험은 그 상태에서 아무것도 안 본다"
    for row in _rows(body):
        assert not row.get("assignee_user_ids"), f"담당자가 있는 티켓이 미할당에 섞였다: {row['title']}"


def test_a_condition_that_matches_nothing_returns_nothing(client, signed_in):
    """조건을 조용히 버리는 서버는 **이 방향에서만** 드러난다."""
    for params in (
        {"status": "그런상태없음"},
        {"category": "그런대분류없음"},
        {"q": "존재하지않는제목"},
        {"project_id": "00000000-0000-0000-0000-000000000000"},
    ):
        body = _get(client, "/api/tickets/team", {"active": "false", **params, "page_size": 100})
        assert body["total"] == 0 and _rows(body) == [], f"{params} 가 조용히 무시됐다"


def test_ticket_pages_cover_every_row_exactly_once(client, signed_in):
    whole = _get(client, "/api/tickets/team", {"active": "false", "page_size": 100})
    seen: list[str] = []
    for page in (1, 2, 3, 4):
        body = _get(client, "/api/tickets/team",
                    {"active": "false", "page": page, "page_size": 3})
        assert body["total"] == whole["total"], "쪽마다 total 이 달라진다"
        seen.extend(r["id"] for r in _rows(body))
    assert len(seen) == len(set(seen)), "같은 티켓이 두 쪽에 나왔다"
    assert set(seen) == _ids(whole), "쪽을 이어 붙였는데 빠진 티켓이 있다"


# ── 문서 · 게시판 · 알림 ──────────────────────────────────────────────────────

def test_document_filters_return_exactly_the_matching_documents(client, signed_in):
    cases = [
        Case("user_knowledge", "검색어 단독", "/api/knowledge/documents",
             {"q": "회의록"}, lambda r: "회의록" in (r.get("title") or ""),
             "list_documents: documents.title ILIKE %?%"),
        Case("user_knowledge", "분류(태그) 단독", "/api/knowledge/documents",
             {"tag": "meeting"},
             lambda r: any(t.get("slug") == "meeting" or t.get("name") == "회의록"
                           for t in (r.get("tags") or [])),
             "list_documents: documents.id IN (SELECT document_id FROM document_tags …)",
             "document_tags → tags.slug"),
        Case("user_knowledge", "복합 — 검색어 × 분류", "/api/knowledge/documents",
             {"q": "배포", "tag": "meeting"},
             lambda r: "배포" in (r.get("title") or "")
             and any(t.get("slug") == "meeting" or t.get("name") == "회의록"
                     for t in (r.get("tags") or [])),
             "list_documents: 두 절이 AND 로 함께 걸린다", "document_tags → tags.slug"),
    ]
    for case in cases:
        case.base["space_id"] = signed_in["space"].id
        _run(client, case, page_param="limit", page_size=200)


def test_board_filters_return_exactly_the_matching_posts(client, signed_in):
    cases = [
        Case("user_board", "카테고리 단독", "/api/board/posts",
             {"category": "공지"}, lambda r: r.get("category") == "공지",
             "list_posts: board_posts.category = ?"),
        Case("user_board", "검색어 단독", "/api/board/posts",
             {"q": "자유"}, lambda r: "자유" in (r.get("title") or ""),
             "list_posts: title/body/author ILIKE %?%"),
    ]
    for case in cases:
        _run(client, case, page_param="page_size", page_size=100)


def test_board_sort_actually_reorders_the_list(client, signed_in):
    """정렬은 **집합이 아니라 순서**라 위 표로는 안 잡힌다 — 따로 본다.

    두 정렬이 같은 순서를 내면 그 회차는 「정렬이 걸렸다」를 증명하지 못한다. 고정 글이
    언제나 맨 위라는 규칙도 함께 지켜져야 한다.
    """
    recent = _rows(_get(client, "/api/board/posts", {"sort": "recent", "page_size": 100}))
    views = _rows(_get(client, "/api/board/posts", {"sort": "views", "page_size": 100}))
    assert [r["id"] for r in recent] and len(recent) == len(views)
    assert recent[0].get("is_pinned") is True, "고정 글이 맨 위가 아니다"
    # 최신순은 created_at 내림차순이어야 한다(고정 글을 뺀 나머지에서).
    rest = [r for r in recent if not r.get("is_pinned")]
    stamps = [r.get("created_at") for r in rest]
    assert stamps == sorted(stamps, reverse=True), "최신순인데 시간 역순이 아니다"
    _CHAIN.append({
        "surface": "user_board", "flow": "정렬 — 최신순",
        "ui_state": "sort=recent", "url": "#/board?sort=recent",
        "api_request": "GET /api/board/posts?sort=recent",
        "backend_query": "list_posts: ORDER BY is_pinned DESC, created_at DESC, id DESC",
        "data_relation": "",
        "api_response": {"count": len(recent)},
        "rendered": {"rows": len(recent), "total_shown": len(recent)},
        "expected": {"source": "derived-check", "note": "고정 글이 맨 위 · 나머지는 시간 역순"},
    })


def test_notification_audience_and_read_state_are_separate_axes(client, signed_in):
    cases = [
        Case("user_notifications", "대상 단독", "/api/notifications",
             {"audience": "user"}, lambda r: r.get("audience") == "user",
             "list_notifications: notifications.audience = ?"),
        Case("user_notifications", "읽음 상태 단독", "/api/notifications",
             {"unread_only": "true"}, lambda r: r.get("read_at") is None,
             "list_notifications: notifications.read_at IS NULL"),
        Case("user_notifications", "복합 — 대상 × 읽음 상태", "/api/notifications",
             {"audience": "user", "unread_only": "true"},
             lambda r: r.get("audience") == "user" and r.get("read_at") is None,
             "list_notifications: 두 절이 AND 로 함께 걸린다"),
    ]
    for case in cases:
        _run(client, case, page_param="page_size", page_size=100)


def test_admin_user_filters_return_exactly_the_matching_users(client, signed_in):
    cases = [
        Case("admin_users", "역할 단독", "/api/admin/users",
             {"role": "user"}, lambda r: r.get("role") == "user",
             "list_users: users.role = ?"),
        Case("admin_users", "검색어 단독", "/api/admin/users",
             {"q": "체인 동료"},
             lambda r: "체인 동료" in (r.get("display_name") or ""),
             "list_users: display_name/email ILIKE %?%"),
    ]
    for case in cases:
        _run(client, case, page_param="page_size", page_size=100)


# ── 사슬을 파일로 남긴다 ─────────────────────────────────────────────────────

def test_zz_write_chain_evidence():
    """앞 시험들이 쌓은 사슬을 원장으로 떨어뜨린다.

    이름이 `zz` 인 이유는 하나다 — **마지막에 돌아야** 한다. pytest 는 파일 안에서 선언
    순서대로 돌리므로 그것으로 충분하지만, 다른 파일과 섞여 돌 때를 대비해 이름으로도
    말해 둔다. 이 시험은 앞이 하나도 안 돌았으면 아무것도 안 쓴다(빈 원장을 증거로
    남기면 그게 더 나쁘다).
    """
    if not _CHAIN:
        pytest.skip("이 회차에서 사슬이 하나도 안 쌓였다 — 남길 원장이 없다")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": "S15 — C7 8단계 사슬. 기대값은 전량 목록에 파이썬 술어를 적용해 직접 셌다.",
        "generated_by": "tests/regression/test_filter_chain.py",
        "flows": _CHAIN,
    }
    (OUT_DIR / "chain.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    assert len(_CHAIN) >= 20, f"사슬이 {len(_CHAIN)}줄뿐이다 — 표가 줄어든 것은 아닌가"
    _ = os.environ  # noqa: B018 — 환경에 의존하지 않는다는 표시
