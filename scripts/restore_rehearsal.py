"""복구 리허설 — 백업이 «복원되면 앱이 실제로 도는가» 를 증명한다 (S12 · P-23a · D-204).

## 왜 이 스크립트가 있는가

`app/backups/` 는 백업 **파일 자체**를 검사한다(`pg_dump -Fc` + sha256 + `pg_restore --list`
+ 임시 DB 실복원). 그것으로도 답하지 못하는 질문이 하나 남는다: **그 복원본을 물고 앱이
실제로 뜨고 읽기 경로가 도는가.** 백업은 복원해 본 적이 없으면 백업이 아니다.

1~6 단계가 전부 통과해도 7단계에서 죽을 수 있다 — ORM 이 기대하는 컬럼이 없거나, 부팅
경로가 읽는 부트스트랩 행이 덤프에서 빠졌거나, 파생 표를 비운 것이 어딘가를 깨뜨린 경우다.
그 사실은 **사고 당일이 아니라 오늘** 알아야 한다.

## 여덟 단계

  1. **백업** — 앱 자신의 코드로 뜬다(`app/backups/service.py::run_backup`). 손으로 부른
     `pg_dump` 가 아니다 — 검증 대상은 「PostgreSQL 이 덤프를 뜰 수 있는가」가 아니라
     **「이 제품의 백업 기능이 되돌릴 수 있는 것을 만드는가」** 다.
  2. **앱 자신의 검증** — 그 행의 상태가 `verified` 인가. 체크섬 + `pg_restore --list`
     + 임시 DB 실복원을 이미 통과했다는 뜻이다. `succeeded`(구조만 확인)는 **통과가
     아니다** — D-204 가 막으려는 그 초록이다.
  3. **복원** — **새 데이터베이스**로 되돌린다. PG 에는 「파일을 제자리에」가 없다.
  4. **복원본의 무결성** — `integrity_check` 대신 **스키마의 성질**이 살아 왔는지 본다:
     부분 유니크의 `WHERE` · `gin_trgm_ops` GIN · `jsonb` 가 `jsonb` 인 채로 · identity.
     S2 가 실 PG 에서 이 넷을 짚었고(`EVIDENCE/S2/pg_backup_roundtrip.txt`), 여기서는
     **원본과 개수를 대조**한다.
  5. **표 집합과 행 수** — 원본과 대조한다. 정책이 행을 뺀 표(`policy.excluded_tables`)는
     **0 이어야 하고**, 나머지는 **같아야 한다**. 이 두 방향을 함께 보는 것이 핵심이다 —
     한쪽만 보면 「정책이 안 걸렸다」와 「데이터를 잃었다」를 구별하지 못한다.
  6. **`alembic_version`** — 복원본의 판이 **코드가 아는 head** 와 같은가. 백업이 옛
     스키마인데 새 코드를 올리면 여기서 걸린다.
  7. **복원본으로 앱을 실제로 띄워 읽기 경로를 호출한다** ← 이것이 진짜 확인이다.
     `create_app()` 을 복원본 주소로 만들고 `TestClient` 로 실제 HTTP 를 태운다.
  8. **첨부 파일** (BKP-02) — DB 가 참조하는 바이트가 디스크에 있는가. 아래
     `check_attachment_files()` 는 S2 때부터 PG 위에서 돌던 조각이고 시험도 그대로다.
     S8 의 `files`/`storage_providers` 축은 `app/storage/service.py::verify_files` 가 본다.

## 7단계는 왜 비밀번호를 바꾸는가

읽기 경로 대부분이 로그인을 요구한다. 복원본은 **버리는 사본**이므로 그 안의 관리자
계정 하나에 임시 비밀번호를 심고 진짜 `/login` 을 지난다 — 세션을 손으로 만들어 넣으면
인증 경로 자체가 검증에서 빠지고, 그러면 「앱이 뜬다」만 확인하고 「앱을 쓸 수 있다」는
확인하지 못한다. **운영 DB 는 건드리지 않는다**(1·2단계만 원본에 붙고 그것도 백업 행
하나를 더할 뿐이다).

## 끝나면 치운다

복원본 데이터베이스는 기본으로 지운다. `--keep` 을 주면 남긴다 — 실패를 손으로 파고들
때 필요하다. 남긴 이름은 마지막 줄에 적는다.

`--record` 는 결과 한 줄을 `restore_rehearsals` 표에 남겨 관리 콘솔의 복구 리허설 화면이
「마지막으로 복원을 시험한 게 언제인가」를 보여 주게 한다. 기록에 실패해도 리허설 결과
자체는 바뀌지 않는다 — 증거를 남기지 못한 것이 증거를 뒤집지는 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


def _utcnow() -> datetime:
    """UTC 저장 계약(CLAUDE.md §6 7번). `datetime.utcnow()` 는 deprecated 다."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── 첨부 파일 확인 (BKP-02) ──────────────────────────────────────────────────
