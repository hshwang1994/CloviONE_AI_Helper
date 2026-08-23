"""본문 저장에 **낙관적 잠금** (Z2).

예전에는 조건 없이 덮어썼다. 미할당 티켓은 **아무나 편집 가능**하므로 두 사람이 동시에
본문을 쓰면 나중 사람이 앞사람 글을 통째로 지운다 — 그리고 **양쪽 다 성공 토스트를 본다.**
사람이 이미 한 일을 파괴하는 부류라 그 어떤 성능 문제보다 아프다.

타임스탬프가 아니라 **내용의 해시**를 쓴다: 타임스탬프는 내용이 안 바뀐 저장(공백 정리)에도
달라져 헛 충돌을 만들고, 같은 초에 두 번 저장되면 못 잡는다.
"""

from __future__ import annotations

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row


# 이 파일은 **Notion 저장소 구현체 위에서** 티켓을 만들고 고친다(가짜 Notion 서버가
# 픽스처다). 제품 기본 소스는 S14 부터 `native` 이므로 여기서 되돌려 놓는다.
#
# 이 표는 동시에 **Notion 을 걷어낼 때 다시 쓸 파일의 목록**이다 — 여기서 지키는 성질은
# 소스와 무관하게 지켜야 하는 것이고, 자체 DB 위에서 다시 서야 한다.
pytestmark = [pytest.mark.integration, pytest.mark.notion_source]

PAGE = "page-lock"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[task_row(page_id=PAGE, tid=1, title="잠금 확인", status="진행", people=[])],
        projects=[project_row(page_id="p1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def csrf(client, settings, notion, make_user, portal_project):
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    make_user(email="lock@goodmit.co.kr", role="user", display_name="편집자")
    r = client.post("/login", json={"email": "lock@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _detail(client):
    return client.get(f"/api/tickets/{PAGE}").json()


def test_saving_with_the_version_you_started_from_works(client, csrf):
    version = _detail(client)["body_version"]
    r = client.put(f"/api/tickets/{PAGE}/body",
                   json={"body_markdown": "첫 번째 글", "base_version": version},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_a_stale_version_is_refused(client, csrf):
    """앞사람이 이미 저장한 뒤 옛 지문으로 저장하면 **막힌다.**"""
    version = _detail(client)["body_version"]
    client.put(f"/api/tickets/{PAGE}/body",
               json={"body_markdown": "앞사람 글", "base_version": version},
               headers={"X-CSRF-Token": csrf})

    r = client.put(f"/api/tickets/{PAGE}/body",
                   json={"body_markdown": "뒷사람 글", "base_version": version},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409, f"앞사람 글이 조용히 지워진다: {r.status_code}"
    assert "먼저 저장" in r.text

    # 그리고 **앞사람 글이 그대로 남아 있어야** 한다 — 막았는데 지워졌으면 소용없다.
    assert _detail(client)["body_markdown"] == "앞사람 글"


def test_omitting_the_version_keeps_the_old_behaviour(client, csrf):
    """구버전 클라이언트·CLI 호환. 새 계약을 강제해 기존 경로를 깨뜨리지 않는다."""
    r = client.put(f"/api/tickets/{PAGE}/body", json={"body_markdown": "버전 없이"},
                   headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_the_response_carries_the_new_version(client, csrf):
    """저장 뒤 지문을 돌려주지 않으면 화면이 다음 저장에서 반드시 충돌한다."""
    version = _detail(client)["body_version"]
    body = client.put(f"/api/tickets/{PAGE}/body",
                      json={"body_markdown": "새 글", "base_version": version},
                      headers={"X-CSRF-Token": csrf}).json()
    assert body.get("body_version") and body["body_version"] != version
