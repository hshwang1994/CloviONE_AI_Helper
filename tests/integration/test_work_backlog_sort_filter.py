# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""작업 보드 · 백로그의 **여러 값 조건 · 예상 WD 범위 · 백로그 정렬** (D-497).

## 이 파일이 못박는 계약

새 작업 보드 화면은 다른 티켓 표와 같은 머리 필터 · 정렬을 쓴다. 그 화면이 믿는 서버 계약이
여기 있다.

1. 판 · 열 · 백로그가 `project_id` · `assignee_user_id` · `priority` · `difficulty` 를 **여러 번**
   받는다. 같은 축끼리는 OR, 축 사이는 AND 다. 값 하나만 보내도 예전처럼 걸린다.
2. `est_wd_min` · `est_wd_max` 는 양 끝을 포함하고, 범위가 걸리면 예상 WD 가 빈 행은 빠진다.
3. 백로그는 `sort` · `order` 를 받는다. 기본(`rank` · `asc`)은 끌어 옮긴 순서이고, 나머지는
   티켓 목록과 같은 순서다 — 값이 없는 행은 어느 방향이든 끝이고 같은 값은 id 로 갈린다.
   커서를 끝까지 따라가면 `total` 과 정확히 같은 수를 중복 없이 받는다.
4. 다른 종류의 커서 · 모르는 정렬은 422 다.
5. 「맨 위로 / 맨 아래로」의 `position_*` 가 목록과 같은 여러 값 조건을 쓰고, 옛 화면이 보내는
   문자열 하나도 그대로 받는다.
6. 「내 티켓만」은 고른 담당자보다 먼저다.

## 왜 동률과 빈 값을 심는가

값이 전부 다르고 빈 값이 없으면 1차 키만으로 순서가 정해져서, id 타이브레이크나 NULL 의 자리가
틀려도 이 시험이 통과한다. 그래서 우선순위 · 예상 WD · 마감에 같은 값과 빈 값을 함께 심는다.
기대 순서는 서버를 흉내 내지 않고 **업무 규칙을 이 파일에 따로 적어** 계산한다(아래 두 표).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import codes as work_codes
from app.work.rank import STEP

pytestmark = pytest.mark.integration

BOSS = "backlog-sort-boss@goodmit.co.kr"
MATE_ONE = "backlog-sort-one@goodmit.co.kr"
MATE_TWO = "backlog-sort-two@goodmit.co.kr"
NOBODY = "00000000-0000-0000-0000-000000000000"
BAD_CURSOR = "목록 위치 정보가 올바르지 않습니다. 목록을 새로고침해 주세요."

#: 업무 규칙 — 우선순위는 급한 것부터다. 「중간」은 이관 원본의 이름이고 「보통」과 같은 자리다.
PRIORITY_ORDER = {"긴급": 1, "높음": 2, "보통": 3, "중간": 3, "낮음": 4}
#: 업무 규칙 — 난이도는 폼 드롭다운 순서다. 숫자 등급이 숫자 크기대로 먼저, 그다음 상 · 중 · 하.
DIFFICULTY_ORDER = {"1": 1, "2": 2, "3": 3, "6": 6, "상": 11, "중": 12, "하": 13}


@dataclass(frozen=True)
class Row:
    name: str
    project: str
    priority: str | None
    difficulty: str | None
    est_wd: float | None
    due: str | None
    assignee: str | None
    rank: int | None
    seq: int | None


#: 한 팀의 백로그 아홉 장. 「특급」 · 「9」는 표에 없는 값이고, 번호(`seq`)가 없는 두 장은 이름이 없다.
ROWS = (
    Row("r01", "alpha", "긴급", "1", 0.0, "2026-10-01", "one", 100, 3),
    Row("r02", "alpha", "높음", "6", 1.5, "2026-09-25", "two", 200, 1),
    Row("r03", "beta", "보통", "상", 3.0, None, "boss", 300, 2),
    Row("r04", "beta", "낮음", "하", None, "2026-09-30", "one", 400, 1),
    Row("r05", "alpha", None, None, 5.0, "2026-09-25", "two", 500, 2),
    Row("r06", "beta", "높음", "3", 1.5, None, None, None, None),
    Row("r07", "alpha", "특급", "중", 2.0, "2026-11-01", "boss", 700, None),
    Row("r08", "beta", "긴급", "9", None, None, "two", 800, 3),
    Row("r09", "alpha", "중간", "2", 3.0, "2026-09-25", None, 900, 4),
)
BY_NAME = {row.name: row for row in ROWS}


