"""문서 첨부 — `document_attachments` 를 쓰는 **유일한 자리** (S8).

## 왜 입구가 하나여야 하는가

S6·S7 이 세운 규칙 그대로다. 첨부는 두 표에 걸쳐 있다(`files` 와 `document_attachments`)
고, 두 표를 각자 쓰는 코드가 두 곳이 되면 한쪽만 만들어진 상태가 생긴다 — 파일은
올라갔는데 문서에 안 붙거나, 붙었는데 파일 행이 없다. 둘 다 오류를 안 내고, 화면에서는
「첨부가 사라졌다」로만 보인다. `scripts/check_domain_single_source.py` 가 이 규칙을 지킨다.

## 접근 판정은 여기 없다

첨부의 접근권은 **부모 문서가 정한다**(`app/knowledge/models.py::DocumentAttachment`).
이 모듈의 함수는 이미 가시성 검사를 통과한 문서를 받는다 — 라우터가
`get_scoped_document_or_404` 로 그것을 먼저 한다.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.knowledge.models import Document, DocumentAttachment
from app.storage import service as storage_service
from app.storage.models import File
from app.work import rank


def of_document(db: Session, document_id: str) -> list[tuple[DocumentAttachment, File]]:
    """한 문서의 첨부 전부. 붙인 순서대로 나온다."""
    rows = db.execute(
        select(DocumentAttachment, File)
        .join(File, File.id == DocumentAttachment.file_id)
        .where(DocumentAttachment.document_id == document_id)
        .order_by(DocumentAttachment.sort_order)
    ).all()
    return [(a, f) for a, f in rows]


def counts_for(db: Session, document_ids: list[str]) -> dict[str, int]:
    """문서 여러 건의 첨부 개수. 목록 화면이 문서마다 질의하지 않게 한다."""
    if not document_ids:
        return {}
    rows = db.execute(
        select(DocumentAttachment.document_id, func.count())
        .where(DocumentAttachment.document_id.in_(tuple(sorted(set(document_ids)))))
        .group_by(DocumentAttachment.document_id)
    ).all()
    return {str(doc_id): int(n) for doc_id, n in rows}


def attach(
    db: Session,
    document: Document,
    *,
    filename: str,
    content: bytes,
    created_by: str | None = None,
    caption: str | None = None,
) -> tuple[DocumentAttachment, File]:
    """파일을 저장하고 문서에 붙인다. **저장이 먼저, 연결이 다음이다.**

    저장이 실패하면 예외가 나가고 연결은 만들어지지 않는다. 반대 순서면 「첨부 줄은
    있는데 파일이 없다」가 생기고, 그것은 사용자에게 거짓말이다.
    """
    record = storage_service.store_bytes(
        db,
        filename=filename,
        content=content,
        owner_ref=f"document:{document.id}",
        created_by=created_by,
    )
    link = DocumentAttachment(
        document_id=document.id,
        file_id=record.id,
        caption=(caption or None),
        sort_order=_next_order(db, document.id),
        created_by=created_by,
    )
    db.add(link)
    db.flush()
    return link, record


def get_or_404(db: Session, attachment_id: str) -> tuple[DocumentAttachment, File]:
    row = db.execute(
        select(DocumentAttachment, File)
        .join(File, File.id == DocumentAttachment.file_id)
        .where(DocumentAttachment.id == attachment_id)
    ).first()
    if row is None:
        raise NotFoundError("첨부를 찾지 못했습니다.")
    return row[0], row[1]


def detach(db: Session, link: DocumentAttachment) -> None:
    """연결을 끊는다. **파일 행은 다른 문서가 안 쓸 때만 함께 지운다.**

    한 파일이 여러 문서에 붙어 있을 수 있다. 무조건 지우면 남의 문서의 첨부가 조용히
    깨지고, 무조건 남기면 아무도 안 가리키는 바이트가 쌓인다. 그래서 세어 보고 정한다 —
    세다가 놓친 것은 `storage_service.sweep_orphans` 가 나중에 치운다.
    """
    file_id = link.file_id
    db.delete(link)
    db.flush()
    still_used = db.execute(
        select(func.count())
        .select_from(DocumentAttachment)
        .where(DocumentAttachment.file_id == file_id)
    ).scalar_one()
    if still_used:
        return
    record = db.get(File, file_id)
    if record is not None:
        storage_service.delete_file(db, record)


def json_of(link: DocumentAttachment, record: File) -> dict:
    """화면 계약 한 벌. **직렬화는 여기 하나다** — 화면마다 필드 이름이 갈리면
    프런트가 첨부 하나에 여러 벌의 처리를 갖게 된다."""
    return {
        "id": link.id,
        "document_id": link.document_id,
        "file_id": record.id,
        "filename": record.filename,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "checksum_sha256": record.checksum_sha256,
        "caption": link.caption,
        "created_by": link.created_by,
        "created_at": link.created_at,
    }


def _next_order(db: Session, document_id: str) -> Decimal:
    last = db.execute(
        select(func.max(DocumentAttachment.sort_order)).where(
            DocumentAttachment.document_id == document_id
        )
    ).scalar_one_or_none()
    return (Decimal(last) + rank.STEP) if last is not None else rank.STEP
