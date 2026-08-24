"""소스의 행을 PostgreSQL 에 넣는다. **두 번 돌려도 같은 결과다** (S13).

## 세 층으로 나뉜다

1. **표 복사** — 이름이 같고 컬럼이 그대로인 61 표 + 이름만 바뀐 2 표. 옛 `id` 를
   그대로 쓰므로 표 사이 참조가 저절로 맞는다. 재실행은 `ON CONFLICT DO UPDATE` 다.
2. **도메인 이전** — 모양이 바뀐 자리. 프로젝트 코드(D-282)·재채번(D-196)·
   문서 본문(D-198)·첨부(D-250)가 여기다.
3. **다리 놓기** — `legacy_mapping` · `migration_exceptions`.

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
from app.core.uploads import NS_TICKET, save_upload
from app.core.ownership import (
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
    OWNER_UNSET,
)
from app.knowledge import tags, versions
from app.knowledge.models import (
    SOURCE_MIGRATION,
    VSRC_MIGRATION,
    Document,
    DocumentAttachment,
    DocumentVersion,
    KnowledgeSpace,
)
from app.org.constants import DEFAULT_ORG_ID
from app.migration import plan as plan_mod
from app.migration import transform
from app.migration.convert import ConvertError, coerce
from app.migration.models import (
    SRC_NOTION,
    SRC_SQLITE,
    T_COMMENT,
    T_DOCUMENT,
    T_FILE,
    T_PROJECT,
    T_TICKET,
    T_TICKET_FILE,
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
from app.storage.models import File
from app.tickets.attachments import ALLOWED_TICKET_MEDIA, MAX_TICKET_ATTACHMENTS
from app.tickets.models import Ticket, TicketAttachment, TicketComment
from app.users.models import User
from app.work import codes, numbering, relations
from app.work.models import REL_BLOCKS, MigrationException

logger = logging.getLogger("app.migration.load")

# `user_notion_mappings.source` 의 세 번째 값. `workflow` 는 S11 이 걷었고 `manual` 은
# 사람이 지정했다는 뜻이라 여기 쓰면 거짓말이 된다 — 이관이 만든 행은 그렇게 말한다.
MAP_SOURCE_MIGRATION = "migration"

# 이관이 만든 문서가 들어갈 공간. 실측상 문서 110건이 전부 `owner_kind='unset'` 이라
# 하나면 된다. 소유가 붙은 문서가 생기면 `_space_for` 가 그 축으로 공간을 더 만든다.
DEFAULT_SPACE_SLUG = "team-docs"
DEFAULT_SPACE_NAME = "팀 문서"

# 본문 이미지의 `src`. 라우트의 정본은 `app/knowledge/router.py::serve_attachment` 이고
# 여기서는 그 주소를 만들기만 한다. 상대 주소라 호스트가 바뀌어도 안 깨진다 —
# `clovirassist.gooddi.lab` 을 본문에 박아 두면 도메인을 옮기는 날 이미지가 전부 죽는다.
DOC_ATTACHMENT_URL = "/api/knowledge/attachments/{attachment_id}/content"

# 티켓 본문 이미지의 `src`. 라우트의 정본은 `app/tickets/router.py::serve_ticket_attachment`
# 이고 여기서는 그 주소를 만들기만 한다. 문서 쪽과 같은 이유로 상대 주소다.
TICKET_ATTACHMENT_URL = "/api/tickets/attachments/{attachment_id}"

# `_body_media` 가 받는 두 갈래. 본문에서 바이트를 꺼내 오는 일은 같고, **붙는 자리만**
# 다르다 — 문서는 `files` 를 지나 `document_attachments` 로, 티켓은 `ticket_attachments`
# 로 간다.
MEDIA_OWNER_DOCUMENT = "document"
MEDIA_OWNER_TICKET = "ticket"

# 본문 이미지가 첨부 목록에서 앉는 자리. 속성 첨부(`(index+1)*1024`)보다 뒤에 둔다 —
# 사람이 페이지 속성에 붙인 파일이 본문 그림 사이에 섞이면 목록이 무슨 순서인지 못 읽는다.
BODY_MEDIA_SORT_BASE = 1_000_000

# 옛 회차가 못 옮긴 블록 자리에 박아 둔 글자. 사람이 칠 리 없는 모양이라 「이 본문은
# 이관이 썼다」의 증거로 쓴다. 새 회차는 이 글자를 안 만든다(`transform` 이 사람이 읽는
# 문장으로 바꿨다).
_LEGACY_PLACEHOLDER = "[원본에서 확인: "

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
        # 기본 저장소는 한 회차에 한 번만 찾는다. 이미지마다 다시 찾으면 본문 이미지
        # 수백 건이 그대로 왕복 수백 번이 된다.
        self._provider = None

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

    def assign_project_codes(self) -> StageResult:
        """프로젝트마다 코드를 붙인다 (D-282). **이름은 안 본다.**

        ## 왜 씨앗이 `notion_page_id or id` 인가

        Dry Run 과 Cutover 는 같은 도구가 **서로 다른 데이터베이스**에 대고 도는 회차다.
        같은 프로젝트가 두 회차에서 같은 코드를 받으려면 코드가 **두 DB 에서 같은 값**
        에서 나와야 한다.

        * Notion 이 준 프로젝트는 `notion_page_id` 가 그 값이다. 소스가 주는 값이라
          어느 DB 에 적재하든 같다.
        * Notion 응답에 없는 미러 프로젝트는 `id` 가 그 값이다. 표 복사가 소스의 기본키를
          **그대로** 옮기므로(모듈 docstring) 이것도 두 DB 에서 같다.

        `id` 를 먼저 보면 안 된다: Notion 에만 있는 프로젝트의 `id` 는 `load_projects` 가
        회차마다 새로 만드는 uuid 라, 그 프로젝트만 두 DB 에서 다른 코드를 받는다.

        ## 이미 코드가 있으면 건드리지 않는다

        재실행 2회차가 아무것도 안 바꾸는 근거가 이 한 줄이다. 코드를 다시 지으면 그
        프로젝트 티켓 전부의 `canonical_key` 가 바뀌고, 1회차가 검증한 이름이 전부
        무효가 된다.

        보관된 프로젝트도 받는다. 안 주면 그 프로젝트의 티켓이 **영원히** 번호 없는
        예외로 남는다 — 보관은 「끝난 일」이지 「이름이 없어도 되는 일」이 아니다.
        """
        started = time.monotonic()
        projects = self.db.execute(sa.select(Project)).scalars().all()
        stage = StageResult(name="project codes", source_rows=len(projects))
        already = sum(1 for project in projects if project.code)
        seeds = {
            project.id: (project.notion_page_id or project.id) for project in projects
        }
        assigned = codes.assign_many(self.db, projects, seed_of=seeds)
        stage.inserted = len(assigned)
        stage.updated = already
        missing = [project.id for project in projects if not project.code]
        for project_id in missing:
            # 여기 오면 코드를 못 지은 것이고, 그 프로젝트의 티켓은 번호를 못 받는다.
            # **classified 로 적지 않는다** — classified 는 회차를 통과시키고, 통과한
            # 회차는 「이름 없는 티켓」을 만든 채로 초록이 된다.
            self.report.finding(
                SEVERITY_BLOCKING, "project_code_missing", "projects",
                "프로젝트 코드를 붙이지 못했습니다.", ref=project_id,
            )
        stage.skipped = len(missing)
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    # ── 2층: 티켓 ────────────────────────────────────────────────────────────

    def load_tickets(
        self, notion_rows: list[dict], blocks: dict[str, list[dict]], *, fetch=None,
    ) -> StageResult:
        """Notion 작업을 미러 위에 덮고 **옛 이름을 영구 별칭으로** 남긴다.

        `blocks` 는 본문 **블록 그대로**다. 마크다운을 미리 만들어 받지 않는 이유는
        본문 이미지 때문이다 — 이미지의 `src` 는 바이트를 우리 저장소로 옮긴 뒤에야
        생기고, 옮기는 일은 DB 를 아는 여기가 한다. 문서가 이미 그 길이다(D4).
        """
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

            body = self._ticket_body(ticket, page_id, blocks.get(page_id) or [], fetch)
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

            # 옛 티켓 이름(`GIT-142`)은 **안 옮긴다** (D-283). 소스의 번호
            # (`notion_ticket_number`)는 계속 읽는다 — 그것은 이름이 아니라 **채번
            # 순서**이고, 그 순서가 있어야 재실행이 같은 번호를 매긴다(D-281).
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
        self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def renumber(self) -> StageResult:
        """소속을 정하고 번호를 매긴다. **못 정하면 안 매기고 사유를 남긴다** (U11)."""
        started = time.monotonic()
        stage = StageResult(name="renumber + exceptions")

        # 코드가 있는 프로젝트 전부. **보관된 것도 센다** — 보관은 「끝난 일」이지
        # 「이름이 없어도 되는 일」이 아니고, 빼 두면 그 티켓들이 영원히 번호 없는
        # 예외로 남는다.
        keyed = {
            project_id
            for (project_id,) in self.db.execute(
                sa.select(Project.id).where(Project.code.is_not(None))
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
                # 프로젝트는 정해졌는데 그 프로젝트에 코드가 없다. 번호를 주면 트리거가
                # 거절한다. **이 자리는 이제 닿지 않는 자리다** — 앞 단계가 모든
                # 프로젝트에 코드를 붙이기 때문이다(D-282). 그래도 안 지우는 이유:
                # 닿았다면 앞 단계가 실패한 것이고, 그 사실이 여기서 조용히 번호 없는
                # 티켓으로 새는 것보다 예외로 남는 편이 낫다.
                verdicts[ticket.id] = transform.TicketExceptionVerdict(
                    "unresolved", {"project_id": resolved, "reason": "project_code_missing"}
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

    # ── 2층: 티켓 댓글 (D11) ────────────────────────────────────────────────

    def load_ticket_comments(
        self, comments: list, *, dry_run: bool = False
    ) -> StageResult:
        """Notion 페이지 댓글 → `ticket_comments`. **시간 순으로 한 줄씩 넣는다.**

        ## 순서가 곧 대화다

        `ticket_comments.seq` 는 `GENERATED ALWAYS AS IDENTITY` 라 앱이 값을 못 넣는다.
        목록은 그 `seq` 로 동점을 깨므로(모델 주석), 우리가 정할 수 있는 것은 **넣는
        순서** 하나다. 그래서 원본 시각 오름차순으로 정렬해 한 줄씩 넣는다 — 묶어서
        넣으면 같은 분에 달린 댓글의 순서가 회차마다 달라진다.

        ## 스레드는 편다

        원본은 `discussion_id` 로 답글을 묶지만 우리 표는 평평하고 부모 칸이 없다.
        시간 순으로 펴면 **같은 스레드의 답글은 원글 뒤에 온다** — 답글이 원글보다
        먼저 쓰일 수 없기 때문이다. 대화의 묶음은 잃지만 순서는 잃지 않는다.

        ## 작성자를 지어내지 않는다

        `author_user_id` 가 NOT NULL 이라 아무나 골라 적고 싶어지는 자리다. 그렇게 하면
        「이 사람이 이렇게 말했다」가 거짓 기록으로 남고, 그 거짓은 화면이 정상으로
        보이기 때문에 아무도 신고하지 않는다. 못 풀면 넣지 않고 분류된 예외로 남긴다
        (D9 · U11).

        ## 두 번 돌려도 안 늘어난다

        `legacy_mapping` 에 Notion 댓글 id 로 적어 둔다. 그 표에 있으면 건너뛴다 —
        **행이 지금 있는지 다시 확인하지 않는다.** 사람이 지운 댓글을 되살리는 것은
        재실행이 할 일이 아니다.
        """
        started = time.monotonic()
        stage = StageResult(name="ticket comments (Notion)", source_rows=len(comments))
        if not comments:
            self.report.add(stage)
            return stage

        by_page = dict(self.ticket_by_page)
        if not by_page:
            by_page = {
                page_id: ticket_id
                for page_id, ticket_id in self.db.execute(
                    sa.select(Ticket.notion_page_id, Ticket.id).where(
                        Ticket.notion_page_id.is_not(None)
                    )
                ).all()
            }
        done = {
            row.legacy_source_id
            for row in self.db.execute(
                sa.select(LegacyMapping).where(
                    LegacyMapping.legacy_source == SRC_NOTION,
                    LegacyMapping.target_type == T_COMMENT,
                )
            ).scalars()
        }

        # 시각이 없는 댓글은 뒤로 보낸다. 앞에 끼우면 시각을 아는 댓글의 순서가 밀린다.
        ordered = sorted(
            comments,
            key=lambda item: (
                item.created_at is None, item.created_at or utcnow(), item.comment_id
            ),
        )
        for item in ordered:
            if item.comment_id in done:
                # 앞 회차가 이미 넣었다. 「갱신」으로 세는 이유는 재실행의 신규가 0
                # 이어야 멱등이 증명되기 때문이다.
                stage.updated += 1
                continue
            ticket_id = by_page.get(item.page_id)
            if ticket_id is None:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "comment_ticket_missing", "ticket_comments",
                    "댓글이 달린 티켓이 이관 대상에 없어 넣지 않았습니다.",
                    ref=item.comment_id,
                )
                stage.skipped += 1
                continue
            author = self._user_for_notion(
                [item.author_notion_id] if item.author_notion_id else []
            )
            if author is None:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "comment_author_unresolved", "ticket_comments",
                    f"작성자 «{item.author_label or item.author_notion_id or '?'}» 의 "
                    f"포털 사용자를 못 찾아 넣지 않았습니다(종류: "
                    f"{item.author_kind or '?'}).",
                    ref=item.comment_id,
                )
                stage.skipped += 1
                continue
            if not item.body.strip():
                self.report.finding(
                    SEVERITY_CLASSIFIED, "comment_body_empty", "ticket_comments",
                    "본문도 첨부도 없는 댓글이라 넣지 않았습니다.", ref=item.comment_id,
                )
                stage.skipped += 1
                continue
            if item.created_at is None:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "comment_time_missing", "ticket_comments",
                    "원본 시각을 읽지 못해 넣지 않았습니다.", ref=item.comment_id,
                )
                stage.skipped += 1
                continue
            stage.inserted += 1
            if dry_run:
                # 세기만 한다. 여기서 행을 만들면 그것은 세는 것이 아니라 쓰는 것이다.
                continue
            row = TicketComment(
                id=new_uuid(), ticket_uid=ticket_id, author_user_id=author,
                body=item.body,
                # 우리 `created_at` 은 이관일이다. 원본 시각을 안 넣으면 댓글 324건이
                # 전부 같은 날 같은 시각에 달린 것이 된다.
                created_at=item.created_at, updated_at=item.created_at,
            )
            self.db.add(row)
            # 한 줄씩 flush 한다. 묶으면 `seq` 가 우리가 정한 순서대로 붙는다는 보장이
            # 없고, 그 사실은 목록이 뒤집힐 때만 드러난다.
            self.db.flush()
            self._map(SRC_NOTION, item.comment_id, T_COMMENT, row.id)

        attached = sum(item.attachment_count for item in ordered)
        if attached:
            # 댓글에 붙은 파일은 붙일 자리가 없다 — `ticket_comments` 에 첨부 표가 없고,
            # `ticket_attachments` 는 티켓에 붙는 것이지 댓글에 붙는 것이 아니다. 글은
            # 옮기고 파일은 못 옮겼다는 사실을 수로 남긴다.
            self.report.finding(
                SEVERITY_CLASSIFIED, "comment_attachment_not_moved", "ticket_comments",
                f"댓글에 붙은 파일 {attached}건은 붙일 자리가 없어 못 옮겼습니다.",
            )
        if not dry_run:
            # 다리를 **댓글과 같은 커밋에** 적는다. 뒤 단계에서 회차가 죽으면 댓글은
            # 들어갔는데 다리는 파이썬 목록에만 남고, 그 상태로 다시 돌리면 같은 댓글이
            # 한 번 더 들어간다.
            self.flush_mappings()
            self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    # ── 2층: 문서 ────────────────────────────────────────────────────────────

    def load_documents(
        self, notion_rows: list[dict], bodies: dict[str, list[dict]],
        *, taxonomy: dict[str, str], projects: dict[str, str] | None = None,
        fetch=None, only_untouched: bool = False, dry_run: bool = False,
    ) -> StageResult:
        """`document_cache` + Notion 본문 → `documents` + `document_versions`.

        **다리는 `documents.legacy_page_id` 다** (부분 유니크). 재실행이 그 값으로 같은
        문서를 찾으므로 판이 새로 쌓이지 않는다.

        `fetch` 가 있으면 본문 안의 이미지 바이트를 우리 저장소로 옮기고 `src` 를 우리
        엔드포인트로 바꾼다(D4). 문서 행이 먼저 있어야 첨부를 붙일 수 있으므로 그 일은
        판을 쌓기 **직전**에 문서 하나씩 한다.

        `only_untouched` 는 「본문만 다시 넣기」가 켠다(D5). 사용자가 고친 문서는 건드리지
        않는다 — 판정 근거는 `_body_is_untouched` 에 적었다.
        """
        started = time.monotonic()
        stage = StageResult(name="documents", source_rows=len(notion_rows))
        mirror = {
            row["notion_page_id"]: row
            for row in self.db.execute(sa.text(
                "SELECT notion_page_id, id, document_type, restricted, archived, "
                "owner_kind, owner_dept_id, owner_project_id, title, org_id "
                "FROM document_cache WHERE notion_page_id IS NOT NULL"
            )).mappings()
        }
        existing = {
            document.legacy_page_id: document
            for document in self.db.execute(
                sa.select(Document).where(Document.legacy_page_id.is_not(None))
            ).scalars()
        }
        spaces: dict[tuple[str, str | None, str], KnowledgeSpace] = {}

        for raw in notion_rows:
            parsed = transform.parse_document(raw)
            page_id = parsed["notion_page_id"]
            if not page_id:
                continue
            cached = mirror.get(page_id) or {}
            document = existing.get(page_id)
            if document is None:
                if only_untouched or dry_run:
                    # 「본문만 다시 넣기」는 새 문서를 만들지 않는다. 본문을 다시 넣는
                    # 일과 문서를 새로 들이는 일은 위험이 다르다 — 후자는 전체 회차가 한다.
                    # `dry_run` 도 같이 본다: 세기만 하는 회차가 행을 만들면 그것은 이미
                    # 쓰기다.
                    stage.skipped += 1
                    continue
                document = Document(
                    id=new_uuid(), space_id=self._space_for(spaces, cached).id,
                    legacy_page_id=page_id,
                    title=parsed["title"] or cached.get("title") or "(제목 없음)",
                    source_type=SOURCE_MIGRATION,
                )
                self.db.add(document)
                self.db.flush()
                stage.inserted += 1
            elif only_untouched and not self._body_is_untouched(document):
                stage.skipped += 1
                self.report.finding(
                    SEVERITY_NOTE, "document_edited_by_user", "documents",
                    "사용자가 고친 문서라 본문을 다시 넣지 않았습니다.", ref=page_id,
                )
                continue
            else:
                stage.updated += 1
            self.document_by_page[page_id] = document.id
            if dry_run:
                # 무엇이 바뀔지 세기만 한다. 아래 어느 줄도 실행하지 않는다 — 「세기만
                # 한다」가 절반만 지켜지면 그것은 세는 것이 아니라 쓰는 것이다.
                continue
            document.space_id = self._space_for(spaces, cached).id
            document.title = parsed["title"] or cached.get("title") or document.title
            document.doc_type = _doc_type(parsed, taxonomy, cached)
            document.confidential = bool(cached.get("restricted"))
            document.archived = bool(parsed["archived"] or cached.get("archived"))
            # 원본이 말한 생긴 날과 고친 날. 우리 `created_at` 은 **이관일**이라 이 값을
            # 안 옮기면 문서 110건이 전부 같은 날이 된다(0013).
            document.legacy_created_at = parsed["notion_created_time"]
            document.legacy_updated_at = parsed["notion_last_edited"]
            # 작성자. **이메일로 이어진 사람만** 붙는다 — 이름으로 잇지 않는다(U11).
            author = self._user_for_notion(parsed["author_notion_ids"])
            if author:
                document.created_by = author
            self._tag_document(document, parsed, taxonomy, projects or {})
            self._map(SRC_NOTION, page_id, T_DOCUMENT, document.id)
            if cached.get("id"):
                self._map(SRC_SQLITE, cached["id"], T_DOCUMENT, document.id)

            raw_blocks = bodies.get(page_id) or []
            media_urls = self._body_media(
                MEDIA_OWNER_DOCUMENT, document.id, page_id, raw_blocks, fetch
            )
            self._snapshot(document, raw_blocks, media_urls=media_urls)

        if not dry_run:
            self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _tag_document(
        self, document: Document, parsed: dict, taxonomy: dict[str, str],
        projects: dict[str, str],
    ) -> None:
        """분류와 소속 프로젝트를 태그로 남긴다. **가진 태그를 지우지 않는다.**

        카테고리는 원래 태그가 되던 값이다 — `documents` 에 그 칸이 없고 S7 이 만든
        `tags` 가 바로 그 자리다(안 옮기면 문서 61건의 분류가 사라진다).

        프로젝트도 여기로 온다. `document_relations` 는 **문서와 문서만** 잇는
        표이고(`from_document_id`·`to_document_id` 가 둘 다 `documents` 를 가리킨다),
        프로젝트를 가리킬 칸이 없다. 없는 관계를 만들어 내는 대신 태그로 남긴다 —
        34건의 소속이 사라지는 것보다 낫고, 태그는 화면에 보이고 검색에도 걸린다.

        `tags.set_for_document` 는 **집합 치환**이라 그대로 부르면 사용자가 붙인 태그가
        사라진다(D5). 그래서 지금 붙어 있는 이름과 합집합을 넘긴다 — 이관은 더하기만 한다.
        """
        wanted = [
            (taxonomy.get(cid) or "").strip() for cid in parsed["category_ids"]
        ]
        wanted += [
            (projects.get(pid) or "").strip() for pid in parsed["project_ids"]
        ]
        wanted = [name for name in wanted if name]
        if not wanted:
            return
        have = [tag.name for tag in tags.of_document(self.db, document.id)]
        merged: list[str] = []
        for name in (*have, *wanted):
            if name not in merged:
                merged.append(name)
        if merged == have:
            return
        try:
            with self.db.begin_nested():
                tags.set_for_document(self.db, document, merged)
        except AppError as exc:
            self.report.finding(
                SEVERITY_CLASSIFIED, "document_tags_rejected", "document_tags",
                f"분류를 태그로 못 붙였습니다: {exc}", ref=document.legacy_page_id,
            )

    def _body_is_untouched(self, document: Document) -> bool:
        """이 문서의 지금 본문을 **이관이 썼는가** (D5).

        판정 근거는 현재 판의 `source` 하나다. 사용자가 편집기에서 저장하면
        `versions.snapshot` 이 `VSRC_USER` 로 새 판을 쌓고 `current_version_id` 가 그리로
        옮겨 간다 — 즉 「사람이 고쳤다」는 사실이 현재 판에 그대로 적혀 있다. 글자를
        비교하지 않는 이유는 그것이 「같은 글로 다시 저장했다」와 「한 번도 안 고쳤다」를
        구별하지 못하기 때문이다.

        판이 아직 없으면 덮을 것도 없으므로 참이다.
        """
        if not document.current_version_id:
            return True
        source = self.db.execute(
            sa.select(DocumentVersion.source).where(
                DocumentVersion.id == document.current_version_id
            )
        ).scalar_one_or_none()
        return source in (None, VSRC_MIGRATION)

    def _body_media(
        self, owner_kind: str, owner_id: str, page_id: str, raw_blocks, fetch
    ) -> dict[str, str]:
        """본문이 들고 있는 이미지·파일을 우리 저장소로 옮기고 **블록 id → 우리 주소**.

        ## 문서와 티켓이 같은 이 함수를 지난다

        두 벌로 쓰면 한쪽만 이미지를 옮기게 되고, 그것이 실제로 S14 이전의 상태였다 —
        문서 본문의 49블록은 옮기고 티켓 본문의 222블록은 글자로 남았다. 바이트를 받는
        일도, 두 번 안 받는 일도, 상한에 걸린 것을 예외로 남기는 일도 전부 같다.
        갈라지는 것은 **붙는 자리 한 걸음**뿐이고 그 한 걸음만 `owner_kind` 로 나눈다.

        ## 왜 Notion 주소를 그대로 안 쓰는가

        서명이 한 시간이면 만료된다(D4 · 실측). 만료된 주소를 본문에 적어 두면 화면에는
        깨진 그림만 남고, 깨졌다는 사실은 오류 로그가 아니라 사용자의 클릭에서만 드러난다.
        라이브로 블록을 다시 읽으면 새 서명 주소가 나오고 그것으로 받을 수 있다.

        ## 같은 이미지를 두 번 받지 않는다

        `legacy_mapping` 에 블록 id 로 적어 둔다. 재실행은 그 표를 먼저 보고, 이미 있으면
        바이트를 다시 안 받고 붙어 있는 첨부를 그대로 쓴다 — 그것이 「두 번 돌려도 첨부가
        안 늘어난다」의 근거다.

        ## 상한에 걸린 것은 예외로 남긴다

        10MB 상한과 형식 허용 목록은 제품이 정한 것이고(`store_bytes` · `save_upload`)
        이관 때문에 넓히지 않는다. 걸린 파일은 분류된 예외가 되고 본문에는 사람이 읽는
        한 줄이 남는다.
        """
        media = transform.media_of(page_id, raw_blocks)
        if not media:
            return {}
        if owner_kind == MEDIA_OWNER_TICKET and len(media) > MAX_TICKET_ATTACHMENTS:
            # 사람이 화면에서 붙일 수 있는 개수 상한(`ensure_capacity`)은 본문 이미지에
            # 걸지 않는다. 그 상한은 「한 사람이 몇 개까지 붙일 수 있는가」를 정한 것이고
            # 본문 이미지는 사람이 고른 첨부가 아니라 **본문 그 자체**다 — 상한 때문에
            # 버리면 D12 가 막으려 한 「내용을 버리는 것」이 그대로 일어난다. 대신 이
            # 티켓에서는 사람이 첨부를 새로 못 붙인다는 사실을 남긴다.
            self.report.finding(
                SEVERITY_NOTE, "ticket_body_media_over_ui_limit", "ticket_attachments",
                f"본문 파일이 {len(media)}건이라 이 티켓에는 첨부를 새로 못 붙입니다.",
                ref=page_id,
            )
        out: dict[str, str] = {}
        for order, item in enumerate(media):
            if not item.hosted:
                # 바깥 링크는 바이트가 우리 것이 아니다. 본문의 링크 문단이 그대로
                # 원본 주소를 가리키는 편이 낫고, 그 주소는 서명 URL 이 아니다.
                out[item.block_id] = item.url
                continue
            url = self._moved_media_url(owner_kind, owner_id, item, order)
            if url is None and fetch is not None:
                url = self._move_media(owner_kind, owner_id, item, order, fetch)
            if url:
                out[item.block_id] = url
        return out

    def _moved_media_url(self, owner_kind: str, owner_id: str, item, order: int
                         ) -> str | None:
        """앞 회차가 이미 옮긴 파일인가. 이미 옮겼으면 **그 첨부의 주소**.

        재실행이 바이트를 다시 안 받는 근거가 이 조회다. 문서 쪽은 첨부 행을 여기서 다시
        upsert 한다 — `files` 행과 `document_attachments` 행이 따로라 한쪽만 남을 수
        있고, 그때 본문이 주소를 잃는다. 티켓 쪽은 첨부 행 자체가 대상이라 조회로 끝난다.
        """
        if owner_kind == MEDIA_OWNER_TICKET:
            attachment_id = self._mapped_target(item, T_TICKET_FILE)
            if attachment_id is None:
                return None
            row = self.db.get(TicketAttachment, attachment_id)
            # 표는 남아 있는데 첨부 행이 사라진 경우가 있다(사람이 뗐거나 앞 회차가
            # 되감겼다). 그 id 를 그대로 쓰면 본문이 404 를 가리킨다.
            if row is None or row.ticket_uid != owner_id:
                return None
            return TICKET_ATTACHMENT_URL.format(attachment_id=attachment_id)
        file_id = self._existing_media_file(item)
        if file_id is None:
            return None
        return self._attach_document_media(owner_id, file_id, item, order)

    def _attach_document_media(self, document_id: str, file_id: str, item, order: int
                               ) -> str | None:
        """문서 본문의 파일을 첨부로 붙이고 그 주소를 돌려준다.

        🔴 파일 id 를 **인자로 받는다.** 방금 만든 파일을 `legacy_mapping` 으로 다시
        찾으면 안 된다 — `_map` 은 다리를 모아 두었다가 나중에 한꺼번에 쓰므로 같은
        회차 안에서는 아직 조회에 안 걸린다. 다시 찾으면 첫 회차에서 첨부가 하나도 안
        붙고, 두 번째 회차에서야 붙는다.
        """
        # 속성 첨부 뒤에 온다. 두 무리가 같은 자리를 다투면 첨부 목록의 순서가
        # 회차마다 달라진다.
        attachment_id = self._attach_to_document(
            document_id, file_id, item, order=BODY_MEDIA_SORT_BASE + order * 1024,
        )
        if not attachment_id:
            return None
        return DOC_ATTACHMENT_URL.format(attachment_id=attachment_id)

    def _move_media(self, owner_kind: str, owner_id: str, item, order: int, fetch
                    ) -> str | None:
        """바이트를 받아 우리 저장소에 넣고 첨부를 붙인다. 못 하면 사유를 남긴다.

        `transform.media_bytes` 를 지난다 — `item.url` 이 `data:` URI 면(원본 안에 이미지가
        그대로 인코딩된 경우) 네트워크로 안 보내고 그 자리에서 디코드한다. 그대로
        `fetch()` 에 넘기면 `OutboundClient` 가 http/https 가 아닌 스킴이라 거절한다.
        """
        try:
            content = transform.media_bytes(item.url, fetch)
        except AppError as exc:
            self.report.finding(
                SEVERITY_BLOCKING, "body_media_download_failed", "files",
                f"{item.name}: {exc}", ref=item.legacy_id,
            )
            return None
        if owner_kind == MEDIA_OWNER_TICKET:
            return self._store_ticket_media(owner_id, item, content)
        file_id = self._store_media(item, content)
        if file_id is None:
            return None
        return self._attach_document_media(owner_id, file_id, item, order)

    def _mapped_target(self, item, target_type: str) -> str | None:
        """이 블록이 이미 옮겨졌다면 그 대상의 id. 다리는 `legacy_mapping` 하나다."""
        return self.db.execute(
            sa.select(LegacyMapping.target_id).where(
                LegacyMapping.legacy_source == SRC_NOTION,
                LegacyMapping.legacy_source_id == item.legacy_id,
                LegacyMapping.target_type == target_type,
            )
        ).scalar_one_or_none()

    def _existing_media_file(self, item) -> str | None:
        row = self._mapped_target(item, T_FILE)
        if row is None:
            return None
        # 표는 남아 있는데 파일 행이 사라진 경우가 있다(사람이 지웠거나 앞 회차가 되감겼다).
        # 그때 그 id 를 그대로 쓰면 첨부가 없는 파일을 가리킨다.
        return row if self.db.get(File, row) is not None else None

    def _storage_provider(self):
        """기본 저장소. 한 회차에 한 번만 찾는다."""
        if self._provider is None:
            self._provider = storage_service.ensure_default_provider(
                self.db, self.settings
            )
        return self._provider

    def _store_media(self, item, content: bytes) -> str | None:
        try:
            with self.db.begin_nested():
                record = storage_service.store_bytes(
                    self.db, filename=item.name, content=content,
                    owner_ref=f"document:{self.document_by_page.get(item.page_id) or ''}",
                    provider=self._storage_provider(),
                )
        except AppError as exc:
            self.report.finding(
                SEVERITY_CLASSIFIED, "body_media_rejected", "files",
                f"{item.name}: {exc}", ref=item.legacy_id,
            )
            return None
        self._map(SRC_NOTION, item.legacy_id, T_FILE, record.id)
        return record.id

    def _store_ticket_media(self, ticket_uid: str, item, content: bytes) -> str | None:
        """티켓 본문의 파일 하나를 `ticket_attachments` 로 옮긴다. **올린 사람은 없다.**

        `save_upload` 를 지나는 이유는 그것이 티켓 첨부의 **검증 → 저장명 → 경로**를 아는
        유일한 자리이기 때문이다(화면의 업로드도 그것을 부른다). 여기서 바이트를 직접
        쓰면 매직바이트 판정과 경로 규칙이 두 번째 정의가 되고, 그 둘은 언젠가 갈린다.

        형식 허용 목록과 10MB 상한은 제품이 정한 것이라 이관 때문에 넓히지 않는다.
        걸린 파일은 분류된 예외가 되고, 본문에는 `transform` 이 사람이 읽는 한 줄을 남긴다.

        `uploaded_by_user_id` 는 `NULL` 이다 — 이관이 가져온 파일에는 올린 사람이 없고
        그 사실을 그 칸이 그대로 말한다(D12 · `TicketAttachment` 의 컬럼 주석).
        """
        data_dir = getattr(self.settings, "data_dir", None)
        if data_dir is None:
            self.report.finding(
                SEVERITY_BLOCKING, "body_media_no_data_dir", "ticket_attachments",
                "저장 경로를 몰라 티켓 본문의 파일을 못 옮겼습니다.", ref=item.legacy_id,
            )
            return None
        try:
            stored_name, media_type, size, display_name = save_upload(
                data_dir, ticket_uid, filename=item.name, content=content,
                namespace=NS_TICKET, allowed_media_types=ALLOWED_TICKET_MEDIA,
            )
        except AppError as exc:
            self.report.finding(
                SEVERITY_CLASSIFIED, "body_media_rejected", "ticket_attachments",
                f"{item.name}: {exc}", ref=item.legacy_id,
            )
            return None
        row = TicketAttachment(
            id=new_uuid(), ticket_uid=ticket_uid, uploaded_by_user_id=None,
            filename=display_name, stored_name=stored_name, media_type=media_type,
            size_bytes=size, created_at=utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        self._map(SRC_NOTION, item.legacy_id, T_TICKET_FILE, row.id)
        return TICKET_ATTACHMENT_URL.format(attachment_id=row.id)

    def _snapshot(self, document: Document, raw_blocks, *, media_urls=None) -> None:
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
        doc = transform.notion_blocks_to_doc(raw_blocks, media_urls=media_urls)
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

    def _space_for(self, cache, cached: dict) -> KnowledgeSpace:
        """이 문서가 들어갈 공간. **`unset` 으로는 안 만든다** (D7).

        🔴 여기가 실측에서 문서 110건을 아무에게도 안 보이게 만든 자리다.
        `_stored_ownership_rules` 는 소속 갈래 셋(조직·부서·프로젝트)만 열어 주고
        `unset` 은 **어느 갈래에도 안 건다** — 그것이 fail-closed 가 사는 자리다. 그래서
        `owner_kind='unset'` 인 공간은 전역 조회 권한을 가진 4명 말고는 볼 수 없고,
        AI 검색도 같은 절을 써서 0건을 낸다. 오류는 하나도 안 난다.

        이관 문서는 회사 공통 팀 문서이므로 조직 소유다. 부서나 프로젝트 소속이 미러에
        적혀 있는 문서는 그 축을 그대로 쓴다 — 소속이 있는 문서를 조직 소유로 올리면
        그것은 가시성을 **넓히는** 일이고, 좁혀야 할 문서를 넓히는 것이 더 나쁘다.
        """
        owner_kind = cached.get("owner_kind") or OWNER_UNSET
        owner_id = (
            cached.get("owner_dept_id") if owner_kind == OWNER_DEPARTMENT
            else cached.get("owner_project_id") if owner_kind == OWNER_PROJECT else None
        )
        # 🔴 조직 갈래는 `owner_kind` 와 `org_id` 를 **함께** 본다. `OrgScopedMixin` 의
        # 기본값(`DEFAULT_ORG_ID`)을 그대로 두면 부트스트랩 조직 id 가 박히고, 사용자는
        # 소스가 준 조직에 속해 있어서 절이 여전히 안 걸린다 — 소속만 고치고 조직을
        # 안 고치면 화면은 고치기 전과 똑같다. 그래서 **문서가 실제로 속한 조직**을 쓴다.
        org_id = cached.get("org_id") or DEFAULT_ORG_ID
        # 소속 종류와 대상은 함께 있거나 함께 없다(`ck_kspace_dept_pair`). 짝이 안 맞는
        # 미러 값은 조직 소유로 내린다 — 짝이 깨진 행은 제약이 거절하고, 거절되면 문서가
        # 통째로 안 들어간다.
        kind = owner_kind if owner_id else OWNER_ORGANIZATION
        cache_key = (kind, owner_id, org_id)
        if cache_key in cache:
            return cache[cache_key]
        slug, name = _space_identity(kind, owner_id)
        space = self.db.execute(
            sa.select(KnowledgeSpace).where(
                KnowledgeSpace.slug == slug, KnowledgeSpace.org_id == org_id
            )
        ).scalars().first()
        if space is None:
            # 슬러그는 조직 안에서만 유일하다(`uq_kspace_slug`). 조직이 다른 같은 이름의
            # 공간이 이미 있어도 부딪히지 않는다.
            space = KnowledgeSpace(
                id=new_uuid(), name=name, slug=slug, org_id=org_id,
                description="옛 시스템에서 옮긴 문서가 들어 있습니다.",
                owner_kind=kind,
                owner_dept_id=owner_id if kind == OWNER_DEPARTMENT else None,
                owner_project_id=owner_id if kind == OWNER_PROJECT else None,
            )
            self.db.add(space)
            self.db.flush()
        else:
            self._repair_space_owner(space, kind, owner_id, org_id)
        cache[cache_key] = space
        return space

    def _repair_space_owner(
        self, space: KnowledgeSpace, kind: str, owner_id, org_id: str
    ) -> None:
        """이미 만들어진 공간의 소유를 고친다. **`unset` 일 때만 손댄다.**

        앞 회차가 세운 운영 공간이 `unset` 으로 굳어 있으므로 재실행이 그것을 고쳐야
        한다 — 안 고치면 이 수정은 「다음에 새로 만드는 DB 에서만」 성립하고, 실제로
        문서를 못 보는 사람은 계속 못 본다.

        사람이 정해 둔 소유는 안 덮는다. 이관이 남의 결정을 되돌리면 그 공간은 회차마다
        소유가 바뀌고, 바뀐 이유를 아무도 못 찾는다.
        """
        if space.owner_kind != OWNER_UNSET:
            return
        space.owner_kind = kind
        space.owner_dept_id = owner_id if kind == OWNER_DEPARTMENT else None
        space.owner_project_id = owner_id if kind == OWNER_PROJECT else None
        # 조직 갈래는 `owner_kind` 와 `org_id` 를 **함께** 본다. 하나만 고치면 절이 여전히
        # 안 걸리고, 화면은 고치기 전과 똑같다.
        if kind == OWNER_ORGANIZATION and not space.org_id:
            space.org_id = org_id
        self.db.flush()
        self.report.finding(
            SEVERITY_NOTE, "space_owner_repaired", "knowledge_spaces",
            f"공간 «{space.name}» 의 소속을 조직으로 고쳤습니다.", ref=space.id,
        )

    # ── 2층: 티켓 본문만 다시 넣기 (D5) ─────────────────────────────────────

    def reimport_ticket_bodies(
        self, notion_rows: list[dict], blocks: dict[str, list[dict]], *,
        fetch=None, dry_run: bool = False,
    ) -> StageResult:
        """티켓의 **본문만** 다시 넣는다. 속성·번호·관계는 안 건드린다.

        🔴 사용자가 고친 본문은 덮지 않는다. 판정 근거 셋을 `_ticket_body_is_ours` 에
        적었다 — 하나라도 사람이 손댄 흔적이면 건너뛰고 세기만 한다.

        `dry_run` 은 `fetch` 없이 부른다(`runner`). 그러면 이미 옮겨 둔 파일의 주소는
        그대로 나오고 아직 안 옮긴 것만 자리 문장으로 세어진다 — 세는 회차가 바이트를
        받거나 첨부를 만들면 그것은 세는 것이 아니라 쓰는 것이다.
        """
        started = time.monotonic()
        stage = StageResult(name="ticket bodies", source_rows=len(notion_rows))
        tickets = {
            ticket.notion_page_id: ticket
            for ticket in self.db.execute(
                sa.select(Ticket).where(Ticket.notion_page_id.is_not(None))
            ).scalars()
        }
        for raw in notion_rows:
            page_id = raw.get("id")
            ticket = tickets.get(page_id or "")
            if page_id and ticket is not None:
                # 본문이 없거나 사람이 고쳤어도 이 페이지는 이 티켓이다 — `load_files`
                # 가 속성 첨부를 이 티켓에 붙이려면 여기서 먼저 채워 둬야 한다. 본문
                # 스킵과 첨부 스킵은 서로 다른 판정이다.
                self.ticket_by_page[page_id] = ticket.id
            raw_blocks = blocks.get(page_id or "") or []
            if not page_id or ticket is None or not raw_blocks:
                stage.skipped += 1
                continue
            # 🔴 덮어도 되는 본문인지를 **바이트를 옮기기 전에** 묻는다. 순서를 뒤집으면
            # 안 덮을 티켓에도 첨부가 붙고, 그 첨부는 본문 어디에서도 안 보인다.
            if not self._ticket_body_is_ours(ticket):
                stage.skipped += 1
                self.report.finding(
                    SEVERITY_NOTE, "ticket_body_edited_by_user", "tickets",
                    "사용자가 고친 본문이라 다시 넣지 않았습니다.", ref=page_id,
                )
                continue
            body = self._ticket_body(ticket, page_id, raw_blocks, fetch)
            if not body:
                stage.skipped += 1
                continue
            if ticket.body_markdown == body:
                continue
            stage.updated += 1
            if dry_run:
                continue
            ticket.body_markdown = body
        if not dry_run:
            self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _ticket_body(self, ticket: Ticket, page_id: str, raw_blocks, fetch) -> str:
        """티켓 본문 마크다운. **바이트를 먼저 옮기고 그 주소를 본문에 넣는다.**

        문서와 다른 것은 마지막 한 걸음뿐이다: 문서의 정본은 판 하나(JSON)이고 티켓의
        정본은 `tickets.body_markdown` 이다. 그 앞의 「이미지를 우리 것으로 만든다」는
        `_body_media` 하나가 두 쪽 모두에 한다 — 두 벌로 쓰면 한쪽만 옮기게 된다.
        """
        media_urls = self._body_media(
            MEDIA_OWNER_TICKET, ticket.id, page_id, raw_blocks, fetch
        )
        return transform.notion_blocks_to_markdown(raw_blocks, media_urls=media_urls)

    @staticmethod
    def _ticket_body_is_ours(ticket: Ticket) -> bool:
        """이 티켓의 본문을 **이관이 썼는가**.

        문서와 달리 티켓에는 판 이력이 없어서 `source` 하나로는 못 판정한다. 대신
        사람이 포털에서 저장했다는 사실이 남는 자리를 본다:

        * `body_synced_at` — `repository_native.save_body` 가 저장할 때마다 찍는다.
          이관은 그 칸을 안 건드리므로 값이 있으면 **사람이 저장한 것**이다.
        * `body_sync_error` — 옛 push 실패가 적힌 행이다. 그 본문은 포털이 갖고 있고
          원본에는 없으므로 덮으면 사용자가 쓴 글이 사라진다.
        * 옛 자리표시자(`[원본에서 확인: `) — 사람이 칠 리 없는 글자다. 이 글자가 있으면
          그 본문은 이관이 쓴 것이 확실하므로, 위 둘이 애매해도 다시 넣어도 된다.

        비어 있으면 덮을 것이 없으므로 참이다.
        """
        body = ticket.body_markdown or ""
        if not body.strip():
            return True
        if _LEGACY_PLACEHOLDER in body:
            return True
        return ticket.body_synced_at is None and not ticket.body_sync_error

    # ── 2층: 첨부 ────────────────────────────────────────────────────────────

    def load_files(self, attachments: list, fetch, *, dry_run: bool = False) -> StageResult:
        """첨부 바이트를 실제 저장소로 옮긴다 (D-250).

        `store_bytes` 를 지나는 이유는 그것이 **검증 → 저장 → 행** 순서를 아는 유일한
        자리이기 때문이다. 여기서 바이트를 직접 쓰면 체크섬·경로 규칙·저장소 선택이
        두 번째 정의가 된다.

        지원하지 않는 형식(예: 회의 녹음 `.m4a`)은 **거절하고 분류한다.** 업로드 정책을
        이관 때문에 넓히지 않는다 — 그것은 제품 결정이고 S13 의 범위가 아니다.

        🔴 **문서와 티켓은 붙는 자리가 다르다** (S14 실측으로 드러남). 문서는 `files` +
        `document_attachments` 두 표를 쓰지만, 티켓은 `ticket_attachments` 하나뿐이고
        그 표에 `files` 를 가리키는 칸이 없다(D12). 예전에는 이 함수가 `document_id` 를
        찾았을 때만 붙이고 못 찾으면 **아무 것도 안 했다** — 바이트는 `files` 에
        저장되고 다리(`legacy_mapping`)도 남는데, 정작 티켓 어디에도 안 걸렸다. 화면에는
        「그런 첨부가 없다」로 보이고 그 실종은 아무 오류도 안 낸다.

        그래서 갈래를 본문 미디어(`_body_media`)와 **같은 판정**(`ticket_by_page` /
        `document_by_page`)으로 정한다. 티켓 쪽은 `files` 표를 아예 안 거치고
        `_store_ticket_media` — 본문 미디어가 쓰는 그 함수 그대로 — 로 보낸다. 두 번째
        판정 자리를 만들면 언젠가 갈린다.

        🔴 **이미 잘못 옮겨진 예전 회차의 흔적도 고친다.** 이 버그가 고쳐지기 전 회차가
        이미 `legacy_mapping` 에 `file` 로 적어 둔 티켓 소유 첨부가 실제 운영 DB에
        있다 — 그 다리를 그대로 「이미 옮겼다」로 읽으면 영영 안 고쳐진다. 그래서 다리를
        찾을 때 종류(`target_type`)도 같이 보고, 티켓 소유인데 `file` 로 적혀 있으면
        바이트를 다시 안 받고(이미 우리 저장소에 있다) `ticket_attachments` 로 옮긴 뒤
        다리를 고쳐 적는다.

        `dry_run` 은 이미 옮긴 것(`done`)과 아닌 것만 센다 — 바이트를 안 받고 저장소
        기본 공급자도 안 만든다. `reimport-bodies` 가 이 길로 부른다(D5): 「본문과
        속성의 첨부」라는 그 함수의 약속을 지키려면 첨부도 다시 넣어야 하고, 안전한
        이유는 여기도 `legacy_mapping` 으로 두 번 안 받기 때문이다.
        """
        started = time.monotonic()
        stage = StageResult(name="attachments", source_rows=len(attachments))
        if not attachments:
            self.report.add(stage)
            return stage
        provider = (
            None if dry_run
            else storage_service.ensure_default_provider(self.db, self.settings)
        )
        done = {
            row.legacy_source_id: (row.target_type, row.target_id)
            for row in self.db.execute(
                sa.select(LegacyMapping).where(
                    LegacyMapping.legacy_source == SRC_NOTION,
                    LegacyMapping.target_type.in_((T_FILE, T_TICKET_FILE)),
                )
            ).scalars()
        }
        for item in attachments:
            mapped = done.get(item.legacy_id)
            if mapped is not None:
                target_type, target_id = mapped
                ticket_id = self.ticket_by_page.get(item.page_id)
                if ticket_id and target_type == T_FILE:
                    if dry_run:
                        stage.inserted += 1
                        continue
                    if self._reroute_file_to_ticket(ticket_id, item, target_id):
                        stage.inserted += 1
                    else:
                        stage.skipped += 1
                    continue
                stage.updated += 1
                continue
            if not item.hosted:
                self.report.finding(
                    SEVERITY_CLASSIFIED, "attachment_external_link", "files",
                    f"바깥 링크라 바이트가 없습니다: {item.name}", ref=item.legacy_id,
                )
                stage.skipped += 1
                continue
            if dry_run:
                # 세기만 한다 — 바이트를 안 받고 행도 안 만든다.
                stage.inserted += 1
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
            document_id = self.document_by_page.get(item.page_id)
            ticket_id = self.ticket_by_page.get(item.page_id)
            if ticket_id and not document_id:
                if self._store_ticket_media(ticket_id, item, content) is None:
                    stage.skipped += 1
                    continue
                stage.inserted += 1
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
            if document_id:
                self._attach_to_document(
                    document_id, record.id, item, order=(item.index + 1) * 1024,
                )
        if not dry_run:
            self.db.commit()
        stage.seconds = time.monotonic() - started
        self.report.add(stage)
        return stage

    def _reroute_file_to_ticket(self, ticket_uid: str, item, file_id: str) -> bool:
        """예전 버그가 `files` 표에 얹어 둔 티켓 소유 첨부를 `ticket_attachments` 로 옮긴다.

        바이트는 이미 우리 저장소에 있으므로 다시 안 받는다(`storage_service.read_bytes`).
        옮긴 뒤에는 다리(`legacy_mapping`)를 그 자리에서 고쳐 적는다 — 새 행을 더하면
        같은 `legacy_source_id` 에 `file` 다리가 죽은 채로 남아 다음 회차가 또 이 자리를
        본다.
        """
        file_row = self.db.get(File, file_id)
        if file_row is None:
            # 다리는 있는데 파일 행이 없다(사람이 지웠거나 앞 회차가 되감겼다). 옮길
            # 바이트가 없으므로 분류된 예외로 남긴다.
            self.report.finding(
                SEVERITY_CLASSIFIED, "attachment_reroute_source_missing",
                "ticket_attachments",
                f"옮길 파일 행이 이미 없습니다: {item.name}", ref=item.legacy_id,
            )
            return False
        try:
            content = storage_service.read_bytes(self.db, file_row)
        except AppError as exc:
            # 행은 있는데 바이트가 없다(장치가 바뀌었거나 사람이 지웠다). 억지로
            # 옮기려다 회차 전체를 죽이지 않는다 — 이 한 건만 분류된 예외로 남긴다.
            self.report.finding(
                SEVERITY_BLOCKING, "attachment_reroute_bytes_missing",
                "ticket_attachments",
                f"저장소에서 바이트를 못 읽었습니다: {item.name} ({exc})",
                ref=item.legacy_id,
            )
            return False
        attachment_id = self._store_ticket_media(ticket_uid, item, content)
        if attachment_id is None:
            return False
        storage_service.delete_file(self.db, file_row)
        self.db.execute(
            sa.update(LegacyMapping)
            .where(
                LegacyMapping.legacy_source == SRC_NOTION,
                LegacyMapping.legacy_source_id == item.legacy_id,
                LegacyMapping.target_type == T_FILE,
            )
            .values(target_type=T_TICKET_FILE, target_id=attachment_id, migrated_at=utcnow())
        )
        return True

    def _owner_ref(self, page_id: str) -> str | None:
        document_id = self.document_by_page.get(page_id)
        if document_id:
            return f"document:{document_id}"
        ticket_id = self.ticket_by_page.get(page_id)
        return f"ticket:{ticket_id}" if ticket_id else None

    def _attach_to_document(
        self, document_id: str, file_id: str, item, *, order: int
    ) -> str | None:
        """문서에 첨부를 붙이고 **그 첨부의 id** 를 돌려준다.

        id 가 필요한 이유는 본문 이미지 때문이다 — `src` 가 첨부를 여는 우리 주소여야
        하고, 그 주소는 첨부 id 로 만들어진다. `DO NOTHING` 이면 이미 붙어 있는 회차에서
        아무것도 안 돌려주므로 재실행이 이미지 주소를 잃는다. 그래서 `DO UPDATE` 로
        같은 값을 다시 적고 id 를 받는다 — 두 번 돌려도 첨부는 한 줄이다.
        """
        table = DocumentAttachment.__table__
        stmt = pg_insert(table).values([{
            "id": new_uuid(), "document_id": document_id, "file_id": file_id,
            "caption": item.name[:500], "sort_order": order,
            "created_by": None, "created_at": utcnow(),
        }])
        return self.db.execute(stmt.on_conflict_do_update(
            index_elements=["document_id", "file_id"],
            set_={"caption": stmt.excluded.caption},
        ).returning(table.c.id)).scalar_one_or_none()

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
    # 조직 소유 공간은 조직 하나에 하나뿐이라 주소가 고정이다. `space_slug` 로 만들면
    # 운영에 이미 서 있는 `team-docs` 옆에 같은 뜻의 공간이 하나 더 생기고, 문서가 두
    # 공간에 갈린다.
    if owner_kind in (OWNER_UNSET, OWNER_ORGANIZATION) or not owner_id:
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
