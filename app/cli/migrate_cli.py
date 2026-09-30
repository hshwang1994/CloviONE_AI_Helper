"""Migration CLI — Dry Run 과 Cutover 가 **같은 코드를 부른다** (S13).

    python -m app.cli.migrate_cli plan      --sqlite <path>
    python -m app.cli.migrate_cli extract   --sqlite <path> --cache <dir> [--comments]
    python -m app.cli.migrate_cli dry-run   --sqlite <path> --cache <dir> --report <dir>
    python -m app.cli.migrate_cli verify    --sqlite <path>
    python -m app.cli.migrate_cli reimport-bodies --cache <dir> [--dry-run]

`dry-run` 과 Cutover 의 차이는 **`DATABASE_URL` 이 어디를 가리키는가** 하나다. 도구가
모드에 따라 다르게 동작하면 Dry Run 이 증명하는 것이 Cutover 에서 성립하지 않는다 —
그래서 `--mode cutover` 는 이름표일 뿐이고 코드 경로가 같다.

## `plan` 이 따로 있는 이유

옮기기 전에 **무엇을 옮기고 무엇을 안 옮기는지** 먼저 읽을 수 있어야 한다. DB 도
Notion 도 안 건드리고 소스 스키마만 본다.

## `extract` 가 따로 있는 이유

Notion 재수집은 십 분 넘게 걸린다. 캐시를 먼저 채워 두면 `dry-run` 을 여러 번 돌려도
그 시간을 다시 쓰지 않는다 — 그리고 캐시가 곧 「그때 Notion 이 뭐라고 했는가」의 원장이다.

## `reimport-bodies` 가 따로 있는 이유

컷오버 뒤에 본문을 고쳐야 할 때 `dry-run` 을 다시 돌리면 **표 63개가 소스 스냅숏으로
덮인다.** 그 스냅숏은 컷오버 시각의 사진이라, 그 뒤에 사람이 만든 티켓과 댓글과 설정이
사라진다. 되돌릴 수 없는 사고이므로 본문만 건드리는 길을 따로 둔다 — 그리고 이 명령은
`--sqlite` 를 **받지 않는다.** 실수로 함께 돌릴 길 자체가 없어야 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.allowlist import AllowlistRegistry
from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.errors import AppError
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider
from app.migration import plan as plan_mod
from app.migration import runner, validate
from app.migration.report import MigrationReport
from app.migration.source_notion import NotionSource
from app.migration.source_sqlite import SqliteSource

# 콘솔이 cp949 면 한글에서 죽는다. 결과를 못 읽는 실패는 실패보다 나쁘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _notion(settings: Settings, args) -> NotionSource:
    outbound = OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
    )
    return NotionSource(
        outbound,
        secret_ref=args.secret_ref or settings.notion_docs_token_ref,
        cache_dir=args.cache,
        api_version=settings.notion_api_version,
        api_base=settings.notion_api_base,
        throttle_seconds=args.throttle,
    )


def _overrides(args) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in args.database or []:
        role, _, value = pair.partition("=")
        if not value:
            raise SystemExit(f"--database 는 role=id 형식입니다: {pair}")
        out[role.strip()] = value.strip()
    return out


def cmd_plan(args) -> int:
    """소스 스키마를 계획과 대조해 보여 준다. **아무것도 안 쓴다.**"""
    with SqliteSource(args.sqlite) as source:
        classification = plan_mod.classify(source.tables())
        payload = {
            "source": str(args.sqlite),
            "tables": len(source.tables()),
            "copy": [
                {"source": c.source, "target": c.target, "rows": source.count(c.source)}
                for c in plan_mod.ordered_copies(classification)
            ],
            "dropped": [
                {"table": table, "reason": reason, "rows": source.count(table)}
                for table, reason in classification.dropped
            ],
            "derived": [
                {"table": table, "rows": source.count(table)}
                for table in classification.derived
            ],
            "unknown": list(classification.unknown),
            "absent_in_source": list(classification.missing_target),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    # 계획에 없는 표가 있으면 **여기서 멈춘다.** 사람이 정하기 전에 옮기면 안 된다.
    return 1 if payload["unknown"] else 0


def cmd_extract(args) -> int:
    """Notion 을 읽어 캐시에 담는다. DB 는 안 건드린다."""
    settings = Settings()
    notion = _notion(settings, args)
    databases = notion.discover(overrides=_overrides(args))
    total = 0
    for role, database_id in sorted(databases.items()):
        rows = notion.query_database(database_id, role=role)
        total += len(rows)
        print(f"{role}: {len(rows)}행")
        if args.bodies and role in ("tasks", "documents"):
            for raw in rows:
                notion.page_blocks(
                    raw.get("id"), last_edited=raw.get("last_edited_time")
                )
        # 댓글 캐시를 미리 채운다 (D11). 안 채우면 그 왕복이 `dry-run` 안으로 들어가고,
        # 페이지 1,235건에 초당 3요청이면 회차가 십 분 넘게 길어진다.
        if args.comments and role in ("tasks", "documents"):
            for raw in rows:
                notion.page_comments(raw.get("id"))
    print(json.dumps(notion.stats.as_dict(), ensure_ascii=False, indent=2))
    print(f"EXTRACT_OK rows={total} cache={notion.cache}")
    return 0


def cmd_dry_run(args) -> int:
    settings = Settings()
    notion = None if args.no_notion else _notion(settings, args)
    options = runner.MigrationOptions(
        sqlite_path=args.sqlite,
        mode=args.mode,
        with_notion=not args.no_notion,
        with_bodies=not args.no_bodies,
        with_files=not args.no_files,
        with_comments=not args.no_comments,
        database_overrides=_overrides(args),
        limit_pages=args.limit,
    )
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        report = runner.run(db, options, notion=notion, settings=settings)
    return _emit(report, args)


def cmd_reimport_bodies(args) -> int:
    """본문과 첨부와 문서 태그와 공간 소유, 그리고 티켓 댓글만 다시 넣는다 (D5 · D11).

    `dry-run` 을 다시 돌리지 않는 이유는 그것이 **표 63개를 소스 스냅숏에서 복사**하기
    때문이다. 그 스냅숏은 컷오버 시각의 사진이고, 지금 다시 돌리면 그 뒤에 사람이 만든
    티켓·댓글·설정이 3주 전 상태로 덮인다 — 되돌릴 수 없는 사고다.

    소스 SQLite 를 안 받는 것이 이 명령의 계약이다. 인자로도 못 주게 해서 「실수로 함께
    돌렸다」가 아예 생기지 않게 한다.
    """
    settings = Settings()
    notion = _notion(settings, args)
    options = runner.MigrationOptions(
        sqlite_path="",
        mode="reimport-bodies",
        with_files=not args.no_files,
        with_comments=not args.no_comments,
        database_overrides=_overrides(args),
        limit_pages=args.limit,
        scope=getattr(args, "scope", "all"),
        only_pages=tuple(getattr(args, "pages", None) or ()),
    )
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        # 작성자를 이메일로도 이름으로도 못 푼 문서가 앉을 계정. Confluence 쪽과 같은
        # 규칙이다 — 두 소스가 같은 문제를 갖는다(D-440).
        fallback = (
            _actor(db, args.fallback_author)
            if getattr(args, "fallback_author", "") else None
        )
        report = runner.reimport_bodies(
            db, options, notion=notion, settings=settings, dry_run=args.dry_run,
            fallback_author=fallback,
        )
    print(report.to_text())
    if args.report:
        out = Path(args.report)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(report.to_json(), encoding="utf-8")
        (out / "report.txt").write_text(report.to_text(), encoding="utf-8")
        print(f"\n원장: {out}")
    print("\nREIMPORT_DRY_RUN_OK" if args.dry_run else "\nREIMPORT_OK")
    return 0


def cmd_import_confluence(args) -> int:
    """Confluence 두 Space 의 **모든** 페이지를 문서로 가져온다 (문서 개편 14~20번).

    한 번 가져오기다. 주기 동기화도, 변경 감지도, 되돌려 쓰기도 없다 — 이 경로에는
    Confluence 로 나가는 쓰기 호출 자체가 없다.
    """
    from app.migration.source_confluence import ConfluenceSource

    settings = Settings()
    outbound = OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
    )
    source = ConfluenceSource(
        outbound,
        api_base=args.site,
        secret_ref=args.secret_ref,
        cache_dir=args.cache,
        throttle_seconds=args.throttle,
    )
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        actor = _actor(db, args.actor)
        # 작성자를 이메일로도 이름으로도 못 푼 문서가 앉을 계정. 안 주면 회차를 돌린
        # 사람이다. 원본 이름은 그래도 `legacy_author_name` 에 남는다.
        fallback = _actor(db, args.fallback_author) if args.fallback_author else actor
        report = runner.import_confluence(
            db,
            source=source,
            actor=actor,
            fallback_author=fallback,
            space_keys=args.space,
            settings=settings,
            with_files=not args.no_files,
            with_comments=not args.no_comments,
            limit_pages=args.limit or None,
            dry_run=args.dry_run,
        )
    print(report.to_text())
    if args.report:
        out = Path(args.report)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(report.to_json(), encoding="utf-8")
        (out / "report.txt").write_text(report.to_text(), encoding="utf-8")
        print(f"\n원장: {out}")
    # 🔴 판정은 이 줄이 아니라 Blocking Finding 이 0인가다. 「전부 가져왔다」는
    # `confluence_reconcile` 단계가 증명한다.
    blocking = [f for f in report.findings if f.severity == "blocking"]
    print("\nCONFLUENCE_DRY_RUN_OK" if args.dry_run
          else ("CONFLUENCE_IMPORT_OK" if not blocking else "CONFLUENCE_IMPORT_FAILED"))
    return 0 if (args.dry_run or not blocking) else 1


def _actor(db, email: str):
    """가져온 사람. 안 주면 시스템 관리자 하나를 고른다 — 작성자를 못 푼 문서·댓글이
    이 계정으로 앉으므로 **실재하는 계정**이어야 한다."""
    import sqlalchemy as sa

    from app.users.models import User

    if email:
        row = db.execute(
            sa.select(User).where(sa.func.lower(User.email) == email.strip().lower())
        ).scalar_one_or_none()
        if row is None:
            raise SystemExit(f"그 이메일의 계정을 찾지 못했습니다: {email}")
        return row
    row = db.execute(
        sa.select(User).where(User.role == "system_admin").order_by(User.created_at)
    ).scalars().first()
    if row is None:
        raise SystemExit("가져온 사람으로 적을 계정이 없습니다. --actor 로 지정해 주세요.")
    return row


def cmd_prune_empty(args) -> int:
    """본문이 없거나 아주 짧은 문서를 치운다.

    Confluence 와 Notion 에는 제목만 있는 페이지가 흔하다 — 하위를 묶는 목차이거나 만들다
    만 자리다. 우리 쪽에서는 목록과 검색에서 자리를 차지하는데 열어 보면 아무것도 없다.

    지우는 방식은 **제품의 삭제**다: 보관 처리라 휴지통에 뜨고 되돌릴 수 있다.
    """
    from app.migration import prune as prune_mod
    from app.migration.report import MigrationReport

    settings = Settings()
    factory = make_session_factory(make_engine(settings.database_url))
    report = MigrationReport(mode="prune-empty")
    with factory() as db:
        actor = _actor(db, args.actor)
        result = prune_mod.prune_empty(
            db, actor=actor, max_chars=args.max_chars,
            dry_run=args.dry_run, report=report,
        )
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        for title in result.titles[:40]:
            print(f"  - {title}")
        if len(result.titles) > 40:
            print(f"  ... 그리고 {len(result.titles) - 40}건 더")
        for finding in report.findings:
            print(f"[{finding.severity}] {finding.kind}: {finding.detail}")
    if args.report:
        report.write(args.report)
    ok = result.refused_native == 0
    print()
    print("PRUNE_DRY_RUN_OK" if args.dry_run
          else ("PRUNE_OK" if ok else "PRUNE_FAILED"))
    return 0 if (args.dry_run or ok) else 1


def cmd_classify(args) -> int:
    """가져온 문서의 프로젝트·분류·태그를 다시 정한다 (문서 개편 11·12·15·16번).

    두 걸음이다. `--emit` 이 **사람이 읽고 고칠 파일**을 만들고, `--apply` 가 그 파일만
    읽어 쓴다. 한 번에 판정해 버리지 않는 이유는 `app/migration/classify.py` 머리말에 있다.
    """
    from app.migration import classify as classify_mod
    from app.migration.report import MigrationReport

    if not args.emit and not args.apply_path:
        raise SystemExit("--emit 이나 --apply 중 하나가 필요합니다.")

    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    report = MigrationReport(mode="classify")
    with factory() as db:
        if args.emit:
            documents = classify_mod.migrated_documents(
                db, source=(args.source or None)
            )
            proposals = classify_mod.propose(
                db, documents=documents, source=(args.source or "all")
            )
            out = classify_mod.write_proposals(args.emit, proposals)
            by = {}
            for p in proposals:
                by[p.decision] = by.get(p.decision, 0) + 1
            print(f"문서 {len(proposals)}건 · {by}")
            print(f"제안: {out}")
            print("\n검토한 뒤 --apply 로 적용해 주세요.")
            print("\nCLASSIFY_EMIT_OK")
            return 0

        actor = _actor(db, args.actor)
        rows = classify_mod.read_proposals(args.apply_path)
        result = classify_mod.apply(
            db, rows, actor=actor, report=report, dry_run=args.dry_run
        )
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        for finding in report.findings:
            print(f"[{finding.severity}] {finding.kind}: {finding.detail}")
    # 🔴 자체 작성 문서를 하나라도 건드리려 했으면 **실패다.** 그 시도가 있었다는 것은
    # 제안 파일이나 생성기가 틀렸다는 뜻이고, 조용히 넘기면 다음 회차에 또 온다.
    ok = result.refused_native == 0
    print("\nCLASSIFY_DRY_RUN_OK" if args.dry_run
          else ("CLASSIFY_APPLY_OK" if ok else "CLASSIFY_APPLY_FAILED"))
    return 0 if (args.dry_run or ok) else 1


def cmd_verify(args) -> int:
    """이미 적재된 DB 에 검증만 다시 돌린다. **적재는 안 한다.**"""
    settings = Settings()
    report = MigrationReport(mode="verify")
    report.source_sqlite = str(args.sqlite)
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db, SqliteSource(args.sqlite) as source:
        report.target_database = runner.database_label(db)
        report.source_fingerprint = runner.source_fingerprint(source)
        expected = _expected_from_cache(args.cache)
        validate.validate(db, source, report, notion=expected)
    return _emit(report, args)


def _expected_from_cache(cache: str) -> dict:
    """캐시에 남은 Notion 행 수. 없으면 그 검사는 건너뛴다(빈 사전)."""
    out: dict = {}
    root = Path(cache)
    for role in ("tasks", "documents", "projects"):
        path = root / f"{role}.json"
        if not path.exists():
            continue
        try:
            out[role] = len(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def _emit(report: MigrationReport, args) -> int:
    print(report.to_text())
    if args.report:
        out = Path(args.report)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(report.to_json(), encoding="utf-8")
        (out / "report.txt").write_text(report.to_text(), encoding="utf-8")
        print(f"\n원장: {out}")
    print(
        "\nMIGRATION_DRY_RUN_OK" if report.passed else "\nMIGRATION_DRY_RUN_FAILED"
    )
    return 0 if report.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migrate_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(node, *, needs_cache: bool = True) -> None:
        node.add_argument("--sqlite", required=True, help="옛 SQLite 스냅숏 경로")
        if needs_cache:
            node.add_argument("--cache", default="var/migration-cache")
            node.add_argument("--secret-ref", default="", dest="secret_ref")
            node.add_argument("--throttle", type=float, default=0.34)
            node.add_argument(
                "--database", action="append",
                help="role=database_id 로 Notion DB 를 직접 지정한다 (제목 조회 대신)",
            )

    node = sub.add_parser("plan")
    common(node, needs_cache=False)
    node.set_defaults(func=cmd_plan)

    node = sub.add_parser("extract")
    common(node)
    node.add_argument("--bodies", action="store_true", help="본문 블록까지 받는다")
    node.add_argument("--comments", action="store_true", help="페이지 댓글까지 받는다")
    node.set_defaults(func=cmd_extract)

    node = sub.add_parser("dry-run")
    common(node)
    node.add_argument("--report", default="", help="보고서를 쓸 디렉터리")
    node.add_argument("--mode", default="dry-run", choices=["dry-run", "cutover"])
    node.add_argument("--no-notion", action="store_true")
    node.add_argument("--no-bodies", action="store_true")
    node.add_argument("--no-files", action="store_true")
    node.add_argument("--no-comments", action="store_true", help="댓글을 안 옮긴다")
    node.add_argument("--limit", type=int, default=0, help="표본 회차용 페이지 상한")
    node.set_defaults(func=cmd_dry_run)

    # 소스 SQLite 를 안 받는다. 표 복사를 함께 돌릴 길 자체를 없앤다.
    node = sub.add_parser("reimport-bodies")
    node.add_argument("--cache", default="var/migration-cache")
    node.add_argument("--secret-ref", default="", dest="secret_ref")
    node.add_argument("--throttle", type=float, default=0.34)
    node.add_argument(
        "--database", action="append",
        help="role=database_id 로 Notion DB 를 직접 지정한다 (제목 조회 대신)",
    )
    node.add_argument("--report", default="", help="보고서를 쓸 디렉터리")
    node.add_argument("--no-files", action="store_true")
    # 댓글은 **기본으로 함께 온다** (D11). 더하기만 하는 경로라 본문 재이관과 같은
    # 회차에서 안전하고, 따로 돌리면 사람이 두 명령을 기억해야 한다.
    node.add_argument(
        "--fallback-author", default="", dest="fallback_author",
        help="작성자를 못 푼 문서가 앉을 계정 이메일 (안 주면 안 앉힌다)",
    )
    node.add_argument("--no-comments", action="store_true", help="댓글을 안 옮긴다")
    node.add_argument("--limit", type=int, default=0, help="표본 회차용 페이지 상한")
    node.add_argument(
        "--dry-run", action="store_true",
        help="무엇이 바뀔지 세기만 하고 아무것도 안 쓴다",
    )
    node.add_argument(
        "--scope", default="all", choices=["all", "documents"],
        help="documents 면 문서 본문만 고친다 (티켓 본문 약 1,120건은 그대로 둔다)",
    )
    node.add_argument(
        "--page", action="append", default=None, dest="pages",
        help="이 Notion 페이지만 다시 넣는다. 여러 번 줄 수 있다 (기본: 전부)",
    )
    node.set_defaults(func=cmd_reimport_bodies)

    node = sub.add_parser("import-confluence")
    node.add_argument(
        "--site", required=True,
        help="Confluence 사이트 주소(예: https://example.atlassian.net). 이관 허용 목록에도 그 호스트를 더한다",
    )
    node.add_argument("--cache", default="var/migration-cache")
    node.add_argument("--secret-ref", default="confluence_token", dest="secret_ref")
    node.add_argument("--throttle", type=float, default=0.12)
    node.add_argument(
        "--space", action="append", required=True,
        help="가져올 Space key. 여러 번 줄 수 있다",
    )
    node.add_argument("--actor", default="", help="가져온 사람으로 적을 계정 이메일")
    node.add_argument(
        "--fallback-author", default="", dest="fallback_author",
        help="작성자를 못 푼 문서가 앉을 계정 이메일 (기본: 가져온 사람)",
    )
    node.add_argument("--report", default="", help="보고서를 쓸 디렉터리")
    node.add_argument("--no-files", action="store_true")
    node.add_argument("--no-comments", action="store_true")
    node.add_argument("--limit", type=int, default=0, help="표본 회차용 페이지 상한")
    node.add_argument(
        "--dry-run", action="store_true",
        help="무엇이 들어올지 세기만 하고 아무것도 안 쓴다",
    )
    node.set_defaults(func=cmd_import_confluence)

    node = sub.add_parser("classify")
    node.add_argument(
        "--emit", default="",
        help="제안을 이 파일(jsonl)로 쓴다. 아무것도 안 고친다",
    )
    node.add_argument(
        "--apply", default="", dest="apply_path",
        help="사람이 검토한 파일을 실제로 적용한다",
    )
    node.add_argument(
        "--source", default="", choices=["", "notion", "confluence"],
        help="어느 소스로 들어온 문서만 볼 것인가 (기본: 전부)",
    )
    node.add_argument("--actor", default="", help="적용을 수행할 계정 이메일")
    node.add_argument("--report", default="")
    node.add_argument("--dry-run", action="store_true")
    node.set_defaults(func=cmd_classify)

    node = sub.add_parser("prune-empty")
    node.add_argument(
        "--max-chars", type=int, default=20,
        help="본문이 이 글자 수 이하면 빈 문서로 본다 (기본 20)",
    )
    node.add_argument("--actor", default="", help="지운 사람으로 적을 계정 이메일")
    node.add_argument("--report", default="")
    node.add_argument("--dry-run", action="store_true")
    node.set_defaults(func=cmd_prune_empty)

    node = sub.add_parser("verify")
    common(node)
    node.add_argument("--report", default="")
    node.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "limit", 0) == 0:
        args.limit = None
    try:
        return args.func(args)
    except AppError as exc:
        print(f"오류: {exc.message}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
