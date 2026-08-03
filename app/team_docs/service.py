"""팀 공간 > 문서 비즈니스 규칙 (필터 옵션·즐겨찾기·최근 열람).

유니크 제약이 걸린 삽입(즐겨찾기·최근열람)은 동시 요청에서 500이 나지 않도록 SAVEPOINT +
IntegrityError 흡수로 멱등하게 처리한다(자유게시판 검수에서 배운 패턴).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.team_docs import repository
from app.team_docs.models import (
    DocumentCache,
    DocumentFavorite,
    DocumentRecentView,
    join_names,
    split_names,
)
# 수동 동기화는 운영자군만(무분별한 Notion 호출·비용 방지). 주기 동기화는 워커가 전원에게 제공.
# 문서 삭제(휴지통)도 같은 선이다 — 운영자군은 무엇이든, 그 외는 본인 문서만.
# 예전엔 SYNC_ROLES / _DOC_DELETE_ROLES 두 이름이 **같은 집합**을 각자 계산하고 있었다:
# 한쪽만 고치면 "동기화는 되는데 삭제는 안 되는" 상태가 조용히 생긴다. 이제 이름도
# 지우고 authz 의 MODERATOR_ROLES 를 그대로 쓴다.
from app.core.authz import MODERATOR_ROLES
from app.users.models import User


def can_trigger_sync(user: User) -> bool:
    return user.role in MODERATOR_ROLES


def ensure_can_delete_doc(doc: DocumentCache, user: User) -> None:
    """문서 삭제 권한 — 운영자군이거나 작성자/소유자 본인(이름 일치)."""
    if user.role in MODERATOR_ROLES:
        return
    name = (user.display_name or "").strip()
    authors = {a.strip() for a in split_names(doc.author_names or "")}
    if name and (name in authors or name == (doc.owner or "").strip()):
        return
    raise ForbiddenError("이 문서를 삭제할 권한이 없습니다(작성자 또는 운영자만 가능).")


def trash_document(db: Session, *, user: User, page_id: str, now: datetime) -> dict:
    """문서를 휴지통으로 보낸다(노션 원본은 보관기간 뒤 삭제). 작성자/운영자만."""
    from app.trash import service as trash_service
    from app.trash.models import TRASH_DOCUMENT

    doc = repository.get_by_page_id(db, page_id)
    if doc is None:
        raise NotFoundError("문서를 찾을 수 없습니다.")
    ensure_can_delete_doc(doc, user)
    item = trash_service.move_to_trash(
        db, item_type=TRASH_DOCUMENT, notion_page_id=page_id,
        title=doc.title or "(제목 없음)", url=doc.url, user=user, now=now,
    )
    return {"title": item.title, "url": item.url}


def trash_documents_bulk(db: Session, *, user: User, page_ids: list[str], now: datetime) -> dict:
    """문서 여러 건을 휴지통으로. 건별 권한 검사, 실패는 건너뛰고 계속(부분 성공)."""
    from app.core.errors import AppError

    trashed: list[dict] = []
    failed: list[dict] = []
    for pid in page_ids:
        try:
            result = trash_document(db, user=user, page_id=pid, now=now)
            trashed.append({"id": pid, "title": result["title"]})
        except AppError as exc:
            failed.append({"id": pid, "error": exc.message})
    return {"trashed": trashed, "failed": failed}


def filter_options(db: Session) -> dict:
    """필터·작성 폼 옵션. 문서 종류·업무 분야·기술 태그는 고정 상수(공통), 프로젝트·상태는
    캐시에서 실제 쓰이는 값."""
    from app.team_docs.classify import DOC_TYPES, TECH_TAGS, WORK_FIELDS

    projects: set[str] = set()
    statuses: set[str] = set()
    for row in repository.all_active(db):
        projects.update(split_names(row.project_names))
        if row.status:
            statuses.add(row.status)
    return {
        "doc_types": list(DOC_TYPES),
        "work_fields": list(WORK_FIELDS),
        "tech_tags": list(TECH_TAGS),
        "projects": sorted(projects),
        "statuses": sorted(statuses),
    }


def _document_uid(db: Session, page_id: str) -> str | None:
    """Notion page id → 미러 행의 자체 UUID(0025). 미러에 없으면 None.

    None 이 정상 상태다: 방금 만들어져 아직 동기화되지 않은 문서를 즐겨찾기할 수 있다.
    그래서 이 값을 필수로 만들거나 FK 로 걸지 않는다 — 조회·유일성은 계속 notion_page_id 가
    담당하고 이 컬럼은 소스 전환을 위한 다리일 뿐이다.
    """
    from app.team_docs.models import DocumentCache

    return db.execute(
        select(DocumentCache.id).where(DocumentCache.notion_page_id == page_id)
    ).scalar_one_or_none()


def toggle_favorite(db: Session, *, user_id: str, page_id: str, on: bool, now: datetime) -> bool:
    existing = repository.find_favorite(db, user_id, page_id)
    if on:
        if existing is not None:
            return True
        row = DocumentFavorite(
            user_id=user_id, notion_page_id=page_id, created_at=now,
            document_id=_document_uid(db, page_id),
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            pass  # 동시 요청이 먼저 추가 — 멱등
        return True
    if existing is not None:
        db.delete(existing)
        db.flush()
    return False


def record_view(db: Session, *, user_id: str, page_id: str, now: datetime) -> None:
    existing = repository.find_recent(db, user_id, page_id)
    if existing is not None:
        existing.viewed_at = now
        db.flush()
        return
    row = DocumentRecentView(
        user_id=user_id, notion_page_id=page_id, viewed_at=now,
        document_id=_document_uid(db, page_id),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # 경쟁에서 진 쪽 — 이미 생긴 행의 시각을 갱신.
        again = repository.find_recent(db, user_id, page_id)
        if again is not None:
            again.viewed_at = now
            db.flush()


def cache_created_document(
    db: Session, *, page: dict, title: str, document_type, work_field, tech_tags,
    project_names, status, priority, owner, memo, now: datetime, author_name: str = "",
) -> DocumentCache:
    """방금 생성한 문서를 캐시에 즉시 반영해 목록에 바로 뜨게 한다. 신규 택소노미는 사용자가
    고른 값을 저장하고 classification_manual=True 로 둬 이후 sync가 덮어쓰지 않게 한다."""
    pid = page.get("id")
    row = repository.get_by_page_id(db, pid) or DocumentCache(notion_page_id=pid)
    row.url = page.get("url")
    row.title = title
    row.type_names = ""
    row.category_names = ""
    row.project_names = join_names(project_names)
    row.document_type = document_type or "기타"
    row.work_field = work_field or "기타"
    row.tech_tags = join_names(tech_tags)
    row.classification_manual = True
    row.status = status
    row.priority = priority
    row.owner = owner or ""
    row.memo = memo or ""
    row.author_names = join_names([author_name]) if author_name else ""
    row.last_edited = page.get("last_edited_time")
    row.created_time = page.get("created_time")
    row.original_url = None
    row.source_url = None
    row.has_files = False
    row.notion_favorite = False
    row.archived = False
    row.synced_at = now
    db.add(row)
    db.flush()
    return row


def recent_documents(db: Session, user_id: str, *, limit: int = 10) -> list:
    """최근 열람 순으로 캐시 문서를 돌려준다(캐시에 없는 오래된 항목은 건너뛴다)."""
    views = repository.recent_views(db, user_id, limit=limit)
    out = []
    for v in views:
        doc = repository.get_by_page_id(db, v.notion_page_id)
        if doc is not None:
            out.append(doc)
    return out
