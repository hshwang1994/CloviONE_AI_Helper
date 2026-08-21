# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-21** (S1)
- phase: **A — 기반**
- session: **S1 완료.** 다음은 **S2 — PostgreSQL Foundation**
- branch: `ui/mui-migration`
- last_stable_commit: **`95a89189`** — **S1 의 마지막 안정 커밋**(= `s1_commit`).
  **`check_test_strength.py` 가 이 값을 기준선으로 읽는다** — 그래서 이 줄은 장식이 아니다.
  S2 는 여기서부터 비교되고, 끝날 때 자기 커밋 해시로 올린다. 그래야 **커밋된 시험 약화**가
  다음 세션에 보인다
- s1_commit: **`95a89189`** — S1 의 마지막 커밋(P-04 운영 재측정 반영). 구현 본체는
  `18aef2de`, 해시 고정은 `2b890846` 이다
- working_tree: clean
- **제품 코드 변경: 0** — `app/**` · `frontend/**` · `alembic/**` · `runner/**` · `tests/**`
  diff **0**. S1 이 고친 것은 `scripts/**`(Harness·Probe)와 `docs/**` 뿐이다

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **스택 검증 완료.** PG16.15 + pgvector 0.6.0 + pg_trgm 1.6 을 테스트 서버 CPU 에서 실측했고 인덱스 파라미터·임베딩 모델이 **확정**됐다(D-209~D-212). **서버 시스템 설치는 아직 0** — S4 Installer Stage 6·7 의 일이다 | PG16 + pgvector 0.6.0 + pg_trgm 이 System of Record | S2(이식) → S4(설치) |
| **SQLite 제거** | **운영 정본.** `/var/lib/clovirone-web-assistant/web.sqlite3`, 75 테이블 · 257 인덱스 · alembic head `0061` · 22 MB | Runtime 의존 0 | S2 → S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110 | Notion Runtime 의존 0, 데이터는 PG 로 이관 | S13(Dry Run) → S14(Cutover) |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | `pg_dump` 개념 없음. Rollback 모델이 **"백업한 DB 파일 되돌리기"** — 단일 파일 전제 | `pg_dump -Fc` + 파일 아카이브 + manifest + **복원 후 앱 기동 검증** | S12 |

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착시켰다.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 넷 다 끝났다.
  - **P-01 프로브 8건** — 거짓 통과 경로를 전부 막았다. Checker **5개**가 `--self-test` 를 새로
    갖고(총 8개), `probe_selftest` 는 19 → **30 사례**(브라우저 없이 도는 로직 반례 11 추가,
    `static_checks.sh` 가 매번 돌린다). 상세는 [`INVENTORY/12_PROBE.md`](INVENTORY/12_PROBE.md)
  - **P-02** — S1 소유 미확인 항목이 전부 닫혔다. 전수 목록은 만들지 않았다(E9 · Inventory 규칙 4)
  - **P-03 PG 스택 실측** — 실 PG16.15 에서 한국어 검색·벡터 인덱스·CPU 임베딩을 재고
    **D-209~D-212** 로 확정했다
  - **P-04 `VARCHAR(n)` 감사** — **운영 정본**(alembic `0061`)에서 선언 410 컬럼을 쟀다.
    초과 **1건**이고 그 값을 **지금 코드가 만든다**. S2 가 쓸 숫자는 관측 80 이 아니라
    **계약상 최대 108** 이다 (D-214)

### S1 이 드러낸 것 둘 — 둘 다 Owner 가 붙어 있다

| 발견 | 성격 | Owner |
|---|---|---|
| **`/api/admin/approval-delegations` 표면 전체에 범위 게이트가 없다** — 부서 범위 admin 이 남의 부서 결재 대리를 만들고 취소할 수 있다 | 권한 결함 | **S5** (`BACKLOG.md` P-12a · `check_scope_gates.py::KNOWN_GAPS`) |
| **`messages.message_id` 가 `VARCHAR(64)` 인데 코드가 최대 108자를 만든다**(운영 관측 80 · 20/311행) — PG 에서 `INSERT` 가 거부된다 | 이식 차단 | **S2** (D-214) |

**S1 은 제품 코드를 고치지 않는다.** 둘 다 기록하고 Owner 로 넘겼다 (E9).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S1 은 `scripts/**` 와 `docs/**` 만 바꿨다. 변경 Surface 를 검증하고, **지문이 같은 고비용
검증은 인용한다**(E1).

| 대상 | 결과 | 지문 |
|---|---|---|
| `scripts/static_checks.sh` | **STATIC_CHECKS_OK** | S1 트리 |
| `check_ui_renewal_coverage.py --self-test` | **OK** (사례 10 + 배선 2) | S1 트리 |
| `check_ui_renewal_coverage.py --stage plan` / `--stage wave`(W5) | **UI_RENEWAL_COVERAGE_OK** (억제 0건) | S1 트리 |
| `probe_selftest` (DOM 19 + 로직 11) | **PROBE_SELFTEST_OK (30 사례)** | S1 트리 |
| `pytest` — `scripts/**` 를 소비하는 시험 5파일 | **30 PASS** | S1 트리 |
| backend `run_full_regression.sh` | **FULL_REGRESSION_OK** — **인용** (`app`·`tests` diff 0) | `60f8fafb` |
| frontend `npx vitest run` | **2,409 PASS / 0 FAIL** — **인용** (`frontend` diff 0) | `60f8fafb` |
| runner `test_assistant.py` | **293 PASS** — **인용** (`runner` diff 0) | `60f8fafb` |

