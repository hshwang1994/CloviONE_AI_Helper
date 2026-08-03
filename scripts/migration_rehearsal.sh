#!/usr/bin/env bash
# 마이그레이션 리허설 — 운영에 올리기 전에 '올리고 되돌리고 다시 올리기'를 사본에서 해 본다.
#
# 왜 필요한가: 이번 배포는 사용자 결정에 따라 **한 번에** 나간다(UI 전면 교체 + 마이그레이션 여러 개).
# 롤백 단위가 크다는 뜻이라, 되돌아갈 수 있다는 걸 미리 증명해 두지 않으면 배포 당일에
# "되돌릴 수 있나?"를 처음 시험하게 된다.
#
# 특히 SQLite에서 batch_alter_table 다운그레이드는 **테이블을 다시 만든다**. 컬럼 순서·기본값·
# 인덱스가 조용히 달라질 수 있어서, 왕복(up→down→up)이 성공하는 것만으로는 부족하고
# 스키마와 행 수를 앞뒤로 비교해야 한다. 이 스크립트가 그걸 한다.
#
# 사용법:
#   bash scripts/migration_rehearsal.sh                     # var/web.sqlite3 사본으로
#   bash scripts/migration_rehearsal.sh /path/to/prod.sqlite3
#   STEPS=3 bash scripts/migration_rehearsal.sh             # 3단계 내려갔다 올라온다
#
# 운영 DB를 쓸 때도 **원본은 절대 건드리지 않는다** — 사본을 만들어 그 위에서만 돈다.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=".venv/bin/python"
[ -x "$PY" ] || PY="python"

# Windows 기본 콘솔 인코딩(cp949)에서는 아래 Python 블록의 한국어 판정 문구가 깨져
# 읽을 수 없다. 실패했을 때 이유를 못 읽으면 검사가 없는 것과 같다.
export PYTHONIOENCODING=utf-8

SRC="${1:-var/web.sqlite3}"
STEPS="${STEPS:-1}"
WORK="var/rehearsal"
STAMP="$(date +%Y%m%d-%H%M%S)"
DB="$WORK/rehearsal-$STAMP.sqlite3"

fail() { echo ""; echo "[FAIL] $1" >&2; exit 1; }

[ -f "$SRC" ] || fail "원본 DB가 없다: $SRC"
mkdir -p "$WORK"
cp "$SRC" "$DB"
# WAL/SHM 도 함께 복사해야 커밋되지 않은 트랜잭션까지 같은 상태가 된다.
[ -f "$SRC-wal" ] && cp "$SRC-wal" "$DB-wal"
[ -f "$SRC-shm" ] && cp "$SRC-shm" "$DB-shm"
echo "사본 생성: $DB  (원본 $SRC 는 건드리지 않는다)"

# 상대 경로로 준다. Git Bash에서 $(pwd)는 /c/Users/... 형태라 SQLAlchemy가 열지 못한다
# (Windows에서 'unable to open database file'로 떨어진다). 스크립트는 항상 저장소 루트에서
# 돌기 때문에 상대 경로가 안전하다.
export DATABASE_URL="sqlite:///./$DB"

snapshot() {   # $1 = 라벨. 스키마와 테이블별 행 수를 찍는다.
  "$PY" - "$DB" "$1" <<'PYEOF'
import sqlite3, sys, json
db, label = sys.argv[1], sys.argv[2]
c = sqlite3.connect(db)
tables = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
out = {}
for t in tables:
    cols = [(r[1], r[2], r[3], r[5]) for r in c.execute(f'pragma table_info("{t}")')]
    try:
        n = c.execute(f'select count(*) from "{t}"').fetchone()[0]
    except sqlite3.Error:
        n = -1
    out[t] = {"columns": cols, "rows": n}
ver = c.execute("select version_num from alembic_version").fetchone()
print(json.dumps({"label": label, "alembic": ver and ver[0], "tables": out},
                 ensure_ascii=False, sort_keys=True))
PYEOF
}

echo ""
echo "== 1) 현재 상태 =="
BEFORE="$(snapshot before)"
echo "$BEFORE" | "$PY" -c "import sys,json; d=json.load(sys.stdin); print('  head:', d['alembic'], '| 테이블', len(d['tables']))"

