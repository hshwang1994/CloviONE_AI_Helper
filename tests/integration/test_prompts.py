"""프롬프트 PATCH 는 **보낸 칸만** 바꾸고, 이름은 공백만으로 만들 수 없다.

관리자 콘솔(DataScreen)은 바뀐 필드만 PATCH 로 보낸다. 그런데 프롬프트의 수정 스키마는
`content` 를 필수로 받고 있어서, 「용도」한 줄만 고치면 422 가 났다 — 게다가 오류가 손대지도
않은 「프롬프트 내용」 칸에 「필수 항목입니다」로 붙어, 관리자는 무엇을 고쳐야 할지 알 수
없었다. 같은 뿌리에서 정책은 반대로 200 을 주며 규칙을 지웠다(`test_policies.py`).

이름 검증은 `app/org/service.py::normalize_name` 과 같은 규칙이다. 공백만 남는 이름은 목록·
사용 통계·이름 필터에서 가리킬 수 없는 행을 만든다.
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("system_admin")


def _h(csrf):
    return {"X-CSRF-Token": csrf}


def _create(client, csrf, name="부분수정 프롬프트", content="원본 지시문", purpose="처음 용도"):
    r = client.post(
        "/api/admin/prompts",
        # 발행하려면 사용처가 있어야 한다(D-518).
        json={"name": name, "content": content, "purpose": purpose, "slot": "answer"},
        headers=_h(csrf),
    )
    assert r.status_code == 201, r.text
    return r.json()["item"]


def test_patching_only_the_purpose_keeps_the_content(client, admin_csrf):
    """ai-02: 용도만 보낸 PATCH 가 200 이고, 내용은 저장된 값 그대로다."""
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/prompts/{item['id']}",
        json={"purpose": "바뀐 용도"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["purpose"] == "바뀐 용도"
    assert r.json()["item"]["content"] == "원본 지시문"

    after = client.get(f"/api/admin/prompts/{item['id']}").json()["item"]
    assert after["content"] == "원본 지시문"
    assert after["purpose"] == "바뀐 용도"
    # 부분 수정은 버전을 만들지 않는다 — 같은 초안을 계속 고치는 일이다.
    assert after["version"] == 1


def test_patching_the_content_still_changes_it(client, admin_csrf):
    """반례: 내용을 **명시적으로** 보내면 그 값이 저장돼야 한다(안 고쳐지면 그것도 결함이다)."""
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/prompts/{item['id']}",
        json={"content": "새 지시문"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == "새 지시문"
    # 안 보낸 용도는 그대로 남는다 — 반대 방향의 같은 계약이다.
    assert r.json()["item"]["purpose"] == "처음 용도"


def test_patching_both_fields_at_once_changes_both(client, admin_csrf):
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/prompts/{item['id']}",
        json={"content": "둘 다 바꾼 지시문", "purpose": "둘 다 바꾼 용도"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == "둘 다 바꾼 지시문"
    assert r.json()["item"]["purpose"] == "둘 다 바꾼 용도"


def test_sending_null_purpose_clears_it(client, admin_csrf):
    """`null` 은 「안 보냈다」와 다른 사실이다 — 용도를 지우겠다는 뜻으로 받는다."""
    item = _create(client, admin_csrf)

    r = client.patch(
        f"/api/admin/prompts/{item['id']}", json={"purpose": None}, headers=_h(admin_csrf)
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["purpose"] is None
    assert r.json()["item"]["content"] == "원본 지시문"


def test_prompt_content_null_is_still_rejected(client, admin_csrf):
    """UB-22 계약 유지: 프롬프트 본문은 자유 텍스트라 `null` 은 422 다.

    부분 갱신을 열면서 이 게이트까지 열리면, 문자열 리터럴 "{}" 가 본문에 저장되던 옛 결함이
    되살아난다. 「안 보냈다」(부분 갱신)와 「null 을 보냈다」(잘못된 값)는 다른 사실이다.
    """
    item = _create(client, admin_csrf)
    r = client.patch(
        f"/api/admin/prompts/{item['id']}", json={"content": None}, headers=_h(admin_csrf)
    )
    assert r.status_code == 422, r.text


def test_empty_patch_body_changes_nothing(client, admin_csrf):
    item = _create(client, admin_csrf)
    r = client.patch(f"/api/admin/prompts/{item['id']}", json={}, headers=_h(admin_csrf))
    assert r.status_code == 200, r.text
    assert r.json()["item"]["content"] == "원본 지시문"
    assert r.json()["item"]["purpose"] == "처음 용도"


def test_partial_patch_still_refuses_a_published_row(client, admin_csrf):
    """반례: 부분 갱신이 되더라도 발행된 버전은 여전히 못 고친다(초안에서만 고친다)."""
    item = _create(client, admin_csrf)
    for step in ("published",):
        r = client.post(
            f"/api/admin/prompts/{item['id']}/transition",
            json={"status": step},
            headers=_h(admin_csrf),
        )
        assert r.status_code == 200, r.text

    r = client.patch(
        f"/api/admin/prompts/{item['id']}", json={"purpose": "발행본 용도"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 409, r.text
    assert client.get(f"/api/admin/prompts/{item['id']}").json()["item"]["purpose"] == "처음 용도"


@pytest.mark.parametrize("blank", ["   ", "\n\n", "\t", " \n "])
def test_blank_name_is_rejected(client, admin_csrf, blank):
    """xb-11: 공백·개행만으로 이뤄진 이름은 만들 수 없다."""
    r = client.post(
        "/api/admin/prompts", json={"name": blank, "content": "x"}, headers=_h(admin_csrf)
    )
    assert r.status_code == 422, f"공백만 이름이 통과했다: {r.status_code} {r.text}"


def test_a_real_name_is_still_accepted_and_trimmed(client, admin_csrf):
    """반례: 정상 이름은 그대로 만들어진다. 앞뒤 공백은 이름의 일부가 아니라 잘라 낸다 —
    ' 티켓 요약' 과 '티켓 요약' 이 갈라지면 중복 검사와 버전 묶음이 함께 갈라진다."""
    r = client.post(
        "/api/admin/prompts",
        json={"name": "  티켓 요약  ", "content": "x"},
        headers=_h(admin_csrf),
    )
    assert r.status_code == 201, r.text
    assert r.json()["item"]["name"] == "티켓 요약"

    dup = client.post(
        "/api/admin/prompts", json={"name": "티켓 요약", "content": "y"}, headers=_h(admin_csrf)
    )
    assert dup.status_code == 409, dup.text
