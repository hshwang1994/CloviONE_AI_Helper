# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-23** (S10)
- phase: **C — AI**
- session: **S10 완료.** 다음은 **S11 — n8n · 외부 Runner 제거**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S10 도 옮기지 않는다.** S10 의 시험 변경은 전부 강화 방향이다 — **시험 5파일 신설**
  (unit 19 · integration 22 · security 9 · regression 12 = **62건**) + 옛 시험 `test_ai_domain_seed`
  11→**15건** · 프런트 시험 **5건** 신설. `check_test_strength.py` 통과(약화 0)
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3` · s4_commit: `6909bb96` ·
  s5_commit: `aa9c8c63` · s6_commit: `971a31fa` · s7_commit: `87dd8707` · s8_commit: `0240c661` ·
  s9_commit: `ba68ef2c`
- working_tree: clean
- **Runtime Component 는 안 늘었다.** 새 유닛도 새 표도 없다 — `0008` 은 **인덱스 둘**만
  만든다. 대신 **프런트가 바뀌었다**(화면 하나 신설 + 편집기 앵커 + 라우트) — 번들을 다시
  만들었고 초기 gzip **265KB**(예산 280)로 그대로다

## S10 이 실제로 한 것

AI 의 두 번째 축이다. 이제 **검색이 그 인덱스를 읽고, 권한이 그보다 먼저 걸리며, 답에는
눌러서 갈 수 있는 근거가 붙는다.**

| | |
|---|---|
| 🔴 **권한이 `LIMIT` 앞에 걸린다** | 세 레인이 전부 `effective_visibility_clause` 가 만든 후보 집합 **안에서만** 돈다. chunk 에 권한 컬럼이 없으므로(D-256) 그 질의가 **유일한 판정**이고, `check_visibility_single_source.py` 가 소비자 여섯 번째로 그 도달을 확인한다 |
| 🔴 **음성 시험이 답변이 아니라 Context 를 본다** | 「답변에 안 나왔다」는 증거가 아니다(D-202). 가짜 생성 Adapter 가 (system, user) 쌍을 그대로 들고 있고, 시험은 **범위 밖 문장이 그 안에 있는지**를 직접 본다. 그리고 「범위를 안 걸면 상한 안에 내 것이 한 건도 안 들어온다」는 반례를 **시험 안에 심었다** |
| **반영 지연이 0 이라는 것이 시험으로 남았다** | 부여 행 하나를 넣고 다음 질의가 곧바로 새 답을 낸다 — 그 사이 chunk 지문은 **한 줄도 안 바뀐다.** 재색인도, 이벤트 처리도, 300초 대기도 없다 |
| **융합 가중치를 실측으로 다시 정했다** | D-209 초기값 `fts 0.5 / vec 1.0` → **`fts 1.0 / vec 0.5`**. 전체 MRR@10 **0.7553 → 0.8869**(+17.4%). 근거는 아래 절과 [`EVIDENCE/S10/`](EVIDENCE/S10/README.md) (**D-260**) |
| 🔴 **벡터 레인에 거리 상한을 뒀다** | 최근접 이웃은 **언제나** 답을 낸다 — 상한이 없으면 아무 관계 없는 질의에도 근거가 생기고, 그러면 「근거가 없다」가 영원히 성립하지 않는다. `0.16` 은 독립된 측정 둘이 가리키는 자리다 (**D-261**) |
| **임베딩 모델은 그대로 둔다** | D-211 의 상향 경로를 긴 본문(중앙값 705자)으로 다시 쟀다. `bge-m3` 는 **+2.7%** 인데 **색인 9.8배 · 질의 2.5배**다. 안 바꾼다 (**D-262**) |
| **인용이 문서가 아니라 문단을 가리킨다** | 주소는 서버가 만든다(`/knowledge/<id>?block=<블록 id>`). 편집기의 `blockId` 가 `rendered: false` 라 DOM 에 안 나가고 있었고, 그것이 인용을 문서 맨 위까지만 데려가는 유일한 이유였다 (**D-263**) |
| **생성으로 가는 문은 그대로 하나다** | 답변과 문서 초안이 지시문만 다르고 같은 `Gateway.generate(task=, data=)` 를 지난다. **근거가 0 이면 모델을 아예 안 부르고**, 초안을 못 쓰면 **문서를 안 만든다** (**D-264**) |
| **검색은 쿼터를 안 쓴다** | `/api/ai/search` 에서 도는 임베딩은 서버 CPU 이지 구독 호출이 아니다. 그 성질이 곧 「생성 차단 시 검색·인용 계속 동작」을 **라우터 모양**으로 만든다 |

## S10 이 드러낸 것 — 측정과 회귀가 안 잡았으면 그대로 갔을 것 넷

### 1. 질의 종류를 하나 빠뜨리면 **D-209 를 뒤집는 결론**이 나온다

처음에는 질의를 두 종류(어절 경계 부분구간 · 기억나는 대로)로만 만들었다. 그 표에서
FTS 가 트라이그램을 이겼다 — D-209 가 실측으로 정한 「후보 생성은 `pg_trgm` 하나가
책임진다」를 정면으로 뒤집는 값이다. 빠진 것은 **어절 내부 부분구간**이었고, 그것을 넣자
FTS 는 그 질의군에서 **0.0575** 로 주저앉았다(트라이그램 0.6600). D-209 를 긴 본문에서
그대로 재현한 값이다.

**한국어 검색을 재면서 어절 내부 질의를 빼면 무엇을 재도 틀린 답이 나온다.**

### 2. 그리고 그 측정이 제품 결함 하나를 잡았다

AI 트라이그램 레인이 검색창의 **낱말 AND 가지**를 안 갖고 있었다. 사람이 기억나는 대로
친 질의(`스프린트 정리`)에서 MRR 이 **0.01** 이었다 — 같은 질의를 검색창은 찾는다.
「검색에서는 나오는데 AI 는 못 찾는다」는 아무 오류도 안 내는 종류의 결함이다. 두 검색이
같은 조건을 쓰도록 `app/search/query.py::trgm_condition` 하나로 합쳤다.

### 3. 동질적인 코퍼스에서는 **거리 상한이 순위를 못 매긴다**

실측 코퍼스는 한 문서가 chunk 의 66%라 주제가 매우 동질적이다. 그 안에서 정답까지의 거리
p50 은 **0.1401**, 최근접 오답까지는 **0.1375** 다 — **오답이 더 가까운 쪽이 절반**이다.
어떤 상한도 그 둘을 못 가른다.

그래서 상한의 일을 좁혀 적었다: **주제가 아예 다른 질의를 걸러 내 「근거가 없다」를
성립시키는 것** 하나이고, 같은 주제 안의 순위는 RRF 가 맡는다. 값은 이 코퍼스가 아니라
**S9 의 주제 분리 실측**(0.1151 대 0.1984)과 함께 읽어야 하는 값이다.

### 4. 전 회귀가 **S10 이 만든 구멍 둘**을 잡았다

둘 다 「기능은 도는데 감시가 안 붙은」 종류다 — 화면을 열어 보는 것으로는 절대 안 드러난다.

| 무엇 | 왜 조용한가 |
|---|---|
| `/ai` 가 **QA 캡처 하네스에 없었다**(`scripts/ui_qa/routes.py`) | 하네스를 몇 번 돌려도 그 화면은 한 번도 안 찍힌다. 캡처가 0장이면 캡처 검사도 0번 돈다 — 요약은 초록이다 |
| `POST /api/ai/{ask,documents}` 가 **점검 모드 정책에 분류돼 있지 않았다** | 라우터에는 `block_if_maintenance` 가 이미 걸려 있었다. 빠진 것은 게이트가 아니라 **「이것이 의도다」라는 기록**이고, 그 기록이 없으면 다음 사람이 게이트를 떼도 아무도 모른다 |

`test_ui_qa_route_registry_completeness.py` 와 `test_maintenance_coverage.py` 가 각각
잡았다. 둘 다 「새 라우트가 분류 없이 지나가는 것」만 보는 검사이고, **정확히 그 일을 했다.**

### 그리고 범위 밖 결함 **둘**을 그 자리에서 고쳤다 — 뿌리가 같다

S7 의 지식 화면 둘이 **`kit.jsx` 에 없는 API 를 부르고 있었다.**

1. `useToast()` 는 **함수**를 돌려주는데(`ToastCtx.Provider value={push}`) `toast.show(...)`
   로 불렀다 — 실제 브라우저에서는 그 열 줄이 전부 `TypeError` 다.
2. `EmptyState` 에는 **`body` prop 이 없다**(`help` 다). `body="…"` 로 넘긴 다섯 줄은
   화면에 한 글자도 안 나왔다 — 빈 상태가 제목만 보여 주고 있었다.

**시험이 초록이었던 이유가 더 나쁘다**: 토스트 대역이 `useToast: () => ({ show })` 였다.
대역이 진짜 계약과 다르면 시험은 제품이 아니라 **대역을** 확인한다. 호출부 열다섯 곳과
그 대역을 함께 고쳤다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0`.
  결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** Clean OS 에서 세 줄, 재부팅하면 스스로 복귀.
  결정 **D-225~D-229**.
