"""팀 공간 > 문서 비즈니스 규칙 (필터 옵션·즐겨찾기·최근 열람).

유니크 제약이 걸린 삽입(즐겨찾기·최근열람)은 동시 요청에서 500이 나지 않도록 SAVEPOINT +
IntegrityError 흡수로 멱등하게 처리한다(자유게시판 검수에서 배운 패턴).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.team_docs import repository
from app.team_docs.models import (
    DocumentCache,
    DocumentFavorite,
    DocumentRecentView,
    join_names,
    split_names,
)
from app.users.models import ROLE_OPERATOR, User, roles_at_least

# 수동 동기화는 운영자군만(무분별한 Notion 호출·비용 방지). 주기 동기화는 워커가 전원에게 제공.
SYNC_ROLES = roles_at_least(ROLE_OPERATOR)


def can_trigger_sync(user: User) -> bool:
    return user.role in SYNC_ROLES


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


def toggle_favorite(db: Session, *, user_id: str, page_id: str, on: bool, now: datetime) -> bool:
    existing = repository.find_favorite(db, user_id, page_id)
    if on:
        if existing is not None:
            return True
        row = DocumentFavorite(user_id=user_id, notion_page_id=page_id, created_at=now)
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
    row = DocumentRecentView(user_id=user_id, notion_page_id=page_id, viewed_at=now)
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
