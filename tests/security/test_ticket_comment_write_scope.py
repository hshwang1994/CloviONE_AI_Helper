"""티켓 댓글 **쓰기**(수정·삭제)도 범위를 지킨다 (§0-A).

`scripts/check_scope_gates.py` 가 잡은 자리다: `DELETE /api/tickets/comments/{comment_id}` 는
`ensure_can_delete` 만 지났는데 그건 **작성자/운영자 판정**이지 범위 판정이 아니다. 그래서
목록(`list_ticket_comments`)에는 `ensure_in_scope` 가 있는데 삭제에는 없는, **목록만 닫힌**
상태였다 — 남의 부서 운영자가 comment_id 하나로 범위 밖 티켓의 논의를 지울 수 있었고,
자기가 쓴 댓글이 붙은 티켓이 나중에 남의 부서로 배정돼도 계속 고칠 수 있었다(첨부에서
같은 순서로 실제 일어난 일이다 — tests/security/test_ticket_attachment_scope.py).

수정(`edit_ticket_comment`)은 작성자 본인만이라 남의 댓글은 애초에 못 건드리지만, **내가 쓴
댓글이 범위 밖으로 나간 경우**가 남는다. 읽기는 404 인데 쓰기는 되면 "못 보는 티켓을 고칠 수
있다"가 된다.

## 403 이 아니라 404 다

403 은 "그 id 는 존재하지만 너는 못 본다" 를 알려 준다 — 저장소 규칙(`core/scope.py` 모듈
docstring, 팀 채팅 이미지 서빙, `get_scoped_user_or_404`)이 이미 404 로 못박아 놨다.
**단, 범위 안에서의 권한 부족은 그대로 403 이다** — 그건 존재를 숨기는 문제가 아니라 누가
남의 문장을 지울 수 있느냐는 문제다. 아래 오탐 방지 테스트가 그 선을 지킨다.

## ⚠️ 담당자를 해석할 수 없는 티켓의 댓글은 **여전히 지워져야 한다**

그런 티켓은 미할당 트리아지에 뜬다(포탈 전용 버킷). 댓글 쓰기만 막으면 목록에는 보이는데
자기가 쓴 댓글을 못 지우는 화면이 된다 — 그건 보안이 아니라 고장이다. 그 결합은
`ensure_in_scope` 가 갖고 있고, 댓글 경로가 그걸 깨뜨리지 않는지 여기서 지킨다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.tickets.models import TicketCache, TicketComment, utcnow
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-tc-mine", "notion-tc-theirs"

MINE, THEIRS, GHOST = "tc-mine", "tc-theirs", "tc-ghost"

ME = "tc-me@goodmit.co.kr"
OTHER = "tc-other@goodmit.co.kr"
DEPT_ADMIN = "tc-admin@goodmit.co.kr"


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
    """부서가 갈린 사용자 셋 + 세 티켓 + 각 티켓에 이미 달려 있는 댓글.

    댓글은 API 가 아니라 직접 만든다 — `add_ticket_comment` 에는 이미 범위가 걸려 있어
    API 로는 "남의 팀 티켓에 내 댓글이 이미 달려 있는" 상태를 만들 수 없다. 이 테스트가
    보는 것은 다는 권한이 아니라 **이미 달려 있는 댓글을 누가 고치고 지울 수 있나**다.
    """
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.tickets import comments as ticket_comments
    from app.tickets.sync import sync_tickets

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    mine_dept = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs_dept = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine_dept, theirs_dept])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    other = make_user(OTHER, role="user", display_name="남")
    # 부서 범위 관리자 — 역할로는 모더레이션이 되지만 범위는 우리팀뿐이다. 이 조합이
    # 정확히 구멍의 주인공이다: `ensure_can_delete` 만 보면 통과해 버린다.
    boss = make_user(DEPT_ADMIN, role="admin", display_name="우리팀장")
    me.department_id = mine_dept.id
    other.department_id = theirs_dept.id
    boss.department_id = mine_dept.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine_dept.id
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

    def _comment(page_id: str, author, body: str) -> str:
        return ticket_comments.create_comment(
            db, ticket_uid=_uid(page_id), author=author, body=body, now=utcnow()
        ).id

    ids = {
        "mine_by_me": _comment(MINE, me, "우리팀 티켓에 내가 쓴 댓글"),
        "mine_by_other": _comment(MINE, other, "우리팀 티켓에 남이 쓴 댓글"),
        "theirs_by_other": _comment(THEIRS, other, "남의팀 논의 내용"),
        # 미할당일 때 내가 달았는데 그 뒤 남의 부서로 배정된 티켓 — 실제로 일어나는 순서다.
        "theirs_by_me": _comment(THEIRS, me, "범위 밖으로 나간 내 댓글"),
        "ghost_by_me": _comment(GHOST, me, "트리아지 티켓에 내가 쓴 댓글"),
    }
    db.commit()
    return ids


def _url(comment_id: str) -> str:
    return f"/api/tickets/comments/{comment_id}"


def _alive(app, comment_id: str) -> bool:
    """앱이 쓰는 세션과 **다른** 세션으로 다시 읽는다 — 지워졌는지는 DB 에 물어야 안다."""
    with app.state.session_factory() as s:
        row = s.get(TicketComment, comment_id)
        return row is not None and row.deleted_at is None


def _body_of(app, comment_id: str) -> str:
    with app.state.session_factory() as s:
        return s.get(TicketComment, comment_id).body


# ── 범위 밖: 지워지지도, 고쳐지지도, 새 나가지도 않아야 한다 ────────────────────

def test_a_dept_admin_cannot_delete_a_comment_on_another_teams_ticket(
    client, login_as, world, app
):
    """모더레이션 권한은 **범위 안에서만** 있다 — 역할만 보고 통과시키면 부서가 무의미해진다."""
    csrf = login_as("admin", email=DEPT_ADMIN)
    r = client.delete(_url(world["theirs_by_other"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 404, (
        f"남의 팀 티켓 댓글이 지워진다({r.status_code}) — 목록은 404 인데 삭제만 열려 있다: "
        f"{r.text[:160]}"
    )
    assert _alive(app, world["theirs_by_other"]), "404 라고 답해 놓고 댓글은 실제로 지워졌다"


def test_the_comment_list_is_404_too_so_the_two_agree(client, login_as, world):
    """목록과 쓰기가 **같은 말**을 해야 한다 — 이 테스트가 전제(목록은 이미 막혀 있다)를 지킨다."""
    login_as("admin", email=DEPT_ADMIN)
    assert client.get(f"/api/tickets/{THEIRS}/comments").status_code == 404


def test_the_404_does_not_leak_the_other_teams_discussion(client, login_as, world):
    """거절 응답에 목록이 실려 나가면 막은 의미가 없다.

    성공 응답이 **늘 그 티켓의 댓글 전체**라 여기가 특히 위험하다: 지운 댓글 자신은 툼스톤이
    돼 본문이 비지만 **같은 티켓의 다른 댓글은 본문 그대로** 실린다. 즉 지울 생각이 없어도
    삭제를 한 번 던지면 남의 팀 논의를 읽을 수 있었다.
    """
    csrf = login_as("admin", email=DEPT_ADMIN)
    r = client.delete(_url(world["theirs_by_other"]), headers={"X-CSRF-Token": csrf})
    assert "범위 밖으로 나간 내 댓글" not in r.text, (
        "삭제 응답에 같은 티켓의 다른 댓글 본문이 실려 나갔다 — 삭제가 곧 조회가 된다"
    )
    assert "남의팀 논의 내용" not in r.text, "404 인데 응답에 남의 팀 댓글 본문이 실렸다"


def test_an_out_of_scope_stranger_gets_404_not_403(client, login_as, world):
    """범위 판정이 권한 판정보다 **먼저**여야 한다.

    순서가 뒤집히면 이 사람은 403 을 받는다("작성자도 운영자도 아니다"). 그런데 403 은 **그
    comment_id 가 존재한다**는 뜻이라, id 를 찍어 가며 403/404 를 세면 남의 부서 논의의 존재를
    통째로 열거할 수 있다 — 목록에서 가린 것이 단건에서 새는 IDOR 그 자체다.
    """
    csrf = login_as("user", email=ME)
    r = client.delete(_url(world["theirs_by_other"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 404, (
        f"범위 밖 댓글에 403 이 나갔다({r.status_code}) — 존재를 알려 주는 답이다"
    )


def test_the_author_cannot_delete_a_comment_that_left_their_scope(client, login_as, world, app):
    """작성자 본인이면 티켓을 보지 않고 지운다 — 그 분기에 범위 판정이 없었다.

    미할당일 때 단 댓글이 나중에 남의 부서로 배정되는 것은 실제 순서다. 그때 읽기는 404 인데
    쓰기는 되면 못 보는 티켓의 논의를 고칠 수 있다는 뜻이다.
    """
    csrf = login_as("user", email=ME)
    r = client.delete(_url(world["theirs_by_me"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 404, f"범위 밖 티켓의 내 댓글이 지워진다: {r.status_code} {r.text[:160]}"
    assert _alive(app, world["theirs_by_me"]), "404 라고 답해 놓고 댓글은 실제로 지워졌다"


def test_the_author_cannot_edit_a_comment_that_left_their_scope(client, login_as, world, app):
    """수정도 같은 판정을 지나야 한다 — 지우는 것만 막고 고쳐 쓰는 것을 열어 두면 반쪽이다."""
    csrf = login_as("user", email=ME)
    r = client.patch(_url(world["theirs_by_me"]), json={"body": "덮어쓰기"},
                     headers={"X-CSRF-Token": csrf})

    assert r.status_code == 404, f"범위 밖 티켓의 내 댓글이 고쳐진다: {r.status_code} {r.text[:160]}"
    assert _body_of(app, world["theirs_by_me"]) == "범위 밖으로 나간 내 댓글", (
        "404 라고 답해 놓고 본문은 실제로 바뀌었다"
    )


def test_a_trashed_tickets_comment_cannot_be_deleted(client, login_as, world, app):
    """휴지통에 넣은 티켓의 댓글은 없는 것으로 본다(H2) — 목록이 이미 그렇게 답한다."""
    csrf = login_as("user", email=ME)
    trashed = client.post(f"/api/tickets/{MINE}/trash", headers={"X-CSRF-Token": csrf})
    assert trashed.status_code == 200, f"전제(휴지통 이동)가 깨졌다: {trashed.text[:160]}"
    assert client.get(f"/api/tickets/{MINE}/comments").status_code == 404, "전제: 목록은 이미 404 다"

    r = client.delete(_url(world["mine_by_me"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 404, f"지운 티켓의 댓글이 계속 지워진다({r.status_code})"
    assert _alive(app, world["mine_by_me"]), "404 라고 답해 놓고 댓글은 실제로 지워졌다"


# ── 오탐 방지: 좁히면서 할 수 있던 일을 뺏지 않는다 ────────────────────────────────

def test_a_comment_on_a_ticket_with_an_unmapped_assignee_can_still_be_deleted(client, login_as, world, app):
    """**목록에 보이는 티켓의 댓글은 지워져야 한다.** 목록엔 있는데 못 지우면
    그건 보안이 아니라 고장이다.

    이 티켓은 담당자를 앱 계정으로 해석할 수 없는 경우다. 0060 부터 그 사실은 가시성과
    무관하고(소속은 프로젝트가 정한다) 우리 팀 프로젝트에 붙어 있으므로 목록에 보인다.
    """
    csrf = login_as("user", email=ME)
    listed = {t["id"] for t in client.get("/api/tickets/team").json()["tickets"]}
    assert GHOST in listed, "이 테스트의 전제(팀 목록에 보인다)가 깨졌다"

    r = client.delete(_url(world["ghost_by_me"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 200, (
        f"목록에 보이는 티켓의 댓글을 못 지운다({r.status_code}) — 목록엔 있는데 못 지우는 화면: "
        f"{r.text[:160]}"
    )
    assert not _alive(app, world["ghost_by_me"])


def test_you_can_still_edit_and_delete_on_your_own_teams_ticket(client, login_as, world, app):
    csrf = login_as("user", email=ME)
    edited = client.patch(_url(world["mine_by_me"]), json={"body": "고침"},
                          headers={"X-CSRF-Token": csrf})
    assert edited.status_code == 200, f"자기 팀 티켓의 내 댓글을 못 고친다: {edited.text[:160]}"
    assert _body_of(app, world["mine_by_me"]) == "고침"

    removed = client.delete(_url(world["mine_by_me"]), headers={"X-CSRF-Token": csrf})
    assert removed.status_code == 200, f"자기 팀 티켓의 내 댓글을 못 지운다: {removed.text[:160]}"
    assert not _alive(app, world["mine_by_me"])


def test_a_dept_admin_still_moderates_inside_their_own_scope(client, login_as, world, app):
    """범위를 걸면서 모더레이션 자체를 없애면 안 된다 — 우리팀 티켓의 남의 댓글은 그대로 지워진다."""
    csrf = login_as("admin", email=DEPT_ADMIN)
    r = client.delete(_url(world["mine_by_other"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 200, f"자기 범위 안에서도 모더레이션이 안 된다: {r.text[:160]}"
    assert not _alive(app, world["mine_by_other"])


def test_a_global_admin_can_still_delete_anything(client, login_as, world, app):
    csrf = login_as("system_admin")
    r = client.delete(_url(world["theirs_by_other"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 200, f"전역 관리자가 막힌다: {r.text[:160]}"
    assert not _alive(app, world["theirs_by_other"])


def test_in_scope_permission_failures_are_still_403_not_404(client, login_as, world, app):
    """범위 **안**에서 권한이 없는 것은 404 로 뭉개지 않는다 — 존재를 숨길 이유가 없고,
    전부 404 로 만들면 "왜 안 되지" 를 사용자도 우리도 알 수 없다."""
    csrf = login_as("user", email=ME)
    r = client.delete(_url(world["mine_by_other"]), headers={"X-CSRF-Token": csrf})

    assert r.status_code == 403, f"범위 안 권한 부족이 403 이 아니다: {r.status_code} {r.text[:160]}"
    assert _alive(app, world["mine_by_other"])
