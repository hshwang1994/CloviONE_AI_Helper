"""문서 댓글 (사용자 지적 #9).

`app/tickets/comments.py` 를 그대로 옮겼다. 새로 설계하지 않은 이유가 그 자체로 규칙이다:
댓글은 두 화면에서 **같은 규약**으로 움직여야 한다. 티켓에서는 툼스톤이 남는데 문서에서는
행이 조용히 사라지면, 사용자는 같은 낱말('삭제')이 화면마다 다른 뜻이라는 것을 스스로
알아내야 한다.

권한(테스트로 고정한다):
  * 작성 -- 그 문서가 보이는 사람 누구나. 문서는 팀 전체 조회 대상이고(범위 안에서),
    댓글만 작성자로 좁히면 "옆 팀 사람이 물어볼 곳이 없다" 가 된다.
  * 수정 -- **작성자 본인만.** 운영자도 남의 문장을 고쳐 쓸 수는 없다. 남의 말을 바꾸는 것은
    지우는 것보다 나쁘다(누가 썼는지는 그대로인데 내용만 달라진다).
  * 삭제 -- 작성자 본인 또는 운영자군(모더레이션). 게시판, 티켓 댓글과 같은 규약.

**여기 있는 것은 "누가" 이지 "어느 문서에서" 가 아니다.** 범위 판정은 이 모듈에 없다 --
그건 부모 문서의 성질이고, 이 모듈은 문서를 모른다(작성자 Notion id 도 휴지통도 여기서는
보이지 않는다). 범위는 부르는 쪽인 `app/team_docs/service.py` 가 `get_doc_in_scope` 로
**권한 판정보다 먼저** 하고, 목록, 작성, 수정, 삭제가 전부 그 한 함수를 지난다.
티켓 댓글에서 정확히 이 자리가 뚫려 있었다: 목록에는 범위가 걸렸는데 삭제는 comment_id 만
받아 그냥 지나갔다(→ tests/security/test_ticket_comment_write_scope.py).

삭제는 soft-delete 다. 그리고 **목록은 삭제된 댓글도 툼스톤으로 계속 돌려준다** -- 행이 그냥
사라지면 이미 목록을 받아 둔 클라이언트는 자기 화면이 낡았는지조차 알 수 없다. 툼스톤에는
본문을 싣지 않는다(삭제의 목적은 내용을 안 보이게 하는 것이다).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import people
from app.core.authz import MODERATOR_ROLES
from app.core.errors import ForbiddenError, NotFoundError
from app.team_docs.models import DocumentComment
from app.users.models import User

# 티켓 댓글과 같은 값. 화면(frontend/src/screens/CommentThread.jsx)의 입력 제한은 힌트일
# 뿐이고 실제 거절은 여기가 한다.
MAX_COMMENT_CHARS = 2000


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def comment_view(c: DocumentComment, *, author_name: str, me: User) -> dict:
    """댓글 한 건의 API 응답. 삭제된 댓글은 **본문 없는 툼스톤**으로 나간다."""
    deleted = c.deleted_at is not None
    return {
        "id": c.id,
        "author_user_id": c.author_user_id,
        "author_name": author_name,
        # 본문은 살아 있는 댓글에만. 지운 내용을 계속 내려보내면 삭제가 아니다.
        "body": "" if deleted else c.body,
        "deleted": deleted,
        "deleted_at": _iso(c.deleted_at),
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
        # 화면이 버튼을 그릴지 판단하는 값. 서버는 이 값과 무관하게 매 요청 다시 검사한다.
        "can_edit": (not deleted) and c.author_user_id == me.id,
        "can_delete": (not deleted) and _can_delete(c.author_user_id, me),
    }


def _can_delete(author_user_id: str, me: User) -> bool:
    return me.id == author_user_id or me.role in MODERATOR_ROLES


def ensure_can_edit(comment: DocumentComment, me: User) -> None:
    """수정은 작성자 본인만 -- 운영자 우회 없음.

    **범위 판정이 아니다.** 부모 문서가 이 사람에게 보이는지는 부르는 쪽이 먼저 본다
    (모듈 docstring 참조) -- 그 순서라야 범위 밖이 403 이 아닌 404 로 나간다.
    """
    if comment.author_user_id != me.id:
        raise ForbiddenError("본인이 작성한 댓글만 수정할 수 있습니다.")


def ensure_can_delete(comment: DocumentComment, me: User) -> None:
    """모더레이션 권한(`MODERATOR_ROLES`)은 **역할**이지 범위가 아니다 -- 부모 문서가 보이는지는
    부르는 쪽이 먼저 본다(모듈 docstring 참조)."""
    if not _can_delete(comment.author_user_id, me):
        raise ForbiddenError("본인이 작성한 댓글만 삭제할 수 있습니다.")


def get_or_404(db: Session, comment_id: str) -> DocumentComment:
    comment = db.get(DocumentComment, comment_id)
    if comment is None:
        raise NotFoundError("댓글을 찾을 수 없습니다.")
    return comment


def list_comments(db: Session, *, page_id: str, me: User) -> dict:
    """그 문서의 댓글 전부(삭제된 것은 툼스톤으로) + 등장인물 신원(`people`). 오래된 것부터.

    사용자 지시(#13): *"게시글과 댓글에는 작성자의 부서·팀·직책을 함께 표시한다"*.
    게시판(`app/board/router.py::_people_of`)이 이미 같은 것을 답하고 있어, 조립은
    `core/people.identities_for` 를 그대로 쓴다 -- 새로 짜지 않는다(티켓 댓글과 같은 판단).
    """
    rows = db.execute(
        select(DocumentComment)
        .where(DocumentComment.notion_page_id == page_id)
        # 동점(같은 created_at)일 때의 tie-break 가 **삽입 순서**여야 한다. id 로 깨면 UUID4 는
        # 무작위라 순서가 매번 동전 던지기가 된다 -- 시계가 멈춘 테스트에서는 항상 동점이라
        # 목록이 절반의 확률로 뒤집히고(플래키 테스트), 운영에서도 같은 순간에 달린 두 댓글이
        # 답글보다 먼저 보이는 일이 생긴다. `seq` 가 그 삽입 순서다
        # (`GENERATED ALWAYS AS IDENTITY`, models.py) — 예전에는 SQLite 의 숨은 `rowid`
        # 였고 PG 에는 그것이 없다. 티켓 댓글과 같은 판단이다.
        .order_by(DocumentComment.created_at.asc(), DocumentComment.seq.asc())
    ).scalars().all()
    authors = _authors_by_ids(db, [r.author_user_id for r in rows])
    names = {uid: (u.display_name or "") for uid, u in authors.items()}
    return {
        "comments": [
            comment_view(r, author_name=names.get(r.author_user_id, ""), me=me) for r in rows
        ],
        "people": people.identities_for(db, authors),
    }


def _authors_by_ids(db: Session, user_ids: list[str]) -> dict[str, User]:
    """{user_id: User} -- 표시 이름과 신원(부서·직책·사진)을 **한 번의 질의**로 함께 얻는다.

    `department`/`title` 은 `User` 의 관계 프로퍼티고 `lazy="joined"` 다(app/users/models.py)
    -- 이 select 하나로 추가 질의 없이 함께 실린다.
    """
    ids = {i for i in (user_ids or ()) if i}
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(ids))).scalars().all()
    return {u.id: u for u in rows}


def create_comment(
    db: Session,
    *,
    page_id: str,
    document_id: str | None,
    author: User,
    body: str,
    now: datetime,
) -> DocumentComment:
    """`document_id` 는 **없어도 된다**(미러 행이 아직 없거나 방금 prune 으로 사라진 경우).
    조회는 `page_id` 가 하므로 그 상태에서도 댓글은 온전하다 -- models.py 의 이유 참조."""
    comment = DocumentComment(
        notion_page_id=page_id,
        document_id=document_id,
        author_user_id=author.id,
        body=body,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    db.flush()
    return comment


def update_comment(
    db: Session, comment: DocumentComment, *, body: str, now: datetime
) -> DocumentComment:
    """이미 지운 댓글은 되살아나지 않는다 -- 수정으로 삭제를 되돌리는 뒷문을 만들지 않는다."""
    if comment.deleted_at is not None:
        raise NotFoundError("이미 삭제된 댓글입니다.")
    comment.body = body
    comment.updated_at = now
    db.flush()
    return comment


def soft_delete_comment(db: Session, comment: DocumentComment, *, now: datetime) -> None:
    if comment.deleted_at is not None:
        return  # 멱등 -- 두 번 눌러도 삭제 시각이 바뀌지 않는다
    comment.deleted_at = now
    comment.updated_at = now
    db.flush()