def _ticket_id(name: str) -> str:
    """티켓 id 를 손으로 정한다 — 같은 값끼리의 순서(id 타이브레이크)를 기대값으로 계산하려면
    id 가 이 파일이 아는 값이어야 한다. 접두어가 같고 길이가 같아 어느 정렬 규칙으로도 순서가 같다."""
    return f"bs-{name}"


@dataclass
class World:
    team: Department
    projects: dict
    people: dict
    keys: dict


@pytest.fixture()
def world(db, make_user):
    team = Department(name="정렬팀", org_id=DEFAULT_ORG_ID)
    db.add(team)
    db.commit()

    boss = make_user(BOSS, role="admin", display_name="정렬팀장")
    one = make_user(MATE_ONE, role="user", display_name="담당 하나")
    two = make_user(MATE_TWO, role="user", display_name="담당 둘")
    for person in (boss, one, two):
        person.department_id = team.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = team.id
    db.commit()

    projects = {
        "alpha": work_codes.insert_with_code(db, Project(
            name="정렬 알파", org_id=DEFAULT_ORG_ID, dept_id=team.id, notion_page_id="bs-proj-alpha",
        )),
        "beta": work_codes.insert_with_code(db, Project(
            name="정렬 베타", org_id=DEFAULT_ORG_ID, dept_id=team.id, notion_page_id="bs-proj-beta",
        )),
    }
    db.commit()
    # 담당자 칸에는 사람을 가리키는 토큰이 들어간다. 옛 짝이 없는 계정은 자기 id 가 토큰이다
    # (`app/tickets/service.py::assignee_token`).
    people = {"boss": boss.id, "one": one.id, "two": two.id}
    tickets = {}
    for row in ROWS:
        tickets[row.name] = Ticket(
            id=_ticket_id(row.name), title=f"정렬 {row.name}", notion_page_id=f"bs-page-{row.name}",
            project_uid=projects[row.project].id, project_link=PROJECT_LINK_OK, status="계획",
            org_id=DEFAULT_ORG_ID, source="notion", priority=row.priority,
            difficulty=row.difficulty, est_wd=row.est_wd, due_date=row.due,
            assignee_notion_ids=join_names([people[row.assignee]] if row.assignee else []),
            backlog_rank=None if row.rank is None else Decimal(row.rank),
            board_rank=None if row.rank is None else Decimal(row.rank), seq=row.seq,
        )
        db.add(tickets[row.name])
    db.commit()
    # 이름(`canonical_key`)은 앱이 아니라 트리거가 짓는다 — 다시 읽어야 ORM 쪽 값이 찬다.
    keys = {}
    for name, ticket in tickets.items():
        db.refresh(ticket)
        keys[name] = ticket.canonical_key
    assert keys["r01"] and keys["r06"] is None, f"트리거가 이름을 안 지었거나 너무 지었다: {keys}"
    return World(team=team, projects=projects, people=people, keys=keys)


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS)}


def _names(ids) -> list[str]:
    """응답의 티켓 id → 이 파일의 이름(`r01`). 심지 않은 행이 섞이면 그대로 드러난다."""
    return [value[len("bs-"):] if value.startswith("bs-") else value for value in ids]


def _expected(world: World, sort: str, order: str) -> list[str]:
    """업무 규칙으로 계산한 기대 순서 — 값이 있는 행이 먼저 그 값의 순서로, 같은 값은 id 로
    (방향을 따른다), 값이 없는 행은 **어느 방향이든 끝**에 id 순으로 선다."""

    def value(row: Row):
        if sort == "rank":
            return row.rank
        if sort == "priority":
            return PRIORITY_ORDER.get(row.priority)
        if sort == "difficulty":
            return DIFFICULTY_ORDER.get(row.difficulty)
        if sort == "est_wd":
            return row.est_wd
        if sort == "due_date":
            return row.due
        if sort == "tid":
            key = world.keys[row.name]
            if key is None:
                return None
            code, number = key.split("-")
            return (code, int(number))
        raise AssertionError(sort)

    descending = order == "desc"
    ranked = [row for row in ROWS if value(row) is not None]
    unranked = [row for row in ROWS if value(row) is None]
    ranked.sort(key=lambda row: (value(row), _ticket_id(row.name)), reverse=descending)
    unranked.sort(key=lambda row: _ticket_id(row.name), reverse=descending)
    return [row.name for row in ranked + unranked]


