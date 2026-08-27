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
    6. 구조를 다시 심는다 — 마이그레이션이 심었던 행(「전체 채팅」 방 같은 것)
    7. 확인한다         — 사용자 데이터는 0, **보호 대상은 그대로**

6번을 빼면 기능이 조용히 없어진다. 「전체 채팅」 방은 사람이 만든 대화가 아니라
마이그레이션 `0001` 이 심은 구조이고, 마이그레이션은 한 번만 돌기 때문에 저절로 안 돌아온다.
앱은 그 방이 없어도 안 죽어서 아무도 모른 채 지나간다 — 실제로 한 번 밟았다.

7번이 이 스크립트의 마지막 방어다. 「지웠다」가 아니라 「지우지 말아야 할 것이 그대로다」를
확인한다 — 전자는 성공했다는 말이고 후자는 사고가 없었다는 말이다.

## 파일

채팅 이미지는 DB 밖에도 있다(`<data_dir>/uploads/team_chat/<room_id>/`). 행만 지우면 그
파일들은 아무도 참조하지 않는 채 디스크에 남는다. `--purge-files` 를 주면 그 디렉터리도
지운다 — 기본값은 **안 지운다**: 파일 삭제는 스냅샷으로 되돌릴 수 없기 때문이다.

## 쓰는 법

    python scripts/reset_domain_data.py chat --dry-run      # 표·FK·행 수만 보고 끝낸다
    python scripts/reset_domain_data.py document --dry-run --snapshot-dir …  # 받아만 둔다
    python scripts/reset_domain_data.py chat --snapshot-dir /var/backups/clovir
    python scripts/reset_domain_data.py chat --snapshot-dir … --purge-files --yes

`--yes` 가 없으면 실제 삭제는 안 한다. 되돌리기 어려운 일이라 기본값이 "안 함" 이다.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: 지울 수 있는 Domain 과 그 표 — **자식부터** 적는다. 이 순서가 곧 삭제 순서다.
#:
#: 순서를 FK 로 자동 계산하지 않는 이유: 계산이 맞아도 사람이 읽어서 확인할 수 없다.
#: 여기 적힌 순서가 틀리면 외래키가 즉시 거절하므로, 틀린 채로 지나가지 않는다.
@dataclass(frozen=True)
class Target:
    """지울 표 하나. `where` 가 있으면 **그 표의 일부**다.

    부분 삭제가 필요한 이유는 하나뿐이다: 검색 색인(`search_documents`)은 티켓·게시판·
    사용자와 문서를 **한 표에** 담는다. 표 전체를 비우면 문서를 지우면서 티켓 검색이
    함께 사라지고, 그것은 이 작업이 허락받은 범위가 아니다.

    조건은 코드에 상수로만 적는다 — 명령행에서 받지 않는다. 받는 순간 이 스크립트는
    「임의의 DELETE 를 실행하는 도구」가 되고, 목록을 코드에 적어 둔 의미가 없어진다.
    """

    table: str
    where: str = ""

    def __str__(self) -> str:
        return f"{self.table} ({self.where})" if self.where else self.table


