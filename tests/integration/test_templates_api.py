import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def workflow_id(client, admin_csrf):
    r = client.post(
        "/api/admin/workflows",
        json={
            "name": "주간 보고서 workflow",
            "webhook_url": "http://127.0.0.1:5678/webhook/weekly-report",
            "operation_mode": "write",
        },
        headers=_headers(admin_csrf),
    )
    return r.json()["workflow"]["id"]


def _template_payload(workflow_id, **overrides):
    return {
        "name": "주간 프로젝트 보고서",
        "description": "매주 월요일 지난주 완료 작업 요약",
        "input_schema": {"type": "object", "properties": {"week": {"type": "string"}}},
        "target_type": "workflow",
        "target_ref": workflow_id,
        "approval_policy": {"required": True},
        **overrides,
    }


def test_create_template_disabled_by_default(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/templates",
        json=_template_payload(workflow_id),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["template"]["enabled"] is False


def test_template_target_must_exist(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/templates",
        json=_template_payload("no-such-workflow", name="유령 대상"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_template_bad_target_type(client, admin_csrf, workflow_id):
    r = client.post(
        "/api/admin/templates",
        json=_template_payload(workflow_id, target_type="cron"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422


def test_template_bad_policy_id_rejected(client, admin_csrf, workflow_id):
    # Regression: policy_id was accepted and stored without existence validation.
    r = client.post(
        "/api/admin/templates",
        json=_template_payload(workflow_id, name="정책 유령", policy_id="no-such-policy"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text


def test_template_update_and_enable(client, admin_csrf, workflow_id):
    created = client.post(
        "/api/admin/templates",
        json=_template_payload(workflow_id),
        headers=_headers(admin_csrf),
    ).json()["template"]

    r = client.put(
        f"/api/admin/templates/{created['id']}",
        json=_template_payload(workflow_id, description="수정된 설명"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 200
    assert r.json()["template"]["description"] == "수정된 설명"

    r = client.post(
        f"/api/admin/templates/{created['id']}/enable", headers=_headers(admin_csrf)
    )
    assert r.status_code == 200


def test_duplicate_template_name(client, admin_csrf, workflow_id):
    payload = _template_payload(workflow_id)
    client.post("/api/admin/templates", json=payload, headers=_headers(admin_csrf))
    r = client.post("/api/admin/templates", json=payload, headers=_headers(admin_csrf))
    assert r.status_code == 409


def test_rename_to_existing_name_returns_409_not_500(client, admin_csrf, workflow_id):
    """다른 템플릿 이름으로 바꾸면 409(생성 경로와 일관)여야 한다 — 옛 코드는 IntegrityError로
    500을 냈다(round16 제품 스윕)."""
    a = client.post("/api/admin/templates", json=_template_payload(workflow_id, name="템플릿 A"),
                    headers=_headers(admin_csrf)).json()
    client.post("/api/admin/templates", json=_template_payload(workflow_id, name="템플릿 B"),
                headers=_headers(admin_csrf))
    tid = (a.get("item") or a.get("template") or a)["id"]
    r = client.put(f"/api/admin/templates/{tid}",
                   json=_template_payload(workflow_id, name="템플릿 B"),
                   headers=_headers(admin_csrf))
    assert r.status_code == 409, r.text


# UB-14: 활성화 시점에 대상 Workflow가 여전히 살아 있는지 확인해야 한다 — 예전엔 비활성화된
# 대상을 가리키는 템플릿도 무조건 200으로 활성화됐고, 문제는 나중에 사용자의 문서 생성
# 요청에서야 터졌다.
def test_enable_rejects_disabled_target_workflow(client, admin_csrf, workflow_id):
    created = client.post(
        "/api/admin/templates", json=_template_payload(workflow_id), headers=_headers(admin_csrf)
    ).json()["template"]

    disable = client.post(
        f"/api/admin/workflows/{workflow_id}/disable", headers=_headers(admin_csrf)
    )
    assert disable.status_code == 200, disable.text

    r = client.post(
        f"/api/admin/templates/{created['id']}/enable", headers=_headers(admin_csrf)
    )
    assert r.status_code == 409, r.text

    # 대상을 다시 켜면 정상적으로 활성화된다 — 게이트가 존재 자체가 아니라 살아있는지만
    # 본다는 것을 함께 고정한다.
    client.post(f"/api/admin/workflows/{workflow_id}/enable", headers=_headers(admin_csrf))
    r2 = client.post(
        f"/api/admin/templates/{created['id']}/enable", headers=_headers(admin_csrf)
    )
    assert r2.status_code == 200, r2.text


# UB-29: archived 상태(다시는 안 쓴다는 의도적 퇴역 표시)의 Prompt/Policy를 새 템플릿에
# 바인딩할 수 있었다 — draft/test/review는 여전히 허용한다(발행본 없을 때 pinned 값으로
# 폴백하는 documents/service.py의 의도적 fail-safe와 충돌하지 않도록).
def test_create_rejects_archived_prompt(client, admin_csrf, workflow_id):
    prompt = client.post(
        "/api/admin/prompts",
        json={"name": "보관될 프롬프트", "content": "안녕하세요"},
        headers=_headers(admin_csrf),
    ).json()
    prompt_id = (prompt.get("item") or prompt)["id"]
    transition = client.post(
        f"/api/admin/prompts/{prompt_id}/transition",
        json={"status": "archived"},
        headers=_headers(admin_csrf),
    )
    assert transition.status_code == 200, transition.text

    r = client.post(
        "/api/admin/templates",
        json=_template_payload(workflow_id, prompt_id=prompt_id, name="보관 프롬프트 템플릿"),
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 422, r.text
