"""티켓 첨부 (지시서 §4 + 제품화 지시).

여기에도 Notion 이 한 번도 나오지 않는다. 첨부는 처음부터 **우리 데이터**이고 티켓과의 연결은
`ticket_cache.id`(자체 UUID)로만 한다 — 댓글(comments.py)과 같은 규약이다. 라우터가 URL 로
받은 page_id → uid 해석만 저장소 seam(`ensure_local`)을 통해 이뤄진다.

왜 Notion 에 올리지 않는가. Notion 파일 업로드 API 로 밀어 넣으면 '포털에서 올린 이미지'가
곧바로 만료되는 서명 URL 뒤로 들어가고, 우리는 그걸 다시 프록시해야 하며, 소스를 바꾸는 날
전부 잃는다. 반대로 여기 두면 티켓 본문(Notion)에 있던 이미지는 그대로 읽고(notion_write.py
`_image_view`), 사용자가 새로 붙이는 것은 우리가 갖는다. 제품화의 방향과도 맞다 —
"사용자가 DB(현재는 노션)에 접근하지 않아도 본인 업무를 모두 관리".

권한:
  * 올리기·지우기 — 티켓을 편집할 수 있는 사람(service.ensure_can_edit 과 같은 선).
    남의 담당 티켓에 파일을 붙이거나 떼는 것은 티켓을 고치는 일이다.
  * 보기 — 로그인한 누구나. 티켓 자체가 팀 전체 조회 대상(`/api/tickets/team`)이라
    첨부만 좁히면 "옆 팀 사람이 첨부를 못 본다"가 되고, 그건 §4 가 없애려는 상태다.
  * 없는 첨부·지워진 티켓 — **404**. 403 은 "그런 첨부가 있긴 하다"를 알려 준다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.uploads import (
    IMAGE_MEDIA_TYPES,
    MAX_UPLOAD_BYTES,
    NS_TICKET,
    attachment_path,
    save_upload,
)
from app.tickets.models import TicketAttachment
from app.users.models import User

# 티켓 하나에 붙일 수 있는 최대 개수. 게시판(5)보다 넉넉한 이유: 티켓은 화면 캡처를 순서대로
# 붙여 설명하는 일이 잦다("이 화면에서 이렇게 눌렀더니 이렇게 나옵니다").
MAX_TICKET_ATTACHMENTS = 10

# PDF 도 받는다(게시판과 같은 허용 목록). 첨부한 규격서를 보려고 노션을 열게 만들지 않는다.
ALLOWED_TICKET_MEDIA = IMAGE_MEDIA_TYPES | {"application/pdf"}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def attachment_view(att: TicketAttachment, *, uploader_name: str = "") -> dict:
    """첨부 한 건의 API 응답. `url` 은 인증이 걸린 우리 라우트다(디스크 경로가 아니다)."""
    return {
        "id": att.id,
        "filename": att.filename,
        "media_type": att.media_type,
        "size_bytes": att.size_bytes,
        "is_image": att.media_type in IMAGE_MEDIA_TYPES,
        "uploaded_by_user_id": att.uploaded_by_user_id,
        "uploaded_by_name": uploader_name,
        "created_at": _iso(att.created_at),
        "url": f"/api/tickets/attachments/{att.id}",
    }


def list_attachments(db: Session, *, ticket_uid: str) -> list[TicketAttachment]:
    return list(
        db.execute(
            select(TicketAttachment)
            .where(TicketAttachment.ticket_uid == ticket_uid)
            .order_by(TicketAttachment.created_at.asc(), TicketAttachment.id.asc())
        ).scalars()
    )


def attachment_views(db: Session, *, ticket_uid: str) -> list[dict]:
    """목록 + 올린 사람 이름. 이름은 한 번의 질의로 모아 온다(첨부 개수만큼 부르지 않는다)."""
    rows = list_attachments(db, ticket_uid=ticket_uid)
    if not rows:
        return []
    names = dict(
        db.execute(
            select(User.id, User.display_name)
            .where(User.id.in_({r.uploaded_by_user_id for r in rows}))
        ).all()
    )
    return [attachment_view(r, uploader_name=names.get(r.uploaded_by_user_id) or "") for r in rows]


def ensure_capacity(db: Session, *, ticket_uid: str) -> None:
    count = db.execute(
        select(func.count())
        .select_from(TicketAttachment)
        .where(TicketAttachment.ticket_uid == ticket_uid)
    ).scalar_one()
    if count >= MAX_TICKET_ATTACHMENTS:
        raise ValidationAppError(
            f"첨부는 티켓 하나에 최대 {MAX_TICKET_ATTACHMENTS}개까지 올릴 수 있습니다."
        )


def add_attachment(
    db: Session, data_dir: Path, *, ticket_uid: str, uploader: User,
    filename: str, content: bytes, now: datetime,
) -> TicketAttachment:
    """바이트를 디스크에 쓰고 메타를 등록한다. 형식 판정은 **매직바이트**가 한다."""
    ensure_capacity(db, ticket_uid=ticket_uid)
    stored_name, media_type, size, display_name = save_upload(
        data_dir, ticket_uid, filename=filename, content=content,
        namespace=NS_TICKET, allowed_media_types=ALLOWED_TICKET_MEDIA,
    )
    att = TicketAttachment(
        ticket_uid=ticket_uid,
        uploaded_by_user_id=uploader.id,
        filename=display_name,
        stored_name=stored_name,
        media_type=media_type,
        size_bytes=size,
        created_at=now,
    )
    db.add(att)
    db.flush()
    return att


def get_attachment(db: Session, attachment_id: str) -> TicketAttachment | None:
    return db.get(TicketAttachment, attachment_id)


def file_path(data_dir: Path, att: TicketAttachment) -> Path | None:
    return attachment_path(data_dir, att.ticket_uid, att.stored_name, namespace=NS_TICKET)


def remove_attachment(db: Session, att: TicketAttachment) -> None:
    """메타만 지운다. 디스크의 바이트는 남긴다 — 게시판 첨부와 같은 판단이다.

    되돌릴 수 없는 삭제를 요청 한 번에 붙이면, 동기화 사고 한 번으로 사용자가 올린 원본이
    사라진다. 도달할 수 없는 파일은 보관 정책이 따로 치운다.
    """
    db.delete(att)
    db.flush()


__all__ = [
    "ALLOWED_TICKET_MEDIA",
    "MAX_TICKET_ATTACHMENTS",
    "MAX_UPLOAD_BYTES",
    "add_attachment",
    "attachment_view",
    "attachment_views",
    "ensure_capacity",
    "file_path",
    "get_attachment",
    "list_attachments",
    "remove_attachment",
]
