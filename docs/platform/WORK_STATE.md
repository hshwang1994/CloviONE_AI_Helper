# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-21** (S0)
- phase: **A — 기반**
- session: **S0 완료.** 다음은 **S1**
- branch: `ui/mui-migration`
- last_stable_commit: **`60f8fafb`** — S0 직전의 마지막 안정 커밋
  (W5 문서 커밋). S0 커밋 해시는 아래 `s0_commit` 에 건다
- s0_commit: **`3d489bbc`** — S0 문서 커밋. 이 커밋과 해시를 거는 다음 커밋이 S0 의 전부다
- working_tree: clean
- **제품 코드 변경: 0** — S0 은 문서만 만들었다. `app/**` · `frontend/**` · `scripts/**` ·
  `alembic/**` diff 0. 서버 변경 0 · PostgreSQL 설치 0 · Migration 실행 0 · n8n 제거 0

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **미설치.** 서버에 `psql`·`pg_config` 없음, 5432 미청취. `postgresql-16`·`postgresql-16-pgvector` 는 Ubuntu 24.04 공식 저장소에서 **설치 가능**함을 apt 로 확인 | PG16 + pgvector 0.6.0 + pg_trgm 이 System of Record | S1(검증) → S2(이식) |
| **SQLite 제거** | **운영 정본.** `/var/lib/clovirone-web-assistant/web.sqlite3`, 75 테이블 · 257 인덱스 · alembic head `0061` · 22 MB | Runtime 의존 0 | S2 → S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `ticket_cache` 1,124 · `document_cache` 110 | Notion Runtime 의존 0, 데이터는 PG 로 이관 | S13(Dry Run) → S14(Cutover) |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | `pg_dump` 개념 없음. Rollback 모델이 **"백업한 DB 파일 되돌리기"** — 단일 파일 전제 | `pg_dump -Fc` + 파일 아카이브 + manifest + **복원 후 앱 기동 검증** | S12 |

## 완료

- **S0 — Plan 기록.** Plan Mode 에서 확정한 Architecture · Decision · S0~S22 실행계획을 Repository
  지속 문서에 정착시켰다. 이제 **다음 세션은 이 저장소 문서만으로 이어받을 수 있다**
  - 신규: `docs/platform/MASTER_PLAN.md` · `WORK_STATE.md`(이 파일) · `BACKLOG.md` ·
    `INSTALLATION.md` · `INVENTORY/`(index + 12종)
  - 기존 재사용: `docs/DECISIONS.md` 에 **D-187~D-208** 22건 추가 (새 파일을 만들지 않았다)
  - 기존 갱신: `docs/ui-renewal/WORK_STATE.md` 에 **W5B~W15 동결 선언 + 재배치 표**
  - 색인 정정: `docs/README.md` · `docs/WORK_PLAN_INDEX.md` 가 삭제된 문서를 가리키던 링크를
    `docs/platform/*` 로 돌렸다

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S0 은 제품 코드를 건드리지 않았으므로 **회귀를 새로 돌리지 않았다** (E1: 지문이 같으면 인용한다).
`60f8fafb` 시점의 값을 그대로 인용한다 — 출처는 `docs/ui-renewal/WORK_STATE.md`:

| 대상 | 결과 | 지문 |
|---|---|---|
| backend `run_full_regression.sh` | **FULL_REGRESSION_OK** (unit·regression·security·integration) | `60f8fafb` |
| frontend `npx vitest run` | **2,409 PASS / 0 FAIL** (파일 322) | `60f8fafb` |
| runner `test_assistant.py` | **293 PASS** | `60f8fafb` |
| `scripts/static_checks.sh` | **STATIC_CHECKS_OK** | `60f8fafb` |
| `probe_selftest` | **PROBE_SELFTEST_OK (19 사례)** | `60f8fafb` |
| `check_ui_renewal_coverage.py --stage wave`(W5) | **PASS** (억제 0건) | build `08b5525cb2f52618` |

S0 이 실제로 돌린 것은 **문서 정합성 검사 하나**다 — `check_ui_renewal_coverage.py --stage plan`
을 편집 전후로 실행해 둘 다 `UI_RENEWAL_COVERAGE_OK`.

## NOW

**S0 은 끝났다.** 이 저장소는 이제 계획을 스스로 갖고 있다.

