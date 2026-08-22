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

from app.core.sync_prune import PruneResult, prune_missing
from app.org.constants import DEFAULT_ORG_ID
from app.reports import notion_source
from app.tickets import notion_write, project_link
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
from app.work import relations


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


def _project_map(
    outbound, settings, schema: dict, *, failed: list[str] | None = None
) -> tuple[dict[str, str], list[dict]]:
    """({프로젝트 page_id: 이름}, [{id, name}] 정렬된 목록).

    프로젝트 조회가 실패해도 티켓 미러링은 계속한다 — 이름 없이라도 목록은 살아 있는 편이 낫다.
    다만 **실패했다는 사실은 알린다**(C4): `failed` 를 주면 거기에 표시한다.

    왜 알려야 하나: 이 맵이 비면 `meta.projects_json` 이 `[]` 가 되는데, **티켓 생성은
    프로젝트를 필수로 요구한다**(`repository_notion.py`). 즉 조회 한 번 실패로 '새 티켓' 폼이
    막혀 티켓을 만들 수 없게 되는데, 동기화 상태는 `ok` 였다. 사용자는 "폼이 고장났다" 고
    신고하고 관리자는 폼 코드를 판다 — 원인은 동기화이고 그 화면은 정상이라고 말하고 있다.
    """
    _, prop = notion_write.schema_prop_for(schema, "project")
    db_id = notion_write.relation_target_db(prop) if prop else None
    if not db_id:
        return {}, []
    try:
        rows = notion_write.query_relation_titles(outbound, settings, db_id)
    except Exception:  # noqa: BLE001 — 프로젝트 이름은 있으면 좋은 값이지 필수가 아니다
        if failed is not None:
            failed.append("프로젝트")
        return {}, []
    rows = [r for r in rows if r.get("id")]
    rows.sort(key=lambda r: (r.get("name") or "￿"))
    return {r["id"]: (r.get("name") or "") for r in rows}, rows


def _upsert(
    db: Session, t: dict, proj_map: dict[str, str], now: datetime,
    portal_projects: dict[str, str] | None = None,
) -> None:
    """파싱된 Notion 행 하나를 캐시에 반영한다(있으면 갱신, 없으면 삽입).

    `portal_projects`(외부 page id → Portal 프로젝트 id)를 주면 소속 해석까지 여기서
    끝난다. 안 주면 해석은 `project_link.reresolve_all()` 이 나중에 한다 — 그때까지
    `project_link` 는 기본값 `unresolved` 라 **닫혀 있다**(열린 채 방치되지 않는다).
    """
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
    # 소속 해석(0060). 원본 relation 은 위 두 줄에 그대로 남고, 권한 계산이 쓰는 것은
    # 아래 두 컬럼뿐이다 — 외부 소스가 바뀌어도 Portal 소유 관계는 이 형태로 유지된다.
    if portal_projects is not None:
        project_link.apply_to_row(row, portal_projects)
    row.assignee_notion_ids = join_names(t.get("assignees") or [])
    # 상위 작업 미러 (0044). **파서는 아직 이 키를 만들지 않는다** — Notion 쪽 읽기는 다음
    # 단계라 그때까지 NULL 로 남는다(있는 척하지 않는다). 자리를 지금 잡는 이유는 진행률의
    # '리프만 세기'가 이 컬럼 없이는 부모와 자식을 구별할 수 없기 때문이다.
    row.parent_page_id = t.get("parent_page_id")
    row.notion_created_time = t.get("created_time")
    row.notion_last_edited = t.get("last_edited")
    row.source = SOURCE_NOTION
    # 돌아왔다 — 지난 회차에 "안 보임" 으로 표시됐더라도 아무 일 없었던 것이 된다(0043).
    row.notion_missing_at = None
    row.synced_at = now
    row.updated_at = now


