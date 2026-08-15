"""FN-41: 부서 범위 필터링이 페이지를 자른 **뒤에** 적용되면 total과 페이지 채움이 어긋난다.

예전 순서: SQL이 검색/타입 등으로 좁힌 결과를 먼저 `offset`/`limit`으로 자르고, 그 페이지
결과에만 `doc_in_scope`를 사후 적용했다 — 페이지 안에서 범위 밖 문서가 걸리면 total은
"이번 페이지에서 걸러진 수"로만 보정되고(다른 페이지의 손실은 못 잡음), 사용자는 "총 N건"
페이저와 그보다 적은 항목을 동시에 봤다.

고친 순서: 검색/타입 등으로 좁힌 결과 **전체**에 범위를 먼저 적용하고, 그 결과를 파이썬에서
페이지로 자른다 — total은 항상 "범위 안에서 실제로 존재하는 전체 개수"이고, 페이지는
있는 만큼 채워진다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-pg-mine", "notion-pg-theirs"
ME = "pg-me@goodmit.co.kr"
OTHER = "pg-other@goodmit.co.kr"


@pytest.fixture()
def interleaved_docs(db, make_user):
    """제목 정렬 시 범위 안/밖 문서가 번갈아 나오게 만든다(1=밖,2=안,3=밖,4=안,5=밖,6=안) —
    "SQL이 먼저 자른 페이지 안에 마침 범위 밖 문서가 섞인" 상황을 결정적으로 재현한다."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.team_docs.models import DocumentCache

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    other = make_user(OTHER, role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))

    for i, nid in zip(range(1, 7), [NID_THEIRS, NID_MINE, NID_THEIRS, NID_MINE, NID_THEIRS, NID_MINE]):
        db.add(DocumentCache(notion_page_id=f"pg{i}", title=f"{i}-문서", author_notion_ids=nid))
    db.commit()


def _list(client, **params):
    r = client.get("/api/team-docs", params={"sort": "title", **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_total_is_the_true_in_scope_count_not_a_per_page_approximation(client, login_as, interleaved_docs):
    login_as("user", email=ME)
    body = _list(client, page=1, page_size=2)
    assert body["total"] == 3, (
        f"진짜 범위 안 문서는 3건(2-문서/4-문서/6-문서)인데 total={body['total']} — "
        "이번 페이지에서만 거른 수로 근사하고 있다"
    )


def test_a_short_page_is_filled_from_later_matches_not_left_short(client, login_as, interleaved_docs):
    """🔴 revert-to-verify 대상 — 예전 순서(페이지 먼저, 범위 나중)면 1페이지가 1건으로
    짧게 나온다(SQL이 1,2번만 자르고 그중 1번만 걸러짐)."""
    login_as("user", email=ME)
    page1 = _list(client, page=1, page_size=2)
    assert [it["title"] for it in page1["items"]] == ["2-문서", "4-문서"], (
        f"1페이지가 채워지지 않았다: {[it['title'] for it in page1['items']]}"
    )
    page2 = _list(client, page=2, page_size=2)
    assert [it["title"] for it in page2["items"]] == ["6-문서"], (
        f"2페이지가 예상과 다르다: {[it['title'] for it in page2['items']]}"
    )


def test_out_of_scope_titles_never_appear_on_any_page(client, login_as, interleaved_docs):
    login_as("user", email=ME)
    all_titles = set()
    for page in (1, 2, 3):
        body = _list(client, page=page, page_size=2)
        all_titles |= {it["title"] for it in body["items"]}
    assert all_titles == {"2-문서", "4-문서", "6-문서"}, all_titles
