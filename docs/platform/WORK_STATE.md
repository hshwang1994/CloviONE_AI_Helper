# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-21** (S2)
- phase: **A — 기반**
- session: **S2 완료.** 다음은 **S3 — Product Identity · Hostname · TLS**
- branch: `ui/mui-migration`
- last_stable_commit: **`95a89189`** — 아직 **S1 의 마지막 커밋**이다.
  **`check_test_strength.py` 가 이 값을 기준선으로 읽는다** — 그래서 이 줄은 장식이 아니다.
  S2 의 시험 변경이 그 기준선과 비교돼야 하므로, **S2 본체를 커밋한 직후** 후속 커밋
  하나로 이 값을 S2 해시로 올린다(S1 이 `2b890846` 로 한 것과 같은 순서). 그래야
  **커밋된 시험 약화**가 다음 세션에 보인다
- s1_commit: `95a89189`
- working_tree: clean
- **제품 코드가 크게 바뀌었다** — S1 과 정반대다. `app/**` · `alembic/**` · `tests/**` ·
  `deploy/**` · `scripts/**` 가 전부 움직였다. 앱은 이제 **PostgreSQL 로만 뜬다**

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다**

이 구분이 다음 세션이 가장 먼저 알아야 하는 것이다.

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001_pg_baseline` 하나가 70 표 · **256 인덱스** · 부트스트랩 5행을 만든다 |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |

즉 **지금 운영 서버에 이 코드를 올리면 빈 DB 로 뜬다.** 이관은 S13(Dry Run) → S14(Cutover)의
일이고, 그 사이의 Session(S3~S12)은 새 스키마 위에서 개발한다. `alembic/legacy_sqlite/` 61개를
지우지 않은 이유가 이것이다 — S13 이 운영 SQLite 를 읽을 때 그 표의 내력이 필요하다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **이식 완료.** 앱·마이그레이션·시험이 전부 PG16 위에서 돈다. 인덱스 파라미터·임베딩 모델 확정(D-209~D-212). **서버 시스템 설치는 아직 0** — S4 Installer Stage 6·7 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ → S4(설치) |
| **SQLite 제거** | **Runtime 의존 0.** `app/**` 에 `sqlite3` import 0. 다만 **운영 데이터는 아직 SQLite 에 있다**(위 절) | Runtime 0 + 데이터 이관 완료 | S2 ✅ → S13·S14(데이터) |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110 | Notion Runtime 의존 0, 데이터는 PG 로 이관 | S13(Dry Run) → S14(Cutover) |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | **기본형 완료.** `pg_dump -Fc` + 체크섬 + `pg_restore --list` + **임시 DB 실복원**. 실복원을 못 하면 `verified` 로 올리지 않고 «구조만 확인» 이라고 말한다(D-204) | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ → S12(운영) |

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착시켰다.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 실행목록 13항 중 **12항 이행**(10번은 계획대로 S6·S7).
  상세는 [`INVENTORY/08_SQLITE.md`](INVENTORY/08_SQLITE.md), 결정은 **D-215~D-221**.

### S2 가 실제로 한 것

| | |
|---|---|
| **스키마** | `alembic/versions/` 61개 → `alembic/legacy_sqlite/`(비활성). `0001_pg_baseline` 하나가 **70 표 · 256 인덱스 · jsonb 37 · identity 3 · 부분유니크 4 · GIN trgm 2 · 부트스트랩 5행** |
| **충돌 분류** | `is_write_conflict` → `is_serialization_conflict` / `is_unique_violation` / `is_insert_race`. **40 호출부 · 24 모듈 전수 감사** → 재시도 9 · insert-race 31. FK·NOT NULL·CHECK 는 이제 **그대로 올라간다** |
| **검색** | FTS5 가상 표 + SQLite 트리거 → **`gin_trgm_ops` 인덱스**(D-209). 2단 질의가 1단이 됐고 트리거로 지키던 성질을 인덱스가 준다 |
| **큐** | claim 에 **`FOR UPDATE SKIP LOCKED`**. 워커를 늘리면 실제로 병렬이 된다 |
| **`--workers`** | **1 → 4.** rate limit 을 `rate_limit_buckets` 표로, 잠금 5자리를 advisory lock 으로, 설정 캐시를 TTL 갱신으로 **먼저** 옮긴 뒤 올렸다(D-192·D-216·D-217) |
| **백업** | `sqlite_backup.py` 삭제 → `pg_backup.py`. cron/rollback 스크립트도 함께 옮겼다 — 안 옮기면 **매일 밤 DB 없는 백업이 «성공» 으로 쌓인다** |
| **기동 순서** | systemd 유닛 셋에 `After=/Wants=postgresql.service` 를 걸었다. SQLite 시절엔 DB 가 파일이라 기다릴 서비스가 없었다 — **S2 가 만든 의존이라 S2 가 건다**. `After=` 만으로 접속 가능이 보장되지는 않으므로 **기동 시 PG 준비 대기**는 INSTALLATION §6 대로 S4 가 넣는다 |
| **시험** | 파일 복사 하네스 → **2계층**(기본 되감기 / `@pytest.mark.real_db` 전용 DB, D-218). **3,229건 중 320건(9.9%)** 이 전용 DB 계층이다 — D-190 이 예상한 «동시성 약 40개 + 마이그레이션» 과 같은 크기다 |

### S2 가 드러낸 것 — 계획에 없던 발견

**옛 체인이 만들고 안 지운 이름 88개 중 10개가 모델에 없었다.** 기준선을 모델에서 생성하는
순간 그 열이 조용히 사라진다 — 부분 유니크 셋, `ix_jobs_claim`, 뜨거운 질의 인덱스 여섯.
**셋 다 오류를 내지 않는다**: 데이터가 이상해지거나, 큐가 밀리거나, 그냥 느려질 뿐이다.

D-189 는 `sqlite_where=` 가 PG 에서 무시되는 경로를 경고했는데, **모델/마이그레이션
어긋남**이라는 두 번째 경로가 더 넓었다. 그리고 **처음 만든 검사가 그중 여섯을 놓쳤다** —
좁은 정규식이 0041 의 「목록 변수를 도는」 형태를 못 봤고, 시험이 빨간불로 잡아냈다.

열 개 다 모델에 올렸고 두 겹으로 지킨다:
`test_baseline_carries_every_legacy_index.py`(전수 대조 + 검사 자기 확인 + 이름 회귀)와,
옛 왕복 시험 6개를 다시 쓴 `test_migration_00*.py`.

계획 추정치 정정 셋도 **D-221** 에 적었다(호출부 115→40, `*_json` 27→37, 부분유니크 3→4).

**두 번째 발견: 제품은 옮겼는데 그 제품을 검사하는 도구가 안 옮겨진 자리가 둘 있었다.**
실행 코드에서 `sqlite` 를 전수로 훑어 찾았다(주석·설명 문장을 걷어내고 토큰만 본다 — 이
저장소는 «왜 이렇게 됐는가» 를 주석에 많이 적어 두어서, 문자열만 세면 129건이 나오고
그중 진짜는 몇 건 없다).

| 무엇 | 왜 위험한가 |
|---|---|
| `deploy/00-precheck.sh` 가 `sqlite3` 설치를 모의하고 있었다 | 설치 전 점검이 **초록인데 설치가 패키지에서 죽는다.** 사전 점검의 존재 이유가 정확히 그것을 미리 보는 것이다. 설치 스크립트가 실제로 까는 목록(`postgresql-client-16`·`rsync` 포함)과 같게 맞췄다 |
| `scripts/restore_rehearsal.py` 에 죽은 SQLite 구현 340줄이 남아 있었다 | 이미 지운 `app.backups.sqlite_backup` 을 import 한다. 아무도 안 부르지만, 부르는 순간 `ImportError` 이고 「SQLite 의존 0」이 거짓이 된다 |

리허설 자체의 이식은 계획대로 S12 지만, 8단계 중 **첨부 파일 확인(BKP-02)만은 살려 뒀다** —
그것은 저장소 종류를 타지 않는 질문이라 PG 로 옮겨 시험까지 함께 남겼다. 옮기면서 PG 에만
있는 함정 하나를 새로 못 박았다: 문장 하나가 실패하면 트랜잭션 전체가 중단되므로, 조회를
savepoint 로 감싸지 않으면 **표 하나가 없을 뿐인데 멀쩡한 표까지 「조회 실패」로 보고된다.**
시험이 그것을 잡는지 반대 방향으로 확인했다(savepoint 를 빼면 `4 == 3` 으로 빨간불).

**세 번째 발견이 가장 무겁다: 이 저장소에는 «정의되지 않은 이름» 을 잡는 검사가 없다.**

S2 가 `POST /api/tickets/sync` 의 잠금을 advisory lock 으로 바꾸면서 **import 를 빼먹었다.**
문법도 맞고 모듈도 잘 실려서 `compileall` 도 `pytest --collect-only` 도 전부 초록이었다.
드러난 것은 **그 라우트를 실제로 부르는 시험 세 개**가 전 회귀 마지막 청크에서 빨간불을
냈을 때다 — 그 시험이 없었으면 운영에서 500 이다.

한 건을 고치고 끝내지 않고 `pyflakes` 로 전 저장소를 훑었다. 결과:

| | |
|---|---|
| S2 가 만든 F821 | **1자리**(`tickets/router.py` — 고쳤다) |
| 이미 있던 F821 | **5자리** — 그중 `tickets/service.py:1369` 의 `split_names` 는 **닿으면 `NameError` 인 진짜 결함**이다(`0a082f36`, 2026-08-07). 나머지는 문자열 주석 하나와 S1 도구 셋 |
| S2 가 고아로 만든 import | 11자리 — 지웠다 |
| 이미 있던 안 쓰이는 import | 22자리 — 손대지 않았다 |

검사를 `static_checks.sh` 에 넣는 것과 남은 F821 다섯은 **범위 밖이라 `BACKLOG.md`
P-09b · P-09c 로 넘겼다**(개발 의존 추가가 따라온다). 다만 **이 세션이 그것 때문에 한 번
당했다는 사실**은 여기 남긴다 — 다음에 같은 판단을 할 사람이 근거로 쓸 수 있게.

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

전부 **PostgreSQL 16 위에서** 돌렸다. S2 는 거의 모든 층을 건드렸으므로 인용 없이 전 회귀를
새로 돌렸다(E1 의 지문이 하나도 같지 않다).

| 대상 | 결과 |
|---|---|
| `scripts/run_full_regression.sh` (unit · regression · security · integration 4청크) | **FULL_REGRESSION_OK** — 일곱 스위트 전부 통과(**3,229건 · 29분 37초**). 이 결과를 낸 소스 트리는 `d8fadd78` 이고, 그 뒤 바뀐 것은 이 문서뿐이다 |
| `scripts/static_checks.sh` | **S2 가 넣은 것은 전부 통과.** `check_test_strength.py` 는 **TEST_STRENGTH_OK**(기준선 `95a89189` 대비 시험 파일 87개). 전체는 **빨간불이고 그 원인은 S2 가 아니다** — 아래 절 참조 |
| `alembic upgrade head` → 빈 DB | 71 표(앱 70 + `alembic_version`) · **256 인덱스** · jsonb 37 · identity 3 · 부분유니크 4 · GIN trgm 2 · 부트스트랩 5행 |
| `alembic revision --autogenerate` (drift 확인) | **빈 diff** — 모델과 기준선이 정확히 일치한다 |
| **검색 인덱스가 실제로 쓰이는가** | `gin_trgm_ops` 두 개가 `ILIKE` 를 **받는다**(BitmapOr, 6.4ms 대 seq 23.7ms). 다만 PG 가 `ILIKE '%…%'` 선택도를 추정 못 해(20,000행에서 추정 19,998 · 실제 435) 작은 표에서는 seq scan 을 고른다 — **현재 색인 규모(1~2천 행)에서는 그게 맞는 판단**이다. 코퍼스가 자란 뒤 느려지면 인덱스가 아니라 통계·비용 파라미터를 본다. 원장 [`EVIDENCE/S2/search_gin_index_is_usable.txt`](EVIDENCE/S2/search_gin_index_is_usable.txt) |
| **실 앱 기동**(하네스 아닌 제품 경로) | 빈 PG → `alembic upgrade head` → `create_app` → `/healthz` 200 · `/readyz` 200 · `/login` 200 · 틀린 비밀번호 401. **그 401 이 세션을 롤백했는데도 rate limit 토큰은 10→9 로 남았다**(D-217 이 실 경로에서 성립). 원장 [`EVIDENCE/S2/app_boots_on_postgres.txt`](EVIDENCE/S2/app_boots_on_postgres.txt) |
| **`pg_dump` 왕복 실측** (테스트 서버 PG 16.15) | 500행 덤프→복원 성공. **부분 유니크의 `WHERE` · GIN trgm · jsonb · identity 전부 살아서 복원**됐고, 손상된 아카이브는 `pg_restore --list` 가 거부했다. 원장 [`EVIDENCE/S2/pg_backup_roundtrip.txt`](EVIDENCE/S2/pg_backup_roundtrip.txt) |
| frontend `npx vitest run` | **인용** — `frontend/**` diff 0 (지문 `60f8fafb`) |
| runner `test_assistant.py` | **인용** — `runner/**` diff 0 (지문 `60f8fafb`) |

### ⚠️ `static_checks.sh` 전체는 지금 빨간불이다 — **S2 가 만든 것이 아니다**

S1 이후 UI 커밋 둘이 남긴 것이고, S2 는 두 파일 다 건드리지 않았다(`git blame` 으로 확인):

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) **7건** | `4dd62181` — `Integrity.jsx` · `AccentPicker.jsx` · `Sprint.jsx` · registry 4곳 |
| `tokens.css` 가 `theme.js` 와 어긋남 | `dac17928` 이 토큰 정본(`frontend/src/ui/theme.js`)을 고치고 `node scripts/generate_design_tokens.mjs` 를 안 돌렸다 |

**S2 가 넣은 문구 하나(백업 복원 안내의 em 대시)는 이번에 고쳤다.** 나머지 둘은 범위 밖이라
손대지 않고 `BACKLOG.md` **P-09a** 로 Owner(UI 축)에 넘긴다(E9). 다만 **고칠 때까지 모든
Session 이 빨간 정적 검사를 본다** — 다음 세션이 이것을 자기 회귀로 오해하지 않도록 여기 적는다.

## NOW

**S2 는 끝났다.** 이제 제품이 PostgreSQL 위에서 돈다 — 그리고 그 사실을 **숨길 수 없다**:
`sqlite://` 를 주면 기동을 거부한다. 조용히 파일 하나로 되돌아가는 경로를 없애는 것이
이 세션에서 가장 중요한 한 줄이었다.

`--workers` 를 1에서 4로 올린 것이 이 전환의 **보상**이다. 대가가 아니다 — 못 올리던 이유가
성능이 아니라 「방어가 프로세스 메모리 안에 있어서」였고, 그것을 옮기는 일이 곧 PG 이식이었다.

## NEXT — 다음 시작점: S3 (요청 시)

**S3 = Product Identity · Hostname · TLS.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1.

S2 가 S3 에게 넘기는 것:

1. **DB 는 신경 쓸 것이 없다.** S3 는 nginx·TLS·cookie domain·QA base URL 축이다
2. `scripts/ui_qa/tls.py` 의 `DEFAULT_VERIFY = True` 한 줄이면 19개 프로브가 함께 켜진다
   (S1 이 스위치를 만들어 뒀다)
3. 시험을 돌리려면 **PostgreSQL 이 필요하다.** 아래 「입력」의 접속 정보 참조

## RISK — 지금 살아 있는 것

전체 18건은 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12. **S2 가 소유하던 셋이 닫혔다.**

| # | Risk | 상태 |
|---|---|---|
| ~~R1~~ | `is_write_conflict` 가 PG 에서 진짜 제약 위반을 재시도로 감춘다 | **해소** — 둘로 쪼개고 40 호출부 전수 감사. **음성 테스트**(`tests/security/test_conflict_classification.py`)가 실제 PG 의 FK 위반이 어느 통에도 안 들어감을 증명한다. 40곳 전부의 분류는 [`EVIDENCE/S2/conflict_reclassification_audit.txt`](EVIDENCE/S2/conflict_reclassification_audit.txt) (D-191) |
| ~~R2~~ | 부분 유니크 인덱스가 PG 에서 전체 유니크가 된다 | **해소** — `postgresql_where=` 4개. 그리고 **셋은 모델에 아예 없었다**(D-221) |
| ~~R3~~ | 동시성 테스트가 거짓 초록이 된다 | **해소** — 2계층 하네스 + `real_db` 마커. `db_url` 은 마커 없이 쓰면 **실패한다** (D-218) |
| ~~R4~~~~R7~~ | (S1 이 닫음) | 해소 |

다음 Session 이 실제로 만나는 것:

| # | Risk | Owner |
|---|---|---|
| R17 | pgvector 검색 품질 | 인덱스 파라미터는 확정(D-210). 남은 것은 S10 의 하이브리드 가중치 |
| — | **AI 쿼터 잠금이 커넥션을 하나 더 쓴다** — 그 블록 안에 외부 AI 호출(수 초)이 있어 동시 AI 요청 수만큼 유휴 커넥션이 잡힌다. 기본 풀 15 에서 **동시 7~8을 넘으면 마른다**(증상은 오류가 아니라 «느리다»). 지금은 rate limiter 가 그 수를 눌러 준다 | S4(풀·`max_connections` 사이징) |
| — | **운영 데이터가 아직 SQLite 에 있다** | S13 · S14 (위 「코드는 옮겼고 데이터는 아직」 절) |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **시험용 PostgreSQL** | **필요하다.** 시험은 `CLOVIR_TEST_PG_URL` 로 붙고 기본값은 로컬 개발 컨테이너다. 그 서버에 **DB 를 만들고 지울 권한**이 있어야 한다(하네스가 `CREATE DATABASE … TEMPLATE` 를 쓴다). 개발 머신에서 쓴 것: `docker run -d --name clovir-s2-pg -e POSTGRES_USER=cloviradmin -e POSTGRES_PASSWORD=s2devpw -e POSTGRES_DB=clovir -p 55433:5432 postgres:16-alpine`. 시험 DB 이름에 프로세스 id 가 들어가므로 **두 개를 동시에 돌려도 안 부딪힌다** |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다** — 백업 왕복은 테스트 서버에서 확인했다(위 원장). 배포 대상 Ubuntu 에는 PG 와 함께 깔린다. `PG_BIN_DIR` 를 **비워 두면 안 된다**: `PATH` 의 `pg_dump` 가 서버보다 낮은 버전이면 실행을 거부한다 |
| **테스트 서버 sudo** | **쓸 수 있다** — `10.100.64.71` 한정. S1 의 사용자 공간 PG 는 `~/s1pg/` 에 있고 `pg_ctl -D ~/s1pg/data start` 로 띄운다(S2 가 실제로 그렇게 띄워 백업 왕복을 쟀다). **시스템 설치는 S4 Installer Stage 6·7** 의 일이다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo 필요), 개발 사본은 `var/secrets/`(gitignore). **네 파일은 같은 값이다.** 상세 [`INVENTORY/07_NOTION.md`](INVENTORY/07_NOTION.md). **S13 의 본문 재수집이 이걸 쓴다** |
| **운영 SQLite 읽기** | **가능하다.** 원장은 [`EVIDENCE/S1/varchar_prod.json`](EVIDENCE/S1/varchar_prod.json). S13 이 이관 원본으로 읽는다 |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 20개 Project Key 명명 | **S6 에서** 초안표 제시 → 사용자 확인 → 적용. **확정 전 재채번 없음** (U11) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음. **Core Migration 은 이 결정과 무관하게 진행** (U19) |
| GitLab Repository 주소·자격증명 | **없어도 S4 는 진행한다** (Remote 중립 + 오프라인 Bundle) (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
