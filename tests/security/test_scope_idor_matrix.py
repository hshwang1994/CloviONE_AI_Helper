"""관리 범위(0024) IDOR 매트릭스 — 목록과 단건이 **같은 규칙**을 쓰는지 전수 확인한다.

(전역관리자 / 조직관리자 / 부서관리자 / 일반사용자) × (자기 범위 / 남의 범위) 조합을
목록·단건 각각에 대해 본다. 하나씩 손으로 확인하면 반드시 한 칸이 빠지고, 빠진 칸이
정확히 유출이 되는 자리다.

**핵심 단언: 범위 밖 단건은 403 이 아니라 404 다.**
403 은 "그 id 는 존재한다"를 알려 준다. 남의 부서 사용자 id 를 넣어 보며 403/404 를 세면
조직도를 통째로 열거할 수 있다 — 목록에서 가린 것이 단건에서 새면 가린 의미가 없다.
그래서 이 파일은 '접근이 막혔다'가 아니라 **'404 여야 한다'**를 못박는다.
"""

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.users.models import User

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"

D_DEV = "dept-dev-0001"
D_DEV_FE = "dept-dev-fe-01"   # 개발팀의 하위 부서 — 서브트리 전개가 실제로 도는지 본다
D_SALES = "dept-sales-001"


@pytest.fixture()
def org_tree(db):
    """부서 트리: 개발팀 > 프런트팀, 그리고 별개의 영업팀."""
    rows = [
        Department(id=D_DEV, name="개발팀", org_id=DEFAULT_ORG_ID, parent_id=None),
        Department(id=D_DEV_FE, name="프런트팀", org_id=DEFAULT_ORG_ID, parent_id=D_DEV),
        Department(id=D_SALES, name="영업팀", org_id=DEFAULT_ORG_ID, parent_id=None),
    ]
    for row in rows:
        db.add(row)
    db.commit()
    return {"dev": D_DEV, "fe": D_DEV_FE, "sales": D_SALES}


@pytest.fixture()
def people(db, make_user, org_tree):
    """행위자 4명 + 대상 3명. 대상은 부서별로 하나씩 둔다."""
    made = {}

    def _mk(key, email, role, *, dept=None, scope="global", scope_dept=None):
        user = make_user(email=email, role=role, display_name=key)
        user.department_id = dept
        user.admin_scope = scope
        user.scope_dept_id = scope_dept
        user.scope_org_id = DEFAULT_ORG_ID if scope != "global" else None
        db.add(user)
        made[key] = user
        return user

    # 행위자
    _mk("global_admin", "ga@goodmit.co.kr", "admin", dept=org_tree["dev"], scope="global")
    _mk("org_admin", "oa@goodmit.co.kr", "admin", dept=org_tree["dev"], scope="org")
    _mk("dept_admin", "da@goodmit.co.kr", "admin",
        dept=org_tree["dev"], scope="dept", scope_dept=org_tree["dev"])
    _mk("plain", "plain@goodmit.co.kr", "user", dept=org_tree["dev"])
    # 대상
    _mk("target_dev", "t-dev@goodmit.co.kr", "user", dept=org_tree["dev"])
    _mk("target_fe", "t-fe@goodmit.co.kr", "user", dept=org_tree["fe"])
    _mk("target_sales", "t-sales@goodmit.co.kr", "user", dept=org_tree["sales"])
    db.commit()
    return {k: (v.id, v.email) for k, v in made.items()}


def _login(client, email):
    response = client.post("/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _listed_ids(client) -> set[str]:
    response = client.get("/api/admin/users?page_size=100")
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["items"]}


# ── 목록 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "actor, sees_sales",
    [
        ("global_admin", True),   # 전역: 전부 본다
        ("org_admin", True),      # 조직: 같은 조직이므로 전부 본다(조직이 하나뿐이라)
        ("dept_admin", False),    # 부서: 영업팀은 안 보인다
    ],
)
def test_list_is_scoped(client, people, actor, sees_sales):
    _login(client, people[actor][1])
    ids = _listed_ids(client)

    assert people["target_dev"][0] in ids, "자기 부서 사용자는 항상 보여야 한다"
    assert people["target_fe"][0] in ids, "하위 부서 사용자도 보여야 한다(서브트리 전개)"
    assert (people["target_sales"][0] in ids) is sees_sales


def test_plain_user_cannot_reach_the_admin_list_at_all(client, people):
    """역할 게이트가 먼저 막는다 — 범위 이전의 방어선."""
    _login(client, people["plain"][1])
    assert client.get("/api/admin/users").status_code == 403


