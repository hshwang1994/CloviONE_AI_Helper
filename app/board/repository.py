"""자유게시판 데이터 접근 (쿼리 전용 — 비즈니스 규칙은 service).

soft delete 규약: 조회 함수는 기본으로 deleted_at IS NULL 만 돌려준다. 삭제된 행을
직접 다뤄야 하는 곳(소유권 확인 등)만 include_deleted=True 를 쓴다.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.board.models import Comment, Post, PostAttachment, Reaction
from app.users.models import User


def get_post(db: Session, post_id: str, *, include_deleted: bool = False) -> Post | None:
    stmt = select(Post).where(Post.id == post_id)
    if not include_deleted:
        stmt = stmt.where(Post.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_posts(
    db: Session,
    *,
    category: str | None,
    search: str | None,
    sort: str,
    offset: int,
    limit: int,
) -> tuple[list[Post], int]:
    stmt = select(Post).where(Post.deleted_at.is_(None))
    if category:
        stmt = stmt.where(Post.category == category)
    if search:
        like = f"%{search.strip()}%"
        # 제목·본문·작성자 표시명 검색(§18). 작성자 검색은 users를 조인해 표시명으로 찾는다.
        author_ids = select(User.id).where(User.display_name.ilike(like))
        stmt = stmt.where(
            or_(
                Post.title.ilike(like),
                Post.body.ilike(like),
                Post.author_user_id.in_(author_ids),
            )
        )
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    # 공지 고정은 항상 위. 그다음 정렬 기준(최신순/조회순).
    order = [Post.is_pinned.desc()]
    if sort == "views":
        order.append(Post.view_count.desc())
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


def author_names(db: Session, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(User.id, User.display_name).where(User.id.in_(user_ids))
    ).all()
    return {uid: name for uid, name in rows}


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
    rows = (
        db.execute(
            select(Comment)
            .where(Comment.post_id == post_id, Comment.deleted_at.is_(None))
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
