"""메일 모양 미리 보기 API (계획 M3, D-549).

못박는 것:
  * 콘솔 읽기 역할이 열 가지 종류를 보고, 각 종류의 제목 · 평문 · HTML 을 받는다. 모르는 종류는 404 다.
  * 미리 보기는 표본만 쓴다 - 실제 사용자 이름 · 티켓 제목이 DB 에 있어도 응답에 나오지 않는다.
  * 일반 사용자는 볼 수 없다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_every_kind_renders_with_an_inline_logo_and_unknown_is_404(client, login_as):
    """종류는 표본 표(`samples.PREVIEW_KINDS`, D-562 로 늘었다)가 정한다. 미리 보기의 로고는 sandbox 가 그릴 수 있는 data 주소다(D-561)."""
    from app.mail.samples import PREVIEW_KINDS

    h = {"X-CSRF-Token": login_as("auditor")}
    kinds = client.get("/api/admin/mail/templates", headers=h).json()["items"]
    assert len(kinds) == len(PREVIEW_KINDS) >= 26 and kinds[0] == {"key": "ticket_assigned", "label": "티켓 배정"}
    for kind in kinds:
        r = client.get(f"/api/admin/mail/templates/{kind['key']}/preview", headers=h)
        assert r.status_code == 200, (kind, r.text)
        body = r.json()
        assert body["subject"] and body["text"] and body["html"].lstrip().startswith("<!DOCTYPE html>")
        assert 'src="data:image/png;base64,' in body["html"] and "cid:" not in body["html"], kind
    assert client.get("/api/admin/mail/templates/nope/preview", headers=h).status_code == 404


def test_the_preview_never_carries_database_content(client, db, login_as, make_user):
    make_user(email="real-person@goodmit.co.kr", display_name="실제사람이름XYZ")
    h = {"X-CSRF-Token": login_as("system_admin")}
    for kind in ("ticket_assigned", "invite", "password_reset", "test"):
        text = client.get(f"/api/admin/mail/templates/{kind}/preview", headers=h).text
        assert "실제사람이름XYZ" not in text and "real-person@goodmit.co.kr" not in text, kind


def test_a_plain_user_cannot_preview(client, login_as):
    h = {"X-CSRF-Token": login_as("user")}
    assert client.get("/api/admin/mail/templates", headers=h).status_code in (401, 403)


def test_the_dark_scheme_forces_the_dark_rules_and_nothing_else(client, login_as):
    """`?scheme=dark` 는 body 에 `data-ogsc` 를 단 같은 HTML 이다(D-571) - 보는 사람의 운영체제 설정과 상관없이 다크 모양을 본다."""
    h = {"X-CSRF-Token": login_as("auditor")}
    light = client.get("/api/admin/mail/templates/ticket_assigned/preview", headers=h).json()
    dark = client.get("/api/admin/mail/templates/ticket_assigned/preview?scheme=dark", headers=h).json()
    assert light["scheme"] == "light" and dark["scheme"] == "dark"
    body_tag = lambda html: html[html.index("<body"):html.index(">", html.index("<body"))]  # noqa: E731
    assert 'data-ogsc=""' in body_tag(dark["html"]) and "data-ogsc" not in body_tag(light["html"])
    # 「라이트」는 보는 사람의 운영체제가 다크여도 밝다 - 다크 미디어 규칙만 꺼져 있고 나머지는 같은 HTML 이다.
    assert "@media (prefers-color-scheme: dark)" in dark["html"] and "@media (prefers-color-scheme: dark)" not in light["html"]
    unpinned = light["html"].replace("@media not all", "@media (prefers-color-scheme: dark)", 1)
    assert dark["html"].replace(' data-ogsc=""', "", 1) == unpinned and dark["text"] == light["text"]
    assert (light["background"], dark["background"]) == ("#F5F6FB", "#0A0C16")
    assert client.get("/api/admin/mail/templates/ticket_assigned/preview?scheme=light", headers=h).json()["html"] == light["html"]
    assert client.get("/api/admin/mail/templates/ticket_assigned/preview?scheme=sepia", headers=h).status_code == 422
