# -*- coding: utf-8 -*-
"""S1 / P-03 (A) — 한국어 키워드 검색: `pg_trgm` GIN vs PG FTS(simple).

## 무엇을 결정하는가

R5. 지금 검색은 SQLite FTS5 `tokenize='trigram'` 이다. PG 기본 `to_tsvector` 는 한국어를
**공백으로만** 쪼개므로 「접근통제」를 「통제」로 못 찾는다 — 0030 에서 이미 기각한
`unicode61` 의 실패 모드와 같다. `pg_trgm` GIN 이 그 직접 대체물인지를 **실 Corpus 로** 잰다.

## 정답은 무엇인가

`ILIKE '%q%'` 전량 스캔이 **정의상 정답**이다(부분일치의 의미 그대로). 각 경로의 recall 은
그 집합을 얼마나 되찾는가로 잰다.

표준 라이브러리만 쓴다 — psycopg 없이 `psql` 을 통해 SQL 을 던진다.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys
import time

PSQL = os.environ["PSQL"]
SOCK = os.environ["PGSOCK"]
PORT = os.environ.get("PGPORT", "55432")
DB = os.environ.get("PGDATABASE", "s1bench")
CORPUS = sys.argv[1] if len(sys.argv) > 1 else "corpus.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "bench_text.json"


def sql(text: str, *, quiet: bool = True) -> str:
    cmd = [PSQL, "-h", SOCK, "-p", PORT, "-d", DB, "-v", "ON_ERROR_STOP=1",
           "-t", "-A", "-F", "\t", "-c", text]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("SQL FAILED:", text[:160])
        print(r.stderr[:2000])
        raise SystemExit(1)
    return r.stdout


def sql_file(path: str) -> str:
    cmd = [PSQL, "-h", SOCK, "-p", PORT, "-d", DB, "-v", "ON_ERROR_STOP=1", "-f", path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stderr[:2000])
        raise SystemExit(1)
    return r.stdout


rows = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
print("corpus rows: %d" % len(rows))

# ── 적재 ──────────────────────────────────────────────────────────────────
sql("""
DROP TABLE IF EXISTS docs;
CREATE TABLE docs (
  id text PRIMARY KEY,
  kind text NOT NULL,
  title text NOT NULL DEFAULT '',
  body  text NOT NULL DEFAULT '',
  txt   text NOT NULL DEFAULT ''
);
""")
copy_path = "/tmp/s1_docs.tsv"
with open(copy_path, "w", encoding="utf-8", newline="\n") as fh:
    for r in rows:
        def clean(s: str) -> str:
            return (s or "").replace("\\", "\\\\").replace("\t", " ").replace("\n", " ").replace("\r", " ")
        fh.write("\t".join([r["id"], r["kind"], clean(r["title"]),
                            clean(r["body"]), clean(r["text"])]) + "\n")
sql("\\copy docs FROM '%s' WITH (FORMAT text)" % copy_path)
print("loaded:", sql("SELECT count(*) FROM docs").strip())

# ── 인덱스 ────────────────────────────────────────────────────────────────
def timed(stmt: str) -> float:
    t = time.perf_counter()
    sql(stmt)
    return (time.perf_counter() - t) * 1000


build = {}
build["gin_trgm"] = timed(
    "DROP INDEX IF EXISTS docs_txt_trgm; "
    "CREATE INDEX docs_txt_trgm ON docs USING gin (txt gin_trgm_ops);")
build["gin_fts_simple"] = timed(
    "DROP INDEX IF EXISTS docs_txt_fts; "
    "CREATE INDEX docs_txt_fts ON docs USING gin (to_tsvector('simple', txt));")
sql("ANALYZE docs;")
print("index build ms:", build)

size = {}
for name in ("docs_txt_trgm", "docs_txt_fts"):
    size[name] = sql("SELECT pg_size_pretty(pg_relation_size('%s'))" % name).strip()
size["table"] = sql("SELECT pg_size_pretty(pg_relation_size('docs'))").strip()
print("sizes:", size)

# ── 질의 만들기 ───────────────────────────────────────────────────────────
# 두 갈래로 만든다:
#  (a) 어절 경계에 맞는 질의   — FTS 가 원리상 찾을 수 있는 것
#  (b) 어절 **안쪽** 부분 문자열 — FTS5 trigram 이 하던 일. PG FTS 는 원리상 못 찾는다.
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
print("질의 — 어절 %d개 · 어절내부 %d개" % (len(word_q), len(sub_q)))


def q_esc(s: str) -> str:
    return s.replace("'", "''")


def ids(stmt: str) -> set[str]:
    return {x for x in sql(stmt).split("\n") if x.strip()}


def measure(stmt_tpl: str, queries: list[str], repeat: int = 3) -> tuple[dict, list[float]]:
    """(질의 -> 결과 집합, 지연 목록ms)"""
    got, lat = {}, []
    for q in queries:
        stmt = stmt_tpl % {"q": q_esc(q)}
        best = None
        for _ in range(repeat):
            t = time.perf_counter()
            res = ids(stmt)
            ms = (time.perf_counter() - t) * 1000
            best = ms if best is None else min(best, ms)
        got[q] = res
        lat.append(best)
    return got, lat


TRUTH = "SELECT id FROM docs WHERE txt ILIKE '%%%(q)s%%'"
TRGM = ("SET LOCAL enable_seqscan = off; "
        "SELECT id FROM docs WHERE txt ILIKE '%%%(q)s%%'")
FTS = ("SELECT id FROM docs WHERE to_tsvector('simple', txt) "
       "@@ plainto_tsquery('simple', '%(q)s')")

result = {"corpus_rows": len(rows), "index_build_ms": build, "sizes": size,
          "queries": {"word": word_q, "substring": sub_q}, "sets": {}}

for label, queries in (("word", word_q), ("substring", sub_q)):
    truth, t_lat = measure(TRUTH, queries)
    trgm, g_lat = measure(TRGM, queries)
    fts, f_lat = measure(FTS, queries)

    def recall(got: dict) -> float:
        num = den = 0
        for q in queries:
            den += len(truth[q])
            num += len(truth[q] & got[q])
        return (num / den) if den else 1.0

    def hitrate(got: dict) -> float:
        """정답이 1건 이상인 질의 중, 하나라도 되찾은 비율 — 사용자가 «검색이 죽었다» 고 느끼는 축."""
        live = [q for q in queries if truth[q]]
        return sum(1 for q in live if truth[q] & got[q]) / len(live) if live else 1.0

    result["sets"][label] = {
        "n_queries": len(queries),
        "avg_truth_hits": statistics.mean(len(truth[q]) for q in queries),
        "seqscan_ilike": {"recall": 1.0, "p50_ms": statistics.median(t_lat),
                          "p95_ms": sorted(t_lat)[int(len(t_lat) * 0.95) - 1]},
        "pg_trgm_gin": {"recall": recall(trgm), "hitrate": hitrate(trgm),
                        "p50_ms": statistics.median(g_lat),
                        "p95_ms": sorted(g_lat)[int(len(g_lat) * 0.95) - 1]},
        "fts_simple": {"recall": recall(fts), "hitrate": hitrate(fts),
                       "p50_ms": statistics.median(f_lat),
                       "p95_ms": sorted(f_lat)[int(len(f_lat) * 0.95) - 1]},
    }
    r = result["sets"][label]
    print("\n[%s] 질의 %d개 · 정답 평균 %.1f건" % (label, r["n_queries"], r["avg_truth_hits"]))
    for k in ("seqscan_ilike", "pg_trgm_gin", "fts_simple"):
        v = r[k]
        print("  %-14s recall=%.3f hit=%s p50=%.1fms p95=%.1fms"
              % (k, v["recall"], ("%.3f" % v["hitrate"]) if "hitrate" in v else "1.000",
                 v["p50_ms"], v["p95_ms"]))

# 인덱스가 실제로 쓰이는지 — 「빠른데 인덱스를 안 탔다」를 구별한다.
plan = sql("EXPLAIN (ANALYZE, BUFFERS) SELECT id FROM docs WHERE txt ILIKE '%%%s%%'"
           % q_esc(sub_q[0] if sub_q else "통제"))
result["explain_trgm"] = plan
print("\nEXPLAIN (trgm 경로):")
print(plan[:900])

json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nwrote %s" % OUT)