def _walk_backlog(client, headers, params: dict, *, limit: int = 2):
    """백로그 커서를 끝까지 따라간다 → (받은 이름 순서, `total`, 마지막 응답)."""
    seen: list[str] = []
    totals: set[int] = set()
    cursor = None
    for _ in range(100):
        query = {**params, "limit": limit}
        if cursor:
            query["cursor"] = cursor
        response = client.get("/api/work/backlog", params=query, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        totals.add(body["total"])
        seen.extend(_names(item["id"] for item in body["items"]))
        cursor = body["next_cursor"]
        if not cursor:
            assert len(totals) == 1, f"쪽마다 total 이 다르다: {totals}"
            return seen, totals.pop(), body
    raise AssertionError("커서가 끝나지 않는다 — 무한 루프")


def _backlog_names(client, headers, params: dict) -> set[str]:
    response = client.get("/api/work/backlog", params={**params, "limit": 100}, headers=headers)
    assert response.status_code == 200, response.text
    return set(_names(item["id"] for item in response.json()["items"]))


def _board_names(client, headers, params: dict) -> set[str]:
    response = client.get("/api/work/board", params={**params, "column_page_size": 100}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    cards = [card for column in body["columns"] for card in column["cards"]] + body["unclassified"]
    return set(_names(card["id"] for card in cards))


def _column_names(client, headers, params: dict) -> set[str]:
    response = client.get(
        "/api/work/board/columns/계획", params={**params, "limit": 100}, headers=headers,
    )
    assert response.status_code == 200, response.text
    return set(_names(card["id"] for card in response.json()["cards"]))


def _three_lists(client, headers, params: dict) -> dict[str, set[str]]:
    """판 · 열 · 백로그 — 같은 조건이면 같은 집합이어야 한다(모든 행이 「계획」 열에 있다)."""
    return {
        "board": _board_names(client, headers, params),
        "column": _column_names(client, headers, params),
        "backlog": _backlog_names(client, headers, params),
    }


# ── 1 · 2 여러 값 조건과 예상 WD 범위 ─────────────────────────────────────────


def test_without_conditions_all_three_lists_see_the_whole_team(client, login_as, world):
    """반례의 바닥 — 조건이 없으면 세 목록이 아홉 장 전부를 본다. 아니면 아래 시험이 헛돈다."""
    lists = _three_lists(client, _hdr(login_as), {})
    for name, got in lists.items():
        assert got == set(BY_NAME), f"{name}: 조건 없이 불렀는데 심은 행이 다 안 보인다: {got}"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        # 값 하나 — 예전 계약 그대로다.
        ({"priority": "긴급"}, {"r01", "r08"}),
        # 같은 축끼리는 OR.
        ({"priority": ["긴급", "높음"]}, {"r01", "r02", "r06", "r08"}),
        ({"difficulty": ["1", "상"]}, {"r01", "r03"}),
        ({"project_id": ["alpha"]}, {"r01", "r02", "r05", "r07", "r09"}),
        ({"project_id": ["alpha", "beta"]}, set(BY_NAME)),
        ({"assignee_user_id": ["one", "two"]}, {"r01", "r02", "r04", "r05", "r08"}),
        # 축 사이는 AND.
        ({"priority": ["긴급", "높음"], "project_id": ["beta"]}, {"r06", "r08"}),
        ({"difficulty": ["3", "9", "중"], "assignee_user_id": ["two"]}, {"r08"}),
        # 예상 WD — 양 끝 포함, 범위가 걸리면 빈 값은 빠진다. 0 은 빈 값이 아니다.
        ({"est_wd_min": 1.5, "est_wd_max": 3}, {"r02", "r03", "r06", "r07", "r09"}),
        ({"est_wd_min": 0}, {"r01", "r02", "r03", "r05", "r06", "r07", "r09"}),
        ({"est_wd_max": 0}, {"r01"}),
        ({"est_wd_min": 4, "priority": ["긴급", "높음", "보통"]}, set()),
    ],
)
def test_multi_value_filters_and_the_estimate_range_agree_on_all_three_lists(
    client, login_as, world, params, expected,
):
    resolved = {}
    for axis, value in params.items():
        values = value if isinstance(value, list) else [value]
        if axis == "project_id":
            values = [world.projects[v].id for v in values]
        elif axis == "assignee_user_id":
            values = [world.people[v] for v in values]
        resolved[axis] = values if isinstance(value, list) else values[0]
    lists = _three_lists(client, _hdr(login_as), resolved)
    for name, got in lists.items():
        assert got == expected, f"{name} {params}: {sorted(got)} — 기대 {sorted(expected)}"


