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
    IDEA_CATEGORY_ETC,
    IDEA_CATEGORY_FEATURE,
    IDEA_CATEGORY_PERF,
    IDEA_CATEGORY_UX,
    IDEA_STATUSES,
    KIND_FREE,
    KIND_IDEA,
    POST_KINDS,
    REACTION_EMOJIS,
    TARGET_COMMENT,
    TARGET_POST,
    Comment,
    Post,
)
from app.board.schemas import (
    CommentCreate,
    CommentUpdate,
    IdeaStatusUpdate,
    PostCreate,
    PostUpdate,
    ReactionInput,
)
from app.core import people, uploads
from app.core.audit import audit_failure_on_exception, record_audit_from_request
from app.core.deps import get_current_user, get_db, require_csrf
from app.core.errors import ForbiddenError, NotFoundError
from app.core.feature_flags import load_feature_flags
from app.core.pagination import PageParams
from app.users.models import User
from app.settings.gate import block_if_maintenance

# 목록 필터·작성 폼에서 쓰는 카테고리 노출 순서(§18의 나열 순서).
CATEGORY_ORDER = [
    CATEGORY_FREE,
    CATEGORY_QUESTION,
    CATEGORY_INFO,
    CATEGORY_FOOD,
    CATEGORY_NOTICE,
]
# 제안 게시판의 카테고리 노출 순서.
IDEA_CATEGORY_ORDER = [
    IDEA_CATEGORY_FEATURE,
    IDEA_CATEGORY_UX,
    IDEA_CATEGORY_PERF,
    IDEA_CATEGORY_ETC,
]
CATEGORY_ORDER_BY_KIND: dict[str, list[str]] = {
    KIND_FREE: CATEGORY_ORDER,
    KIND_IDEA: IDEA_CATEGORY_ORDER,
}
EXCERPT_LEN = 140


def _kind_of(value: str | None) -> str:
    """쿼리로 온 종류를 화이트리스트로 떨어뜨린다. 모르는 값은 자유게시판이다.

    거절하지 않고 기본값으로 떨어뜨리는 이유: 남이 준 링크가 조금 망가졌다고 화면이
    오류로 죽는 것보다 기본 게시판이라도 보이는 편이 낫다(lib/useQueryState.js 와 같은 판단).
    """
    return value if value in POST_KINDS else KIND_FREE


def require_board_enabled(request: Request) -> None:
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("board_enabled", True):
        raise NotFoundError("자유게시판 기능이 비활성화되어 있습니다.")


router = APIRouter(
    prefix="/api/board",
    tags=["board"],
    dependencies=[Depends(require_board_enabled), Depends(block_if_maintenance)],
)


# ── 직렬화 ──────────────────────────────────────────────────────────────────
def _people_of(db: Session, authors: dict[str, User]) -> dict[str, dict]:
    """{user_id: 신원} — 글·댓글에 나오는 사람을 **한 명당 한 줄만** 실어 보낸다.

    사용자 지시(#13): *"게시글과 댓글에는 작성자의 부서·팀·직책을 함께 표시한다"*.
    게시판은 `author_name` 하나만 주고 있었는데 표시 이름에는 유일성 제약이 없어서
    (`app/users/models.py`) 동명이인이면 '작성자' 칸이 **아무것도 답하지 못한다**.
    채팅(`app/team_chat/router.py`)이 이미 같은 모양으로 답하고 있으므로 신원 조각을
    만드는 자리는 늘리지 않고 `core/people.identity` 를 그대로 쓴다.

    사진도 여기서 함께 온다(#8). 서빙 경로(`/api/profile/avatar/{user_id}`)는 **이미 전
    직원 대상**이라, 없던 것은 남의 주소를 알려 주는 이 payload 하나뿐이었다.

    댓글마다 신원을 되풀이하지 않고 uid 로 찾아 쓰게 하는 이유는 두 가지다: 같은 사람이
    댓글 수만큼 반복되면 응답이 부풀고, 상세는 댓글·반응을 쓸 때마다 다시 불린다.
    질의는 작성자 수와 무관하게 셋뿐이다(사람 1 + 조직명 1 + 사진 1).
    """
    org_names = people.org_name_map(db)
    avatars = people.avatar_map(db, authors.keys())
    from app.core.org_tree import DeptTree

    tree = DeptTree.load(db)
    return {uid: people.identity(u, org_names, avatars, tree) for uid, u in authors.items()}


