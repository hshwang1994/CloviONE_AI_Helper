"""자유게시판 API (팀 공간 §18).

순수 내부 기능 — 외부 호출 없음. 조회는 인증만, 상태변경은 CSRF + 소유권(작성자 또는
운영자군). 공지 고정·타인 글 수정은 운영자군만. IDOR는 소유권 검사로 차단, 감사는
성공 경로에서만 남긴다(실패 시 get_db 롤백으로 감사도 함께 취소된다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.board import repository, service
from app.board.models import (
    CATEGORY_FOOD,
    CATEGORY_FREE,
    CATEGORY_INFO,
    CATEGORY_NOTICE,
    CATEGORY_QUESTION,
    REACTION_EMOJIS,
    TARGET_COMMENT,
    TARGET_POST,
    Comment,
    Post,
)
from app.board.schemas import CommentCreate, CommentUpdate, PostCreate, PostUpdate, ReactionInput
from app.core import uploads
from app.core.audit import record_audit_from_request
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import ForbiddenError, NotFoundError
from app.core.feature_flags import load_feature_flags
from app.core.pagination import PageParams
from app.users.models import User

# 목록 필터·작성 폼에서 쓰는 카테고리 노출 순서(§18의 나열 순서).
CATEGORY_ORDER = [
    CATEGORY_FREE,
    CATEGORY_QUESTION,
    CATEGORY_INFO,
    CATEGORY_FOOD,
    CATEGORY_NOTICE,
]
EXCERPT_LEN = 140


def require_board_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("board_enabled", True):
        raise NotFoundError("자유게시판 기능이 비활성화되어 있습니다.")


router = APIRouter(
    prefix="/api/board",
    tags=["board"],
    dependencies=[Depends(require_board_enabled)],
)


# ── 직렬화 ──────────────────────────────────────────────────────────────────
def _post_summary(post: Post, *, author_name: str, comments: int, me: User) -> dict:
    body = post.body or ""
    excerpt = body[:EXCERPT_LEN]
    return {
        "id": post.id,
        "category": post.category,
        "title": post.title,
        "excerpt": excerpt,
        "excerpt_truncated": len(body) > EXCERPT_LEN,
        "author_user_id": post.author_user_id,
        "author_name": author_name,
        "is_pinned": post.is_pinned,
        "view_count": post.view_count,
        "comment_count": comments,
        "can_edit": me.id == post.author_user_id or service.can_moderate(me),
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


def _attachment_view(att) -> dict:
    return {
        "id": att.id,
        "filename": att.filename,
        "media_type": att.media_type,
        "size_bytes": att.size_bytes,
        "url": f"/api/board/attachments/{att.id}",
        "is_image": att.media_type.startswith("image/"),
    }


def _comment_view(c: Comment, *, author_name: str, reactions: list[dict], me: User) -> dict:
    return {
        "id": c.id,
        "post_id": c.post_id,
        "parent_comment_id": c.parent_comment_id,
        "author_user_id": c.author_user_id,
        "author_name": author_name,
        "body": c.body,
        "reactions": reactions,
        "can_edit": me.id == c.author_user_id or service.can_moderate(me),
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def _post_detail(db: Session, post: Post, me: User) -> dict:
    comments = repository.list_comments(db, post.id)
    author_ids = {post.author_user_id} | {c.author_user_id for c in comments}
    names = repository.author_names(db, author_ids)

    post_reacts = repository.reactions_for(db, TARGET_POST, [post.id])
    comment_reacts = repository.reactions_for(db, TARGET_COMMENT, [c.id for c in comments])
    by_comment: dict[str, list] = {}
    for r in comment_reacts:
        by_comment.setdefault(r.target_id, []).append(r)

    attachments = repository.attachments_for(db, post.id)
    return {
        "id": post.id,
        "category": post.category,
        "title": post.title,
        "body": post.body or "",
        "author_user_id": post.author_user_id,
        "author_name": names.get(post.author_user_id, "(알 수 없음)"),
        "is_pinned": post.is_pinned,
        "view_count": post.view_count,
        "can_edit": me.id == post.author_user_id or service.can_moderate(me),
        "can_moderate": service.can_moderate(me),
        "reactions": service.reaction_summary(post_reacts, my_user_id=me.id),
        "attachments": [_attachment_view(a) for a in attachments],
        "comments": [
            _comment_view(
                c,
                author_name=names.get(c.author_user_id, "(알 수 없음)"),
                reactions=service.reaction_summary(
                    by_comment.get(c.id, []), my_user_id=me.id
                ),
                me=me,
            )
            for c in comments
        ],
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


def _get_post_or_404(db: Session, post_id: str) -> Post:
    post = repository.get_post(db, post_id)
    if post is None:
        raise NotFoundError("게시글을 찾을 수 없습니다.")
    return post


def _get_comment_or_404(db: Session, comment_id: str) -> Comment:
    comment = repository.get_comment(db, comment_id)
    if comment is None:
        raise NotFoundError("댓글을 찾을 수 없습니다.")
    return comment


# ── 게시글 ──────────────────────────────────────────────────────────────────
@router.get("/meta")
def board_meta(user: User = Depends(get_current_user)):
    """작성 폼·필터가 쓰는 상수(카테고리·이모지)와 현재 사용자의 중재 권한."""
    return {
        "categories": CATEGORY_ORDER,
        "reaction_emojis": list(REACTION_EMOJIS),
        "can_moderate": service.can_moderate(user),
    }


@router.get("/mine")
def my_activity(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    limit: int = Query(default=5, ge=1, le=20),
):
    """내 업무 홈의 게시판 활동 위젯 — 본인이 쓴 최근 글 + 요약(글 수·받은 댓글·조회수)."""
    posts = repository.list_by_author(db, me.id, limit=limit)
    counts = repository.comment_counts(db, [p.id for p in posts])
    items = [
        {
            "id": p.id,
            "title": p.title,
            "category": p.category,
            "is_pinned": p.is_pinned,
            "comment_count": counts.get(p.id, 0),
            "view_count": p.view_count,
            "created_at": p.created_at.isoformat(),
        }
        for p in posts
    ]
    return {"items": items, "summary": repository.author_stats(db, me.id)}


@router.get("/posts")
def list_posts(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    page: PageParams = Depends(),
    category: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="recent"),
):
    sort = sort if sort in {"recent", "views"} else "recent"
    cat = category if category in CATEGORY_ORDER else None
    rows, total = repository.list_posts(
        db, category=cat, search=q, sort=sort, offset=page.offset, limit=page.page_size
    )
    names = repository.author_names(db, {r.author_user_id for r in rows})
    counts = repository.comment_counts(db, [r.id for r in rows])
    return {
        "items": [
            _post_summary(
                r,
                author_name=names.get(r.author_user_id, "(알 수 없음)"),
                comments=counts.get(r.id, 0),
                me=me,
            )
            for r in rows
        ],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        "can_moderate": service.can_moderate(me),
    }


@router.post("/posts", dependencies=[Depends(require_csrf)])
def create_post(
    request: Request,
    payload: PostCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    post = service.create_post(
        db,
        author=me,
        category=payload.category,
        title=payload.title,
        body=payload.body,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request,
        db,
        action="board.post.create",
        object_type="board_post",
        object_id=post.id,
        after={"category": post.category, "title": post.title},
    )
    return {"post": _post_detail(db, post, me)}


@router.get("/posts/{post_id}")
def get_post(
    post_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    # 조회는 조회수를 올리지 않는다. 예전엔 여기서 increment_view를 불러, 반응·댓글 등
    # 상태변경 뒤 상세를 다시 불러올 때마다(refetch=GET) 조회수가 부풀었다. 조회 집계는
    # 아래 전용 /view 핑으로만 한다(진입 시 한 번).
    post = _get_post_or_404(db, post_id)
    return {"post": _post_detail(db, post, me)}


@router.post("/posts/{post_id}/view", dependencies=[Depends(require_csrf)])
def mark_viewed(
    post_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """상세 진입 시 프런트가 한 번 호출해 조회수를 올린다(GET refetch로는 안 오른다)."""
    post = _get_post_or_404(db, post_id)
    service.increment_view(db, post)
    return {"ok": True, "view_count": post.view_count}


@router.patch("/posts/{post_id}", dependencies=[Depends(require_csrf)])
def update_post(
    request: Request,
    post_id: str,
    payload: PostUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    post = _get_post_or_404(db, post_id)
    service.ensure_can_edit(post.author_user_id, me)
    before = {"category": post.category, "title": post.title}
    service.update_post(db, post, payload, now=request.app.state.clock.now())
    record_audit_from_request(
        request,
        db,
        action="board.post.update",
        object_type="board_post",
        object_id=post.id,
        before=before,
        after={"category": post.category, "title": post.title},
    )
    return {"post": _post_detail(db, post, me)}


@router.delete("/posts/{post_id}", dependencies=[Depends(require_csrf)])
def delete_post(
    request: Request,
    post_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    post = _get_post_or_404(db, post_id)
    service.ensure_can_edit(post.author_user_id, me)
    service.soft_delete_post(db, post, now=request.app.state.clock.now())
    record_audit_from_request(
        request,
        db,
        action="board.post.delete",
        object_type="board_post",
        object_id=post.id,
        before={"title": post.title},
    )
    return {"ok": True}


@router.post("/posts/{post_id}/pin", dependencies=[Depends(require_csrf)])
def pin_post(
    request: Request,
    post_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    pinned: bool = Query(default=True),
):
    if not service.can_moderate(me):
        raise ForbiddenError("공지 고정은 운영자만 할 수 있습니다.")
    post = _get_post_or_404(db, post_id)
    service.set_pinned(db, post, pinned=pinned, now=request.app.state.clock.now())
    record_audit_from_request(
        request,
        db,
        action="board.post.pin",
        object_type="board_post",
        object_id=post.id,
        after={"is_pinned": pinned},
    )
    return {"post": _post_detail(db, post, me)}


# ── 댓글 ────────────────────────────────────────────────────────────────────
@router.post("/posts/{post_id}/comments", dependencies=[Depends(require_csrf)])
def create_comment(
    request: Request,
    post_id: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    post = _get_post_or_404(db, post_id)
    comment = service.create_comment(
        db,
        post=post,
        author=me,
        body=payload.body,
        parent_comment_id=payload.parent_comment_id,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request,
        db,
        action="board.comment.create",
        object_type="board_comment",
        object_id=comment.id,
        after={"post_id": post.id},
    )
    return {"post": _post_detail(db, post, me)}


@router.patch("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def update_comment(
    request: Request,
    comment_id: str,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    comment = _get_comment_or_404(db, comment_id)
    service.ensure_can_edit(comment.author_user_id, me)
    service.update_comment(db, comment, payload, now=request.app.state.clock.now())
    record_audit_from_request(
        request,
        db,
        action="board.comment.update",
        object_type="board_comment",
        object_id=comment.id,
    )
    post = _get_post_or_404(db, comment.post_id)
    return {"post": _post_detail(db, post, me)}


@router.delete("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def delete_comment(
    request: Request,
    comment_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    comment = _get_comment_or_404(db, comment_id)
    service.ensure_can_edit(comment.author_user_id, me)
    service.soft_delete_comment(db, comment, now=request.app.state.clock.now())
    record_audit_from_request(
        request,
        db,
        action="board.comment.delete",
        object_type="board_comment",
        object_id=comment.id,
    )
    return {"ok": True}


# ── 반응(이모지) ────────────────────────────────────────────────────────────
def _validate_reaction_target(db: Session, target_type: str, target_id: str) -> None:
    if target_type == TARGET_POST:
        if repository.get_post(db, target_id) is None:
            raise NotFoundError("게시글을 찾을 수 없습니다.")
    else:
        comment = repository.get_comment(db, target_id)
        # 댓글이 살아 있어도 그 부모 글이 삭제됐으면 반응을 받지 않는다(삭제된 글 아래
        # 댓글에 반응이 쌓이는 고아 데이터 방지 — get_post는 삭제 글을 제외한다).
        if comment is None or repository.get_post(db, comment.post_id) is None:
            raise NotFoundError("댓글을 찾을 수 없습니다.")


@router.post("/reactions", dependencies=[Depends(require_csrf)])
def add_reaction(
    request: Request,
    payload: ReactionInput,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    _validate_reaction_target(db, payload.target_type, payload.target_id)
    service.add_reaction(
        db,
        target_type=payload.target_type,
        target_id=payload.target_id,
        user_id=me.id,
        emoji=payload.emoji,
        now=request.app.state.clock.now(),
    )
    return {"ok": True}


@router.delete("/reactions", dependencies=[Depends(require_csrf)])
def remove_reaction(
    payload: ReactionInput,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    service.remove_reaction(
        db,
        target_type=payload.target_type,
        target_id=payload.target_id,
        user_id=me.id,
        emoji=payload.emoji,
    )
    return {"ok": True}


# ── 첨부 (업로드·서빙) ────────────────────────────────────────────────────────
@router.post("/posts/{post_id}/attachments", dependencies=[Depends(require_csrf)])
def upload_attachment(
    request: Request,
    post_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    post = _get_post_or_404(db, post_id)
    service.ensure_can_edit(post.author_user_id, me)
    service.ensure_attachment_capacity(
        db, post.id, max_count=uploads.MAX_ATTACHMENTS_PER_POST
    )
    # sync 핸들러에서는 UploadFile의 내부 파일 객체를 직접 읽는다(await 불필요, 불변 §1).
    content = file.file.read(uploads.MAX_UPLOAD_BYTES + 1)
    stored_name, media_type, size, display_name = uploads.save_upload(
        request.app.state.settings.data_dir,
        post.id,
        filename=file.filename or "file",
        content=content,
    )
    att = service.register_attachment(
        db,
        post_id=post.id,
        filename=display_name,
        stored_name=stored_name,
        media_type=media_type,
        size_bytes=size,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request,
        db,
        action="board.attachment.upload",
        object_type="board_attachment",
        object_id=att.id,
        after={"post_id": post.id, "media_type": media_type, "size_bytes": size},
    )
    return {"attachment": _attachment_view(att)}


@router.get("/attachments/{attachment_id}")
def serve_attachment(
    request: Request,
    attachment_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    att = repository.get_attachment(db, attachment_id)
    if att is None:
        raise NotFoundError("첨부를 찾을 수 없습니다.")
    # 부모 글이 삭제됐으면(운영자가 내린 부적절 콘텐츠 등) 첨부도 더는 서빙하지 않는다 —
    # 예전엔 글은 404여도 첨부 URL을 쥔 사람은 계속 받을 수 있었다(삭제가 접근을 못 막음).
    if repository.get_post(db, att.post_id) is None:
        raise NotFoundError("첨부를 찾을 수 없습니다.")
    path = uploads.attachment_path(
        request.app.state.settings.data_dir, att.post_id, att.stored_name
    )
    if path is None:
        raise NotFoundError("첨부 파일을 찾을 수 없습니다.")
    # nosniff + inline. 서버가 판정·저장한 media_type만 신뢰한다. 실행 불가.
    return FileResponse(
        str(path),
        media_type=att.media_type,
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )
