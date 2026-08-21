"""복구 리허설 — 백업이 «복원되면 앱이 실제로 도는가» 를 증명한다. **아직 PG 이식 전이다.**

## 왜 이 스크립트가 있는가

`app/backups/` 는 백업 **파일 자체**를 검사한다(`pg_dump -Fc` + sha256 + `pg_restore --list`
+ 임시 DB 실복원). 그런데 그것으로도 답하지 못하는 질문이 하나 남는다: **그 복원본을 물고
앱이 실제로 뜨고 읽기 경로가 도는가.** 백업은 복원해 본 적이 없으면 백업이 아니다.

복원은 마지막 안전망이고, 그 안전망을 사고 당일에 처음 시험하게 둘 수는 없다.

## 지금은 왜 멈추는가

옛 구현 8단계는 전부 SQLite 를 전제했다 — 온라인 Backup API · `PRAGMA integrity_check` ·
**파일 하나를 제자리에 되돌리는 복원**. System of Record 가 PostgreSQL 로 옮겨지면서
(D-187) 그중 어느 것도 성립하지 않는다.

그래서 **조용히 이상한 결과를 내는 대신 여기서 멈춘다.** 복구 리허설이 「통과」를 찍는데
실제로는 아무것도 확인하지 않은 상태가 가장 나쁘다 — 사람들이 그 초록을 믿고 복원 계획을
세우기 때문이다. S2 는 그 아래 계층(`app/backups/pg_backup.py`)까지만 만들었고, 이 스크립트의
이식은 **S12(Backup/Restore 운영)** 가 한다.

옛 SQLite 구현은 커밋 `95a89189` 에 그대로 있다. 되살려 고치는 것이 아니라 **PG 기준으로
다시 쓰는** 편이 맞다 — 아래 단계 중 절반이 PG 에서는 다른 일이 된다.

## S12 가 다시 만들 단계 (뒤로 갈수록 사용자가 보는 층에 가깝다)

  1. 앱 자신의 코드로 백업을 뜬다 (`app/backups/pg_backup.py` — 손으로 부른 `pg_dump` 가 아니라)
  2. 앱 자신의 검증 (체크섬 + `pg_restore --list`)
  3. 복원: **새 데이터베이스**로 되돌린다 (PG 에는 «파일을 제자리에» 가 없다)
  4. 복원본의 무결성 — `integrity_check` 대신 제약과 인덱스가 실제로 다시 섰는지 본다
     (부분 유니크의 `WHERE` · GIN trgm · identity 는 실제로 잘 떨어지는 자리다)
  5. 표 집합과 행 수를 원본과 대조한다 (유실 탐지)
  6. `alembic_version` 이 **코드가 아는 head** 와 같은가
     — 백업이 옛 스키마인데 새 코드를 올리면 여기서 걸린다
  7. **복원본을 물고 앱을 실제로 띄워 읽기 경로를 호출한다** ← 이것이 진짜 확인이다.
     1~6 이 전부 통과해도 여기서 죽을 수 있다(ORM 이 기대하는 컬럼이 없는 경우 등).
  8. 첨부 파일이 실제로 디스크에 있는가 (BKP-02) — **이 조각은 아래에 살아 있다.**
     `check_attachment_files()` 는 저장소 종류를 타지 않아 PG 로 옮겨 뒀고, 시험도 그대로다.
     S12 는 이것을 다시 쓰지 말고 그냥 부르면 된다.

`--record` 는 결과 한 줄을 `restore_rehearsals` 표에 남겨(0001 기준선에 있다) 관리 콘솔의
백업 화면이 「마지막으로 복원을 시험한 게 언제인가」를 보여 주게 한다. 기록에 실패해도
리허설 결과 자체는 바뀌지 않는다 — 증거를 남기지 못한 것이 증거를 뒤집지는 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ── 첨부 파일 확인 (BKP-02) — 8단계 중 **이 조각만** 남겨 뒀다 ──────────────────
#
# 나머지 단계와 달리 이것은 SQLite 를 전제하지 않는다. DB 가 참조하는 바이트가 디스크에
# 실제로 있는지 보는 일이라, 저장소가 무엇이든 같은 질문이다. 그래서 PG 로 옮겨 살려 뒀고
# 시험도 함께 남아 있다(`tests/regression/test_restore_rehearsal_attachments.py`) —
# S12 가 리허설을 다시 쓸 때 이 조각은 그대로 부르면 된다.
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


MESSAGE = """복구 리허설은 아직 PostgreSQL 로 이식되지 않았습니다.

  이 스크립트의 8단계는 SQLite(파일 하나가 곧 DB)를 전제했습니다. System of Record 가
  PostgreSQL 로 바뀌어(D-187) 그 전제가 더는 성립하지 않습니다.

  지금 쓸 수 있는 것: 백업 자체의 검증은 제품이 이미 합니다.
    pg_dump -Fc + 체크섬 + pg_restore --list + 임시 DB 실복원
    (app/backups/pg_backup.py, 관리 콘솔의 백업 실행과 검증)

  아직 없는 것: 복원본으로 앱을 띄워 읽기 경로까지 확인하는 단계입니다.
  그것이 이 스크립트의 존재 이유이고, 이식은 S12 가 합니다
  (docs/platform/MASTER_PLAN.md 9.1)."""


def main() -> int:
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