## NOW

**S1 은 끝났다.** 이제 계획이 **숫자를 갖고 있다** — 인덱스 파라미터도, 모델도, 넘치는 컬럼도
추정이 아니라 실측이다. 그리고 그 숫자를 재는 검사들이 더 이상 눈을 감지 않는다.

S1 이 이 순서였던 이유는 하나다: **눈을 감은 검사 위에서 Route 와 DB 를 갈아엎으면 무엇이
깨졌는지 알 수 없다.** 실제로 눈을 뜨자마자 권한 결함 하나와 이식 차단 하나가 나왔다.

## NEXT — S2 부터 시작한다

**S2 = PostgreSQL Foundation.** 앱 고유 ~60 테이블을 **도메인 변경 없이** 이식한다.
정확한 범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 작업 목록은
[`INVENTORY/08_SQLITE.md`](INVENTORY/08_SQLITE.md) 의 13항이다.

S1 이 S2 에게 넘기는 것:

1. **`messages.message_id` 를 `≥108` 로 넓힌다** (D-214). 절단은 유니크 키를 깨므로 선택지가
   아니고, 관측값 80 에 맞추면 더 긴 유효 id 가 오는 날 다시 깨진다
2. **인덱스 정책이 이미 정해져 있다** (D-210) — **Vector 인덱스를 처음부터 만들지 않는다.**
   수천 규모에서 exact 가 1~9ms 다. 임계(384차원 ≈ 1.2만 벡터)를 넘으면 그때 HNSW
   `m=32, ef_construction=200, ef_search=40`
3. **키워드 검색은 `pg_trgm` GIN 이 정본**이다 (D-209). FTS `simple` 은 보조 가산점이고
   단독 경로가 아니다
4. **PG 를 어디서 띄우고 회귀를 돌릴 것인가** — 아래 「입력」 참조

## RISK — 지금 살아 있는 것

전체 18건은 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12. S1 이 소유하던 넷은 **닫혔다**.

| # | Risk | 상태 |
|---|---|---|
| ~~R4~~ | Coverage Gate 가 Route 개편 시 조용히 통과한다 | **해소** — 빈 결과 FATAL + 표본 수 출력 (D-213) |
| ~~R5~~ | 한국어 검색 품질 회귀 | **해소** — `pg_trgm` GIN 이 어절 내부 부분일치 recall 1.000 (D-209) |
| ~~R6~~ | CPU 리랭킹이 느림 | **확정** — 대리 측정 6.7초. **리랭커를 쓰지 않고 RRF 로 간다** (D-212) |
| ~~R7~~ | `VARCHAR(n)` 초과로 Migration 실패 | **범위 확정** — 초과 1건, 대응은 «넓힌다» (D-214) |

다음 Session 이 실제로 만나는 것:

| # | Risk | Owner |
|---|---|---|
| R1 | **`is_write_conflict` 가 PG 에서 진짜 제약 위반을 재시도로 감춘다** | S2 |
| R2 | **부분 유니크 인덱스 3개가 PG 에서 전체 유니크가 된다** | S2 |
| R3 | **약 40개 동시성 테스트가 거짓 초록이 된다** | S2 |
| R17 | pgvector 검색 품질 | **인덱스 파라미터는 확정됐다**(D-210). 남은 것은 S10 의 하이브리드 가중치다 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **테스트 서버 sudo** | **쓸 수 있다** — 사용자가 2026-08-21 에 다시 제공했고 `10.100.64.71` 한정이다. **제품 자체에는 이 자격증명이 들어가지 않는다**: 설치 시 권한 상승은 운영자가 `sudo …/install.sh` 로 하거나 installer 가 요구한다([`INSTALLATION.md`](INSTALLATION.md) §1·§4). S1 이 실측에 쓴 **사용자 공간 PG**(`scripts/bench/pg_userspace_bootstrap.sh`)는 sudo 없이도 되므로 S2 회귀에 그대로 쓸 수 있다 — 시스템 설치는 **S4 Installer Stage 6·7** 의 일이다 |
| **운영 SQLite 읽기** | **가능하다.** P-04 는 운영 정본(alembic `0061`)을 `.backup` 무중단 스냅숏으로 재고 스냅숏을 지웠다 — 운영 DB 는 읽기만 했다. 원장은 [`EVIDENCE/S1/varchar_prod.json`](EVIDENCE/S1/varchar_prod.json) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 20개 Project Key 명명 | **S6 에서** 초안표 제시 → 사용자 확인 → 적용. **확정 전 재채번 없음** (U11) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음. **Core Migration 은 이 결정과 무관하게 진행** (U19) |
| GitLab Repository 주소·자격증명 | **없어도 S4 는 진행한다** (Remote 중립 + 오프라인 Bundle) (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
