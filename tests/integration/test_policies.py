"""정책 PATCH 는 **보낸 칸만** 바꾼다 — 「용도」를 고쳤다고 규칙이 지워지면 안 된다.

이 회차 최악의 데이터 손실이었다. 관리자 콘솔(DataScreen)은 바뀐 필드만 PATCH 로 보내는데,
정책 수정 스키마의 `content` 기본값이 `"{}"` 라 「용도」한 줄만 고쳐도 그 정책의 업무 규칙이
빈 객체로 덮어써졌다. 응답은 200 이고 화면은 「저장했습니다.」라고 말했다. 초안 단계에서는
버전 기록에도 이전 내용이 없어 되돌릴 자리가 없었다.

정책이 프롬프트의 쌍둥이 화면이므로 두 화면이 같은 요청에 같은 답을 해야 한다
(`test_prompts.py` 가 반대쪽을 잰다).
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("system_admin")


def _h(csrf):
    return {"X-CSRF-Token": csrf}


RULES = {"required_fields": ["title", "owner"], "min_length": 10}


def _create(client, csrf, name="부분수정 정책", content=None, purpose="처음 용도"):
    r = client.post(
        "/api/admin/policies",
        json={"name": name, "content": RULES if content is None else content, "purpose": purpose},
        headers=_h(csrf),
    )
    assert r.status_code == 201, r.text
    return r.json()["item"]


def test_patching_only_the_purpose_keeps_the_content(client, admin_csrf):
    """ai-01 / xa-14: 용도만 보낸 PATCH 는 규칙(JSON)을 건드리지 않는다."""
    item = _create(client, admin_csrf)
    assert item["content"] == RULES

    r = client.patch(
        f"/api/admin/policies/{item['id']}",
        json={"purpose": "용도만 바꾼다"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == RULES
    assert r.json()["item"]["purpose"] == "용도만 바꾼다"

    after = client.get(f"/api/admin/policies/{item['id']}").json()["item"]
    assert after["content"] == RULES
    assert after["version"] == 1


def test_patching_the_content_still_replaces_the_rules(client, admin_csrf):
    """반례: 규칙을 **명시적으로** 보내면 그 값으로 바뀐다."""
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/policies/{item['id']}",
        json={"content": {"min_length": 99}},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == {"min_length": 99}
    assert r.json()["item"]["purpose"] == "처음 용도"


def test_explicit_empty_rules_still_clear_them(client, admin_csrf):
    """반례: 「빈 객체를 보냈다」는 「안 보냈다」와 다른 사실이다 — 보냈으면 비운다."""
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": {}}, headers=_h(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == {}


def test_policy_content_null_still_means_empty_rules(client, admin_csrf):
    """UB-22 계약 유지: 콘솔의 빈 JSON 입력란은 `null` 로 오고, 정책에서는 `{}` 로 받는다."""
    item = _create(client, admin_csrf)
    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": None}, headers=_h(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == {}


def test_invalid_json_content_is_still_rejected(client, admin_csrf):
    """반례: 보낸 규칙이 JSON 객체가 아니면 422 다 — 부분 갱신이 이 검증을 건너뛰면 안 된다."""
    item = _create(client, admin_csrf)
    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": "not-json"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 422, r.text
    assert client.get(f"/api/admin/policies/{item['id']}").json()["item"]["content"] == RULES


def test_empty_patch_body_changes_nothing(client, admin_csrf):
    item = _create(client, admin_csrf)
    r = client.patch(f"/api/admin/policies/{item['id']}", json={}, headers=_h(admin_csrf))
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == RULES
    assert r.json()["item"]["purpose"] == "처음 용도"


def test_partial_patch_still_refuses_a_published_row(client, admin_csrf):
    """반례: 발행된 정책은 여전히 못 고친다(초안에서만 고친다)."""
    item = _create(client, admin_csrf)
    for step in ("published",):
        r = client.post(
            f"/api/admin/policies/{item['id']}/transition",
            json={"status": step},
            headers=_h(admin_csrf),
        )
        assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"purpose": "발행본 용도"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("blank", ["   ", "\n\n", "\t"])
def test_blank_name_is_rejected(client, admin_csrf, blank):
    """xb-11: 공백·개행만으로 이뤄진 이름은 만들 수 없다."""
    r = client.post(
        "/api/admin/policies", json={"name": blank, "content": {}}, headers=_h(admin_csrf)
    )
    assert r.status_code == 422, f"공백만 이름이 통과했다: {r.status_code} {r.text}"


def test_a_real_name_is_still_accepted_and_trimmed(client, admin_csrf):
    """반례: 정상 이름은 만들어지고, 앞뒤 공백만 잘린다."""
    r = client.post(
        "/api/admin/policies", json={"name": "  휴가 승인  ", "content": {}}, headers=_h(admin_csrf)
    )
    assert r.status_code == 201, r.text
    assert r.json()["item"]["name"] == "휴가 승인"
