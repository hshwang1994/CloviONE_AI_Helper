"""자유게시판 비즈니스 규칙 (소유권·소프트 삭제·한 단계 답글·반응 토글·조회수).

소유권: 작성자 본인 또는 운영자군(operator/admin/system_admin)만 수정·삭제. 공지 고정은
운영자군만. 서버측에서만 판단한다(불변 §5, UI 숨김은 통제가 아님).
"""

from __future__ import annotations

import logging

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.board import repository
from app.board.models import (
    CATEGORIES_BY_KIND,
    IDEA_PROPOSED,
    IDEA_STATUSES,
    IDEA_TRANSITIONS,
    KIND_FREE,
    KIND_IDEA,
    POST_CATEGORIES,
    Comment,
    Post,
    PostAttachment,
    Reaction,
)
from app.board.schemas import CommentUpdate, PostUpdate
# 운영자군 = operator/admin/system_admin (계층 operator 이상). 게시판 중재 권한.
# 정의는 app/core/authz.py 한 곳뿐이다 — 화면마다 다른 '운영자'가 생기지 않게.
from app.core.authz import MODERATOR_ROLES
from app.core.db import is_insert_race
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.users.models import User

logger = logging.getLogger("app.board")


def can_moderate(user: User) -> bool:
    return user.role in MODERATOR_ROLES


def ensure_can_edit(author_user_id: str, user: User) -> None:
    """수정은 **작성자 본인만.** 티켓·문서 댓글(`app/tickets/comments.py`,
    `app/knowledge/comments.py`)과 같은 규칙이다 — 운영자도 남의 문장을 고쳐 쓸 수는
    없다. 남의 말을 바꾸는 것은 지우는 것보다 나쁘다(누가 썼는지는 그대로인데 내용만
    달라진다). 예전에는 이 함수가 삭제까지 함께 검사해 운영자가 남의 글을 조용히
    고쳐 쓸 수 있었다(감사 로그에는 남지만 화면에는 "(수정됨)" 조차 없었다) — 삭제
    권한은 `ensure_can_delete`로 분리했다."""
    if user.id != author_user_id:
        raise ForbiddenError("본인이 작성한 글만 수정할 수 있습니다.")


def ensure_can_delete(author_user_id: str, user: User) -> None:
    """삭제는 작성자 본인 또는 운영자군(모더레이션) — 티켓·문서 댓글과 같은 규칙."""
    if user.id == author_user_id or can_moderate(user):
        return
    raise ForbiddenError("본인이 작성한 글만 삭제할 수 있습니다.")


