"""티켓 캐시 동기화 (PLAN §A, §7.4 장애 격리 — team_docs/sync.py 와 같은 구조).

Notion "작업" DB 전체를 한 번에 읽어 relation(프로젝트) 이름을 해석하고 로컬 TicketCache 로
upsert 한다. 폼 드롭다운이 쓰는 스키마 파생값(상태·우선순위·난이도 옵션 + 프로젝트 목록)도 같은
왕복에서 TicketMetaCache 에 담는다 — 티켓만 캐시하고 이걸 두면 '새 티켓' 폼이 계속 느리다.

Notion 장애/미설정이면 캐시를 건드리지 않고 sync 상태에만 error 를 남긴다 — 기존 목록(마지막
정상 동기화)은 그대로 살아 있고 다른 기능엔 아무 영향이 없다. 예외는 절대 밖으로 나가지 않는다
(워커 tick 이 죽으면 스케줄러·하트비트까지 함께 멈춘다).
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.org.constants import DEFAULT_ORG_ID
from app.reports import notion_source
from app.tickets import notion_write
from app.tickets.models import (
    META_CACHE_ID,
    SOURCE_NOTION,
    SYNC_ERROR,
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketMetaCache,
    TicketSyncState,
    join_names,
)


def get_or_create_state(db: Session) -> TicketSyncState:
    state = db.get(TicketSyncState, SYNC_STATE_ID)
    if state is None:
        state = TicketSyncState(id=SYNC_STATE_ID)
        db.add(state)
        db.flush()
    return state


def get_or_create_meta(db: Session) -> TicketMetaCache:
    meta = db.get(TicketMetaCache, META_CACHE_ID)
    if meta is None:
        meta = TicketMetaCache(id=META_CACHE_ID)
        db.add(meta)
        db.flush()
    return meta


def _project_map(outbound, settings, schema: dict) -> tuple[dict[str, str], list[dict]]:
    """({프로젝트 page_id: 이름}, [{id, name}] 정렬된 목록).

    프로젝트 조회 실패는 치명적이지 않다 — 이름 없이 티켓만이라도 미러링되게 빈 값으로 흘린다
    (기존 실시간 경로의 _project_names_map 과 같은 관용).
    """
    _, prop = notion_write.schema_prop_for(schema, "project")
    db_id = notion_write.relation_target_db(prop) if prop else None
    if not db_id:
        return {}, []
    try:
        rows = notion_write.query_relation_titles(outbound, settings, db_id)
    except Exception:  # noqa: BLE001 — 프로젝트 이름은 있으면 좋은 값이지 필수가 아니다
        return {}, []
    rows = [r for r in rows if r.get("id")]
    rows.sort(key=lambda r: (r.get("name") or "￿"))
    return {r["id"]: (r.get("name") or "") for r in rows}, rows


def _upsert(db: Session, t: dict, proj_map: dict[str, str], now: datetime) -> None:
    """파싱된 Notion 행 하나를 캐시에 반영한다(있으면 갱신, 없으면 삽입)."""
    pid = t.get("id")
    if not pid:
        return
    row = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == pid)
    ).scalar_one_or_none()
    if row is None:
        row = TicketCache(notion_page_id=pid, org_id=DEFAULT_ORG_ID, created_at=now)
        db.add(row)
    project_ids = [p for p in (t.get("project_ids") or []) if p]
    row.notion_ticket_number = t.get("tid")
    row.url = t.get("url")
    row.title = t.get("title") or ""
    row.status = t.get("status")
    row.priority = t.get("priority")
    row.difficulty = t.get("difficulty")
    row.est_wd = t.get("est_wd")
    row.act_wd = t.get("act_wd")
    row.due_date = t.get("due")
    row.start_date = t.get("start")
    row.category = t.get("category")
    row.project_ids = join_names(project_ids)
    row.project_names = join_names([proj_map.get(p, "") for p in project_ids])
    row.assignee_notion_ids = join_names(t.get("assignees") or [])
    row.notion_created_time = t.get("created_time")
    row.notion_last_edited = t.get("last_edited")
    row.source = SOURCE_NOTION
    row.synced_at = now
    row.updated_at = now


def _prune(db: Session, keep: set[str]) -> None:
    """Notion에서 사라진(삭제·공유 해제) 티켓은 캐시에서도 지운다.

    자체(native) 티켓 — notion_page_id 가 없는 행 — 은 절대 건드리지 않는다. Notion 조회 결과에
    없는 게 당연하기 때문이다.
    """
    rows = db.execute(
        select(TicketCache).where(TicketCache.notion_page_id.is_not(None))
    ).scalars().all()
    for row in rows:
        if row.notion_page_id not in keep:
            db.delete(row)


def _sync_meta(db: Session, schema: dict, projects: list[dict], now: datetime) -> None:
    """폼 드롭다운용 스키마 파생값(옵션 목록 + 프로젝트)을 싱글턴에 담는다."""

    def opts(field: str) -> list[str]:
        _, prop = notion_write.schema_prop_for(schema, field)
        return notion_write.option_names(prop) if prop else []

    meta = get_or_create_meta(db)
    meta.statuses = join_names(opts("status"))
    meta.priorities = join_names(opts("priority"))
    meta.difficulties = join_names(opts("difficulty"))
    meta.projects_json = json.dumps(
        [{"id": r.get("id"), "name": r.get("name") or ""} for r in projects],
        ensure_ascii=False,
    )
    meta.synced_at = now
    meta.updated_at = now


def sync_tickets(db: Session, *, outbound, settings, now: datetime) -> TicketSyncState:
    """전체 동기화. 어떤 단계에서 실패해도 예외를 밖으로 던지지 않고 상태에 error 로 기록만
    한다 — 호출측(워커 tick)은 절대 크래시하지 않고 캐시(마지막 정상)가 그대로 남는다.
    fetch 뿐 아니라 upsert/prune/flush(동시 sync 충돌 등)까지 통째로 가둔다."""
    state = get_or_create_state(db)
    state.last_run_at = now
    try:
        schema = notion_write.fetch_schema(outbound, settings)
        proj_map, projects = _project_map(outbound, settings, schema)
        tickets, truncated = notion_source.query_all_tasks_paged(outbound, settings)

        keep: set[str] = set()
        for t in tickets:
            _upsert(db, t, proj_map, now)
            if t.get("id"):
                keep.add(t["id"])
        # 상한(_MAX_PAGES)에 걸려 일부만 받아왔다면 prune 하지 않는다 — 안 받아온 티켓을
        # 'Notion에서 삭제됨'으로 오인해 캐시에서 지우면 앱 전체에서 티켓이 사라진다.
        if not truncated:
            _prune(db, keep)

        _sync_meta(db, schema, projects, now)

        state.status = SYNC_OK
        state.last_success_at = now
        state.ticket_count = len(keep)
        state.truncated = truncated
        state.error = (
            None if not truncated
            else f"티켓이 상한({len(keep)}건)을 초과해 일부만 동기화했습니다."
        )
        state.updated_at = now
        db.flush()
    except Exception as exc:  # AppError(Notion 오류)·DB 충돌 등 무엇이든 여기서 가둔다
        db.rollback()
        # 롤백으로 state 가 detach 될 수 있으니 다시 읽어 error 를 남긴다(별도 flush).
        # last_success_at 은 손대지 않는다 — 캐시가 '언제까지 정상이었는지'가 staleness 표시의
        # 근거이고, 실패했다고 그 사실이 사라지면 화면이 신선도를 거짓말한다.
        fresh = get_or_create_state(db)
        fresh.last_run_at = now
        fresh.status = SYNC_ERROR
        fresh.error = getattr(exc, "message", None) or type(exc).__name__
        fresh.updated_at = now
        db.flush()
        return fresh
    return state
