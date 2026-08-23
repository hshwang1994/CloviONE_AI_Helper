"""PostgreSQL 백업 — `pg_dump -Fc` + 체크섬 + **진짜 복원 검증** (§6.1 · §12 · D-204).

SQLite 시절에는 `sqlite3.Connection.backup()` 하나면 됐다. 파일 하나가 DB 였기 때문이다.
PG 에서는 파일 복사가 아예 성립하지 않는다 — 데이터 디렉터리를 통째로 복사하려면 서버를
멈추거나 WAL 을 함께 다뤄야 하고, 둘 다 우리가 원하는 것이 아니다.

`pg_dump -Fc`(custom format)를 쓴다:
  * **온라인**이다. 서비스를 멈추지 않고 일관된 스냅숏을 뜬다.
  * **압축**된다.
  * `pg_restore` 가 **부분 복원**을 할 수 있다(표 하나만 되돌리기). plain SQL 덤프로는 못 한다.
  * `pg_restore --list` 로 **풀지 않고 목차를 읽을 수 있다** — 검증이 싸진다.

## 파일이 생겼다고 성공이 아니다 (D-204)

`pg_dump` 가 0 을 돌려주고 파일이 생겨도 그 파일이 복원 가능한지는 다른 질문이다. 그래서
세 걸음으로 본다:

  1. **체크섬** — 파일이 그 뒤에 바뀌지 않았는가.
  2. `pg_restore --list` — 아카이브 목차를 읽을 수 있는가(구조가 깨지지 않았는가).
  3. **임시 DB 로 실제 복원** — 정말 복원되는가. 여기까지 해야 «검증됨» 이다.

3번을 못 하는 환경(DB 생성 권한이 없는 역할)에서는 그 사실을 `reason` 에 적어 돌려준다 —
**조용히 2번까지만 하고 «검증됨» 이라고 말하지 않는다.** 그게 이 파일이 막으려는 실패다.

**복원 후 앱 기동 검증**은 여기 없다. 여기는 그 아래 계층인 «덤프 하나를 믿을 수 있는가» 다.
그 위층은 S12 가 세웠다 — 운영 정책·보존·매니페스트는 `app/backups/{policy,manifest}.py`,
「복원본을 물고 앱이 실제로 도는가」는 `scripts/restore_rehearsal.py` 7단계다(D-204·D-273).

## 왜 `pg_bin_dir` 가 필요한가

Ubuntu 는 버전별 디렉터리에 바이너리를 둔다(`/usr/lib/postgresql/16/bin`). `PATH` 의
`pg_dump` 는 다른(대개 더 낮은) 버전일 수 있고, **`pg_dump` 가 서버보다 낮으면 실행을
거부한다.** 실측: 이 제품의 테스트 서버에는 `pg_dump` 가 아예 `PATH` 에 없다.
그래서 경로를 설정으로 받는다.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

# 덤프 파일 확장자. custom format 이라 `.sql` 이 아니다 — 텍스트가 아니고, 그 사실을
# 파일 이름이 말해 줘야 운영자가 `cat` 으로 열어 보지 않는다.
BACKUP_SUFFIX = ".dump"

# 외부 명령 상한(초). 걸리면 죽인다 — 백업 하나가 영원히 도는 것보다 실패가 낫다.
DUMP_TIMEOUT_SECONDS = 3600
RESTORE_TIMEOUT_SECONDS = 3600
LIST_TIMEOUT_SECONDS = 120


class PgToolMissing(RuntimeError):
    """`pg_dump`/`pg_restore` 를 못 찾았다. 설치가 덜 됐거나 `pg_bin_dir` 가 틀렸다."""


def resolve_tool(name: str, bin_dir: str | None = None) -> str:
    """`pg_dump` 같은 도구의 실행 경로.

    `bin_dir` 를 주면 거기만 본다 — `PATH` 로 조용히 내려가지 않는다. 내려가면 **서버보다
    낮은 버전**을 집어 들 수 있고, 그때 나오는 오류("server version mismatch")는 백업이
    한 번도 성공한 적 없다는 뜻인데 증상은 그 시점에야 보인다.
    """
    if bin_dir:
        candidate = Path(bin_dir) / name
        for path in (candidate, candidate.with_suffix(".exe")):
            if path.exists():
                return str(path)
        raise PgToolMissing(f"{name} 을(를) {bin_dir} 에서 찾지 못했습니다.")
    found = shutil.which(name)
    if not found:
        raise PgToolMissing(
            f"{name} 을(를) 찾지 못했습니다. PostgreSQL 클라이언트 도구를 설치하거나 "
            "pg_bin_dir 설정에 경로를 지정해 주세요."
        )
    return found


def libpq_env(database_url: str) -> tuple[dict[str, str], str]:
    """`database_url` 을 libpq 환경변수와 DB 이름으로 나눈다.

    **비밀번호는 인자가 아니라 환경변수로 넘긴다.** 명령행에 넣으면 같은 호스트의 다른
    사용자가 `ps` 로 읽을 수 있고, 무엇보다 실패 로그에 명령행이 통째로 찍히는 순간
    비밀번호가 로그에 남는다(§6.3: Secret 을 로그·명령행에 평문 노출하지 않는다).
    """
    parsed = urlparse(database_url)
    env = dict(os.environ)
    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    dbname = (parsed.path or "").lstrip("/")
    if dbname:
        env["PGDATABASE"] = dbname
    return env, dbname


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(argv: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    """외부 도구 한 번. **인코딩을 명시한다** — 안 적으면 로케일(한국어 Windows 는 cp949)로
    디코드하다 실패 메시지를 읽지 못하고, 정작 왜 실패했는지를 못 본다."""
    return subprocess.run(
        argv,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def backup_database(
    database_url: str,
    dest_path: Path,
    *,
    bin_dir: str | None = None,
    exclude_table_data: tuple[str, ...] | list[str] = (),
) -> dict:
    """`pg_dump -Fc` 로 일관된 온라인 덤프를 만든다.

    `exclude_table_data` 는 **행만** 뺀다(표는 그대로 선다). 무엇을 왜 빼는지는
    `app/backups/policy.py` 가 정하고, 여기서는 그 목록을 받기만 한다 — 정책이 두 곳에
    있으면 매니페스트가 말하는 범위와 실제로 뺀 것이 어긋나는 날이 온다.
    """
    dump = resolve_tool("pg_dump", bin_dir)
    env, dbname = libpq_env(database_url)
    if not dbname:
        raise ValueError("database_url 에 데이터베이스 이름이 없습니다.")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    argv = [
        dump,
        "--format=custom",
        # 소유자·권한은 복원하는 쪽 역할을 따른다. 안 그러면 원본과 같은 역할이 없는
        # 서버(재해 복구 대상)에서 복원이 통째로 실패한다.
        "--no-owner",
        "--no-privileges",
    ]
    for table in exclude_table_data:
        argv.append(f"--exclude-table-data={table}")
    argv += ["--file", str(dest_path), "--dbname", dbname]

    result = _run(argv, env, DUMP_TIMEOUT_SECONDS)
    if result.returncode != 0:
        # 실패했는데 파일이 남으면 다음 검증이 그 조각을 «백업» 으로 본다.
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump 실패(rc={result.returncode}): {result.stderr.strip()[:500]}")

    return {
        "path": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "checksum": sha256_file(dest_path),
    }


def verify_backup(
    backup_path: Path, expected_checksum: str | None = None, *, bin_dir: str | None = None
) -> dict:
    """파일이 그대로인가 + 아카이브 목차를 읽을 수 있는가.

    `PRAGMA integrity_check` 자리다. `pg_restore --list` 는 아카이브를 **풀지 않고** 목차만
    읽으므로 싸고, 헤더나 TOC 가 깨졌으면 여기서 걸린다.
    """
    if not backup_path.exists():
        return {"ok": False, "reason": "file_missing"}
    if expected_checksum is not None and sha256_file(backup_path) != expected_checksum:
        return {"ok": False, "reason": "checksum_mismatch"}
    try:
        restore = resolve_tool("pg_restore", bin_dir)
    except PgToolMissing as exc:
        return {"ok": False, "reason": f"tool_missing: {exc}"}
    result = _run([restore, "--list", str(backup_path)], dict(os.environ), LIST_TIMEOUT_SECONDS)
    if result.returncode != 0:
        return {"ok": False, "reason": f"archive_unreadable: {result.stderr.strip()[:200]}"}
    if not result.stdout.strip():
        # 목차가 비었다 = 아무것도 안 담긴 덤프다. 파일은 멀쩡한데 내용이 없는 경우라,
        # 이걸 통과시키면 «백업이 있다» 고 믿으면서 아무것도 못 되돌린다.
        return {"ok": False, "reason": "archive_empty"}
    return {"ok": True, "reason": None}


def admin_env_for(database_url: str) -> dict[str, str]:
    """`postgres` 에 붙는 관리 연결 환경.

    복원 대상 DB 를 만들거나 지우려면 **그 DB 밖에** 있어야 한다. 자기 자신에 붙어서는
    자기를 지울 수 없다.
    """
    env, _ = libpq_env(database_url)
    env = dict(env)
    env["PGDATABASE"] = "postgres"
    return env


def sibling_url(database_url: str, dbname: str) -> str:
    """같은 서버의 다른 데이터베이스를 가리키는 URL.

    복구 리허설이 복원본을 **앱에 물릴** 때 쓴다. 자격증명 부분(`netloc`)을 **손대지 않고
    그대로 옮긴다** — 다시 조립하면 비밀번호에 든 `@`·`/` 의 퍼센트 인코딩이 풀려 인증이
    조용히 실패한다.

    `urlunparse` 를 안 쓰는 이유: `netloc` 이 비면(`postgresql:///db` — 유닉스 소켓 +
    peer 인증인 운영 모양이다) `//` 를 떨어뜨려 `postgresql:/db` 를 만든다. 그 문자열은
    스킴이 통째로 달라 보이고, `normalize_database_url` 이 「PostgreSQL 주소가 아니다」로
    거절한다. 실 서버 리허설에서 실제로 여기서 멈췄다.

    질의 문자열은 함께 옮긴다 — `?host=/run/postgresql` 처럼 **어디에 붙는지**가 거기
    적혀 있을 수 있다.
    """
    parsed = urlparse(database_url)
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}/{dbname}{query}"


def create_database(database_url: str, dbname: str, *, bin_dir: str | None = None) -> None:
    """빈 데이터베이스 하나. 실패하면 `RuntimeError`."""
    psql = resolve_tool("psql", bin_dir)
    result = _run(
        [psql, "-v", "ON_ERROR_STOP=1", "-c", f'CREATE DATABASE "{dbname}"'],
        admin_env_for(database_url),
        LIST_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CREATE DATABASE 실패: {result.stderr.strip()[:300]}")


def drop_database(database_url: str, dbname: str, *, bin_dir: str | None = None) -> None:
    """지운다. 없으면 아무 일도 안 한다 — 치우는 코드가 죽으면 쓰레기가 남는다."""
    try:
        psql = resolve_tool("psql", bin_dir)
    except PgToolMissing:
        return
    _run(
        [psql, "-c", f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'],
        admin_env_for(database_url),
        LIST_TIMEOUT_SECONDS,
    )


def restore_into(
    backup_path: Path, dbname: str, *, database_url: str, bin_dir: str | None = None
) -> dict:
    """아카이브를 **이미 있는** 데이터베이스에 푼다.

    PG 에는 「파일을 제자리에 되돌린다」가 없다. 되돌린다는 것은 언제나 **어떤 데이터베이스에
    푼다**는 뜻이고, 그래서 대상 이름을 받는다. 살아 있는 DB 를 대상으로 부르지 않는 것은
    호출부의 책임이다 — 이 함수는 시키는 대로 푼다.
    """
    restore = resolve_tool("pg_restore", bin_dir)
    env = admin_env_for(database_url)
    result = _run(
        [restore, "--dbname", dbname, "--no-owner", "--no-privileges", str(backup_path)],
        env,
        RESTORE_TIMEOUT_SECONDS,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stderr": result.stderr.strip()[:2000],
    }


def restore_test(
    backup_path: Path, *, database_url: str | None = None, bin_dir: str | None = None
) -> dict:
    """**임시 DB 에 실제로 복원해 본다.** 살아 있는 데이터는 건드리지 않는다 (§6.3).

    `database_url` 이 없으면 어디에 복원할지 알 수 없으므로 구조 검증(`verify_backup`)까지만
    하고 **그 사실을 `reason` 에 적어** 돌려준다. 조용히 통과시키지 않는다 — 그러면
    "검증됨" 이 두 가지 다른 뜻을 갖게 되고, 정작 복원이 안 되는 백업이 초록으로 보인다.
    """
    structural = verify_backup(backup_path, bin_dir=bin_dir)
    if not structural["ok"]:
        return structural
    if not database_url:
        return {"ok": True, "reason": "structure_only: 복원 대상 서버를 몰라 구조만 확인했습니다."}

    try:
        resolve_tool("pg_restore", bin_dir)
    except PgToolMissing as exc:
        return {"ok": False, "reason": f"tool_missing: {exc}"}

    temp_db = f"clovir_restore_test_{uuid.uuid4().hex[:12]}"

    try:
        resolve_tool("psql", bin_dir)
    except PgToolMissing as exc:
        return {"ok": False, "reason": f"tool_missing: {exc}"}

    try:
        create_database(database_url, temp_db, bin_dir=bin_dir)
    except RuntimeError as exc:
        # 권한이 없어 임시 DB 를 못 만드는 환경이 있다. 구조 검증은 통과했으므로 거짓말은
        # 아니지만, **어디까지 봤는지**를 반드시 함께 말한다.
        return {"ok": True, "reason": f"structure_only: 임시 DB 를 만들지 못했습니다({exc})."}
    try:
        restored = restore_into(
            backup_path, temp_db, database_url=database_url, bin_dir=bin_dir
        )
        if not restored["ok"]:
            return {"ok": False, "reason": f"restore_failed: {restored['stderr'][:200]}"}
        return {"ok": True, "reason": None}
    finally:
        drop_database(database_url, temp_db, bin_dir=bin_dir)