DOMAINS: dict[str, tuple[Target, ...]] = {
    # 팀 채팅(사내 메신저). `conversations`/`messages` 는 **여기 없다** — 그쪽은 AI 도우미의
    # 대화 기록이라 다른 Domain 이고, 지시 17 이 말한 「Chat DB 데이터」가 아니다.
    # 넣고 싶으면 사용자에게 다시 확인받고 이 목록에 적는다.
    "chat": (
        Target("chat_message_images"),   # -> chat_messages
        Target("chat_messages"),         # -> chat_rooms
        Target("chat_read_cursors"),     # -> chat_rooms
        Target("chat_room_members"),     # -> chat_rooms
        Target("chat_rooms"),
    ),
    # 문서(Native Knowledge). 지시 22.3 이 「사용자 Document 데이터와 그 문서에서 직접
    # 파생된 DB 데이터」라고 적은 범위다.
    #
    # **여기 없는 것이 여기 있는 것만큼 중요하다.**
    #
    #   * `knowledge_spaces` · `folders` — 문서가 아니라 문서가 사는 **골격**이다. 비우면
    #     초기화 뒤 「새 문서」가 고를 공간이 하나도 없어서 문서를 만들 수 없다.
    #   * `files` — 첨부의 **본체 메타데이터**이고 그 뒤에 실제 바이너리가 있다. 지시가
    #     이름으로 지우지 말라고 적었다. 여기서 지우는 것은 문서와 파일을 잇는 줄
    #     (`document_attachments`)뿐이고, 파일 자체는 남아 별도 Sweep 대상이 된다.
    #   * `document_cache` — 옛 Notion 미러다. 향후 1회성 재이관의 계보라 지시 22.2 가
    #     남기라고 적었다. 지금 화면은 이 표를 읽지 않는다.
    #   * `trash_items` — 티켓도 함께 들어 있는 공용 표다. Native 문서는 이 표를 쓰지 않고
    #     (`documents.archived` 가 휴지통의 정본이다), 지금 문서 항목도 0건이다.
    "document": (
        Target("document_chunks"),         # -> documents, files, document_versions
        Target("ai_index_state"),          # -> documents
        Target("document_recent_views"),   # -> documents
        Target("document_favorites"),      # -> documents
        Target("document_comments"),       # -> documents
        Target("document_mentions"),       # -> documents
        Target("document_attachments"),    # -> documents, files (**연결만** 지운다)
        Target("document_relations"),      # -> documents (양방향)
        Target("document_tags"),           # -> documents, tags
        Target("tags"),                    # 문서 태그 어휘. 문서가 없으면 뜻이 없다
        # 판을 문서보다 **먼저** 지운다. 두 표가 서로를 가리키는데
        # (`documents.current_version_id` -> SET NULL) 이 방향이라야 한 번에 풀린다.
        Target("document_versions"),
        Target("documents"),
        # 부분 삭제 하나 — 문서 색인만. 티켓·게시판·사용자 색인은 그대로 둔다.
        Target("search_documents", where="kind = 'document'"),
    ),
}

#: 🔴 **데이터를 지우면 함께 사라지는 구조 행.** 지운 뒤 다시 심는다.
#:
#: 이 목록이 왜 필요한가는 실제로 밟아 봐서 안다. 채팅 초기화에서 `chat_rooms` 를 비웠더니
#: 「전체 채팅」 방이 함께 사라졌다 — 그 행은 사람이 만든 대화가 아니라 **마이그레이션
#: `0001` 이 심은 구조**였고, 마이그레이션은 한 번만 돌기 때문에 저절로 돌아오지 않는다.
#: 앱은 그 방이 없어도 안 죽는다(`get_global_room` 이 `None` 을 곱게 다룬다) — 그래서
#: 기능 하나가 조용히 없어진 채로 남는다. 「일관성 있게 초기화한다」가 뜻하는 것이 이것이다:
#: 사용자 데이터는 0 으로, 구조는 처음 상태로.
#:
#: 부서 방은 여기 없다. 그쪽은 방 목록을 여는 길목에서 게으르게 다시 만들어진다
#: (`app/team_chat/service.py::ensure_team_room`) — 저절로 돌아오는 것을 심으면 두 곳이
#: 같은 행을 만들려고 다툰다.
RESEED: dict[str, tuple[tuple[str, dict], ...]] = {
    "chat": (
        (
            "INSERT INTO chat_rooms"
            " (id, kind, title, is_global, dm_key, event_seq, org_id, created_at, updated_at)"
            " VALUES (:id, 'group', :title, true, NULL, 0, :org, :now, :now)"
            " ON CONFLICT (id) DO NOTHING",
            {
                # `alembic/versions/0001_pg_baseline.py` 의 `_GLOBAL_CHAT_ROOM_ID` 와 같은 값이다.
                # 고정 id 라 두 번 심어도 하나다(`ON CONFLICT DO NOTHING`).
                "id": "00000000-0000-0000-0000-0000cha70001",
                "title": "전체 채팅",
                "org": "00000000-0000-0000-0000-00000000org1",
            },
        ),
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
    # ── 문서 회차가 이름으로 지목한 것들 (지시 22.3) ──────────────────────────
    # 문서를 지우면서 함께 사라지기 **쉬운** 것들이라 여기 적는다. 셋 다 「문서 데이터」로
    # 읽힐 수 있지만 하나도 문서가 아니다.
    "knowledge_spaces",   # 문서가 사는 골격. 비우면 새 문서를 만들 공간이 없어진다
    "folders",            # 같은 골격의 정리 축
    "files",              # 첨부의 본체 메타데이터. 그 뒤에 실제 바이너리가 있다
    "document_cache",     # 옛 Notion 미러 — 향후 1회성 재이관의 계보 (지시 22.2)
    "trash_items",        # 티켓이 함께 들어 있는 공용 표
    # AI 도우미의 대화 기록. 사내 메신저(`chat_*`)와 다른 Domain 이고, 지우라는 요청을
    # 받은 적이 없다. 채팅 회차에 실제로 헷갈릴 뻔한 자리라 이름으로 잠근다.
    "conversations", "messages",
)

#: 삭제 뒤 「그대로인가」를 확인할 표. 여기 수가 바뀌었으면 사고다.
WITNESS: tuple[str, ...] = ("users", "projects", "tickets")


def _settings():
    """설치의 설정 한 벌. **`Settings()` 를 직접 만든다** — 이 저장소에는 캐시된 접근자가
    없다(`app/main.py` 도 같은 방식으로 만든다). 값은 서비스가 읽는 환경 파일에서 온다."""
    from app.core.config import Settings

    return Settings()


def _engine():
    from app.core.db import make_engine

    return make_engine(_settings().database_url)


def _table_names(conn) -> set[str]:
    from sqlalchemy import inspect

    return set(inspect(conn).get_table_names())


def _count(conn, table: str, where: str = "") -> int:
    from sqlalchemy import text as sa_text

    sql = f'SELECT count(*) FROM "{table}"'
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sa_text(sql)).scalar_one()


