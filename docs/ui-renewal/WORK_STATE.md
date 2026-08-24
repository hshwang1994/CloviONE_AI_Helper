# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-24T20:00:00+09:00
- wave: W5B
- wave_status: **완료 (S15).** 동결이 풀렸고 진행 단위는 Wave 가 아니라 **Session S15~S20**
  이다 — 재배치 표는 아래 NEXT, 계획 전체는 `docs/platform/MASTER_PLAN.md` §14 다
- build_index_sha256: `c9cab277de958811` — **S15 캡처(`s15-after`)가 찍은 번들**.
  W5 `08b5525cb2f52618` · W4 `1a48d92ee9e55127` · W3 `c03113861aaa5138` ·
  W2 `344ce7e7fc221246` · W1 `104e49366bf030f4` · Before `9ab4d470163e475a`.
  소스 지문 `BUILD_STAMP.source_hash` `9477754b5121`
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W5B**) **PASS** (억제 0건).
  S15 가 셋을 더했다. **C11 의 검사 범위가 Wave 가 아니다** — 조건 Flow 를 PASS 라고 적은
  Surface 는 전부 검사한다(조건 축을 고치는 Session 은 화면을 소유하지 않아서 이 조건은 그동안
  **아무 Surface 도 안 보고 있었다**). **PASS 에 증거를 요구한다**. 그리고 **「이 머신에 없다」와
  「없다」를 가른다** — 캡처 실행이 하나도 없으면 종료코드 3 이고 통과로 접지 않는다
- static_checks: **FAILED — S15 가 만든 것이 아니다.** `check_test_strength.py` 가 기준
  `eec4886c` 대비 **15건**을 드는데 전부 S13·S14 가 남긴 선언 미비다(변경을 stash 한 채로 같은
  열다섯이 뜬다). S15 가 만든 한 건(`my-stats.test.jsx`)은 그 자리에서 선언했다. 소유는 **P-38**
- tests: frontend `npx vitest run` **2,379 PASS / 3 FAIL**(파일 320) — 그 셋은 **P-34**(S14
  이전부터 빨갛다, 소유 S17). backend `tests/unit` **1,362 PASS** · `tests/security` **759 PASS** ·
  `tests/integration` 4청크 전부 **OK** · `tests/regression` **445 PASS / 4 FAIL** — 그 넷은
  전부 S14 가 남겼다(**P-39**, 변경을 stash 한 채로 같은 넷이 뜬다). S15 신규 시험 19건 PASS
- 실측 (`s15-after` — 건드린 화면 11개 × 2뷰포트 × 2테마 = **44페이지**, E5 대로 변경
  Surface 만): 승격 다섯 중 넷이 fail 0. 다섯째 `numeric_alignment` 8건은 **S16 소유**의 표
  정렬 부채다. 실브라우저가 결함 하나를 새로 잡았다 — `/knowledge` 의 공간 선택기가 평범한
  드롭다운이었다(`plain_dropdown_for_entity`). 고치고 같은 검사로 확인했다(4 → 0)
- 조건 사슬 실측: `tests/regression/test_filter_chain.py` 가 목록 일곱 곳에서 **38회차**를
  돌린다. 기대 집합은 **전량 목록에 파이썬 술어를 적용해 직접 세고**, 서버의 SQL 과 갈리면
  실패다(표본이 판정력을 잃어도 실패). 원장은 `dist/ui-qa/s15-filter-chain/chain.json`
- open_findings: S15 가 **F-0010(Critical)** 을 닫았다 — 사용자가 신고한 「연결된 티켓이
  Filter 결과에서 누락된다」. 새로 등록 2건(`user_board`/`numeric_alignment` → S16 ·
  `user_knowledge`/`brand_presence` → S19), 재측정으로 닫힘 18건
- reviewers: 독립 에이전트 검수는 안 썼다 — 판정을 **두 구현의 대조**(SQL ↔ 술어)와 실브라우저
  검사로 세웠고, 고친 것마다 Known-Bad 를 되돌려 빨개지는 것을 확인했다(다섯 건)
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 값은 `dist/ops/server.env`.
  ⚠️ **S15 는 배포하지 않았다** — 캡처는 임시 데이터베이스 위에 앱을 띄워 찍었다
  (`scripts/ui_qa/local_capture.py`). 설치처 배포는 캡처의 전제가 아니라 별개의 결정이다
- commit: 아래 NEXT 참조 (S15 본체)
- plan: `docs/ui-renewal/PLAN.md`(UI 축 정본) · `DIRECTIVE_v7.txt`(원 지시서) ·
  **`docs/platform/MASTER_PLAN.md`(제품 전체 정본 — 여기가 상위다)**

## NOW
**동결이 풀렸다. S15 가 W5B 를 끝냈다** — 목적은 그대로였고 대상만 바뀌었다(U7): Legacy
Notion Query 가 아니라 **새 PG Query 와 Relation** 위에서 조건이 맞는지를 봤다.

이번 회차가 답한 질문은 하나다 — **결과가 맞는가.** 화면에서 값이 바뀌는 것은 정상 동작의
증거가 아니므로, 목록 일곱 곳에서 조건을 걸고 그 결과를 **전량 목록에서 직접 센 기대 집합**과
대조했다. 서버의 SQL 과 시험의 술어가 같은 질문에 따로 답한다.

그렇게 해서 나온 결함 여섯은 전부 **오류를 내지 않는** 종류였다:

* 담당자 축이 **새 계정을 가리키지 못했다** — 활성 15명 중 2명이 「내 티켓」이 영원히 비고
  담당자 후보에도 없었다. 화면은 **없어진 시스템에 연결을 요청하라**고 안내했다 (D-285)
