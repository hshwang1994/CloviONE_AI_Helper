"""한 Domain 의 데이터만 지운다 — **스냅샷을 먼저 받고, 나머지는 손대지 않는다**.

지시 23 이 삭제를 허용한 것은 둘뿐이다: Chat Domain 과 Document DB. 나머지(User ·
Organization · Project · Ticket · 권한/RBAC · 요청하지 않은 다른 Domain)는 지우지 않는다.

## 왜 손으로 SQL 을 치지 않는가

`DELETE FROM chat_messages` 는 한 줄이다. 그 한 줄이 위험한 이유는 **어디까지가 그
Domain 인가**를 치는 사람이 그때그때 기억으로 정하기 때문이다. 표 하나를 빠뜨리면 고아
행이 남고, 하나를 더 넣으면 남의 Domain 이 사라진다. 둘 다 실행하는 순간에는 성공으로
보인다.

그래서 목록을 **코드에 적고 시험이 그 목록을 지킨다**(`tests/unit/test_reset_domain.py`).
목록 밖의 표는 이 스크립트로 지울 수 없고, 보호 목록의 표는 이름을 적어도 거절한다.

## 순서

    1. 표를 연다        — 실제 DB 에 있는가, 없는 표를 적고 있지 않은가
    2. 외래키를 적는다   — 지우는 차례가 그 관계에서 나온다
    3. 행 수를 센다      — 지우기 전/후를 둘 다 남긴다
    4. 스냅샷을 받는다   — `pg_dump` 로 **그 표들만**. 경로를 보고서에 적는다
    5. 지운다           — 한 트랜잭션. 자식부터
    6. 확인한다         — 대상은 0 이고 **보호 대상은 그대로다**

6번이 이 스크립트의 마지막 방어다. 「지웠다」가 아니라 「지우지 말아야 할 것이 그대로다」를
확인한다 — 전자는 성공했다는 말이고 후자는 사고가 없었다는 말이다.

## 파일

채팅 이미지는 DB 밖에도 있다(`<data_dir>/uploads/team_chat/<room_id>/`). 행만 지우면 그
파일들은 아무도 참조하지 않는 채 디스크에 남는다. `--purge-files` 를 주면 그 디렉터리도
지운다 — 기본값은 **안 지운다**: 파일 삭제는 스냅샷으로 되돌릴 수 없기 때문이다.

## 쓰는 법

    python scripts/reset_domain_data.py chat --dry-run      # 표·FK·행 수만 보고 끝낸다
    python scripts/reset_domain_data.py chat --snapshot-dir /var/backups/clovir
    python scripts/reset_domain_data.py chat --snapshot-dir … --purge-files --yes

`--yes` 가 없으면 실제 삭제는 안 한다. 되돌리기 어려운 일이라 기본값이 "안 함" 이다.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: 지울 수 있는 Domain 과 그 표 — **자식부터** 적는다. 이 순서가 곧 삭제 순서다.
#:
#: 순서를 FK 로 자동 계산하지 않는 이유: 계산이 맞아도 사람이 읽어서 확인할 수 없다.
#: 여기 적힌 순서가 틀리면 외래키가 즉시 거절하므로, 틀린 채로 지나가지 않는다.
DOMAINS: dict[str, tuple[str, ...]] = {
    # 팀 채팅(사내 메신저). `conversations`/`messages` 는 **여기 없다** — 그쪽은 AI 도우미의
    # 대화 기록이라 다른 Domain 이고, 지시 17 이 말한 「Chat DB 데이터」가 아니다.
    # 넣고 싶으면 사용자에게 다시 확인받고 이 목록에 적는다.
    "chat": (
        "chat_message_images",   # → chat_messages
        "chat_messages",         # → chat_rooms
        "chat_read_cursors",     # → chat_rooms
        "chat_room_members",     # → chat_rooms
        "chat_rooms",
    ),
}

#: 이 스크립트가 **어떤 경우에도** 손대지 않는 표. 지시 23 이 이름으로 적은 것들이다.
#:
#: 목록에 없다고 지워도 되는 것은 아니다 — 지울 수 있는 것은 `DOMAINS` 에 적힌 것뿐이고,
#: 이 목록은 그 위에 한 겹 더 두는 자물쇠다. 실수로 `DOMAINS` 에 이름을 적는 날을 막는다.
PROTECTED: tuple[str, ...] = (
    "users", "organizations", "departments",
    "projects", "project_milestones", "project_key_registry",
    "tickets", "ticket_cache", "ticket_activities", "ticket_comments",
    "roles", "role_permissions", "user_roles", "permissions",
    "audit_logs",
)

#: 삭제 뒤 「그대로인가」를 확인할 표. 여기 수가 바뀌었으면 사고다.
WITNESS: tuple[str, ...] = ("users", "projects", "tickets")


def _engine():
    from app.core.config import get_settings
    from app.core.db import make_engine

    return make_engine(get_settings().database_url)


def _table_names(conn) -> set[str]:
    from sqlalchemy import inspect

    return set(inspect(conn).get_table_names())


def _count(conn, table: str) -> int:
    from sqlalchemy import text as sa_text

    return conn.execute(sa_text(f'SELECT count(*) FROM "{table}"')).scalar_one()


def _foreign_keys(conn, table: str) -> list[str]:
    from sqlalchemy import inspect

    out = []
    for fk in inspect(conn).get_foreign_keys(table):
        cols = ", ".join(fk.get("constrained_columns") or [])
        ref = fk.get("referred_table")
        out.append(f"{cols} → {ref}")
    return out


def _snapshot(tables: tuple[str, ...], out_dir: Path, url: str) -> Path:
    """`pg_dump` 로 **그 표들만** 받는다. 경로를 돌려준다.

    전체 덤프를 받지 않는 이유: 이 작업의 되돌리기 대상은 그 표들이고, 전체 덤프는
    되돌릴 때 남의 Domain 까지 함께 되돌릴 수 있는 도구가 된다. 좁은 스냅샷이 좁은
    복구를 강제한다.

    `pg_dump` 경로는 `PGDUMP` 로 덮을 수 있다 — `PATH` 의 것이 서버보다 낮은 버전이면
    거절당한다(`app/core/config.py` 가 같은 사정을 적어 뒀다).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # 파일 이름에 시각을 넣지 않는다 — 이 스크립트는 시계를 읽지 않고, 호출부가 디렉터리로
    # 회차를 가른다. 같은 디렉터리에 두 번 받으면 덮어쓴다는 뜻이고, 그게 의도다.
    target = out_dir / "chat-domain.sql"
    cmd = [os.environ.get("PGDUMP", "pg_dump"), "--data-only", "--no-owner", "--no-privileges"]
    for t in tables:
        cmd += ["--table", t]
    cmd += ["--file", str(target), url]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(f"[FAIL] 스냅샷을 받지 못했다 — 지우지 않는다.\n{proc.stderr.strip()}")
    return target