def _foreign_keys(conn, table: str) -> list[str]:
    from sqlalchemy import inspect

    out = []
    for fk in inspect(conn).get_foreign_keys(table):
        cols = ", ".join(fk.get("constrained_columns") or [])
        ref = fk.get("referred_table")
        out.append(f"{cols} → {ref}")
    return out


def _snapshot(domain: str, tables: list[str], out_dir: Path, url: str) -> Path:
    """`pg_dump` 로 **그 표들만** 받는다. 경로를 돌려준다.

    전체 덤프를 받지 않는 이유: 이 작업의 되돌리기 대상은 그 표들이고, 전체 덤프는
    되돌릴 때 남의 Domain 까지 함께 되돌릴 수 있는 도구가 된다. 좁은 스냅샷이 좁은
    복구를 강제한다.

    부분 삭제 대상(`Target.where`)도 **표 전체**를 받는다. 조건에 맞는 행만 받으면
    되돌릴 때 그 표의 나머지가 어떤 상태였는지 알 수 없고, 스냅샷은 넉넉한 쪽이 안전하다.

    `pg_dump` 경로는 `PGDUMP` 로 덮을 수 있다 — `PATH` 의 것이 서버보다 낮은 버전이면
    거절당한다(`app/core/config.py` 가 같은 사정을 적어 뒀다).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # 파일 이름에 시각을 넣지 않는다 — 이 스크립트는 시계를 읽지 않고, 호출부가 디렉터리로
    # 회차를 가른다. 같은 디렉터리에 두 번 받으면 덮어쓴다는 뜻이고, 그게 의도다.
    target = out_dir / f"{domain}-domain.sql"
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

    settings = _settings()
    targets = DOMAINS[args.domain]
    tables = [t.table for t in targets]

    bad = [t.table for t in targets if t.table in PROTECTED]
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

        print(f"== {args.domain} Domain — 표 {len(targets)}개 ==")
        before = {}
        for t in targets:
            before[t] = _count(conn, t.table, t.where)
            fks = _foreign_keys(conn, t.table)
            print(f"  {str(t):34s} {before[t]:>8,}행   FK: {', '.join(fks) or '없음'}")
        witness_before = {t: _count(conn, t) for t in WITNESS if t in present}
        print("== 지우지 않는 것(대조군) ==")
        for t, n in witness_before.items():
            print(f"  {t:34s} {n:>8,}행")

    if args.dry_run:
        # 스냅샷은 **여기서도** 받을 수 있다. 승인을 받기 전에 되돌릴 자리를 먼저 만들어
        # 두려는 것이라, 「받아 두기」와 「지우기」를 한 명령에 묶지 않는다.
        if args.snapshot_dir:
            snap = _snapshot(args.domain, tables, Path(args.snapshot_dir), settings.database_url)
            print(f"\n스냅샷: {snap}  ({snap.stat().st_size:,} bytes)")
        print("\nDRY_RUN — 아무것도 지우지 않았다.")
        return 0

    if not args.snapshot_dir:
        print("\n[FAIL] `--snapshot-dir` 없이는 지우지 않는다(지시 23 · 4).")
        return 1
    if not args.yes:
        print("\n[FAIL] `--yes` 없이는 지우지 않는다. 되돌리기 어려운 일이라 기본값이 «안 함» 이다.")
        return 1

    snap = _snapshot(args.domain, tables, Path(args.snapshot_dir), settings.database_url)
    print(f"\n스냅샷: {snap}  ({snap.stat().st_size:,} bytes)")

    with engine.begin() as conn:
        # 한 트랜잭션이다. 중간에 실패하면 **하나도 안 지워진다** — 반쯤 지워진 도메인은
        # 고아 행과 깨진 참조가 남아, 되돌리려면 결국 스냅샷을 통째로 되살려야 한다.
        for t in targets:
            sql = f'DELETE FROM "{t.table}"'
            if t.where:
                sql += f" WHERE {t.where}"
            conn.execute(sa_text(sql))

    # 지운 **뒤에** 구조를 다시 심는다. 순서가 반대면 방금 심은 행을 그 자리에서 지운다.
    seeds = RESEED.get(args.domain, ())
    if seeds:
        from datetime import datetime, timezone

        # naive UTC 다 — 이 저장소의 저장 규약이다(§불변 7).
        stamp = datetime.now(timezone.utc).replace(tzinfo=None)
        with engine.begin() as conn:
            for sql, params in seeds:
                conn.execute(sa_text(sql), {**params, "now": stamp})

    with engine.connect() as conn:
        after = {t: _count(conn, t.table, t.where) for t in targets}
        witness_after = {t: _count(conn, t) for t in witness_before}

    print("== 결과 ==")
    for t in targets:
        print(f"  {str(t):34s} {before[t]:>8,} → {after[t]:>8,}")
    # 남아도 되는 것은 **다시 심은 구조 행뿐**이다. 그 수를 세어 두고 그만큼만 허용한다 —
    # 「0 이 아니면 실패」로 두면 재시드를 넣는 순간 검사가 늘 빨개지고, 「그냥 통과」로
    # 두면 안 지워진 사용자 데이터를 못 잡는다.
    seeded = len(RESEED.get(args.domain, ()))
    left = [str(t) for t, n in after.items() if n]
    if sum(after.values()) > seeded:
        print(f"[FAIL] 지워지지 않은 표가 있다: {', '.join(left)}")
        return 1
    if seeded:
        print(f"  (구조 행 {seeded}개를 다시 심었다 — 사용자 데이터가 아니다)")

    # 🔴 마지막 방어. 「지웠다」가 아니라 **「지우지 말아야 할 것이 그대로다」** 를 본다.
    moved = {t: (witness_before[t], witness_after[t])
             for t in witness_before if witness_before[t] != witness_after[t]}
    if moved:
        print("[FAIL] 지우지 말아야 할 표의 행 수가 바뀌었다:")
        for t, (b, a) in moved.items():
            print(f"  {t}: {b:,} → {a:,}")
        return 1
    for t, n in witness_after.items():
        print(f"  {t:34s} {n:>8,} (그대로)")

    if args.purge_files and args.domain == "chat":
        removed = _purge_files(Path(settings.data_dir), "team_chat")
        print(f"업로드 파일 {removed:,}개를 지웠다 (uploads/team_chat).")

    print("\nRESET_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