* 주소에 이미 질의가 달린 목록은 조건이 **서버에 안 닿았다** — 알림 화면에 관리 알림이
  섞였고 「다음」을 눌러도 같은 20건이 왔다 (D-286)
* 스프린트의 프로젝트 조건이 **1,133건 전부에서 언제나 거짓**이었다 — 화면이 옛 relation
  축만 봤다. 같은 뿌리로 편집 모달의 프로젝트 칸도 늘 비어 보였다 (D-287)
* 문서 검색 상자가 주소와 갈라졌다 — 조건을 지워도 글자가 남아 화면이 없는 조건을 말했다
* 게시판·결재함이 **20건에서 조용히 잘렸다** — 건수를 적어 놓고 21번째부터는 열 길이 없었다
* 문서 목록 정렬이 전순서가 아니었다 — 같은 시각 문서 사이에서 쪽 경계가 행을 반복하거나
  빠뜨릴 수 있다(이관은 여럿을 한 회차에 적재한다)

**시험이 응답 모양을 흉내 내지 않으면 결함을 못 본다**는 것을 이번에도 겪었다 — 스프린트
픽스처가 `project_ids` 에 Portal id 를 넣어 두어, 화면이 옛 축만 보던 동안에도 초록이었다.

## NEXT
다음 작업은 **S16 — Table / Grid / Metadata / Alignment + Chart** 다 (Backlog **P-26**).
`numeric_alignment` 8건이 그 회차를 기다리고 있고, S15 의 캡처(`s15-after`)가 그 실측을
남겨 뒀다. 시작점은 `docs/platform/WORK_STATE.md` 이고 이 파일은 그 회차가 다시 연다.

S15 가 다음 Session 에게 넘기는 것 넷:

1. **조건 사슬을 다시 잴 수 있다.** `tests/regression/test_filter_chain.py` 에 목록을 한 줄
   더하면 그 화면의 조건이 같은 방식으로 검증된다 — 기대값을 손으로 적지 않는다.
2. **캡처를 설치처 없이 찍는다** — `scripts/ui_qa/local_capture.py` 가 임시 데이터베이스
   위에 앱을 띄우고 그 주소로 하네스를 부른다.
3. **C11 이 이제 실제로 검사한다.** 조건 Flow 를 PASS 라고 적으면 그 화면의 복합·쪽 초기화·
   경합·캐시 키·뒤로가기 Flow 가 함께 있어야 하고, PASS 에는 증거가 있어야 한다.
4. **범위 밖으로 넘긴 것 셋**: `numeric_alignment`(S16) · `user_knowledge`/`brand_presence`
   (S19) · 시험 강도 선언 미비 15건(**P-38**, S13·S14 가 남겼다).

재배치 표(정본은 **D-207** · `docs/platform/MASTER_PLAN.md` §14.3):

| Wave | 판정 | 재배치 | 넘긴 Finding |
|---|---|---|---|
| **W5B** | **REDEFINE** — 목적 보존, 대상 교체 | **S15 완료** (새 PG Query·Relation 대상 8단계 사슬) | — |
| W6 | KEEP(공유 부품) + MERGE(Inline Edit → Ticket 도메인) | **S16** | 20 |
| W7 | KEEP | **S17** | 4 |
| W8 | REDEFINE — Pilot 집합을 새 IA Archetype 으로 | **S18** | 26 |
| W9 | MERGE into S6·S7 + REMOVE(수동 동기화는 개념 소멸로 자동 해소) | **S6·S7 흡수** | 4 |
| W10 | REDEFINE(Route 집합 자체가 바뀐다) | **S19** | 11 |
| W11 | REDEFINE(새 IA 로 교체) | **S20** | — |
| W12 | REDEFINE(Notion/SQLite 화면 제거 후 재산정) | **S20** (W11 과 `navConfig.js`·`AdminRoutes.jsx` 공유 — 이 묶음만 합친다) | 13 |
| **W13** | **MOVE — 맨 앞으로** | **S3** (Identity·Hostname·TLS. 이후 증거가 한 origin 으로 모인다) | 4 |
| W14 | KEEP + 확장(Backlog·Sprint·Board·Space·Citation·Storage) | **S21** | 4 |
| W15 | KEEP + 확장(설치 Acceptance 포함) | **S22** | 6 |

승격 예정 Gate 는 소유 Session 을 따라간다: `equal_column_split`·`column_width_vs_content`·
`brand_role_coverage` → S16 · `mascot_visible_size` → S17 · `detail_side_imbalance` → S19.

동결 해제 시 지키는 것: Session 마다 **CHECKPOINT 를 먼저 올린다** → 구현 → focused test → 배포 →
**건드린 Surface 만** 재캡처 → `collect_evidence --into after` → `merge_qa_findings --write` →
`--stage wave` → **자기 Exit 조건이 요구하는 경우** 구현하지 않은 에이전트의 독립 검수.
`check_test_strength.py` 는 `--base <직전 Session 커밋>`.

**실행 규칙의 우선순위**: S15~S20 에는 `docs/platform/MASTER_PLAN.md` §9.3(**D-208**)이 우선한다.
`PLAN.md` 의 「Wave 종료마다 전체 Regression」·「전체 뷰포트 × 2테마 전량 실행」 조항은 **W0~W5 가
그렇게 했다는 기록**이고 재개되는 Session 에 적용하지 않는다 — **영향 Surface/범위만** 검증하고,
Whole-product Full Capture 는 **S22 최종 빌드에서 1회**다. **W0~W5 의 완료 기록과 Evidence 는
그대로 둔다.**

## BLOCKERS
- 없음. 동결은 Blocker 가 아니라 **결정**이다(D-207).
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
