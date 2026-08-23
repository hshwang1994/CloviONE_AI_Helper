"""소스의 행을 PostgreSQL 에 넣는다. **두 번 돌려도 같은 결과다** (S13).

## 세 층으로 나뉜다

1. **표 복사** — 이름이 같고 컬럼이 그대로인 61 표 + 이름만 바뀐 2 표. 옛 `id` 를
   그대로 쓰므로 표 사이 참조가 저절로 맞는다. 재실행은 `ON CONFLICT DO UPDATE` 다.
2. **도메인 이전** — 모양이 바뀐 자리. 티켓의 세 층 이름(D-195)·재채번(D-196)·
   문서 본문(D-198)·첨부(D-250)가 여기다.
3. **다리 놓기** — `legacy_mapping` · `ticket_key_aliases` · `migration_exceptions`.

## 왜 `id` 를 새로 만들지 않는가

옛 앱은 이미 UUID 를 쓴다. 새로 매기면 표 63개의 상호 참조를 전부 다시 이어야 하고,
그 작업 하나가 이 도구의 위험 대부분을 차지한다. **바꿀 이유가 없는 것은 안 바꾼다** —
바꾸는 것은 모양이 실제로 달라진 자리(문서·파일)뿐이고, 거기서만 `legacy_mapping` 이
필요하다.

## 실패한 행 하나가 회차를 멈추지 않는다

일괄 삽입이 제약 위반으로 죽으면 **그 묶음만** 한 행씩 다시 넣어 범인을 가린다. 그렇게
안 하면 1,400행 중 하나 때문에 「감사 로그 이관 실패」만 남고, 어느 행인지는 아무도
모른다. 가려낸 행은 Finding 이 되고 나머지는 들어간다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, ValidationAppError
from app.core.models_base import Base, join_names, new_uuid, split_names, utcnow
from app.knowledge import tags, versions
from app.knowledge.models import (
    SOURCE_MIGRATION,
    VSRC_MIGRATION,
    Document,
    DocumentAttachment,
    KnowledgeSpace,
)
from app.migration import plan as plan_mod
from app.migration import transform
from app.migration.convert import ConvertError, coerce
from app.migration.models import (
    SRC_NOTION,
    SRC_SQLITE,
    T_DOCUMENT,
    T_FILE,
    T_PROJECT,
    T_TICKET,
    LegacyMapping,
)
from app.migration.report import (
    SEVERITY_BLOCKING,
    SEVERITY_CLASSIFIED,
    SEVERITY_NOTE,
    MigrationReport,
    StageResult,
)
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.projects.models import Project
from app.storage import service as storage_service
from app.tickets.models import Ticket
from app.users.models import User
from app.work import keys as keys_mod
from app.work import numbering, project_keys, relations
from app.work.models import (
    ALIAS_LEGACY,
    REL_BLOCKS,
    MigrationException,
    TicketKeyAlias,
)

logger = logging.getLogger("app.migration.load")

# `user_notion_mappings.source` 의 세 번째 값. `workflow` 는 S11 이 걷었고 `manual` 은
# 사람이 지정했다는 뜻이라 여기 쓰면 거짓말이 된다 — 이관이 만든 행은 그렇게 말한다.
MAP_SOURCE_MIGRATION = "migration"

# 이관이 만든 문서가 들어갈 공간. 실측상 문서 110건이 전부 `owner_kind='unset'` 이라
# 하나면 된다. 소유가 붙은 문서가 생기면 `_space_for` 가 그 축으로 공간을 더 만든다.
DEFAULT_SPACE_SLUG = "team-docs"
DEFAULT_SPACE_NAME = "팀 문서"

_BIND_BUDGET = 30_000  # PG 한계는 65,535 다. 절반 아래로 잡아 여유를 둔다.


class LoadAborted(AppError):
    """계속하면 데이터가 더 망가지는 상태. 회차를 세운다."""

    status_code = 500
    code = "migration_load_aborted"
    default_message = "이관을 계속할 수 없습니다."


class Loader:
    """한 회차 동안 세션 하나를 들고 단계를 순서대로 돈다."""

    def __init__(
        self,
        db: Session,
        *,
        report: MigrationReport,
        settings=None,
    ) -> None:
        self.db = db
        self.report = report
        self.settings = settings
        # 「Notion 이 준 page id → 우리 행 id」. 단계 사이에서 재조회를 없앤다.
        self.ticket_by_page: dict[str, str] = {}
        self.project_by_page: dict[str, str] = {}
        self.document_by_page: dict[str, str] = {}
        self._pending_map: list[dict] = []
        # 「이 페이지가 저 페이지를 막는다」. 티켓 적재가 모으고 관계 단계가 쓴다 —
        # 두 단계 사이에 페이지 id 를 우리 id 로 바꿀 표가 완성되기 때문이다.
        self.block_edges: set[tuple[str, str]] = set()
        self._mapping_cache: dict[str, str] | None = None

    # ── 1층: 표 복사 ─────────────────────────────────────────────────────────

    def copy_tables(self, source, classification: plan_mod.Classification) -> None:
        for copy in plan_mod.ordered_copies(classification):
            self._copy_one(source, copy)

    def _copy_one(self, source, copy: plan_mod.TableCopy) -> StageResult:
        started = time.monotonic()
        table = Base.metadata.tables[copy.target]
        source_columns = set(source.columns(copy.source))
        columns = [
            column for column in table.columns
            if column.name in source_columns
            and (copy.source, column.name) not in plan_mod.DROPPED_COLUMNS
            # 뒤 단계가 주인인 컬럼은 복사가 안 건드린다. 이유는 `plan.DERIVED_COLUMNS`.
            and (copy.source, column.name) not in plan_mod.DERIVED_COLUMNS
        ]
        pk = [column.name for column in table.primary_key.columns]
        stage = StageResult(
            name=f"copy {copy.source}" + (f" → {copy.target}" if copy.renamed else "")
        )
        stage.source_rows = source.count(copy.source)

        if not columns or not pk or any(name not in source_columns for name in pk):
            self.report.finding(
                SEVERITY_BLOCKING, "table_shape", copy.source,
                "기본키나 공통 컬럼이 없어 복사할 수 없습니다.",
            )
            self.report.add(stage)
            return stage

        # 자기 자신을 가리키는 FK 가 있으면 부모를 먼저 넣어야 한다. 실측상
        # `org_units.parent_id` 하나지만, 표가 늘어도 따라오게 계산한다.
        self_fk = [
            column.name for column in columns
            for fk in column.foreign_keys
            if fk.column.table.name == table.name
        ]

        batch_size = max(1, _BIND_BUDGET // max(1, len(columns)))
        rows = list(source.rows(copy.source))
        if self_fk:
            rows = _parent_first(rows, key=pk[0], parents=self_fk)

        payload: list[dict] = []
        for row in rows:
            record = self._coerce_row(table, columns, row, where=copy.source)
            if record is None:
                stage.skipped += 1
                continue
            payload.append(record)

        for chunk in _chunks(payload, batch_size):
            inserted, updated = self._upsert(table, columns, pk, chunk, where=copy.source)
            stage.inserted += inserted
            stage.updated += updated
            stage.skipped += len(chunk) - inserted - updated

        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _coerce_row(self, table, columns, row: dict, *, where: str) -> dict | None:
        record: dict = {}
        for column in columns:
            try:
                record[column.name] = coerce(column, row.get(column.name))
            except ConvertError as exc:
                self.report.finding(
                    SEVERITY_BLOCKING, exc.kind, where, exc.message,
                    ref=str(row.get("id") or ""),
                )
                return None
        return record

    def _upsert(self, table, columns, pk, chunk: list[dict], *, where: str
                ) -> tuple[int, int]:
        """묶음 하나. 실패하면 한 행씩 다시 넣어 범인을 가린다."""
        try:
            with self.db.begin_nested():
                return self._upsert_once(table, columns, pk, chunk)
        except (DBAPIError, SQLAlchemyError):
            pass

        inserted = updated = 0
        for record in chunk:
            try:
                with self.db.begin_nested():
                    one_in, one_up = self._upsert_once(table, columns, pk, [record])
                inserted += one_in
                updated += one_up
            except (DBAPIError, SQLAlchemyError) as exc:
                self.report.finding(
                    SEVERITY_BLOCKING, "row_rejected", where,
                    _short(exc), ref=str(record.get(pk[0]) or ""),
                )
        return inserted, updated

    def _upsert_once(self, table, columns, pk, chunk: list[dict]) -> tuple[int, int]:
        stmt = pg_insert(table)
        update_set = {
            column.name: stmt.excluded[column.name]
            for column in columns if column.name not in pk
        }
        stmt = stmt.values(chunk)
        if update_set:
            stmt = stmt.on_conflict_do_update(index_elements=pk, set_=update_set)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=pk)
        # `xmax = 0` 이면 이번에 새로 들어간 행이다. 「몇 건이 새것이고 몇 건이 갱신인가」를
        # 세지 않으면 **재실행이 정말 멱등인지 증명할 수 없다** — 두 번째 회차의 신규가
        # 0 이어야 한다는 것이 그 증명이다.
        rows = self.db.execute(
            stmt.returning(sa.literal_column("(xmax = 0)"))
        ).scalars().all()
        inserted = sum(1 for value in rows if value)
        return inserted, len(rows) - inserted

    # ── 2층: 프로젝트 ────────────────────────────────────────────────────────

    def load_projects(self, notion_rows: list[dict]) -> StageResult:
        """Notion 프로젝트를 미러 위에 덮는다. 미러에 없으면 새로 만든다."""
        started = time.monotonic()
        stage = StageResult(name="projects (Notion)", source_rows=len(notion_rows))
        by_page = {
            project.notion_page_id: project
            for project in self.db.execute(
                sa.select(Project).where(Project.notion_page_id.is_not(None))
            ).scalars()
        }
        for raw in notion_rows:
            parsed = transform.parse_project(raw)
            page_id = parsed["notion_page_id"]
            project = by_page.get(page_id)
            if project is None:
                project = Project(
                    id=new_uuid(), name=parsed["name"] or "(이름 없음)",
                    notion_page_id=page_id,
                )
                self.db.add(project)
                self.db.flush()
                stage.inserted += 1
            else:
                stage.updated += 1
            if parsed["name"]:
                project.name = parsed["name"]
            project.notion_status = parsed["notion_status"]
            project.notion_progress_pct = parsed["notion_progress_pct"]
            project.notion_owner_ids = _join(parsed["notion_owner_ids"])
            project.notion_last_edited = parsed["notion_last_edited"]
            # 아래 다섯은 **앱 정본 컬럼**이다. 미러가 비워 둔 채였고(옛 동기화가 안
            # 읽었다) 소스에는 21건 전부 값이 있다 — 안 옮기면 프로젝트 화면의 기간·
            # 사업 구분·제품이 전부 빈칸으로 열린다.
            if parsed["biz_type"]:
                project.biz_type = parsed["biz_type"]
            if parsed["product"]:
                project.product = parsed["product"]
            if parsed["starts_on"]:
                project.starts_on = parsed["starts_on"]
            if parsed["ends_on"]:
                project.ends_on = parsed["ends_on"]
            if parsed["goal"]:
                project.goal = parsed["goal"]
            self.project_by_page[page_id] = project.id
            self._map(SRC_NOTION, page_id, T_PROJECT, project.id)

        # 미러에는 있는데 Notion 에는 없는 프로젝트. 지우지 않는다 — 붙어 있는 주간
        # 리포트·헬스 이력이 함께 사라지고 그 둘은 Notion 에 없다(모델 주석).
        orphans = sorted(set(by_page) - set(self.project_by_page))
        for page_id in orphans:
            self.report.finding(
                SEVERITY_CLASSIFIED, "project_source_missing", "projects",
                "Notion 응답에 없는 프로젝트입니다. 지우지 않고 그대로 둡니다.",
                ref=page_id,
            )
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def apply_project_keys(self) -> StageResult:
        """확정 Key 20건을 적용한다 (D-243). **골라 주지 않는다.**"""
        started = time.monotonic()
        stage = StageResult(
            name="project keys", source_rows=len(project_keys.CONFIRMED)
        )
        # 예약어(`GIT`)가 먼저 서 있어야 한다. 0003 이 심지만, 빈 DB 로 시작한 회차나
        # 되감았다 올린 DB 에서는 없을 수 있다 — 없으면 `GIT-142` 별칭과 새 canonical 이
        # 같은 문자열이 될 수 있는 문이 열린다.
        keys_mod.seed_reserved(self.db)
        result = project_keys.apply_confirmed(self.db)
        stage.inserted = len(result[project_keys.APPLIED])
        stage.updated = len(result[project_keys.ALREADY])
        for kind in (project_keys.NOT_FOUND, project_keys.AMBIGUOUS, project_keys.OTHER_KEY):
            for entry in result[kind]:
                stage.skipped += 1
                self.report.finding(
                    SEVERITY_CLASSIFIED, f"project_key_{kind}", "projects",
                    f"«{entry['name']}» 에 {entry['key']} 를 붙이지 않았습니다.",
                    ref=entry.get("project_id") or entry.get("current"),
                )
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    # ── 2층: 티켓 ────────────────────────────────────────────────────────────

    def load_tickets(self, notion_rows: list[dict], bodies: dict[str, str]) -> StageResult:
        """Notion 작업을 미러 위에 덮고 **옛 이름을 영구 별칭으로** 남긴다."""
        started = time.monotonic()
        stage = StageResult(name="tickets (Notion)", source_rows=len(notion_rows))
        tickets = {
            ticket.notion_page_id: ticket
            for ticket in self.db.execute(
                sa.select(Ticket).where(Ticket.notion_page_id.is_not(None))
            ).scalars()
        }
        seen: set[str] = set()
        for raw in notion_rows:
            parsed = transform.parse_task(raw)
            page_id = parsed["notion_page_id"]
            if not page_id:
                continue
            seen.add(page_id)
            ticket = tickets.get(page_id)
            if ticket is None:
                ticket = Ticket(id=new_uuid(), notion_page_id=page_id, title="")
                self.db.add(ticket)
                self.db.flush()
                stage.inserted += 1
            else:
                stage.updated += 1

            ticket.title = parsed["title"] or ticket.title or ""
            ticket.url = parsed["url"]
            ticket.status = parsed["status"]
            ticket.priority = parsed["priority"]
            ticket.difficulty = parsed["difficulty"]
            ticket.est_wd = parsed["est_wd"]
            ticket.act_wd = parsed["act_wd"]
            ticket.start_date = parsed["start_date"]
            ticket.due_date = parsed["due_date"]
            ticket.category = parsed["category"]
            ticket.assignee_notion_ids = _join(parsed["assignee_notion_ids"])
            ticket.project_ids = _join(parsed["project_ids"])
            ticket.parent_page_id = parsed["parent_page_id"]
            ticket.notion_ticket_number = parsed["notion_ticket_number"]
            ticket.notion_created_time = parsed["notion_created_time"]
            ticket.notion_last_edited = parsed["notion_last_edited"]
            # 이번 회차에 보였으므로 「사라짐」 표시를 지운다.
            ticket.notion_missing_at = None

            body = bodies.get(page_id)
            # 포털에서 저장한 본문이 있는데 Notion 이 비어 있으면 **포털 쪽이 옳다** —
            # 그 상태는 push 가 실패했다는 뜻이고(`body_sync_error`), Notion 을 정본으로
            # 삼으면 사용자가 쓴 글이 사라진다.
            if body:
                ticket.body_markdown = body
            elif ticket.body_markdown:
                self.report.finding(
                    SEVERITY_NOTE, "body_kept_from_portal", "tickets",
                    "Notion 본문이 비어 포털 본문을 유지했습니다.", ref=page_id,
                )

            for other in parsed["blocked_by_pages"]:
                self.block_edges.add((other, page_id))
            for other in parsed["blocks_pages"]:
                self.block_edges.add((page_id, other))

            if parsed["parent_count"] > 1:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "ticket_multiple_parents", "tickets",
                    f"상위 작업이 {parsed['parent_count']}건이라 첫 번째만 씁니다.",
                    ref=page_id,
                )

            prefix = parsed["legacy_prefix"] or "GIT"
            number = parsed["notion_ticket_number"]
            if number is not None:
                ticket.legacy_key = f"{prefix}-{number}"
            self.ticket_by_page[page_id] = ticket.id
            self._map(SRC_NOTION, page_id, T_TICKET, ticket.id)

        # Notion 응답에 없는 미러 티켓. **지우지 않고 표시만 한다** — 붙어 있는 댓글과
        # 첨부는 Notion 에 없어서 재동기화로 안 돌아온다(0043 의 판단 그대로).
        stamp = utcnow()
        for page_id, ticket in tickets.items():
            if page_id in seen:
                continue
            if ticket.notion_missing_at is None:
                ticket.notion_missing_at = stamp
            stage.skipped += 1

        self.db.flush()
        self._write_aliases()
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _write_aliases(self) -> None:
        """`GIT-142` → 티켓. **영구다** (D-195)."""
        rows = self.db.execute(
            sa.select(Ticket.id, Ticket.legacy_key).where(Ticket.legacy_key.is_not(None))
        ).all()
        if not rows:
            return
        payload = [
            {"alias": legacy_key, "ticket_id": ticket_id,
             "kind": ALIAS_LEGACY, "created_at": utcnow()}
            for ticket_id, legacy_key in rows
        ]
        table = TicketKeyAlias.__table__
        for chunk in _chunks(payload, 2000):
            stmt = pg_insert(table).values(chunk)
            self.db.execute(stmt.on_conflict_do_update(
                index_elements=["alias"],
                set_={"ticket_id": stmt.excluded.ticket_id},
            ))

    # ── 2층: 재채번과 예외 ───────────────────────────────────────────────────

    def renumber(self) -> StageResult:
        """소속을 정하고 번호를 매긴다. **못 정하면 안 매기고 사유를 남긴다** (U11)."""
        started = time.monotonic()
        stage = StageResult(name="renumber + exceptions")

        keyed = {
            project_id
            for (project_id,) in self.db.execute(
                sa.select(Project.id).where(
                    Project.code.is_not(None), Project.archived_at.is_(None)
                )
            ).all()
        }
        by_notion_page = dict(self.project_by_page)
        if not by_notion_page:
            by_notion_page = {
                page_id: project_id
                for page_id, project_id in self.db.execute(
                    sa.select(Project.notion_page_id, Project.id).where(
                        Project.notion_page_id.is_not(None)
                    )
                ).all()
            }

        tickets = self.db.execute(sa.select(Ticket)).scalars().all()
        stage.source_rows = len(tickets)

        buckets: dict[str, list[tuple[str, int | None, str]]] = {}
        existing: dict[str, dict[str, int]] = {}
        verdicts: dict[str, transform.TicketExceptionVerdict] = {}

        for ticket in tickets:
            source_ids = _split(ticket.project_ids)
            resolved = None
            if len(source_ids) == 1:
                resolved = by_notion_page.get(source_ids[0])
            # 미러가 이미 풀어 둔 값이 있으면 그것을 믿는다 — 같은 판단을 두 번 하지
            # 않는다. 다만 **관계가 여럿이면** 미러 값이 있어도 ambiguous 다.
            if resolved is None and len(source_ids) <= 1 and ticket.project_uid:
                resolved = ticket.project_uid
            verdict = transform.classify_ticket_exception(
                project_ids=source_ids,
                resolved_project_id=resolved,
                notion_missing=ticket.notion_missing_at is not None,
            )
            verdicts[ticket.id] = verdict
            if verdict.excepted:
                continue
            if resolved not in keyed:
                # 프로젝트는 정해졌는데 그 프로젝트에 Key 가 없다. 번호를 주면 트리거가
                # 거절한다 — 「미해결」로 분류하고 사람이 Key 를 정하면 다음 회차가 매긴다.
                verdicts[ticket.id] = transform.TicketExceptionVerdict(
                    "unresolved", {"project_id": resolved, "reason": "project_key_missing"}
                )
                continue
            buckets.setdefault(resolved, []).append(
                (ticket.id, ticket.notion_ticket_number, ticket.id)
            )
            if ticket.seq is not None:
                existing.setdefault(resolved, {})[ticket.id] = ticket.seq

        by_id = {ticket.id: ticket for ticket in tickets}
        for project_id, candidates in buckets.items():
            assigned = transform.assign_sequences(
                existing=existing.get(project_id, {}), candidates=candidates
            )
            for ticket_id, seq in assigned.items():
                ticket = by_id[ticket_id]
                changed = ticket.project_uid != project_id or ticket.seq != seq
                ticket.project_uid = project_id
                ticket.project_link = "ok"
                ticket.seq = seq
                if changed:
                    stage.inserted += 1
                else:
                    stage.updated += 1

        excepted = self._write_exceptions(by_id, verdicts)
        stage.skipped = excepted
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _write_exceptions(self, by_id, verdicts) -> int:
        """예외 원장. **미해결은 티켓당 하나**이고, 사라진 사유는 해결로 닫는다."""
        open_rows = {
            row.ticket_id: row
            for row in self.db.execute(
                sa.select(MigrationException).where(
                    MigrationException.resolved_at.is_(None)
                )
            ).scalars()
        }
        stamp = utcnow()
        count = 0
        for ticket_id, verdict in verdicts.items():
            ticket = by_id[ticket_id]
            if not verdict.excepted:
                # 이번 회차에 소속이 정해졌다. 열린 예외가 있으면 닫는다 — 안 닫으면
                # 「몇 건 남았나」가 영원히 안 줄어든다.
                row = open_rows.get(ticket_id)
                if row is not None:
                    row.resolved_at = stamp
                continue
            count += 1
            ticket.project_uid = None
            ticket.seq = None
            ticket.project_link = _link_for(verdict.reason)
            evidence = _json(verdict.evidence)
            row = open_rows.get(ticket_id)
            if row is None:
                self.db.add(MigrationException(
                    id=new_uuid(), ticket_id=ticket_id, reason=verdict.reason,
                    source_evidence=evidence, created_at=stamp,
                ))
            else:
                row.reason = verdict.reason
                row.source_evidence = evidence
        self.db.flush()
        return count

    def seed_counters(self) -> StageResult:
        """`last_seq = MAX(seq)`. **재채번 뒤에 부른다** — 앞에 부르면 아무 일도 안 한다."""
        started = time.monotonic()
        touched = numbering.seed_counters(self.db)
        self.db.commit()
        stage = StageResult(name="ticket counters", updated=touched)
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    # ── 2층: 관계 ────────────────────────────────────────────────────────────

    def load_relations(self) -> StageResult:
        """`parent_page_id` → `subtask_of`. **`relations.sync_parent_links` 하나가 한다.**

        여기서 다시 쓰지 않는 이유는 방향과 순환이다. 방향을 뒤집으면
        `uq_trel_single_parent` 가 「부모가 자식을 하나만」으로 뜻이 바뀌고, 순환을 안
        걸러 내면 WBS 트리를 그리는 코드가 무한히 돈다. 그 둘을 아는 자리는 하나여야
        한다(`app/work/relations.py` · `check_domain_single_source.py`).

        그 함수는 **없어진 관계도 지운다.** 재실행에서 소스의 상위 작업이 바뀌면
        옛 변이 남지 않는다.
        """
        started = time.monotonic()
        pending = int(self.db.execute(sa.text(
            "SELECT count(*) FROM tickets WHERE parent_page_id IS NOT NULL"
        )).scalar_one())
        result = relations.sync_parent_links(self.db)
        blocks = self._sync_block_links()
        stage = StageResult(
            name="ticket relations", source_rows=pending + len(self.block_edges),
            inserted=result["added"] + blocks["added"],
            updated=result["removed"] + blocks["removed"],
            skipped=result["skipped"] + blocks["skipped"],
        )
        if result["skipped"]:
            self.report.finding(
                SEVERITY_CLASSIFIED, "relation_skipped", "ticket_relations",
                f"상위 작업 {result['skipped']}건을 잇지 못했습니다(순환이거나 짝이 없습니다).",
            )
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _sync_block_links(self) -> dict[str, int]:
        """`티켓 선택(선행/후속)` → `ticket_relations(blocks)`.

        Notion 은 이 관계를 **양쪽에** 적어 둔다 — 한쪽만 읽으면 반대쪽만 적힌 30여
        건을 놓친다. 둘 다 읽고 같은 변으로 모으므로 `uq_trel_edge` 가 중복을 막는다.

        `sync_parent_links` 처럼 **없어진 변은 지운다.** 안 지우면 소스에서 뗀 선후
        관계가 재실행마다 그대로 남는다.
        """
        if not self.block_edges and not self._existing_blocks():
            return {"added": 0, "removed": 0, "skipped": 0}
        page_to_id = {
            page_id: ticket_id
            for page_id, ticket_id in self.db.execute(
                sa.select(Ticket.notion_page_id, Ticket.id)
                .where(Ticket.notion_page_id.is_not(None))
            ).all()
        }
        wanted: set[tuple[str, str]] = set()
        for from_page, to_page in self.block_edges:
            from_id = page_to_id.get(from_page)
            to_id = page_to_id.get(to_page)
            if from_id is None or to_id is None or from_id == to_id:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "relation_target_missing", "ticket_relations",
                    "선후 관계의 짝이 이관 대상에 없습니다.", ref=f"{from_page}->{to_page}",
                )
                continue
            wanted.add((from_id, to_id))

        current = self._existing_blocks()
        added = removed = skipped = 0
        for from_id, to_id in sorted(current - wanted):
            if relations.remove(
                self.db, from_ticket_id=from_id, to_ticket_id=to_id, kind=REL_BLOCKS
            ):
                removed += 1
        for from_id, to_id in sorted(wanted - current):
            try:
                relations.add(
                    self.db, from_ticket_id=from_id, to_ticket_id=to_id,
                    kind=REL_BLOCKS, actor_id=None,
                )
                added += 1
            except (ConflictError, ValidationAppError):
                skipped += 1
        self.db.flush()
        return {"added": added, "removed": removed, "skipped": skipped}

    def _existing_blocks(self) -> set[tuple[str, str]]:
        return {
            (row[0], row[1])
            for row in self.db.execute(sa.text(
                "SELECT from_ticket_id, to_ticket_id FROM ticket_relations "
                "WHERE kind = :kind"
            ), {"kind": REL_BLOCKS}).all()
        }

    # ── 2층: 사용자 매핑 ─────────────────────────────────────────────────────

    def load_user_mappings(self, people: dict[str, dict]) -> StageResult:
        """포털 사용자 → Notion 사람. **검증된 이메일이 정확히 하나 맞을 때만** 잇는다.

        표가 사용자 쪽으로 키를 잡고 있다(`user_id` unique · NOT NULL). 그래서 사람을
        돌지 않고 **사용자를 돈다** — 반대로 하면 포털에 없는 Notion 사람마다 주인 없는
        행을 만들게 되고, 그 행은 NOT NULL 을 못 넘는다.

        이름으로 잇지 않는다. 동명이인 하나가 남의 티켓을 자기 것으로 보게 되고, 그
        사고는 화면이 정상으로 보이기 때문에 아무도 신고하지 않는다(U11 과 같은 규칙).

        S11 이 자동 조회 워크플로를 걷은 뒤로 이 표를 채우는 경로가 없었다. 여기서
        채우는 것은 그 워크플로를 되살리는 것이 아니다 — 이관이 한 번 하는 일이다.
        """
        started = time.monotonic()
        stage = StageResult(name="user mappings", source_rows=len(people))
        by_email: dict[str, list[str]] = {}
        for notion_id, person in people.items():
            email = (person.get("email") or "").strip().lower()
            if email:
                by_email.setdefault(email, []).append(notion_id)

        existing = {
            row.user_id: row
            for row in self.db.execute(sa.select(UserNotionMapping)).scalars()
        }
        stamp = utcnow()
        matched: set[str] = set()
        for user_id, email in self.db.execute(
            sa.select(User.id, User.email).where(User.email.is_not(None))
        ).all():
            candidates = by_email.get((email or "").strip().lower(), [])
            if len(candidates) != 1:
                if len(candidates) > 1:
                    self.report.finding(
                        SEVERITY_CLASSIFIED, "user_email_ambiguous",
                        "user_notion_mappings",
                        f"같은 이메일의 Notion 사람이 {len(candidates)}명입니다.",
                        ref=email,
                    )
                continue
            notion_id = candidates[0]
            matched.add(notion_id)
            row = existing.get(user_id)
            if row is None:
                self.db.add(UserNotionMapping(
                    id=new_uuid(), user_id=user_id, notion_user_id=notion_id,
                    notion_email=email, status=STATUS_VERIFIED,
                    source=MAP_SOURCE_MIGRATION, last_verified_at=stamp,
                ))
                stage.inserted += 1
                continue
            if row.notion_user_id and row.notion_user_id != notion_id:
                # 사람이 지정해 둔 짝과 다르다. **덮지 않는다** — 어느 쪽이 옳은지
                # 이 코드가 알 방법이 없고, 틀린 쪽으로 덮으면 남의 티켓이 보인다.
                self.report.finding(
                    SEVERITY_CLASSIFIED, "user_mapping_conflict",
                    "user_notion_mappings",
                    "이미 다른 Notion 사람과 이어져 있어 그대로 둡니다.", ref=user_id,
                )
                stage.skipped += 1
                continue
            row.notion_user_id = notion_id
            row.notion_email = email
            row.status = STATUS_VERIFIED
            row.last_verified_at = stamp
            row.error_message = None
            if not row.source:
                row.source = MAP_SOURCE_MIGRATION
            stage.updated += 1

        # 포털에 짝이 없는 Notion 사람. 실측상 담당자 미해석 티켓이 16% 였고, 그 원인이
        # 여기다 — 지어내지 않고 몇 명인지 남긴다.
        for notion_id in sorted(set(people) - matched):
            person = people[notion_id]
            self.report.finding(
                SEVERITY_CLASSIFIED, "user_unmapped", "user_notion_mappings",
                f"{person.get('name') or notion_id} 의 포털 사용자를 못 찾았습니다.",
                ref=notion_id,
            )
            stage.skipped += 1

        # 이미 `unmapped` 로 남아 있던 행은 건드리지 않는다. 사람이 그렇게 둔 것일 수 있다.
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    # ── 2층: 문서 ────────────────────────────────────────────────────────────

    def load_documents(
        self, notion_rows: list[dict], bodies: dict[str, list[dict]],
        *, taxonomy: dict[str, str],
    ) -> StageResult:
        """`document_cache` + Notion 본문 → `documents` + `document_versions`.

        **다리는 `documents.legacy_page_id` 다** (부분 유니크). 재실행이 그 값으로 같은
        문서를 찾으므로 판이 새로 쌓이지 않는다.
        """
        started = time.monotonic()
        stage = StageResult(name="documents", source_rows=len(notion_rows))
        mirror = {
            row["notion_page_id"]: row
            for row in self.db.execute(sa.text(
                "SELECT notion_page_id, id, document_type, restricted, archived, "
                "owner_kind, owner_dept_id, owner_project_id, title "
                "FROM document_cache WHERE notion_page_id IS NOT NULL"
            )).mappings()
        }
        existing = {
            document.legacy_page_id: document
            for document in self.db.execute(
                sa.select(Document).where(Document.legacy_page_id.is_not(None))
            ).scalars()
        }
        spaces: dict[tuple[str, str | None], KnowledgeSpace] = {}

        for raw in notion_rows:
            parsed = transform.parse_document(raw)
            page_id = parsed["notion_page_id"]
            if not page_id:
                continue
            cached = mirror.get(page_id) or {}
            space = self._space_for(
                spaces,
                owner_kind=(cached.get("owner_kind") or "unset"),
                owner_dept_id=cached.get("owner_dept_id"),
                owner_project_id=cached.get("owner_project_id"),
            )
            document = existing.get(page_id)
            if document is None:
                document = Document(
                    id=new_uuid(), space_id=space.id, legacy_page_id=page_id,
                    title=parsed["title"] or cached.get("title") or "(제목 없음)",
                    source_type=SOURCE_MIGRATION,
                )
                self.db.add(document)
                self.db.flush()
                stage.inserted += 1
            else:
                stage.updated += 1
            document.space_id = space.id
            document.title = parsed["title"] or cached.get("title") or document.title
            document.doc_type = _doc_type(parsed, taxonomy, cached)
            document.confidential = bool(cached.get("restricted"))
            document.archived = bool(parsed["archived"] or cached.get("archived"))
            # 작성자. **이메일로 이어진 사람만** 붙는다 — 이름으로 잇지 않는다(U11).
            author = self._user_for_notion(parsed["author_notion_ids"])
            if author:
                document.created_by = author
            # 카테고리는 태그가 된다. `documents` 에 그 칸이 없고, S7 이 만든 `tags` 가
            # 바로 그 자리다 — 안 옮기면 문서 61건의 분류가 사라진다.
            category_names = [
                (taxonomy.get(cid) or "").strip()
                for cid in parsed["category_ids"]
            ]
            category_names = [name for name in category_names if name]
            if category_names:
                try:
                    with self.db.begin_nested():
                        tags.set_for_document(self.db, document, category_names)
                except AppError as exc:
                    self.report.finding(
                        SEVERITY_CLASSIFIED, "document_tags_rejected", "document_tags",
                        f"카테고리를 태그로 못 붙였습니다: {exc}", ref=page_id,
                    )
            self.document_by_page[page_id] = document.id
            self._map(SRC_NOTION, page_id, T_DOCUMENT, document.id)
            if cached.get("id"):
                self._map(SRC_SQLITE, cached["id"], T_DOCUMENT, document.id)

            self._snapshot(document, bodies.get(page_id) or [])

        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _snapshot(self, document: Document, raw_blocks) -> None:
        """판을 쌓는다. **`versions.snapshot` 하나가 그 일을 한다** (D-198).

        여기서 `DocumentVersion(...)` 를 직접 만들지 않는 이유는 판을 만드는 자리가
        둘이 되면 한쪽이 `version_no` 를 다르게 매기거나 파생을 안 만들기 때문이다.
        그 문서는 이력이 끊긴 채로 남고, 끊긴 이력은 다시 계산해서 복구할 수 없다.
        (`scripts/check_domain_single_source.py` 가 이 규칙을 코드로 확인한다.)

        같은 본문이면 `snapshot` 이 `None` 을 낸다 — 재실행이 판을 안 늘린다. 앞판
        이어붙이기(`carry_from`)도 그 함수 안에 있다(D-247).

        `reindex=False` 인 이유는 그 함수의 docstring 에 있다: 적재 직후 파생 넷은
        비어 있는 것이 정상이고, 색인 레인의 훑기가 스스로 찾아 돈다(D-270 · S9).
        """
        doc = transform.notion_blocks_to_doc(raw_blocks)
        try:
            versions.snapshot(
                self.db, document, doc,
                author_id=None,
                change_reason="옛 시스템에서 옮겼습니다.",
                source=VSRC_MIGRATION,
                reindex=False,
            )
        except ValidationAppError as exc:
            # 본문의 모양이 틀렸다. 문서 한 건이 안 들어가는 것이지 회차가 서는 것은 아니다.
            self.report.finding(
                SEVERITY_BLOCKING, "body_unreadable", "document_versions",
                str(getattr(exc, "message", exc)), ref=document.legacy_page_id,
            )
            return

    def _user_for_notion(self, notion_ids: list[str]) -> str | None:
        """Notion 사람 → 포털 사용자. **정확히 하나일 때만** 답한다.

        `load_user_mappings` 가 만들어 둔 표를 읽는다 — 여기서 다시 이메일을 맞추면
        판정이 두 곳이 되고, 그 둘은 언젠가 갈린다.
        """
        if not notion_ids:
            return None
        if self._mapping_cache is None:
            self._mapping_cache = {
                row.notion_user_id: row.user_id
                for row in self.db.execute(
                    sa.select(UserNotionMapping).where(
                        UserNotionMapping.notion_user_id.is_not(None),
                        UserNotionMapping.status == STATUS_VERIFIED,
                    )
                ).scalars()
            }
        found = [
            self._mapping_cache[nid] for nid in notion_ids if nid in self._mapping_cache
        ]
        return found[0] if len(found) == 1 else None

    def _space_for(self, cache, *, owner_kind, owner_dept_id, owner_project_id
                   ) -> KnowledgeSpace:
        owner_id = (
            owner_dept_id if owner_kind == "department"
            else owner_project_id if owner_kind == "project" else None
        )
        cache_key = (owner_kind, owner_id)
        if cache_key in cache:
            return cache[cache_key]
        slug, name = _space_identity(owner_kind, owner_id)
        space = self.db.execute(
            sa.select(KnowledgeSpace).where(KnowledgeSpace.slug == slug)
        ).scalars().first()
        if space is None:
            space = KnowledgeSpace(
                id=new_uuid(), name=name, slug=slug,
                description="옛 시스템에서 옮긴 문서가 들어 있습니다.",
                owner_kind=owner_kind,
                owner_dept_id=owner_dept_id if owner_kind == "department" else None,
                owner_project_id=owner_project_id if owner_kind == "project" else None,
            )
            self.db.add(space)
            self.db.flush()
        cache[cache_key] = space
        return space

    # ── 2층: 첨부 ────────────────────────────────────────────────────────────

    def load_files(self, attachments: list, fetch) -> StageResult:
        """첨부 바이트를 실제 저장소로 옮긴다 (D-250).

        `store_bytes` 를 지나는 이유는 그것이 **검증 → 저장 → 행** 순서를 아는 유일한
        자리이기 때문이다. 여기서 바이트를 직접 쓰면 체크섬·경로 규칙·저장소 선택이
        두 번째 정의가 된다.

        지원하지 않는 형식(예: 회의 녹음 `.m4a`)은 **거절하고 분류한다.** 업로드 정책을
        이관 때문에 넓히지 않는다 — 그것은 제품 결정이고 S13 의 범위가 아니다.
        """
        started = time.monotonic()
        stage = StageResult(name="attachments", source_rows=len(attachments))
        if not attachments:
            self.report.add(stage)
            return stage
        provider = storage_service.ensure_default_provider(self.db, self.settings)
        done = {
            row.legacy_source_id: row.target_id
            for row in self.db.execute(
                sa.select(LegacyMapping).where(
                    LegacyMapping.legacy_source == SRC_NOTION,
                    LegacyMapping.target_type == T_FILE,
                )
            ).scalars()
        }
        for item in attachments:
            if item.legacy_id in done:
                stage.updated += 1
                continue
            if not item.hosted:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "attachment_external_link", "files",
                    f"바깥 링크라 바이트가 없습니다: {item.name}", ref=item.legacy_id,
                )
                stage.skipped += 1
                continue
            try:
                content = fetch(item.url)
            except AppError as exc:
                self.report.finding(
                    SEVERITY_BLOCKING, "attachment_download_failed", "files",
                    f"{item.name}: {exc}", ref=item.legacy_id,
                )
                stage.skipped += 1
                continue
            owner_ref = self._owner_ref(item.page_id)
            try:
                with self.db.begin_nested():
                    record = storage_service.store_bytes(
                        self.db, filename=item.name, content=content,
                        owner_ref=owner_ref, provider=provider,
                    )
            except AppError as exc:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "attachment_rejected", "files",
                    f"{item.name}: {exc}", ref=item.legacy_id,
                )
                stage.skipped += 1
                continue
            stage.inserted += 1
            self._map(SRC_NOTION, item.legacy_id, T_FILE, record.id)
            document_id = self.document_by_page.get(item.page_id)
            if document_id:
                self._attach_to_document(document_id, record.id, item)
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _owner_ref(self, page_id: str) -> str | None:
        document_id = self.document_by_page.get(page_id)
        if document_id:
            return f"document:{document_id}"
        ticket_id = self.ticket_by_page.get(page_id)
        return f"ticket:{ticket_id}" if ticket_id else None

    def _attach_to_document(self, document_id: str, file_id: str, item) -> None:
        table = DocumentAttachment.__table__
        stmt = pg_insert(table).values([{
            "id": new_uuid(), "document_id": document_id, "file_id": file_id,
            "caption": item.name[:500], "sort_order": (item.index + 1) * 1024,
            "created_by": None, "created_at": utcnow(),
        }])
        self.db.execute(stmt.on_conflict_do_nothing(
            index_elements=["document_id", "file_id"]
        ))

    # ── 3층: 다리 ────────────────────────────────────────────────────────────

    def _map(self, source: str, source_id: str, target_type: str, target_id: str) -> None:
        self._pending_map.append({
            "id": new_uuid(), "legacy_source": source, "legacy_source_id": source_id,
            "target_type": target_type, "target_id": target_id,
            "migrated_at": utcnow(),
        })
        if len(self._pending_map) >= 500:
            self.flush_mappings()

    def flush_mappings(self) -> int:
        rows = self._pending_map
        if not rows:
            return 0
        table = LegacyMapping.__table__
        written = 0
        for chunk in _chunks(rows, 500):
            stmt = pg_insert(table).values(chunk)
            result = self.db.execute(stmt.on_conflict_do_update(
                index_elements=["legacy_source", "legacy_source_id", "target_type"],
                set_={
                    "target_id": stmt.excluded.target_id,
                    "migrated_at": stmt.excluded.migrated_at,
                },
            ).returning(sa.literal_column("1")))
            written += len(result.scalars().all())
        self._pending_map = []
        return written


def _space_identity(owner_kind: str, owner_id: str | None) -> tuple[str, str]:
    if owner_kind == "unset" or not owner_id:
        return DEFAULT_SPACE_SLUG, DEFAULT_SPACE_NAME
    slug = transform.space_slug(owner_kind=owner_kind, owner_id=owner_id)
    return slug, f"{owner_kind} 문서"


def _doc_type(parsed: dict, taxonomy: dict[str, str], cached) -> str | None:
    """문서 유형. Notion relation 이 먼저이고 미러 값이 그 다음이다.

    미러의 `type_names` 는 110건 전부 빈 문자열이었다(INVENTORY 05) — 분류가 미러에
    안 들어와 있다. 그래서 relation id 를 taxonomy 이름으로 푼다.
    """
    for type_id in parsed.get("type_ids") or []:
        name = (taxonomy.get(type_id) or "").strip()
        if name:
            return name[:32]
    fallback = (cached.get("document_type") or "").strip() if cached else ""
    return fallback[:32] or None


def _link_for(reason: str) -> str:
    """예외 사유 → `tickets.project_link`. 화면이 읽는 어휘와 맞춘다."""
    return "ambiguous" if reason == "ambiguous" else "missing"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _join(values: Iterable[str]) -> str:
    return join_names(list(values))


def _split(joined: str | None) -> list[str]:
    return [value for value in split_names(joined or "") if value]


def _chunks(rows: list, size: int):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _parent_first(rows: list[dict], *, key: str, parents: list[str]) -> list[dict]:
    """자기 참조가 있는 표를 부모 먼저 정렬한다. 순환은 마지막에 둔다."""
    by_id = {row.get(key): row for row in rows}
    out: list[dict] = []
    placed: set = set()

    def place(row_id, seen: set) -> None:
        if row_id in placed or row_id in seen or row_id not in by_id:
            return
        seen.add(row_id)
        row = by_id[row_id]
        for column in parents:
            parent = row.get(column)
            if parent and parent != row_id:
                place(parent, seen)
        if row_id not in placed:
            placed.add(row_id)
            out.append(row)

    for row in rows:
        place(row.get(key), set())
    # 키가 없는 행(있으면 안 되지만 소스가 그럴 수 있다)은 뒤에 붙인다.
    out.extend(row for row in rows if row.get(key) not in placed)
    return out


def _short(exc: Exception, limit: int = 200) -> str:
    text = str(getattr(exc, "orig", exc)).strip().replace("\n", " ")
    return text[:limit]
