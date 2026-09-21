"""검색 정규화 행렬 — **모든 검색창이 같은 규칙으로 찾는가** (D-495).

## 무엇을 못박는가

사용자 요구는 한 줄이다: 「현황 제외」라는 제목은 「현황제외」로 쳐도 찾아져야 하고, 앞뒤
공백 · 낱말 사이 공백 · 영문 대소문자 · 전각 표기 · NFD 한글이 결과를 바꾸면 안 된다.
`%` · `_` · `\\` 는 와일드카드가 아니라 글자다. 그리고 **의미를 바꾸는 퍼지는 없다.**

규칙은 `app/core/search_text.py` 하나이고, 그 규칙을 지나는 검색 표면은 목록 · 작업 보드 ·
통합 검색 · AI 검색에 흩어져 있다. 한 곳만 옛 방식으로 남아도 그 화면에서만 「검색이 안
된다」가 되고, 그 차이는 오류를 안 낸다. 그래서 사례 일곱을 **표면 전부**에 같은 방식으로 댄다.

## 판정

표면마다 같은 아홉 행을 심는다(`ITEMS`). 사례마다 검색어를 보내고, 심은 행 중에서 걸린
것이 **정확히** 기대한 행인지 본다 — 더 걸려도(와일드카드가 샌 것) 덜 걸려도(대상 쪽을
안 접은 것) 실패다. 심지 않은 행(로그인한 관리자 같은)은 판정에 넣지 않는다.

C7 은 뜻이 다르다. 제로폭 공백(U+200B) 하나만 붙여 넣은 검색어는 접으면 빈 값이다.
목록에서는 **조건이 아니다** — 검색어가 없을 때와 같은 목록이 나와야 한다(`LIKE '%%'` 로
전 행을 거는 것과 결과는 같아도 뜻이 다르다). 통합 검색에서는 **빈 결과**다.

각 표면은 먼저 검색어 없이 불러 심은 아홉 행이 **전부 보이는지** 확인한다. 안 보이면 권한이나
범위가 가린 것이라 그 뒤의 판정은 아무것도 증명하지 않는다.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import pytest

from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    D_A1,
    D_B1,
    org_tree,
    people,
)

pytestmark = pytest.mark.integration

ADMIN = "matrix-admin@goodmit.co.kr"
NOW = datetime(2026, 9, 21, 9, 0, 0)

BACKSLASH = "\\"
ZERO_WIDTH_SPACE = chr(0x200B)


def _fullwidth(text: str) -> str:
    """ASCII 를 전각 표기로. U+FF01~U+FF5E 는 ASCII 0x21~0x7E 를 그대로 옮긴 자리다."""
    return "".join(chr(ord(ch) + 0xFEE0) for ch in text)


def _nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


#: 표면마다 같은 아홉 행. 값이 곧 그 행의 검색 대상 글이다.
ITEMS: dict[str, str] = {
    "spaced": "현황 제외 보고서",
    "joined": "현황제외 목록",
    "brand": "ClovirONE 배포 계획",
    "nfc": "주간 회의록",
    "nfd": _nfd("월간 보고"),
    "percent": "달성률 100% 확인",
    "underscore": "snake_case 규칙",
    "backslash": "C:" + BACKSLASH + "temp 경로",
    "plain": "평범한 제목",
}

#: 「조건이 아니다」 — 검색어가 없을 때와 같은 목록이어야 한다.
NO_FILTER = None


@dataclass(frozen=True)
class Case:
    name: str
    queries: tuple[tuple[str, frozenset[str] | None], ...]


def _keys(*names: str) -> frozenset[str]:
    return frozenset(names)


CASES = (
    Case("C1-joined-and-spaced", (
        ("현황제외", _keys("spaced", "joined")),
        ("현황 제외", _keys("spaced", "joined")),
    )),
    Case("C2-padded-and-repeated-spaces", (
        ("  현황   제외 ", _keys("spaced", "joined")),
    )),
    Case("C3-letter-case", (
        ("ClovirONE", _keys("brand")),
        ("clovirone", _keys("brand")),
        ("CLOVIRONE", _keys("brand")),
    )),
    Case("C4-full-width", (
        (_fullwidth("ClovirONE"), _keys("brand")),
    )),
    Case("C5-nfd-hangul", (
        (_nfd("회의록"), _keys("nfc")),
        ("월간 보고", _keys("nfd")),
    )),
    Case("C6-literal-like-metacharacters", (
        ("%", _keys("percent")),
        ("_", _keys("underscore")),
        (BACKSLASH, _keys("backslash")),
    )),
    Case("C7-lone-zero-width-space", (
        (ZERO_WIDTH_SPACE, NO_FILTER),
    )),
)


# ── 세계 ──────────────────────────────────────────────────────────────────────


@dataclass
class World:
    client: object
    db: object
    admin: object
    csrf: str
    team: object
    project: object
    make_user: object
    make_ticket: object
    make_project: object
    make_space: object
    make_knowledge_document: object
    extra: dict = field(default_factory=dict)

    @property
    def headers(self) -> dict:
        return {"X-CSRF-Token": self.csrf}

    def get(self, path: str, params: dict) -> dict:
        response = self.client.get(path, params=params, headers=self.headers)
        assert response.status_code == 200, f"{path} {params} → {response.status_code} {response.text[:300]}"
        return response.json()


@pytest.fixture()
def world(client, db, make_user, login_as, make_project, make_ticket, make_space,
          make_knowledge_document):
    """관리자 한 명 · 팀 하나 · 그 팀의 프로젝트 하나. 작업 보드는 팀을 먼저 고르므로
    관리자를 그 팀에 두고 프로젝트도 그 팀 것으로 만든다 — 그래야 판·백로그가 이 행들을 본다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    team = Department(name="매트릭스팀", org_id=DEFAULT_ORG_ID)
    db.add(team)
    db.flush()
    admin = make_user(ADMIN, role="system_admin", display_name="매트릭스 관리자")
    admin.department_id = team.id
    db.commit()
    project = make_project(name="매트릭스 프로젝트", dept=team)
    csrf = login_as("system_admin", email=ADMIN)
    return World(
        client=client, db=db, admin=admin, csrf=csrf, team=team, project=project,
        make_user=make_user, make_ticket=make_ticket, make_project=make_project,
        make_space=make_space, make_knowledge_document=make_knowledge_document,
    )