echo ""
echo "== 2) upgrade head =="
"$PY" -m alembic upgrade head 2>&1 | tail -3 || fail "upgrade head 실패"
AFTER_UP="$(snapshot after_up)"
echo "$AFTER_UP" | "$PY" -c "import sys,json; d=json.load(sys.stdin); print('  head:', d['alembic'], '| 테이블', len(d['tables']))"

echo ""
echo "== 3) downgrade -$STEPS =="
"$PY" -m alembic downgrade "-$STEPS" 2>&1 | tail -3 || fail "downgrade 실패 — 되돌릴 수 없는 마이그레이션이다"
DOWN="$(snapshot after_down)"
echo "$DOWN" | "$PY" -c "import sys,json; d=json.load(sys.stdin); print('  head:', d['alembic'], '| 테이블', len(d['tables']))"

echo ""
echo "== 4) 다시 upgrade head =="
"$PY" -m alembic upgrade head 2>&1 | tail -3 || fail "재-upgrade 실패 — 다운그레이드가 스키마를 망가뜨렸다"
AFTER_RE="$(snapshot after_reup)"

echo ""
echo "== 5) 왕복 전후 비교 =="
"$PY" - <<PYEOF
import json, sys
up = json.loads(r'''$AFTER_UP''')
down = json.loads(r'''$DOWN''')
re_ = json.loads(r'''$AFTER_RE''')

# 되돌리는 구간에서 **생성된** 테이블은, 되돌리면 지워지는 것이 정상이다. 그 안의 행이
# 사라졌다고 실패로 치면 이 게이트는 영구히 빨간불이 되고 사람들이 곧 무시하게 된다.
# 그렇다고 조용히 넘기면 "롤백하면 무엇을 잃는가"를 아무도 모른 채 배포일을 맞는다.
# 그래서 둘로 가른다:
#   치명 — 다운그레이드 후에도 남아 있던 테이블이 행을 잃었다(진짜 유실).
#   경고 — 다운그레이드가 지우는 테이블이라 왕복 후 비었다(롤백의 대가. 보고만 한다).
dropped_by_rollback = set(up["tables"]) - set(down["tables"])

problems, rollback_cost = [], []
if up["alembic"] != re_["alembic"]:
    problems.append(f"head 불일치: {up['alembic']} vs {re_['alembic']}")
only_up = set(up["tables"]) - set(re_["tables"])
only_re = set(re_["tables"]) - set(up["tables"])
if only_up: problems.append(f"왕복 후 사라진 테이블: {sorted(only_up)}")
if only_re: problems.append(f"왕복 후 생긴 테이블: {sorted(only_re)}")
for t in sorted(set(up["tables"]) & set(re_["tables"])):
    a, b = up["tables"][t], re_["tables"][t]
    if a["columns"] != b["columns"]:
        problems.append(f"{t}: 컬럼 정의가 달라졌다\\n    전: {a['columns']}\\n    후: {b['columns']}")
    if a["rows"] == b["rows"]:
        continue
    if t in dropped_by_rollback:
        rollback_cost.append(f"{t}: {a['rows']}행 → {b['rows']}행")
    else:
        problems.append(f"{t}: 행 수 {a['rows']} → {b['rows']} (데이터 유실)")

if rollback_cost:
    print(f"[주의] 이 구간을 롤백하면 아래 테이블이 통째로 사라진다({len(rollback_cost)}개).")
    print("       스키마상 정상이지만, 되돌리기 전에 백업을 뜨라는 뜻이다:")
    for c in rollback_cost: print("  -", c)
if problems:
    print("[FAIL] 왕복이 스키마/데이터를 보존하지 않았다:")
    for p in problems: print("  -", p)
    sys.exit(1)
kept = len(re_["tables"]) - len(dropped_by_rollback)
print(f"[OK] 왕복 후 스키마 동일, 살아남는 테이블 {kept}개의 행 수 동일 "
      f"(전체 {len(re_['tables'])}개)")
PYEOF
[ $? -eq 0 ] || fail "왕복 검증 실패"

echo ""
echo "== 6) 무결성 검사 =="
INTEG="$("$PY" -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('pragma integrity_check').fetchone()[0])" "$DB")"
[ "$INTEG" = "ok" ] || fail "integrity_check: $INTEG"
echo "  integrity_check: ok"

echo ""
echo "REHEARSAL_OK  (사본: $DB — 확인 후 지워도 된다)"
