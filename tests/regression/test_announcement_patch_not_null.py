"""FN-40: 공지 PATCH 가 NOT NULL 컬럼에 null 을 넣어 500 을 냈다.

`title`/`body`/`level`/`audience` 컬럼은 전부 `nullable=False` 인데, 부분 갱신용
`AnnouncementPatch` 스키마는 넷 다 `str | None` 이다. Pydantic 은 Optional 필드의 `None`
값에 `min_length` 같은 문자열 제약을 적용하지 않으므로, "필드를 아예 안 보냄"(부분 갱신,
기존 값 유지)과 "필드를 `null` 로 명시함"이 둘 다 통과해 `exclude_unset=True` 를 지나
`data`에 `None`으로 남았다. 그 값이 그대로 `setattr(row, key, None)` 까지 내려가
`IntegrityError` → 500. POST 경로는 body 하나만 `payload.body or ""` 로 이미 방어하고
있었다(FN-40 원 보고). body 는 같은 규칙(빈 문자열은 유효)으로 채우고, title/level/audience
는 빈 값이 의미가 없어(제목 없는 공지가 말이 되지 않는다) 명확한 422 로 막는다 - 셋 다
같은 구조적 결함이라 body 만 고치면 나머지 셋이 그대로 남는다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


def _create(client, csrf):
    r = client.post(
        "/api/admin/announcements",
        json={"title": "공지", "body": "본문", "level": "info", "audience": "all"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_patch_body_null_clears_to_empty_string_instead_of_500(client, login_as):
    csrf = login_as("system_admin")
    row_id = _create(client, csrf)

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"body": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["body"] == ""


@pytest.mark.parametrize("field", ["title", "level", "audience"])
def test_patch_null_on_other_not_null_fields_is_a_clean_422_not_a_500(client, login_as, field):
    csrf = login_as("system_admin")
    row_id = _create(client, csrf)

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={field: None},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422, f"{field}=null 이 500 이거나 조용히 통과했다: {r.text}"


def test_patch_omitting_body_keeps_the_existing_value(client, login_as):
    """필드를 안 보내는 것(부분 갱신)과 null 로 보내는 것은 다르다 - 안 보내면 그대로 있어야 한다."""
    csrf = login_as("system_admin")
    row_id = _create(client, csrf)

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"title": "제목만 바꿈"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "본문"
