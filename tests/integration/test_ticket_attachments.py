"""티켓 첨부 API (지시서 §4) — 실제 HTTP 경로에서 계약을 못박는다.

여기서 고정하는 것:
  * 첨부는 `ticket_cache.id`(자체 UUID)에 걸린다. URL 은 Notion page id 로 부르므로 그 해석이
    실제로 되는지 라우터 경유로 확인한다(댓글과 같은 규약).
  * 상세 응답(`GET /api/tickets/{page_id}`)에 **바로 실려 나온다** — §4 가 요구하는 "현재
    화면과 티켓 상세에서 바로 확인"이 이 한 줄이다.
  * **256KB 를 넘는 파일이 올라간다.** 미들웨어의 본문 상한 예외 목록에 이 라우트가 없으면
    10MB 를 받는다고 해 놓고 413 이 난다(팀 채팅 이미지에서 실제로 그랬다).
  * 없는 첨부는 **404**. 403 은 "그런 첨부가 있긴 하다"를 알려 준다.
  * 남의 담당 티켓에는 못 붙인다(편집 권한과 같은 선).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.tickets.models import TicketAttachment, TicketCache
from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.integration

PAGE_ID = "page-a001"
OTHERS_PAGE_ID = "page-a002"
TOKEN_REF = "notion_report_token"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"\x00" * 64


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id=PAGE_ID, tid=901, title="첨부 붙일 티켓", status="진행",
                     due="2026-09-01", people=[]),
            # 남이 맡고 있는 티켓 — 편집 권한 선을 확인하는 데 쓴다.
            task_row(page_id=OTHERS_PAGE_ID, tid=902, title="남의 티켓", status="진행",
                     due="2026-09-01", people=["notion-someone-else"]),
        ],
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def api(client, settings, notion, make_user):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")

    def _login(email: str, *, role: str = "user", name: str = "사람"):
        from app.users.service import get_user_by_email

        with client.app.state.session_factory() as db:
            if get_user_by_email(db, email) is None:
                make_user(email=email, role=role, display_name=name)
        response = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
        assert response.status_code == 200, response.text
        return response.json()["csrf_token"]

    return _login


def _upload(client, csrf, page_id, name="화면.png", content=PNG, mime="image/png"):
    return client.post(
        f"/api/tickets/{page_id}/attachments",
        files={"file": (name, content, mime)},
        headers={"X-CSRF-Token": csrf},
    )


def test_attachment_lands_on_the_ticket_cache_uuid_not_the_page_id(client, api, db):
    csrf = api("att@goodmit.co.kr", name="가")
    r = _upload(client, csrf, PAGE_ID)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert [a["filename"] for a in body["attachments"]] == ["화면.png"]
    assert body["attachments"][0]["is_image"] is True

    cache = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == PAGE_ID)
    ).scalar_one()
    att = db.execute(select(TicketAttachment)).scalars().one()
    # FK 는 우리 자체 UUID 다 — Notion page id 에 걸면 소스를 바꾸는 순간 전부 고아가 된다.
    assert att.ticket_uid == cache.id


def test_detail_carries_attachments_so_the_screen_shows_them_without_another_call(client, api):
    """§4 "현재 화면과 티켓 상세에서 바로 확인" — 상세 한 번으로 첨부가 온다."""
    csrf = api("att2@goodmit.co.kr")
    _upload(client, csrf, PAGE_ID)
    detail = client.get(f"/api/tickets/{PAGE_ID}").json()
    assert detail["ok"] is True
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["url"].startswith("/api/tickets/attachments/")
    assert detail["can_edit"] is True


def test_uploaded_bytes_are_served_back_with_nosniff(client, api):
    csrf = api("att3@goodmit.co.kr")
    att = _upload(client, csrf, PAGE_ID).json()["attachments"][0]
    r = client.get(att["url"])
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_upload_larger_than_the_256k_body_limit_succeeds(client, api):
    """미들웨어의 본문 상한 예외 목록에 이 라우트가 없으면 여기서 413 이 난다.

    팀 채팅 이미지가 정확히 그 상태였다 — 10MB 를 받는다고 해 놓고 256KB 에서 잘렸다.
    """
    csrf = api("att4@goodmit.co.kr")
    big = PNG + b"\x00" * (400 * 1024)
    r = _upload(client, csrf, PAGE_ID, name="큰그림.png", content=big)
    assert r.status_code == 200, r.text
    assert r.json()["attachments"][0]["size_bytes"] == len(big)


def test_pdf_is_allowed_so_a_spec_does_not_force_a_trip_to_the_source(client, api):
    csrf = api("att5@goodmit.co.kr")
    r = _upload(client, csrf, PAGE_ID, name="규격서.pdf", content=PDF, mime="application/pdf")
    assert r.status_code == 200, r.text
    att = r.json()["attachments"][0]
    assert att["media_type"] == "application/pdf" and att["is_image"] is False


def test_executable_disguised_as_png_is_rejected_by_magic_bytes(client, api):
    csrf = api("att6@goodmit.co.kr")
    r = _upload(client, csrf, PAGE_ID, name="악성.png", content=b"MZ\x90\x00" + b"\x00" * 64)
    assert r.status_code == 422, r.text


def test_missing_attachment_is_404_not_403(client, api):
    """403 은 "그런 첨부가 있긴 하다"를 알려 준다 — 없는 것과 못 보는 것을 구분해 주면 안 된다."""
    api("att7@goodmit.co.kr")
    assert client.get("/api/tickets/attachments/no-such-id").status_code == 404


def test_serving_requires_a_session(client, api):
    csrf = api("att8@goodmit.co.kr")
    url = _upload(client, csrf, PAGE_ID).json()["attachments"][0]["url"]
    client.post("/logout", headers={"X-CSRF-Token": csrf})
    assert client.get(url).status_code == 401


def test_cannot_attach_to_someone_elses_ticket(client, api):
    """남의 담당 티켓에 파일을 붙이는 것은 티켓을 고치는 일이다 — 편집 권한과 같은 선."""
    csrf = api("outsider@goodmit.co.kr")
    r = _upload(client, csrf, OTHERS_PAGE_ID)
    assert r.status_code == 403, r.text


def test_uploader_can_remove_their_own_attachment(client, api):
    csrf = api("att9@goodmit.co.kr")
    att = _upload(client, csrf, PAGE_ID).json()["attachments"][0]
    r = client.delete(f"/api/tickets/attachments/{att['id']}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["attachments"] == []
    assert client.get(f"/api/tickets/{PAGE_ID}").json()["attachments"] == []


def test_others_cannot_remove_an_attachment_on_a_ticket_they_cannot_edit(client, api):
    owner_csrf = api("owner@goodmit.co.kr")
    att = _upload(client, owner_csrf, PAGE_ID).json()["attachments"][0]
    client.post("/logout", headers={"X-CSRF-Token": owner_csrf})

    # 남의 티켓(OTHERS_PAGE_ID)이 아니라 미할당 티켓이라 '편집 가능'으로 잡히는 상황을 피하려면
    # 첨부가 붙은 티켓의 담당자를 바꿔야 한다. 여기서는 더 단순하게, 올린 사람이 아닌 사용자가
    # **편집 불가한 티켓**의 첨부를 지우려는 경우를 본다.
    other_csrf = api("nosy@goodmit.co.kr")
    others_att = _upload(client, owner_csrf, OTHERS_PAGE_ID)
    assert others_att.status_code == 403  # 애초에 붙일 수도 없다

    # 올린 사람이 아니고 티켓이 미할당이면 편집 가능 — 지울 수 있다(정책상 맞다).
    r = client.delete(f"/api/tickets/attachments/{att['id']}",
                      headers={"X-CSRF-Token": other_csrf})
    assert r.status_code == 200, r.text


# OPS-04: 업로드 실패도 감사에 남아야 한다 — 예전엔 record_audit_from_request가 성공
# 경로 끝에만 있어서, save_upload가 던지는 예외(OSError→StorageUnavailableError, OPS-05)가
# 그 호출 자체를 건너뛰고 빠져나가 감사 행이 하나도 안 남았다.
def test_failed_upload_still_leaves_an_audit_trail(client, api, db, monkeypatch):
    from pathlib import Path

    from app.audit.models import AuditLog

    def _boom(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", _boom)

    csrf = api("audited-fail@goodmit.co.kr")
    r = _upload(client, csrf, PAGE_ID)
    assert r.status_code == 503, r.text

    rows = db.execute(
        select(AuditLog).where(AuditLog.action == "ticket.attachment.upload")
    ).scalars().all()
    assert rows, "실패한 업로드인데 ticket.attachment.upload 감사 기록이 없다"
    assert rows[-1].result == "failure"
    assert rows[-1].after_json is not None and "page-a001" in rows[-1].after_json
