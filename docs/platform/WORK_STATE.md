# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-22** (S7)
- phase: **B — 도메인**
- session: **S7 완료.** 다음은 **S8 — File Storage Providers**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S7 도 옮기지 않는다.** S7 의 시험 변경은 전부 강화 방향이다 — **시험 7파일 · 155건 신설**
  (unit 72 · integration 33 · security 24 · regression 26) + 프런트 10건. 백엔드 전체는
  3,497 → **3,669건 / 370파일**. 옛 시험에서 줄인 것은 없고, 축이 바뀐 자리 하나(`test_ticket_sync` 의 `due_date` 단정)는 **문자열 대신 `date` 로**
  같은 사실을 더 강하게 단언한다
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3` · s4_commit: `6909bb96` ·
  s5_commit: `aa9c8c63` · s6_commit: `971a31fa`
- working_tree: clean
- **Runtime Component 는 늘지 않았다** — Installer 계약(D-205)은 무변경. 프런트 의존이
  셋 늘었고(`@tiptap/react`·`@tiptap/pm`·`@tiptap/starter-kit`) **초기 번들은 그대로다**
  (gzip 265KB, 예산 280) — 편집기가 지연 청크 309KB 에 산다

## S7 이 실제로 한 것

본문의 축이다. 이제 **본문의 정본은 블록이고, 그 블록에 이름이 붙어 영원히 같은 문장을
가리킨다.**

| | |
|---|---|
| **정본은 Block JSON** | `document_versions.body`(진짜 `jsonb`)가 정본이고 Markdown·Plain Text 는 파생이다. 셋을 `app/knowledge/blocks.py::derive()` **하나**가 함께 만든다 (D-198) |
| **블록 id 가 인용 앵커** | 최상위 블록마다 `attrs.blockId`. 안 건드린 문단의 인용은 판이 바뀌어도 같은 곳을 가리킨다. 앵커의 주인은 편집기이고, id 를 안 돌려주는 클라이언트(도구·**S13 마이그레이션**)에는 **앞판의 같은 자리**를 물려준다 (**D-247**) |
| **폴더 `path`·`depth` 는 트리거** | BEFORE 가 부모에서 파생시키고 AFTER 가 자손을 따라 고친다. **순환도 트리거가 거절한다** — 앱을 안 지나는 경로가 언젠가 생긴다 (**D-244**) |
| **권한은 공간이 정한다** | 문서에 소속 컬럼이 **없다**. 폴더 이동은 정리이지 권한 변경이 아니다(§5.3). 가시성 자원 둘 신설 — `space` · `knowledge_document` (**D-245**) |
| **되돌리기는 쌓는다** | 3판→1판 되돌리기는 **4판**을 만들고 이력은 남는다(`source='RESTORE'`). 남의 편집을 덮는 동작이라 `base_version` 을 받는다 (**D-246**) |
| **같은 본문이면 판을 안 만든다** | 비교는 **파생이 아니라 정본**으로. 안 그러면 이력이 「변경 없음」 수백 줄이 된다 |
| **길이로 안 거절한다** | 옛 `MAX_BLOCKS=100`·`MAX_LINE_CHARS=1900` 은 Notion 상한이지 제품 규칙이 아니었다. 거절하는 것은 **모양**이다 — 모르는 노드 · 위험한 링크 스킴(마크만 뗀다) · 재귀 깊이 |
| **편집기는 늦게 싣는다** | TipTap MIT extension 만. `React.lazy` 로 route-level 분리하고 `block-editor-lazy.test.jsx` 가 정적 import 재유입을 코드로 막는다 |
| **날짜가 진짜 날짜가 됐다** | **16컬럼**(달력일 11 · 시각 5)을 `0005_real_dates` 하나로. 화면 계약(ISO 문자열)은 그대로고 경계는 `app/core/dates.py` 하나다 (**D-248** · P-14a) |

## S7 이 드러낸 것 — 오류를 안 내는 결함 셋

**1. `vite.config.js` 의 `manualChunks` 가 이름으로 패키지를 잡고 있었다.**
`id.includes("/react/")` 는 **이름에 react 가 들어간 모든 패키지**를 초기 청크로 끌어온다.
`@tiptap/react` 를 들이자 TipTap 과 ProseMirror 전부가 거기 들어가 `React.lazy` 가 아무
일도 안 하게 됐고, 예산이 gzip **348KB**(예산 280)로 넘었다. 빌드는 성공했다.
패키지 경로(`node_modules/react/`)로 정확히 짚게 고쳤다.

**2. `app/projects/service.py::_last_activity_on` 이 `isinstance(edited, str)` 로 갈랐다.**
컬럼이 `timestamp` 가 되면 그 조건은 **영영 거짓**이고, 「저쪽에서 사람이 만진 시각」이
조용히 버려진다 — 그 프로젝트는 미러가 스쳐 지나간 시각만으로 「활동 중」이 된다.

**3. `app/projects/sync.py::_apply` 는 「같은 값이면 안 쓴다」로 회차 변화를 판정한다.**
소스 문자열을 `date` 컬럼과 비교하면 영영 다르고, 매 회차 전 프로젝트의 `updated_at` 이
덮여 목록 정렬(updated_at DESC)이 무너진다.

셋 다 시험이 없으면 「느려졌다」·「왜 다 최근이지」로만 드러난다. 셋 다 시험을 붙였다.

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
- **S7 — Knowledge Domain (+P-14a).** 위 두 절. 결정 **D-244~D-248**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`~`0005` 가 **93 표**를 만든다 (S7 이 8 표 신설 · 트리거 2 · 날짜 16컬럼 전환) |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

