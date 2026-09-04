"""빈 문서를 치운다 — 본문이 없거나 아주 짧은 문서.

## 왜 필요한가

Confluence 와 Notion 에는 **제목만 있는 페이지**가 흔하다. 하위 페이지를 묶는 목차이거나,
만들다 만 자리이거나, 옛 구조의 껍데기다. 우리 쪽으로 넘어오면 그것들은 목록에서 자리를
차지하고 검색 결과에 섞이는데 열어 보면 아무것도 없다 — 읽는 사람에게는 고장으로 보인다.

## 지우는 방식은 **제품의 삭제**다

행을 지우지 않는다. `knowledge_service.delete_document` 를 그대로 불러 보관 처리하고
「누가 언제」를 적는다 — 휴지통에 뜨고 되돌릴 수 있으며, 보관 기간이 지나면 제품의 규칙에
따라 영구 삭제된다. 이관 도구가 삭제 의미를 새로 만들지 않는다.

## 🔴 자체 작성 문서는 안 건드린다

사람이 방금 만든 빈 문서는 「쓰레기」가 아니라 **쓰려던 자리**다. 이관·Import 로 들어온
문서만 후보로 삼는다 — 적재기·분류 적용기와 같은 술어(`classify.is_rewritable`)를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.knowledge import service as knowledge_service
from app.knowledge.models import Document, DocumentVersion

__all__ = ["PruneResult", "find_empty", "prune_empty", "DEFAULT_MIN_CHARS"]

#: 이 글자 수 **이하**면 빈 문서로 본다. 사용자가 정한 값이다.
DEFAULT_MIN_CHARS = 20


@dataclass
class PruneResult:
    scanned: int = 0
    deleted: int = 0
    refused_native: int = 0
    already_archived: int = 0
    attachments_taken: int = 0
    comments_taken: int = 0
    titles: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "deleted": self.deleted,
            "refused_native": self.refused_native,
            "already_archived": self.already_archived,
            "attachments_taken": self.attachments_taken,
            "comments_taken": self.comments_taken,
        }


def find_empty(db: Session, *, max_chars: int = DEFAULT_MIN_CHARS) -> list[Document]:
    """본문이 `max_chars` 이하인 **보관 안 된** 문서.

    판이 없는 문서(한 번도 저장 안 됨)도 여기 든다 — `body_text` 가 NULL 이면 0자다.
    제목은 안 센다: 사용자가 말한 것은 **본문**이다.
    """
    length = sa.func.coalesce(
        sa.func.length(sa.func.btrim(DocumentVersion.body_text)), 0
    )
    stmt = (
        sa.select(Document)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
        .where(sa.not_(Document.archived), length <= max_chars)
        .order_by(Document.title)
    )
    return list(db.execute(stmt).scalars().unique().all())


def prune_empty(
    db: Session, *, actor, max_chars: int = DEFAULT_MIN_CHARS,
    dry_run: bool = False, report=None, now=None,
) -> PruneResult:
    """빈 문서를 보관 처리한다. **자체 작성 문서는 세기만 하고 안 건드린다.**"""
    from app.knowledge.models import DocumentAttachment, DocumentComment
    from app.migration.classify import is_rewritable
    from app.migration.report import SEVERITY_NOTE

    result = PruneResult()
    for document in find_empty(db, max_chars=max_chars):
        result.scanned += 1
        if not is_rewritable(db, document):
            # 사람이 만든 빈 문서다. 쓰려던 자리일 수 있다.
            result.refused_native += 1
            continue
        result.attachments_taken += db.execute(
            sa.select(sa.func.count()).select_from(DocumentAttachment)
            .where(DocumentAttachment.document_id == document.id)
        ).scalar_one()
        result.comments_taken += db.execute(
            sa.select(sa.func.count()).select_from(DocumentComment)
            .where(DocumentComment.document_id == document.id)
        ).scalar_one()
        if len(result.titles) < 200:
            result.titles.append(document.title or "(제목 없음)")
        if not dry_run:
            knowledge_service.delete_document(db, actor, document.id, now=now)
        result.deleted += 1

    if report is not None:
        report.check(
            "빈 문서 정리", result.refused_native == 0,
            "자체 작성 문서 0건", f"{result.refused_native}건",
            "자체 작성 문서는 후보에 안 든다. 사람이 만든 빈 문서는 쓰려던 자리다.",
        )
        if result.deleted:
            report.finding(
                SEVERITY_NOTE, "empty_documents_pruned", "documents",
                f"본문이 {max_chars}자 이하인 문서 {result.deleted}건을 휴지통으로 옮겼습니다"
                f"(첨부 {result.attachments_taken}건과 댓글 {result.comments_taken}건이 함께 갑니다).",
            )
    if not dry_run:
        db.flush()
    return result