#
# 저장소 종류를 타지 않는다. DB 가 참조하는 바이트가 디스크에 실제로 있는지 보는 일이라,
# 저장소가 무엇이든 같은 질문이다. S2 가 PG 로 옮겨 살려 뒀고 시험도 함께 있다
# (`tests/regression/test_restore_rehearsal_attachments.py`).
#
# 왜 필요한가: 게시판·팀챗·티켓 첨부·프로필 사진은 별도 파일
# (`data_dir/uploads/<네임스페이스>/<owner_id>/<저장명>`)이라 **DB 만 복원하면 그 행들이
# 가리키는 실제 바이트가 없을 수 있다.** 네 자원이 각자 다른 (표, 네임스페이스, owner_id
# 칸, 저장명 칸) 모양이라 하나로 묶지 못한다.
ATTACHMENT_CHECKS = (
    # (표, 네임스페이스, owner_id 칸, 저장명 칸)
    ("board_attachments", "board", "post_id", "stored_name"),
    ("chat_message_images", "team_chat", "room_id", "stored_name"),
    ("ticket_attachments", "ticket", "ticket_uid", "stored_name"),
    ("user_preferences", "avatar", "user_id", "avatar_stored_name"),
)


def check_attachment_files(conn, uploads_root: Path) -> list[str]:
    """복원된 DB 가 참조하는 첨부 파일이 실제로 `uploads_root` 아래에 있는지 확인한다.

    반환값은 「무엇이 없다」를 사람이 읽을 수 있게 적은 문자열 목록이고, 빈 목록이면 전부
    있다는 뜻이다. 표 자체가 없거나(구버전 스키마) 조회가 실패하면 **그것도 보고 대상**이다 —
    조용히 건너뛰면 「확인했는데 문제없음」과 「애초에 확인을 못 함」이 구별되지 않는다.

    조회 하나를 savepoint 로 감싸는 이유: PG 는 문장 하나가 실패하면 **트랜잭션 전체가
    중단 상태**가 되어 다음 조회부터 `25P02` 로 줄줄이 실패한다. 그러면 표 하나가 없을 뿐인데
    나머지 셋도 「조회 실패」로 보고돼 진짜 원인이 묻힌다. SQLite 에는 없던 함정이다.
    """
    missing: list[str] = []
    for table, namespace, owner_col, stored_col in ATTACHMENT_CHECKS:
        try:
            with conn.begin_nested():
                rows = conn.execute(
                    text(
                        f'select "{owner_col}", "{stored_col}" from "{table}" '
                        f'where "{stored_col}" is not null'
                    )
                ).fetchall()
        except SQLAlchemyError as exc:
            orig = getattr(exc, "orig", exc)
            reason = str(orig).strip().splitlines()[0] if str(orig).strip() else type(exc).__name__
            missing.append(f"{table}: 조회 실패({reason}) — 스키마 불일치일 수 있다")
            continue
        for owner_id, stored_name in rows:
            path = uploads_root / namespace / str(owner_id) / str(stored_name)
            if not path.is_file():
                missing.append(
                    f"{table} owner={owner_id} stored_name={stored_name}: 파일 없음 ({path})"
                )
    return missing