- **S5 — Identity & Access.** 권한이 표가 되고 가시성이 함수 하나가 됐다. 결정 **D-230~D-235**.
- **S6 — Work Domain.** 티켓이 세 이름으로 불리고 그 셋이 같은 티켓을 가리킨다.
  결정 **D-236~D-243**.
- **S7 — Knowledge Domain (+P-14a).** 본문의 정본이 블록이 되고 그 블록에 이름이 붙었다.
  결정 **D-244~D-248**.
- **S8 — File Storage Providers.** 파일이 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.
  결정 **D-249~D-253**.
- **S9 — AI Platform 1 (Gateway · Pipeline).** 모델이 계약 뒤로 들어가고 문서가 스스로
  색인된다. 결정 **D-254~D-259**.
- **S10 — AI Platform 2 (Retrieval · Citation · 생성).** 위 두 절. 결정 **D-260~D-264**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`~`0008` 이 **98 표**를 만든다 (S10 은 표를 안 만들었다 — 인덱스 둘) |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

**S13 이 알아야 하는 것 아홉** (앞 일곱은 S6~S9 가 남긴 것 그대로):
1. 표 이름이 `departments` → `org_units`(D-234), `ticket_cache` → `tickets`(D-238)로 바뀌었다.
   **컬럼 이름은 둘 다 그대로**다.
2. 적재 직후 `app/work/numbering.py::seed_counters()` 를 부른다.
3. **Project Key 20건은 확정됐다**(D-243). 순서는 하나다 — 프로젝트 적재 →
   `project_keys.apply_confirmed(db)` → `numbering.seed_counters(db)` → 재채번.
4. **날짜 컬럼 16개가 `date`/`timestamp` 다**(D-248). 소스 문자열을 그대로 대입하면
   못 읽는 값에서 **500** 이 난다 — `app/core/dates.py::parse_date`/`parse_dt` 를 지난다.
5. **본문을 옮길 때 앞판을 함께 넘긴다**(D-247). `blocks.derive(body, carry_from=앞판)` 을
   안 쓰면 재실행마다 판이 새로 쌓인다. 다리는 `documents.legacy_page_id`(부분 유니크)다.
6. **파일을 옮길 때 `app/storage/service.py::store_bytes` 를 지난다**(D-250).
7. **색인은 따로 안 만들어도 된다**(S9). 적재가 끝나면 색인 레인의 훑기가 상태 행이 없는
   문서를 전부 찾아 스스로 돈다. 급하면 `python -m app.cli.ai_cli reindex`.
8. 🔴 **색인 처리량은 D-211 의 120 docs/s 가 아니다.** 그 숫자는 96자 글의 값이고, 실제
   본문 길이(중앙값 705자)에서는 **11.7 chunk/s** 다(D-262). 용량 계산에 쓸 값은 이쪽이다.
9. **본문이 실려 오면 융합 가중치와 모델을 다시 볼 자리가 생긴다.** S10 은 업무 기록으로는
   못 쟀다 — 미러에 본문이 없다(실측: `document_cache` 0건 · `ticket_cache` 31건).
   하네스는 `scripts/bench/retrieval_*.py` 에 그대로 있다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension 을 세운다. `0007` 이 `vector` 확장을 켜고 `0008` 이 키워드 인덱스 둘을 건다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ · S9 ✅ · S10 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 코드 수준 13항이 전부 닫혔다. 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ · S7 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `tickets` 1,123 · `document_cache` 110 이고 **본문은 거의 비어 있다**(실측: 문서 0건 · 티켓 31건). 받을 그릇과 검색·인용은 다 섰다 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **Retrieval 까지 섰다.** 권한이 `LIMIT` 앞에 걸리고, 세 레인이 RRF 로 융합되고, 인용이 문단을 가리키고, 초안이 `source_type=AI` 문서가 된다. 남은 것은 **옛 경로 철거** — n8n → `claude-work-assistant`(8789)가 여전히 Notion 전량을 모델에 싣는다 | Model Gateway ✅ + 권한이 앞서는 Hybrid Retrieval ✅ | S9 ✅ · S10 ✅ · **S11** |
| **Backup** | **기본형 + 설치 스냅샷 + 파일 저장소 이관.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원 + 파일 아카이브. **AI 색인은 일부러 백업 대상이 아니다**(D-203·D-204) | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ · S8 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 S14 다 (`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S10 은 **공유 계층 둘**을 바꿨다 — 검색 질의 조립(`app/search/query.py` 의 `ilike_pattern`·
`trgm_condition` 공개)과 본문 조립(`blocks.from_plain_text`). 그래서 백엔드 전 회귀를
다시 돌렸다.

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | 첫 완주에서 **2건 실패**했고 둘 다 S10 이 만든 것이다(위 4절). 고친 뒤 `tests/regression`·`tests/security` 재실행 **전부 초록**, `tests/unit` + AI integration 재실행 **전부 초록**. ⚠️ **`pytest tests` 를 백그라운드로 직접 돌리면 안 된다**(P-09e) |
| 프런트 전 회귀 (vitest) | **2,446 통과 · 3 실패** — 실패 셋은 전부 **S10 이전 것**이고 P-09a 소유다(`ko-wordbreak.test.jsx` 안 닫힌 주석 · `SettingVersions.jsx:75` 동사표 · `settings-coerce`). S10 이 만든 실패 **0** |
| **권한 음성 (S10 Exit)** | **9건.** 부서가 다른 문서가 **후보 집합에서 이미 없다** · 그 문장이 **모델에게 넘어간 메시지에 없다** · 범위 밖 행이 상한을 채워도 내 것이 남는다(**반례를 시험 안에 심었다**) · `confidential` 은 같은 부서 동료에게도 안 보이고 **명시 부여자에게는 보인다** · 🔴 **부여 한 줄로 다음 질의가 바뀌는데 chunk 지문은 그대로다** |
| **프롬프트 경계 (S10)** | 본문이 구분자 **안**에 갇힌다 · 시스템 쪽에는 우리 문장만 있다 · 흉내 낸 구분자를 걷어내고 **그 사실을 보고한다** · 난스가 매번 다르다 |
| **Retrieval (integration)** | **12건.** 세 레인이 각각 답한다 · **의미 검색이 낱말이 하나도 안 겹치는 문서를 찾는다** · 질의는 `query:` 접두사로 임베딩된다 · 모델이 없어도 키워드 두 레인이 답하고 그 사실을 말한다 · 보관된 문서는 근거가 아니다 · 🔴 **생성이 막혀도 인용이 나온다** · **Context 는 인용 밖을 못 본다** · 근거가 0 이면 모델을 안 부른다 |
| **AI API (integration)** | **10건.** 상태가 「안 됨」이 아니라 **왜 안 되는지**를 말한다 · 검색은 **쿼터를 안 쓴다** · POST 는 CSRF 를 요구한다 · 실패한 생성은 쿼터를 안 깎는다 · 초안이 `source_type=AI` + `VSRC_AI` 문서가 된다 · **실패한 초안은 빈 문서를 안 남긴다** |
| **융합·인용 (unit)** | **19건.** 두 레인의 합의가 한 레인의 1등을 이긴다 · 한 레인의 표는 하나다 · 동점이 매번 같은 순서다 · **모르는 레인은 0 이 아니라 예외다** · 벡터가 낱말 레인을 못 넘는다 · 블록 앵커가 링크의 일부다 · **응답에 chunk 전문이 안 실린다** |
| **배선 (regression)** | **12건.** `/api/ai` 의 모든 경로에 권한 게이트가 있다(**반례 포함**) · POST 는 CSRF 를 요구한다 · **검색 경로가 쿼터를 안 잡는다** · Gateway 가 프로세스에 하나다 · `0008` 이 head 다 · **벡터 인덱스가 아직 없다** · 화면이 라우트로 이어져 있다 · 🔴 **편집기가 블록 id 를 DOM 에 싣는다** |
| **스키마 ↔ 코드** | **15건**(S9 의 11 + S10 의 4). FTS 설정이 마이그레이션과 카탈로그에서 같다 · 두 인덱스가 실제로 선다 · 🔴 **플래너가 그 인덱스를 쓸 수 있다**(글자 비교가 아니라 `EXPLAIN`) |
| 프런트 (vitest 신설) | **5건.** 생성이 막혀도 근거가 나오고 왜인지 말한다 · **인용을 누르면 `?block=` 까지 간다** · 답변과 근거가 함께 나온다 · 모델이 없으면 지금 무엇으로 찾는지 말한다 · 결과 없음과 데이터 없음을 구별한다 |
| `check_domain_single_source.py` | 규칙 18→**20**, 자기검증 29→**33사례**. 레인 SQL 과 **AI 후보 집합**이 각각 한 곳에서만 만들어진다 |
| `check_visibility_single_source.py` | 소비자 5→**6**. AI Retrieval 이 그 함수를 지난다 |
| 마이그레이션 왕복 | `upgrade`→`downgrade`→`upgrade` 를 실 PG 에서. 표 **98** 그대로 · 인덱스 389→**391** · 제약 **955** 그대로이고 되감기가 **대칭**이다 |
| 모델 ↔ 스키마 | autogenerate diff **0** — 새 인덱스 둘을 포함해 모델과 스키마가 같다 |
| 프런트 번들 | 다시 만들었다. 초기 gzip **265KB**(예산 280) · CSS 29KB(예산 120) · `BUNDLE_FRESH_OK` |
| `static_checks.sh` | S10 이 만든 실패 **0**(고친 뒤 재실행). 남은 넷은 전부 P-09a 소유(가운뎃점 8 · em 대시 1 · subprocess encoding · `tokens.css` 드리프트) |
| QA 캡처 하네스 | `/ai` 두 얼굴을 등록했다 — 「아직 안 물었다」와 「근거가 없다」. `/search` 가 빈 상태와 결과 상태를 둘 다 찍는 것과 같은 이유다 |

