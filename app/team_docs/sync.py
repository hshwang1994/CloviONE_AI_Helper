"""문서 캐시 동기화 (§17.2 동기화, §17.4 장애 격리).

Notion "문서" DB 전체를 읽어 relation 이름을 해석하고 로컬 DocumentCache로 upsert 한다.
Notion 장애/미설정이면 캐시를 건드리지 않고 sync 상태만 error로 남긴다 — 기존 목록(마지막
정상 동기화)은 그대로 살아 있고, 티켓 등 다른 기능엔 아무 영향이 없다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.sync_prune import PruneResult, prune_missing
from app.team_docs import notion_docs
from app.team_docs.classify import classify
from app.team_docs.models import (
    SYNC_ERROR,
    SYNC_OK,
    SYNC_STATE_ID,
    DocumentCache,
    DocumentSyncState,
    join_names,
)


def get_or_create_state(db: Session) -> DocumentSyncState:
    state = db.get(DocumentSyncState, SYNC_STATE_ID)
    if state is None:
        state = DocumentSyncState(id=SYNC_STATE_ID)
        db.add(state)
        db.flush()
    return state


def _name_list(ids: list[str], name_map: dict[str, str]) -> list[str]:
    return [name_map.get(i, "").strip() for i in ids if name_map.get(i, "").strip()]


def _names(ids: list[str], name_map: dict[str, str]) -> str:
    return join_names([name_map.get(i, "").strip() for i in ids])


def _upsert(db: Session, d: dict, rel_maps: dict, now: datetime) -> None:
    pid = d["notion_page_id"]
    if not pid:
        return
    row = db.execute(
        select(DocumentCache).where(DocumentCache.notion_page_id == pid)
    ).scalar_one_or_none()
    if row is None:
        row = DocumentCache(notion_page_id=pid)
        db.add(row)
    row.url = d.get("url")
    row.title = d.get("title") or ""
    type_list = _name_list(d.get("type_ids") or [], rel_maps.get(notion_docs.PROP_TYPE, {}))
    cat_list = _name_list(d.get("category_ids") or [], rel_maps.get(notion_docs.PROP_CATEGORY, {}))
    row.type_names = join_names(type_list)  # 원본 유형(분류 입력·참고용)
    row.category_names = join_names(cat_list)
    row.project_names = _names(d.get("project_ids") or [], rel_maps.get(notion_docs.PROP_PROJECT, {}))
    # 신규 택소노미 자동 계산 — 사용자가 수동으로 고친 문서는 건드리지 않는다.
    if not row.classification_manual:
        dt, wf, tags = classify(type_list, cat_list, row.title)
        row.document_type = dt
        row.work_field = wf
        row.tech_tags = join_names(tags)
    row.status = d.get("status")
    row.priority = d.get("priority")
    row.author_names = join_names(d.get("author_names") or [])
    row.author_notion_ids = join_names(d.get("author_notion_ids") or [])
    row.owner = d.get("owner") or ""
    row.doc_date = d.get("doc_date")
    row.orig_date = d.get("orig_date")
    row.created_time = d.get("created_time")
    row.last_edited = d.get("last_edited")
    row.original_url = d.get("original_url")
    row.source_url = d.get("source_url")
    row.memo = d.get("memo") or ""
    row.has_files = bool(d.get("has_files"))
    row.notion_favorite = bool(d.get("notion_favorite"))
    row.archived = bool(d.get("archived"))
    row.synced_at = now


def _prune(db: Session, keep: set[str]) -> PruneResult:
    """Notion에서 사라진(삭제·공유 해제) 문서는 캐시에서도 지운다.

    삭제 판단은 `core.sync_prune` 의 바닥을 거친다. 문서 쪽이 티켓보다 위험하다 —
    `classification_manual` 로 표시된 **사용자가 손으로 고친 분류는 Notion 에 대응 필드가 없어서**
    지워지면 영구 소실이고, 재동기화하면 자동 분류가 덮어써서 아무도 알아채지 못한다.
    """
    existing = db.execute(select(DocumentCache)).scalars().all()
    return prune_missing(db, existing, keep, key=lambda r: r.notion_page_id, label="문서")


def sync_documents(db: Session, *, outbound, settings, now: datetime) -> DocumentSyncState:
    """전체 동기화. 어떤 단계에서 실패해도 예외를 밖으로 던지지 않고 상태에 error로 기록만
    한다(§17.4) — 호출측(엔드포인트/워커)은 절대 크래시하지 않고 캐시(마지막 정상)로 폴백한다.
    fetch 뿐 아니라 upsert/prune/flush(동시 sync 충돌 등)까지 통째로 가둔다."""
    state = get_or_create_state(db)
    state.last_run_at = now
    try:
        schema = notion_docs.fetch_documents_schema(outbound, settings)
        # relation 조회 실패는 **분류를 통째로 뒤집는다** — 상태에 올려야 한다(C4).
        rel_failures: list[str] = []
        rel_maps = notion_docs.resolve_relation_maps(
            outbound, settings, schema, failures=rel_failures
        )
        docs, truncated = notion_docs.query_all_documents(outbound, settings)

        keep: set[str] = set()
        for d in docs:
            _upsert(db, d, rel_maps, now)
            if d.get("notion_page_id"):
                keep.add(d["notion_page_id"])
        # 상한(_MAX_PAGES)에 걸려 일부만 받아왔다면 prune하지 않는다 — 안 받아온 문서를
        # 'Notion에서 삭제됨'으로 오인해 캐시에서 지우면 목록이 흔들린다(§17.4 최근 정상 보존).
        pruned = _prune(db, keep) if not truncated else PruneResult()

        notes = []
        if truncated:
            notes.append(f"문서가 상한({len(keep)})을 초과해 일부만 동기화했습니다.")
        if rel_failures:
            notes.append(
                "분류 정보를 읽지 못했습니다(" + ", ".join(rel_failures) + "). "
                "이번 회차 문서의 종류, 업무분야, 기술태그가 '기타' 로 저장됐을 수 있습니다."
            )
        if pruned.refused:
            notes.append(pruned.refused)

        bad = bool(pruned.refused or rel_failures)
        state.status = SYNC_ERROR if bad else SYNC_OK
        if not bad:
            state.last_success_at = now
        state.doc_count = len(keep)
        state.pruned_count = pruned.deleted
        state.error = " / ".join(notes) or None
        db.flush()
    except Exception as exc:  # AppError(Notion 오류)·DB 충돌 등 무엇이든 여기서 가둔다
        db.rollback()
        # 롤백으로 state가 detach될 수 있으니 다시 읽어 error를 남긴다(별도 flush).
        fresh = get_or_create_state(db)
        fresh.last_run_at = now
        fresh.status = SYNC_ERROR
        fresh.error = getattr(exc, "message", None) or type(exc).__name__
        db.flush()
        return fresh
    return state
