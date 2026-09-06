"""공지 쓰기 API 의 거절은 정직한 4xx 다 (S-08 · XB-05 · XB-16 · XB-04).

공지는 **전 사용자에게 뜨는 배너**다. 그래서 제목은 그 행을 가리키는 유일한 문자열이고,
빈 제목은 관리자 목록에서도 사용자 화면에서도 정체를 알 수 없는 행을 만든다. 화면 폼이
필수 표시를 하더라도 경계는 서버다 — 이 API 는 연동·스크립트가 직접 부른다.

여기서 세우는 계약 셋:

1. **공백뿐인 제목은 422 다.** `Field(min_length=1)` 은 strip 전 길이를 보므로 「   」가
   검사를 지나고, 생성 경로의 `strip()` 이 그것을 빈 제목으로 만들었다. 수정 경로는
   strip 조차 안 해서 공백이 그대로 남았다 — 두 경로가 서로 다른 값을 만들었다.
2. **NOT NULL 컬럼에 null 을 보내면 422 다.** 보내지 않는 것(그대로 둔다)과 null 로
   보내는 것(값을 지운다)은 다른 요청이고, 뒤쪽은 성립하지 않는다.
3. **NUL 이 든 문자열은 422 다.** PostgreSQL 의 text 가 담지 못하는 문자라 예전에는
   psycopg 가 던지는 `DataError` 까지 내려가 500 이 됐다.

반례를 같은 파일에 둔다 — 정상 제목·한글·이모지는 그대로 저장되고, 필드를 안 보내는
부분 수정은 예전처럼 동작한다. 반례가 없으면 위 셋은 「전부 거절하는」 구현으로도
초록이 된다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _create(client, csrf, **overrides):
    body = {"title": "공지 제목", "body": "본문", "level": "info", "audience": "all"}
    body.update(overrides)
    return client.post(
        "/api/admin/announcements", json=body, headers={"X-CSRF-Token": csrf}
    )


def _created_id(client, csrf) -> str:
    response = _create(client, csrf)
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ── 공백뿐인 제목 (S-08 · XB-16) ─────────────────────────────────────────────


@pytest.mark.parametrize("blank", ["   ", "\t", "\n\n"])
def test_a_whitespace_only_title_is_refused_instead_of_becoming_an_empty_banner(
    client, login_as, blank
):
    """🔴 예전에는 201 이었고 저장된 제목은 빈 문자열이었다 — 목록에서 그 행이
    무엇인지 알 수 없어 지우려면 id 를 봐야 했다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, title=blank)
    assert response.status_code == 422, response.text
    assert "제목" in response.json()["error"]["message"]


def test_a_whitespace_only_title_is_refused_on_update_too(client, login_as):
    """수정 경로는 strip 도 안 해서 공백 세 칸이 그대로 남았다 — 같은 규칙을 쓴다."""
    csrf = login_as("system_admin")
    row_id = _created_id(client, csrf)

    response = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"title": "   "},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


def test_a_title_with_surrounding_spaces_is_stored_trimmed(client, login_as):
    """반례 — 공백이 낀 정상 제목은 거절이 아니라 정규화다. 검증한 형태와 저장한
    형태가 같아야 목록·감사 로그·배너가 같은 문자열을 말한다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, title="  점검 안내  ")
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "점검 안내"

    patched = client.patch(
        f"/api/admin/announcements/{response.json()['id']}",
        json={"title": "  바뀐 제목  "},
        headers={"X-CSRF-Token": csrf},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "바뀐 제목"


# ── NOT NULL 컬럼에 null (XB-05) ─────────────────────────────────────────────


@pytest.mark.parametrize("field", ["active", "dismissible"])
def test_patching_a_boolean_column_to_null_is_a_clean_422_not_a_500(
    client, login_as, field
):
    """🔴 FN-40 이 title·body·level·audience 넷을 고치면서 이 두 칸을 빼놓았다.
    둘 다 `bool | None` 이고 컬럼은 NOT NULL 이라 같은 500 이 그대로 남아 있었다."""
    csrf = login_as("system_admin")
    row_id = _created_id(client, csrf)

    response = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={field: None},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("field", ["active", "dismissible"])
def test_patching_the_same_columns_with_a_real_boolean_still_works(client, login_as, field):
    """반례 — null 을 막는 것이 「이 칸은 못 바꾼다」가 되면 배너를 내릴 수 없다."""
    csrf = login_as("system_admin")
    row_id = _created_id(client, csrf)

    response = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={field: False},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()[field] is False


def test_omitting_a_field_leaves_it_alone(client, login_as):
    """보내지 않는 것과 null 로 보내는 것은 다른 요청이다 — 안 보내면 그대로 있는다."""
    csrf = login_as("system_admin")
    row_id = _created_id(client, csrf)

    response = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"title": "제목만 바꾼다"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is True
    assert response.json()["dismissible"] is True


# ── NUL (XB-04) ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["title", "body", "link_label"])
def test_a_nul_byte_in_a_string_field_is_422_not_a_psycopg_error(client, login_as, field):
    """🔴 PostgreSQL 의 text 는 NUL 을 담지 못한다. 예전에는 그 사실을 psycopg 가
    처음 말했고, 관리자가 본 것은 원인을 알 수 없는 500 이었다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, **{field: "a\x00b"})
    assert response.status_code == 422, response.text


def test_a_nul_byte_is_also_refused_on_update(client, login_as):
    csrf = login_as("system_admin")
    row_id = _created_id(client, csrf)

    response = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"body": "붙여넣은\x00본문"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


def test_korean_and_emoji_are_stored_as_they_are(client, login_as):
    """반례 — 여기서 막는 것은 「저장할 수 없는 문자」 하나뿐이다. 한글도 이모지도
    PostgreSQL 이 담는 문자이고, 그대로 저장돼야 한다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, title="정기 점검 🛠 안내", body="자정부터 두 시간입니다.")
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "정기 점검 🛠 안내"
