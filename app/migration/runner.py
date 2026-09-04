"""파이프라인 한 회차 (S13).

## 순서가 계약이다

```
표 복사 → 프로젝트(Notion) → 프로젝트 코드 → 티켓(Notion) → 재채번 → 채번 시드
        → 관계 → 사용자 매핑 → 티켓 댓글 → 문서 → 첨부 → 다리 → 검증
```

세 자리가 특히 못 바뀐다:

* **프로젝트 코드는 재채번보다 앞이다.** `canonical_key` 를 만드는 트리거가
  `projects.code` 를 읽는다 — 코드가 없으면 번호를 주는 순간 트리거가 거절한다(0003).
  그리고 코드는 **프로젝트 적재보다 뒤**여야 한다: 씨앗으로 쓰는 `notion_page_id` 가
  그 단계에서 붙는다(D-282).
* **채번 시드는 재채번보다 뒤다.** `seed_counters()` 는 `MAX(seq)` 를 읽는다. 앞에서
  부르면 아직 아무 티켓에도 번호가 없어 **아무 일도 하지 않고** 통과한다 — 그리고
  그 사실은 첫 신규 티켓이 1번을 받아 기존 티켓과 부딪힐 때 드러난다.

* **티켓 댓글은 사용자 매핑보다 뒤다.** 작성자를 `user_notion_mappings` 로 풀기
  때문에, 앞에서 부르면 댓글 324건이 전부 「작성자를 못 찾았다」로 분류되고 회차는
  아무 오류 없이 통과한다(D11).

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

__all__ = [
    "MigrationOptions", "run", "reimport_bodies",
    "database_label", "source_fingerprint",
]


@dataclass
class MigrationOptions:
    sqlite_path: str
    mode: str = "dry-run"
    with_notion: bool = True
    with_bodies: bool = True
    with_files: bool = True
    with_comments: bool = True
    database_overrides: dict[str, str] | None = None
    limit_pages: int | None = None   # 시험·표본 회차용. None 이면 전부.
    #: 특정 Notion 페이지만 다시 넣는다. 비어 있으면 전부다.
    #: 실측이 「한 건만 짧다」고 말할 때 그 한 건만 고치기 위한 자리다.
    only_pages: tuple[str, ...] = ()
    #: 「본문만 다시 넣기」가 **무엇의** 본문을 고칠 것인가.
    #:
    #: `all`(예전 동작)은 문서와 티켓 본문을 함께 고친다. `documents` 는 문서만이다.
    #: 이 갈래가 생긴 이유: 이번 회차의 요구는 **문서**이고, 티켓 본문 약 1,120건을 같은
    #: 회차에 함께 다시 쓰면 되돌릴 수 없는 변경의 범위가 열 배가 된다. 티켓에도 같은
    #: 자리표시자가 남아 있다는 사실은 보고서가 말하고, 고칠지는 사람이 정한다.
    scope: str = "all"


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
        # 본문 이미지의 바이트를 받아 올 손. 없으면 본문에는 사람이 읽는 자리 문장이
        # 남는다 — 서명 URL 을 대신 적어 두지 않는다(D4).
        fetch = notion.download if (options.with_files and notion is not None) else None
        loader.load_projects(notion_rows["projects"])
        loader.assign_project_codes()
        loader.load_tickets(
            notion_rows["tasks"], notion_rows["ticket_blocks"], fetch=fetch
        )
        loader.renumber()
        loader.seed_counters()
        loader.load_relations()
        loader.load_user_mappings(notion_rows["people"])
        # 댓글은 **사용자 매핑 뒤**다. 작성자를 그 표로 풀기 때문에, 앞에서 부르면
        # 324건이 전부 「작성자를 못 찾았다」로 분류되고 회차는 그대로 통과한다.
        loader.load_ticket_comments(notion_rows["comments"])
        loader.load_documents(
            notion_rows["documents"], notion_rows["document_bodies"],
            taxonomy=notion_rows["taxonomy"],
            projects=notion_rows["project_titles"],
            fetch=fetch,
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


def reimport_bodies(
    db: Session,
    options: MigrationOptions,
    *,
    notion,
    settings=None,
    report: MigrationReport | None = None,
    dry_run: bool = False,
    fallback_author=None,
) -> MigrationReport:
    """**본문·첨부·공간 소유·티켓 댓글만** 다시 넣는다 (D5 · D11).

    ## 왜 전체 회차를 다시 안 돌리는가

    `run()` 은 표 63개를 소스 스냅숏에서 복사한다. 그 스냅숏은 컷오버 시각의 사진이므로,
    지금 다시 돌리면 그 뒤에 사람이 만든 티켓·댓글·설정이 **3주 전 상태로 덮인다.**
    그것은 되돌릴 수 없는 사고이고, 본문을 고치려고 치를 대가가 아니다.

    그래서 이 경로는 소스 SQLite 를 아예 안 연다. 건드리는 것은 다섯뿐이다:
    문서 본문 · 본문과 속성의 첨부 · 문서의 분류 태그 · 이관 공간의 소유 ·
    아직 한 건도 안 옮긴 Notion 티켓 댓글(D11). 채번·프로젝트 코드·사용자 매핑·관계는
    이미 맞고, 다시 돌릴 이유가 없다.

    `dry_run` 은 **아무것도 안 쓴다.** 무엇이 바뀔지 세기만 하고 커밋도 안 한다.
    """
    report = report or MigrationReport()
    report.mode = "reimport-bodies" + ("(dry-run)" if dry_run else "")
    report.started_at = _now()
    report.target_database = database_label(db)

    notion_rows = _extract_notion(report, options, notion)
    loader = Loader(db, report=report, settings=settings,
                    fallback_author=fallback_author)
    # 세기만 하는 회차에는 손을 안 준다. 바이트를 받아 첨부를 만드는 것은 이미 쓰기다.
    fetch = (
        notion.download
        if (options.with_files and notion is not None and not dry_run) else None
    )
    documents_only = options.scope == "documents"
    if documents_only:
        # 티켓 본문에도 같은 자리표시자가 남아 있다 — 안 고친다는 사실을 **수와 함께**
        # 남긴다. 조용히 건너뛰면 다음 사람이 「이미 고쳤나」를 다시 세어야 한다.
        report.finding(
            SEVERITY_NOTE, "ticket_bodies_out_of_scope", "tickets",
            f"이번 회차는 문서만 고칩니다. 티켓 {len(notion_rows['tasks'])}건의 본문은 "
            "그대로 두었습니다.",
        )
    else:
        loader.reimport_ticket_bodies(
            notion_rows["tasks"], notion_rows["ticket_blocks"],
            fetch=fetch, dry_run=dry_run,
        )
        # 댓글도 이 길로 온다 (D11). 안전한 이유는 **더하기만 하기** 때문이다: 이미 옮긴
        # 댓글은 `legacy_mapping` 이 걸러 내고, 사람이 포털에서 쓴 댓글은 아예 안 본다.
        loader.load_ticket_comments(notion_rows["comments"], dry_run=dry_run)
    loader.load_documents(
        notion_rows["documents"], notion_rows["document_bodies"],
        taxonomy=notion_rows["taxonomy"],
        projects=notion_rows["project_titles"],
        fetch=fetch,
        only_untouched=True,
        dry_run=dry_run,
        only_pages=(set(options.only_pages) if options.only_pages else None),
    )
    # 속성 첨부(문서의 「첨부파일」, 티켓의 「파일과 미디어」). 본문 안 이미지와 달리
    # 이 둘은 `load_documents`/`reimport_ticket_bodies` 가 안 건드린다 — 페이지 속성이라
    # 본문 블록을 안 지나기 때문이다. `legacy_mapping` 으로 이미 옮긴 것은 걸러지므로
    # 몇 번을 다시 돌려도 안전하다(D-250).
    if options.with_files and notion is not None:
        loader.load_files(notion_rows["attachments"], fetch, dry_run=dry_run)
    elif notion_rows["attachments"]:
        report.finding(
            SEVERITY_NOTE, "attachments_skipped", "files",
            f"첨부 {len(notion_rows['attachments'])}건을 이번 회차는 안 옮겼습니다.",
        )
    if dry_run:
        # 회차가 남긴 것이 없어야 한다. 세는 동안 붙은 SAVEPOINT 나 flush 까지 되돌린다.
        db.rollback()
    else:
        loader.flush_mappings()
        db.commit()
        report.counts = _counts(db)
    if notion is not None:
        report.notion.update(notion.stats.as_dict())
    report.finished_at = _now()
    return report


# ── Extract ──────────────────────────────────────────────────────────────────


def _extract_notion(report: MigrationReport, options: MigrationOptions, notion) -> dict:
    """Notion 에서 읽을 것을 전부 읽어 사전 하나로 만든다."""
    empty = {
        "tasks": [], "projects": [], "documents": [],
        "ticket_blocks": {}, "document_bodies": {}, "taxonomy": {},
        "project_titles": {}, "attachments": [], "people": {}, "comments": [],
        "expected": {},
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

    # 티켓도 문서와 똑같이 **블록 그대로** 넘긴다. 여기서 마크다운을 만들면 본문
    # 이미지의 주소를 넣을 수 없다 — 그 주소는 바이트를 우리 저장소로 옮긴 뒤에야
    # 생기고, 옮기는 일은 DB 를 아는 적재가 한다(D4 · B2).
    ticket_blocks: dict[str, list[dict]] = {}
    document_bodies: dict[str, list[dict]] = {}
    if options.with_bodies:
        for raw in tasks:
            page_id = raw.get("id")
            if not page_id:
                continue
            ticket_blocks[page_id] = notion.page_blocks(
                page_id, last_edited=raw.get("last_edited_time")
            )
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
    # 여기 있던 `ticket_body_media_not_moved` 예외는 **걷었다.** 그 예외의 사유는
    # 「붙일 자리의 `uploaded_by_user_id` 가 NOT NULL 이라 못 옮긴다」였고, 0014 가 그
    # 칸을 nullable 로 바꿔 사유 자체가 없어졌다(D12). 이제 티켓 본문의 파일도 실제로
    # 옮겨지고, **정말 못 옮긴 것만** 적재가 `body_media_rejected` 로 남긴다.

    comments, comment_rows = _extract_comments(report, options, notion, tasks, documents)

    attachments = []
    people: dict[str, dict] = {}
    for raw in (*tasks, *documents):
        attachments.extend(transform.attachments_of(raw))
        _collect_people(raw, people)

    return {
        "tasks": tasks,
        "projects": projects,
        "documents": documents,
        "ticket_blocks": ticket_blocks,
        "document_bodies": document_bodies,
        "taxonomy": taxonomy,
        # 문서의 「프로젝트 선택」 34건이 가리키는 이름. `document_relations` 는 문서와
        # 문서만 잇는 표라 프로젝트를 가리킬 수 없어서 태그로 남긴다(`_tag_document`).
        "project_titles": transform.relation_titles(projects),
        "attachments": attachments,
        "people": people,
        "comments": comments,
        "expected": {
            "tasks": len(tasks),
            "documents": len(documents),
            "projects": len(projects),
            # **원본이 준 날것의 수**다. 읽어서 만든 `comments` 의 길이가 아니다 — 그
            # 둘을 같은 값으로 세면 파싱이 버린 댓글이 「원본에 없었다」가 된다.
            "comments": comment_rows,
        },
    }


def _extract_comments(report, options: MigrationOptions, notion, tasks, documents):
    """페이지 댓글을 읽는다 (D11). **문서 쪽도 세어 본다.**

    문서에는 원본 댓글이 0건이라는 것이 전수 훑기의 결론이지만, 그 사실을 코드가
    가정하면 다음에 하나가 생긴 날 조용히 사라진다. 캐시가 이미 있어 읽는 값이 거의
    0 이므로 **세고, 있으면 말한다** — 문서 댓글은 `document_comments` 표로 가야 하고
    그 길은 이번 범위가 아니다.
    """
    if not options.with_comments:
        report.finding(
            SEVERITY_NOTE, "comments_skipped", "notion",
            "이 회차는 댓글을 읽지 않았습니다.",
        )
        return [], 0

    comments: list = []
    rows = 0
    for raw in tasks:
        page_id = raw.get("id")
        if not page_id:
            continue
        found = notion.page_comments(page_id)
        rows += len(found)
        comments.extend(transform.comments_of(page_id, found))

    in_documents = 0
    for raw in documents:
        page_id = raw.get("id")
        if not page_id:
            continue
        in_documents += len(notion.page_comments(page_id))
    if in_documents:
        report.finding(
            SEVERITY_CLASSIFIED, "document_comment_not_moved", "document_comments",
            f"문서에 달린 댓글 {in_documents}건은 이번 경로가 옮기지 않습니다.",
        )
    return comments, rows


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
        "ticket_comments", "migration_exceptions", "documents",
        "document_versions", "document_attachments", "document_tags", "tags",
        "files", "knowledge_spaces", "legacy_mapping",
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


# ── Confluence 한 번 가져오기 (문서 개편 14~20번) ────────────────────────────


def import_confluence(
    db: Session,
    *,
    source,
    actor,
    space_keys: list[str],
    settings=None,
    report: MigrationReport | None = None,
    with_files: bool = True,
    with_comments: bool = True,
    limit_pages: int | None = None,
    dry_run: bool = False,
    fallback_author=None,
) -> MigrationReport:
    """CMP · ClovirONE 두 Space 의 **모든** 페이지를 문서로 가져온다.

    ## 실패의 단위가 페이지 하나다

    페이지마다 SAVEPOINT 를 연다. 한 페이지가 죽어도 앞의 것들이 안 되감긴다 — 524건
    회차에서 한 건 때문에 처음부터 다시 도는 도구는 아무도 두 번 안 돌린다.

    ## 판정은 마지막 줄의 초록이 아니다

    `reconcile()` 이 「열거한 수 == 설명된 수」를 본다. 안 맞으면 Blocking Finding 이
    남고, 그것이 「전부 가져왔다」를 주장이 아니라 증명으로 만든다.
    """
    from app.migration.load_confluence import ConfluenceLoader

    report = report or MigrationReport()
    report.mode = "import-confluence" + ("(dry-run)" if dry_run else "")
    report.started_at = _now()
    report.target_database = database_label(db)

    spaces = source.find_spaces(space_keys)
    pages: list[dict] = []
    for key, space_id in spaces.items():
        pages.extend(source.list_pages(space_id, space_key=key))
        # 블로그 글은 실측 0건이지만 **세어서 보고한다** — 「0이었다」와 「안 봤다」는
        # 다른 사실이고, 그 둘을 못 가르면 다음 사람이 다시 센다.
        blogs = source.list_blogposts(space_id, space_key=key)
        if blogs:
            report.finding(
                SEVERITY_NOTE, "confluence_blogposts_seen", "documents",
                f"{key}: 블로그 글 {len(blogs)}건은 이번 범위가 아닙니다.",
            )
    if limit_pages:
        pages = pages[:limit_pages]

    loader = ConfluenceLoader(
        db, report=report, actor=actor, settings=settings,
        fallback_author=fallback_author,
    )
    fetch = source.download if (with_files and not dry_run) else None
    #: 원본이 가진 첨부 수. 대조 게이트가 「하나도 못 옮겼다」를 잡는 근거다.
    attachments_seen = 0

    for page in pages:
        page_id = str(page.get("id") or "")
        try:
            with db.begin_nested():
                body = source.page_body(
                    page_id, version=(page.get("version") or {}).get("number")
                )
                # 원본 작성자의 **이름**을 봉투에 실어 준다(`_author_email` 과 같은 규약).
                # 우리 계정으로는 못 잇는다 — Confluence 가 이메일을 안 주기 때문이다.
                # 서로 다른 작성자가 스물몇 명이라 소스가 캐시로 받는다.
                body["_author_name"] = source.author_name(body.get("authorId"))
                attachments = source.page_attachments(page_id) if with_files else []
                attachments_seen += len(attachments)
                comments = source.page_comments(page_id) if with_comments else []
                loader.load_page(
                    page, body,
                    attachments=attachments, comments=comments,
                    fetch=fetch, dry_run=dry_run,
                )
        except Exception as exc:  # noqa: BLE001 - 한 페이지가 회차를 멈추지 않는다
            # 🔴 `account` 가 참일 때만 센다. 로더가 이미 결과를 적은 페이지를 여기서
            # 또 세면 3건이 4건으로 보고된다 — 대조 게이트가 실제로 잡은 결함이다.
            if loader.result.account(page_id):
                loader.result.documents_skipped += 1
                loader.result.skipped_page_ids.append(page_id)
            report.finding(
                SEVERITY_BLOCKING, "confluence_page_failed", "documents",
                f"{page.get('title', '')}: {type(exc).__name__}: {exc}", ref=page_id,
            )

    report.stages.append(loader.reconcile(
        len(pages),
        # 세기만 하는 회차와 파일을 안 받는 회차는 첨부 대조에서 뺀다 — 「안 받기로 했다」와
        # 「못 받았다」는 다른 사실이다.
        attachments_seen=(attachments_seen if fetch is not None else None),
    ))
    # `notion` 칸을 「외부 소스 통계」로 함께 쓴다 — 보고서가 이미 그 칸을 찍는다.
    report.notion = {"confluence": source.stats.as_dict(), "load": loader.result.as_dict()}
    if dry_run:
        # 세기만 한 회차는 아무것도 안 남긴다.
        db.rollback()
    else:
        db.commit()
    report.finished_at = _now()
    return report
