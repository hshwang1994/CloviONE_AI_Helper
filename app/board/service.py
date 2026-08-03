"""자유게시판 비즈니스 규칙 (소유권·소프트 삭제·한 단계 답글·반응 토글·조회수).

소유권: 작성자 본인 또는 운영자군(operator/admin/system_admin)만 수정·삭제. 공지 고정은
운영자군만. 서버측에서만 판단한다(불변 §5, UI 숨김은 통제가 아님).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.board import repository
from app.board.models import (
    Comment,
    Post,
    PostAttachment,
    Reaction,
)
from app.board.schemas import CommentUpdate, PostUpdate
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
# 운영자군 = operator/admin/system_admin (계층 operator 이상). 게시판 중재 권한.
# 정의는 app/core/authz.py 한 곳뿐이다 — 화면마다 다른 '운영자'가 생기지 않게.
from app.core.authz import MODERATOR_ROLES
from app.users.models import User


def can_moderate(user: User) -> bool:
    return user.role in MODERATOR_ROLES


def ensure_can_edit(author_user_id: str, user: User) -> None:
    """작성자 본인 또는 운영자군만 수정·삭제할 수 있다. 아니면 403."""
    if user.id == author_user_id or can_moderate(user):
        return
    raise ForbiddenError("본인이 작성한 글만 수정하거나 삭제할 수 있습니다.")


# ── 게시글 ────────────────────────────────────────────────────────────────
def create_post(
    db: Session, *, author: User, category: str, title: str, body: str, now: datetime
) -> Post:
    post = Post(
        author_user_id=author.id,
        category=category,
        title=title,
        body=body or "",
        is_pinned=False,
        view_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(post)
    db.flush()
    return post


def update_post(db: Session, post: Post, data: PostUpdate, *, now: datetime) -> Post:
    if data.category is not None:
        post.category = data.category
    if data.title is not None:
        post.title = data.title
    if data.body is not None:
        post.body = data.body
    post.updated_at = now
    db.flush()
    return post


def soft_delete_post(db: Session, post: Post, *, now: datetime) -> None:
    post.deleted_at = now
    db.flush()


def set_pinned(db: Session, post: Post, *, pinned: bool, now: datetime) -> Post:
    post.is_pinned = pinned
    post.updated_at = now
    db.flush()
    return post


def increment_view(db: Session, post: Post) -> None:
    """조회수 원자적 증가 — 동시 조회에서 값이 유실되지 않도록 SQL 레벨에서 +1 하고,
    응답에 쓰도록 DB에서 다시 읽어 온다(수동 +1을 더하면 세션 동기화와 겹쳐 두 번 센다)."""
    db.execute(
        update(Post).where(Post.id == post.id).values(view_count=Post.view_count + 1)
    )
    db.flush()
    db.refresh(post)


# ── 댓글 ──────────────────────────────────────────────────────────────────
def create_comment(
    db: Session,
    *,
    post: Post,
    author: User,
    body: str,
    parent_comment_id: str | None,
    now: datetime,
) -> Comment:
    if parent_comment_id is not None:
        parent = repository.get_comment(db, parent_comment_id)
        if parent is None or parent.post_id != post.id:
            raise NotFoundError("답글을 달 댓글을 찾을 수 없습니다.")
        # 한 단계 답글만(§18) — 답글에 다시 답글을 달 수 없다.
        if parent.parent_comment_id is not None:
            raise ValidationAppError("답글에는 다시 답글을 달 수 없습니다.")
    comment = Comment(
        post_id=post.id,
        author_user_id=author.id,
        parent_comment_id=parent_comment_id,
        body=body,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    db.flush()
    return comment


def update_comment(
    db: Session, comment: Comment, data: CommentUpdate, *, now: datetime
) -> Comment:
    comment.body = data.body
    comment.updated_at = now
    db.flush()
    return comment


def soft_delete_comment(db: Session, comment: Comment, *, now: datetime) -> None:
    comment.deleted_at = now
    # 한 단계 답글도 함께 숨긴다. 부모만 지우면 그 답글이 어느 최상위 댓글에도 안 붙는
    # 고아가 되어 화면엔 안 보이면서 댓글 수에만 남는다('댓글 1'인데 목록은 비어 보임).
    # 부모 댓글 삭제는 그 답글까지 삭제로 본다(§18 한 단계 구조라 손자 답글은 없다).
    db.execute(
        update(Comment)
        .where(Comment.parent_comment_id == comment.id, Comment.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    db.flush()


# ── 반응(이모지) ──────────────────────────────────────────────────────────
def add_reaction(
    db: Session, *, target_type: str, target_id: str, user_id: str, emoji: str, now: datetime
) -> Reaction:
    """멱등 — 이미 같은 반응이 있으면 그대로 돌려준다.

    동시 요청(두 탭·두 기기)이 같은 반응을 동시에 넣으면 check-then-insert 사이에 둘 다
    통과해 uq_board_reaction 유니크 위반 → IntegrityError → 500이 날 수 있다. 삽입을
    SAVEPOINT로 감싸고 위반을 흡수해 이미 들어간 행을 돌려준다(레포 관례: jobs/repository,
    scheduler와 동일). 저장은 정확히 한 번만 남는다.
    """
    existing = repository.find_reaction(
        db, target_type=target_type, target_id=target_id, user_id=user_id, emoji=emoji
    )
    if existing is not None:
        return existing
    row = Reaction(
        target_type=target_type,
        target_id=target_id,
        user_id=user_id,
        emoji=emoji,
        created_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        # 경쟁에서 진 쪽 — 상대가 먼저 넣은 행을 다시 읽어 돌려준다.
        return repository.find_reaction(
            db, target_type=target_type, target_id=target_id, user_id=user_id, emoji=emoji
        )


def remove_reaction(
    db: Session, *, target_type: str, target_id: str, user_id: str, emoji: str
) -> bool:
    existing = repository.find_reaction(
        db, target_type=target_type, target_id=target_id, user_id=user_id, emoji=emoji
    )
    if existing is None:
        return False
    db.delete(existing)
    db.flush()
    return True


def reaction_summary(
    reactions: list[Reaction], *, my_user_id: str
) -> list[dict]:
    """대상별 반응 목록을 {emoji, count, mine} 배열로 집계한다(이모지 등장 순)."""
    order: list[str] = []
    counts: dict[str, int] = {}
    mine: set[str] = set()
    for r in reactions:
        if r.emoji not in counts:
            counts[r.emoji] = 0
            order.append(r.emoji)
        counts[r.emoji] += 1
        if r.user_id == my_user_id:
            mine.add(r.emoji)
    return [
        {"emoji": e, "count": counts[e], "mine": e in mine} for e in order
    ]


# ── 첨부 (메타 등록; 파일 저장은 app/core/uploads.py) ───────────────────────
def register_attachment(
    db: Session,
    *,
    post_id: str,
    filename: str,
    stored_name: str,
    media_type: str,
    size_bytes: int,
    now: datetime,
) -> PostAttachment:
    row = PostAttachment(
        post_id=post_id,
        filename=filename,
        stored_name=stored_name,
        media_type=media_type,
        size_bytes=size_bytes,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def ensure_attachment_capacity(db: Session, post_id: str, *, max_count: int) -> None:
    if repository.attachment_count(db, post_id) >= max_count:
        raise ConflictError(f"첨부는 게시글당 최대 {max_count}개까지 올릴 수 있습니다.")
