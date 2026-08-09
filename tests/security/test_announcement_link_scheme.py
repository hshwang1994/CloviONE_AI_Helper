"""공지 링크는 서버가 스킴을 검사한다 (SEC1).

## 왜 이게 권한 상승이었나

공지 배너는 `audience=all` 이면 **전 사용자에게** 뜬다. `link_url` 은 길이만 검사하고 그대로
저장·반환됐고, 배너를 그리는 `Banners.jsx` 는 `<Button href={item.link_url}>` 로 통과시켰다.

세 겹이 전부 없었다:
  1. 서버 — `max_length=500` 뿐. `service.validate()` 는 level/audience 만 봤다.
  2. React — react-dom 18.3.1 의 `sanitizeURL` 은 **개발 빌드 전용 `console.error`** 다.
  3. CSP — `script-src` 에 `'unsafe-inline'` 이 들어가면서 `javascript:` URI 가 실행 가능해졌다.

그래서 `admin`(system_admin 아님)이 `javascript:` 페이로드를 공지에 넣고, `system_admin` 이
한 번 누르면 그 세션에서 실행된다 — `app/users/router.py` 의 "admin 이상 계정 생성은
system_admin 만" 통제를 우회한다. 운영 실측(2026-08-05) 기준 사용자 15명 중 **admin 이 12명**
이라 이 경로에 설 수 있는 사람이 12명이었다.

## 왜 서버에서 막나

`frontend/src/lib/safeUrl.js` 도 같은 검사를 하지만 그건 이중 방어다. API 를 직접 부르면
화면 검사는 지나가지도 않는다 — **경계는 서버다.**
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

DANGEROUS = [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",          # 대소문자
    "  javascript:alert(1)",        # 선행 공백
    "\tjavascript:alert(1)",        # 선행 탭
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "/relative-path",               # 외부 링크 자리에 내부 경로
]


def _create(client, csrf, link_url):
    return client.post(
        "/api/admin/announcements",
        json={
            "title": "공지",
            "body": "본문",
            "level": "info",
            "audience": "all",
            "link_url": link_url,
        },
        headers={"X-CSRF-Token": csrf},
    )


@pytest.mark.parametrize("url", DANGEROUS)
def test_dangerous_link_url_is_refused_on_create(client, login_as, url):
    csrf = login_as("system_admin")
    r = _create(client, csrf, url)
    assert r.status_code == 422, f"{url!r} 이 통과했다: {r.text}"


def test_safe_link_url_is_accepted(client, login_as):
    csrf = login_as("system_admin")
    for url in ("https://notion.so/a", "http://intra.local/a", None):
        r = _create(client, csrf, url)
        assert r.status_code == 201, f"{url!r} 이 거부됐다: {r.text}"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x"])
def test_dangerous_link_url_is_refused_on_patch(client, login_as, url):
    """수정 경로도 막는다 — 만들 때만 막으면 만든 뒤 바꾸면 그만이다."""
    csrf = login_as("system_admin")
    row_id = _create(client, csrf, "https://ok/a").json()["id"]

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"link_url": url},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 422, f"PATCH 로 {url!r} 이 통과했다: {r.text}"


def test_patch_without_link_url_keeps_working(client, login_as):
    """부분 갱신이라 link_url 을 안 보내는 요청이 훨씬 흔하다 — 그게 막히면 안 된다."""
    csrf = login_as("system_admin")
    row_id = _create(client, csrf, "https://ok/a").json()["id"]

    r = client.patch(
        f"/api/admin/announcements/{row_id}",
        json={"title": "제목만 바꿈"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["link_url"] == "https://ok/a"  # 기존 값이 살아 있다


# CORE-11: 빈 문자열은 "링크 없음"이지 안전하지 않은 값이 아니다.
def test_empty_link_url_means_no_link_not_a_rejection(client, login_as):
    csrf = login_as("system_admin")
    r = _create(client, csrf, "")
    assert r.status_code == 201, f"빈 문자열이 거부됐다(링크 없음으로 처리돼야 한다): {r.text}"
    assert r.json()["link_url"] is None


def test_link_url_with_leading_control_characters_is_stored_normalized(client, login_as):
    """CORE-11: 검증이 본 형태(제어문자를 벗긴 형태)와 저장된 형태가 같아야 한다 —
    다르면 검증을 통과한 문자열과 실제로 저장·렌더되는 문자열이 갈라진다."""
    csrf = login_as("system_admin")
    r = _create(client, csrf, "\x01https://ok.example/a")
    assert r.status_code == 201, r.text
    assert r.json()["link_url"] == "https://ok.example/a", (
        "저장된 값에 제어문자가 남아 있다 — 검증한 형태와 저장한 형태가 다르다"
    )


# UB-05: 저장된 값이 이미 안전하지 않아도(safe_url 가드 이전에 들어온 legacy 값),
# link_url 자체를 건드리지 않는 PATCH(예: 배너 끄기)는 막히면 안 된다.
def test_disabling_a_banner_works_even_if_its_stored_link_is_legacy_unsafe(client, login_as, db):
    from datetime import datetime

    from app.announcements.models import Announcement

    csrf = login_as("system_admin")
    row = Announcement(
        title="레거시 배너", body="", level="info", audience="all",
        active=True, dismissible=True,
        link_url="javascript:alert(1)",  # safe_url 가드가 생기기 전에 들어온 값을 흉내
        created_by=None, created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )
    db.add(row)
    db.commit()

    r = client.patch(
        f"/api/admin/announcements/{row.id}",
        json={"active": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, f"link_url을 안 건드렸는데도 기존 값 때문에 막혔다: {r.text}"
    assert r.json()["active"] is False