### 실측 하네스가 셋 늘었다

`scripts/bench/retrieval_corpus.py`(코퍼스·질의) · `retrieval_embed.py`(서버에서 실 모델로
벡터) · `retrieval_fusion.py`(실 PG 에서 **제품 레인 SQL 로** 격자 측정) ·
`retrieval_model_review.py`(모델 비교). 벤치가 SQL 을 다시 쓰면 측정한 것과 운영이 도는
것이 다른 질의가 되므로 **제품 코드를 그대로 부른다.**

## NOW

**S10 은 끝났다.** 검색이 인덱스를 읽고, 권한이 그보다 먼저 걸리고, 답에 눌러서 갈 수
있는 근거가 붙는다.

이 세션에서 가장 값이 나간 것은 코드가 아니라 **측정을 제대로 설계한 것**이다. 질의를 두
종류로만 만들었을 때 나온 표는 D-209 를 뒤집는 값이었고, 그 표를 믿고 가중치를 정했으면
한국어 검색의 핵심 성질을 정확히 반대로 튜닝했을 것이다. 빠진 것은 **어절 내부 질의**
하나였다.

두 번째는 **벡터 레인이 「못 찾았다」를 말할 수 있게 한 것**이다. 최근접 이웃은 언제나
답을 낸다 — 그 성질을 그대로 두면 「근거가 없다」가 영원히 성립하지 않고, 모델은 매번
상관없는 문서를 근거로 받는다. 인용 번호까지 붙은 채로.

