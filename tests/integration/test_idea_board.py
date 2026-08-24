"""기능 개선 제안 게시판 (7단계 사용자 지적 #1).

새 모듈이 아니라 **기존 게시판의 종류 하나**다(`post.kind = "idea"`). 첨부·댓글·알림·검색·
조직 범위가 이미 지나는 길을 그대로 쓰기 위해서다. 그래서 이 파일이 지키는 것도 "새 기능이
동작하는가" 뿐 아니라 **"원래 있던 게시판이 그대로인가"** 다.

여기서 보는 것은 전부 조용히 틀릴 수 있는 것들이다:

  1. 상태 전이 권한 — 화면에서 버튼을 감추는 것은 통제가 아니다. 서버가 거절해야 한다.
  2. 공감 정렬 — 정렬 키를 받기만 하고 무시해도 목록은 200 으로 돌아온다.
  3. **기존 게시글이 그대로 보이는가** — `kind` 컬럼이 없던 시절에 쓰인 행이 목록에서
     사라지는 것이 이 작업의 가장 큰 위험이다. 마이그레이션이 기본값을 안 채우거나
     목록이 `kind = 'idea'` 만 보게 되면 자유게시판이 통째로 빈다.
  4. 진행 전환이 티켓을 만들고 **연결**하는가 — 제안이 실제 일이 되는 지점이다.
  5. 조직 범위 — 게시판이 이미 지나는 축을 아이디어도 그대로 지나는가.

🔴 4번은 티켓이 **정말로 생겼는지**를 본다. 응답 200 만 보면 '만들었다고 말만 하는'
구현이 통과한다 — 이 저장소에서 이미 여러 번 당한 함정이다(가짜 초록불). 예전에는 가짜
Notion 서버가 받은 생성 요청을 셌지만, S14 부터 티켓 정본은 자체 DB 라 **`tickets` 표에
행이 생겼는지**를 직접 본다. 밖으로 나간 요청이 0 이라는 것도 함께 단언한다 — 그 둘이
같이 있어야 「자체 DB 에 만들었다」가 증명된다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import or_, select, text

from app.tickets.models import Ticket

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row

pytestmark = pytest.mark.integration


# ── 준비 ────────────────────────────────────────────────────────────────────
@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    """옛 소스를 흉내 내는 가짜 서버 — **반례 장치**로만 붙여 둔다.

    제품은 티켓을 자체 DB 에만 만든다. 이 서버가 한 번이라도 생성 요청을 받으면 그것이
    회귀다. 붙여 두지 않으면 「밖으로 안 나갔다」를 확인할 계측기가 없어, 어느 경로가 다시
    밖을 부르기 시작해도 이 파일은 조용히 초록으로 남는다.
    """
    return FakeNotionTasksDB(
        rows=[],
        projects=[project_row(page_id="proj-1", name="포털 개선")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


def _write_idea(client, csrf, *, title, body="", category="기능"):
    r = client.post(
        "/api/board/posts",
        json={"kind": "idea", "category": category, "title": title, "body": body},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    return r.json()["post"]


def _write_free(client, csrf, *, title, category="자유"):
    r = client.post(
        "/api/board/posts",
        json={"category": category, "title": title, "body": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    return r.json()["post"]


def _like(client, csrf, post_id):
    r = client.post(
        "/api/board/reactions",
        json={"target_type": "post", "target_id": post_id, "emoji": "👍"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text


def _set_status(client, csrf, post_id, status, **extra):
    return client.post(
        f"/api/board/posts/{post_id}/status",
        json={"status": status, **extra},
        headers={"X-CSRF-Token": csrf},
    )


def _ticket_row(db, page_id):
    """게시글이 들고 있는 `ticket_page_id` 로 티켓 행을 찾는다 — **두 축을 다 본다**(S14).

    그 값은 모양이 두 가지다: 이관해 온 티켓에서는 `tickets.notion_page_id` 이고, 자체
    DB 에서 만든 티켓에서는 행의 uuid 다(`app/tickets/repository_native.py` 의 식별자
    규약). 한 축만 보면 소스를 되돌리는 날 이 검사가 아무 행도 못 찾고, 그 실패는 제안
    게시판과 아무 관계가 없다.
    """
    return db.execute(
        select(Ticket).where(or_(Ticket.notion_page_id == page_id, Ticket.id == page_id))
    ).scalar_one_or_none()


def _tickets_titled(db, title):
    """제목이 이것인 티켓이 몇 건인가. 중복 발주를 세는 자리라 **수**가 답이다."""
    return db.execute(select(Ticket).where(Ticket.title == title)).scalars().all()


def _ideas(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get("/api/board/posts?kind=idea" + ("&" + query if query else ""))
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. 상태 전이 권한 ────────────────────────────────────────────────────────
def test_a_regular_member_cannot_move_an_idea_along(client, login_as):
    """상태는 **운영자 이상**만 바꾼다. 제안은 누구나 하지만 '진행' 은 약속이다."""
    csrf = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(client, csrf, title="검색을 초성으로도 되게 해 주세요")

    r = _set_status(client, csrf, idea["id"], "검토중")
    assert r.status_code == 403, (
        f"평사원이 제안 상태를 바꿀 수 있다({r.status_code}) - 화면에서 버튼을 감추는 것은 통제가 아니다"
    )


def test_an_operator_can_move_an_idea_along(client, login_as):
    author = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(client, author, title="알림을 요약해서 보내 주세요")

    op = login_as("operator", email="op@goodmit.co.kr")
    r = _set_status(client, op, idea["id"], "검토중")
    assert r.status_code == 200, r.text
    assert r.json()["post"]["idea_status"] == "검토중"


def test_an_unknown_status_is_refused(client, login_as):
    author = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(client, author, title="상태 화이트리스트")
    op = login_as("operator", email="op@goodmit.co.kr")

    r = _set_status(client, op, idea["id"], "아무거나")
    assert r.status_code == 422, f"모르는 상태가 그대로 저장된다({r.status_code})"


def test_a_new_idea_starts_as_proposed(client, login_as):
    csrf = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(client, csrf, title="첫 상태는 제안")
    assert idea["idea_status"] == "제안"


# ── 2. 공감(👍) 정렬 ─────────────────────────────────────────────────────────
def test_ideas_can_be_sorted_by_likes(client, login_as):
    """공감이 많은 제안이 위로. 정렬 키를 받고 **무시해도** 목록은 200 이라 값을 본다."""
    a = login_as("user", email="a@goodmit.co.kr")
    quiet = _write_idea(client, a, title="공감이 없는 제안")
    loud = _write_idea(client, a, title="공감이 많은 제안")
    _like(client, a, loud["id"])

    b = login_as("user", email="b@goodmit.co.kr")
    _like(client, b, loud["id"])

    titles = [i["title"] for i in _ideas(client, sort="likes")["items"]]
    assert titles[0] == "공감이 많은 제안", f"공감 정렬이 먹지 않는다: {titles}"
    assert titles.index("공감이 없는 제안") > 0

    # 그리고 몇 명이 공감했는지 화면이 말할 수 있어야 한다 - 정렬만 되고 수가 없으면
    # 사용자는 왜 그 순서인지 알 수 없다.
    top = _ideas(client, sort="likes")["items"][0]
    assert top["like_count"] == 2, f"공감 수가 응답에 없거나 틀리다: {top.get('like_count')}"


def test_status_filter_narrows_the_idea_list(client, login_as):
    author = login_as("user", email="member@goodmit.co.kr")
    kept = _write_idea(client, author, title="검토 중인 제안")
    _write_idea(client, author, title="아직 제안 단계")

    op = login_as("operator", email="op@goodmit.co.kr")
    assert _set_status(client, op, kept["id"], "검토중").status_code == 200

    titles = [i["title"] for i in _ideas(client, status="검토중")["items"]]
    assert titles == ["검토 중인 제안"], f"상태 필터가 걸러 내지 않는다: {titles}"


# ── 3. 🔴 기존 게시글이 그대로 보인다 ────────────────────────────────────────
def test_posts_written_before_the_kind_column_still_show_up(client, login_as, db):
    """`kind` 가 없던 시절의 행을 **직접** 넣고 자유게시판 목록에서 찾는다.

    이 작업에서 가장 크게 깨질 수 있는 것이 이것이다: 마이그레이션이 기본값을 안 채우거나
    목록이 종류를 엄격히 걸면, 사내 게시판이 **하루아침에 통째로 빈다**. 앱을 통해 만든
    글로는 이걸 확인할 수 없다 - 새 코드가 항상 `kind` 를 채워 넣기 때문이다. 그래서
    컬럼을 빼고 INSERT 한다(마이그레이션의 기본값이 없으면 이 INSERT 자체가 실패한다).
    """
    csrf = login_as("user", email="member@goodmit.co.kr")
    from app.org.constants import DEFAULT_ORG_ID
    from app.users.service import get_user_by_email

    author = get_user_by_email(db, "member@goodmit.co.kr")
    db.execute(
        text(
            "INSERT INTO board_posts "
            "(id, org_id, author_user_id, category, title, body, is_pinned, view_count,"
            " created_at, updated_at) "
            # `is_pinned` 는 boolean 이다. SQLite 는 0/1 을 받았지만 PG 는 타입을 지킨다 —
            # 정수를 넣으면 「column is of type boolean but expression is of type integer」다.
            "VALUES (:id, :org, :uid, :cat, :title, '', false, 0,"
            " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        ),
        {
            "id": "legacy-post-1",
            "org": DEFAULT_ORG_ID,
            "uid": author.id,
            "cat": "공지",
            "title": "종류 컬럼이 생기기 전에 쓴 공지",
        },
    )
    db.commit()

    r = client.get("/api/board/posts")
    assert r.status_code == 200, r.text
    titles = [i["title"] for i in r.json()["items"]]
    assert "종류 컬럼이 생기기 전에 쓴 공지" in titles, (
        f"기존 게시글이 목록에서 사라졌다: {titles}"
    )

    # 단건도 열려야 한다 - 목록에만 보이고 못 열면 반쪽이다.
    detail = client.get("/api/board/posts/legacy-post-1")
    assert detail.status_code == 200, detail.text
    assert detail.json()["post"]["kind"] == "free"

    # 그리고 아이디어 목록에는 **섞이면 안 된다.**
    assert "종류 컬럼이 생기기 전에 쓴 공지" not in [
        i["title"] for i in _ideas(client)["items"]
    ]


def test_the_two_boards_do_not_mix(client, login_as):
    csrf = login_as("user", email="member@goodmit.co.kr")
    _write_free(client, csrf, title="점심 뭐 먹지")
    _write_idea(client, csrf, title="다크 모드를 켜 주세요")

    free_titles = [i["title"] for i in client.get("/api/board/posts").json()["items"]]
    assert free_titles == ["점심 뭐 먹지"], f"아이디어가 자유게시판에 샜다: {free_titles}"

    idea_titles = [i["title"] for i in _ideas(client)["items"]]
    assert idea_titles == ["다크 모드를 켜 주세요"], f"자유글이 아이디어에 샜다: {idea_titles}"


def test_a_free_post_has_no_status_at_all(client, login_as):
    """상태 컬럼은 아이디어에만 뜻이 있다. 자유게시글에 값이 실려 나가면 화면이 배지를 그린다."""
    csrf = login_as("user", email="member@goodmit.co.kr")
    free = _write_free(client, csrf, title="상태 없는 글")
    assert free["idea_status"] is None
    assert free["kind"] == "free"

    op = login_as("operator", email="op@goodmit.co.kr")
    r = _set_status(client, op, free["id"], "검토중")
    assert r.status_code in (404, 409, 422), (
        f"자유게시글에 제안 상태가 붙는다({r.status_code})"
    )
    assert client.get(f"/api/board/posts/{free['id']}").json()["post"]["idea_status"] is None


# ── 4. 진행 전환이 티켓을 만들고 연결한다 ───────────────────────────────────
def test_moving_to_progress_creates_a_ticket_and_links_it(
    client, login_as, notion, portal_project, db
):
    """제안이 실제 일이 되는 지점. **티켓 행이 실제로 생겼는지**를 저장소에서 확인한다."""
    author = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(
        client, author, title="티켓 자동 생성", body="진행으로 넘길 때 티켓을 만든다"
    )
    op = login_as("operator", email="op@goodmit.co.kr")
    assert _set_status(client, op, idea["id"], "검토중").status_code == 200

    r = _set_status(client, op, idea["id"], "진행", project_id=portal_project.id)
    assert r.status_code == 200, r.text
    post = r.json()["post"]
    assert post["idea_status"] == "진행"
    assert post["ticket_page_id"], "티켓을 만들었다면서 연결을 남기지 않았다"

    # 응답 200 만 보면 '만들었다고 말만 하는' 구현이 통과한다 - 표에 행이 있는지 본다.
    row = _ticket_row(db, post["ticket_page_id"])
    assert row is not None, (
        f"티켓을 만들었다는데 표에 행이 없다: ticket_page_id={post['ticket_page_id']}"
    )
    assert "티켓 자동 생성" in (row.title or ""), f"제안 제목이 티켓에 안 실렸다: {row.title}"
    assert "진행으로 넘길 때 티켓을 만든다" in (row.body_markdown or ""), (
        "제안 본문이 티켓 설명으로 안 옮겨졌다"
    )
    # 그리고 그 티켓은 **밖으로 나가지 않았다**(S14) - 자체 DB 가 정본이므로 왕복이 0 이다.
    # 이 반례가 있어야 위 검사가 "표에 있다"와 "노션에도 만들었다"를 구별한다.
    assert notion.created == [], "자체 DB 경로인데 밖으로 생성 요청이 나갔다"


def test_a_failed_ticket_leaves_the_status_untouched(
    client, login_as, db, monkeypatch, portal_project
):
    """티켓을 못 만들면 '진행' 도 남기지 않는다.

    이 저장소에는 "알림 실패가 본 작업을 막지 않는다" 는 규칙이 있지만 여기는 **반대**다.
    알림은 본 작업에 딸린 통지지만, 여기서는 티켓이 곧 '진행' 이라는 말의 내용이다.
    티켓 없이 진행으로 적히면 게시판은 "이 일은 시작됐다"고 말하는데 아무도 그 일을 찾을
    수 없다 - 되돌릴 방법도, 다시 시도할 자리도 없는 거짓말이 영구히 남는다.
    """
    # 🔴 '설정이 안 돼서' 실패하는 것과 '저장소가 쓰다가 죽는' 것은 다른 사건이다. 앞엣것은
    # 티켓 생성에 닿기도 전에 막혀서, 되감기가 정말 도는지를 하나도 검사하지 못한다.
    # 그래서 저장소가 **행을 다 만든 다음에** 죽게 한다(S14 · 자체 DB 경로).
    from app.tickets.repository_native import NativeTicketRepository

    real_create = NativeTicketRepository.create

    def _write_then_die(self, session, *, draft, now=None):
        real_create(self, session, draft=draft, now=now)
        raise RuntimeError("저장소가 티켓 쓰기를 끝내지 못했다")

    monkeypatch.setattr(NativeTicketRepository, "create", _write_then_die)

    author = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(client, author, title="티켓이 실패하는 제안")
    op = login_as("operator", email="op@goodmit.co.kr")

    # 🔴 검토중까지는 **성공해야 한다.** 곧장 진행으로 밀면 전이 규칙(제안에서 진행으로
    # 바로 못 간다)에 먼저 걸려 422 가 나고, 그러면 아래 단정은 '티켓 실패' 가 아니라
    # 전혀 다른 이유로 초록불이 된다 - 실제로 처음 쓸 때 그렇게 통과했다.
    assert _set_status(client, op, idea["id"], "검토중").status_code == 200

    r = _set_status(client, op, idea["id"], "진행", project_id=portal_project.id)
    assert r.status_code >= 400, f"티켓을 못 만들었는데 성공이라고 답한다({r.status_code})"

    after = client.get(f"/api/board/posts/{idea['id']}").json()["post"]
    assert after["idea_status"] == "검토중", (
        f"티켓 없이 상태만 진행으로 남았다: {after['idea_status']}"
    )
    assert not after["ticket_page_id"]
    # 반대쪽도 남으면 안 된다 - 제안이 안 가리키는 **고아 티켓**이 표에 남으면 아무도
    # 그 일을 자기 일로 여기지 않는다. 요청이 통째로 되감겼는지를 여기서 본다.
    assert _tickets_titled(db, "티켓이 실패하는 제안") == [], "되감기지 않은 고아 티켓이 남았다"


def test_a_long_single_paragraph_idea_still_becomes_a_ticket(
    client, login_as, notion, portal_project
):
    """게시글은 줄바꿈 없는 긴 문단 하나로 쓰이는 일이 흔하다 - 예전엔 본문을
    `[:3900]`로만 잘라 그 한 줄이 여전히 티켓 설명의 줄당 상한(1900자)을 넘었고,
    티켓 생성이 **결정적으로** 거절돼 이 제안은 영원히 '진행'으로 못 넘어갔다
    (같은 버튼을 다시 눌러도 같은 본문이라 같은 이유로 또 거절된다).
    """
    author = login_as("user", email="member@goodmit.co.kr")
    long_body = "이 제안은 아주 길게 설명해야 합니다. " * 100  # 줄바꿈 없이 2000자 이상
    idea = _write_idea(client, author, title="긴 제안", body=long_body)
    op = login_as("operator", email="op@goodmit.co.kr")

    assert _set_status(client, op, idea["id"], "검토중").status_code == 200
    r = _set_status(client, op, idea["id"], "진행", project_id=portal_project.id)
    assert r.status_code == 200, r.text
    assert r.json()["post"]["ticket_page_id"], "긴 본문 때문에 티켓 연결이 비었다"


def test_moving_to_progress_twice_does_not_make_a_second_ticket(
    client, login_as, notion, portal_project, db
):
    """이미 티켓이 붙은 제안을 다시 진행으로 밀어도 티켓은 하나다(중복 발주 방지).

    완료로 닫았다가 되살리는 것이 실제로 일어나는 경로다 - 그때 티켓이 하나 더 생기면
    같은 일이 두 장으로 발주된다.

    세는 자리가 **표**여야 한다(S14). 밖으로 나간 요청을 세면 자체 DB 경로에서는 처음부터
    0 이라, 두 번 만들어도 `0 == 0` 으로 통과한다 - 이 검사가 아무것도 안 보게 된다.
    """
    author = login_as("user", email="member@goodmit.co.kr")
    idea = _write_idea(client, author, title="중복 발주 방지")
    op = login_as("operator", email="op@goodmit.co.kr")

    assert _set_status(client, op, idea["id"], "검토중").status_code == 200
    assert _set_status(client, op, idea["id"], "진행", project_id=portal_project.id).status_code == 200
    assert len(_tickets_titled(db, "중복 발주 방지")) == 1, "첫 진행에서 티켓이 안 생겼다"
    assert _set_status(client, op, idea["id"], "완료").status_code == 200
    assert _set_status(client, op, idea["id"], "진행", project_id=portal_project.id).status_code == 200
    assert len(_tickets_titled(db, "중복 발주 방지")) == 1, "같은 제안으로 티켓이 두 번 만들어졌다"


# ── 5. 조직 범위 ────────────────────────────────────────────────────────────
def test_another_organization_neither_sees_nor_moves_an_idea(client, login_as, two_orgs, db):
    """아이디어 게시판도 **조직** 축을 지난다. 범위 밖은 403 이 아니라 404 다."""
    from app.core.authz import ROLE_OPERATOR

    a_csrf = login_as("user", email="orga@goodmit.co.kr")
    idea = _write_idea(client, a_csrf, title="A조직만 볼 제안")

    two_orgs.user_b.role = ROLE_OPERATOR
    db.commit()
    b_csrf = login_as("user", email="orgb@goodmit.co.kr")

    assert idea["title"] not in [i["title"] for i in _ideas(client)["items"]], (
        "다른 조직 제안이 목록에 보인다"
    )
    assert client.get(f"/api/board/posts/{idea['id']}").status_code == 404

    r = _set_status(client, b_csrf, idea["id"], "검토중")
    assert r.status_code == 404, (
        f"다른 조직 운영자가 남의 회사 제안 상태를 바꾼다({r.status_code})"
    )