**S13 이 알아야 하는 것 다섯** (앞 셋은 S6 이 남긴 것 그대로):
1. 표 이름이 `departments` → `org_units`(D-234), `ticket_cache` → `tickets`(D-238)로 바뀌었다.
   **컬럼 이름은 둘 다 그대로**다.
2. 적재 직후 `app/work/numbering.py::seed_counters()` 를 부른다.
3. **Project Key 20건은 확정됐다**(D-243). 순서는 하나다 — 프로젝트 적재 →
   `project_keys.apply_confirmed(db)` → `numbering.seed_counters(db)` → 재채번.
4. **날짜 컬럼 16개가 `date`/`timestamp` 다**(D-248). 소스 문자열을 그대로 대입하면
   못 읽는 값에서 **500** 이 난다 — `app/core/dates.py::parse_date`/`parse_dt` 를 지난다.
5. **본문을 옮길 때 앞판을 함께 넘긴다**(D-247). Notion 본문에는 `blockId` 가 없으므로,
   `blocks.derive(body, carry_from=앞판)` 을 안 쓰면 **재실행마다 판이 새로 쌓이고**
   내용이 같은데도 차이가 「전부 새로 씀」으로 나온다. 자체 DB 문서의 다리는
   `documents.legacy_page_id`(부분 유니크)다.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension 을 세운다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 코드 수준 13항이 **전부 닫혔다**(10번을 S7 이 닫았다). 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ · S7 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `tickets` 1,124 · `document_cache` 110. **받을 그릇은 이제 다 있다** — 식별자·채번·예외 분류(S6)에 더해 본문 정본·앵커·다리(S7)까지 | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다. **인용 앵커는 이제 있다**(블록 id) — S10 은 `effective_visibility_clause` 에 연결하고 그 앵커를 쓰면 된다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | S9 · S10 · S11 |