세 번째는 **음성 시험이 답변이 아니라 Context 를 보게 한 것**이다. D-202 가 그 말을 미리
적어 뒀고, 그것을 구현으로 옮기려면 가짜 Adapter 가 넘어온 문자열을 들고 있어야 했다.

## NEXT — 다음 시작점: S11 (요청 시)

**S11 = n8n · 외부 Runner 제거.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, Backlog 는 **P-21**.

S10 이 다음 Session 에게 넘기는 것:

1. 🔴 **대체 경로가 이제 실재한다.** `/api/ai/search`·`/ask` 가 권한을 통과한 문서만
   근거로 쓴다. 옛 경로(n8n → `claude-work-assistant` 8789)는 **Notion 전량을 모델에
   싣는다** — 그것이 D-202 가 지목한 바로 그 상태이고, 걷어낼 근거는 「기능이 겹친다」가
   아니라 **「하나는 권한을 안 본다」**다.
2. **화면 입구가 이미 이어져 있다.** `/chat`(AI 도우미) 머리에 「문서에서 찾기」가 있고
   `/ai` 로 간다. 옛 화면을 걷어낼 때 그 입구를 **사이드바 항목으로 올릴 자리**가 생긴다 —
   지금은 「내 업무」가 여섯 항목이라 못 넣었다(`nav-ia-taxonomy.test.js`).