def _purge_files(data_dir: Path, namespace: str) -> int:
    """업로드 네임스페이스 하나를 통째로 비운다. 지운 파일 수를 돌려준다.

    **되돌릴 수 없다.** DB 스냅샷에는 파일이 없다 — 그래서 기본값이 «안 지움» 이다.
    """
    import shutil

    root = Path(data_dir) / "uploads" / namespace
    if not root.is_dir():
        return 0
    n = sum(1 for p in root.rglob("*") if p.is_file())
    shutil.rmtree(root)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("domain", choices=sorted(DOMAINS))
    ap.add_argument("--dry-run", action="store_true", help="표·FK·행 수만 보고 끝낸다")
    ap.add_argument("--snapshot-dir", help="pg_dump 를 받을 디렉터리(삭제하려면 필수)")
    ap.add_argument("--purge-files", action="store_true",
                    help="업로드 파일도 지운다. 스냅샷으로 되돌릴 수 없다")
    ap.add_argument("--yes", action="store_true", help="실제로 지운다")
    args = ap.parse_args()

    from sqlalchemy import text as sa_text

    from app.core.config import get_settings

    settings = get_settings()
    tables = DOMAINS[args.domain]

    bad = [t for t in tables if t in PROTECTED]
    if bad:
        print(f"[FAIL] 보호 대상이 삭제 목록에 있다: {', '.join(bad)}")
        return 1

    engine = _engine()
    with engine.connect() as conn:
        present = _table_names(conn)
        missing = [t for t in tables if t not in present]
        if missing:
            print(f"[FAIL] DB 에 없는 표를 적고 있다: {', '.join(missing)}")
            return 1

        print(f"== {args.domain} Domain — 표 {len(tables)}개 ==")
        before = {}
        for t in tables:
            before[t] = _count(conn, t)
            fks = _foreign_keys(conn, t)
            print(f"  {t:24s} {before[t]:>8,}행   FK: {', '.join(fks) or '없음'}")
        witness_before = {t: _count(conn, t) for t in WITNESS if t in present}
        print("== 지우지 않는 것(대조군) ==")
        for t, n in witness_before.items():
            print(f"  {t:24s} {n:>8,}행")

    if args.dry_run:
        print("\nDRY_RUN — 아무것도 지우지 않았다.")
        return 0

    if not args.snapshot_dir:
        print("\n[FAIL] `--snapshot-dir` 없이는 지우지 않는다(지시 23 · 4).")
        return 1
    if not args.yes:
        print("\n[FAIL] `--yes` 없이는 지우지 않는다. 되돌리기 어려운 일이라 기본값이 «안 함» 이다.")
        return 1

    snap = _snapshot(tables, Path(args.snapshot_dir), settings.database_url)
    print(f"\n스냅샷: {snap}  ({snap.stat().st_size:,} bytes)")

    with engine.begin() as conn:
        # 한 트랜잭션이다. 중간에 실패하면 **하나도 안 지워진다** — 반쯤 지워진 채팅은
        # 고아 행과 깨진 방이 남아, 되돌리려면 결국 스냅샷을 통째로 되살려야 한다.
        for t in tables:
            conn.execute(sa_text(f'DELETE FROM "{t}"'))

    with engine.connect() as conn:
        after = {t: _count(conn, t) for t in tables}
        witness_after = {t: _count(conn, t) for t in witness_before}

    print("== 결과 ==")
    for t in tables:
        print(f"  {t:24s} {before[t]:>8,} → {after[t]:>8,}")
    left = [t for t, n in after.items() if n]
    if left:
        print(f"[FAIL] 지워지지 않은 표가 있다: {', '.join(left)}")
        return 1

    # 🔴 마지막 방어. 「지웠다」가 아니라 **「지우지 말아야 할 것이 그대로다」** 를 본다.
    moved = {t: (witness_before[t], witness_after[t])
             for t in witness_before if witness_before[t] != witness_after[t]}
    if moved:
        print("[FAIL] 지우지 말아야 할 표의 행 수가 바뀌었다:")
        for t, (b, a) in moved.items():
            print(f"  {t}: {b:,} → {a:,}")
        return 1
    for t, n in witness_after.items():
        print(f"  {t:24s} {n:>8,} (그대로)")

    if args.purge_files and args.domain == "chat":
        removed = _purge_files(Path(settings.data_dir), "team_chat")
        print(f"업로드 파일 {removed:,}개를 지웠다 (uploads/team_chat).")

    print("\nRESET_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