S0 이 한 일은 문서를 쓴 것뿐이지만, 그것이 이 Session 의 전부인 이유는 하나다 — Plan Mode 의
전수조사 결과가 대화 안에만 있으면 다음 `/clear` 에서 사라진다. **파일이 장기 기억이다**(D-01).

## NEXT — S1 부터 시작한다

**S1 = 기반 정직화 · 실측 · 성능 검증.** 정확한 시작점은 아래 넷이고, **제품 코드 변경은 0** 이다.

1. **Probe 8건 수정** — `INVENTORY/12_PROBE.md` 의 표가 대상이다. 우선순위 1번
   (`check_ui_renewal_coverage.py` 의 `read_tab_groups()`/`read_settings_tabs()`/`read_jsx_routes()`
   **빈 결과 FATAL화**)부터. 신뢰할 만한 셋(`check_icon_props.py`·`check_ink_scale.py`·
   `check_logical_border_props.py`)과 `probe_selftest.py` 가 템플릿이다 — **실제 스캔 전에 양방향
   `--self-test` 를 돌리고 실패하면 아무것도 보고하지 않는다**
2. **Inventory 12종 완성** — `INVENTORY/` 각 파일의 `완성도` 절이 S1 이 채울 자리를 지목한다.
   Plan Mode 실측치는 이미 들어 있다. **`11_TEST.md` 의 프런트 테스트 수 불일치(2,409 vs 1,987)를
   실행으로 확정하는 것이 여기 포함된다**
3. **PG 성능 검증** — 테스트 서버에 `postgresql-16` `postgresql-16-pgvector` `postgresql-contrib`
   설치 후 실 Corpus(문서 1,238 + 티켓 1,119)로 HNSW/IVFFlat/exact 세 경로의 recall·지연 측정,
   인덱스 파라미터(`m`·`ef_construction`·`ef_search`·`lists`) 결정, `pg_trgm` GIN 과 FTS 의 가중치
   결정. CPU 임베딩/리랭킹 벤치 → 모델 확정.
   **Version 은 판정 대상이 아니다 — D-188 로 확정돼 있다**
4. **`VARCHAR(n)` 13개 컬럼 길이 감사** — `ticket_cache.title(500)` ·
   `document_cache.original_url(1000)` · `trash_items.title(400)` 외 10개. SQLite 는 길이를 무시했고
   PG 는 강제한다 (R7)

**S1 Exit**: 프로브 self-test 통과 · 실측 수치와 인덱스 파라미터가 `DECISIONS.md` 에 기록 ·
**제품 코드 diff 0** · Commit · Working Tree Clean.

> S1 은 **제품 코드를 고치지 않는다.** 고치는 것은 Harness/Probe 와 문서다.
> PG 이식은 S2 부터다.

## RISK — 지금 살아 있는 것

전체 18건은 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12. 다음 두 Session 이 실제로 만나는 것만 적는다.

| # | Risk | Owner |
|---|---|---|
| R4 | **Coverage Gate 가 Route 개편 시 조용히 통과한다** — 빈 결과가 `[]` 라 검사 루프가 0번 돌고 OK 를 찍는다 | **S1** |
| R5 | 한국어 검색 품질 회귀 — PG 기본 `to_tsvector` 는 한국어를 공백으로만 쪼갠다 | **S1** |
| R6 | CPU 임베딩/리랭킹이 예상보다 느림 → 리랭커가 느리면 **RRF 융합으로 대체** | **S1** |
| R7 | `VARCHAR(n)` 길이 초과로 Migration 실패 | **S1** |
| R1 | **`is_write_conflict` 가 PG 에서 진짜 제약 위반을 재시도로 감춘다** | S2 |
| R2 | **부분 유니크 인덱스 3개가 PG 에서 전체 유니크가 된다** | S2 |
| R3 | **약 40개 동시성 테스트가 거짓 초록이 된다** | S2 |

## BLOCKERS

- **없음.** 아래 넷은 Blocker 가 아니라 **대기 중인 외부 결정**이고, 어느 것도 S1~S5 를 막지 않는다.

| 항목 | 처리 |
|---|---|
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) |
| 20개 Project Key 명명 | **S6 에서** 초안표 제시 → 사용자 확인 → 적용. **확정 전 재채번 없음** (U11) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음. **Core Migration 은 이 결정과 무관하게 진행** (U19) |
| GitLab Repository 주소·자격증명 | **없어도 S4 는 진행한다** (Remote 중립 + 오프라인 Bundle) (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