3. **`/api/me/ai-quota` 는 채팅 화면이 쓴다.** 그 화면을 걷어내면 이 엔드포인트의 소비자를
   다시 봐야 한다 — AI 작업공간은 아직 쿼터 잔량을 안 보여 준다.
4. **티켓은 아직 색인하지 않는다.** 지금 출처는 `document` 와 `file` 둘이다. n8n 이 하던
   「티켓을 근거로 답한다」를 새 경로가 대신하려면 티켓 색인이 필요하고, 그때
   `_collect_units` 에 출처를 더하고 `source_kind`·`anchor_kind` CHECK 와 `0007` 의 얼린
   어휘를 **함께** 넓힌다. ⚠️ **권한을 묻는 자리를 먼저 정해야 한다** — 지금
   `document_chunks.document_id` 가 NOT NULL 이라 티켓 chunk 가 가리킬 자리가 없다.
5. **벡터 인덱스는 여전히 없고 그것이 의도다**(D-210). 임계는 약 1.2만 벡터이고 넘었는지는
   `ai_cli status` 의 `vector_index_recommended` 가 말한다.
6. **`app/llm` 은 아직 산다.** 주간 리포트 요약이 그 경로를 쓴다 — 지우면 그 기능이 멈춘다
   (S9 이 감싼 이유 그대로).

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| ~~R15~~ | LXD 컨테이너가 실 장비와 다르다 | **해소** — 재부팅 축은 S4(D-229), Storage 축은 S8 이 **호스트에서** 닫았다 |
| ~~R17~~ | pgvector 검색 품질 | **해소 (S10)** — 가중치 실측 재조정으로 MRR@10 0.7553 → **0.8869**(D-260) · 벡터 레인 거리 상한(D-261) · 모델 재검토 종결(D-262). 레인 지연 p50 1~3.4ms |
| R11 | **시험 Storage 가 실 NAS 와 다르다** | **살아 있다(의도한 대로)** — 실 정보 수령 시 **설정만** 바꾼다 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| — | **검색 품질을 업무 기록으로는 아직 못 쟀다** | **살아 있다** — 미러에 본문이 없다. 하네스는 그대로 있고 다시 재는 자리는 **S13 이후**다(D-262) |
| — | **저장소 장애 중 쓰기가 21초~180초 이상 걸린다** | **알려진 성질**(D-251) |
| — | **색인 레인이 안 뜨면 검색 결과가 조용히 낡는다** | **완화** — `ALWAYS_ACTIVE_UNITS` 에 있어 재부팅 판정과 Stage 17 이 본다. 그래도 **아무 오류도 안 나는** 종류의 실패라 감시 대상이다 |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐다** (2026-08-22 · D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). **지금 적용된 프로젝트는 0건이고 그것이 정상이다** — PG 의 `projects` 가 비어 있다(적재는 S13) |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **임베딩 모델 파일** | **테스트 서버에 셋 다 있다** — `~/s1bench/models/`(`e5-small` · `e5-base` · `bge-m3`). 설치처에 넣는 것은 `deploy/install.sh ai --ai-model-dir <디렉터리>` 이고 **네트워크로 안 받는다**(D-259) |
| **S9·S10 검증 하네스** | 서버의 `~/s9verify`(S9 파이프라인) · `~/s10bench`(S10 임베딩). S10 벤치를 다시 돌리는 순서는 [`EVIDENCE/S10/README.md`](EVIDENCE/S10/README.md) 에 있다. 이 서버에는 **PostgreSQL 이 없다** — DB 축은 개발 머신의 실 PG 가 본다 |
| **S9 이 쓴 LXD 컨테이너** | **지웠다.** 다시 만들려면 `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz> <이름>`. **S10 은 설치 축을 안 건드렸다** — 새 유닛도 새 Stage 도 없다 |
| **테스트 서버의 시험 Storage** | **세워 뒀다** — NFS export `/srv/clv-nfs-export` · Samba share `/srv/clv-smb-share`(`[clvtest]`) · 마운트 `/mnt/clv-nfs`·`/mnt/clv-smb`(enabled, 재부팅 복귀 확인) · 시험 계정 `clvsvc`. SMB 자격증명은 `/etc/clovirassist/secrets/smb_matrix`(0600, root)이고 **값은 저장소에 없다** |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433 · 이미지 `pgvector/pgvector:pg16`). `CLOVIR_TEST_PG_URL` 로 덮어쓴다(주소는 `postgresql+psycopg://` — `psycopg2` 는 안 깔려 있다). S10 벤치는 `clovir_s10bench` 를 **따로** 만들었다 지운다 — 시험 DB 를 쓰면 벤치가 시험 결과를 바꿀 수 있다 |
| **전 회귀를 돌릴 때** | **`scripts/run_full_regression.sh` 를 쓴다.** `pytest tests` 를 백그라운드로 직접 돌리면 14% 근처에서 **CPU 0 으로 멈춘다**(P-09e). 그 러너는 `< /dev/null` 을 붙이고 통을 넷으로 나눈다 |
| **회귀 결과를 읽을 때** | **파이프 뒤에서 읽지 않는다.** `pytest … \| grep …` 의 `$?` 는 **grep 의 종료코드**다. 그리고 **도는 시험 아래에서 소스를 만지지 않는다** |
| **프런트를 고쳤을 때** | `cd frontend && npm run build` → `python scripts/check_bundle_fresh.py --write`. 안 하면 git 으로 설치한 서버가 **아무 오류 없이 옛 화면을 계속 돌린다** |
| **원격에서 오래 걸리는 명령을 돌릴 때** | **하네스가 걸릴 수 있는 자리에는 시간 제한을 건다.** 걸린 하네스는 결과를 한 줄도 안 내므로 「걸렸다」는 사실조차 증거로 안 남는다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 실 정보를 받으면 `storage_providers` 행의 `source`·`options` 만 바꾸고 `deploy/install.sh storage` 를 다시 돌린다 (U8·U9) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
