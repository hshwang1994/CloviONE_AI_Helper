"""자유게시판 데이터 접근 (쿼리 전용 — 비즈니스 규칙은 service).

soft delete 규약: 조회 함수는 기본으로 deleted_at IS NULL 만 돌려준다. 삭제된 행을
직접 다뤄야 하는 곳(소유권 확인 등)만 include_deleted=True 를 쓴다.
"""

from __future__ import annotations

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.board.models import (
    LIKE_EMOJI,
    TARGET_POST,
    Comment,
    Post,
    PostAttachment,
    Reaction,
)
from app.users.models import User


def visible_posts(org_id: str | None = None, *, include_deleted: bool = False):
    """게시글이 **보이는가**를 정하는 단 하나의 자리 — 목록도 단건도 여기서 출발한다.

    판정이 두 벌이 되면 한쪽만 고쳐지고 증상은 "어떤 사람만 안 된다" 가 된다. 실제로
    그랬다: `list_posts` 만 `org_id` 를 걸고 단건·댓글·첨부·쓰기는 id 를 그대로 받아,
    목록에서 가린 남의 회사 글이 id 하나로 읽히고 **고쳐지고 지워졌다**(3순위 IDOR).

    거는 축은 **조직 하나뿐**이다. 부서로는 좁히지 않는다 — 자유게시판은 **사내** 공지판
    이라 부서로 나누면 그 성격이 사라진다(사내 공지가 자기 팀에만 보이면 공지판이 아니다).

    `org_id` 가 없으면 아무것도 안 건다. 목록이 처음부터 그렇게 판정했고, 단건만 더 엄하게
    만들면 그 순간 판정이 다시 두 벌이 된다.
    """
    stmt = select(Post)
    if not include_deleted:
        stmt = stmt.where(Post.deleted_at.is_(None))
    if org_id:
        stmt = stmt.where(Post.org_id == org_id)
    return stmt


def get_post(
    db: Session,
    post_id: str,
    *,
    include_deleted: bool = False,
    org_id: str | None = None,
) -> Post | None:
    """단건. `org_id` 를 주면 **범위 밖은 없는 것으로 취급한다** — None 을 돌려주므로
    호출자는 404 를 낸다(403 은 그 글이 존재한다는 사실을 알려 준다, 저장소 규칙)."""
    stmt = visible_posts(org_id, include_deleted=include_deleted).where(Post.id == post_id)
    return db.execute(stmt).scalar_one_or_none()


def _like_counts_subquery():
    """게시글별 공감(👍) 수. 반응 표에서 세며, 공감 전용 표는 만들지 않는다.

    `group_by(target_id)` 라 게시글 한 건당 한 행이다 — 이것을 outer join 해도 원래 행이
    불어나지 않는다(총 건수가 조용히 부풀지 않는 근거).
    """
    return (
        select(Reaction.target_id.label("target_id"), func.count().label("likes"))
        .where(Reaction.target_type == TARGET_POST, Reaction.emoji == LIKE_EMOJI)
        .group_by(Reaction.target_id)
        .subquery()
    )


