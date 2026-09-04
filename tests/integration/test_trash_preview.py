"""휴지통에서 **지우기 전에 본문을 본다** — 티켓과 옛 미러 문서.

## 무엇이 없었나

영구 삭제는 되돌릴 수 없고 댓글·첨부까지 함께 지운다. 그런데 이 표에서 티켓과 옛 미러
문서는 **제목 문자열 말고는 볼 방법이 전혀 없었다.** 평소 경로가 전부 막혀 있기 때문이다 —
`ticket_detail` 은 첫 줄에서 `ensure_not_trashed` 를, `GET /api/team-docs/{id}` 는
`ensure_doc_not_trashed` 를 지난다(H2).

그 두 가드는 **편집을 막으려고** 있다. 「지웠는데 아직 고쳐지고, 고친 것이 나중에
사라진다」가 그 머리말이 적은 증상이다. 보기를 막는 것은 그 목적이 아니었고, 오히려 보기를
막은 결과가 「무엇인지 모른 채 영구 삭제」였다.

## 여기서 보는 것

  1. 휴지통 항목의 본문이 온다 — **가드를 지나온 뒤에도.**
  2. 그런데 **가드를 건너뛴 것은 그 하나뿐이다**: 범위 밖 사람에게는 404 다. 두 문을 다
     지난다 — 휴지통 행의 범위와 **자원 자신의 범위**. 후자가 없으면 「원래 못 보던 티켓을
     팀원이 버렸다는 이유로」 읽게 된다.
  3. 이 경로가 열렸다고 **상세와 편집이 열리는 것은 아니다** — 그 둘은 그대로 404 다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

ME = "tpv-me@goodmit.co.kr"
OUTSIDER = "tpv-out@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user, make_ticket, make_project):
    """티켓 한 건을 본문과 함께 심고 휴지통에 넣은 상태 + 범위 밖 관리자 한 명."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.trash.models import TrashItem

    mine = Department(name="미리보기팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의 미리보기팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    me = make_user(ME, role="admin", display_name="나")
    me.department_id = mine.id
    outsider = make_user(OUTSIDER, role="admin", display_name="남")
    outsider.admin_scope = "dept"
    outsider.scope_dept_id = theirs.id
    outsider.department_id = theirs.id

    project = make_project(name="미리보기 프로젝트", external_id="tpv-proj")
    make_ticket(
        page_id="tpv-page-1", project=project, title="지울 티켓",
        body="# 지우기 전에 보는 본문\n\n두 번째 줄입니다.",
    )
    item = TrashItem(
        item_type="ticket", notion_page_id="tpv-page-1", title="지울 티켓",
        deleted_by_user_id=me.id, deleted_by_name="나",
        deleted_at=__import__("datetime").datetime(2026, 8, 1, 0, 0, 0),
        org_id=DEFAULT_ORG_ID,
    )
    db.add(item)
    db.commit()
    return {"trash_id": item.id, "page_id": "tpv-page-1"}


def _hdr(login_as, email=ME):
    return {"X-CSRF-Token": login_as("admin", email=email)}


def test_the_body_of_a_trashed_ticket_can_be_read_before_purging_it(client, login_as, world):
    """🔴 예전에는 제목 말고 볼 것이 없었다."""
    r = client.get(f"/api/trash/{world['trash_id']}/preview", headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "지울 티켓"
    assert body["item_type"] == "ticket"
    text = " ".join(b.get("text") or "" for b in (body["blocks"] or []))
    assert "지우기 전에 보는 본문" in text, "본문이 안 왔다 — 미리보기가 제목만 되풀이한다"
    assert "두 번째 줄입니다" in text


def test_opening_the_ticket_the_normal_way_is_still_refused(client, login_as, world):
    """반례 — 미리보기를 열었다고 상세가 열리면 그것은 H2 가드를 없앤 것이다.

    이 시험이 없으면 「`ensure_not_trashed` 를 통째로 지운다」로 고쳐도 위 시험이 초록이다.
    """
    r = client.get(f"/api/tickets/{world['page_id']}", headers=_hdr(login_as))
    assert r.status_code == 404, (
        f"휴지통 티켓의 상세가 {r.status_code} 로 열렸다 — 편집을 막던 가드가 사라졌다"
    )


def test_someone_outside_the_scope_gets_nothing(client, login_as, world):
    """범위 밖에는 404 다. 미리보기는 **읽기 구멍이 아니다.**

    이 갈래는 **첫 번째 문**(휴지통 행의 범위)이 막는다 — 그 행을 버린 사람이 남의 부서다.
    """
    r = client.get(f"/api/trash/{world['trash_id']}/preview",
                   headers=_hdr(login_as, email=OUTSIDER))
    assert r.status_code == 404, (
        f"남의 부서 사람이 휴지통 티켓 본문을 {r.status_code} 로 읽었다"
    )


def test_the_second_gate_matters_too_the_resource_has_its_own_scope(
    client, login_as, world, db, make_user, make_ticket, make_project
):
    """🔴 **문이 둘인 이유가 이것이다.**

    첫 번째 문은 「누가 버렸나」로 판정한다(`repository.visible_to`). 그것만 보면, 원래 볼
    수 없던 티켓을 **같은 팀 사람이 버렸다는 이유로** 읽게 된다 — 휴지통이 자원의 권한을
    넓히는 구멍이 된다. 그래서 자원 자신의 범위(`tickets.ensure_in_scope`)를 한 번 더 지난다.

    여기서 만드는 세계가 정확히 그 조합이다: 휴지통 행은 **내 팀 사람이** 버렸고(첫 문
    통과), 그 티켓은 **내가 볼 수 없는 프로젝트**의 것이다(두 번째 문이 막아야 한다).
    이 시험이 없으면 `ensure_in_scope` 한 줄을 지워도 이 파일이 전부 초록이다.
    """
    from datetime import datetime
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.trash.models import TrashItem
    from app.users.models import User
    from sqlalchemy import select

    theirs = db.execute(select(Department).where(Department.name == "남의 미리보기팀")).scalar_one()
    mine = db.execute(select(Department).where(Department.name == "미리보기팀")).scalar_one()
    # 평범한 사용자다 — 티켓 가시성이 가장 좁은 갈래를 재려는 것이다.
    narrow = make_user("tpv-narrow@goodmit.co.kr", role="user", display_name="좁은")
    narrow.department_id = mine.id
    db.commit()

    # 🔴 프로젝트를 **티켓보다 먼저** 만든다 — 티켓 소속은 프로젝트가 정하고 그 해석은
    # 티켓을 심는 시점에 일어난다(`app/tickets/project_link.py`).
    hidden_project = make_project(name="남의 프로젝트", dept=theirs, external_id="tpv-hidden")
    make_ticket(page_id="tpv-hidden-1", project=hidden_project, title="남의 티켓", body="비밀 본문")
    me = db.execute(select(User).where(User.email == ME)).scalar_one()
    item = TrashItem(
        item_type="ticket", notion_page_id="tpv-hidden-1", title="남의 티켓",
        # 🔴 **내 부서 사람이 버렸다** — 그래서 첫 번째 문은 통과한다.
        deleted_by_user_id=me.id, deleted_by_name="나",
        deleted_at=datetime(2026, 8, 1, 0, 0, 0), org_id=DEFAULT_ORG_ID,
    )
    db.add(item)
    db.commit()

    hdr = {"X-CSRF-Token": login_as("user", email="tpv-narrow@goodmit.co.kr")}
    # 첫 번째 문은 실제로 열려 있다 — 그 줄이 이 사람의 휴지통 목록에 보인다.
    listing = client.get("/api/trash", headers=hdr)
    assert listing.status_code == 200, listing.text
    assert any(r["title"] == "남의 티켓" for r in listing.json()["items"]), (
        "첫 번째 문이 이미 막고 있다 — 그러면 이 시험은 두 번째 문을 재지 못한다"
    )

    r = client.get(f"/api/trash/{item.id}/preview", headers=hdr)
    assert r.status_code == 404, (
        f"자원 범위 밖 티켓의 본문이 {r.status_code} 로 열렸다 — 두 번째 문이 없다"
    )


def test_a_native_document_row_is_sent_to_the_document_screen_instead(client, login_as, world):
    """Native 문서는 여기 오지 않는다 — 문서 화면이 직접 연다. 조용히 빈 것을 주지 않는다."""
    r = client.get("/api/trash/doc:11111111-2222-3333-4444-555555555555/preview",
                   headers=_hdr(login_as))
    assert r.status_code == 404


def test_an_unknown_trash_id_is_not_found(client, login_as, world):
    r = client.get("/api/trash/no-such-row/preview", headers=_hdr(login_as))
    assert r.status_code == 404


def test_preview_is_read_only(client, login_as, world):
    """쓰기 메서드는 이 경로에 없다 — GET 하나뿐이다."""
    assert client.post(f"/api/trash/{world['trash_id']}/preview",
                       headers=_hdr(login_as)).status_code == 405
