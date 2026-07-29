"""관리자 콘솔의 JSON 입력 필드가 실제로 보내는 페이로드로 각 생성/수정을 검증한다.

콘솔(common.js)은 `type:"json"` 필드를 **파싱된 객체**로, 비워 두면 **null**로 보낸다.
백엔드가 이를 못 받아 정책 생성·수정이 항상 422이고, 선택 JSON을 비운 템플릿·스케줄·문서
생성이 422였다(round16 제품 스윕 B1·B2·B4). 이 테스트가 그 계약을 못 박는다.
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _h(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def workflow_id(client, admin_csrf):
    r = client.post(
        "/api/admin/workflows",
        json={"name": "콘솔계약 WF", "webhook_url": "http://127.0.0.1:5678/webhook/weekly-report",
              "operation_mode": "write"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text
    return r.json()["workflow"]["id"]


def test_policy_create_accepts_parsed_object(client, admin_csrf):
    # B1(HIGH): 콘솔은 content를 파싱된 객체로 보낸다. 문자열만 받으면 정책 생성이 항상 422.
    r = client.post(
        "/api/admin/policies",
        json={"name": "필수필드 정책", "content": {"required_fields": ["title"]}},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["item"]["content"] == {"required_fields": ["title"]}


def test_policy_update_accepts_parsed_object(client, admin_csrf):
    # B1(HIGH): 정책 수정도 객체를 보낸다.
    created = client.post(
        "/api/admin/policies",
        json={"name": "수정용 정책", "content": {"a": 1}},
        headers=_h(admin_csrf),
    ).json()["item"]
    r = client.patch(
        f"/api/admin/policies/{created['id']}",
        json={"content": {"a": 2, "b": 3}},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text


def test_prompt_content_still_free_text(client, admin_csrf):
    # 회귀 방지: 프롬프트 본문은 자유 텍스트(문자열)라 코어서가 건드리면 안 된다.
    r = client.post(
        "/api/admin/prompts",
        json={"name": "자유텍스트 프롬프트", "content": "이건 그냥 문장입니다."},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["item"]["content"] == "이건 그냥 문장입니다."


def test_template_create_with_null_optional_json(client, admin_csrf, workflow_id):
    # B2(MED): 선택 JSON(input_schema/approval_policy)을 비우면 콘솔은 null을 보낸다. 기본값으로 받는다.
    r = client.post(
        "/api/admin/templates",
        json={"name": "빈스키마 템플릿", "target_type": "workflow", "target_ref": workflow_id,
              "input_schema": None, "approval_policy": None},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text  # 옛 코드는 null → 422였다
    body = r.json()
    item = body.get("item") or body.get("template") or body
    assert item.get("input_schema") == {} and item.get("approval_policy") == {}, body


def test_schedule_create_with_null_optional_json(client, admin_csrf, workflow_id):
    # B2(MED): 스케줄의 payload_template/retry_policy를 비우면 null. 기본값으로 받는다.
    r = client.post(
        "/api/admin/schedules",
        json={"name": "빈페이로드 스케줄", "target_type": "workflow", "target_ref": workflow_id,
              "cron_expression": "0 9 * * *", "payload_template": None, "retry_policy": None,
              "concurrency_policy": "skip", "misfire_policy": "skip"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text


def test_document_generate_auto_publish_mode(client, admin_csrf, workflow_id):
    # B4(MED): 콘솔의 '자동 발행' 모드 값은 auto_publish여야 한다(옛 'auto'는 유효값이 아니라 실패).
    r = client.post(
        "/api/admin/documents/generate",
        json={"workflow_id": workflow_id, "period": "2026-W29", "mode": "auto_publish", "config": None},
        headers=_h(admin_csrf),
    )
    # 성공(202/201) 또는 승인 필요 등 도메인 응답. 422(계약 불일치)만 아니면 된다.
    assert r.status_code != 422, r.text