def _prune(db: Session, keep: set[str], now: datetime) -> PruneResult:
    """Notion에서 사라진(삭제·공유 해제) 티켓을 **표시**한다 — 지우지 않는다(0043).

    자체(native) 티켓 — notion_page_id 가 없는 행 — 은 절대 건드리지 않는다. Notion 조회 결과에
    없는 게 당연하기 때문이다.

    삭제 판단은 `core.sync_prune` 의 바닥을 거친다. Notion 이 빈 결과를 200 으로 돌려주면
    여기서 전 티켓과 그 댓글·첨부·미push 본문이 함께 사라지기 때문이다(거기 주석 참조).

    **왜 지우지 않고 표시하는가**: 그 바닥은 *대량* 손실을 막지만, 티켓 **한 건**이 응답에서
    깜빡이는 것은 정상 삭제로 보여 그대로 지운다. 그러면 CASCADE 가 그 티켓의 댓글·첨부를
    함께 지우는데, 셋 다 Notion 에 없으므로 **재동기화로 돌아오지 않는다.**
    재현: `tests/regression/test_comment_survives_resync.py`.

    표시된 행은 목록에서 즉시 빠지므로 사용자에게는 삭제와 똑같아 보인다. 유예를 넘겨도 안
    돌아오면 `app/core/retention.py` 가 그때 진짜로 지운다.
    """
    rows = db.execute(
        select(TicketCache).where(
            TicketCache.notion_page_id.is_not(None),
            # 이미 표시된 행은 다시 후보로 세지 않는다 — 세면 낙폭 비율이 회차마다 부풀어
            # 바닥이 엉뚱하게 발동하고, 표시 시각이 계속 갱신돼 유예가 영원히 안 끝난다.
            TicketCache.notion_missing_at.is_(None),
        )
    ).scalars().all()

    def _mark(row: TicketCache) -> None:
        row.notion_missing_at = now

    return prune_missing(
        db, rows, keep, key=lambda r: r.notion_page_id, label="티켓", mark=_mark
    )


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
        # 프로젝트 조회 실패는 '새 티켓' 폼을 막는다 — 상태에 올린다(C4).
        rel_failed: list[str] = []
        proj_map, projects = _project_map(outbound, settings, schema, failed=rel_failed)
        portal_projects = project_link.portal_project_map(db)
        tickets, truncated = notion_source.query_all_tasks_paged(outbound, settings)

        keep: set[str] = set()
        for t in tickets:
            _upsert(db, t, proj_map, now, portal_projects)
            if t.get("id"):
                keep.add(t["id"])
        # 상한(_MAX_PAGES)에 걸려 일부만 받아왔다면 prune 하지 않는다 — 안 받아온 티켓을
        # 'Notion에서 삭제됨'으로 오인해 캐시에서 지우면 앱 전체에서 티켓이 사라진다.
        pruned = _prune(db, keep, now) if not truncated else PruneResult()

        # 계층을 `ticket_relations` 로 **파생**시킨다 (S6). `parent_page_id` 는 이
        # 한 방향의 입력이고, 읽는 쪽은 전부 그 표만 본다 — 두 벌이 되면 갈라진 뒤
        # 갈라진 쪽을 아무도 못 고친다(0044 가 적어 둔 그대로다).
        #
        # prune 뒤에 부르는 이유: 사라진 티켓의 관계는 CASCADE 로 이미 없다.
        db.flush()
        relations.sync_parent_links(db, now=now)

        _sync_meta(db, schema, projects, now)

        notes = []
        if truncated:
            notes.append(f"티켓이 상한({len(keep)}건)을 초과해 일부만 동기화했습니다.")
        if rel_failed:
            notes.append(
                "프로젝트 목록을 읽지 못했습니다. '새 티켓' 폼에서 프로젝트를 고를 수 없어 "
                "티켓 생성이 막힙니다(프로젝트는 필수 항목입니다)."
            )
        if pruned.refused:
            notes.append(pruned.refused)

        # prune 을 거부했다는 것은 소스를 믿을 수 없다는 뜻이다. 그걸 ok 로 적으면 화면이
        # '정상'이라 말하는 동안 캐시가 조용히 낡아 간다 — C1 이 눈에 안 띈 이유가 정확히 그것이다.
        bad = bool(pruned.refused or rel_failed)
        state.status = SYNC_ERROR if bad else SYNC_OK
        if not bad:
            state.last_success_at = now
        state.ticket_count = len(keep)
        state.truncated = truncated
        state.pruned_count = pruned.deleted
        state.error = " / ".join(notes) or None
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
