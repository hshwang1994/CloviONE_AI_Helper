"""게시판 검색이 사용자 표를 통째로 훑지 않는다.

## 무엇이 잘못됐나

작성자 이름 검색이 **비상관 서브쿼리**였다:

    author_ids = select(User.id).where(User.display_name.ilike(like))
    ... Post.author_user_id.in_(author_ids)

SQLite 는 이런 `IN (SELECT ...)` 를 임시 표로 **구체화(materialize)** 한다. 즉 게시판
검색을 한 번 할 때마다 `users` 전체를 훑어 임시 인덱스를 만든다. 게시글이 아니라
**사람 수**에 비례해 무거워지는데, 정작 필요한 것은 "이 글의 작성자가 그 이름인가" 하나다.

상관 서브쿼리(EXISTS)로 바꾸면 글 한 줄마다 `users.id` 기본키를 한 번 찍는다.

## 왜 실행 계획을 보나

이 결함은 **결과가 같고 속도만 다르다.** 결과만 보는 테스트는 고치기 전에도 통과한다 —
그래서 값이 실제로 달라지는 것, 즉 SQLite 가 고른 실행 계획을 본다. 계획 문자열은
`SCAN users`(전수 스캔) → `SEARCH users ... (id=?)`(기본키 조회)로 바뀐다.

행동이 그대로인지는 아래 두 테스트가 따로 못박는다 — 계획만 보면 "빠르지만 틀린" 질의로
바뀌어도 초록불이다.

qa-contract-change: 검색 대조가 공용 접기 규칙(D-495)으로 바뀌어 조건에 `LIKE … ESCAPE` 가 붙었고, 옛 `literal_binds` 렌더링은 그 escape 문자를 문법 오류로 만든다 — 계획은 바인드를 보존하는 EXPLAIN(`tests/fakes/explain.py`)으로 묻는다. 접힌 조건에서 PG 는 users 를 바깥쪽에서 한 번 훑는 Nested Loop 를 고르므로 「Nested Loop 가 없다」는 대리 단언을 「Nested Loop 안쪽에 users 전수 스캔이 없다」로 정확히 고쳐 쓰고 그 판정의 반례 시험을 더했으며, 행동 시험 셋은 그대로 두고 공백을 무시하는 작성자 검색 한 건을 더한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.board.models import Post
from app.board.repository import author_search_clause, list_posts
from app.core.search_text import pattern_for
from tests.fakes.explain import plan_for, plan_tree, walk

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 9, 0, 0)


def _plan(db, stmt) -> list[str]:
    """실행 계획의 각 줄. PG 는 `EXPLAIN` 이다(SQLite 의 `EXPLAIN QUERY PLAN` 이 아니다).

    실행은 하지 않는다 — 계획만 본다. 값은 바인드로 넘긴다(`tests/fakes/explain.py`).
    """
    return plan_for(db, stmt).splitlines()


def test_author_search_does_not_rescan_users_per_post(db):
    """작성자 검색이 사람 표를 **글 하나마다 다시 읽지 않는가.**

    qa-contract-change: 실행 계획을 읽는 어휘가 SQLite 와 PG 사이에서 통째로 달라져 단언을 다시 썼다. PG 는 이 질의를 해시 조인으로 풀어 users 를 한 번만 훑으므로, 옛 「users 를 스캔하면 안 된다」를 그대로 옮기면 더 나은 계획을 실패로 판정하게 된다.
    `SCAN users`(전수) / `SEARCH users`(인덱스) 두 낱말로 말했고, 옛 단언은 "SEARCH 여야
    한다" 였다 — 그건 SQLite 플래너가 `board_posts` 를 몰고 `users` 를 PK 로 찍는다는
    전제였다.

    PG 는 같은 질의를 **해시 조인**으로 푼다: `users` 를 **한 번** 훑어 해시를 만들고
    글마다 그 해시를 본다. 그건 옛 계획보다 나쁘지 않고 대개 낫다. 그러므로 "users 를
    스캔하면 안 된다" 를 그대로 옮기면 **더 나은 계획을 실패로 판정하게 된다.**

    그래서 엔진과 무관하게 성립하는 성질로 다시 쓴다: **`users` 를 글마다 다시 읽지
    않는다.** 그 실패 모양이 `Nested Loop` 안쪽의 `users` 스캔이고, 원래 이 시험이
    막으려던 것도 정확히 그것이다(매 검색마다 사람 표를 반복해서 읽는 것).

    `Nested Loop` 가 있다는 것만으로는 실패가 아니다. 접힌 이름 조건(`search_fold(...)
    LIKE`)이 걸리자 PG 는 `users` 를 **바깥쪽에서 한 번** 훑어 걸린 사람만 고르고, 그 사람의
    글을 `ix_board_posts_author_user_id` 로 찾는 계획을 고른다 — 사람 표는 한 번만 읽힌다.
    그래서 계획을 나무로 받아 **안쪽**에 `users` 전수 스캔이 있는지를 본다.

    `display_name ILIKE '%…%'` 자체는 어느 DB 에서도 인덱스를 못 탄다(선행 와일드카드) —
    그러니 "users 를 한 번도 안 읽는다" 는 애초에 요구할 수 없는 성질이다.
    """
    stmt = select(Post.id).where(author_search_clause(pattern_for("김")))
    steps = _plan(db, stmt)
    joined = chr(10).join(steps)
    assert steps, "계획이 비었다 — 아무것도 안 보고 통과한다"

    tree = plan_tree(db, stmt)
    users = [node for node in walk(tree) if node.get("Relation Name") == "users"]
    assert users, f"계획에 users 가 없다 — 작성자 조건이 빠졌다: {joined}"
    assert _inner_users_scans(tree) == [], f"작성자 검색이 users 를 글마다 다시 읽는다: {joined}"
    assert joined.count("on users") <= 1, (
        f"users 를 두 번 이상 읽는다: {joined}"
    )


def _inner_users_scans(tree: dict) -> list[dict]:
    """`Nested Loop` 의 **안쪽**에 붙은 `users` 전수 스캔 — 바깥 행마다 사람 표를 다시 훑는 자리."""
    return [
        child
        for node in walk(tree) if node["Node Type"] == "Nested Loop"
        for child in node.get("Plans", ())
        if child.get("Parent Relationship") == "Inner"
        and child.get("Relation Name") == "users"
        and child["Node Type"] == "Seq Scan"
    ]


def test_the_rescan_detector_flags_a_per_post_users_scan(db):
    """반례 — 위 판정이 **정말로 잡는가.** 잡지 못하면 위 시험은 아무것도 안 보고 초록이다.

    작성자 조건을 키 없이(`display_name LIKE title`) 걸면 해시로 받을 수 없어 PG 는 글마다
    `users` 를 다시 훑는다. 중간 저장(Materialize)을 끄면 그 모양이 계획에 그대로 드러난다.
    """
    from sqlalchemy import exists, text

    from app.users.models import User

    db.execute(text("SET LOCAL enable_material = off"))
    bad = select(Post.id).where(
        exists(select(User.id).where(User.display_name.like(Post.title)))
    )
    tree = plan_tree(db, bad)
    assert _inner_users_scans(tree), f"반례를 못 잡는다 — 판정이 헛돈다: {tree}"


# ── 행동은 그대로여야 한다 ────────────────────────────────────────────────────


@pytest.fixture()
def posts(db, make_user):
    """작성자 이름으로만 걸리는 글 + 제목으로만 걸리는 글."""
    kim = make_user("bs-kim@goodmit.co.kr", role="user", display_name="김지혜")
    lee = make_user("bs-lee@goodmit.co.kr", role="user", display_name="이철수")
    db.add_all([
        Post(id="bs-p1", author_user_id=kim.id, category="free",
             title="점심 메뉴", body="본문", created_at=NOW, updated_at=NOW),
        Post(id="bs-p2", author_user_id=lee.id, category="free",
             title="김치 담그기", body="본문", created_at=NOW, updated_at=NOW),
    ])
    db.commit()
    return {"kim": kim.id, "lee": lee.id}


def test_searching_by_author_name_still_finds_their_post(db, posts):
    rows, total = list_posts(
        db, category=None, search="김지혜", sort="recent", offset=0, limit=20
    )
    assert {row.id for row in rows} == {"bs-p1"}, "작성자 이름 검색이 글을 못 찾는다"
    assert total == 1


def test_title_and_author_matches_are_unioned_not_intersected(db, posts):
    """'김' 은 작성자(김지혜)와 제목(김치)에 둘 다 걸린다 — 둘 다 나와야 한다."""
    rows, total = list_posts(
        db, category=None, search="김", sort="recent", offset=0, limit=20
    )
    assert {row.id for row in rows} == {"bs-p1", "bs-p2"}, (
        "제목 일치와 작성자 일치 중 하나가 사라졌다"
    )
    assert total == 2, f"총 건수가 결과와 어긋난다: {total}"


def test_a_name_nobody_has_returns_nothing(db, posts):
    rows, total = list_posts(
        db, category=None, search="박영희", sort="recent", offset=0, limit=20
    )
    assert rows == [] and total == 0


def test_the_author_name_matches_with_spaces_folded_on_both_sides(db, posts):
    """작성자 이름도 공용 접기 규칙을 지난다 — 「김 지혜」로 「김지혜」의 글을 찾는다."""
    rows, total = list_posts(
        db, category=None, search="  김  지혜 ", sort="recent", offset=0, limit=20
    )
    assert {row.id for row in rows} == {"bs-p1"} and total == 1
