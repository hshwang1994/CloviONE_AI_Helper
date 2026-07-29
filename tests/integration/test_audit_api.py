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
