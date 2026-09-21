"""새 티켓 본문에 쓸 수 없는 그림 주소가 들어오면 422 다 — 500 이 아니고, 티켓도 안 생긴다.

운영 로그(2026-09-16)의 500 다섯 건이 이 경로였다. 사용자가 다른 앱에서 그림을 복사해
붙이면 편집기가 `cid:` · `blob:` · `file:` 주소를 그대로 들고 오고, 서버의 본문 정규화
(`app/knowledge/blocks.py`)가 그 그림을 거절한다. 본문 **저장** 경로는 그 거절을 422 로
옮기고 있었는데 **만들기** 경로는 안 옮겨서 사용자는 「알 수 없는 오류」를 다섯 번 봤다.
"""

from __future__ import annotations

import pytest

from app.tickets.models import TicketCache
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def author(db, make_user, make_project) -> dict[str, str]:
    user = make_user(email="writer@goodmit.co.kr", role="system_admin", display_name="작성자")
    project = make_project(name="알파", external_id="proj-bad-image")
    db.commit()
    return {"user_id": user.id, "project_id": project.id}


def _login(client, email: str) -> str:
    response = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _doc_with_image(src: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "붙여 넣은 그림"}]},
            {"type": "image", "attrs": {"src": src, "alt": ""}},
        ],
    }


@pytest.mark.parametrize("src", ["cid:image001.png@01DA", "blob:https://mail.example/1234", "file:///C:/x.png"])
def test_unusable_image_address_is_422_and_creates_nothing(client, db, author, src):
    csrf = _login(client, "writer@goodmit.co.kr")
    before = db.query(TicketCache).count()
    response = client.post(
        "/api/tickets",
        json={
            "title": "그림을 붙인 티켓", "project_id": author["project_id"],
            "est_wd": 1, "due_date": "2026-12-31",
            "description_doc": _doc_with_image(src),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert "이미지" in body["message"], body["message"]
    db.expire_all()
    assert db.query(TicketCache).count() == before, "거절한 본문인데 티켓이 만들어졌다"


def test_http_image_address_still_creates_the_ticket(client, db, author):
    """거절은 **쓸 수 없는 주소만**이다 — 평범한 https 그림까지 막으면 고친 것이 아니다."""
    csrf = _login(client, "writer@goodmit.co.kr")
    response = client.post(
        "/api/tickets",
        json={
            "title": "그림이 있는 티켓", "project_id": author["project_id"],
            "est_wd": 1, "due_date": "2026-12-31",
            "description_doc": _doc_with_image("https://example.com/a.png"),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code in (200, 201), response.text