def test_mine_overrides_the_picked_assignee(client, login_as, world):
    """「내 티켓만」은 고른 담당자보다 먼저다 — 켜 둔 채 담당자 칸의 옛 값이 따라와도 내 것만 보인다."""
    params = {"mine": "true", "assignee_user_id": [world.people["one"]]}
    lists = _three_lists(client, _hdr(login_as), params)
    for name, got in lists.items():
        assert got == {"r03", "r07"}, f"{name}: 「내 티켓만」이 고른 담당자에게 졌다: {sorted(got)}"


def test_an_unresolved_assignee_among_several_drops_only_itself(client, login_as, world):
    """여러 담당자 중 모르는 id 가 섞이면 **그 id 만** 빠진다 — 조건 전체가 지워지지도(전부 열림),
    나머지까지 닫히지도 않는다."""
    params = {"assignee_user_id": [world.people["one"], NOBODY]}
    lists = _three_lists(client, _hdr(login_as), params)
    for name, got in lists.items():
        assert got == {"r01", "r04"}, f"{name}: {sorted(got)}"


@pytest.mark.parametrize(
    "params",
    [
        {"est_wd_min": "nan"},
        {"est_wd_max": "inf"},
        {"priority": "가" * 65},
        {"project_id": "x" * 37},
        {"difficulty": [str(n) for n in range(41)]},
    ],
)
def test_malformed_conditions_are_refused_not_dropped(client, login_as, world, params):
    """틀린 조건은 422 다. 조용히 버리면 그 축이 사라져 거른 줄 알았던 목록이 전부 열린다."""
    headers = _hdr(login_as)
    for path in ("/api/work/board", "/api/work/board/columns/계획", "/api/work/backlog"):
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 422, f"{path} {params}: {response.status_code} {response.text[:200]}"


# ── 3 · 4 백로그 정렬 ─────────────────────────────────────────────────────────


SORTS = ("rank", "tid", "priority", "difficulty", "est_wd", "due_date")


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", SORTS)
def test_backlog_sort_walks_every_row_exactly_once_in_the_business_order(
    client, login_as, world, sort, order,
):
    """쪽 크기 2 로 끝까지 — 경계를 네 번 지난다. 받은 순서가 업무 규칙의 순서와 **완전히 같다**."""
    headers = _hdr(login_as)
    seen, total, last = _walk_backlog(client, headers, {"sort": sort, "order": order})
    assert total == len(ROWS), f"total 이 심은 수가 아니다: {total}"
    assert len(seen) == total and len(set(seen)) == total, f"중복 또는 누락: {seen}"
    assert seen == _expected(world, sort, order), f"{sort} {order}: {seen}"
    assert (last["sort"], last["order"]) == (sort, order), "서버가 쓴 정렬을 돌려주지 않는다"
    # 한 번에 받은 순서와도 같다 — 쪽 경계에서 순서가 흔들리면 그 흔들림이 곧 누락 · 중복이다.
    single, _, _ = _walk_backlog(client, headers, {"sort": sort, "order": order}, limit=100)
    assert single == seen


def test_backlog_sort_narrows_with_the_same_filters(client, login_as, world):
    """정렬해서 보는 동안에도 조건은 그대로 걸린다 — 정렬이 조건을 우회하는 길이 아니다."""
    params = {"sort": "priority", "order": "desc", "project_id": [world.projects["beta"].id]}
    seen, total, _ = _walk_backlog(client, _hdr(login_as), params)
    assert total == 4
    assert seen == ["r04", "r03", "r06", "r08"], seen


def test_the_default_backlog_is_the_dragged_order(client, login_as, world):
    """정렬을 안 고르면 예전 그대로 끌어 옮긴 순서다 — 그리고 서버가 그렇다고 말한다."""
    seen, total, last = _walk_backlog(client, _hdr(login_as), {})
    assert total == len(ROWS)
    assert seen == _expected(world, "rank", "asc")
    assert (last["sort"], last["order"]) == ("rank", "asc")


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "title"},
        {"sort": "backlog_rank; DROP TABLE tickets"},
        {"sort": "PRIORITY"},
        {"order": "up"},
        {"sort": "priority", "order": "descending"},
    ],
)
def test_an_unknown_sort_is_refused(client, login_as, world, params):
    """모르는 정렬은 422 다 — 조용히 기본 순서로 떨어지면 「눌렀는데 순서가 그대로」가 된다."""
    response = client.get("/api/work/backlog", params=params, headers=_hdr(login_as))
    assert response.status_code == 422, f"{params}: {response.status_code} {response.text[:200]}"