| **Backup** | **기본형 + 설치 스냅샷.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원 + 복원 결과 확인 | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 S14 다 (`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S7 은 **공유 계층 둘**을 바꿨다 — 가시성 판정(자원 2종 추가)과 **날짜 컬럼 16개**.
그래서 E1 인용으로 끝내지 않고 **백엔드 전 회귀를 다시 돌렸다.**

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | **통과** — `pytest tests` 전체 초록 (**3,669건 / 370파일**). ⚠️ 이 회귀를 세 번 돌렸다: 앞의 두 번은 결과를 `grep` 에 물려 읽는 바람에 **pytest 가 아니라 grep 의 종료코드**를 봤고, 그래서 실패 8건을 「통과」로 읽었다. 파이프 없이 다시 돌려 전부 잡았다 — **회귀 결과는 파이프 뒤에서 읽지 않는다** |
| **판 · 차이 · 되돌리기** (S7 Exit) | **16건.** 저장할 때마다 판이 쌓이고 **안 바뀌면 안 쌓이고**(그 사실을 `created_version` 으로 말한다), 차이가 블록 단위로 나오고, 되돌리기가 **이력을 남긴 채** 새 판을 만든다. 남의 저장 뒤 되돌리기는 **409**, 잠금 값이 맞으면 200 — 반대편을 함께 둔다 |
| **폴더 트리 트리거** (실 DB) | **17건.** 앱이 적은 `path`·`depth` 를 트리거가 덮는다 · 옮기면 **자손 전부**가 따라온다 · 순환을 **앱을 안 지나는 UPDATE** 로도 막는다 · 깊이 상한 · 형제 이름 유일(뿌리는 부분 유니크) · **폴더를 지워도 문서는 안 지운다** |
| **Block JSON** | **33건.** 파생 셋이 함께 나온다 · 앵커가 재정규화에서 살아남는다 · **길이로 안 거절한다**(옛 상한 3배·2배로 실제 저장) · 모양은 거절한다 · `javascript:` 6종이 마크만 잃고 글자는 남는다(정상 링크 5종은 통과) · diff 가 수정/이동/추가/삭제를 구별한다 |
| **범위 (음성)** | **24건.** 공간·문서·폴더·판·차이·되돌리기·관계가 전부 범위를 지킨다(**404**, 403 이 아니다). `confidential` 은 `SPACE_ADMIN` 만 연다. 각 단정에 「우리 것은 보인다」를 함께 둔다 |
| **날짜 컬럼** (P-14a) | **54건**(경계 파서 28 · 컬럼과 계약 26). 16컬럼의 실제 타입 · **DB 가 `2026-02-31` 과 `TBD` 를 거절한다**(정상 날짜는 들어간다) · 화면 계약이 여전히 ISO 문자열 · 스프린트 422(500 아님) · **동기화가 안 바뀐 값을 「바뀜」으로 안 본다** |
| **회귀가 잡은 것 8건** | 전부 S7 이 만든 것이고 전부 고쳤다. ① `/knowledge`·`/knowledge/:id` 가 QA 하네스에 없었다(`scripts/ui_qa/routes.py`) — **사이드바 항목이 없다고 캡처 대상이 아닌 것은 아니다**. ② 날짜 단정 5건이 읽어 온 `date` 를 문자열과 비교했다(프로젝트 동기화·주간 리포트·헬스 스냅샷·티켓 동기화). ③ `team_docs` 골든 3건 — `last_edited` 가 소스 원문에서 정규화된 naive UTC 로 바뀌었다. **같은 순간이고** 프런트 소비처 넷이 전부 시간대 표기가 없으면 `Z` 를 붙인다(`fmtDateTime`·`fmtRelative`·`toUTCDate`) — 확인하고 골든을 같은 변경에 함께 넣었다 |
| `check_domain_single_source.py` | S6 의 work 전용 검사를 **도메인 검사로 넓혔다** — 규칙 6→**10**, 자기검증 8→**14사례**(검출 11 · 위양성 3). 파생 본문·판·폴더 경로·멘션이 각각 한 곳에서만 쓰인다 |
| 마이그레이션 왕복 | `upgrade`→`downgrade`→`upgrade` 를 실 PG 에서. `0004`: 표 85→93 · 인덱스 313→358 · 제약 201→243 · 트리거 1→3 **대칭**. `0005`: 실 데이터(정상·시각포함·못읽는값·빈값)로 왕복 확인 |
| 모델 ↔ 스키마 | autogenerate diff **0** (두 마이그레이션 각각) |
| 프런트 | `npx vitest run` — **2,441 / 2,444 통과.** 남은 셋은 P-09a 소유(S7 이 만든 것 아님). 편집기 지연 로딩 4건 · 문서 화면 6건 신설 |
| 번들 | 초기 JS gzip **265KB → 265KB**(예산 280) · `BUNDLE_BUDGET_OK` · `check_bundle_fresh.py --write` |
| `static_checks.sh` | S7 이 만든 실패 **0**. 남은 넷은 전부 P-09a |

### ⚠️ `static_checks.sh` 와 프런트 시험은 아직 빨간불이다 — **S7 이 만든 것이 아니다**

`BACKLOG.md` **P-09a** 가 Owner 를 갖는다. **S7 은 자기가 넣은 것을 전부 고쳤고,
S6 이 남긴 것 하나를 함께 고쳤다**(`WorkBoard.jsx` 「스프린트 만들기」→「추가」 — 같은
규칙의 한 단어라 라우팅보다 고치는 것이 쌌다).

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) 7건 · `tokens.css` 드리프트 · S4 잔여 둘 | S5 가 기록한 넷 |
| `app/work/project_keys.py:152` 의 가운뎃점 | S6 |
| `ko-wordbreak.test.jsx:179` 안 닫힌 JSX 주석 | `dac17928` |
| `SettingVersions.jsx:75` 의 「변경」(표준 동사표는 「수정」) | `c1bd9306` |
| `settings-coerce.test.jsx` 「검증 통과」 미표시 | S6 이전 |

## NOW

**S7 은 끝났다.** 본문의 정본이 블록이 되고, 그 블록에 이름이 붙었다.

이 세션에서 가장 값이 나간 것은 표를 만든 것이 아니라 **파생을 만들 수 있는 자리를 하나로
묶은 것**이다. Markdown 과 Plain Text 는 정본에서 나오고, 폴더의 경로는 트리거에서 나오고,
멘션 표는 현재 판에서 나온다. 셋 다 「조심해서 쓰자」로 막을 수 있는 성질이 아니다 —
갈라져도 오류가 안 나고, 갈라진 뒤에는 어느 쪽이 맞는지 알 방법이 없기 때문이다.

두 번째는 **오류를 안 내는 결함 셋을 잡은 것**이다(위 절). 셋 다 「기능이 안 된다」로
드러나지 않는다 — 번들은 빌드에 성공하고, 활동 시각은 그럴듯하고, 목록은 최신순으로
보인다. 그런 결함은 시험이 없으면 영원히 안 잡힌다.

## NEXT — 다음 시작점: S8 (요청 시)

**S8 = File Storage Providers.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 설계 요지는 §5.3(D-199).

S7 이 다음 Session 에게 넘기는 것:

1. **`document_attachments` 는 S7 이 안 만들었다 — 일부러다.** 첨부는 `files` 를 가리키고
   `files` 는 `storage_providers` 를 가리킨다(D-199). 저장소 없이 첨부 표만 만들면 그
   컬럼이 무엇을 가리키는지 정하지 못한 채 굳는다. **S8 이 셋을 함께 만든다.**
   붙일 자리는 `documents.id` 이고 CASCADE 규약은 `document_tags` 와 같다.
2. **권한 어휘 `STORAGE_CONFIGURE` 는 이미 있다** (S5 가 미리 고정했다). 새 이름을 짓지
   말고 그것을 쓰고, 소비처를 연결한 뒤 `tests/unit/test_identity_access_seed.py` 를 본다 —
   S7 이 `SPACE_*` 에 그렇게 했다.
3. **쓰기 입구를 하나로 두는 검사가 이제 도메인 단위다.** `scripts/check_domain_single_source.py`
   의 `RULES` 에 한 줄 더하면 그 규칙이 app 전체에서 지켜진다. S8 의 `st_dev` 가드(D-199 13번)가
   정확히 같은 성질을 요구한다 — **마운트 판정이 두 곳이면 그중 하나가 빠진 날 로컬 디스크에
   조용히 쌓인다.**
4. **파일 크기·MIME 는 화면 계약이 아직 없다.** `documents` 상세 응답에 첨부 칸을 더할 때
   `_document_json`(`app/knowledge/router.py`) 한 곳만 고치면 된다 — 직렬화가 그 파일에
   모여 있다.
5. **날짜를 저장할 일이 있으면 `app/core/dates.py` 를 지난다** (D-248). 백업 만료·마운트
   점검 시각이 그 부류다. 새 파서를 만들지 않는다.
6. **`kit.jsx` 는 S7 도 안 건드렸다.** S8 과 겹치지 않는다.

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| R15 | LXD 컨테이너가 실 장비와 다르다 | **절반 해소**(재부팅 축은 D-229). **Storage(NFS/SMB)는 여전히 컨테이너에서 검증되지 않는다** → S8 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| R17 | pgvector 검색 품질 | S10(하이브리드 가중치) |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐다** (2026-08-22 · D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). **지금 적용된 프로젝트는 0건이고 그것이 정상이다** — PG 의 `projects` 가 비어 있다(적재는 S13) |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz>` 로 언제든 다시 돈다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다 |
| **리허설 소스 tarball** | 작업 트리를 그대로 tar 로 만들어 넣는다(`.git`·`node_modules`·`docs`·`tests`·`var` 제외). **LF 로 저장돼 있어야 한다** — Windows 에서 파이썬으로 파일을 다시 쓰면 기본이 CRLF 다(S7 이 한 번 밟았다) |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다 — `tls.py` 가 파이썬과 Node 양쪽에 심는다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). `CLOVIR_TEST_PG_URL` 로 덮어쓴다 — 주소는 `postgresql+psycopg://` 로 적는다(`psycopg2` 는 안 깔려 있다) |
| **전 회귀를 백그라운드로 돌릴 때 (Windows)** | **`run_full_regression.sh` 가 이제 스스로 `< /dev/null` 을 붙인다** (P-09e). 근본 조치(시험이 `stdin=subprocess.DEVNULL` 을 넘기는 것)는 P-09e 가 소유한다 |
| **회귀 결과를 읽을 때** | **파이프 뒤에서 읽지 않는다.** `pytest … \| grep …` 의 `$?` 는 **grep 의 종료코드**다 — 시험이 실패해도 grep 이 한 줄이라도 찾으면 0 이 나온다. S7 이 여기서 두 번 속아 실패 8건을 「통과」로 읽었다. 파일로 받고(`> out.txt 2>&1`) 종료코드를 따로 찍은 뒤 그 파일을 본다. 그리고 **도는 시험 아래에서 `git stash` 를 하지 않는다** — 그 회차의 결과는 무엇이든 믿을 수 없다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | 시험 Storage 로 실검증. 실 정보 수령 시 **Configuration 만** 변경 (U8·U9) — **S8 이 바로 쓸 입력이다** |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