def like_counts(db: Session, post_ids: list[str]) -> dict[str, int]:
    """{post_id: 공감 수}. 정렬만 하고 수를 안 주면 화면은 **왜 그 순서인지 말할 수 없다.**"""
    if not post_ids:
        return {}
    rows = db.execute(
        select(Reaction.target_id, func.count())
        .where(
            Reaction.target_type == TARGET_POST,
            Reaction.emoji == LIKE_EMOJI,
            Reaction.target_id.in_(post_ids),
        )
        .group_by(Reaction.target_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


def author_search_clause(like: str):
    """작성자 표시명이 검색어에 걸리는가 — **상관** 서브쿼리(EXISTS)로.

    예전에는 비상관 서브쿼리였다:

        Post.author_user_id.in_(select(User.id).where(User.display_name.ilike(like)))

    SQLite 는 이런 `IN (SELECT ...)` 를 임시 표로 **구체화**한다. 게시판 검색 한 번마다
    `users` 를 통째로 훑어 임시 인덱스를 만든다는 뜻이다 — 비용이 게시글이 아니라 **사람
    수**에 비례하는데, 정작 필요한 것은 "이 글의 작성자가 그 이름인가" 하나다.

    EXISTS 로 상관시키면 글 한 줄마다 `users.id` 기본키를 한 번 찍는다. 실행 계획이
    `SCAN users` 에서 `SEARCH users ... (id=?)` 로 바뀐다
    (`tests/unit/test_board_search_query_plan.py` 가 그 문자열을 못박는다 — 결과가 같고
    속도만 다른 결함이라 결과만 보는 테스트로는 잡히지 않는다).

    결과는 같다. `author_user_id` 가 NULL 이면 양쪽 다 거짓이다.
    """
    return (
        select(literal(1))
        .where(User.id == Post.author_user_id, User.display_name.ilike(like))
        .exists()
    )


def list_posts(
    db: Session,
    *,
    category: str | None,
    search: str | None,
    sort: str,
    offset: int,
    limit: int,
    org_id: str | None = None,
    kind: str | None = None,
    idea_status: str | None = None,
) -> tuple[list[Post], int]:
    """`org_id` 를 주면 그 조직 글만 (1순위 유출 #4).

    자유게시판은 **사내** 공지판이다 — 다른 회사 글이 섞이면 안 된다. 부서로 좁히지는
    않는다(그러면 사내 공지판이 아니게 된다). `Post` 는 `OrgScopedMixin` 을 이미 상속한다 —
    **모델은 선언했는데 질의가 안 걸고 있었다.**

    조직이 하나뿐일 때는 이 조건을 넣어도 **한 행도 안 걸러져 검증이 불가능**했다(PLAN4).
    `two_orgs` 시드를 먼저 만든 뒤에야 초록불이 뜻을 갖는다.

    판정 자체는 `visible_posts` 한 곳에 있다 — 단건·댓글·첨부·쓰기가 같은 것을 쓴다.
    """
    stmt = visible_posts(org_id)
    # 종류는 **범위가 아니라 화면 구분**이다 — 그래서 `visible_posts`(범위 판정 한 곳)가
    # 아니라 여기서 건다. 단건·댓글·첨부는 종류를 안 본다: id 로 여는 글은 어느 게시판에서
    # 왔든 같은 상세 화면이고, 여기에 종류 조건을 더하면 판정이 두 축으로 늘어난다.
    if kind:
        stmt = stmt.where(Post.kind == kind)
    if idea_status:
        stmt = stmt.where(Post.idea_status == idea_status)
    if category:
        stmt = stmt.where(Post.category == category)
    if search:
        like = f"%{search.strip()}%"
        # 제목·본문·작성자 표시명 검색(§18).
        stmt = stmt.where(
            or_(
                Post.title.ilike(like),
                Post.body.ilike(like),
                author_search_clause(like),
            )
        )
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    # 공지 고정은 항상 위. 그다음 정렬 기준(최신순/조회순/공감순).
    order = [Post.is_pinned.desc()]
    if sort == "views":
        order.append(Post.view_count.desc())
    elif sort == "likes":
        # 총 건수를 **센 뒤에** 조인한다. 조인은 정렬을 위한 것이지 걸러 내기 위한 것이
        # 아니라, 세는 질의에 끼면 의미가 흐려진다(그리고 조인 하나 때문에 총 건수가
        # 달라지는 종류의 버그는 페이지 끝에서만 드러나 늦게 발견된다).
        likes = _like_counts_subquery()
        stmt = stmt.outerjoin(likes, likes.c.target_id == Post.id)
        order.append(func.coalesce(likes.c.likes, 0).desc())
    order.append(Post.created_at.desc())
    order.append(Post.id.desc())
    rows = (
        db.execute(stmt.order_by(*order).offset(offset).limit(limit)).scalars().all()
    )
    return list(rows), int(total)


def list_by_author(db: Session, author_user_id: str, *, limit: int) -> list[Post]:
    """작성자 본인의 최근 글(삭제 제외). 내 업무 홈의 게시판 활동 위젯용."""
    stmt = (
        select(Post)
        .where(Post.deleted_at.is_(None), Post.author_user_id == author_user_id)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def author_stats(db: Session, author_user_id: str) -> dict[str, int]:
    """작성자의 게시판 활동 요약: 내 글 수, 내 글 총 조회수, 내 글에 달린 총 댓글 수(삭제 제외)."""
    base = (Post.deleted_at.is_(None), Post.author_user_id == author_user_id)
    post_count = db.execute(select(func.count()).select_from(Post).where(*base)).scalar_one()
    total_views = db.execute(select(func.coalesce(func.sum(Post.view_count), 0)).where(*base)).scalar_one()
    my_post_ids = select(Post.id).where(*base)
    total_comments = db.execute(
        select(func.count()).select_from(Comment).where(
            Comment.deleted_at.is_(None),
            Comment.post_id.in_(my_post_ids),
            Comment.author_user_id != author_user_id,  # '받은 댓글' = 남이 단 것(내 자답 제외)
        )
    ).scalar_one()
    return {
        "post_count": int(post_count),
        "view_count_total": int(total_views),
        "comment_count_received": int(total_comments),
    }


def authors_by_ids(db: Session, user_ids) -> dict[str, User]:
    """{user_id: User} — **한 번의 질의로**.

    이름만으로는 "이 사람이 누구냐"에 답할 수 없다: `users.display_name` 에는 유일성 제약이
    없어서(`app/users/models.py`) 동명이인은 스키마상 정상 상태다. 그래서 게시글·댓글도
    채팅과 같은 신원 묶음(`app/core/people.py::identity`)을 실어야 하고, 그러려면 이름
    두 글자가 아니라 사람 행이 필요하다. 부서·직책은 `lazy="joined"` 라 **추가 질의 없이**
    함께 온다.

    건별로 돌지 않는다 — 상세·목록은 댓글·반응을 쓸 때마다 다시 불리는 경로다.
    """
    ids = [i for i in set(user_ids or ()) if i]
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(ids))).scalars().all()
    return {u.id: u for u in rows}


def author_names(db: Session, user_ids: set[str]) -> dict[str, str]:
    """{user_id: 표시 이름} — 이름만 쓰는 호출부(내 업무 홈 위젯)를 위한 얇은 껍데기.

    질의를 두 벌로 두지 않으려고 `authors_by_ids` 하나에서 갈라 쓴다.
    """
    return {uid: (u.display_name or "") for uid, u in authors_by_ids(db, user_ids).items()}


def comment_count(db: Session, post_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Comment)
            .where(Comment.post_id == post_id, Comment.deleted_at.is_(None))
        ).scalar_one()
    )


