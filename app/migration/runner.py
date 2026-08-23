"""파이프라인 한 회차 (S13).

## 순서가 계약이다

```
표 복사 → 프로젝트(Notion) → Project Key → 티켓(Notion) → 재채번 → 채번 시드
        → 관계 → 사용자 매핑 → 문서 → 첨부 → 다리 → 검증
```

두 자리가 특히 못 바뀐다:

* **Project Key 는 재채번보다 앞이다.** `canonical_key` 를 만드는 트리거가
  `projects.code` 를 읽는다 — Key 가 없으면 번호를 주는 순간 트리거가 거절한다(0003).
* **채번 시드는 재채번보다 뒤다.** `seed_counters()` 는 `MAX(seq)` 를 읽는다. 앞에서
  부르면 아직 아무 티켓에도 번호가 없어 **아무 일도 하지 않고** 통과한다 — 그리고
  그 사실은 첫 신규 티켓이 1번을 받아 기존 티켓과 부딪힐 때 드러난다.

  (`docs/platform/WORK_STATE.md` 의 S12 인수인계는 이 둘을 반대로 적었다. 실제로
  성립하는 순서는 위쪽이고, `numbering.seed_counters` 의 docstring 이 「적재를 끝낸
  직후」라고 같은 말을 하고 있다.)

## Notion 이 없으면 **없다고 말한다**

`--no-notion` 은 시험과 반례용이다. 그 회차는 본문·속성·첨부를 하나도 안 옮기므로
보고서에 그렇게 적고, 검증은 Notion 기준 수를 건너뛴다 — 「검사가 통과했다」가
「Notion 을 봤다」로 읽히면 안 된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.migration import plan as plan_mod
from app.migration import transform, validate
from app.migration.load import Loader
from app.migration.report import (
    SEVERITY_BLOCKING,
    SEVERITY_CLASSIFIED,
    SEVERITY_NOTE,
    MigrationReport,
)
from app.migration.source_notion import (
    DB_CATEGORIES,
    DB_DOCUMENTS,
    DB_DOC_TYPES,
    DB_PROJECTS,
    DB_TASKS,
)
from app.migration.source_sqlite import SqliteSource

logger = logging.getLogger("app.migration.runner")

__all__ = ["MigrationOptions", "run", "database_label", "source_fingerprint"]


@dataclass
class MigrationOptions:
    sqlite_path: str
    mode: str = "dry-run"
    with_notion: bool = True
    with_bodies: bool = True
    with_files: bool = True
    database_overrides: dict[str, str] | None = None
    limit_pages: int | None = None   # 시험·표본 회차용. None 이면 전부.


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(
    db: Session,
    options: MigrationOptions,
    *,
    notion=None,
    settings=None,
    report: MigrationReport | None = None,
) -> MigrationReport:
    report = report or MigrationReport()
    report.mode = options.mode
    report.started_at = _now()
    report.source_sqlite = str(options.sqlite_path)
    report.target_database = database_label(db)

    with SqliteSource(options.sqlite_path) as source:
        report.source_fingerprint = source_fingerprint(source)
        classification = plan_mod.classify(source.tables())
        _report_classification(report, classification)

        loader = Loader(db, report=report, settings=settings)
        loader.copy_tables(source, classification)

        notion_rows = _extract_notion(report, options, notion)
        loader.load_projects(notion_rows["projects"])
        loader.apply_project_keys()
        loader.load_tickets(notion_rows["tasks"], notion_rows["ticket_bodies"])
        loader.renumber()
        loader.seed_counters()
        loader.load_relations()
        loader.load_user_mappings(notion_rows["people"])
        loader.load_documents(
            notion_rows["documents"], notion_rows["document_bodies"],
            taxonomy=notion_rows["taxonomy"],
        )
        if options.with_files and notion is not None:
            loader.load_files(notion_rows["attachments"], notion.download)
        elif notion_rows["attachments"]:
            report.finding(
                SEVERITY_NOTE, "attachments_skipped", "files",
                f"첨부 {len(notion_rows['attachments'])}건을 이번 회차는 안 옮겼습니다.",
            )
        loader.flush_mappings()
        db.commit()

        report.counts = _counts(db)
        validate.validate(db, source, report, notion=notion_rows["expected"])

    if notion is not None:
        # 속성 적용률은 위에서 이미 채워 뒀다. 통계를 그 위에 **덮지 않고 더한다.**
        report.notion.update(notion.stats.as_dict())
    report.finished_at = _now()
    return report


# ── Extract ──────────────────────────────────────────────────────────────────


def _extract_notion(report: MigrationReport, options: MigrationOptions, notion) -> dict:
    """Notion 에서 읽을 것을 전부 읽어 사전 하나로 만든다."""
    empty = {
        "tasks": [], "projects": [], "documents": [],
        "ticket_bodies": {}, "document_bodies": {}, "taxonomy": {},
        "attachments": [], "people": {}, "expected": {},
    }
    if notion is None or not options.with_notion:
        report.finding(
            SEVERITY_NOTE, "notion_skipped", "notion",
            "이 회차는 Notion 을 읽지 않았습니다. 본문과 속성과 첨부가 안 옮겨집니다.",
        )
        return empty

    databases = notion.discover(overrides=options.database_overrides)
    tasks = notion.query_database(databases[DB_TASKS], role=DB_TASKS)
    projects = notion.query_database(databases[DB_PROJECTS], role=DB_PROJECTS)
    documents = notion.query_database(databases[DB_DOCUMENTS], role=DB_DOCUMENTS)
    doc_types = notion.query_database(databases[DB_DOC_TYPES], role=DB_DOC_TYPES)
    categories = notion.query_database(databases[DB_CATEGORIES], role=DB_CATEGORIES)

    if options.limit_pages:
        tasks = tasks[: options.limit_pages]
        documents = documents[: options.limit_pages]

    taxonomy = {
        **transform.relation_titles(doc_types),
        **transform.relation_titles(categories),
    }
    _report_property_coverage(report, tasks, documents, projects)

    ticket_bodies: dict[str, str] = {}
    document_bodies: dict[str, list[dict]] = {}
    if options.with_bodies:
        for raw in tasks:
            page_id = raw.get("id")
            if not page_id:
                continue
            blocks = notion.page_blocks(
                page_id, last_edited=raw.get("last_edited_time")
            )
            markdown = transform.notion_blocks_to_markdown(blocks)
            if markdown.strip():
                ticket_bodies[page_id] = markdown
        for raw in documents:
            page_id = raw.get("id")
            if not page_id:
                continue
            document_bodies[page_id] = notion.page_blocks(
                page_id, last_edited=raw.get("last_edited_time")
            )
    else:
        report.finding(
            SEVERITY_NOTE, "bodies_skipped", "notion",
            "이 회차는 본문 블록을 읽지 않았습니다.",
        )

    attachments = []
    people: dict[str, dict] = {}
    for raw in (*tasks, *documents):
        attachments.extend(transform.attachments_of(raw))
        _collect_people(raw, people)

    return {
        "tasks": tasks,
        "projects": projects,
        "documents": documents,
        "ticket_bodies": ticket_bodies,
        "document_bodies": document_bodies,
        "taxonomy": taxonomy,
        "attachments": attachments,
        "people": people,
        "expected": {
            "tasks": len(tasks),
            "documents": len(documents),
            "projects": len(projects),
        },
    }


def _report_property_coverage(report, tasks, documents, projects) -> None:
    """이름을 맞힌 속성이 **실제로 값을 냈는가** (D-213).

    속성 이름이 안 맞으면 Notion 은 오류를 안 낸다 — 그냥 그 키가 없는 응답을 준다.
    그래서 「이 필드는 0건이었다」를 세지 않으면 컬럼이 조용히 빈 채로 이관된다.
    실제로 그렇게 됐던 자리가 문서 분류 110건이다(INVENTORY 05 · S13 이 원인을 찾았다).
    """
    for label, rows, names in (
        ("작업", tasks, transform.TASK_PROPS),
        ("문서", documents, transform.DOC_PROPS),
        ("프로젝트", projects, transform.PROJECT_PROPS),
    ):
        if not rows:
            continue
        coverage = transform.property_coverage(rows, names)
        report.notion.setdefault("property_coverage", {})[label] = coverage
        for field, hits in sorted(coverage.items()):
            if hits:
                continue
            report.finding(
                SEVERITY_CLASSIFIED, "property_never_filled", f"notion:{label}",
                f"«{names[field]}» 이 {len(rows)}행 중 한 번도 값을 내지 않았습니다. "
                "정말 비어 있거나 속성 이름이 바뀐 것입니다.",
                ref=field,
            )


def _collect_people(raw: dict, out: dict[str, dict]) -> None:
    """페이지의 모든 `people` 속성에서 사람을 모은다 — **이메일까지**.

    이름으로 잇지 않으려면 이메일이 필요하고, Notion 은 그 값을 속성 안에 이미 실어
    준다(`person.email`). 별도 `/v1/users` 왕복이 필요 없다.
    """
    for prop in (raw.get("properties") or {}).values():
        if not isinstance(prop, dict) or prop.get("type") != "people":
            continue
        for person in prop.get("people") or []:
            if not isinstance(person, dict) or not person.get("id"):
                continue
            holder = person.get("person")
            email = holder.get("email") if isinstance(holder, dict) else None
            entry = out.setdefault(person["id"], {"name": person.get("name")})
            if email:
                entry["email"] = email


# ── 보고 ─────────────────────────────────────────────────────────────────────


def _report_classification(report: MigrationReport, c: plan_mod.Classification) -> None:
    for table, reason in c.dropped:
        report.finding(SEVERITY_NOTE, "table_dropped", table, reason)
    for table in c.derived:
        report.finding(
            SEVERITY_NOTE, "table_derived", table,
            "파생 데이터라 행을 넣지 않습니다. 제품이 원본에서 다시 만듭니다(D-270).",
        )
    for table in c.unknown:
        report.finding(
            SEVERITY_BLOCKING, "table_unknown", table,
            "계획에 없는 표입니다. 옮길지 말지 사람이 정해야 합니다.",
        )
    for table in c.missing_target:
        report.finding(
            SEVERITY_NOTE, "table_absent_in_source", table,
            "계획에는 있는데 이 소스에는 없습니다.",
        )


def source_fingerprint(source) -> dict:
    """소스가 무엇이었는지. **증거 재사용의 근거다** (CLAUDE.md §7)."""
    out: dict = {"tables": len(source.tables())}
    for table in ("ticket_cache", "document_cache", "users", "audit_logs", "projects"):
        try:
            out[table] = source.count(table)
        except Exception:  # noqa: BLE001 — 없는 표는 지문에서 빠질 뿐이다
            continue
    try:
        rows = source.select("SELECT version_num FROM alembic_version")
        if rows:
            out["alembic"] = rows[0]["version_num"]
    except Exception:  # noqa: BLE001
        pass
    return out


def _counts(db: Session) -> dict:
    """적재가 끝난 뒤의 표별 행 수. **재실행이 같은지 대조하는 값이다.**"""
    import sqlalchemy as sa

    out: dict = {}
    for table in (
        "users", "org_units", "projects", "tickets", "ticket_relations",
        "ticket_key_aliases", "migration_exceptions", "documents",
        "document_versions", "document_attachments", "document_tags", "tags",
        "files", "knowledge_spaces", "legacy_mapping", "project_key_registry",
        "user_notion_mappings",
    ):
        out[table] = int(
            db.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        )
    return out


def database_label(db: Session) -> str:
    """어느 DB 에 넣었는가. **자격증명은 빼고** 적는다."""
    try:
        url = db.get_bind().engine.url
        return f"{url.host or 'local'}:{url.port or ''}/{url.database}"
    except Exception:  # noqa: BLE001
        return "?"