# ── 리허설 ───────────────────────────────────────────────────────────────────


@dataclass
class Rehearsal:
    """단계별 결과를 모은다. **실패해도 계속 가는 단계와 못 가는 단계가 다르다.**

    3단계(복원)가 실패하면 4~8 은 물어볼 대상 자체가 없으므로 멈춘다. 4~8 사이의 실패는
    서로 독립이라 전부 돌린다 — 한 번에 여러 문제를 보는 편이 한 번에 하나씩 고치며
    여덟 번 돌리는 것보다 낫다.
    """

    failures: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    started_at: datetime = field(default_factory=_utcnow)

    def fail(self, stage: str, detail: str) -> None:
        line = f"{stage}: {detail}"
        self.failures.append(line)
        print(f"  FAIL {line}", flush=True)

    def note(self, message: str) -> None:
        print(f"  {message}", flush=True)

    @property
    def ok(self) -> bool:
        return not self.failures


# 복원본의 **스키마 성질**을 세는 질의. S2 가 실 PG 에서 짚은 넷이 그대로 이 자리다.
SHAPE_QUERIES = {
    "partial_unique_indexes": (
        "select count(*) from pg_index i join pg_class c on c.oid = i.indexrelid "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and i.indisunique and i.indpred is not null"
    ),
    "trgm_gin_indexes": (
        "select count(*) from pg_index i join pg_class c on c.oid = i.indexrelid "
        "join pg_namespace n on n.oid = c.relnamespace "
        "join pg_opclass o on o.oid = any(i.indclass::oid[]) "
        "where n.nspname = 'public' and o.opcname = 'gin_trgm_ops'"
    ),
    "jsonb_columns": (
        "select count(*) from information_schema.columns "
        "where table_schema = 'public' and data_type = 'jsonb'"
    ),
    "identity_columns": (
        "select count(*) from information_schema.columns "
        "where table_schema = 'public' and is_identity = 'YES'"
    ),
    "foreign_keys": (
        "select count(*) from pg_constraint c join pg_namespace n on n.oid = c.connamespace "
        "where n.nspname = 'public' and c.contype = 'f'"
    ),
    "check_constraints": (
        "select count(*) from pg_constraint c join pg_namespace n on n.oid = c.connamespace "
        "where n.nspname = 'public' and c.contype = 'c'"
    ),
}


def _table_names(conn) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' and table_type = 'BASE TABLE' "
                "order by table_name"
            )
        )
    ]


def _row_counts(conn, tables: list[str]) -> dict[str, int]:
    """표마다 세어 온다.

    한 문장으로 묶으면(`union all`) 표가 94개일 때 SQL 이 길어지기만 하고 빨라지지
    않는다 — 어차피 각 표를 훑는다. 대신 표 하나가 실패해도 나머지를 계속 센다.
    """
    counts: dict[str, int] = {}
    for name in tables:
        try:
            with conn.begin_nested():
                counts[name] = int(
                    conn.execute(text(f'select count(*) from "{name}"')).scalar_one()
                )
        except SQLAlchemyError:
            counts[name] = -1
    return counts


def _shape(conn) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, sql in SHAPE_QUERIES.items():
        out[key] = int(conn.execute(text(sql)).scalar_one())
    return out


def _partial_unique_predicates(conn) -> set[str]:
    """부분 유니크 인덱스의 `WHERE` 절 원문 집합.

    개수만 세면 「인덱스는 왔는데 `WHERE` 가 빠졌다」를 못 잡는다 — 그것이 D-189 가
    경고한 실패 모양이고, 그때 그 인덱스는 **전체 유니크**가 되어 정상 재요청을 막는다.
    """
    return {
        row[0]
        for row in conn.execute(
            text(
                "select pg_get_expr(i.indpred, i.indrelid) from pg_index i "
                "join pg_class c on c.oid = i.indexrelid "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and i.indisunique and i.indpred is not null"
            )
        )
    }


