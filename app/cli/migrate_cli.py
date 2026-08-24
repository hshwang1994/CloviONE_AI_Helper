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
    )
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        report = runner.reimport_bodies(
            db, options, notion=notion, settings=settings, dry_run=args.dry_run
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
    node.add_argument("--no-comments", action="store_true", help="댓글을 안 옮긴다")
    node.add_argument("--limit", type=int, default=0, help="표본 회차용 페이지 상한")
    node.add_argument(
        "--dry-run", action="store_true",
        help="무엇이 바뀔지 세기만 하고 아무것도 안 쓴다",
    )
    node.set_defaults(func=cmd_reimport_bodies)

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