def test_an_empty_sort_means_the_default_order(client, login_as, world):
    """빈 값은 「고르지 않았다」다 — 화면이 정렬을 풀면 `?sort=` 로 올 수 있고, 그때는 기본 순서다."""
    seen, _, last = _walk_backlog(client, _hdr(login_as), {"sort": "", "order": ""})
    assert seen == _expected(world, "rank", "asc")
    assert (last["sort"], last["order"]) == ("rank", "asc")


def _first_cursor(client, headers, params: dict) -> str:
    response = client.get("/api/work/backlog", params={**params, "limit": 2}, headers=headers)
    assert response.status_code == 200, response.text
    cursor = response.json()["next_cursor"]
    assert cursor, "아홉 장인데 다음 쪽이 없다 — 전제가 깨졌다"
    return cursor


def test_a_cursor_of_the_wrong_kind_is_refused(client, login_as, world):
    """커서는 불투명하지만 **종류가 있다** — 다른 정렬로 받은 커서를 이어 붙이면 422 다.

    받아 주면 순위 커서의 값을 오프셋으로 읽거나(또는 그 반대) 다른 정렬의 자리에서 이어 받아,
    오류 없이 행을 건너뛰거나 두 번 준다.
    """
    headers = _hdr(login_as)
    rank_cursor = _first_cursor(client, headers, {})
    priority_cursor = _first_cursor(client, headers, {"sort": "priority", "order": "asc"})

    def refused(path: str, params: dict) -> None:
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 422, f"{path} {params}: {response.status_code} {response.text[:200]}"
        assert response.json()["error"]["message"] == BAD_CURSOR

    # 반례 — 같은 종류면 이어진다.
    for params in ({"cursor": rank_cursor}, {"sort": "priority", "cursor": priority_cursor}):
        response = client.get("/api/work/backlog", params={**params, "limit": 2}, headers=headers)
        assert response.status_code == 200, response.text

    refused("/api/work/backlog", {"sort": "priority", "cursor": rank_cursor})
    refused("/api/work/backlog", {"cursor": priority_cursor})
    refused("/api/work/backlog", {"sort": "priority", "order": "desc", "cursor": priority_cursor})
    refused("/api/work/backlog", {"sort": "difficulty", "cursor": priority_cursor})
    refused("/api/work/backlog", {"sort": "rank", "order": "desc", "cursor": rank_cursor})
    refused("/api/work/board/columns/계획", {"cursor": priority_cursor})
    refused("/api/work/backlog", {"sort": "priority", "cursor": "아무거나"})


# ── 5 「맨 위로 / 맨 아래로」의 `position_*` ─────────────────────────────────


@pytest.fixture()
def mover(db, world):
    """옮길 카드 한 장 — 순위가 가장 뒤다. 순위 계산은 옮기는 카드 자신을 이웃에서 뺀다."""
    row = Ticket(
        id=_ticket_id("mover"), title="옮길 카드", notion_page_id="bs-page-mover",
        project_uid=world.projects["alpha"].id, project_link=PROJECT_LINK_OK, status="계획",
        org_id=DEFAULT_ORG_ID, source="notion", backlog_rank=Decimal(10_000),
    )
    db.add(row)
    db.commit()
    return row.id


def _move_to(client, headers, db, ticket_id: str, position: str, extra: dict) -> Decimal:
    response = client.post(
        f"/api/work/board/{ticket_id}/move",
        json={"reorder": True, "to_position": position, **extra},
        headers=headers,
    )
    assert response.status_code == 200, f"{extra}: {response.status_code} {response.text[:300]}"
    db.expire_all()
    return db.get(Ticket, ticket_id).backlog_rank


def _rank_of(name: str) -> Decimal:
    return Decimal(BY_NAME[name].rank)


