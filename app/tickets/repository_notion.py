"""TicketRepository 의 Notion 구현 (§7.1.C).

**Notion 이라는 구현 세부가 사는 유일한 티켓 모듈이다** — 속성 이름, 스키마 옵션, 페이지네이션,
쓰기 페이로드가 전부 여기 안에만 있다. 서비스·라우터·스프린트·리포트는 도메인 DTO만 본다.

읽기 전략(설정 `ticket_source`):
  * `notion_cache`(기본) — 로컬 미러(ticket_cache)를 읽는다. 미러가 비었거나 한 번도 성공적으로
    동기화되지 않았으면 실시간 Notion 으로 폴백한다(첫 기동·마이그레이션 직후에도 화면이 빈
    목록으로 보이지 않게).
  * `notion` — 캐시를 아예 보지 않는 **운영 킬 스위치**. 캐시 도입 전과 완전히 같은 실시간 경로다.

쓰기는 어느 모드에서든 항상 Notion 실시간이다(정본은 아직 Notion). 성공하면 그 자리에서 캐시
행을 같이 고친다(write-through) — 안 그러면 "방금 만든 티켓이 목록에 없다"가 된다.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.core.models_base import NAMES_SEP, utcnow
from app.core.notion_blocks import markdown_to_blocks
from app.org.constants import DEFAULT_ORG_ID
from app.reports import notion_source
from app.tickets import notion_write
from app.tickets.models import (
    META_CACHE_ID,
    SOURCE_NOTION,
    SYNC_STATE_ID,
    TicketCache,
    TicketMetaCache,
    TicketSyncState,
    join_names,
    split_names,
)
from app.tickets.repository import (
    ProjectRef,
    SyncStatus,
    TicketDraft,
    TicketDTO,
    TicketList,
    TicketMeta,
)

# 상태 기본값 — 스키마에 '계획'이 있으면 그것, 없으면 첫 옵션.
_DEFAULT_STATUS = "계획"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _token(value: str) -> str:
    """sentinel-wrapped 토큰 하나 — LIKE contains 로 '정확한 토큰' 매칭을 하기 위한 형태."""
    return NAMES_SEP + value + NAMES_SEP


class NotionTicketRepository:
    """ticket_cache 를 읽고 Notion 에 쓰는 구현체."""

    def __init__(self, settings, outbound, *, use_cache: bool = True) -> None:
        self._settings = settings
        self._outbound = outbound
        self.use_cache = use_cache

    # ── 캐시 가용성 ──────────────────────────────────────────────────────────

    def _cache_ready(self, db: Session) -> tuple[bool, TicketSyncState | None]:
        """(캐시로 답해도 되는가, 동기화 상태). 한 번도 성공 못 했거나 비었으면 실시간으로 간다."""
        if not self.use_cache or db is None:
            return False, None
        state = db.get(TicketSyncState, SYNC_STATE_ID)
        if state is None or state.last_success_at is None:
            return False, state
        count = db.execute(select(func.count()).select_from(TicketCache)).scalar_one()
        return bool(count), state

    def sync_state(self, db: Session) -> SyncStatus | None:
        """캐시로 답할 수 있을 때만 신선도를 돌려준다.

        실시간으로 답한 응답에 미러 상태를 실으면 거짓말이 된다 — 그 응답은 미러를 안 봤다.
        """
        ready, state = self._cache_ready(db)
        return self._sync_status(state) if ready else None

    @staticmethod
    def _sync_status(state: TicketSyncState | None) -> SyncStatus | None:
        if state is None:
            return None
        return SyncStatus(
            status=state.status,
            last_run_at=_iso(state.last_run_at),
            last_success_at=_iso(state.last_success_at),
            ticket_count=state.ticket_count,
            truncated=bool(state.truncated),
            error=state.error,
        )

    # ── DTO 변환 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _from_cache(row: TicketCache) -> TicketDTO:
        return TicketDTO(
            page_id=row.notion_page_id,
            uid=row.id,
            number=row.notion_ticket_number,
            url=row.url,
            title=row.title or "",
            status=row.status,
            due=row.due_date,
            est_wd=row.est_wd,
            act_wd=row.act_wd,
            difficulty=row.difficulty,
            priority=row.priority,
            project_ids=tuple(split_names(row.project_ids)),
            project_names=tuple(split_names(row.project_names)),
            assignee_ids=tuple(split_names(row.assignee_notion_ids)),
            body_markdown=row.body_markdown,
            source=row.source or SOURCE_NOTION,
        )

    @staticmethod
    def _from_notion(parsed: dict, proj_map: dict[str, str] | None = None) -> TicketDTO:
        """notion_source._parse_row 결과 → DTO. proj_map 이 없으면 프로젝트 이름은 비운다
        (오늘의 실시간 경로와 정확히 같은 동작 — 쓰기 응답에는 이름을 붙이지 않는다)."""
        proj_map = proj_map or {}
        project_ids = tuple(p for p in (parsed.get("project_ids") or []) if p)
        names = tuple(n for n in (proj_map.get(p) for p in project_ids) if n)
        return TicketDTO(
            page_id=parsed.get("id"),
            uid=None,  # 실시간으로 읽은 티켓에는 아직 자체 id 가 없다
            number=parsed.get("tid"),
            url=parsed.get("url"),
            title=parsed.get("title") or "",
            status=parsed.get("status"),
            due=parsed.get("due"),
            est_wd=parsed.get("est_wd"),
            act_wd=parsed.get("act_wd"),
            difficulty=parsed.get("difficulty"),
            priority=parsed.get("priority"),
            project_ids=project_ids,
            project_names=names,
            assignee_ids=tuple(parsed.get("assignees") or []),
            source=SOURCE_NOTION,
        )

    # ── 실시간 보조 ──────────────────────────────────────────────────────────

    def _live_project_map(self, db: Session) -> dict[str, str]:
        """{프로젝트 page_id: 이름}. 실패는 치명적이지 않다 — 이름 없이 티켓만이라도 보인다."""
        try:
            return {p.id: p.name for p in self.projects(db) if p.id}
        except Exception:  # noqa: BLE001 — 이름 해석 실패로 목록 전체를 죽이지 않는다
            return {}

    def _live_list(self, db: Session, rows: list[dict]) -> TicketList:
        proj_map = self._live_project_map(db)
        return TicketList(
            tickets=tuple(self._from_notion(r, proj_map) for r in rows),
            from_cache=False,
            sync=None,
        )

    def _cached_list(self, db: Session, stmt, state: TicketSyncState | None) -> TicketList:
        # 마감 빠른 순, 없으면 뒤로, 같으면 티켓 번호 순(Notion 정렬과 같은 순서 + 결정론적 tie-break).
        stmt = stmt.order_by(
            TicketCache.due_date.asc().nulls_last(),
            TicketCache.notion_ticket_number.asc().nulls_last(),
        )
        rows = db.execute(stmt).scalars().all()
        return TicketList(
            tickets=tuple(self._from_cache(r) for r in rows),
            from_cache=True,
            sync=self._sync_status(state),
        )

    # ── 읽기 ─────────────────────────────────────────────────────────────────

    def list_by_assignee(self, db: Session, *, assignee_id: str) -> TicketList:
        ready, state = self._cache_ready(db)
        if ready:
            stmt = select(TicketCache).where(
                TicketCache.assignee_notion_ids.contains(_token(assignee_id), autoescape=True)
            )
            return self._cached_list(db, stmt, state)
        rows = notion_source.query_tasks_by_assignee(
            self._outbound, self._settings, notion_user_id=assignee_id
        )
        return self._live_list(db, rows)

    def list_unassigned(self, db: Session) -> TicketList:
        ready, state = self._cache_ready(db)
        if ready:
            stmt = select(TicketCache).where(TicketCache.assignee_notion_ids == "")
            return self._cached_list(db, stmt, state)
        rows = notion_source.query_unassigned_tasks(self._outbound, self._settings)
        return self._live_list(db, rows)

    def list_all(self, db: Session) -> TicketList:
        ready, state = self._cache_ready(db)
        if ready:
            return self._cached_list(db, select(TicketCache), state)
        rows = notion_source.query_all_tasks(self._outbound, self._settings)
        return self._live_list(db, rows)

    def list_for_period(self, db: Session, *, start: str, end: str) -> TicketList:
        """마감일이 [start, end) 인 티켓. 날짜는 ISO 문자열이라 문자열 비교로 범위가 맞다."""
        ready, state = self._cache_ready(db)
        if ready:
            stmt = select(TicketCache).where(
                TicketCache.due_date.is_not(None),
                TicketCache.due_date >= start,
                TicketCache.due_date < end,
            )
            return self._cached_list(db, stmt, state)
        rows = notion_source.query_tasks_for_period(
            self._outbound, self._settings, start_date=start, end_date=end
        )
        return self._live_list(db, rows)

    def get(self, db: Session, *, page_id: str) -> TicketDTO:
        """상세 화면용 단건. 상세는 늘 실시간이다 — 온디맨드 1건이라 캐시 이득이 없고,
        사용자가 '원본 열기' 직전에 보는 값이라 가장 신선해야 한다."""
        parsed = notion_write.fetch_ticket(self._outbound, self._settings, page_id)
        dto = self._from_notion(parsed, self._live_project_map(db))
        # 킬 스위치(use_cache=False)일 때는 캐시를 아예 보지 않는다 — '캐시 도입 전과 같은 경로'가
        # 이 스위치의 유일한 약속이라, 자체 id 하나를 얻자고 캐시를 읽으면 그 약속이 깨진다.
        cached = self._cache_row(db, page_id) if self.use_cache else None
        if cached is None:
            return dto
        # 자체 id(uid)와 본문 정본은 캐시에만 있다 — 값 자체는 방금 읽은 실시간 것이 이긴다.
        return replace(dto, uid=cached.id, body_markdown=cached.body_markdown)

    def get_live(self, db: Session, *, page_id: str) -> TicketDTO:
        """소유권 판정·감사 스냅샷용. 캐시를 믿지 않고 '지금'의 값을 소스에서 읽는다."""
        parsed = notion_write.fetch_ticket(self._outbound, self._settings, page_id)
        return self._from_notion(parsed)

    def body_blocks(self, db: Session, *, page_id: str) -> list[dict]:
        return notion_write.fetch_page_blocks(self._outbound, self._settings, page_id)

    def meta(self, db: Session | None) -> TicketMeta:
        row = db.get(TicketMetaCache, META_CACHE_ID) if (self.use_cache and db is not None) else None
        if row is not None and row.synced_at is not None:
            return TicketMeta(
                statuses=tuple(split_names(row.statuses)),
                priorities=tuple(split_names(row.priorities)),
                difficulties=tuple(split_names(row.difficulties)),
            )
        schema = notion_write.fetch_schema(self._outbound, self._settings)
        return TicketMeta(
            statuses=tuple(self._options(schema, "status")),
            priorities=tuple(self._options(schema, "priority")),
            difficulties=tuple(self._options(schema, "difficulty")),
        )

    def projects(self, db: Session | None) -> list[ProjectRef]:
        row = db.get(TicketMetaCache, META_CACHE_ID) if (self.use_cache and db is not None) else None
        if row is not None and row.synced_at is not None:
            try:
                data = json.loads(row.projects_json or "[]")
            except ValueError:
                data = []
            return [
                ProjectRef(id=str(d.get("id")), name=d.get("name") or "")
                for d in data
                if isinstance(d, dict) and d.get("id")
            ]
        return self._live_projects()

    def _live_projects(self) -> list[ProjectRef]:
        """작업 DB 스키마의 '프로젝트' relation 대상 DB를 자동 발견해 조회한다."""
        schema = notion_write.fetch_schema(self._outbound, self._settings)
        _, prop = notion_write.schema_prop_for(schema, "project")
        db_id = notion_write.relation_target_db(prop) if prop else None
        if not db_id:
            return []
        rows = [
            r for r in notion_write.query_relation_titles(self._outbound, self._settings, db_id)
            if r.get("id")
        ]
        # 이름 있는 것 먼저, 이름 기준 정렬. 이름 없는(제목 빈) 프로젝트는 뒤로.
        rows.sort(key=lambda r: (r.get("name") or "￿"))
        return [ProjectRef(id=r["id"], name=r.get("name") or "") for r in rows]

    @staticmethod
    def _options(schema: dict, field: str) -> list[str]:
        _, prop = notion_write.schema_prop_for(schema, field)
        return notion_write.option_names(prop) if prop else []

    # ── 쓰기 ─────────────────────────────────────────────────────────────────

    def create(self, db: Session, *, draft: TicketDraft, now: datetime | None = None) -> TicketDTO:
        schema = notion_write.fetch_schema(self._outbound, self._settings)
        properties: dict = {}

        tname, tprop = notion_write.schema_prop_for(schema, "title")
        if not tprop:
            raise ValidationAppError("작업 DB에서 '제목' 속성을 찾지 못했습니다.")
        properties[tname] = notion_write.property_value(tprop, draft.title)

        sname, sprop = notion_write.schema_prop_for(schema, "status")
        if sprop:
            options = notion_write.option_names(sprop)
            status_val = draft.status or None
            if status_val:
                if options and status_val not in options:
                    raise ValidationAppError(
                        f"진행상태 값이 올바르지 않습니다. 허용: {', '.join(options)}"
                    )
            else:
                status_val = (
                    _DEFAULT_STATUS
                    if (not options or _DEFAULT_STATUS in options)
                    else options[0]
                )
            mapped = notion_write.property_value(sprop, status_val)
            if mapped is not None:
                properties[sname] = mapped

        for field_name, label in (("priority", "우선순위"), ("difficulty", "난이도")):
            val = getattr(draft, field_name, None)
            if not val:
                continue
            pname, prop = notion_write.schema_prop_for(schema, field_name)
            if not prop:
                continue
            options = notion_write.option_names(prop)
            if options and val not in options:
                raise ValidationAppError(f"{label} 값이 올바르지 않습니다. 허용: {', '.join(options)}")
            properties[pname] = notion_write.property_value(prop, val)

        if draft.est_wd is not None:
            ename, eprop = notion_write.schema_prop_for(schema, "est_wd")
            if eprop:
                properties[ename] = notion_write.property_value(eprop, draft.est_wd)
        if draft.due_date:
            dname, dprop = notion_write.schema_prop_for(schema, "due_date")
            if dprop:
                properties[dname] = notion_write.property_value(dprop, draft.due_date)

        if draft.assignee_ids:
            pname, pprop = notion_write.schema_prop_for(schema, "assignee_notion_ids")
            if pprop:
                properties[pname] = notion_write.property_value(pprop, list(draft.assignee_ids))

        # 프로젝트 속성이 스키마에 있으면 필수로 요구한다(고아 티켓 방지).
        prj_name, prj_prop = notion_write.schema_prop_for(schema, "project")
        if prj_prop and notion_write.relation_target_db(prj_prop):
            if not draft.project_id:
                raise ValidationAppError("프로젝트를 선택하세요.")
            properties[prj_name] = notion_write.property_value(prj_prop, [draft.project_id])

        children = (
            markdown_to_blocks(draft.description_markdown)
            if draft.description_markdown
            else None
        )
        created = notion_write.create_page(
            self._outbound, self._settings,
            parent_database_id=self._settings.notion_tasks_database_id,
            properties=properties, children=children,
        )
        dto = self._from_notion(created)
        return self._write_through(db, dto, body_markdown=draft.description_markdown, now=now)

    def update(
        self, db: Session, *, page_id: str, changes: dict, now: datetime | None = None
    ) -> TicketDTO:
        """도메인 키(status/priority/difficulty/est_wd/due_date/assignee_ids)만 받는다."""
        if not changes:
            raise ValidationAppError("변경할 내용이 없습니다.")
        schema = notion_write.fetch_schema(self._outbound, self._settings)
        properties: dict = {}
        for key, value in changes.items():
            names = notion_write.EDIT_PROP_ALIASES.get(key)
            if not names:
                continue  # 알 수 없는 키(스키마가 forbid 하므로 실제로는 오지 않음)
            pname, prop = notion_write.schema_prop(schema, names)
            if not prop:
                raise ValidationAppError(f"작업 DB에서 '{names[0]}' 속성을 찾지 못했습니다.")

            if key == "assignee_notion_ids":
                mapped = notion_write.property_value(prop, list(value or []))
            elif key == "status":
                if not value:
                    raise ValidationAppError("진행상태는 비울 수 없습니다.")
                allowed = notion_write.option_names(prop)
                if allowed and value not in allowed:
                    raise ValidationAppError(
                        f"진행상태 값이 올바르지 않습니다. 허용: {', '.join(allowed)}"
                    )
                mapped = notion_write.property_value(prop, value)
            elif key in ("difficulty", "priority"):
                if value:
                    allowed = notion_write.option_names(prop)
                    if allowed and value not in allowed:
                        label = "난이도" if key == "difficulty" else "우선순위"
                        raise ValidationAppError(
                            f"{label} 값이 올바르지 않습니다. 허용: {', '.join(allowed)}"
                        )
                mapped = notion_write.property_value(prop, value)  # 빈 값 → select 지움
            else:  # est_wd, due_date
                mapped = notion_write.property_value(prop, value)

            if mapped is None:
                raise ValidationAppError(f"'{names[0]}' 값을 적용할 수 없습니다.")
            properties[pname] = mapped

        updated = notion_write.update_ticket_properties(
            self._outbound, self._settings, page_id=page_id, properties=properties
        )
        return self._write_through(db, self._from_notion(updated), now=now)

    def archive(self, db: Session | None, *, page_id: str) -> None:
        """소스 원본을 보관처리한다. db 를 주면 캐시 행도 바로 지운다(안 주면 다음 동기화가 지운다)."""
        notion_write.archive_page(self._outbound, self._settings, page_id=page_id)
        if db is None:
            return
        row = self._cache_row(db, page_id)
        if row is not None:
            # 다음 동기화가 어차피 지우지만, 그 사이(기본 180초) 목록에 되살아나 보이면 안 된다.
            db.delete(row)
            db.flush()

    # ── write-through ────────────────────────────────────────────────────────

    def _cache_row(self, db: Session | None, page_id: str | None) -> TicketCache | None:
        if not page_id or db is None:
            return None
        return db.execute(
            select(TicketCache).where(TicketCache.notion_page_id == page_id)
        ).scalar_one_or_none()

    def _cached_project_names(self, db: Session, project_ids: tuple[str, ...]) -> list[str]:
        """프로젝트 이름을 **메타 캐시에서** 채운다 — 쓰기 경로에 Notion 왕복을 더하지 않는다."""
        if not project_ids:
            return []
        row = db.get(TicketMetaCache, META_CACHE_ID) if db is not None else None
        if row is None or row.synced_at is None:
            return []
        try:
            data = json.loads(row.projects_json or "[]")
        except ValueError:
            return []
        name_by_id = {
            d.get("id"): (d.get("name") or "") for d in data if isinstance(d, dict)
        }
        return [n for n in (name_by_id.get(p) for p in project_ids) if n]

    def _write_through(
        self, db: Session, dto: TicketDTO, *, body_markdown: str | None = None,
        now: datetime | None = None,
    ) -> TicketDTO:
        """쓰기 직후 캐시 행을 같은 요청 안에서 고친다.

        이게 없으면 "방금 만든 티켓이 목록에 안 보인다"가 된다 — 다음 동기화(기본 180초)까지
        캐시가 그 티켓을 모르기 때문이다. 응답 DTO 는 자체 id(uid)만 채워 돌려준다.
        """
        page_id = dto.page_id
        if not page_id or db is None:
            return dto
        stamp = now or utcnow()
        row = self._cache_row(db, page_id)
        if row is None:
            row = TicketCache(notion_page_id=page_id, org_id=DEFAULT_ORG_ID, created_at=stamp)
            db.add(row)
        row.notion_ticket_number = dto.number
        row.url = dto.url
        row.title = dto.title
        row.status = dto.status
        row.priority = dto.priority
        row.difficulty = dto.difficulty
        row.est_wd = dto.est_wd
        row.act_wd = dto.act_wd
        row.due_date = dto.due
        row.project_ids = join_names(dto.project_ids)
        # 이름은 DTO 에 없을 수 있다(쓰기 응답은 relation 이름을 해석하지 않는다) — 메타 캐시로 채운다.
        names = list(dto.project_names) or self._cached_project_names(db, dto.project_ids)
        row.project_names = join_names(names)
        row.assignee_notion_ids = join_names(dto.assignee_ids)
        if body_markdown is not None:
            row.body_markdown = body_markdown
        row.source = SOURCE_NOTION
        row.synced_at = stamp
        row.updated_at = stamp
        db.flush()
        return replace(dto, uid=row.id, body_markdown=row.body_markdown)
