# -*- coding: utf-8 -*-
"""S1 / P-03 (A-2) — 지연은 **서버가 잰 값**으로 잰다.

첫 판은 질의마다 `psql` 프로세스를 새로 띄워 재는 바람에 세 경로가 전부 ~20ms 로 같게 나왔다.
그건 PG 지연이 아니라 **프로세스 시작 시간**이다 — 같은 실행의 `EXPLAIN` 이 실제 실행을
0.23ms 로 적고 있었다. 값이 전 표본에서 같으면 측정이 아니라 상수를 읽고 있는 것이다.

두 번째 판은 `EXPLAIN … FORMAT JSON` 출력을 대괄호 개수로 잘랐는데, 한국어 질의 문자열 안에
`[` 가 들어가면 깊이가 어긋났다(1,206/1,800). 파서를 고치는 대신 **서버가 숫자 하나만
돌려주게** 한다 — plpgsql 이 계획을 jsonb 로 받아 `Execution Time` 만 뽑는다.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys

PSQL = os.environ["PSQL"]
SOCK = os.environ["PGSOCK"]
PORT = os.environ.get("PGPORT", "55432")
DB = os.environ.get("PGDATABASE", "s1bench")
CORPUS = sys.argv[1]
OUT = sys.argv[2]
REPEAT = 5

rows = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
random.seed(20260821)
titles = [r["title"] for r in rows if len(r["title"]) >= 8]
word_q, sub_q = [], []
for t in random.sample(titles, min(120, len(titles))):
    words = [w for w in t.split() if len(w) >= 3]
    if words:
        word_q.append(random.choice(words))
    long_words = [w for w in t.split() if len(w) >= 5]
    if long_words:
        w = random.choice(long_words)
        start = random.randint(1, len(w) - 4)
        sub_q.append(w[start:start + 3])
word_q = sorted({q for q in word_q if len(q) >= 3})[:60]
sub_q = sorted({q for q in sub_q if len(q) >= 3})[:60]


def esc(s: str) -> str:
    return s.replace("'", "''")


HELPER = r"""
SET jit = off;
CREATE OR REPLACE FUNCTION explain_ms(q text) RETURNS float8 AS $fn$
DECLARE plan jsonb;
BEGIN
  EXECUTE 'EXPLAIN (ANALYZE, FORMAT JSON, TIMING ON) ' || q INTO plan;
  RETURN (plan -> 0 ->> 'Execution Time')::float8;
END
$fn$ LANGUAGE plpgsql;
"""

PATHS = {
    "seqscan_ilike": ("SET LOCAL enable_bitmapscan=off; SET LOCAL enable_indexscan=off;",
                      "SELECT id FROM docs WHERE txt ILIKE ''%%%s%%'''"),
    "pg_trgm_gin": ("SET LOCAL enable_seqscan=off;",
                    "SELECT id FROM docs WHERE txt ILIKE ''%%%s%%'''"),
    "fts_simple": ("SET LOCAL enable_seqscan=off;",
                   "SELECT id FROM docs WHERE to_tsvector(''simple'', txt) "
                   "@@ plainto_tsquery(''simple'', ''%s'')'"),
}

lines = [HELPER]
index: list[tuple[str, str, str]] = []
for label, queries in (("word", word_q), ("substring", sub_q)):
    for q in queries:
        for path, (setup, tpl) in PATHS.items():
            inner = ("'" + tpl) % esc(q)
            for _ in range(REPEAT):
                lines.append("BEGIN; %s SELECT explain_ms(%s); COMMIT;" % (setup, inner))
                index.append((label, path, q))

script = "/tmp/s1_bench_time.sql"
with open(script, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines) + "\n")

r = subprocess.run([PSQL, "-h", SOCK, "-p", PORT, "-d", DB, "-t", "-A", "-q",
                    "-v", "ON_ERROR_STOP=1", "-f", script],
                   capture_output=True, text=True, encoding="utf-8")
if r.returncode != 0:
    print(r.stderr[:3000])
    raise SystemExit(1)

vals = [x.strip() for x in r.stdout.split("\n") if x.strip()]
vals = [v for v in vals if v.replace(".", "", 1).replace("e-", "", 1).isdigit()]
if len(vals) != len(index):
    print("값 %d개 / 기대 %d개 — 파싱이 어긋났다" % (len(vals), len(index)))
    print(r.stdout[:600])
    raise SystemExit(1)

acc: dict[tuple[str, str, str], list[float]] = {}
for (label, path, q), v in zip(index, vals):
    acc.setdefault((label, path, q), []).append(float(v))

out: dict = {"repeat": REPEAT, "unit": "ms (서버 Execution Time, 질의별 최소값)", "sets": {}}
for label in ("word", "substring"):
    out["sets"][label] = {}
    for path in PATHS:
        best = sorted(min(v) for (lb, p, _q), v in acc.items() if lb == label and p == path)
        out["sets"][label][path] = {
            "n": len(best),
            "p50_ms": round(statistics.median(best), 3),
            "p95_ms": round(best[max(0, int(len(best) * 0.95) - 1)], 3),
            "max_ms": round(best[-1], 3),
            "mean_ms": round(statistics.mean(best), 3),
        }
    print("[%s]" % label)
    for path, v in out["sets"][label].items():
        print("  %-14s n=%d p50=%.3fms p95=%.3fms max=%.3fms"
              % (path, v["n"], v["p50_ms"], v["p95_ms"], v["max_ms"]))

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT)
