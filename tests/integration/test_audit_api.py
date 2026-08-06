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
