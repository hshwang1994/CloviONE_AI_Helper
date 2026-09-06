"""프롬프트·정책의 **버전 쓰기**는 전역 관리자만 한다 — 읽기는 그대로 열어 둔다.

프롬프트와 정책은 부서로 나뉘는 자원이 아니다. 이름 하나에 발행본이 하나뿐이고, 그 이름을
전 부서가 함께 쓴다(스케줄이 그 이름을 참조한다). 그런데 쓰기 게이트가 역할(admin)만 보고
관리 범위(`admin_scope`)를 안 봐서, **서비스운영팀만 관리하는 부서 관리자**가

  * 전사 발행본을 `archived` 로 내려 다른 팀 자동화의 근거를 없애고,
  * `rollback` 으로 자기가 만든 버전을 전사 발행본으로 올릴 수 있었다.

같은 성격의 공지(`app/announcements/router.py`)와 전역 쿼터(`app/quotas/router.py`)는 이미
403 을 내고 있었으므로, 여기만 열려 있던 것은 설계가 아니라 누락이다. 판정은 404 가 아니라
403 이다 — 그 행의 존재는 목록에서 이미 보이고(읽기는 열려 있다), 문제는 존재가 아니라
권한이다(`app/core/scope.py::require_global_management`).
"""

import pytest

pytestmark = pytest.mark.integration

PROMPT_REFUSAL = "프롬프트는 전체 범위 관리자만 바꿀 수 있습니다."
POLICY_REFUSAL = "정책은 전체 범위 관리자만 바꿀 수 있습니다."


