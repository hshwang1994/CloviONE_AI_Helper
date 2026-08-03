"""복구 리허설 — 백업이 '복원되면 앱이 실제로 도는가'를 증명한다.

왜 필요한가: `app/backups/`는 이미 SQLite 온라인 Backup API + sha256 + integrity_check
까지 한다. 그런데 그건 전부 **백업 파일 자체**에 대한 검사다. 그 파일을 제자리에 돌려놨을 때
앱이 뜨는지는 아무도 확인한 적이 없다. 백업은 복원해 본 적이 없으면 백업이 아니다.

특히 이번 배포는 사용자 결정에 따라 **한 번에** 나간다(UI 전면 교체 + 마이그레이션 여러 개).
복원이 마지막 안전망인데, 그 안전망을 사고 당일에 처음 시험하게 둘 수는 없다.

`migration_rehearsal.sh`와의 차이:
  - 마이그레이션 리허설 = 스키마를 올렸다 내렸다 해도 같은가 (앞으로 갈 수 있나)
  - 복구 리허설       = 백업에서 되돌리면 앱이 도는가 (뒤로 갈 수 있나)

검사 순서 — 뒤로 갈수록 사용자가 보는 층에 가깝다:
  1. 앱 자신의 코드로 백업을 뜬다 (naive 파일 복사가 아니라 Backup API — 사양 §6.1)
  2. 앱 자신의 verify_backup (checksum + integrity_check)
  3. 복원: 백업을 별도 경로로 되돌린다
  4. 복원본의 integrity_check
  5. 테이블 집합과 행 수를 원본과 대조 (유실 탐지)
  6. alembic_version 이 **코드가 아는 head** 와 같은가
     — 백업이 옛 스키마인데 새 코드를 올리면 여기서 걸린다
  7. **복원본을 물고 앱을 실제로 띄워 읽기 경로를 호출한다** ← 이게 진짜 확인이다.
     1~6이 전부 통과해도 여기서 죽을 수 있다(ORM이 기대하는 컬럼이 없는 경우 등).

사용법:
  .venv/Scripts/python.exe scripts/restore_rehearsal.py                    # var/web.sqlite3
  .venv/Scripts/python.exe scripts/restore_rehearsal.py /path/prod.sqlite3
원본은 절대 건드리지 않는다 — 읽기만 한다.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

FAILURES: list[str] = []


def step(title: str) -> None:
    print(f"\n== {title} ==")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def bad(msg: str) -> None:
    print(f"  [FAIL] {msg}", file=sys.stderr)
    FAILURES.append(msg)


def table_snapshot(db: Path) -> dict[str, int]:
    """테이블별 행 수. 유실을 잡는 가장 싼 지표다."""
    conn = sqlite3.connect(str(db))
    try:
        names = [
            r[0]
            for r in conn.execute(
                "select name from sqlite_master where type='table' "
                "and name not like 'sqlite_%' order by name"
            )
        ]
        out = {}
        for t in names:
            try:
                out[t] = conn.execute(f'select count(*) from "{t}"').fetchone()[0]
            except sqlite3.Error:
                out[t] = -1
        return out
    finally:
        conn.close()


def code_head() -> str | None:
    """코드가 아는 alembic head. 백업이 옛 스키마면 여기서 갈린다."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        bad(f"alembic head가 {len(heads)}개다: {heads} — 다중 head는 배포에서 거부된다")
        return None
    return heads[0]


