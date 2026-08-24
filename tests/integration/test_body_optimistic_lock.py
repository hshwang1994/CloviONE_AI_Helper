"""본문 저장에 **낙관적 잠금** (Z2).

qa-contract-change: 픽스처가 가짜 Notion 서버에 티켓을 올려 두고 Notion 저장소 구현체 위에서 돌았는데, S14 가 그 구현체를 지웠다(D-284) — 지키는 성질(두 사람이 동시에 쓰면 나중 사람이 앞사람 글을 조용히 지우지 않는다)은 소스와 무관하므로 정본 표에 티켓을 직접 심어 같은 네 가지를 그대로 확인한다.

예전에는 조건 없이 덮어썼다. 미할당 티켓은 **아무나 편집 가능**하므로 두 사람이 동시에
본문을 쓰면 나중 사람이 앞사람 글을 통째로 지운다 — 그리고 **양쪽 다 성공 토스트를 본다.**
사람이 이미 한 일을 파괴하는 부류라 그 어떤 성능 문제보다 아프다.

타임스탬프가 아니라 **내용의 해시**를 쓴다: 타임스탬프는 내용이 안 바뀐 저장(공백 정리)에도
달라져 헛 충돌을 만들고, 같은 초에 두 번 저장되면 못 잡는다.

## 자체 DB 가 되면서 오히려 더 중요해졌다

미러 시절에는 본문의 정본이 저쪽에 있어서 잃어버린 글을 원본에서 되찾을 여지가 있었다.
이제는 이 표가 정본이다 — 덮어쓴 글은 **어디에도 없다.**
"""

from __future__ import annotations

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def page(db, make_ticket, portal_project) -> str:
    """미할당·진행 중인 티켓 하나. **API 가 부르는 이름**을 돌려준다.

    미할당인 것이 핵심이다 — 아무나 편집할 수 있어야 「두 사람이 동시에」가 성립한다.
    """
    ticket = make_ticket(project=portal_project, title="잠금 확인", status="진행")
    db.commit()
    return ticket.id


@pytest.fixture()
def csrf(client, make_user, page):
    make_user(email="lock@goodmit.co.kr", role="user", display_name="편집자")
    r = client.post(
        "/login", json={"email": "lock@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _detail(client, page):
    return client.get(f"/api/tickets/{page}").json()


def test_saving_with_the_version_you_started_from_works(client, csrf, page):
    version = _detail(client, page)["body_version"]
    r = client.put(f"/api/tickets/{page}/body",
                   json={"body_markdown": "첫 번째 글", "base_version": version},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_a_stale_version_is_refused(client, csrf, page):
    """앞사람이 이미 저장한 뒤 옛 지문으로 저장하면 **막힌다.**"""
    version = _detail(client, page)["body_version"]
    client.put(f"/api/tickets/{page}/body",
               json={"body_markdown": "앞사람 글", "base_version": version},
               headers={"X-CSRF-Token": csrf})

    r = client.put(f"/api/tickets/{page}/body",
                   json={"body_markdown": "뒷사람 글", "base_version": version},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, f"앞사람 글이 조용히 지워진다: {r.status_code}"
    assert "먼저 저장" in r.text

    # 그리고 **앞사람 글이 그대로 남아 있어야** 한다 — 막았는데 지워졌으면 소용없다.
    assert _detail(client, page)["body_markdown"] == "앞사람 글"


def test_omitting_the_version_keeps_the_old_behaviour(client, csrf, page):
    """구버전 클라이언트·CLI 호환. 새 계약을 강제해 기존 경로를 깨뜨리지 않는다."""
    r = client.put(f"/api/tickets/{page}/body", json={"body_markdown": "버전 없이"},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_the_response_carries_the_new_version(client, csrf, page):
    """저장 뒤 지문을 돌려주지 않으면 화면이 다음 저장에서 반드시 충돌한다."""
    version = _detail(client, page)["body_version"]
    body = client.put(f"/api/tickets/{page}/body",
                      json={"body_markdown": "새 글", "base_version": version},
                      headers={"X-CSRF-Token": csrf}).json()
    assert body.get("body_version") and body["body_version"] != version