def _ids(items, key: str = "id") -> set[str]:
    return {str(item[key]) for item in items}


# ── 표면: 심기와 읽기 ─────────────────────────────────────────────────────────
#
# `seed(world) -> {항목 키: 그 표면이 돌려주는 id}` · `found(world, q) -> {id}`.
# `q` 가 None 이면 검색어 없이 부른다.


def _seed_tickets(world: World, *, assigned: bool) -> dict[str, str]:
    out = {}
    for key, text in ITEMS.items():
        row = world.make_ticket(
            page_id=f"mx-{key}", project=world.project, title=text,
            assignees=[world.admin.id] if assigned else [],
        )
        out[key] = row.notion_page_id
    return out


def _ticket_list(scope: str):
    def found(world: World, q: str | None) -> set[str]:
        params = {"active": "false", "page_size": 100}
        if q is not None:
            params["q"] = q
        return _ids(world.get(f"/api/tickets/{scope}", params)["items"])
    return found


def _seed_board_tickets(world: World) -> dict[str, str]:
    out = {}
    for index, (key, text) in enumerate(ITEMS.items(), start=1):
        row = world.make_ticket(project=world.project, title=text, status="진행")
        row.backlog_rank = Decimal(1000 * index)
        out[key] = row.id
    world.db.commit()
    return out


def _board_params(world: World, q: str | None, **extra) -> dict:
    params = {"department_id": world.team.id, **extra}
    if q is not None:
        params["q"] = q
    return params


def _found_board(world: World, q: str | None) -> set[str]:
    body = world.get("/api/work/board", _board_params(world, q, column_page_size=100))
    cards = [card for column in body["columns"] for card in column["cards"]]
    return _ids(cards + list(body["unclassified"]))