@pytest.mark.parametrize(
    ("position", "extra", "anchor"),
    [
        # 목록 — 여러 값으로 거른 백로그의 맨 위 · 맨 아래. 기준 행은 **둘째 값**에서 나오고 전체
        # 백로그의 맨 위(r01)도 아니다 — 조건을 안 걸거나 첫 값만 걸면 다른 순위가 나온다.
        ("top", {"position_priority": ["낮음", "높음"]}, ("min", ["r02", "r04"])),
        ("bottom", {"position_difficulty": ["상", "하"]}, ("max", ["r03", "r04"])),
        ("bottom", {"position_assignee_user_id": ["one", "two"]}, ("max", ["r01", "r02", "r04", "r05", "r08"])),
        ("top", {"position_project_id": ["beta"]}, ("min", ["r03", "r04", "r08"])),
        # 옛 화면 — 문자열 하나도 그대로 받는다.
        ("top", {"position_priority": "높음"}, ("min", ["r02"])),
        ("bottom", {"position_assignee_user_id": "one"}, ("max", ["r01", "r04"])),
        ("top", {"position_project_id": "beta"}, ("min", ["r03", "r04", "r08"])),
        # 예상 WD 범위 — 목록과 같은 뜻이다.
        ("top", {"position_est_wd_min": 3}, ("min", ["r03", "r05", "r09"])),
        ("bottom", {"position_est_wd_min": 1.5, "position_est_wd_max": 1.5}, ("max", ["r02"])),
        # 「내 티켓만」이 고른 담당자보다 먼저다.
        ("bottom", {"position_mine": True, "position_assignee_user_id": ["one"]}, ("max", ["r03", "r07"])),
    ],
)
def test_position_moves_rank_against_the_same_multi_value_backlog(
    client, login_as, db, world, mover, position, extra, anchor,
):
    """새 순위는 「걸린 행 중 가장 위 행의 바로 위」(`min - STEP`) 또는 「가장 아래 행의 바로 아래」
    (`max + STEP`)다. 조건이 목록과 다르게 걸리면 기준 행이 달라져 순위가 어긋난다."""
    payload = {}
    for key, value in extra.items():
        if key == "position_project_id":
            ids = [world.projects[v].id for v in (value if isinstance(value, list) else [value])]
            value = ids if isinstance(value, list) else ids[0]
        elif key == "position_assignee_user_id":
            ids = [world.people[v] for v in (value if isinstance(value, list) else [value])]
            value = ids if isinstance(value, list) else ids[0]
        payload[key] = value
    placed = _move_to(client, _hdr(login_as), db, mover, position, payload)
    how, names = anchor
    ranks = [_rank_of(name) for name in names]
    want = min(ranks) - STEP if how == "min" else max(ranks) + STEP
    assert placed == want, f"{extra}: 순위 {placed} — 기대 {want}(기준 행 {names})"


def test_an_unresolved_position_assignee_ranks_against_an_empty_backlog(
    client, login_as, db, world, mover,
):
    """모르는 담당자로 거른 백로그는 **빈 목록**이다 — 전체 백로그의 맨 위가 아니다.

    빈 목록의 맨 위는 첫 값(`STEP`)이다. 조건이 사라져 전체로 계산했다면 가장 위 행(r01)의
    바로 위인 `100 - STEP` 이 나온다.
    """
    headers = _hdr(login_as)
    unfiltered = _move_to(client, headers, db, mover, "top", {})
    assert unfiltered == _rank_of("r01") - STEP, "반례가 서지 않는다 — 전제가 깨졌다"
    closed = _move_to(client, headers, db, mover, "top", {"position_assignee_user_id": [NOBODY]})
    assert closed == STEP, f"모르는 담당자가 조건을 지워 전체 백로그로 계산했다: {closed}"


@pytest.mark.parametrize(
    "extra",
    [
        {"position_priority": [1]},
        {"position_project_id": ["x" * 37]},
        {"position_difficulty": [str(n) for n in range(41)]},
        {"position_signal": "late"},
    ],
)
def test_malformed_position_conditions_are_refused(client, login_as, db, world, mover, extra):
    response = client.post(
        f"/api/work/board/{mover}/move",
        json={"reorder": True, "to_position": "top", **extra},
        headers=_hdr(login_as),
    )
    assert response.status_code == 422, f"{extra}: {response.status_code} {response.text[:200]}"


def test_every_list_condition_has_a_position_twin():
    """`BoardFilterQuery` 에 축이 늘면 `BoardMove` 에도 `position_<이름>` 이 있어야 한다 — 없으면
    이동 위치 계산만 그 축을 모르는 채로 순위를 잰다. 빈 이동 요청으로 옮겨 보기만 해도 드러난다."""
    from dataclasses import fields

    from app.work.schemas import BoardFilterQuery, BoardMove

    move = BoardMove(position_priority="높음", position_project_id=["a", " a ", ""])
    query = move.position_query()
    assert query.priority == ("높음",) and query.project_id == ("a",)
    assert {spec.name for spec in fields(BoardFilterQuery)} <= {
        name.removeprefix("position_") for name in BoardMove.model_fields if name.startswith("position_")
    }
