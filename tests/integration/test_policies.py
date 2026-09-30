"""정책 PATCH 는 **보낸 칸만** 바꾼다 — 「용도」를 고쳤다고 규칙이 지워지면 안 된다.

이 회차 최악의 데이터 손실이었다. 관리자 콘솔(DataScreen)은 바뀐 필드만 PATCH 로 보내는데,
정책 수정 스키마의 `content` 기본값이 `"{}"` 라 「용도」한 줄만 고쳐도 그 정책의 업무 규칙이
빈 객체로 덮어써졌다. 응답은 200 이고 화면은 「저장했습니다.」라고 말했다. 초안 단계에서는
버전 기록에도 이전 내용이 없어 되돌릴 자리가 없었다.

정책이 프롬프트의 쌍둥이 화면이므로 두 화면이 같은 요청에 같은 답을 해야 한다
(`test_prompts.py` 가 반대쪽을 잰다).

qa-contract-change: 정책에 종류와 규칙 칸이 생겼다(D-519). 규칙은 종류마다 정해진 칸만 받고 빠진 칸은 기본값으로 채우므로 「빈 객체를 보내면 비운다」는 「빈 객체를 보내면 기본값으로 되돌린다」가 됐다. 부분 갱신과 JSON 검증의 계약은 그대로다.
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("system_admin")


def _h(csrf):
    return {"X-CSRF-Token": csrf}


# 응답 제한 정책의 규칙(D-519). 빠진 칸이 없게 적어 두어야 「그대로 남는다」를 값 그대로 잴 수 있다.
RULES = {"max_output_chars": 800, "block_external_links": True}
DEFAULTS = {"max_output_chars": None, "block_external_links": False}


def _create(client, csrf, name="부분수정 정책", content=None, purpose="처음 용도"):
    r = client.post(
        "/api/admin/policies",
        json={"name": name, "content": RULES if content is None else content, "purpose": purpose,
              "kind": "content", "applies_to": "*"},
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
        json={"content": {"max_output_chars": 500}},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == {"max_output_chars": 500, "block_external_links": False}
    assert r.json()["item"]["purpose"] == "처음 용도"


def test_explicit_empty_rules_reset_them_to_defaults(client, admin_csrf):
    """반례: 「빈 객체를 보냈다」는 「안 보냈다」와 다른 사실이다 — 보냈으면 기본값으로 되돌린다."""
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": {}}, headers=_h(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == DEFAULTS


def test_policy_content_null_still_means_empty_rules(client, admin_csrf):
    """UB-22 계약 유지: 콘솔의 빈 JSON 입력란은 `null` 로 오고, 정책에서는 `{}` 로 받는다."""
    item = _create(client, admin_csrf)
    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": None}, headers=_h(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == DEFAULTS


def test_invalid_json_content_is_still_rejected(client, admin_csrf):
    """반례: 보낸 규칙이 JSON 객체가 아니면 422 다 — 부분 갱신이 이 검증을 건너뛰면 안 된다."""
    item = _create(client, admin_csrf)
    r = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": "not-json"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 422, r.text
    assert client.get(f"/api/admin/policies/{item['id']}").json()["item"]["content"] == RULES
    # 종류에 없는 규칙도 422 다 — 모르는 칸을 조용히 저장하면 걸리지 않는 규칙을 믿게 된다.
    unknown = client.patch(
        f"/api/admin/policies/{item['id']}", json={"content": {"min_length": 10}}, headers=_h(admin_csrf)
    )
    assert unknown.status_code == 422, unknown.text


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
        "/api/admin/policies", json={"name": blank, "content": {}, "kind": "content"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 422, f"공백만 이름이 통과했다: {r.status_code} {r.text}"


def test_a_real_name_is_still_accepted_and_trimmed(client, admin_csrf):
    """반례: 정상 이름은 만들어지고, 앞뒤 공백만 잘린다."""
    r = client.post(
        "/api/admin/policies", json={"name": "  휴가 승인  ", "content": {}, "kind": "content"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 201, r.text
    assert r.json()["item"]["name"] == "휴가 승인"
