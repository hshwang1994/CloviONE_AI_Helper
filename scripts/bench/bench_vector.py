# -*- coding: utf-8 -*-
"""S1 / P-03 (B) — pgvector: exact vs HNSW vs IVFFlat.

## 무엇을 결정하는가

`m` · `ef_construction` · `ef_search` · `lists`(+`probes`). 그리고 «지금 규모에서 인덱스가
필요하긴 한가» 도 함께 답한다 — 1,169벡터에서 exact 가 이미 충분하면 그것이 답이다.

## 정답은 무엇인가

**인덱스 없는 exact 스캔**이 정답이다. ANN 의 recall@10 은 그 집합을 얼마나 되찾는가다.
질의는 Corpus 벡터에서 뽑되 **자기 자신을 뺀다**(자기 자신은 항상 1위라 recall 을 부풀린다).

## 규모

지금 Corpus 는 1,169건이다. S13 이 Notion 본문을 다시 실어 오고 청킹하면 수만 건이 된다.
그래서 **원본 벡터에 작은 잡음을 더해 늘린 판**에서도 잰다 — 잡음판의 recall 숫자는
«진짜 recall» 이 아니라 **인덱스 파라미터의 상대 비교**용이고, 그 사실을 결과에 적는다.
"""
from __future__ import annotations

import json
import math
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
TSV = sys.argv[1]
DIM = int(sys.argv[2])
OUT = sys.argv[3]
SCALE_N = int(sys.argv[4]) if len(sys.argv) > 4 else 50000