READ_PATHS = (
    # 인증 없이도 도는 것부터. 여기서 죽으면 앱이 아예 못 떴다는 뜻이다.
    ("GET", "/healthz", False),
    ("GET", "/readyz", False),
    # 로그인 뒤 — 도메인마다 하나씩. ORM 이 실제로 그 표를 읽는 경로다.
    ("GET", "/api/me", True),
    ("GET", "/api/tickets/mine", True),
    ("GET", "/api/tickets/meta", True),
    ("GET", "/api/projects", True),
    ("GET", "/api/knowledge/documents?limit=5", True),
    ("GET", "/api/notifications?limit=5", True),
    ("GET", "/api/admin/users?limit=5", True),
    ("GET", "/api/admin/audit?limit=5", True),
    ("GET", "/api/admin/backups", True),
    ("GET", "/api/storage/providers", True),
    ("GET", "/api/search?q=test", True),
)

REHEARSAL_PASSWORD = "Rehearsal!Temp#2026"

# 세션 쿠키는 `Secure` 다(`cookie_secure` 기본값 True). `http://` 로 부르면 브라우저도
# httpx 도 그 쿠키를 **되돌려 보내지 않고**, 그러면 로그인은 200 인데 뒤따르는 요청이
# 전부 401 이 된다. 제품의 쿠키 정책을 시험 때문에 낮추지 않고, **말을 맞춘다**.
BASE_URL = "https://testserver"


