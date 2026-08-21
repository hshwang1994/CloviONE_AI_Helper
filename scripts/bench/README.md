# scripts/bench — S1 실측 하네스

**이 디렉터리는 제품 코드가 아니고 `static_checks.sh` 에도 들어가지 않는다.**
`docs/DECISIONS.md` **D-209~D-212** 의 숫자를 **다시 만들 수 있게** 남겨 둔 것이다.

숫자만 남기고 재는 방법을 버리면, 다음 사람은 그 숫자를 **믿거나 처음부터 다시 재는 것** 둘
중 하나만 할 수 있다. 그리고 대개 믿는다.

## 누가 이걸 다시 쓰는가

| Session | 왜 |
|---|---|
| **S10** | 융합 가중치를 **실제 relevance** 로 재조정한다(D-209 는 초기값만 준다). `bench_text.py` 가 그 A/B 자리다 |
| **S10** | S13 이 Notion 본문을 실어 온 뒤 **긴 문서로 임베딩 모델을 재검토**한다(D-211). `embed.py` · `quality.py` 를 그대로 쓴다 |
| **S2 · S13** | 벡터가 늘어 D-210 의 임계(384차원 ≈ 1.2만)를 넘을 때 `bench_vector.py` 로 인덱스 파라미터를 다시 확인한다 |

## 순서

```bash
# 0) 측정용 PG 를 띄운다 — sudo 없이 공식 .deb 를 홈에 전개한다.
#    시스템에는 아무것도 바꾸지 않는다. 실제 설치는 S4 Installer Stage 6·7 의 일이다.
bash scripts/bench/pg_userspace_bootstrap.sh          # 서버에서 실행
. ~/s1pg/env.sh
export PSQL="$PGHOME/usr/lib/postgresql/16/bin/psql" PGSOCK="$PGHOST"

# 1) Corpus 를 뽑는다 (개발 기계에서)
python scripts/bench/export_corpus.py var/web.sqlite3 corpus.jsonl

# 2) 한국어 키워드: pg_trgm GIN vs FTS(simple)  → D-209
python scripts/bench/bench_text.py corpus.jsonl bench_text.json          # recall
python scripts/bench/bench_text_time.py corpus.jsonl bench_text_time.json # 지연(서버 측정)

# 3) CPU 임베딩 모델  → D-211 · D-212
bash scripts/bench/setup_models.sh                    # ONNX 내려받기 (torch 없음)
. ~/s1bench/venv/bin/activate
QUERY_PREFIX="query: " DOC_PREFIX="passage: " \
  python scripts/bench/embed.py ~/s1bench/models/intfloat__multilingual-e5-small \
         e5-small corpus.jsonl emb.tsv bench_embed.json
python scripts/bench/quality.py corpus.jsonl bench_quality.json

# 4) pgvector 인덱스 스윕  → D-210
python3 scripts/bench/bench_vector.py emb.tsv 384 bench_vec.json 50000

# 5) VARCHAR(n) 감사  → D-214
python scripts/bench/varchar_audit.py var/web.sqlite3 varchar_audit.json
```

## 측정 규율 두 가지 (S1 이 밟아 보고 적는다)

1. **지연은 서버가 재게 한다.** 첫 판은 질의마다 `psql` 프로세스를 새로 띄워 재는 바람에
   세 경로가 전부 ~20ms 로 같게 나왔다 — 그건 PG 지연이 아니라 **프로세스 시작 시간**이었다
   (같은 실행의 `EXPLAIN` 은 0.23ms). **값이 전 표본에서 같으면 측정이 아니라 상수를 읽고
   있는 것이다.** 그래서 `explain_ms()` plpgsql 함수가 `Execution Time` 만 돌려준다.
2. **증폭한 데이터의 recall 은 절대값이 아니다.** `bench_vector.py` 의 50,000행은 원본에
   잡음을 더해 불린 것이라 근접 중복이 많다. **지연·빌드·크기는 유효하고 recall 은
   파라미터 사이 비교로만** 읽는다 — 그 한계를 결과 JSON 에도 적는다.

## 산출물

`docs/platform/EVIDENCE/S1/*.json` 이 2026-08-21 실행 결과다.
측정 환경은 `docs/DECISIONS.md` 의 「S1 실측 결정」 머리말에 적혀 있다.
