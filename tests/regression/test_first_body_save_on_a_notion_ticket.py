"""🔴 **본문이 있는 티켓은 포털에서 첫 저장이 늘 막혔다** (Z2 의 뒷면).

## 어떻게 살아남았나

낙관적 잠금은 두 값을 비교한다.
  · 화면이 편집을 시작할 때 받은 지문 - `service._detail_body_markdown` 이 만든다.
    로컬 본문이 없으면 **Notion 블록을 렌더한 글**로 지문을 만든다.
  · 저장할 때 서버가 비교하는 지문 - `_ensure_body_not_changed` 가 만든다.
    이쪽은 **로컬 컬럼(`ticket_cache.body_markdown`)** 하나만 본다.

포털에서 한 번도 안 고친 티켓은 로컬 컬럼이 NULL 이다. 그래서
  받은 지문 = hash(Notion 본문)  vs  비교 지문 = hash("")
가 되어 **항상 다르고, 첫 저장이 무조건 409** 가 된다. 그것도 하필
"다른 사람이 먼저 저장했습니다" 라는 **사실이 아닌 문구**로 - 아무도 저장하지 않았는데.

기존 잠금 테스트(`test_body_optimistic_lock.py`)가 이걸 못 잡은 이유는 그 픽스처 티켓에
**본문 블록이 하나도 없어서** 양쪽 지문이 우연히 둘 다 hash("") 로 같았기 때문이다.
값이 달라지지 않는 표본으로는 아무것도 증명되지 않는다 - 이 저장소에서 반복된 그 모양이다.
문서 편집 작업자가 문서 쪽에서 같은 구조를 발견하고 알려 줘서 티켓 쪽을 확인했다.
"""

from __future__ import annotations

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.regression

PAGE = "page-with-body"


def _paragraph(text: str) -> dict:
    return {
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "plain_text": text,
                                     "text": {"content": text}}]},
    }


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    """🔴 핵심은 **본문이 비어 있지 않은** 티켓이다. 비어 있으면 이 결함이 사라진다."""
    return FakeNotionTasksDB(
        rows=[task_row(page_id=PAGE, tid=1, title="본문 있는 티켓", status="진행", people=[])],
        projects=[project_row(page_id="p1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
        blocks={PAGE: [_paragraph("Notion 에 이미 적혀 있던 내용")]},
    ).install(fake_http)


@pytest.fixture()
def csrf(client, settings, notion, make_user, portal_project):
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    make_user(email="firstsave@goodmit.co.kr", role="user", display_name="편집자")
    r = client.post(
        "/login", json={"email": "firstsave@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


@pytest.fixture()
def synced(db, csrf, portal_project):
    """🔴 **캐시 행이 있어야 한다.** 이게 없으면 이 파일 전체가 헛것이 된다.

    `_ensure_body_not_changed` 는 캐시 행이 없으면 **검사 없이 통과**한다. 행 없이 쓰면
    잠금 경로를 아예 안 지나고, 결함이 있어도 테스트가 초록이다.
    처음에 정확히 그렇게 써서 3개가 전부 통과했다.

    운영에는 티켓이 1,058건 동기화돼 있다 - **행은 있고 `body_markdown` 만 NULL** 인 상태가
    정상 상태다. 표본을 거기에 맞춘다. (동기화를 통째로 돌리지 않고 행만 만드는 이유:
    이 회귀가 검사하는 것은 **지문 비교 한 곳**이지 동기화가 아니다. 동기화까지 끌어들이면
    관계없는 이유로 빨개져 신호가 흐려진다.)
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.tickets.models import PROJECT_LINK_OK, TicketCache

    db.add(TicketCache(
        notion_page_id=PAGE, title="본문 있는 티켓", status="진행", org_id=DEFAULT_ORG_ID,
        # 소속이 없으면 이 티켓은 상세로 열리지 않는다(0060) — 그러면 본문 잠금 경로에
        # 닿지도 못한 채 404 로 빨개져, 이 파일이 무엇을 재는지 흐려진다.
        project_uid=portal_project.id, project_link=PROJECT_LINK_OK,
    ))
    db.commit()
    return True


def test_the_sample_matches_production_shape(client, db, csrf, synced):
    """오탐 방지 - 세 조건이 다 맞아야 이 파일이 무엇을 증명한다.

    ① 본문이 비어 있지 않다 ② 포털에서 고친 적이 없다 ③ **캐시 행은 있다**
    """
    from sqlalchemy import select

    from app.tickets.models import TicketCache

    detail = client.get(f"/api/tickets/{PAGE}").json()
    assert detail["body_markdown"], f"표본에 본문이 없다: {detail.get('body_markdown')!r}"
    assert detail["body_is_local"] is False, "이미 포털에서 고친 티켓이면 이 결함이 안 보인다"

    db.expire_all()
    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == PAGE)
    ).scalar_one_or_none()
    assert row is not None, "캐시 행이 없으면 잠금 검사를 아예 안 지난다 (헛 검증)"
    assert row.body_markdown is None, (
        f"로컬 본문이 이미 채워져 있으면 이 결함이 안 보인다: {row.body_markdown!r}"
    )


def test_the_first_portal_save_of_an_existing_body_is_not_a_conflict(client, csrf, synced):
    """화면이 준 지문을 그대로 돌려보냈는데 충돌이라고 하면, 사용자는 영영 저장할 수 없다."""
    version = client.get(f"/api/tickets/{PAGE}").json()["body_version"]
    r = client.put(
        f"/api/tickets/{PAGE}/body",
        json={"body_markdown": "포털에서 처음 고친 내용", "base_version": version},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, (
        f"아무도 먼저 저장하지 않았는데 충돌이라고 답했다: {r.status_code} {r.text}"
    )
    assert r.json()["body_markdown"] == "포털에서 처음 고친 내용"


def test_a_genuinely_stale_version_is_still_refused(client, csrf, synced):
    """오탐 방지 - 고치느라 잠금 자체를 없애면 앞사람 글이 조용히 지워진다."""
    version = client.get(f"/api/tickets/{PAGE}").json()["body_version"]
    first = client.put(
        f"/api/tickets/{PAGE}/body",
        json={"body_markdown": "앞사람 글", "base_version": version},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200, first.text

    second = client.put(
        f"/api/tickets/{PAGE}/body",
        json={"body_markdown": "뒷사람 글", "base_version": version},
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 409, (
        f"옛 지문으로 덮어쓸 수 있다 - 앞사람 글이 사라진다: {second.status_code}"
    )
    assert client.get(f"/api/tickets/{PAGE}").json()["body_markdown"] == "앞사람 글"