def _idea_fields(post: Post) -> dict:
    """상태·티켓 연결은 **아이디어일 때만** 실린다.

    자유게시글에 값이 실려 나가면 화면이 상태 배지를 그린다. 화면에도 같은 판정을 넣어
    두었지만(그물 두 겹), 애초에 보내지 않는 것이 먼저다 — 화면은 하나가 아니고, 다음에
    이 응답을 읽는 화면(검색·위젯)이 같은 규칙을 기억하리라는 보장이 없다.
    """
    if (post.kind or KIND_FREE) != KIND_IDEA:
        return {"kind": KIND_FREE, "idea_status": None, "ticket_page_id": None}
    return {
        "kind": KIND_IDEA,
        "idea_status": post.idea_status,
        "ticket_page_id": post.ticket_page_id,
    }


def _post_summary(
    post: Post, *, author_name: str, comments: int, me: User, likes: int = 0
) -> dict:
    body = post.body or ""
    excerpt = body[:EXCERPT_LEN]
    return {
        "id": post.id,
        **_idea_fields(post),
        # 공감 수는 종류와 무관하게 싣는다 — 자유게시판도 같은 👍 반응을 쓰고, 값이 있는
        # 것과 없는 것을 화면이 구분해야 할 이유가 없다.
        "like_count": likes,
        "category": post.category,
        "title": post.title,
        "excerpt": excerpt,
        "excerpt_truncated": len(body) > EXCERPT_LEN,
        "author_user_id": post.author_user_id,
        "author_name": author_name,
        "is_pinned": post.is_pinned,
        "view_count": post.view_count,
        "comment_count": comments,
        # 수정은 작성자 본인만, 삭제는 작성자 또는 운영자군 — 두 값이 다른 이유는
        # `service.ensure_can_edit`/`ensure_can_delete` 의 docstring 참조.
        "can_edit": me.id == post.author_user_id,
        "can_delete": me.id == post.author_user_id or service.can_moderate(me),
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
    """댓글 한 건의 API 응답. 삭제된 댓글은 **본문 없는 툼스톤**으로 나간다 —
    `app/tickets/comments.py::comment_view`·`app/team_docs/comments.py`와 같은 규약
    (`docs/DECISIONS.md` 참조). 예전에는 목록 쿼리가 삭제된 행 자체를 걸러냈다 —
    행이 조용히 사라지면 그 답글(자식)만 남아 부모 없는 대화처럼 보였다."""
    deleted = c.deleted_at is not None
    return {
        "id": c.id,
        "post_id": c.post_id,
        "parent_comment_id": c.parent_comment_id,
        "author_user_id": c.author_user_id,
        "author_name": author_name,
        # 본문은 살아 있는 댓글에만 — 지운 내용을 계속 내려보내면 삭제가 아니다.
        "body": "" if deleted else c.body,
        "deleted": deleted,
        "reactions": [] if deleted else reactions,
        # 수정은 작성자 본인만, 삭제는 작성자 또는 운영자군 — 이미 지운 댓글은 둘 다 불가.
        "can_edit": (not deleted) and me.id == c.author_user_id,
        "can_delete": (not deleted) and (me.id == c.author_user_id or service.can_moderate(me)),
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def _post_detail(db: Session, post: Post, me: User) -> dict:
    comments = repository.list_comments(db, post.id)
    author_ids = {post.author_user_id} | {c.author_user_id for c in comments}
    # 글쓴이와 댓글 작성자를 **한 번에** 읽는다 — 이름과 신원을 따로 조회하면 같은 사람을
    # 두 번 읽게 되고, 상세는 댓글·반응을 쓸 때마다 다시 불리는 경로다.
    authors = repository.authors_by_ids(db, author_ids)
    names = {uid: (u.display_name or "") for uid, u in authors.items()}

    post_reacts = repository.reactions_for(db, TARGET_POST, [post.id])
    comment_reacts = repository.reactions_for(db, TARGET_COMMENT, [c.id for c in comments])
    by_comment: dict[str, list] = {}
    for r in comment_reacts:
        by_comment.setdefault(r.target_id, []).append(r)

    attachments = repository.attachments_for(db, post.id)
    return {
        "id": post.id,
        **_idea_fields(post),
        "like_count": repository.like_counts(db, [post.id]).get(post.id, 0),
        "category": post.category,
        "title": post.title,
        "body": post.body or "",
        "author_user_id": post.author_user_id,
        "author_name": names.get(post.author_user_id, "(알 수 없음)"),
        "is_pinned": post.is_pinned,
        "view_count": post.view_count,
        # 수정은 작성자 본인만, 삭제는 작성자 또는 운영자군 — `_post_summary`와 같은 분리.
        "can_edit": me.id == post.author_user_id,
        "can_delete": me.id == post.author_user_id or service.can_moderate(me),
        "can_moderate": service.can_moderate(me),
        # 상태 버튼을 그릴지 판단하는 값. 감추는 것은 편의일 뿐이고 통제는 서버가 한다.
        "can_change_status": service.can_moderate(me),
        # 이 글의 종류에 맞는 카테고리. 상세 화면은 **글을 열어 봐야** 종류를 안다 —
        # 목록에서 온 것이 아니라 주소로 바로 들어올 수 있기 때문이다. 수정 폼이 쓸 목록을
        # 여기 실어 보내지 않으면 아이디어를 고칠 때 자유게시판 카테고리가 뜬다.
        "categories": CATEGORY_ORDER_BY_KIND[post.kind or KIND_FREE],
        # 지금 상태에서 **갈 수 있는 곳만.** 전이표는 서버에 있고(app/board/models.py),
        # 화면이 그 표를 베껴 들면 두 벌이 되어 언젠가 어긋난다 - 그러면 화면은 고를 수
        # 있다고 하는데 서버가 거절하는 자리가 생긴다.
        "next_statuses": service.next_statuses(post),
        "reactions": service.reaction_summary(post_reacts, my_user_id=me.id),
        "attachments": [_attachment_view(a) for a in attachments],
        # 글쓴이·댓글 작성자의 소속·사진. 화면은 `author_user_id` 로 여기서 찾아 쓴다.
        "people": _people_of(db, authors),
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


def _viewer_org_id(db: Session, me: User) -> str | None:
    """이 사람이 볼 수 있는 게시판의 축 — **조직 하나뿐**이다.

    부서로는 좁히지 않는다: 자유게시판은 **사내** 공지판이라 부서로 나누면 그 성격이
    사라진다(사내 공지가 자기 팀에만 보이면 공지판이 아니다). 목록이 내리는 판정과
    글자 그대로 같아야 해서 여기 한 줄로 두고, 아래 모든 단건 경로가 이것을 쓴다.

    RBAC 재감사(2026-08-16, SEC-34와 같은 자리에서 발견)로 정정: 전역(global) 관리자도
    `User.org_id`가 `OrgScopedMixin`의 `default=DEFAULT_ORG_ID`로 항상 채워져 있어,
    예전엔 `getattr(me, "org_id", None)`을 그대로 써 **전역 관리자조차 자기 기본
    조직으로 좁혀졌다**(다른 조직 공지가 안 보임 — 유출과 반대 방향이지만 여전히
    잘못된 판정). `core/scope.py::visibility_scope`가 이미 역할·admin_scope를 올바르게
    해석하므로 그걸 그대로 쓴다 — 여기서 새 판정을 만들지 않는다.
    """
    from app.core.scope import visibility_scope

    if visibility_scope(db, me).is_global:
        return None
    return getattr(me, "org_id", None)


def _get_post_or_404(db: Session, post_id: str, me: User) -> Post:
    """모든 `/{post_id}` 경로(읽기·수정·삭제·고정·조회수·첨부 업로드)의 단 하나의 문.

    목록만 조직을 가려서는 아무 의미가 없다 — 이 경로들은 id 를 직접 받는다. 범위 밖은
    **404**: 403 은 그 글이 존재한다는 사실을 알려 준다(저장소 규칙).
    """
    post = repository.get_post(db, post_id, org_id=_viewer_org_id(db, me))
    if post is None:
        raise NotFoundError("게시글을 찾을 수 없습니다.")
    return post


def _get_comment_or_404(db: Session, comment_id: str, me: User) -> Comment:
    """댓글의 조직은 **부모 글의 조직**이다.

    댓글 행에 org 를 다시 적어 두면 판정이 두 벌이 되고 한쪽만 고쳐진다 — 부모 글로
    판정해 `_get_post_or_404` 와 같은 조건 하나만 남긴다(삭제된 글 아래 댓글이 살아
    있어도 닫히는 것은 덤이 아니라 같은 규칙의 결과다).
    """
    comment = repository.get_comment(db, comment_id)
    if comment is None or repository.get_post(
        db, comment.post_id, org_id=_viewer_org_id(db, me)
    ) is None:
        raise NotFoundError("댓글을 찾을 수 없습니다.")
    return comment


# ── 게시글 ──────────────────────────────────────────────────────────────────
@router.get("/meta")
def board_meta(
    user: User = Depends(get_current_user),
    kind: str | None = Query(default=None, max_length=16),
):
    """작성 폼·필터가 쓰는 상수(카테고리·상태·이모지)와 현재 사용자의 중재 권한.

    카테고리는 종류마다 다르다 — 자유게시판의 '맛집'을 제안 폼에 그리면 아무도 안 쓰는
    선택지가 늘고, 반대로 제안 카테고리가 자유 폼에 뜨면 글이 엉뚱한 칩에 걸린다.
    """
    resolved = _kind_of(kind)
    return {
        "kind": resolved,
        "categories": CATEGORY_ORDER_BY_KIND[resolved],
        # 상태는 아이디어에만 있다. 자유게시판에는 **빈 목록**을 준다 — 화면이 "상태 칩을
        # 그릴지"를 이 값 하나로 정하게 해서 판정이 두 군데로 갈리지 않게 한다.
        "statuses": list(IDEA_STATUSES) if resolved == KIND_IDEA else [],
        "reaction_emojis": list(REACTION_EMOJIS),
        "can_moderate": service.can_moderate(user),
        "can_change_status": service.can_moderate(user),
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
    kind: str | None = Query(default=None, max_length=16),
    status: str | None = Query(default=None, max_length=16),
):
    sort = sort if sort in {"recent", "views", "likes"} else "recent"
    # 종류를 안 주면 자유게시판이다. 옛 화면·북마크(`/api/board/posts` 그대로)가 계속
    # 예전과 같은 목록을 받는다 - 이 작업에서 가장 크게 깨질 수 있는 자리가 여기다.
    resolved_kind = _kind_of(kind)
    cat = category if category in CATEGORY_ORDER_BY_KIND[resolved_kind] else None
    # 상태 필터는 아이디어에만 뜻이 있다. 자유게시판에 실려 와도 무시한다.
    idea_status = (
        status if resolved_kind == KIND_IDEA and status in IDEA_STATUSES else None
    )
    rows, total = repository.list_posts(
        db, category=cat, search=q, sort=sort, offset=page.offset, limit=page.page_size,
        # 자기 조직 글만 (1순위 유출 #4). 부서로는 좁히지 않는다 - 자유게시판은 **사내**
        # 공지판이라 부서로 나누면 그 성격이 사라진다. 맞는 축은 조직이다.
        # 아이디어 게시판도 **같은 축**이다: 사내 제안이라 부서로 나눌 이유가 없고, 새
        # 게이트를 만들면 판정이 두 벌이 된다. 전역 관리자는 `_viewer_org_id`가
        # `None`(무제한)을 준다 — SEC-34와 같은 자리에서 발견한 정정, 위 함수 참고.
        org_id=_viewer_org_id(db, me),
        kind=resolved_kind,
        idea_status=idea_status,
    )
    authors = repository.authors_by_ids(db, {r.author_user_id for r in rows})
    names = {uid: (u.display_name or "") for uid, u in authors.items()}
    counts = repository.comment_counts(db, [r.id for r in rows])
    likes = repository.like_counts(db, [r.id for r in rows])
    return {
        "kind": resolved_kind,
        "items": [
            _post_summary(
                r,
                author_name=names.get(r.author_user_id, "(알 수 없음)"),
                comments=counts.get(r.id, 0),
                me=me,
                likes=likes.get(r.id, 0),
            )
            for r in rows
        ],
        # 목록의 '작성자' 칸도 상세와 **같은 것으로** 답한다 — 동명이인은 목록에서 먼저
        # 만나는데 여기만 이름 두 글자로 남으면 구분이 안 되는 자리가 그대로 남는다.
        "people": _people_of(db, authors),
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
        kind=payload.kind,
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
        after={"kind": post.kind, "category": post.category, "title": post.title},
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
    post = _get_post_or_404(db, post_id, me)
    return {"post": _post_detail(db, post, me)}


@router.post("/posts/{post_id}/view", dependencies=[Depends(require_csrf)])
def mark_viewed(
    post_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """상세 진입 시 프런트가 한 번 호출해 조회수를 올린다(GET refetch로는 안 오른다)."""
    post = _get_post_or_404(db, post_id, me)
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
    post = _get_post_or_404(db, post_id, me)
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
    post = _get_post_or_404(db, post_id, me)
    service.ensure_can_delete(post.author_user_id, me)
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
    post = _get_post_or_404(db, post_id, me)
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


@router.post("/posts/{post_id}/status", dependencies=[Depends(require_csrf)])
def set_idea_status(
    request: Request,
    post_id: str,
    payload: IdeaStatusUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """제안 → 검토중 → 진행 → 완료 / 보류. **진행으로 넘어갈 때 티켓을 만들어 연결한다.**

    범위 판정은 다른 모든 `/{post_id}` 경로와 **같은 문**을 지난다(`_get_post_or_404`) —
    여기에 조건을 새로 적으면 판정이 두 벌이 되고, 그러면 다른 조직 운영자가 남의 회사
    제안을 진행으로 밀 수 있다(그리고 그 회사 Notion 에 티켓이 생긴다).

    티켓 생성이 실패하면 예외가 그대로 올라가 `get_db` 가 트랜잭션을 되돌린다 — 상태도
    함께 사라진다. 그 판단의 이유는 `service.change_idea_status` 에 적어 두었다.
    """
    post = _get_post_or_404(db, post_id, me)
    before = post.idea_status
    service.change_idea_status(
        db,
        post,
        actor=me,
        status=payload.status,
        now=request.app.state.clock.now(),
        outbound=request.app.state.outbound_client,
        settings=request.app.state.settings,
        project_id=payload.project_id,
        repo=getattr(request.app.state, "repositories", None)
        and request.app.state.repositories.tickets,
    )
    record_audit_from_request(
        request,
        db,
        action="board.idea.status",
        object_type="board_post",
        object_id=post.id,
        before={"idea_status": before},
        after={"idea_status": post.idea_status, "ticket_page_id": post.ticket_page_id},
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
    post = _get_post_or_404(db, post_id, me)
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
    comment = _get_comment_or_404(db, comment_id, me)
    service.ensure_can_edit(comment.author_user_id, me)
    service.update_comment(db, comment, payload, now=request.app.state.clock.now())
    record_audit_from_request(
        request,
        db,
        action="board.comment.update",
        object_type="board_comment",
        object_id=comment.id,
    )
    post = _get_post_or_404(db, comment.post_id, me)
    return {"post": _post_detail(db, post, me)}


@router.delete("/comments/{comment_id}", dependencies=[Depends(require_csrf)])
def delete_comment(
    request: Request,
    comment_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    comment = _get_comment_or_404(db, comment_id, me)
    service.ensure_can_delete(comment.author_user_id, me)
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
def _validate_reaction_target(db: Session, target_type: str, target_id: str, me: User) -> None:
    # 반응도 대상 id 를 **바디로 직접 받는다** — 경로 파라미터가 아니라고 다른 문이 아니다.
    # 그래서 판정은 위의 두 함수를 그대로 쓴다(여기에 조건을 새로 적으면 두 벌이 된다).
    # 댓글이 살아 있어도 그 부모 글이 삭제됐거나 다른 조직이면 반응을 받지 않는다(삭제된
    # 글 아래 댓글에 반응이 쌓이는 고아 데이터 방지 — get_post는 삭제 글을 제외한다).
    if target_type == TARGET_POST:
        _get_post_or_404(db, target_id, me)
    else:
        _get_comment_or_404(db, target_id, me)


@router.post("/reactions", dependencies=[Depends(require_csrf)])
def add_reaction(
    request: Request,
    payload: ReactionInput,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    _validate_reaction_target(db, payload.target_type, payload.target_id, me)
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
    post = _get_post_or_404(db, post_id, me)
    service.ensure_can_edit(post.author_user_id, me)
    service.ensure_attachment_capacity(
        db, post.id, max_count=uploads.MAX_ATTACHMENTS_PER_POST
    )
    # sync 핸들러에서는 UploadFile의 내부 파일 객체를 직접 읽는다(await 불필요, 불변 §1).
    content = file.file.read(uploads.MAX_UPLOAD_BYTES + 1)
    with audit_failure_on_exception(
        request, db, action="board.attachment.upload", object_type="board_attachment",
        after={"post_id": post.id},
    ):
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
    # 첨부의 접근권은 **부모 글이 정한다** — 첨부에 판정을 따로 적으면 두 벌이 된다.
    # 부모 글이 삭제됐으면(운영자가 내린 부적절 콘텐츠 등) 첨부도 더는 서빙하지 않는다 —
    # 예전엔 글은 404여도 첨부 URL을 쥔 사람은 계속 받을 수 있었다(삭제가 접근을 못 막음).
    # 조직도 같은 자리에서 본다: 상세를 막아도 여기가 열려 있으면 사내 자료 바이트가
    # 그대로 나간다(첨부 URL 은 상세 응답에 실려 나가므로 id 는 쉽게 새 나간다).
    if repository.get_post(db, att.post_id, org_id=_viewer_org_id(db, me)) is None:
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
            "Content-Disposition": uploads.content_disposition(att.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )
