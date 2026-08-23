"""qa-contract-change: 선택 JSON 을 비우면 콘솔이 null 을 보낸다는 계약의 소비자가 셋에서 하나로 줄었다 — 템플릿·문서 생성 화면이 S11 과 함께 사라지고 스케줄만 남았다. 남은 스케줄 쪽 단언은 그대로이고, 계약(널을 기본값으로 받는다) 자체는 안 바뀌었다."""

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


# S11 이후 스케줄 대상은 `system` 하나다(D-267).
@pytest.fixture()
def workflow_id():
    return "noop"


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


def test_schedule_create_with_null_optional_json(client, admin_csrf, workflow_id):
    # B2(MED): 스케줄의 payload_template/retry_policy를 비우면 null. 기본값으로 받는다.
    r = client.post(
        "/api/admin/schedules",
        json={"name": "빈페이로드 스케줄", "target_type": "system", "target_ref": workflow_id,
              "cron_expression": "0 9 * * *", "payload_template": None, "retry_policy": None,
              "concurrency_policy": "skip", "misfire_policy": "skip"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text


# 템플릿·문서 생성의 같은 계약(선택 JSON 을 비우면 null 이 온다)은 S11 이 그 두 화면과
# 함께 걷어냈다. 남은 소비자는 스케줄 하나이고 위 시험이 그것을 본다.