def _h(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def dept_admin(db, make_user, login_as):
    """서비스운영팀만 관리하는 admin. 역할은 같고 **범위만** 좁다.

    CSRF 토큰이 아니라 **로그인 함수**를 돌려준다. `client` 는 세션 쿠키를 하나만 들고 있어서,
    씨앗을 심는 픽스처가 나중에 전역 관리자로 로그인하면 부서 관리자의 토큰이 남의 세션에
    붙는다 — 그러면 응답이 403 이긴 한데 이유가 CSRF 라, 권한 시험이 통과한 것처럼 보이고
    아무것도 증명하지 못한다. 그래서 시험 본문에서 **마지막에** 로그인한다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    team = Department(name="서비스운영팀", org_id=DEFAULT_ORG_ID)
    db.add(team)
    db.commit()

    boss = make_user("p4-deptadmin@goodmit.co.kr", role="admin", display_name="부서관리자")
    boss.department_id = team.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = team.id
    db.commit()

    def _login() -> str:
        return login_as("admin", email="p4-deptadmin@goodmit.co.kr")

    return _login


@pytest.fixture()
def global_csrf(login_as):
    return login_as("system_admin")


@pytest.fixture()
def published_prompt(client, global_csrf):
    """전사 발행본 하나 — 부서 관리자가 건드리면 안 되는 대상이다."""
    item = client.post(
        "/api/admin/prompts",
        json={"name": "티켓 요약", "content": "다음 내용을 세 문장으로 요약해 주세요.", "purpose": "요약"},
        headers=_h(global_csrf),
    ).json()["item"]
    for step in ("test", "review", "published"):
        r = client.post(
            f"/api/admin/prompts/{item['id']}/transition",
            json={"status": step},
            headers=_h(global_csrf),
        )
        assert r.status_code == 200, r.text
    return r.json()["item"]


@pytest.fixture()
def draft_prompt(client, global_csrf):
    return client.post(
        "/api/admin/prompts",
        json={"name": "초안 프롬프트", "content": "초안 지시문", "purpose": "초안 용도"},
        headers=_h(global_csrf),
    ).json()["item"]


# ── 부서 범위 관리자는 쓰지 못한다 ────────────────────────────────────────────


def test_a_scoped_admin_cannot_create_a_prompt(client, dept_admin):
    csrf = dept_admin()
    r = client.post(
        "/api/admin/prompts",
        json={"name": "부서관리자 프롬프트", "content": "x"},
        headers=_h(csrf),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == PROMPT_REFUSAL


def test_a_scoped_admin_cannot_create_a_policy(client, dept_admin):
    csrf = dept_admin()
    r = client.post(
        "/api/admin/policies",
        json={"name": "부서관리자 정책", "content": {"a": 1}},
        headers=_h(csrf),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == POLICY_REFUSAL


def test_a_scoped_admin_cannot_edit_someone_elses_draft(client, dept_admin, draft_prompt):
    csrf = dept_admin()
    r = client.patch(
        f"/api/admin/prompts/{draft_prompt['id']}",
        json={"content": "부서관리자가 덮어쓴 지시문"},
        headers=_h(csrf),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == PROMPT_REFUSAL
    assert (
        client.get(f"/api/admin/prompts/{draft_prompt['id']}").json()["item"]["content"]
        == "초안 지시문"
    )


def test_a_scoped_admin_cannot_archive_the_published_version(
    client, dept_admin, published_prompt
):
    """발행본을 내리면 그 이름을 참조하는 스케줄이 조용히 근거를 잃는다."""
    csrf = dept_admin()
    r = client.post(
        f"/api/admin/prompts/{published_prompt['id']}/transition",
        json={"status": "archived"},
        headers=_h(csrf),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == PROMPT_REFUSAL
    assert (
        client.get(f"/api/admin/prompts/{published_prompt['id']}").json()["item"]["status"]
        == "published"
    )


def test_a_scoped_admin_cannot_open_a_new_version(client, dept_admin, published_prompt):
    csrf = dept_admin()
    r = client.post(
        f"/api/admin/prompts/{published_prompt['id']}/new-version", headers=_h(csrf)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == PROMPT_REFUSAL
    rows = client.get("/api/admin/prompts", params={"name": "티켓 요약"}).json()["items"]
    assert len(rows) == 1


def test_a_scoped_admin_cannot_rollback(client, dept_admin, published_prompt):
    csrf = dept_admin()
    r = client.post(
        "/api/admin/prompts/rollback",
        json={"name": "티켓 요약", "version": 1},
        headers=_h(csrf),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["message"] == PROMPT_REFUSAL


# ── 반례: 막힌 것이 권한뿐인지 확인한다 ──────────────────────────────────────


def test_a_global_admin_still_runs_the_whole_lifecycle(client, global_csrf, published_prompt):
    """반례 — 전역 관리자가 못 하게 됐다면 그것은 기능 고장이다."""
    r = client.post(
        f"/api/admin/prompts/{published_prompt['id']}/new-version", headers=_h(global_csrf)
    )
    assert r.status_code == 200, r.text
    v2 = r.json()["item"]
    assert v2["version"] == 2

    r = client.patch(
        f"/api/admin/prompts/{v2['id']}", json={"content": "v2 지시문"}, headers=_h(global_csrf)
    )
    assert r.status_code == 200, r.text

    for step in ("test", "review", "published"):
        r = client.post(
            f"/api/admin/prompts/{v2['id']}/transition",
            json={"status": step},
            headers=_h(global_csrf),
        )
        assert r.status_code == 200, r.text

    r = client.post(
        "/api/admin/prompts/rollback",
        json={"name": "티켓 요약", "version": 1},
        headers=_h(global_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["version"] == 3
    assert r.json()["item"]["status"] == "published"


def test_a_scoped_admin_can_still_read_everything(client, dept_admin, published_prompt):
    """반례 — 읽기까지 막으면 「지금 무엇이 쓰이는가」를 볼 수 없다. 읽기는 좁히지 않는다."""
    dept_admin()
    assert client.get("/api/admin/prompts").status_code == 200
    assert client.get("/api/admin/policies").status_code == 200
    assert client.get(f"/api/admin/prompts/{published_prompt['id']}").status_code == 200
    assert client.get("/api/admin/prompts/usage/stats").status_code == 200
    assert client.get("/api/admin/policies/usage/stats").status_code == 200


def test_an_operator_is_still_refused_by_role(client, login_as, draft_prompt):
    """역할 게이트는 그대로다 — 범위 게이트를 얹었다고 운영자가 열리면 안 된다."""
    csrf = login_as("operator")
    r = client.post(
        "/api/admin/prompts", json={"name": "op 프롬프트", "content": "x"}, headers=_h(csrf)
    )
    assert r.status_code == 403, r.text
    assert client.get("/api/admin/prompts").status_code == 200
