"""티켓 첨부 원본 서빙도 범위를 지킨다 (§0-A 4순위).

`GET /api/tickets/attachments/{attachment_id}` 는 **로그인만 하면** 첨부 원본 바이트를 줬다.
그 근거로 달려 있던 주석은 "티켓 자체가 팀 전체 조회 대상이라 첨부만 좁히면 옆 팀 사람이
첨부를 못 본다" 였는데, **그 전제는 RBAC 작업으로 이미 거짓이 됐다** — `ticket_detail` 과
`list_ticket_comments` 에 `ensure_in_scope` 가 들어가 남의 부서 티켓은 404 인데 첨부 원본만
열려 있었다. 상세가 404 인 티켓의 이미지·규격서를 id 하나로 받아 갈 수 있으면 상세를 막은
의미가 없다(첨부 URL 은 화면에 그대로 노출되는 값이라 id 를 추측할 필요조차 없다).

## 403 이 아니라 404 다

403 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 준다 — 저장소 규칙(`core/scope.py` 모듈
docstring, 팀 채팅 이미지 서빙, `get_scoped_user_or_404`)이 이미 404 로 못박아 놨다.

## ⚠️ 담당자를 해석할 수 없는 티켓은 **여전히 열려야 한다**

그런 티켓은 미할당 트리아지에 뜬다(포탈 전용 버킷). 첨부만 막으면 **목록에는 보이는데 눌러도
안 열리는** 화면이 된다 — 그건 보안이 아니라 고장이다. `ensure_in_scope` 가 갖고 있는 이
결합을 첨부 경로가 깨뜨리지 않는지 여기서 지킨다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.tickets.models import TicketAttachment, TicketCache, utcnow
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-att-mine", "notion-att-theirs"

MINE, THEIRS, GHOST = "att-mine", "att-theirs", "att-ghost"

# 매직바이트가 통과해야 저장된다(save_upload 는 확장자를 믿지 않는다).
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id=MINE, tid=1, title="우리팀 티켓", status="진행",
                     people=[NID_MINE], project_ids=["px-ours"]),
            task_row(page_id=THEIRS, tid=2, title="남의팀 티켓", status="진행",
                     people=[NID_THEIRS], project_ids=["px-theirs"]),
            # 담당자를 앱 계정으로 해석할 수 없는 티켓. 0060 부터 그 사실은 가시성과
            # 무관하고, 소속(우리 팀 프로젝트)이 판정한다.
            task_row(page_id=GHOST, tid=3, title="담당자 미해석", status="진행",
                     people=["notion-x"], project_ids=["px-ours"]),
        ],
        projects=[project_row(page_id="px-ours", name="우리 프로젝트"),
                  project_row(page_id="px-theirs", name="남의 프로젝트")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def world(client, settings, notion, make_user, make_project, db, app):
    """부서가 갈린 두 사용자 + 세 티켓 + 각 티켓에 붙은 첨부.

    첨부는 업로드 API 가 아니라 직접 만든다 — 업로드는 편집 권한(`ensure_can_edit`)에 먼저
    막히므로 API 로는 "남의 팀 티켓에 첨부가 이미 붙어 있는" 상태를 만들 수 없다. 이 테스트가
    보는 것은 붙이는 권한이 아니라 **이미 붙어 있는 첨부를 누가 열 수 있나**다.
    """
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.tickets import attachments as ticket_attachments
    from app.tickets.sync import sync_tickets

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    mine_dept = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs_dept = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine_dept, theirs_dept])
    db.flush()
    me = make_user("ta-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("ta-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine_dept.id
    other.department_id = theirs_dept.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    db.commit()

    # Portal 프로젝트를 **동기화 전에** 만든다 — 티켓 소속은 프로젝트가 정하고,
    # 그 해석은 동기화 시점에 일어난다(app/tickets/project_link.py).
    make_project(name="우리 프로젝트", dept=mine_dept, external_id="px-ours")
    make_project(name="남의 프로젝트", dept=theirs_dept, external_id="px-theirs")

    with app.state.session_factory() as s:
        sync_tickets(s, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        s.commit()

    def _uid(page_id: str) -> str:
        return db.execute(
            select(TicketCache).where(TicketCache.notion_page_id == page_id)
        ).scalar_one().id

    def _attach(page_id: str, uploader) -> str:
        att = ticket_attachments.add_attachment(
            db, settings.data_dir, ticket_uid=_uid(page_id), uploader=uploader,
            filename=f"{page_id}.png", content=PNG, now=utcnow(),
        )
        return att.id

    ids = {
        MINE: _attach(MINE, other),
        THEIRS: _attach(THEIRS, other),
        GHOST: _attach(GHOST, other),
        # 내가 올렸지만 그 뒤 남의 부서로 배정된 티켓 — 삭제 경로의 '올린 사람' 분기용.
        "theirs_uploaded_by_me": _attach(THEIRS, me),
    }
    db.commit()
    return ids


def _url(attachment_id: str) -> str:
    return f"/api/tickets/attachments/{attachment_id}"


def _still_there(app, attachment_id: str) -> bool:
    """앱이 쓰는 세션과 **다른** 세션으로 다시 읽는다 — 지워졌는지는 DB 에 물어야 안다."""
    with app.state.session_factory() as s:
        return s.get(TicketAttachment, attachment_id) is not None


# ── 범위 밖: 바이트가 나가면 안 된다 ─────────────────────────────────────────────

def test_another_teams_attachment_is_404_and_no_bytes_leak(client, login_as, world):
    login_as("user", email="ta-me@goodmit.co.kr")
    r = client.get(_url(world[THEIRS]))
    assert r.status_code == 404, (
        f"남의 팀 티켓 첨부가 그대로 나간다({r.status_code}) — 상세는 404 인데 원본만 열려 있다"
    )
    assert b"\x89PNG" not in r.content, "404 인데 파일 바이트가 응답에 실렸다"


def test_the_detail_is_404_too_so_the_two_agree(client, login_as, world):
    """상세와 첨부가 **같은 말**을 해야 한다 — 이 테스트가 전제(상세는 이미 막혀 있다)를 지킨다."""
    login_as("user", email="ta-me@goodmit.co.kr")
    assert client.get(f"/api/tickets/{THEIRS}").status_code == 404


def test_deleting_an_out_of_scope_attachment_is_404_and_the_file_stays(
    client, login_as, world, app
):
    csrf = login_as("user", email="ta-me@goodmit.co.kr")
    r = client.delete(_url(world[THEIRS]), headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, f"남의 팀 티켓 첨부가 지워진다: {r.status_code} {r.text[:120]}"
    assert _still_there(app, world[THEIRS]), "404 라고 답해 놓고 첨부는 실제로 지워졌다"


def test_the_uploader_cannot_delete_an_attachment_that_left_their_scope(
    client, login_as, world, app
):
    """삭제는 **올린 사람 본인이면 티켓을 보지 않고** 지운다 — 그 분기에 범위 판정이 없었다.

    미할당일 때 붙인 첨부가 나중에 남의 부서로 배정되는 것은 실제로 일어나는 순서다. 그때
    읽기는 404 인데 삭제는 되면, 못 보는 티켓을 고칠 수 있다는 뜻이다.
    """
    csrf = login_as("user", email="ta-me@goodmit.co.kr")
    att_id = world["theirs_uploaded_by_me"]
    r = client.delete(_url(att_id), headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404, f"범위 밖 티켓의 내 첨부가 지워진다: {r.status_code} {r.text[:120]}"
    assert _still_there(app, att_id), "404 라고 답해 놓고 첨부는 실제로 지워졌다"


# ── 오탐 방지: 좁히면서 할 수 있던 일을 뺏지 않는다 ────────────────────────────────

def test_an_attachment_on_a_ticket_with_an_unmapped_assignee_stays_open(client, login_as, world):
    """**목록에 보이는 티켓의 첨부는 열려야 한다.** 목록에는 있는데 첨부만 안 열리면
    그건 보안이 아니라 고장이다.

    이 티켓은 담당자를 앱 계정으로 해석할 수 없는 경우다. 0060 부터 그 사실은 가시성과
    무관하고(소속은 프로젝트가 정한다) 우리 팀 프로젝트에 붙어 있으므로 목록에 보인다 —
    보이는 이상 첨부도 열려야 한다는 결합은 그대로다.
    """
    login_as("user", email="ta-me@goodmit.co.kr")
    listed = {t["id"] for t in client.get("/api/tickets/team").json()["tickets"]}
    assert GHOST in listed, "이 테스트의 전제(팀 목록에 보인다)가 깨졌다"

    r = client.get(_url(world[GHOST]))
    assert r.status_code == 200, (
        f"목록에 보이는 티켓의 첨부가 404 다({r.status_code}) — 목록엔 있는데 못 여는 화면"
    )
    assert r.content == PNG


def test_your_own_teams_attachment_still_serves_the_bytes(client, login_as, world):
    login_as("user", email="ta-me@goodmit.co.kr")
    r = client.get(_url(world[MINE]))
    assert r.status_code == 200, f"자기 팀 티켓 첨부를 못 연다: {r.status_code} {r.text[:160]}"
    assert r.content == PNG
    assert r.headers["x-content-type-options"] == "nosniff"


def test_a_global_admin_can_still_open_anything(client, login_as, world):
    login_as("system_admin")
    assert client.get(_url(world[THEIRS])).status_code == 200


def test_you_can_still_delete_an_attachment_on_your_own_teams_ticket(
    client, login_as, world, app
):
    """범위를 걸면서 **할 수 있던 일을 뺏지 않는다** — 자기 팀 티켓 첨부는 그대로 지워진다."""
    csrf = login_as("user", email="ta-me@goodmit.co.kr")
    r = client.delete(_url(world[MINE]), headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, f"자기 팀 티켓 첨부를 못 지운다: {r.status_code} {r.text[:160]}"
    assert not _still_there(app, world[MINE])


def test_a_trashed_tickets_attachment_is_404(client, login_as, world, app):
    """휴지통에 넣은 티켓의 첨부는 없는 것으로 본다(H2) — 상세가 이미 그렇게 답한다."""
    csrf = login_as("user", email="ta-me@goodmit.co.kr")
    trashed = client.post(f"/api/tickets/{MINE}/trash", headers={"X-CSRF-Token": csrf})
    assert trashed.status_code == 200, f"전제(휴지통 이동)가 깨졌다: {trashed.text[:160]}"

    assert client.get(f"/api/tickets/{MINE}").status_code == 404, "전제: 상세는 이미 404 다"
    r = client.get(_url(world[MINE]))
    assert r.status_code == 404, f"지운 티켓의 첨부가 계속 열린다({r.status_code})"
    assert b"\x89PNG" not in r.content
