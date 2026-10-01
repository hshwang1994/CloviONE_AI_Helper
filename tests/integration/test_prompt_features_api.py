"""프롬프트는 AI 기능마다 한 줄이다 (계획 A4, D-541).

못박는 성질:
1. 목록은 고칠 수 있는 기능 다섯(AI 도우미 · 문서 초안 · 주간 요약 · 홈 문장 요약 · 게임 퀴즈)이고, 연결 확인과 은퇴한 질문 답변은 없다.
   지금 쓰는 지시문(기본 제공 · 관리자 작성 vN), 기능 상태(켜짐 · 꺼짐 · AI 미연결), 초안, 최근 30일 요청 · 실패율 · 마지막 사용을 준다.
2. 기능 상태는 0 의 까닭을 말한다: AI 사용이 꺼지면 모두 꺼짐, 연결이 막히면 AI 미연결, 기능 스위치가 꺼지면 그 기능만 꺼짐.
3. 「지시문 고치기」(`PATCH /features/{기능}`)는 초안이 없으면 지금 지시문을 복사해 만들고, 있으면 그 초안을 고친다 - 초안은 하나다.
   「초안 열기」도 다시 보내도 하나다.
4. 발행하면 다음 호출부터 그 지시문이고, 버리기는 초안만 보관하며, 기본 제공으로 되돌리기는 발행본을 보관한다.
5. 서랍 주소는 기능 키 · `builtin:<기능>` · 그 기능의 버전 id 를 다 받는다. 모르는 값은 404 다.
6. 쓰기는 전역 범위 관리자만 한다(부서 범위 관리자 · 운영자 403). 읽기는 콘솔 읽기 역할이 다 한다.
"""

from __future__ import annotations

import pytest

from tests.fakes.ai import configure_ai

pytestmark = pytest.mark.integration

FEATURES = "/api/admin/prompts/features"


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _rows(client) -> dict:
    return {r["slot"]: r for r in client.get(FEATURES).json()["items"]}


def test_one_row_per_editable_feature(client, login_as):
    login_as("system_admin")
    reply = client.get(FEATURES).json()
    assert [r["slot"] for r in reply["items"]] == ["assistant", "draft", "weekly_summary", "narrative", "quiz"]
    assert reply["days"] == 30
    row = reply["items"][0]
    assert row["current"]["source"] == "builtin" and row["current"]["label"] == "기본 제공"
    assert row["draft"] is None and row["calls_30d"] == 0 and row["failure_rate"] is None
    assert row["frame"]["role"] and row["content"] == row["current"]["instruction"]


def test_feature_state_says_why_a_feature_has_no_calls(app, client, login_as):
    csrf = login_as("system_admin")
    rows = _rows(client)
    assert {r["feature_state"] for r in rows.values()} == {"off"}, "AI 사용이 꺼져 있으면 모든 기능이 꺼짐이다"
    assert "AI 사용이 꺼져" in rows["draft"]["feature_note"]

    configure_ai(app)
    for key, value in (("chat_enabled", True), ("assistant_narrative_enabled", False), ("game_ai_enabled", True)):
        assert client.put(f"/api/admin/settings/{key}", json={"value": value}, headers=_h(csrf)).status_code == 200
    rows = _rows(client)
    assert rows["assistant"]["feature_state"] == "on" and rows["draft"]["feature_state"] == "on"
    assert rows["narrative"]["feature_state"] == "off" and rows["narrative"]["feature_state_label"] == "꺼짐"
    assert rows["quiz"]["feature_state"] == "on"


def test_editing_creates_one_draft_and_publishing_switches_the_instruction(client, login_as):
    csrf = login_as("system_admin")
    first = client.patch(f"{FEATURES}/draft", json={"content": "첫 초안입니다."}, headers=_h(csrf))
    assert first.status_code == 200, first.text
    item = first.json()["item"]
    assert item["draft"]["content"] == "첫 초안입니다." and item["current"]["source"] == "builtin"
    again = client.patch(f"{FEATURES}/draft", json={"content": "고친 초안입니다."}, headers=_h(csrf)).json()["item"]
    assert again["draft"]["id"] == item["draft"]["id"], "고칠 때마다 새 초안을 만들었다"
    opened = client.post(f"{FEATURES}/draft/draft", headers=_h(csrf)).json()["item"]
    assert opened["draft"]["id"] == item["draft"]["id"], "초안 열기를 다시 보내 초안이 둘이 됐다"

    published = client.post(f"{FEATURES}/draft/publish", headers=_h(csrf))
    assert published.status_code == 200, published.text
    now = published.json()["item"]
    assert now["draft"] is None and now["current"]["source"] == "admin"
    assert now["current"]["instruction"] == "고친 초안입니다." and now["current"]["label"] == "관리자 작성 v1"
    versions = client.get("/api/admin/prompts", params={"slot": "draft"}).json()["items"]
    assert [v["status"] for v in versions if v.get("version") is not None] == ["published"]

    second = client.patch(f"{FEATURES}/draft", json={"content": "둘째 판입니다."}, headers=_h(csrf)).json()["item"]
    assert second["draft"]["name"] == now["current"]["name"] and second["draft"]["version"] == 2, "버전 줄기가 끊겼다"
    discarded = client.post(f"{FEATURES}/draft/discard", headers=_h(csrf)).json()["item"]
    assert discarded["draft"] is None and discarded["current"]["instruction"] == "고친 초안입니다."

    reset = client.post(f"{FEATURES}/draft/reset", headers=_h(csrf)).json()["item"]
    assert reset["current"]["source"] == "builtin"
    assert client.post(f"{FEATURES}/draft/reset", headers=_h(csrf)).status_code == 409
    assert client.post(f"{FEATURES}/draft/publish", headers=_h(csrf)).status_code == 409, "초안 없이 발행했다"


def test_the_drawer_address_accepts_old_links(client, login_as):
    csrf = login_as("system_admin")
    item = client.patch(f"{FEATURES}/quiz", json={"content": "퀴즈 초안입니다."}, headers=_h(csrf)).json()["item"]
    for key in ("quiz", "builtin:quiz", item["draft"]["id"]):
        reply = client.get(f"{FEATURES}/{key}")
        assert reply.status_code == 200 and reply.json()["item"]["slot"] == "quiz", key
    for bad in ("connection_test", "answer", "nothing"):
        assert client.get(f"{FEATURES}/{bad}").status_code == 404, bad


def test_only_global_admins_write(client, login_as, db, make_user):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    team = Department(name="기능팀", org_id=DEFAULT_ORG_ID)
    db.add(team)
    db.commit()
    boss = make_user("feature-dept-admin@goodmit.co.kr", role="admin")
    boss.department_id, boss.admin_scope, boss.scope_dept_id = team.id, "dept", team.id
    db.commit()

    csrf = login_as("admin", email="feature-dept-admin@goodmit.co.kr")
    assert client.get(FEATURES).status_code == 200
    assert client.patch(f"{FEATURES}/draft", json={"content": "x"}, headers=_h(csrf)).status_code == 403
    client.post("/logout", headers=_h(csrf))
    csrf = login_as("operator")
    assert client.get(FEATURES).status_code == 200
    assert client.post(f"{FEATURES}/draft/draft", headers=_h(csrf)).status_code == 403
    client.post("/logout", headers=_h(csrf))
    login_as("auditor")
    assert client.get(FEATURES).status_code == 200
