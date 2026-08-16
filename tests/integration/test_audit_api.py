import pytest

pytestmark = pytest.mark.integration


def test_audit_entries_written_and_filterable(client, login_as):
    csrf = login_as("admin")
    headers = {"X-CSRF-Token": csrf}

    client.post(
        "/api/admin/users",
        json={"email": "audited@goodmit.co.kr", "display_name": "감사 대상"},
        headers=headers,
    )

    r = client.get("/api/admin/audit", params={"action": "user.create"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["object_type"] == "user"
    assert entry["after"]["email"] == "audited@goodmit.co.kr"
    assert entry["user_id"] is not None
    assert entry["request_id"]

    # Filter that matches nothing.
    r = client.get("/api/admin/audit", params={"action": "user.delete"})
    assert r.json()["total"] == 0


def test_audit_ordered_newest_first(client, login_as, fake_clock):
    csrf = login_as("admin")
    headers = {"X-CSRF-Token": csrf}
    for i in range(3):
        fake_clock.advance(60)
        client.post(
            "/api/admin/users",
            json={"email": f"order{i}@goodmit.co.kr", "display_name": f"순서{i}"},
            headers=headers,
        )

    r = client.get("/api/admin/audit", params={"action": "user.create"})
    items = r.json()["items"]
    created = [item["created_at"] for item in items]
    assert created == sorted(created, reverse=True)


def test_audit_invalid_date_filter_rejected(client, login_as):
    login_as("auditor")
    r = client.get("/api/admin/audit", params={"since": "not-a-date"})
    assert r.status_code == 422


def test_audit_result_filter_isolates_failures(client, login_as, make_user):
    """'실패만 보기' 가 실제로 실패만 준다 (F7).

    이 조건은 감사 화면의 딥링크(`#/audit?user_id=…&result=failure`)가 보내는 것이다.
    화면이 그 값을 버리고 있었는데, 화면을 고치기 전에 **서버가 정말 거르는지**부터
    못 박는다 — 서버가 안 거르는데 화면만 보내면 '거르는 시늉'이 하나 더 늘 뿐이다.
    """
    make_user(email="target@goodmit.co.kr", role="user")
    # 실패 한 건(비밀번호 오류)과 성공 한 건(로그인)을 같은 사람으로 만든다.
    client.post("/login", json={"email": "target@goodmit.co.kr", "password": "wrong-one!"})
    login_as("user", email="target@goodmit.co.kr")
    login_as("auditor")

    both = client.get("/api/admin/audit", params={"action": "user.login_failed"}).json()
    assert both["total"] == 1

    only_failure = client.get("/api/admin/audit", params={"result": "failure"}).json()
    assert only_failure["total"] >= 1
    assert {item["result"] for item in only_failure["items"]} == {"failure"}

    only_success = client.get("/api/admin/audit", params={"result": "success"}).json()
    assert {item["result"] for item in only_success["items"]} == {"success"}
    # 두 집합이 실제로 갈린다 — 전체가 그대로 나오면 필터가 헛도는 것이다.
    assert only_failure["total"] + only_success["total"] == client.get(
        "/api/admin/audit"
    ).json()["total"]


# VIS-59: 로그인/로그아웃이 화면을 지배해 실제로 봐야 할 사건(설정 변경 등)이 묻힌다.
# exclude_actions 는 action(정확 일치, 하나만 골라 좁힘)과 반대 방향이다 — "이것만 빼고 전부".
def test_audit_exclude_actions_hides_routine_login_logout_noise(client, login_as):
    # user.login(로그인 자체) 여러 건을 먼저 만들고, 마지막 세션의 csrf로 계속한다
    # (login_as를 다시 부르면 이전 세션의 csrf가 무효화된다).
    for _ in range(2):
        login_as("admin")
    csrf = login_as("admin")
    headers = {"X-CSRF-Token": csrf}
    # + user.create(진짜 봐야 할 사건) 한 건.
    client.post(
        "/api/admin/users",
        json={"email": "vis59@goodmit.co.kr", "display_name": "VIS-59"},
        headers=headers,
    )

    everything = client.get("/api/admin/audit").json()
    assert everything["total"] >= 4  # 로그인 여러 건 + 생성 1건

    filtered = client.get(
        "/api/admin/audit", params={"exclude_actions": "user.login,user.logout"}
    ).json()
    actions = {item["action"] for item in filtered["items"]}
    assert "user.login" not in actions
    assert "user.logout" not in actions
    assert "user.create" in actions
    assert filtered["total"] < everything["total"]


def test_audit_export_csv_respects_exclude_actions_too(client, login_as):
    """목록과 CSV 내보내기가 같은 질의를 쓴다는 계약(0033) — exclude_actions도 예외가 아니다."""
    login_as("admin")
    csrf = login_as("admin")  # 여러 번 로그인해 login 행을 만든 뒤, 마지막 세션의 csrf를 쓴다.
    headers = {"X-CSRF-Token": csrf}
    client.post(
        "/api/admin/users",
        json={"email": "vis59-csv@goodmit.co.kr", "display_name": "VIS-59 CSV"},
        headers=headers,
    )

    r = client.get(
        "/api/admin/audit/export.csv", params={"exclude_actions": "user.login,user.logout"}
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "user.create" in body
    # login/logout 행 자체가 CSV에 없어야 한다(액션 원문 문자열로 확인).
    assert "user.login" not in body
    assert "user.logout" not in body