def boot_app_against(db: Path) -> None:
    """복원본을 물고 앱을 띄워 읽기 경로를 실제로 호출한다.

    여기까지 와야 '복원됐다'고 말할 수 있다. 스키마가 멀쩡해 보여도 ORM이 기대하는
    컬럼이 없으면 첫 쿼리에서 죽는데, 그건 파일 검사로는 절대 안 잡힌다.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    import app.models_registry  # noqa: F401  (모든 모델을 메타데이터에 등록)
    from app.core.config import Settings
    from app.core.models_base import Base
    from app.main import create_app

    # 변수 이름을 `app`으로 두면 안 된다 — 위의 `import app.models_registry`가
    # 지역 이름 `app`을 패키지로 덮어써서 `app.state`가 AttributeError로 죽는다.
    settings = Settings(database_url=f"sqlite:///{db.as_posix()}")
    web = create_app(settings=settings)
    with TestClient(web, raise_server_exceptions=False) as client:
        health = client.get("/healthz")
        if health.status_code != 200:
            bad(f"/healthz → {health.status_code} (복원본으로 앱이 뜨지 않는다)")
            return
        ok(f"/healthz → 200  {str(health.json())[:70]}")

        # 인증 벽 뒤의 읽기 경로: 200이 아니라 **401**이어야 정상이다.
        # 500이면 DB에 닿기 전에 죽은 것이고, 그게 우리가 찾는 신호다.
        probe = client.get("/api/tickets/mine")
        if probe.status_code == 500:
            bad(f"/api/tickets/mine → 500 (복원본에서 읽기 경로가 죽는다) {probe.text[:160]}")
        else:
            ok(f"/api/tickets/mine → {probe.status_code} (401=인증벽까지 정상 도달)")

        # ORM이 아는 모든 테이블을 실제로 한 번씩 조회한다. 컬럼 불일치는 여기서 난다.
        # 1~6단계가 전부 통과해도 이 단계에서 죽을 수 있다 — 파일 검사로는 못 잡는 층이다.
        engine = getattr(web.state, "engine", None)
        if engine is None:
            bad("앱이 engine을 state에 두지 않아 ORM 전수 조회를 못 했다")
            return
        broken = []
        with engine.connect() as conn:
            for table in Base.metadata.sorted_tables:
                try:
                    conn.execute(select(table).limit(1)).fetchall()
                except Exception as exc:  # noqa: BLE001 - 어떤 실패든 보고 대상이다
                    broken.append(f"{table.name}: {type(exc).__name__} {exc}"[:180])
        if broken:
            bad(f"ORM 테이블 {len(broken)}개가 복원본에서 조회 실패:")
            for b in broken:
                print(f"      - {b}", file=sys.stderr)
        else:
            ok(f"ORM 테이블 {len(Base.metadata.sorted_tables)}개 전부 조회 성공")


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "web.sqlite3"
    if not src.exists():
        print(f"[FAIL] 원본 DB가 없다: {src}", file=sys.stderr)
        return 1

    work = Path(tempfile.mkdtemp(prefix="restore-rehearsal-"))
    backup_path = work / "backup.sqlite3"
    restored = work / "restored.sqlite3"
    print(f"원본: {src}  (읽기만 한다)")
    print(f"작업: {work}")

    from app.backups.sqlite_backup import backup_database, verify_backup

    step("1) 앱 자신의 코드로 백업 (Backup API, 파일 복사 아님)")
    meta = backup_database(f"sqlite:///{src.as_posix()}", backup_path)
    ok(f"{meta['size_bytes']:,} bytes  sha256={meta['checksum'][:16]}…")

    step("2) 앱 자신의 verify_backup")
    v = verify_backup(backup_path, meta["checksum"])
    if v.get("ok"):
        ok(f"checksum + integrity_check 통과 {v}")
    else:
        bad(f"verify_backup 실패: {v}")

    step("3) 복원 (백업 → 새 위치)")
    shutil.copy2(backup_path, restored)
    ok(f"{restored.name} ({restored.stat().st_size:,} bytes)")

    step("4) 복원본 integrity_check")
    conn = sqlite3.connect(str(restored))
    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    ok(f"integrity_check: {integ}") if integ == "ok" else bad(f"integrity_check: {integ}")

    step("5) 테이블·행 수 대조 (원본 vs 복원본)")
    before, after = table_snapshot(src), table_snapshot(restored)
    lost = sorted(set(before) - set(after))
    gained = sorted(set(after) - set(before))
    diffs = [
        f"{t}: {before[t]} → {after[t]}"
        for t in sorted(set(before) & set(after))
        if before[t] != after[t]
    ]
    if lost:
        bad(f"복원본에서 사라진 테이블: {lost}")
    if gained:
        bad(f"복원본에만 있는 테이블: {gained}")
    if diffs:
        # WAL이 활성인 원본을 읽는 중이라 미세한 차이는 있을 수 있다. 그래도 보고는 한다.
        bad(f"행 수가 다른 테이블 {len(diffs)}개: {diffs[:5]}")
    if not (lost or gained or diffs):
        ok(f"테이블 {len(after)}개, 행 수 전부 일치 (총 {sum(after.values()):,}행)")

    step("6) alembic_version 이 코드 head 와 같은가")
    head = code_head()
    conn = sqlite3.connect(str(restored))
    try:
        row = conn.execute("select version_num from alembic_version").fetchone()
    except sqlite3.Error as exc:
        row = None
        bad(f"alembic_version 조회 실패: {exc}")
    finally:
        conn.close()
    if head and row:
        if row[0] == head:
            ok(f"백업 스키마 {row[0]} == 코드 head {head}")
        else:
            bad(
                f"백업 스키마 {row[0]} != 코드 head {head} — "
                "이 백업으로 복원하면 새 코드가 없는 컬럼을 찾는다. "
                "복원 후 alembic upgrade head 를 반드시 돌려야 한다."
            )

    step("7) 복원본을 물고 앱을 실제로 띄운다")
    try:
        boot_app_against(restored)
    except Exception as exc:  # noqa: BLE001 - 부팅 실패 자체가 결과다
        bad(f"앱 부팅 중 예외: {type(exc).__name__}: {exc}")

    print("")
    if FAILURES:
        print(f"RESTORE_REHEARSAL_FAILED ({len(FAILURES)}건)", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"RESTORE_REHEARSAL_OK  (작업 디렉터리: {work} — 확인 후 지워도 된다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
