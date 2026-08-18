"""홈 '오늘' 위젯(최근 문서·게시판)도 다른 화면과 같은 범위 판정을 지난다 (SEC-12, SEC-13).

`app/home/readers.py`의 `recent_documents`/`recent_board_posts`는 신규 저장소 없이
기존 리더(board 저장소, team_docs 캐시)를 그대로 조합하는 위젯이라고 스스로 문서화하는데,
정작 그 "기존 리더"가 이미 지나는 범위 판정 자체를 안 지났다:

- 게시판의 모든 실제 경로(`board/router.py`)는 `_viewer_org_id(me)`로 조직 게이트를 지난다
  (`Post`가 `OrgScopedMixin`을 상속). 이 위젯은 `org_id` 없이 `list_posts`를 불렀다(SEC-12).
- `GET /api/team-docs`는 `service.doc_in_scope`로 부서 범위 밖 문서를 거른다. 이 위젯은
  `viewer` 인자 자체가 없어 전 부서 문서가 그대로 나갔다(SEC-13).

`two_orgs`/두 부서 세계가 실제로 있어야 조건이 한 행이라도 걸러 검증이 뜻을 갖는다
(PLAN4 — 조직이 하나뿐이면 필터를 넣어도 초록불이 아무것도 증명하지 못한다).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


def test_home_recent_board_only_shows_the_viewers_org(db, two_orgs):
    """SEC-12: 다른 조직 게시글이 홈 '최근 글'에 새면 안 된다."""
    from app.board.models import Post
    from app.home import readers

    db.add_all([
        Post(id="p-mine", author_user_id=two_orgs.user_a.id, category="자유",
             title="우리 조직 공지", org_id=two_orgs.org_a_id),
        Post(id="p-theirs", author_user_id=two_orgs.user_b.id, category="자유",
             title="다른 조직 공지", org_id=two_orgs.org_b_id),
    ])
    db.commit()

    posts = readers.recent_board_posts(db, limit=10, org_id=two_orgs.org_a_id)
    titles = {p["title"] for p in posts}
    assert "우리 조직 공지" in titles
    assert "다른 조직 공지" not in titles, "다른 조직 게시글이 홈 위젯으로 샜다"


def test_home_recent_board_without_org_id_is_unfiltered_baseline(db, two_orgs):
    """org_id를 안 주면(예: 시스템 컨텍스트) 이전처럼 전체를 본다 — 회귀 방지용 대조."""
    from app.board.models import Post
    from app.home import readers

    db.add_all([
        Post(id="p-mine2", author_user_id=two_orgs.user_a.id, category="자유",
             title="우리 조직 공지2", org_id=two_orgs.org_a_id),
        Post(id="p-theirs2", author_user_id=two_orgs.user_b.id, category="자유",
             title="다른 조직 공지2", org_id=two_orgs.org_b_id),
    ])
    db.commit()

    posts = readers.recent_board_posts(db, limit=10, org_id=None)
    titles = {p["title"] for p in posts}
    assert {"우리 조직 공지2", "다른 조직 공지2"} <= titles


@pytest.fixture()
def two_depts(db, make_user):
    """부서 둘 + 각 팀 사람. team_docs 부서-스코프 테스트(test_team_docs_filter_scope.py)와 같은 형태."""
    from dataclasses import dataclass

    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    me = make_user("hw-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("hw-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id="hw-nid-me", status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id="hw-nid-other", status=STATUS_VERIFIED))
    db.commit()

    @dataclass(frozen=True)
    class DeptWorld:
        me: object
        other: object
        # 문서의 소속(0060)은 문서 자신이 든다 — 그 소속을 심으려면 부서도 함께 필요하다.
        mine: object
        theirs: object

    return DeptWorld(me=me, other=other, mine=mine, theirs=theirs)


def test_home_recent_documents_only_shows_the_viewers_department(db, two_depts):
    """SEC-13: 다른 부서 문서(제목·소유자·수정시각)가 홈 '최근 문서'에 새면 안 된다."""
    from app.home import readers
    from app.team_docs.models import DocumentCache

    world = two_depts

    db.add_all([
        DocumentCache(notion_page_id="d-mine", title="우리팀 회의록",
                      author_notion_ids="hw-nid-me", owner_kind="department",
                      owner_dept_id=world.mine.id, last_edited="2026-08-10T00:00:00.000Z"),
        DocumentCache(notion_page_id="d-theirs", title="남의팀 기밀 계약서",
                      author_notion_ids="hw-nid-other", owner_kind="department",
                      owner_dept_id=world.theirs.id, last_edited="2026-08-10T01:00:00.000Z"),
    ])
    db.commit()

    docs = readers.recent_documents(db, limit=10, viewer=two_depts.me)
    titles = {d["title"] for d in docs}
    assert "우리팀 회의록" in titles
    assert "남의팀 기밀 계약서" not in titles, "다른 부서 문서가 홈 위젯으로 샜다"


def test_home_recent_documents_without_viewer_is_unfiltered_baseline(db, two_depts):
    """viewer를 안 주면 이전처럼 전체를 본다 — 회귀 방지용 대조."""
    from app.home import readers
    from app.team_docs.models import DocumentCache

    world = two_depts

    db.add_all([
        DocumentCache(notion_page_id="d-mine2", title="우리팀 회의록2",
                      author_notion_ids="hw-nid-me", owner_kind="department",
                      owner_dept_id=world.mine.id, last_edited="2026-08-10T00:00:00.000Z"),
        DocumentCache(notion_page_id="d-theirs2", title="남의팀 기밀 계약서2",
                      author_notion_ids="hw-nid-other", owner_kind="department",
                      owner_dept_id=world.theirs.id, last_edited="2026-08-10T01:00:00.000Z"),
    ])
    db.commit()

    docs = readers.recent_documents(db, limit=10, viewer=None)
    titles = {d["title"] for d in docs}
    assert {"우리팀 회의록2", "남의팀 기밀 계약서2"} <= titles


def test_home_recent_documents_still_returns_up_to_limit_after_scope_filtering(db, two_depts):
    """부서 필터가 SQL LIMIT 뒤에 걸리므로, 넉넉히 더 가져와 거르지 않으면 실제로는
    더 있는데도 5건 미만만 보이는 회귀가 난다 — 3건이 걸러져도 남은 2건이 다 나와야 한다."""
    from app.home import readers
    from app.team_docs.models import DocumentCache

    world = two_depts

    db.add_all([
        DocumentCache(notion_page_id=f"d-other-{i}", title=f"남의팀 문서{i}",
                      author_notion_ids="hw-nid-other", owner_kind="department",
                      owner_dept_id=world.theirs.id,
                      last_edited=f"2026-08-1{i}T00:00:00.000Z")
        for i in range(3)
    ] + [
        DocumentCache(notion_page_id=f"d-mine-{i}", title=f"우리팀 문서{i}",
                      author_notion_ids="hw-nid-me", owner_kind="department",
                      owner_dept_id=world.mine.id,
                      last_edited=f"2026-08-0{i+1}T00:00:00.000Z")
        for i in range(2)
    ])
    db.commit()

    docs = readers.recent_documents(db, limit=2, viewer=two_depts.me)
    assert len(docs) == 2, docs
    assert all(d["title"].startswith("우리팀") for d in docs)


# ── whole-product 재감사(2026-08-13) — 형제 함수 3개도 같은 판정을 안 지났다 ──────
#
# recent_documents/recent_board_posts는 위에서 이미 SEC-12/SEC-13으로 닫혔는데, 같은
# app/home/readers.py 안의 형제 함수 셋(주간 다이제스트가 쓰는 documents_changed_between·
# board_posts_between, 트리아지가 쓰는 assignee_candidates)은 이번 재감사 전까지 같은
# 판정을 하나도 안 지나고 있었다 — GET /api/assistant/weekly-digest·GET /api/assistant/
# triage 둘 다 role 게이트가 없어(전 사용자용 개인 다이제스트/제안이라는 설계) 아무나
# 회사 밖·타 부서 데이터를 그대로 봤다.

SINCE = "2026-08-02T15:00:00"
UNTIL = "2026-08-09T15:00:00"


def test_home_documents_changed_between_only_shows_the_viewers_department(db, two_depts):
    """SEC-13과 같은 뿌리 — 주간 다이제스트의 '이번 주 변경 문서'도 부서 범위를 지나야 한다."""
    from app.home import readers
    from app.team_docs.models import DocumentCache

    world = two_depts

    db.add_all([
        DocumentCache(notion_page_id="dc-mine", title="우리팀 주간 회의록",
                      author_notion_ids="hw-nid-me", owner_kind="department",
                      owner_dept_id=world.mine.id, last_edited="2026-08-04T02:00:00.000Z"),
        DocumentCache(notion_page_id="dc-theirs", title="남의팀 주간 계약서",
                      author_notion_ids="hw-nid-other", owner_kind="department",
                      owner_dept_id=world.theirs.id, last_edited="2026-08-05T02:00:00.000Z"),
    ])
    db.commit()

    result = readers.documents_changed_between(db, SINCE, UNTIL, viewer=two_depts.me)
    titles = {d["title"] for d in result["items"]}
    assert "우리팀 주간 회의록" in titles
    assert "남의팀 주간 계약서" not in titles, "다른 부서 문서가 주간 다이제스트로 샜다"
    assert result["count"] == 1, "count도 스코프 필터 뒤 값이어야 한다(미리보기 개수가 아니라)"


def test_home_documents_changed_between_without_viewer_is_unfiltered_baseline(db, two_depts):
    """viewer를 안 주면(예: 배경 집계) 이전처럼 전체를 본다 — 회귀 방지용 대조."""
    from app.home import readers
    from app.team_docs.models import DocumentCache

    world = two_depts

    db.add_all([
        DocumentCache(notion_page_id="dc-mine2", title="우리팀 주간 회의록2",
                      author_notion_ids="hw-nid-me", last_edited="2026-08-04T02:00:00.000Z"),
        DocumentCache(notion_page_id="dc-theirs2", title="남의팀 주간 계약서2",
                      author_notion_ids="hw-nid-other", last_edited="2026-08-05T02:00:00.000Z"),
    ])
    db.commit()

    result = readers.documents_changed_between(db, SINCE, UNTIL, viewer=None)
    titles = {d["title"] for d in result["items"]}
    assert {"우리팀 주간 회의록2", "남의팀 주간 계약서2"} <= titles
    assert result["count"] == 2


def test_home_board_posts_between_only_shows_the_viewers_org(db, two_orgs):
    """SEC-12와 같은 뿌리 — 주간 다이제스트의 '이번 주 작성된 글'도 조직 범위를 지나야 한다."""
    from datetime import datetime

    from app.board.models import Post
    from app.home import readers

    db.add_all([
        Post(id="pb-mine", author_user_id=two_orgs.user_a.id, category="자유",
             title="우리 조직 주간 공지", org_id=two_orgs.org_a_id,
             created_at=datetime(2026, 8, 4, 2, 0, 0)),
        Post(id="pb-theirs", author_user_id=two_orgs.user_b.id, category="자유",
             title="다른 조직 주간 공지", org_id=two_orgs.org_b_id,
             created_at=datetime(2026, 8, 5, 2, 0, 0)),
    ])
    db.commit()

    since_utc = datetime(2026, 8, 2, 15, 0, 0)
    until_utc = datetime(2026, 8, 9, 15, 0, 0)
    result = readers.board_posts_between(db, since_utc, until_utc, org_id=two_orgs.org_a_id)
    titles = {p["title"] for p in result["items"]}
    assert "우리 조직 주간 공지" in titles
    assert "다른 조직 주간 공지" not in titles, "다른 조직 게시글이 주간 다이제스트로 샜다"
    assert result["count"] == 1


def test_home_board_posts_between_without_org_id_is_unfiltered_baseline(db, two_orgs):
    """org_id를 안 주면 이전처럼 전체를 본다 — 회귀 방지용 대조."""
    from datetime import datetime

    from app.board.models import Post
    from app.home import readers

    db.add_all([
        Post(id="pb-mine2", author_user_id=two_orgs.user_a.id, category="자유",
             title="우리 조직 주간 공지2", org_id=two_orgs.org_a_id,
             created_at=datetime(2026, 8, 4, 2, 0, 0)),
        Post(id="pb-theirs2", author_user_id=two_orgs.user_b.id, category="자유",
             title="다른 조직 주간 공지2", org_id=two_orgs.org_b_id,
             created_at=datetime(2026, 8, 5, 2, 0, 0)),
    ])
    db.commit()

    since_utc = datetime(2026, 8, 2, 15, 0, 0)
    until_utc = datetime(2026, 8, 9, 15, 0, 0)
    result = readers.board_posts_between(db, since_utc, until_utc, org_id=None)
    titles = {p["title"] for p in result["items"]}
    assert {"우리 조직 주간 공지2", "다른 조직 주간 공지2"} <= titles
    assert result["count"] == 2


def test_home_assignee_candidates_only_shows_the_viewers_org(db, two_orgs):
    """1순위 유출 #7과 같은 뿌리 — 트리아지 담당자 제안도 조직 범위를 지나야 한다."""
    from app.home import readers
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    db.add(UserNotionMapping(user_id=two_orgs.user_a.id, notion_user_id="tri-n-a",
                             status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=two_orgs.user_b.id, notion_user_id="tri-n-b",
                             status=STATUS_VERIFIED))
    db.commit()

    candidates = readers.assignee_candidates(db, org_id=two_orgs.org_a_id)
    names = {c["display_name"] for c in candidates}
    assert "A사람" in names
    assert "B사람" not in names, "다른 조직 사람이 트리아지 담당자 후보로 나온다"


def test_home_assignee_candidates_without_org_id_is_unfiltered_baseline(db, two_orgs):
    """org_id를 안 주면 이전처럼 전체를 본다 — 회귀 방지용 대조."""
    from app.home import readers
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    db.add(UserNotionMapping(user_id=two_orgs.user_a.id, notion_user_id="tri-n-a2",
                             status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=two_orgs.user_b.id, notion_user_id="tri-n-b2",
                             status=STATUS_VERIFIED))
    db.commit()

    candidates = readers.assignee_candidates(db, org_id=None)
    names = {c["display_name"] for c in candidates}
    assert {"A사람", "B사람"} <= names