def _boot_and_read(restored_url: str, rehearsal: Rehearsal) -> None:
    """7단계 — 복원본으로 앱을 띄우고 실제 HTTP 읽기를 태운다."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(database_url=restored_url)
    app = create_app(settings)
    with TestClient(app, base_url=BASE_URL) as client:
        email = _prepare_login(app, rehearsal)
        authenticated = False
        if email is not None:
            response = client.post(
                "/login", json={"email": email, "password": REHEARSAL_PASSWORD}
            )
            if response.status_code == 200:
                authenticated = True
                rehearsal.note(f"로그인 성공: {email}")
            else:
                rehearsal.fail(
                    "7-앱기동", f"복원본에서 로그인 실패 ({response.status_code})"
                )

        called = ok_count = 0
        for method, path, needs_auth in READ_PATHS:
            if needs_auth and not authenticated:
                continue
            try:
                response = client.request(method, path)
            except Exception as exc:  # noqa: BLE001 - 어떤 예외든 «앱이 못 돈다» 다
                rehearsal.fail("7-앱기동", f"{method} {path} 가 터졌다: {exc!r}")
                continue
            called += 1
            # 🔴 **5xx 만 잡으면 안 된다.** 첫 회차에서 세션 쿠키가 안 실려 인증 경로가
            # 전부 401 을 냈는데, 그 회차가 초록으로 끝났다 — 「앱이 떴다」만 보고 「앱을
            # 쓸 수 있다」는 아무것도 확인하지 못한 상태다. 이 단계에서 부르는 경로는
            # 전부 **200 이 나와야 정상**이고, 그 밖의 답은 이유가 무엇이든 실패다.
            if response.status_code != 200:
                rehearsal.fail(
                    "7-앱기동",
                    f"{method} {path} → {response.status_code} {response.text[:200]}",
                )
            else:
                ok_count += 1
        rehearsal.summary["read_paths_called"] = called
        rehearsal.summary["read_paths_ok"] = ok_count
        rehearsal.summary["authenticated"] = authenticated
        # **호출한 경로가 하나뿐이면 그것은 통과가 아니다.** 로그인이 안 되면 인증 경로가
        # 통째로 빠지는데, 그 상태로 초록을 찍으면 이 단계가 아무것도 증명하지 않는다.
        if not authenticated:
            rehearsal.fail(
                "7-앱기동",
                "로그인이 안 돼 인증 읽기 경로를 하나도 호출하지 못했다 "
                f"(호출한 경로 {called}건 — 전부 인증 없이 도는 것뿐이다)",
            )


def _prepare_login(app, rehearsal: Rehearsal) -> str | None:
    """복원본 안의 관리자 하나에 임시 비밀번호를 심는다. **버리는 사본에만 한다.**

    없으면 만든다 — 복원본에 관리자가 없는 설치(첫 백업 직후 등)에서도 7단계가 돌아야
    한다. 만든 사용자는 복원본과 함께 사라진다.
    """
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.users.models import User

    with app.state.session_factory() as db:
        row = db.execute(
            select(User)
            .where(User.role == "system_admin", User.active.is_(True))
            .order_by(User.created_at)
            .limit(1)
        ).scalars().first()
        if row is None:
            rehearsal.note("복원본에 활성 system_admin 이 없어 임시 계정을 만든다")
            try:
                from app.users.service import create_user

                row = create_user(
                    db,
                    email="restore-rehearsal@example.invalid",
                    display_name="복구 리허설",
                    password=REHEARSAL_PASSWORD,
                    settings=app.state.settings,
                    actor_role="system_admin",
                    role="system_admin",
                    active=True,
                )
            except Exception as exc:  # noqa: BLE001
                rehearsal.fail("7-앱기동", f"임시 관리자 생성 실패: {exc!r}")
                return None
        row.password_hash = hash_password(REHEARSAL_PASSWORD)
        row.must_change_password = False
        row.failed_login_count = 0
        row.locked_until = None
        # 조직 게이트(fail-closed)에 걸려 목록이 전부 비면 읽기 경로가 아무것도 안 읽는다.
        row.membership_kind = "organization"
        email = row.email
        db.commit()
    return email


def run(*, label: str | None, keep: bool) -> Rehearsal:
    from app.backups import manifest as manifest_mod
    from app.backups import pg_backup, policy
    from app.backups import service as backup_service
    from app.backups.models import STATUS_VERIFIED
    from app.core.config import Settings
    from app.core.db import make_engine, make_session_factory

    rehearsal = Rehearsal()
    settings = Settings()
    bin_dir = getattr(settings, "pg_bin_dir", "") or None
    source_url = settings.database_url
    engine = make_engine(source_url)
    session_factory = make_session_factory(engine)

    # ── 1·2 — 앱 자신의 코드로 백업하고, 앱 자신의 판정을 읽는다 ──────────────
    print("[1/8] 백업 — 앱 자신의 코드로", flush=True)
    now = _utcnow()
    with session_factory() as db:
        row = backup_service.run_backup(db, settings, created_by=None, now=now)
        db.commit()
        set_dir = Path(row.path)
        status = row.status
        error_message = row.error_message
        checksum = row.checksum
    rehearsal.summary["backup_path"] = str(set_dir)
    rehearsal.summary["backup_sha256"] = checksum
    rehearsal.note(f"세트: {set_dir}")

    print("[2/8] 검증 — 앱이 스스로 «되돌릴 수 있다» 고 말하는가", flush=True)
    if status != STATUS_VERIFIED:
        # `succeeded`(구조만 확인)를 통과로 읽지 않는다. D-204 가 막으려는 초록이다.
        rehearsal.fail("2-검증", f"상태가 {status} 다 ({error_message or '사유 없음'})")
        return rehearsal
    set_check = manifest_mod.verify_set(set_dir)
    if not set_check["ok"]:
        rehearsal.fail("2-검증", f"세트가 적힌 그대로가 아니다: {set_check}")
        return rehearsal
    stored = manifest_mod.read(set_dir) or {}
    rehearsal.summary["manifest_version"] = stored.get("manifest_version")
    rehearsal.summary["alembic_head"] = (stored.get("schema") or {}).get(
        "alembic_head_database"
    )

    # ── 3 — 새 데이터베이스로 복원 ──────────────────────────────────────────
    restored_db = f"clovir_rehearsal_{uuid.uuid4().hex[:10]}"
    restored_url = pg_backup.sibling_url(source_url, restored_db)
    rehearsal.summary["restored_database"] = restored_db
    print(f"[3/8] 복원 — 새 데이터베이스 {restored_db}", flush=True)
    try:
        pg_backup.create_database(source_url, restored_db, bin_dir=bin_dir)
    except Exception as exc:  # noqa: BLE001
        rehearsal.fail("3-복원", f"데이터베이스를 만들지 못했다: {exc}")
        return rehearsal

    try:
        result = pg_backup.restore_into(
            backup_service.dump_path(set_dir),
            restored_db,
            database_url=source_url,
            bin_dir=bin_dir,
        )
        if not result["ok"]:
            rehearsal.fail("3-복원", f"pg_restore rc={result['returncode']}: {result['stderr'][:400]}")
            return rehearsal

        restored_engine = make_engine(restored_url)
        with engine.connect() as src, restored_engine.connect() as dst:
            # ── 4 — 스키마의 성질이 살아 왔는가 ─────────────────────────────
            print("[4/8] 무결성 — 제약·인덱스가 실제로 다시 섰는가", flush=True)
            src_shape, dst_shape = _shape(src), _shape(dst)
            rehearsal.summary["shape"] = dst_shape
            for key in SHAPE_QUERIES:
                if src_shape[key] != dst_shape[key]:
                    rehearsal.fail(
                        "4-무결성", f"{key} 가 원본 {src_shape[key]} 대 복원본 {dst_shape[key]}"
                    )
            src_pred, dst_pred = _partial_unique_predicates(src), _partial_unique_predicates(dst)
            if src_pred != dst_pred:
                rehearsal.fail(
                    "4-무결성",
                    f"부분 유니크의 WHERE 가 다르다 (원본에만: {sorted(src_pred - dst_pred)} · "
                    f"복원본에만: {sorted(dst_pred - src_pred)})",
                )
            if not dst_pred:
                # 하나도 없으면 위 비교가 «둘 다 0» 으로 통과한다 — 검사가 아무것도 안 본
                # 것이다. 이 제품에는 부분 유니크가 있다(D-189 · S2).
                rehearsal.fail("4-무결성", "부분 유니크 인덱스가 하나도 없다")

            # ── 5 — 표 집합과 행 수 ────────────────────────────────────────
            print("[5/8] 행 수 — 유실과 정책을 함께 본다", flush=True)
            src_tables, dst_tables = _table_names(src), _table_names(dst)
            if set(src_tables) != set(dst_tables):
                rehearsal.fail(
                    "5-행수",
                    f"표 집합이 다르다 (원본에만: {sorted(set(src_tables) - set(dst_tables))} · "
                    f"복원본에만: {sorted(set(dst_tables) - set(src_tables))})",
                )
            shared = sorted(set(src_tables) & set(dst_tables))
            src_counts, dst_counts = _row_counts(src, shared), _row_counts(dst, shared)
            excluded = set(policy.excluded_tables())
            total_rows = 0
            for name in shared:
                if name in excluded:
                    # **정책이 실제로 걸렸는가.** 여기가 0 이 아니면 매니페스트가 말하는
                    # 범위와 실제 덤프가 다르다는 뜻이고, 그것은 문서만 맞는 상태다.
                    if dst_counts[name] != 0:
                        rehearsal.fail(
                            "5-행수",
                            f"{name} 은 제외 대상인데 복원본에 {dst_counts[name]}행이 있다",
                        )
                    continue
                if src_counts[name] != dst_counts[name]:
                    rehearsal.fail(
                        "5-행수",
                        f"{name}: 원본 {src_counts[name]} 대 복원본 {dst_counts[name]}",
                    )
                total_rows += max(dst_counts[name], 0)
            rehearsal.summary["tables"] = len(dst_tables)
            rehearsal.summary["rows"] = total_rows
            rehearsal.summary["excluded_tables"] = sorted(excluded)

            # ── 6 — 스키마 판 ──────────────────────────────────────────────
            print("[6/8] 스키마 — 코드가 아는 head 와 같은가", flush=True)
            restored_head = dst.execute(
                text("select version_num from alembic_version")
            ).scalar_one_or_none()
            code_head = manifest_mod.code_alembic_head()
            rehearsal.summary["restored_alembic_head"] = restored_head
            rehearsal.summary["code_alembic_head"] = code_head
            if code_head is None:
                rehearsal.fail("6-스키마", "코드의 alembic head 를 읽지 못했다")
            elif restored_head != code_head:
                rehearsal.fail(
                    "6-스키마", f"복원본 {restored_head} 대 코드 {code_head}"
                )

            # ── 8 — 첨부 파일 (7 보다 먼저 돈다. 커넥션이 열려 있는 지금이 싸다) ──
            print("[8/8] 첨부 — DB 가 가리키는 바이트가 디스크에 있는가", flush=True)
            uploads_root = Path(settings.data_dir) / "uploads"
            missing = check_attachment_files(dst, uploads_root)
            rehearsal.summary["attachments_missing"] = len(missing)
            for line in missing[:20]:
                rehearsal.fail("8-첨부", line)
            if len(missing) > 20:
                rehearsal.fail("8-첨부", f"…그리고 {len(missing) - 20}건 더")

        restored_engine.dispose()

        # ── 7 — 복원본으로 앱을 띄운다 ─────────────────────────────────────
        print("[7/8] 앱 기동 — 복원본을 물고 실제 읽기 경로를 부른다", flush=True)
        try:
            _boot_and_read(restored_url, rehearsal)
        except Exception:  # noqa: BLE001
            rehearsal.fail("7-앱기동", traceback.format_exc(limit=6).strip().splitlines()[-1])
    finally:
        if keep:
            print(f"복원본을 남긴다: {restored_db}", flush=True)
        else:
            pg_backup.drop_database(source_url, restored_db, bin_dir=bin_dir)
        engine.dispose()

    rehearsal.summary["label"] = label or set_dir.name
    return rehearsal


def record(rehearsal: Rehearsal, *, label: str) -> None:
    """결과 한 줄을 `restore_rehearsals` 에 남긴다. 실패해도 결과를 뒤집지 않는다."""
    try:
        from app.backups.models import RestoreRehearsal
        from app.core.config import Settings
        from app.core.db import make_engine, make_session_factory

        settings = Settings()
        session_factory = make_session_factory(make_engine(settings.database_url))
        with session_factory() as db:
            db.add(
                RestoreRehearsal(
                    source_label=label,
                    started_at=rehearsal.started_at,
                    finished_at=_utcnow(),
                    ok=rehearsal.ok,
                    failures_json=json.dumps(rehearsal.failures, ensure_ascii=False),
                    summary_json=json.dumps(rehearsal.summary, ensure_ascii=False),
                )
            )
            db.commit()
        print("기록했다: restore_rehearsals", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"기록하지 못했다(결과는 그대로다): {exc!r}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="복구 리허설 (S12)")
    parser.add_argument("--record", action="store_true", help="결과를 restore_rehearsals 에 남긴다")
    parser.add_argument("--keep", action="store_true", help="복원본 데이터베이스를 안 지운다")
    parser.add_argument("--label", default=None, help="기록에 남길 이름")
    args = parser.parse_args(argv)

    rehearsal = run(label=args.label, keep=args.keep)
    label = args.label or str(rehearsal.summary.get("label") or "restore-rehearsal")
    if args.record:
        record(rehearsal, label=label)

    print(flush=True)
    print(json.dumps(rehearsal.summary, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    if rehearsal.ok:
        print("RESTORE_REHEARSAL_OK", flush=True)
        return 0
    print(f"RESTORE_REHEARSAL_FAILED ({len(rehearsal.failures)}건)", file=sys.stderr, flush=True)
    for line in rehearsal.failures:
        print(f"  - {line}", file=sys.stderr, flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