# ── 단건: 범위 밖은 404 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "actor, target, expected",
    [
        # 자기 범위 — 200
        ("global_admin", "target_sales", 200),
        ("org_admin", "target_sales", 200),
        ("dept_admin", "target_dev", 200),
        ("dept_admin", "target_fe", 200),
        # 남의 범위 — **404**(403 이면 존재가 새어 나간다)
        ("dept_admin", "target_sales", 404),
    ],
)
def test_detail_returns_404_outside_scope_not_403(client, people, actor, target, expected):
    _login(client, people[actor][1])
    response = client.get(f"/api/admin/users/{people[target][0]}")
    assert response.status_code == expected, response.text
    if expected == 404:
        assert response.status_code != 403, "403 은 그 id 가 존재한다는 사실을 알려 준다"


def test_detail_of_a_nonexistent_id_is_indistinguishable_from_out_of_scope(client, people):
    """유출을 막는다는 것은 **두 응답이 구별되지 않는다**는 뜻이다.

    상태 코드만 같고 본문이 다르면 그 차이로 존재를 알아낼 수 있다 — 본문까지 본다.
    """
    _login(client, people["dept_admin"][1])
    out_of_scope = client.get(f"/api/admin/users/{people['target_sales'][0]}")
    nonexistent = client.get("/api/admin/users/00000000-0000-4000-8000-0000deadbeef")

    assert out_of_scope.status_code == nonexistent.status_code == 404

    def _without_request_id(body: dict) -> dict:
        error = {k: v for k, v in body["error"].items() if k != "request_id"}
        return {**body, "error": error}

    # request_id 는 요청마다 다른 것이 정상이다(추적용). 그 외 모든 필드가 같아야 한다.
    assert _without_request_id(out_of_scope.json()) == _without_request_id(nonexistent.json())


# ── 단건 쓰기 경로도 같은 규칙을 타는가 ───────────────────────────────────────