def _found_board_column(world: World, q: str | None) -> set[str]:
    body = world.get("/api/work/board/columns/진행", _board_params(world, q, limit=100))
    return _ids(body["cards"])


def _found_backlog(world: World, q: str | None) -> set[str]:
    return _ids(world.get("/api/work/backlog", _board_params(world, q, limit=100))["items"])


def _seed_projects(world: World) -> dict[str, str]:
    return {key: world.make_project(name=text, dept=world.team).id for key, text in ITEMS.items()}


def _found_projects(world: World, q: str | None) -> set[str]:
    params = {"page_size": 100, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/projects", params)["items"])


def _seed_users(world: World) -> dict[str, str]:
    out = {}
    for key, text in ITEMS.items():
        user = world.make_user(f"mx-{key}@goodmit.co.kr", role="user", display_name=text)
        out[key] = user.id
        world.extra.setdefault("email_of", {})[user.email] = user.id
    return out


def _found_admin_users(world: World, q: str | None) -> set[str]:
    params = {"page_size": 100, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/admin/users", params)["items"])


def _found_users_csv(world: World, q: str | None) -> set[str]:
    response = world.client.get(
        "/api/admin/users/export/csv", params={} if q is None else {"q": q}, headers=world.headers,
    )
    assert response.status_code == 200, response.text[:300]
    rows = list(csv.reader(io.StringIO(response.text.lstrip(chr(0xFEFF)))))
    emails = {row[0] for row in rows[1:] if row}
    email_of = world.extra["email_of"]
    return {email_of[email] for email in emails if email in email_of} | {
        email for email in emails if email not in email_of
    }


def _found_people(world: World, q: str | None) -> set[str]:
    params = {"limit": 500, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/admin/people", params)["items"])


def _knowledge_space(world: World):
    if "space" not in world.extra:
        world.extra["space"] = world.make_space(name="매트릭스 공간", org_wide=True)
    return world.extra["space"]


def _seed_knowledge_titles(world: World) -> dict[str, str]:
    space = _knowledge_space(world)
    return {
        key: world.make_knowledge_document(space=space, title=text, text="문서 본문입니다.").id
        for key, text in ITEMS.items()
    }


def _seed_knowledge_bodies(world: World) -> dict[str, str]:
    space = _knowledge_space(world)
    return {
        key: world.make_knowledge_document(space=space, title=f"문서 {index}", text=text).id
        for index, (key, text) in enumerate(ITEMS.items(), start=1)
    }


def _found_knowledge(world: World, q: str | None) -> set[str]:
    params = {"limit": 200, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/knowledge/documents", params)["items"])


def _seed_posts(world: World, *, field_name: str) -> dict[str, str]:
    from app.board.models import Post
    from app.org.constants import DEFAULT_ORG_ID

    out = {}
    for index, (key, text) in enumerate(ITEMS.items(), start=1):
        author = world.admin
        title, body = f"게시글 {index}", "게시글 본문"
        if field_name == "title":
            title = text
        elif field_name == "body":
            body = text
        else:
            author = world.make_user(f"mx-author-{key}@goodmit.co.kr", role="user", display_name=text)
        post = Post(
            author_user_id=author.id, org_id=DEFAULT_ORG_ID, kind="free", category="자유",
            title=title, body=body, created_at=NOW, updated_at=NOW,
        )
        world.db.add(post)
        world.db.flush()
        out[key] = post.id
    world.db.commit()
    return out


def _found_posts(world: World, q: str | None) -> set[str]:
    params = {"page_size": 100, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/board/posts", params)["items"])


def _seed_conversations(world: World, *, in_message: bool) -> dict[str, str]:
    from app.conversations.models import Conversation, Message

    out = {}
    for index, (key, text) in enumerate(ITEMS.items(), start=1):
        conversation = Conversation(
            user_id=world.admin.id, title=f"대화 {index}" if in_message else text,
        )
        world.db.add(conversation)
        world.db.flush()
        if in_message:
            world.db.add(Message(
                conversation_id=conversation.id, message_id=f"mx-{key}",
                role="user", content=text,
            ))
        out[key] = conversation.id
    world.db.commit()
    return out


def _found_conversations(world: World, q: str | None) -> set[str]:
    params = {"limit": 1000, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/conversations", params)["items"])


def _seed_announcements(world: World, *, in_body: bool) -> dict[str, str]:
    from app.announcements.models import Announcement

    out = {}
    for index, (key, text) in enumerate(ITEMS.items(), start=1):
        row = Announcement(
            title=f"공지 {index}" if in_body else text,
            body=text if in_body else "공지 본문",
        )
        world.db.add(row)
        world.db.flush()
        out[key] = row.id
    world.db.commit()
    return out


def _found_announcements(world: World, q: str | None) -> set[str]:
    params = {"page_size": 100, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/admin/announcements", params)["items"])


def _seed_team_docs(world: World, *, as_author: bool) -> dict[str, str]:
    from app.core.models_base import utcnow
    from app.team_docs.models import DocumentCache, join_names

    out = {}
    for index, (key, text) in enumerate(ITEMS.items(), start=1):
        row = DocumentCache(
            notion_page_id=f"mx-{key}",
            title=f"팀 문서 {index}" if as_author else text,
            author_names=join_names([text]) if as_author else "",
            owner_kind="organization", synced_at=utcnow(),
        )
        world.db.add(row)
        out[key] = row.notion_page_id
    world.db.commit()
    return out


def _found_team_docs(world: World, q: str | None) -> set[str]:
    params = {"page_size": 100, **({} if q is None else {"q": q})}
    return _ids(world.get("/api/team-docs", params)["items"])


SURFACES = {
    "tickets-team": (lambda w: _seed_tickets(w, assigned=False), _ticket_list("team")),
    "tickets-mine": (lambda w: _seed_tickets(w, assigned=True), _ticket_list("mine")),
    "tickets-unassigned": (lambda w: _seed_tickets(w, assigned=False), _ticket_list("unassigned")),
    "work-board": (_seed_board_tickets, _found_board),
    "work-board-column": (_seed_board_tickets, _found_board_column),
    "work-backlog": (_seed_board_tickets, _found_backlog),
    "projects": (_seed_projects, _found_projects),
    "admin-users": (_seed_users, _found_admin_users),
    "admin-users-csv": (_seed_users, _found_users_csv),
    "people-picker": (_seed_users, _found_people),
    "knowledge-title": (_seed_knowledge_titles, _found_knowledge),
    "knowledge-body": (_seed_knowledge_bodies, _found_knowledge),
    "board-title": (lambda w: _seed_posts(w, field_name="title"), _found_posts),
    "board-body": (lambda w: _seed_posts(w, field_name="body"), _found_posts),
    "board-author": (lambda w: _seed_posts(w, field_name="author"), _found_posts),
    "conversations-title": (lambda w: _seed_conversations(w, in_message=False), _found_conversations),
    "conversations-message": (lambda w: _seed_conversations(w, in_message=True), _found_conversations),
    "announcements-title": (lambda w: _seed_announcements(w, in_body=False), _found_announcements),
    "announcements-body": (lambda w: _seed_announcements(w, in_body=True), _found_announcements),
    "team-docs-title": (lambda w: _seed_team_docs(w, as_author=False), _found_team_docs),
    "team-docs-author": (lambda w: _seed_team_docs(w, as_author=True), _found_team_docs),
}


def _sweep(check) -> list[str]:
    """사례 일곱의 검색어 전부를 한 세계에 댄다. 실패는 모아서 한 번에 말한다.

    사례마다 시험을 따로 세우면 세계(앱 · 관리자 · 로그인)를 사례 수만큼 다시 만든다 —
    판정은 같고 비용만 일곱 배다. 대신 어느 사례의 어느 검색어가 틀렸는지를 전부 적는다.
    """
    failures: list[str] = []
    for case in CASES:
        for query, expected in case.queries:
            problem = check(query, expected)
            if problem:
                failures.append(f"{case.name} · {query!r}: {problem}")
    return failures


def _checked_queries() -> int:
    return sum(len(case.queries) for case in CASES)


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_every_list_search_folds_both_sides(world, surface):
    seed, found = SURFACES[surface]
    seeded = seed(world)
    assert len(seeded) == len(ITEMS)
    everything = found(world, None)
    missing = set(seeded.values()) - everything
    assert not missing, (
        f"{surface}: 검색어 없이 불렀는데 심은 행이 안 보인다 — 범위가 가렸고 판정이 헛돈다: {missing}"
    )
    wanted_ids = set(seeded.values())
    checked: list[str] = []

    def check(query: str, expected) -> str | None:
        checked.append(query)
        got = found(world, query)
        if expected is NO_FILTER:
            if got != everything:
                return (
                    "접으면 빈 검색어가 조건처럼 걸렸다 — "
                    f"빠진 것 {sorted(everything - got)} · 더 온 것 {sorted(got - everything)}"
                )
            return None
        hit = {key for key, item_id in seeded.items() if item_id in got}
        if hit != set(expected) or got & wanted_ids != {seeded[key] for key in expected}:
            return f"{sorted(hit)} 를 찾았다 — 기대 {sorted(expected)}"
        return None

    failures = _sweep(check)
    assert len(checked) == _checked_queries() >= 13, f"검색어를 {len(checked)}개만 댔다"
    assert failures == [], f"{surface}:\n  " + "\n  ".join(failures)


# ── 작업 보드 「맨 위로」의 `position_q` ──────────────────────────────────────


def test_move_to_top_ranks_against_the_same_folded_backlog(world):
    """「맨 위로」는 **지금 화면이 보는 백로그** 기준이다 — 검색어도 같은 규칙으로 걸려야 한다.

    옮기는 카드는 어느 검색어에도 안 걸리는 제목이다. 새 순위는 「걸린 행 중 가장 위 행의
    바로 위」(`min - STEP`)다. 검색어가 안 걸리거나 접히지 않으면 가장 위 행이 달라져 순위가
    어긋난다. 옮기는 카드 자신은 이웃 후보에서 빠지므로 앞선 이동이 다음 판정을 흔들지 않는다.
    """
    from app.tickets.models import Ticket
    from app.work.rank import STEP

    _seed_board_tickets(world)
    target = world.make_ticket(project=world.project, title="이동 대상 카드", status="진행")
    target.backlog_rank = Decimal(100_000)
    world.db.commit()
    rank_of = {key: Decimal(1000 * index) for index, key in enumerate(ITEMS, start=1)}
    checked: list[str] = []

    def check(query: str, expected) -> str | None:
        checked.append(query)
        response = world.client.post(
            f"/api/work/board/{target.id}/move",
            json={"reorder": True, "to_position": "top", "position_q": query},
            headers=world.headers,
        )
        if response.status_code != 200:
            return f"이동이 {response.status_code} 로 거절됐다: {response.text[:200]}"
        world.db.expire_all()
        placed = world.db.get(Ticket, target.id).backlog_rank
        keys = set(ITEMS) if expected is NO_FILTER else set(expected)
        want = min(rank_of[key] for key in keys) - STEP
        if placed != want:
            return f"순위 {placed} — 기대 {want}(걸려야 할 행 {sorted(keys)})"
        return None

    failures = _sweep(check)
    assert len(checked) == _checked_queries() >= 13, f"검색어를 {len(checked)}개만 댔다"
    assert failures == [], "맨 위로:\n  " + "\n  ".join(failures)


# ── 통합 검색 ─────────────────────────────────────────────────────────────────


def test_unified_search_folds_the_query_and_the_index(world):
    """통합 검색은 **실제 인덱서**가 만든 색인을 본다 — 티켓 제목이 색인을 거쳐 접힌 열까지 간다.

    C7 은 여기서만 뜻이 다르다: 접으면 빈 검색어는 **빈 결과**다(`mode = empty`).
    """
    from app.search.indexer import reindex_all

    seeded = _seed_tickets(world, assigned=False)
    result = reindex_all(world.db, tickets=world.client.app.state.repositories.tickets, now=NOW)
    world.db.commit()
    assert result.status == "ok", result.error
    checked: list[str] = []

    def check(query: str, expected) -> str | None:
        checked.append(query)
        body = world.get("/api/search", {"q": query, "limit": 50})
        tickets = [
            item for group in body["groups"] if group["kind"] == "ticket" for item in group["items"]
        ]
        if expected is NO_FILTER:
            if not (body["mode"] == "empty" and body["total"] == 0 and body["groups"] == []):
                return f"빈 결과가 아니다: mode={body['mode']} total={body['total']}"
            return None
        hit = {key for key, item_id in seeded.items() if item_id in _ids(tickets)}
        if hit != set(expected):
            return f"{sorted(hit)} 를 찾았다 — 기대 {sorted(expected)}"
        return None

    failures = _sweep(check)
    assert len(checked) == _checked_queries() >= 13, f"검색어를 {len(checked)}개만 댔다"
    assert failures == [], "통합 검색:\n  " + "\n  ".join(failures)


# ── AI 트라이그램 레인 (권한 좁히기 포함) ─────────────────────────────────────


def test_the_ai_trigram_lane_finds_the_spaced_phrase_and_keeps_permission_narrowing(
    db, people, make_space, make_knowledge_document
):
    """「현황제외」로 「현황 제외」가 든 chunk 를 찾는다 — 그리고 권한 밖 chunk 는 그대로 빠진다.

    FTS 레인은 이 질의를 못 찾는다(어절이 「현황」·「제외」 둘이다). 그래서 이 문서가 찾아졌다면
    그것은 접힌 트라이그램 레인이 찾은 것이다 — 그 사실을 레인별 건수로 함께 본다.
    """
    from sqlalchemy import select

    from app.ai.gateway import contract
    from app.ai.index import service as index_service
    from app.ai.models import DocumentChunk
    from app.ai.retrieval import query as query_mod
    from app.ai.retrieval import service as retrieval

    mine_space = make_space(name="A-1 공간", dept=D_A1)
    theirs_space = make_space(name="B-1 공간", dept=D_B1)
    mine = make_knowledge_document(space=mine_space, title="A-1 보고", text="현황 제외 항목을 정리합니다.")
    theirs = make_knowledge_document(space=theirs_space, title="B-1 보고", text="현황 제외 목록입니다.")
    gateway = contract.Gateway()  # 임베딩이 없는 설치 — 키워드 두 레인만 돈다
    index_service.run_once(db, gateway=gateway, limit=100)
    db.commit()

    def documents_of(rows) -> set[str]:
        ids = [str(row[0]) for row in rows]
        return set(db.execute(
            select(DocumentChunk.document_id).where(DocumentChunk.id.in_(ids))
        ).scalars().all()) if ids else set()

    # 반례 — 권한을 안 걸면 두 문서 다 걸린다. 그래야 아래 「빠진다」가 검색 실패가 아니다.
    unscoped = db.execute(query_mod.trgm_lane("현황제외", limit=50)).all()
    assert documents_of(unscoped) == {mine.id, theirs.id}

    narrowing = DocumentChunk.document_id.in_(retrieval.visible_document_ids(db, people["a1"]))
    scoped = db.execute(query_mod.trgm_lane("현황제외", narrowing=narrowing, limit=50)).all()
    assert documents_of(scoped) == {mine.id}, "권한 밖 chunk 가 트라이그램 레인으로 새었다"

    result = retrieval.retrieve(db, people["a1"], raw_query="현황제외", gateway=gateway)
    assert {c.document_id for c in result.citations} == {mine.id}
    assert result.lane_counts.get("trgm", 0) >= 1
    assert result.lane_counts.get("fts", 0) == 0, "FTS 가 찾았다면 이 시험은 접기를 증명하지 못한다"
