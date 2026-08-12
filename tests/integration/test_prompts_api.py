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


def test_patch_prompt_content_null_is_rejected_not_stored_as_braces(client, admin_csrf):
    # UB-22: PromptContentUpdateRequest/PolicyContentUpdateRequest 분리 전에는 이 스키마가
    # 하나(ContentUpdateRequest)였고, Policy용 "빈 JSON 입력란 → {}" 기본값 처리가 타입
    # 게이트 없이 Prompt에도 적용됐다. content가 null이면 프롬프트(자유 텍스트) 본문에는
    # 422 검증 오류가 나야 한다 — 문자열 리터럴 "{}"가 저장되면 안 된다.
    item = _create_prompt(client, admin_csrf)
    r = client.patch(
        f"/api/admin/prompts/{item['id']}", json={"content": None}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 422, r.text

    # 대조군: Policy는 여전히 null → {} 로 받아 줘야 한다(관리자 콘솔의 빈 JSON 입력란).
    policy = client.post(
        "/api/admin/policies", json={"name": "널 정책", "content": "{}"}, headers=_headers(admin_csrf)
    ).json()["item"]
    r = client.patch(
        f"/api/admin/policies/{policy['id']}", json={"content": None}, headers=_headers(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == {}


def _create_policy(client, csrf, name="휴가 승인 정책", content='{"days": 3}', purpose=None):
    body = {"name": name, "content": content}
    if purpose is not None:
        body["purpose"] = purpose
    r = client.post("/api/admin/policies", json=body, headers=_headers(csrf))
    assert r.status_code == 201, r.text
    return r.json()["item"]


# WF1 단독 결함 — Policy에 Prompt와 같은 purpose 필드가 없어 "이 정책이 무엇을 강제하는가"를
# 목록에서 말할 방법이 없었다(app/prompts/models.py::Policy, 마이그레이션 0058). Prompt가
# 이미 갖고 있던 계약(생성 시 저장, PATCH로 변경, new-version에 이어짐)을 그대로 따르는지 고정한다.
def test_policy_purpose_is_stored_and_returned(client, admin_csrf):
    item = _create_policy(client, admin_csrf, purpose="3일 이상 휴가는 팀장 승인이 필요합니다.")
    assert item["purpose"] == "3일 이상 휴가는 팀장 승인이 필요합니다."


def test_policy_purpose_defaults_to_null_not_empty_string(client, admin_csrf):
    # purpose를 아예 안 보내면 빈 문자열이 아니라 null이어야 한다 — "미기재"와 "빈 설명"은
    # 다른 사실이고, 빈 문자열로 채우면 화면이 그 둘을 구분할 방법이 없어진다.
    item = _create_policy(client, admin_csrf)
    assert item["purpose"] is None


def test_policy_purpose_editable_via_patch(client, admin_csrf):
    item = _create_policy(client, admin_csrf, purpose="처음 용도")
    r = client.patch(
        f"/api/admin/policies/{item['id']}",
        json={"content": item["content"] if isinstance(item["content"], str) else '{"days": 3}', "purpose": "바뀐 용도"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["purpose"] == "바뀐 용도"


def test_policy_purpose_carries_to_new_version(client, admin_csrf):
    v1 = _create_policy(client, admin_csrf, purpose="원본 용도")
    r = client.post(f"/api/admin/policies/{v1['id']}/new-version", headers=_headers(admin_csrf))
    assert r.status_code in (200, 201), r.text
    v2 = r.json()["item"]
    assert v2["version"] == 2
    assert v2["purpose"] == "원본 용도"


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


def test_rollback_name_has_the_same_length_limit_as_its_sibling_diff_endpoint(client, admin_csrf):
    """UB-30: 형제 엔드포인트 GET /diff/view의 name 쿼리 파라미터는 이미 max_length=120
    (Prompt.name의 DB 컬럼과 같은 값)을 거는데 rollback의 name 본문 필드만 무제한이었다."""
    r = client.post(
        "/api/admin/prompts/rollback",
        json={"name": "가" * 121, "version": 1},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, f"120자 넘는 name이 검증을 통과했다: {r.status_code} {r.text}"


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
