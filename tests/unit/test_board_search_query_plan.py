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
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select, text

from app.board.models import Post
from app.board.repository import author_search_clause, list_posts

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 9, 0, 0)


def _plan(db, stmt) -> list[str]:
    compiled = stmt.compile(
        db.get_bind(), compile_kwargs={"literal_binds": True}
    )
    return [row[3] for row in db.execute(text("EXPLAIN QUERY PLAN " + str(compiled))).all()]


def test_author_search_does_not_scan_the_whole_user_table(db):
    """`SCAN users` 가 계획에 남아 있으면 매 검색마다 사람 표를 통째로 읽는다."""
    stmt = select(Post.id).where(author_search_clause("%김%"))
    steps = _plan(db, stmt)

    assert not any(step.strip().startswith("SCAN users") for step in steps), (
        f"작성자 검색이 users 를 전수 스캔한다: {steps}"
    )
    assert any("users" in step and "SEARCH" in step for step in steps), (
        f"users 를 기본키로 찍지 않는다: {steps}"
    )


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