def psql(text: str) -> str:
    r = subprocess.run([PSQL, "-h", SOCK, "-p", PORT, "-d", DB, "-t", "-A", "-q",
                        "-v", "ON_ERROR_STOP=1", "-c", text],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("SQL FAILED:", text[:200])
        print(r.stderr[:2000])
        raise SystemExit(1)
    return r.stdout


def psql_script(body: str) -> str:
    path = "/tmp/s1_vec.sql"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    r = subprocess.run([PSQL, "-h", SOCK, "-p", PORT, "-d", DB, "-t", "-A", "-q",
                        "-v", "ON_ERROR_STOP=1", "-f", path],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(r.stderr[:3000])
        raise SystemExit(1)
    return r.stdout


psql("""
SET jit = off;
CREATE OR REPLACE FUNCTION explain_ms(q text) RETURNS float8 AS $fn$
DECLARE plan jsonb;
BEGIN
  EXECUTE 'EXPLAIN (ANALYZE, FORMAT JSON, TIMING ON) ' || q INTO plan;
  RETURN (plan -> 0 ->> 'Execution Time')::float8;
END
$fn$ LANGUAGE plpgsql;
""")

print("== 적재 ==")
psql("DROP TABLE IF EXISTS vecs; CREATE TABLE vecs (id text PRIMARY KEY, v vector(%d));" % DIM)
psql("\\copy vecs FROM '%s' WITH (FORMAT text)" % TSV)
n_base = int(psql("SELECT count(*) FROM vecs").strip())
print("base rows:", n_base)

random.seed(20260821)
all_ids = [x for x in psql("SELECT id FROM vecs").split("\n") if x.strip()]
qids = random.sample(all_ids, min(50, len(all_ids)))
result: dict = {"dim": DIM, "base_rows": n_base, "queries": len(qids), "scales": {}}


def topk_sql(qid: str, k: int = 10) -> str:
    return ("SELECT id FROM vecs WHERE id <> '%s' "
            "ORDER BY v <=> (SELECT v FROM vecs WHERE id = '%s') LIMIT %d" % (qid, qid, k))


def latencies(prefix: str) -> list[float]:
    lines = ["BEGIN; %s SELECT explain_ms($q$%s$q$); COMMIT;" % (prefix, topk_sql(q))
             for q in qids]
    vals = [float(x) for x in psql_script("\n".join(lines)).split("\n") if x.strip()]
    vals.sort()
    return vals


def results_for(prefix: str) -> dict[str, list[str]]:
    got = {}
    for qid in qids:
        got[qid] = [x for x in psql("%s %s" % (prefix, topk_sql(qid))).split("\n") if x.strip()]
    return got


def stat(lat: list[float]) -> dict:
    return {"p50_ms": round(statistics.median(lat), 3),
            "p95_ms": round(lat[int(len(lat) * 0.95) - 1], 3),
            "max_ms": round(lat[-1], 3)}


def measure(n_rows: int) -> dict:
    out: dict = {"rows": n_rows, "exact": {}, "hnsw": [], "ivfflat": []}
    psql("DROP INDEX IF EXISTS vecs_hnsw; DROP INDEX IF EXISTS vecs_ivf; ANALYZE vecs;")
    out["exact"] = stat(latencies("SET LOCAL enable_seqscan=on;"))
    truth = results_for("")
    print("  exact  p50=%.2fms p95=%.2fms" % (out["exact"]["p50_ms"], out["exact"]["p95_ms"]))

    def sweep(kind: str, create: str, guc: str, values: list[int], label: dict) -> None:
        idx = "vecs_hnsw" if kind == "hnsw" else "vecs_ivf"
        t0 = time.perf_counter()
        psql(create)
        build_s = time.perf_counter() - t0
        psql("ANALYZE vecs;")
        size = psql("SELECT pg_size_pretty(pg_relation_size('%s'))" % idx).strip()
        key = guc.split(".")[-1]
        for val in values:
            lat = latencies("SET LOCAL enable_seqscan=off; SET LOCAL %s=%d;" % (guc, val))
            got = results_for("SET %s=%d; SET enable_seqscan=off;" % (guc, val))
            hit = sum(len(set(got[q]) & set(truth[q])) for q in qids)
            tot = sum(len(truth[q]) for q in qids)
            row = dict(label)
            row.update({key: val, "recall@10": round(hit / tot, 4) if tot else 1.0,
                        "build_s": round(build_s, 1), "index_size": size})
            row.update(stat(lat))
            out[kind].append(row)
            print("  %-8s %-34s recall=%.3f p50=%.2fms p95=%.2fms (build %.0fs, %s)"
                  % (kind, "%s %s=%d" % (json.dumps(label, ensure_ascii=False), key, val),
                     row["recall@10"], row["p50_ms"], row["p95_ms"], build_s, size))
        psql("DROP INDEX IF EXISTS %s;" % idx)

    for m, efc in ((16, 64), (16, 200), (32, 200)):
        sweep("hnsw",
              "DROP INDEX IF EXISTS vecs_hnsw; CREATE INDEX vecs_hnsw ON vecs "
              "USING hnsw (v vector_cosine_ops) WITH (m=%d, ef_construction=%d);" % (m, efc),
              "hnsw.ef_search", [10, 40, 100, 200], {"m": m, "ef_construction": efc})
    for lists in sorted({max(10, int(math.sqrt(n_rows))), max(10, n_rows // 1000),
                         max(10, n_rows // 200)}):
        sweep("ivfflat",
              "DROP INDEX IF EXISTS vecs_ivf; CREATE INDEX vecs_ivf ON vecs "
              "USING ivfflat (v vector_cosine_ops) WITH (lists=%d);" % lists,
              "ivfflat.probes", [1, 5, 10, 20], {"lists": lists})
    return out


print("\n== 규모 1: 실 Corpus (%d) ==" % n_base)
result["scales"]["real_%d" % n_base] = measure(n_base)

reps = max(1, SCALE_N // n_base)
if reps > 1:
    print("\n== 규모 2: %d 배 증폭 ==" % reps)
    psql("""
INSERT INTO vecs (id, v)
SELECT b.id || '#' || g,
       (SELECT array_agg(GREATEST(-1.0, LEAST(1.0, x + (random()-0.5)*0.06)))::vector
        FROM unnest(b.v::real[]) AS x)
FROM vecs b, generate_series(1, %d) g
ON CONFLICT (id) DO NOTHING;
""" % (reps - 1))
    n_scaled = int(psql("SELECT count(*) FROM vecs").strip())
    print("scaled rows:", n_scaled)
    result["scales"]["scaled_%d" % n_scaled] = measure(n_scaled)
    result["scaled_note"] = ("증폭판은 원본 벡터 + 균등잡음(±0.03)이다. recall 절대값은 "
                             "«진짜 recall» 이 아니라 파라미터 상대 비교용이다.")

json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT)
