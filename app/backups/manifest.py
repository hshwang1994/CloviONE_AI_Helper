"""백업 세트의 `manifest.json` — **백업과 함께 이동하는 사실** (S12 · D-204).

## 왜 DB 컬럼이 아니라 파일인가

`backups` 표에도 같은 값을 들 수 있다. 그런데 매니페스트가 답해야 하는 질문은
**「이 파일 하나를 들고 낯선 서버 앞에 섰을 때」** 나온다 — 스키마가 몇 판인지, 어떤
제품인지, 무엇이 안 담겼는지. 그 순간 원래 DB 는 없다. 그래서 정본은 **세트 디렉터리
안의 파일**이고, DB 사본은 목록 화면이 디스크를 안 읽으려고 두는 편의다.

## 세트의 모양

```
backup-20260823_140000_123456/
    database.dump     pg_dump -Fc (정책이 정한 표의 행은 빠져 있다)
    manifest.json     이 파일
    SHA256SUMS        위 둘의 체크섬. `sha256sum -c` 가 그대로 읽는다
```

`SHA256SUMS` 를 따로 두는 이유: 매니페스트가 덤프의 체크섬을 들지만, **매니페스트 자신의
체크섬은 자기 안에 못 든다.** 셋 다 한 곳에서 검증되려면 바깥에 한 겹이 필요하다.
표준 형식(`<sha256>  <이름>`)을 쓴다 — 우리 도구가 없는 서버에서도 확인할 수 있어야 한다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.backups.pg_backup import sha256_file
from app.backups.policy import scope_manifest

logger = logging.getLogger("app.backups.manifest")

MANIFEST_NAME = "manifest.json"
CHECKSUMS_NAME = "SHA256SUMS"
DATABASE_DUMP_NAME = "database.dump"

#: 매니페스트 자체의 판. 읽는 쪽이 모르는 판을 만나면 그렇게 말할 수 있어야 한다.
MANIFEST_VERSION = 1


def code_alembic_head() -> str | None:
    """**코드가 아는** 스키마 판. 못 알아내면 `None` — 지어내지 않는다.

    복원본의 `alembic_version` 과 이 값이 다르면 그 백업은 지금 코드로 못 연다. 그
    사실을 복원 전에 알아야 하고, 그러려면 백업에 그 값이 적혀 있어야 한다.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = Path(__file__).resolve().parents[2]
        ini = root / "alembic.ini"
        if not ini.is_file():
            return None
        config = Config(str(ini))
        config.set_main_option("script_location", str(root / "alembic"))
        heads = ScriptDirectory.from_config(config).get_heads()
        return heads[0] if len(heads) == 1 else (",".join(sorted(heads)) or None)
    except Exception:
        # 매니페스트를 못 쓰는 것이 아니라 이 칸만 비운다. 「모른다」와 「틀린 값」은 다르다.
        logger.warning("alembic head 를 코드에서 읽지 못했습니다", exc_info=True)
        return None


def db_alembic_version(db) -> str | None:
    """**데이터베이스가 말하는** 스키마 판."""
    from sqlalchemy import text

    try:
        return db.execute(text("select version_num from alembic_version")).scalar_one_or_none()
    except Exception:
        logger.warning("alembic_version 을 읽지 못했습니다", exc_info=True)
        return None


def build(
    *,
    created_at: datetime,
    created_by: str | None,
    database: dict,
    alembic_head_code: str | None,
    alembic_head_db: str | None,
    destination: dict | None,
    files: dict | None,
    warnings: list[str],
) -> dict:
    """매니페스트 한 벌. 값은 전부 호출부가 **실측한** 것이다."""
    from app.core import product

    return {
        "manifest_version": MANIFEST_VERSION,
        # **slug 만 적는다.** 화면에 보이는 제품명은 설치마다 바뀔 수 있는 설정
        # (`ui_branding.product_name`)이라 「이 백업이 어느 제품 것인가」의 답이 못 된다.
        "product": {"slug": product.SLUG},
        "created_at": created_at.isoformat(),
        "created_by": created_by,
        "schema": {
            "alembic_head_code": alembic_head_code,
            "alembic_head_database": alembic_head_db,
            # 둘이 다르면 그 백업은 «지금 코드가 안 여는 판» 이다. 복원 전에 봐야 한다.
            "matches": bool(
                alembic_head_code and alembic_head_db and alembic_head_code == alembic_head_db
            ),
        },
        "database": database,
        "scope": scope_manifest(),
        #: 백업 저장소(Provider)에 사본이 갔는가. 안 갔으면 안 갔다고 적는다.
        "destination": destination,
        #: 업로드 원본·첨부를 백업 저장소로 옮긴 결과 (S8 `archive_to_backup`).
        "files": files,
        "warnings": list(warnings),
    }


def write(set_dir: Path, manifest: dict) -> dict:
    """`manifest.json` 과 `SHA256SUMS` 를 쓴다. 돌려주는 것은 체크섬 표다."""
    set_dir.mkdir(parents=True, exist_ok=True)
    path = set_dir / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    sums = checksum_table(set_dir)
    write_checksums(set_dir, sums)
    return sums


def checksum_table(set_dir: Path) -> dict[str, str]:
    """세트 안의 파일 전부(`SHA256SUMS` 자신은 뺀다)."""
    return {
        entry.name: sha256_file(entry)
        for entry in sorted(set_dir.iterdir())
        if entry.is_file() and entry.name != CHECKSUMS_NAME
    }


def write_checksums(set_dir: Path, sums: dict[str, str]) -> None:
    body = "".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items()))
    (set_dir / CHECKSUMS_NAME).write_text(body, encoding="utf-8", newline="\n")


def read_checksums(set_dir: Path) -> dict[str, str]:
    path = set_dir / CHECKSUMS_NAME
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if digest and name:
            out[name.strip()] = digest.strip()
    return out


def read(set_dir: Path) -> dict | None:
    path = set_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("매니페스트를 읽지 못했습니다: %s", path, exc_info=True)
        return None


def verify_set(set_dir: Path) -> dict:
    """세트가 **적힌 그대로인가**. 사람이 읽는 사유를 돌려준다.

    파일이 하나 더 생긴 것도 보고한다 — 백업 디렉터리에 예정에 없던 파일이 있다는 것은
    누가 손을 댔다는 뜻이고, 그 사실을 조용히 넘기면 무결성 검사가 아니다.
    """
    if not set_dir.is_dir():
        return {"ok": False, "reason": "set_missing", "detail": str(set_dir)}
    expected = read_checksums(set_dir)
    if not expected:
        return {"ok": False, "reason": "checksums_missing", "detail": CHECKSUMS_NAME}
    actual = checksum_table(set_dir)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(n for n in set(expected) & set(actual) if expected[n] != actual[n])
    if missing or extra or changed:
        return {
            "ok": False,
            "reason": "set_modified",
            "missing": missing,
            "extra": extra,
            "changed": changed,
        }
    return {"ok": True, "reason": None}
