"""저장소 CLI — Installer Stage 11 과 운영자가 같은 코드를 부른다 (S8).

    python -m app.cli.storage_cli bootstrap      # 기본 LOCAL 저장소를 세운다
    python -m app.cli.storage_cli status         # 지금 상태를 JSON 으로 낸다
    python -m app.cli.storage_cli units          # 마운트 유닛과 drop-in 을 내보낸다
    python -m app.cli.storage_cli sweep          # 아무도 안 가리키는 바이트를 치운다
    python -m app.cli.storage_cli verify         # 행이 가리키는 파일이 실제로 있는가
    python -m app.cli.storage_cli archive        # 운영 → 백업
    python -m app.cli.storage_cli restore-files  # 백업 → 운영

**설치 스크립트가 자기만의 판정을 갖지 않게** 하려고 만든 명령이다. 셸에서 `stat` 을
불러 장치 번호를 비교하는 순간 판정이 두 벌이 되고, 그 둘은 언젠가 갈린다
(`scripts/check_domain_single_source.py` 가 파이썬 쪽에서 같은 규칙을 지킨다).

`status` 의 종료코드가 계약이다: 켜진 운영 저장소에 **지금 쓸 수 있으면 0**, 아니면 1.
Stage 11 이 그 값을 그대로 읽는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.errors import AppError
from app.storage import archive, service
from app.storage.models import StorageProvider
from app.storage.units import DROPIN_NAME, render_dropin, render_mount_unit, unit_name

# 콘솔이 cp949 면 한글에서 죽는다. 결과를 못 읽는 실패는 실패보다 나쁘다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def cmd_bootstrap(db: Session, settings: Settings, args) -> int:
    provider = service.ensure_default_provider(db, settings)
    db.commit()
    print(f"STORAGE_BOOTSTRAP_OK name={provider.name} kind={provider.kind} path={provider.base_path}")
    return 0


def cmd_status(db: Session, settings: Settings, args) -> int:
    health = service.storage_health(db)
    print(json.dumps(health, ensure_ascii=False, indent=2, default=str))
    if health["warning"]:
        print(f"경고: {health['warning']}", file=sys.stderr)
    return 0 if health["operational_ok"] else 1


def cmd_units(db: Session, settings: Settings, args) -> int:
    """마운트 유닛과 drop-in 을 만든다. `--out` 없으면 표준출력으로 보여만 준다.

    유닛을 **설치하지는 않는다.** `/etc/systemd/system` 에 쓰는 것은 root 의 일이고,
    이 명령은 서비스 계정으로도 돌 수 있어야 한다.
    """
    rows = list(
        db.execute(
            select(StorageProvider)
            .where(StorageProvider.enabled.is_(True), StorageProvider.mount_point.isnot(None))
            .order_by(StorageProvider.name)
        ).scalars().all()
    )
    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    for row in rows:
        config = json.loads(row.config_json or "{}")
        source = str(config.get("source") or "").strip()
        if not source:
            print(f"오류: {row.name} 에 마운트 소스가 없습니다.", file=sys.stderr)
            return 2
        credentials = (
            str(Path(settings.secrets_dir).resolve() / row.credentials_ref)
            if row.credentials_ref
            else None
        )
        body = render_mount_unit(
            service.ref_of(row),
            source=source,
            options=str(config.get("options") or ""),
            credentials_path=credentials,
        )
        name = unit_name(row.mount_point)
        names.append(name)
        if out_dir:
            (out_dir / name).write_text(body, encoding="utf-8")
        else:
            print(f"# ── {name} ──")
            print(body)

    dropin = render_dropin([r.mount_point for r in rows])
    if out_dir:
        (out_dir / DROPIN_NAME).write_text(dropin, encoding="utf-8")
        print(f"STORAGE_UNITS_OK units={len(names)} dir={out_dir}")
    else:
        print(f"# ── {DROPIN_NAME} ──")
        print(dropin)
    return 0


def cmd_add_provider(db: Session, settings: Settings, args) -> int:
    """저장소를 하나 만든다. 웹 화면과 **같은 서비스 함수**를 부른다.

    화면 없이도 저장소를 세울 수 있어야 하는 이유가 둘이다: 설치 직후에는 아직 관리자
    계정이 없을 수 있고(Stage 10 이 그 사실을 말한다), 실검증 하네스는 브라우저를
    안 쓴다. 검증이 다른 코드를 쓰면 「제품으로 검증했다」가 거짓이 된다.
    """
    provider = service.create_provider(
        db,
        name=args.name, kind=args.kind, role=args.role,
        base_path=args.base_path, mount_point=(args.mount_point or None),
        source=args.source, options=args.options,
        credentials_ref=(args.credentials_ref or None),
        enabled=not args.disabled,
    )
    db.commit()
    print(f"STORAGE_PROVIDER_OK id={provider.id} name={provider.name} kind={provider.kind}")
    return 0


def cmd_disable_provider(db: Session, settings: Settings, args) -> int:
    provider = db.execute(
        select(StorageProvider).where(StorageProvider.name == args.name)
    ).scalars().first()
    if provider is None:
        print(f"오류: 저장소를 찾지 못했습니다({args.name}).", file=sys.stderr)
        return 1
    service.update_provider(db, provider, enabled=False)
    db.commit()
    print(f"STORAGE_PROVIDER_DISABLED name={provider.name}")
    return 0


def cmd_sweep(db: Session, settings: Settings, args) -> int:
    removed = service.sweep_orphans(db)
    db.commit()
    print(f"STORAGE_SWEEP_OK removed={removed}")
    return 0


def cmd_verify(db: Session, settings: Settings, args) -> int:
    result = service.verify_files(db)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if not result["missing"] and not result["corrupt"] else 1


def cmd_archive(db: Session, settings: Settings, args) -> int:
    return _run_copy(archive.archive_to_backup, db)


def cmd_restore_files(db: Session, settings: Settings, args) -> int:
    return _run_copy(archive.restore_from_backup, db)


def _run_copy(fn, db: Session) -> int:
    try:
        result = fn(db)
    except archive.ArchiveNotPossible as exc:
        # 「0건 성공」과 구별해서 말한다. 그 둘을 같은 모양으로 보고하면 마운트가 빠진
        # 밤에도 이력이 초록으로 남는다.
        print(f"STORAGE_COPY_IMPOSSIBLE {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="storage_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap").set_defaults(func=cmd_bootstrap)
    sub.add_parser("status").set_defaults(func=cmd_status)
    units = sub.add_parser("units")
    units.add_argument("--out", default="", help="유닛 파일을 쓸 디렉터리")
    units.set_defaults(func=cmd_units)
    add = sub.add_parser("add-provider")
    add.add_argument("--name", required=True)
    add.add_argument("--kind", required=True, choices=["LOCAL", "NFS", "SMB"])
    add.add_argument("--role", default="OPERATIONAL", choices=["OPERATIONAL", "BACKUP"])
    add.add_argument("--base-path", required=True, dest="base_path")
    add.add_argument("--mount-point", default="", dest="mount_point")
    add.add_argument("--source", default="", help="nas:/export 또는 //nas/share")
    add.add_argument("--options", default="")
    # **이름이지 값이 아니다.** 비밀번호를 명령행에 적으면 프로세스 목록과 셸 이력에 남는다.
    add.add_argument("--credentials-ref", default="", dest="credentials_ref")
    add.add_argument("--disabled", action="store_true")
    add.set_defaults(func=cmd_add_provider)

    disable = sub.add_parser("disable-provider")
    disable.add_argument("--name", required=True)
    disable.set_defaults(func=cmd_disable_provider)

    sub.add_parser("sweep").set_defaults(func=cmd_sweep)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    sub.add_parser("archive").set_defaults(func=cmd_archive)
    sub.add_parser("restore-files").set_defaults(func=cmd_restore_files)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        try:
            return args.func(db, settings, args)
        except AppError as exc:
            db.rollback()
            print(f"오류: {exc.message}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
