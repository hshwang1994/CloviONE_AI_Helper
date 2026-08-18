"""문서 캐시 동기화 (§17.2 동기화, §17.4 장애 격리).

Notion "문서" DB 전체를 읽어 relation 이름을 해석하고 로컬 DocumentCache로 upsert 한다.
Notion 장애/미설정이면 캐시를 건드리지 않고 sync 상태만 error로 남긴다 — 기존 목록(마지막
정상 동기화)은 그대로 살아 있고, 티켓 등 다른 기능엔 아무 영향이 없다.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.sync_prune import PruneResult, prune_missing
from app.org.constants import DEFAULT_ORG_ID
from app.team_docs import notion_docs
from app.team_docs.classify import classify
from app.team_docs.models import (
    OWNER_PROJECT,
    OWNER_UNSET,
    SYNC_ERROR,
    SYNC_OK,
    SYNC_STATE_ID,
    DocumentCache,
    DocumentSyncState,
    join_names,
    split_names,
)

logger = logging.getLogger(__name__)


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
        # RBAC 재감사(2026-08-16, SEC-35와 같은 자리): tickets/sync.py:92와 같은 관용 —
        # Notion 동기화 산출물은 이 설치의 단일 Notion 워크스페이스에 귀속되므로
        # DEFAULT_ORG_ID를 명시한다(컬럼 기본값과 결과가 같아도, 우연히 맞는 것과
        # 의도해서 맞는 것은 다르다 — board의 Post가 그 차이로 뚫렸다).
        row = DocumentCache(notion_page_id=pid, org_id=DEFAULT_ORG_ID)
        db.add(row)
    row.url = d.get("url")
    row.title = d.get("title") or ""
    type_list = _name_list(d.get("type_ids") or [], rel_maps.get(notion_docs.PROP_TYPE, {}))
    cat_list = _name_list(d.get("category_ids") or [], rel_maps.get(notion_docs.PROP_CATEGORY, {}))
    row.type_names = join_names(type_list)  # 원본 유형(분류 입력·참고용)
    row.category_names = join_names(cat_list)
    row.project_names = _names(d.get("project_ids") or [], rel_maps.get(notion_docs.PROP_PROJECT, {}))
    # 식별용 id 도 함께 미러링한다 (0060). 이름만 두면 나중에 Portal 프로젝트와 이을 때
    # 이름 비교로 추측하게 되는데, 이름은 바뀌고 중복될 수 있어 그 추측이 틀린다.
    # ⚠️ `owner_kind`/`owner_dept_id`/`owner_project_id` 는 **여기서 절대 안 건드린다** —
    # 그 셋은 Portal 이 소유하는 소속이고, 동기화가 덮으면 사람이 정한 소속이 회차마다
    # 사라진다(`restricted`(0057)·`classification_manual`(0018)과 같은 자리).
    row.project_external_ids = join_names([p for p in (d.get("project_ids") or []) if p])
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


def resolve_project_ownership(db: Session) -> dict[str, int]:
    """외부 project relation 을 **Portal 문서 Ownership 으로 승격**한다 (0060).

    `document_cache.project_external_ids` 는 Notion relation id 를 그대로 적어 둔 원본이다.
    그 원본은 권한의 근거가 못 된다 — 다중값이고, 가리키는 프로젝트가 Portal 에 없을 수도
    있다. 여기서 **정확히 하나로 해석될 때만** `owner_kind='project'` 로 올린다.

    지키는 세 가지:

      * **미지정 문서만 건드린다.** 사람이 Portal 에서 지정한 Ownership(부서/조직/다른
        프로젝트)은 외부 소스가 덮지 않는다 — 그게 "Portal 이 Ownership 의 정본" 의 뜻이다.
      * **임의로 고르지 않는다.** relation 이 둘이면 미지정으로 둔다. 코드가 하나를 고르면
        그 문서는 남의 부서에 정상으로 보이고, 틀려도 아무도 신고하지 않는다.
      * **되돌리지 않는다.** 한 번 project 로 올라간 문서를 relation 이 사라졌다고 다시
        미지정으로 내리지 않는다. 소스가 한 회차 흔들릴 때마다 문서가 통째로 사라진다.

    프로젝트 동기화가 문서 동기화보다 늦게 돌면 그 사이 문서는 미지정이다 — 그래서 문서
    동기화 끝과 프로젝트 동기화 끝 **양쪽에서** 부른다(`app/projects/sync.py`).
    """
    from app.tickets.project_link import portal_project_map

    portal = portal_project_map(db)
    promoted = 0
    # 세션이 `autoflush=False` 다(`app/core/db.py`). 방금 upsert 한 문서는 아직 INSERT 전이라
    # 질의에 안 잡힌다 — 여기서 flush 하지 않으면 **새로 들어온 문서만 골라서** 미지정으로
    # 남고, 증상은 "새 문서가 아무에게도 안 보인다" 로 나타난다.
    db.flush()
    rows = db.execute(
        select(DocumentCache).where(DocumentCache.owner_kind == OWNER_UNSET)
    ).scalars().all()
    for row in rows:
        ids = [i for i in split_names(row.project_external_ids) if i]
        if len(ids) != 1:
            continue
        uid = portal.get(ids[0])
        if not uid:
            continue
        row.owner_kind = OWNER_PROJECT
        row.owner_project_id = uid
        promoted += 1
    return {"unset": len(rows), "promoted": promoted}


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

        # 새로 들어온 문서의 Ownership 을 해석한다 (0060). 해석 못 하면 미지정이고 미지정은
        # 아무에게도 안 보인다 — 그건 진단 화면(`/integrity`)이 목록으로 보여 주고 관리자가
        # Portal 에서 지정한다. 소스가 조직 권한을 정하게 두지는 않는다.
        try:
            owner_counts = resolve_project_ownership(db)
            if owner_counts["promoted"]:
                logger.info("문서 Ownership 해석: %s", owner_counts)
        except Exception:
            logger.exception("문서 Ownership 해석 실패")

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