# ── 게시글 ────────────────────────────────────────────────────────────────
def create_post(
    db: Session,
    *,
    author: User,
    category: str,
    title: str,
    body: str,
    now: datetime,
    kind: str = KIND_FREE,
) -> Post:
    post = Post(
        author_user_id=author.id,
        # RBAC 재감사(2026-08-16)로 발견: 이 줄이 없어서 모든 새 글이 `org_id`를 컬럼
        # 기본값(OrgScopedMixin의 DEFAULT_ORG_ID)에 맡겼다 — 즉 **작성자가 어느 조직이든
        # 상관없이 모든 새 글이 기본 조직 소속으로 저장됐다.** 결과가 양방향이다: 기본
        # 조직이 아닌 사용자는 방금 쓴 자기 글이 목록에서 사라지고(자기 조직으로 걸면
        # 안 걸림), 기본 조직 사람은 다른 조직이 쓴 글까지 그대로 보게 된다(1순위 유출
        # #4가 지키려던 바로 그 경계가 애초에 안 걸리고 있었다). `visible_posts`/
        # `_viewer_org_id`가 맞게 판정해도 저장이 틀리면 소용없다.
        org_id=author.org_id,
        kind=kind,
        # 아이디어는 **제안**에서 시작한다. 자유글은 NULL 이다 — '상태 없음'과 '제안'은
        # 다른 사실이고, 자유글에 값이 있으면 화면이 상태 배지를 그린다.
        idea_status=IDEA_PROPOSED if kind == KIND_IDEA else None,
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


def ensure_category_fits_kind(post: Post, category: str) -> None:
    """수정에서도 종류와 카테고리의 짝을 지킨다.

    생성은 스키마가 짝을 보지만(kind 를 함께 받으므로), 수정은 kind 를 받지 않아 스키마가
    볼 수 없다. 여기서 안 보면 제안 글에 '맛집'을 붙일 수 있고, 그 글은 제안 게시판의 어느
    카테고리 칩으로도 안 걸러진다.
    """
    allowed = CATEGORIES_BY_KIND.get(post.kind or KIND_FREE, POST_CATEGORIES)
    if category not in allowed:
        raise ValidationAppError("이 게시판에서 쓸 수 없는 카테고리입니다.")


def update_post(db: Session, post: Post, data: PostUpdate, *, now: datetime) -> Post:
    if data.category is not None:
        ensure_category_fits_kind(post, data.category)
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


# ── 제안 상태 (아이디어 게시판, 7단계 #1) ─────────────────────────────────
def ensure_idea(post: Post) -> None:
    """상태는 **아이디어에만** 있다. 자유게시글은 상태를 가질 수 없다.

    404 로 답한다: 자유게시글에 대해서는 이 경로가 아예 없는 것이 맞고, 403/409 는
    "여기 뭔가 있긴 하다"를 알려 준다(이 저장소의 범위 규칙과 같은 이유).
    """
    if (post.kind or KIND_FREE) != KIND_IDEA:
        raise NotFoundError("제안 게시글이 아닙니다.")


def ensure_can_change_status(user: User) -> None:
    """상태 변경은 **운영자군**만. 제안은 누구나 하지만 '진행' 은 회사가 하는 약속이다.

    권한 정의를 새로 만들지 않고 게시판이 이미 쓰는 `can_moderate`(operator 이상)를
    그대로 쓴다 — '운영자' 가 화면마다 다른 뜻을 갖기 시작하면 되돌리기 어렵다.
    """
    if not can_moderate(user):
        raise ForbiddenError("제안 상태는 운영자, 관리자, 시스템 관리자만 바꿀 수 있습니다.")


def next_statuses(post: Post) -> list[str]:
    """고를 수 있는 상태. 자유게시글은 빈 목록이다.

    🔴 **전이 사슬을 걷었다** (사용자 결정, 2026-09-03). 예전에는 제안→검토중→진행처럼
    정해진 길로만 갈 수 있었고, 그 근거는 "'진행' 은 티켓을 만든다 — 되돌릴 수 없는
    쪽이라 더 그렇다" 였다. **그 티켓 생성이 없어졌으므로 근거도 없어졌다.**

    남은 것은 라벨 하나를 고르는 일이고, 사용자는 그것을 티켓처럼 다루기를 원한다 —
    티켓의 상태도 계획에서 곧장 완료로 갈 수 있다. 두 단계를 거쳐야 완료로 갈 수 있는
    제안 게시판이 오히려 예외였다.

    노출 순서는 `IDEA_STATUSES`(일이 흘러가는 순서)를 따른다.
    """
    if (post.kind or KIND_FREE) != KIND_IDEA:
        return []
    return list(IDEA_STATUSES)


def ensure_transition_allowed(current: str | None, target: str) -> None:
    """어휘 안의 값이면 어디로든 갈 수 있다(위 `next_statuses` 의 이유).

    값 자체의 검증은 여기가 아니라 스키마가 한다(`IdeaStatusUpdate._status`) — 어휘 밖
    문자열은 요청이 몸통을 읽는 자리에서 이미 막힌다. 이 함수는 호출부의 이름을 남겨
    두려고 둔다: 나중에 다시 제한이 필요해지면 붙일 자리가 한 곳이다.
    """
    return None


def change_idea_status(
    db: Session,
    post: Post,
    *,
    actor: User,
    status: str,
    now: datetime,
    outbound=None,
    settings=None,
    repo=None,
) -> Post:
    """제안 상태를 바꾼다.

    🔴 **여기서 업무 티켓을 만들지 않는다** (사용자 결정, 2026-09-03).

    예전에는 '진행' 으로 넘어갈 때 프로젝트를 받아 티켓을 만들어 연결했고, 티켓 생성이
    실패하면 상태 변경까지 함께 되돌렸다. 그 설계 자체는 일관됐지만 전제가 틀렸다 —
    이 게시판은 **ClovirAssist 제품 자체에 대한 기능 제안**이다. 고객 프로젝트의 업무
    티켓과 섞이면 프로젝트 보드에 제품 요청이 쌓이고, 그 둘은 담당자도 우선순위 기준도
    다르다. 그래서 티켓 축을 통째로 걷었다(화면·스키마·여기).

    `ticket_page_id` 열은 **남긴다.** 이미 연결된 옛 제안이 있고, 열을 지우는 것은
    마이그레이션이며 되돌릴 수 없는 이력 삭제다. 새로 쓰지 않을 뿐이다.
    """
    ensure_idea(post)
    ensure_can_change_status(actor)
    ensure_transition_allowed(post.idea_status, status)

    post.idea_status = status
    post.updated_at = now
    db.flush()
    _notify_idea_status_change(db, post=post, actor=actor, status=status, now=now)
    return post


def _notify_idea_status_change(
    db: Session, *, post: Post, actor: User, status: str, now: datetime
) -> None:
    """제안 상태가 바뀌면 제안자에게 알린다 (`_notify_post_comment` 와 같은 원칙, N2).

    댓글에는 알림이 있는데(N2) 상태 전환에는 없었다 — 제안자는 자기 글이 검토중/진행/완료/
    보류로 넘어간 것을 `/ideas` 를 스스로 열어야만 알았다. 담당자가 바뀐 자기 티켓은
    `ticket_assigned` 로 알림이 가는데, 자기가 낸 제안이 실제 일(티켓)이 되는 순간은
    조용했다는 뜻이기도 하다.

    자기 자신은 뺀다(운영자가 자기 제안을 스스로 진행시켜도 배지가 켜지지 않게) —
    다른 모든 알림 호출부와 같은 원칙이다.

    실패해도 상태 전환은 남는다 — 알림은 본 작업보다 약한 관심사다(댓글 알림과 같은 규약).
    """
    try:
        if post.author_user_id is None or post.author_user_id == actor.id:
            return

        from app.notifications.service import notify_user

        notify_user(
            db, post.author_user_id, type_="idea_status_changed",
            title=f"제안 상태 변경: {status}",
            body=(post.title or "")[:200],
            related=("board_post", post.id), now=now,
        )
    except Exception:  # noqa: BLE001 — 알림이 상태 전환을 막으면 안 된다
        logger.exception("제안 상태 알림에 실패했다 (post_id=%s)", post.id)


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
    _notify_post_comment(db, post=post, author=author, parent_comment_id=parent_comment_id, now=now)
    return comment


def _notify_post_comment(db: Session, *, post: Post, author: User, parent_comment_id, now) -> None:
    """내 글(또는 내 댓글)에 답이 달리면 알린다 (N2).

    `app/board/` 전체에 `notify` 문자열이 **0건**이었다 — 내 게시글에 댓글이 달려도 알 방법이
    글을 다시 열어 보는 것뿐이었다. 만들어지는 알림 14종이 전부 관리·운영 이벤트 아니면
    채팅이고, **사람이 실제로 협업하는 두 축(티켓·게시판)이 통째로 조용했다.**

    ## 누구에게

    글쓴이. 답글이면 **부모 댓글 작성자에게도** — 답글은 그 사람에게 하는 말이다.
    자기 자신은 뺀다(내가 쓴 것을 나에게 알리면 배지가 늘 켜져 있다).

    ## 실패해도 댓글은 남는다

    알림은 본 작업(댓글)보다 약한 관심사다. 그 반대로 만들면 알림 표 하나가 협업을 멈춘다.
    """
    try:
        targets = {post.author_user_id}
        if parent_comment_id is not None:
            parent = repository.get_comment(db, parent_comment_id)
            if parent is not None:
                targets.add(parent.author_user_id)
        targets.discard(author.id)
        targets.discard(None)
        if not targets:
            return

        from app.notifications.service import notify_user

        for uid in targets:
            notify_user(
                db, uid, type_="board_comment",
                title=f"게시글에 새 댓글: {author.display_name}",
                body=(post.title or "")[:200],
                related=("board_post", post.id), now=now,
            )
    except Exception:  # noqa: BLE001 — 알림이 댓글 저장을 막으면 안 된다
        logger.exception("게시글 댓글 알림에 실패했다 (post_id=%s)", post.id)


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
    except (IntegrityError, OperationalError) as exc:
        if not is_insert_race(exc):
            raise
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
