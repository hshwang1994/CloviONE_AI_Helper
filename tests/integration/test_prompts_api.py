import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _create_prompt(client, csrf, name="티켓 요약 프롬프트", content="v1 내용"):
    r = client.post(
        "/api/admin/prompts",
        json={"name": name, "content": content, "purpose": "테스트"},
        headers=_headers(csrf),
    )
    assert r.status_code == 201, r.text
    return r.json()["item"]


def test_create_starts_as_draft_v1(client, admin_csrf):
    item = _create_prompt(client, admin_csrf)
    assert item["status"] == "draft"
    assert item["version"] == 1


def test_duplicate_name_conflict(client, admin_csrf):
    _create_prompt(client, admin_csrf)
    r = client.post(
        "/api/admin/prompts",
        json={"name": "티켓 요약 프롬프트", "content": "x"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409


def test_duplicate_name_conflict_after_new_version(client, admin_csrf):
    # Regression: once a name has 2+ versions, the existence check used
    # scalar_one_or_none() -> MultipleResultsFound -> HTTP 500. Must stay 409.
    item = _create_prompt(client, admin_csrf)
    r = client.post(
        f"/api/admin/prompts/{item['id']}/new-version", headers=_headers(admin_csrf)
    )
    assert r.status_code in (200, 201), r.text
    r = client.post(
        "/api/admin/prompts",
        json={"name": "티켓 요약 프롬프트", "content": "y"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409, r.text


def _transition(client, csrf, row_id, status):
    return client.post(
        f"/api/admin/prompts/{row_id}/transition",
        json={"status": status},
        headers=_headers(csrf),
    )


def test_lifecycle_happy_path(client, admin_csrf):
    item = _create_prompt(client, admin_csrf)
    for step in ["test", "review", "published"]:
        r = _transition(client, admin_csrf, item["id"], step)
        assert r.status_code == 200, r.text
    assert r.json()["item"]["published_at"] is not None


def test_invalid_transition_rejected(client, admin_csrf):
    item = _create_prompt(client, admin_csrf)
    r = _transition(client, admin_csrf, item["id"], "published")  # draft → published
    assert r.status_code == 409


def test_content_editable_only_in_draft(client, admin_csrf):
    item = _create_prompt(client, admin_csrf)
    _transition(client, admin_csrf, item["id"], "test")
    r = client.patch(
        f"/api/admin/prompts/{item['id']}",
        json={"content": "수정 시도"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409


def test_publish_archives_previous_published(client, admin_csrf):
    v1 = _create_prompt(client, admin_csrf)
    for step in ["test", "review", "published"]:
        _transition(client, admin_csrf, v1["id"], step)

    v2 = client.post(
        f"/api/admin/prompts/{v1['id']}/new-version", headers=_headers(admin_csrf)
    ).json()["item"]
    assert v2["version"] == 2
    assert v2["status"] == "draft"
    client.patch(
        f"/api/admin/prompts/{v2['id']}",
        json={"content": "v2 내용"},
        headers=_headers(admin_csrf),
    )
    for step in ["test", "review", "published"]:
        _transition(client, admin_csrf, v2["id"], step)

    listing = client.get(
        "/api/admin/prompts", params={"name": "티켓 요약 프롬프트"}
    ).json()["items"]
    by_version = {i["version"]: i["status"] for i in listing}
    assert by_version == {1: "archived", 2: "published"}


def test_diff_between_versions(client, admin_csrf):
    v1 = _create_prompt(client, admin_csrf, content="옛날 내용")
    v2 = client.post(
        f"/api/admin/prompts/{v1['id']}/new-version", headers=_headers(admin_csrf)
    ).json()["item"]
    client.patch(
        f"/api/admin/prompts/{v2['id']}",
        json={"content": "새로운 내용"},
        headers=_headers(admin_csrf),
    )
    r = client.get(
        "/api/admin/prompts/diff/view",
        params={"name": "티켓 요약 프롬프트", "from": 1, "to": 2},
    )
    assert r.status_code == 200
    assert "-옛날 내용" in r.json()["diff"]
    assert "+새로운 내용" in r.json()["diff"]


def test_rollback_republishes_old_content_as_new_version(client, admin_csrf):
    v1 = _create_prompt(client, admin_csrf, content="v1 내용")
    for step in ["test", "review", "published"]:
        _transition(client, admin_csrf, v1["id"], step)
    v2 = client.post(
        f"/api/admin/prompts/{v1['id']}/new-version", headers=_headers(admin_csrf)
    ).json()["item"]
    client.patch(
        f"/api/admin/prompts/{v2['id']}", json={"content": "나쁜 v2"}, headers=_headers(admin_csrf)
    )
    for step in ["test", "review", "published"]:
        _transition(client, admin_csrf, v2["id"], step)

    r = client.post(
        "/api/admin/prompts/rollback",
        json={"name": "티켓 요약 프롬프트", "version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    v3 = r.json()["item"]
    assert v3["version"] == 3
    assert v3["status"] == "published"
    assert v3["content"] == "v1 내용"


def test_policy_content_must_be_json_object(client, admin_csrf):
    r = client.post(
        "/api/admin/policies",
        json={"name": "티켓 정책", "content": "not-json"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422

    r = client.post(
        "/api/admin/policies",
        json={"name": "티켓 정책", "content": '{"required_fields": ["title"]}'},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201
    assert r.json()["item"]["content"] == {"required_fields": ["title"]}


def test_operator_cannot_mutate_prompts(client, login_as):
    csrf = login_as("operator")
    r = client.post(
        "/api/admin/prompts",
        json={"name": "op 프롬프트", "content": "x"},
        headers=_headers(csrf),
    )
    assert r.status_code == 403
    assert client.get("/api/admin/prompts").status_code == 200
