"""🔴 **이관해 온 티켓은 포털에서 첫 저장이 늘 막혔다** (Z2 의 뒷면).

## 어떻게 살아남았나

낙관적 잠금은 두 값을 비교한다.
  · 화면이 편집을 시작할 때 받은 지문 — `service._detail_body_markdown` 이 만든다.
  · 저장할 때 서버가 비교하는 지문 — `_ensure_body_not_changed` 가 만든다.
    이쪽은 **로컬 컬럼(`tickets.body_markdown`)** 하나만 본다.

미러 시절에는 앞의 것이 **Notion 블록을 렌더한 글**에서 나왔다. 포털에서 한 번도 안 고친
티켓은 로컬 컬럼이 NULL 이라

    받은 지문 = hash(Notion 본문)   vs   비교 지문 = hash("")

가 되어 **항상 다르고, 첫 저장이 무조건 409** 였다. 그것도 하필 "다른 사람이 먼저
저장했습니다" 라는 **사실이 아닌 문구**로 — 아무도 저장하지 않았는데.

## 지금 무엇이 남았나 (S14)

지문의 출처가 둘이던 상태는 사라졌다. 본문의 정본이 한 곳뿐이라 두 지문이 갈라질 자리가
없다. 그래서 이 파일은 더 이상 그 **메커니즘**을 증명하지 못한다.

남은 것은 **데이터 모양**이다. 이관해 온 티켓 1,058건 중에는 행은 있고 `body_markdown` 만
NULL 인 것이 그대로 있고, 그 사람들이 포털에서 처음 본문을 저장하는 순간이 지금도 매일
온다. 그 첫 저장이 막히면 증상은 그때와 글자 하나 다르지 않다 — 그래서 그 경로를 끝에서
끝까지(상세가 준 지문 → 저장 → 재시도) 그대로 남긴다.

오탐 방지도 함께 남긴다: 고치느라 잠금 자체를 없애면 앞사람 글이 조용히 지워진다.

qa-contract-change: 두 지문의 출처가 하나로 합쳐져 「Notion 본문 대 빈 문자열」이라는 원래 메커니즘은 재현할 수단이 사라졌다. 표본을 그 메커니즘이 아니라 이관해 온 티켓의 데이터 모양(행은 있고 본문 컬럼만 NULL)에 맞추고, 첫 저장과 두 번째 저장의 잠금을 실제 HTTP 경로에서 그대로 확인한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.regression

PAGE = "page-with-body"


@pytest.fixture()
def notion(fake_http):
    """가짜 Notion 서버를 붙이되 **티켓은 한 건도 놓지 않는다** — 반례 장치다.

    본문 경로가 다시 바깥을 읽으면 이 빈 작업 DB 가 티켓을 못 찾아 시험이 소리 내어
    깨진다. 페이크를 안 붙이면 그 회귀는 조용히 지나간다.
    """
    from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB

    return FakeNotionTasksDB(
        rows=[], projects=[], projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def csrf(client, settings, notion, make_user, portal_project):
    make_user(email="firstsave@goodmit.co.kr", role="user", display_name="편집자")
    r = client.post(
        "/login", json={"email": "firstsave@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


@pytest.fixture()
def migrated(db, csrf, portal_project):
    """🔴 **행은 있고 `body_markdown` 만 NULL** — 이관해 온 티켓의 정상 모양이다.

    `_ensure_body_not_changed` 는 행이 없으면 **검사 없이 통과**한다. 행 없이 쓰면 잠금
    경로를 아예 안 지나고, 결함이 있어도 시험이 초록이다.

    소속을 반드시 매단다. 없으면 이 티켓은 상세로 열리지 않고(0060) 본문 잠금 경로에
    닿지도 못한 채 404 로 빨개져, 이 파일이 무엇을 재는지 흐려진다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.tickets.models import PROJECT_LINK_OK, TicketCache

    db.add(TicketCache(
        notion_page_id=PAGE, title="본문 있는 티켓", status="진행", org_id=DEFAULT_ORG_ID,
        project_uid=portal_project.id, project_link=PROJECT_LINK_OK,
    ))
    db.commit()
    return True


def test_the_sample_matches_production_shape(client, db, csrf, migrated):
    """오탐 방지 — 두 조건이 다 맞아야 이 파일이 무엇을 증명한다.

    ① 포털에서 고친 적이 없다(`body_markdown` 이 NULL) ② **행은 있다**
    """
    from app.tickets.models import TicketCache

    detail = client.get(f"/api/tickets/{PAGE}").json()
    # 예전에는 여기서 `detail["body_is_local"] is False` 를 봤다. 그 필드가 응답에서
    # 없어졌다(이관 문서 110건이 전부 그 값이라 편집기가 전 건에 사실이 아닌 서식 손실
    # 경고를 띄웠다). 표본의 조건은 아래 행 검사가 그대로 지킨다.
    assert "body_is_local" not in detail, detail
    assert detail["body_markdown"] == "", "본문 컬럼이 NULL 인 표본이어야 이 결함이 보인다"

    db.expire_all()
    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == PAGE)
    ).scalar_one_or_none()
    assert row is not None, "행이 없으면 잠금 검사를 아예 안 지난다 (헛 검증)"
    assert row.body_markdown is None, (
        f"로컬 본문이 이미 채워져 있으면 이 결함이 안 보인다: {row.body_markdown!r}"
    )


def test_the_first_portal_save_of_a_migrated_ticket_is_not_a_conflict(client, csrf, migrated):
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


def test_a_genuinely_stale_version_is_still_refused(client, csrf, migrated):
    """오탐 방지 — 고치느라 잠금 자체를 없애면 앞사람 글이 조용히 지워진다."""
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


def test_the_version_the_detail_handed_out_is_the_one_the_server_compares(
    client, csrf, migrated
):
    """두 지문의 **출처가 하나**라는 사실을 값으로 확인한다.

    이 파일이 원래 잡은 결함이 「두 출처가 갈라진다」였다. 지금은 갈라질 자리가 없지만,
    그것은 코드를 읽어야만 아는 사실이다 — 저장 뒤 상세가 주는 지문과 저장 응답이 주는
    지문이 같은 값인지 보면 화면 밖에서도 확인된다.
    """
    version = client.get(f"/api/tickets/{PAGE}").json()["body_version"]
    saved = client.put(
        f"/api/tickets/{PAGE}/body",
        json={"body_markdown": "한 줄", "base_version": version},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["body_version"] == client.get(f"/api/tickets/{PAGE}").json()["body_version"]