def comment_counts(db: Session, post_ids: list[str]) -> dict[str, int]:
    if not post_ids:
        return {}
    rows = db.execute(
        select(Comment.post_id, func.count())
        .where(Comment.post_id.in_(post_ids), Comment.deleted_at.is_(None))
        .group_by(Comment.post_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


def get_comment(
    db: Session, comment_id: str, *, include_deleted: bool = False
) -> Comment | None:
    stmt = select(Comment).where(Comment.id == comment_id)
    if not include_deleted:
        stmt = stmt.where(Comment.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_comments(db: Session, post_id: str) -> list[Comment]:
    """이 함수는 **삭제된 댓글도 돌려준다** — 위 모듈 docstring의 "조회 함수는 기본으로
    deleted_at IS NULL만 돌려준다" 규약의 의도된 예외다. 그 규약은 게시글(Post)처럼
    독립된 자원을 위한 것이다: 지운 글이 목록에서 사라지는 것은 맞다. 그런데 댓글은
    스레드 안의 한 노드이고, 답글(parent_comment_id)이 그 노드를 가리킬 수 있다 —
    행이 조용히 사라지면 답글만 남아 부모 없는 대화가 된다(티켓·문서 댓글과 같은
    이유로 툼스톤을 쓴다, `app/tickets/comments.py`). 호출부(`app/board/router.py::
    _comment_view`)가 삭제된 행을 본문 없는 툼스톤으로 감싼다."""
    rows = (
        db.execute(
            select(Comment)
            .where(Comment.post_id == post_id)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
        )
        .scalars()
        .all()
    )
    return list(rows)


def reactions_for(
    db: Session, target_type: str, target_ids: list[str]
) -> list[Reaction]:
    if not target_ids:
        return []
    rows = (
        db.execute(
            select(Reaction).where(
                Reaction.target_type == target_type,
                Reaction.target_id.in_(target_ids),
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def find_reaction(
    db: Session, *, target_type: str, target_id: str, user_id: str, emoji: str
) -> Reaction | None:
    return db.execute(
        select(Reaction).where(
            Reaction.target_type == target_type,
            Reaction.target_id == target_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
    ).scalar_one_or_none()


def attachments_for(db: Session, post_id: str) -> list[PostAttachment]:
    rows = (
        db.execute(
            select(PostAttachment)
            .where(PostAttachment.post_id == post_id)
            .order_by(PostAttachment.created_at.asc(), PostAttachment.id.asc())
        )
        .scalars()
        .all()
    )
    return list(rows)


def attachment_count(db: Session, post_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(PostAttachment)
            .where(PostAttachment.post_id == post_id)
        ).scalar_one()
    )


def get_attachment(db: Session, attachment_id: str) -> PostAttachment | None:
    return db.execute(
        select(PostAttachment).where(PostAttachment.id == attachment_id)
    ).scalar_one_or_none()