@pytest.mark.parametrize(
    "method, suffix",
    [
        ("post", "/enable"),
        ("post", "/disable"),
        ("post", "/archive"),
        ("post", "/unlock"),
        ("post", "/reset-password"),
        ("post", "/revoke-sessions"),
        ("get", "/sessions"),
    ],
)
def test_every_single_object_route_is_scoped(client, people, method, suffix):
    """읽기만 막고 쓰기를 놓치면 목록에 없는 계정을 조작할 수 있다.

    라우터의 모든 `/{user_id}` 경로가 같은 조회 함수(get_scoped_user_or_404)를 지나는지를
    경로별로 확인한다 — 한 곳만 예전 함수를 쓰면 그 경로만 조용히 범위를 무시한다.
    """
    csrf = _login(client, people["dept_admin"][1])
    url = f"/api/admin/users/{people['target_sales'][0]}{suffix}"
    call = client.post if method == "post" else client.get
    response = call(url, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 404, f"{suffix} → {response.status_code}: {response.text}"


def test_patch_is_scoped(client, people):
    csrf = _login(client, people["dept_admin"][1])
    response = client.patch(
        f"/api/admin/users/{people['target_sales'][0]}",
        json={"display_name": "가로채기"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 404

    # 그리고 실제로 안 바뀌었는지 DB 로 되짚는다(404 를 냈지만 이미 썼을 수도 있다).
    from sqlalchemy import select

    with client.app.state.session_factory() as session:
        row = session.execute(
            select(User).where(User.id == people["target_sales"][0])
        ).scalar_one()
        assert row.display_name != "가로채기"


def test_in_scope_write_still_works(client, people):
    """범위 검사가 '전부 막기'로 퇴화하지 않았는지 — 반대 방향 증명."""
    csrf = _login(client, people["dept_admin"][1])
    response = client.post(
        f"/api/admin/users/{people['target_fe'][0]}/disable",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text


# ── 생성 ──────────────────────────────────────────────────────────────────────


def test_scoped_admin_cannot_create_an_account_outside_the_scope(client, people, org_tree):
    """범위 밖에 계정을 만들 수 있으면, 그 계정을 발판으로 범위가 무의미해진다."""
    csrf = _login(client, people["dept_admin"][1])
    response = client.post(
        "/api/admin/users",
        json={
            "email": "newbie@goodmit.co.kr",
            "display_name": "신입",
            "role": "user",
            "department_id": org_tree["sales"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403, response.text

    from sqlalchemy import select

    with client.app.state.session_factory() as session:
        created = session.execute(
            select(User).where(User.email == "newbie@goodmit.co.kr")
        ).scalar_one_or_none()
        assert created is None, "403 을 냈지만 계정이 남았다(롤백되지 않았다)"


def test_scoped_admin_can_create_inside_the_scope(client, people, org_tree):
    csrf = _login(client, people["dept_admin"][1])
    response = client.post(
        "/api/admin/users",
        json={
            "email": "insider@goodmit.co.kr",
            "display_name": "신입",
            "role": "user",
            "department_id": org_tree["fe"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text


# ── dev-monthly 리포트 ────────────────────────────────────────────────────────


@pytest.fixture()
def seeded_tickets(db, people, fake_clock):
    """리포트가 **미러에서** 답하도록 캐시를 채운다.

    Notion 을 부르지 않고 답하게 만드는 것이 목적이다 — 안 그러면 이 환경에서는
    configured=false 로 끝나 스코프 필터를 한 번도 타지 않는다(그러면 이 테스트는
    아무것도 증명하지 못한다).

    티켓 구성:
      * T1 — 영업팀 사람 한 명만 담당 (부서 관리자에게 안 보여야 한다)
      * T2 — 프런트팀 사람 한 명만 담당 (보여야 한다)
      * T3 — 프런트팀 + 영업팀 **공동 담당** (다중 담당자 티켓이 부서에서 사라지지 않아야
        한다 — 계획서가 종결한 쟁점이 바로 이것이다)
    """
    from datetime import datetime

    from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
    from app.tickets.models import SYNC_STATE_ID, TicketCache, TicketSyncState
    from app.core.models_base import join_names

    now = datetime(2026, 7, 14, 9, 0, 0)
    notion_ids = {}
    for key in ("target_fe", "target_sales"):
        user_id = people[key][0]
        notion_ids[key] = f"notion-{key}"
        db.add(UserNotionMapping(
            id=f"map-{key}", user_id=user_id, notion_user_id=notion_ids[key],
            status=STATUS_VERIFIED, source=SOURCE_MANUAL,
        ))

    state = db.get(TicketSyncState, SYNC_STATE_ID)
    state.status = "ok"
    state.last_run_at = now
    state.last_success_at = now
    state.ticket_count = 3

    tickets = (
        ("tc-1", "page-1", 101, "영업팀 전용", [notion_ids["target_sales"]]),
        ("tc-2", "page-2", 102, "프런트팀 전용", [notion_ids["target_fe"]]),
        ("tc-3", "page-3", 103, "공동 담당", [notion_ids["target_fe"], notion_ids["target_sales"]]),
    )
    for uid, page_id, number, title, assignees in tickets:
        db.add(TicketCache(
            id=uid, notion_page_id=page_id, notion_ticket_number=number, title=title,
            status="진행", due_date="2026-07-10",
            assignee_notion_ids=join_names(assignees),
            synced_at=now, created_at=now, updated_at=now,
        ))
    db.commit()
    return {"fe_only": 102, "sales_only": 101, "shared": 103}


def _developer_ids(body) -> set[str]:
    return {row["user_id"] for row in body["developers"] if row.get("user_id")}


def _ticket_numbers(body) -> set[int]:
    return {t["tid"] for row in body["developers"] for t in row["tickets"]}


def test_dev_monthly_only_lists_developers_inside_the_scope(client, people, seeded_tickets):
    """두 번째 적용 지점. 부서 관리자에게는 자기 서브트리 사람만 보인다."""
    _login(client, people["dept_admin"][1])
    body = client.get("/api/admin/reports/dev-monthly?period=2026-07").json()
    assert body.get("configured") and body.get("ok"), body

    ids = _developer_ids(body)
    assert people["target_fe"][0] in ids, "하위 부서 담당자는 보여야 한다"
    assert people["target_sales"][0] not in ids, "범위 밖 담당자가 새어 나왔다"


def test_a_shared_ticket_stays_visible_to_every_assignees_department(
    client, people, seeded_tickets
):
    """**계획서가 종결한 미결 쟁점.**

    담당자가 여럿인 티켓을 스칼라 하나(대표 담당자의 부서)로 정하면, 두 부서가 함께 맡은
    티켓이 한쪽 부서 화면에서 통째로 사라진다 — 그 부서 관리자는 자기 팀이 그 일을 하고
    있다는 사실 자체를 못 본다. 그래서 판정은 담당자 **집합**으로 한다.
    """
    _login(client, people["dept_admin"][1])
    body = client.get("/api/admin/reports/dev-monthly?period=2026-07").json()
    numbers = _ticket_numbers(body)

    assert seeded_tickets["shared"] in numbers, "공동 담당 티켓이 부서 화면에서 사라졌다"
    assert seeded_tickets["fe_only"] in numbers
    assert seeded_tickets["sales_only"] not in numbers, "범위 밖 전용 티켓이 새어 나왔다"


def test_dev_monthly_is_unchanged_for_a_global_admin(client, people, seeded_tickets):
    """전역 관리자에게는 스코프 인자가 None 이라 예전 동작 그대로여야 한다
    (골든이 바이트 단위로 그것을 못박지만, 여기서도 사람이 읽을 수 있게 남긴다)."""
    _login(client, people["global_admin"][1])
    body = client.get("/api/admin/reports/dev-monthly?period=2026-07").json()
    assert body.get("configured") and body.get("ok"), body

    assert people["target_sales"][0] in _developer_ids(body)
    assert _ticket_numbers(body) == set(seeded_tickets.values())
