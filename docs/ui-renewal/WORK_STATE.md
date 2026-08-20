# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-21T00:00:00+09:00
- wave: W5
- wave_status: **완료.** 그리고 **W5B~W15 는 이 시점부터 동결**이다 — 근거 **D-207**.
  이 축의 재개는 Wave 가 아니라 **Session S15~S20** 이다. 아래 NEXT 의 재배치 표가 정본이고,
  계획 전체는 `docs/platform/MASTER_PLAN.md` §14 다
- **동결 중 이 파일이 뜻하는 것**: `wave: W5` 는 「W5 까지 끝났다」는 사실이고, Gate 를
  `--stage wave`(W5)로 돌리면 그 범위를 검사한다. **W5B 로 올리지 않는다** — 올리면 게이트가
  아직 시작하지 않은 범위를 검사한다
- build_index_sha256: `08b5525cb2f52618` — 서버가 서브 중인 것이자 **After 의 지문**.
  W4 `1a48d92ee9e55127` · W3 `c03113861aaa5138` · W2 `344ce7e7fc221246` · W1 `104e49366bf030f4`
  · Before `9ab4d470163e475a`. 소스 지문 `BUILD_STAMP.source_hash` `bc8008f97def`
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W5**) **PASS** (억제 0건).
  W5 가 게이트에 둘을 더했다. **C10c** — 「승격된 Assertion 이 실제로 `--fail-on` 으로 걸린 채
  돌았는가」(W0~W4 는 승격을 **선언만** 했다). **C0** — 「선언한 After 가 이번 Wave 의 전량
  실행인가」(`capture_labels.after` 가 W1 값 그대로여서 W2·W3·W4 게이트가 W1 의 측정을 보고
  초록이 됐다). 뿌리는 증거를 **모으는 손과 가리키는 손이 달랐다**는 것이다
- static_checks: **STATIC_CHECKS_OK** (`check_label_above.py` · `check_qa_target_host.py` 포함)
- tests: frontend `npx vitest run` **2,409 PASS / 0 FAIL**(파일 322) ·
  `check_test_strength.py --base 1c7d8c07` **OK** · runner `test_assistant.py` **293 PASS** ·
  backend `run_full_regression.sh` **FULL_REGRESSION_OK**(4청크). W5 는 `app/**/*.py` diff 0 이다
- 프로브 반례: `probe_selftest` **PROBE_SELFTEST_OK (19 사례)**. W5 는 판정 규칙을 **여덟 번 좁히고
  세 번 넓혔다 — 한 번도 끄지 않았다**
- 실측 (`w5-after` 9뷰포트 × 2테마 전량 — **W1~W4 가 한 번도 안 돌린 범위다**):
  승격 다섯 중 넷이 fail 0 — `header_cell_alignment_mismatch` 578/0 · `plain_dropdown_for_entity`
  306/0 · `isolated_control_row` 1,089/0 · `control_baseline_mismatch` **1,381/0**.
  다섯째 `numeric_alignment` 는 18/182 — 13 Route 의 표 정렬 부채로 **S16(구 W6) 소유**
- open_findings: Surface Finding **339건 전수** · 별도 원장 **173건** 중 **81건 CLOSED**.
  남은 **92건은 전부 소유 Wave 가 있고**, 그 Wave 는 아래 표대로 Session 으로 이관됐다.
  **W5 소유 잔여 0**
- reviewers: 구현하지 않은 독립 3 렌즈가 **24건** 제기 → 상위 10건 반증 검증 → **확정 6 · 기각 4**.
  핵심은 «내가 만든 검사가 내가 만든 결함을 못 봤다» — 노치 라벨이 absolute 라 **모든 MUI 입력**이
  «두 줄» 로 세져 탈락률 100% 였고, 반례 17 사례는 전부 맨 `<button>` 이라 그 실명을 구조적으로
  못 잡았다. 근거·수치는 **D-186**
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 접속·배포·QA 값은
  `dist/ops/server.env`(gitignore). 배포는 사람 없이 돈다 — `scripts/apply-static-update.sh`
- commit: `d41d94e5`(W5 구현·번들·캡처 995장·Control Plane) · `60f8fafb`(W5 문서) ·
  동결 선언 = S0 커밋
- plan: `docs/ui-renewal/PLAN.md`(UI 축 정본) · `DIRECTIVE_v7.txt`(원 지시서) ·
  **`docs/platform/MASTER_PLAN.md`(제품 전체 정본 — 여기가 상위다)**

## NOW
**W5B~W15 동결.** UI 축은 여기서 멈추고, 제품은 데이터 계층부터 다시 세운다.

동결하는 이유는 UI 작업이 덜 중요해서가 아니라 **W5B~W15 의 검증 대상이 곧 사라지기 때문**이다.
W5B 는 Legacy Notion Query 를 대상으로 Search/Filter 정확성을 재려 하고, W8 의 Pilot 8종에는
없어질 Route 가 들어 있으며, W12 의 관리자 44 Surface 에는 Notion·SQLite 화면이 있다.
**지금 실행하면 두 번 일한다.**

Notion 을 System of Record 에서 내리고 PostgreSQL 을 정본으로 세우는 전환이 시작됐다(**D-187**).
그 전환은 Route 집합과 도메인 어휘를 바꾸므로, **새 IA 가 실재한 뒤에** UI 축을 재개한다.

**W0~W5 자산은 폐기하지 않는다**(U6) — `theme.js` · `kit.jsx` · `FilterBar`/`filters.jsx` ·
`EntityCombobox` · `navConfig` · Control Plane 3종 · Assertion 34종 · `probe_selftest.py` ·
프런트 테스트 전량. 이 축이 만든 것은 부품과 계측이고, 그 둘은 데이터 계층이 바뀌어도 산다.

**W5B 의 목적은 반드시 남긴다**(U7). 없애는 것은 **대상**이지 목적이 아니다.

## NEXT
**이 파일이 지목하는 다음 작업은 없다.** 다음 작업은 `docs/platform/WORK_STATE.md` 가 지목한다.
UI 축 재개는 그 계획의 **Phase E** 이고, 그때 이 파일을 다시 연다.

재배치 표(정본은 **D-207** · `docs/platform/MASTER_PLAN.md` §14.3):

| Wave | 판정 | 재배치 | 넘긴 Finding |
|---|---|---|---|
| **W5B** | **REDEFINE** — 목적 보존, 대상 교체 | **S15** (새 PG Query·Relation 대상 8단계 사슬) | — |
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
`--stage wave` → **구현하지 않은 에이전트**의 독립 검수. `check_test_strength.py` 는
`--base <직전 Session 커밋>`. 전량 캡처는 **S22 에서 한 번뿐**이다(D-208 E8).

## BLOCKERS
- 없음. 동결은 Blocker 가 아니라 **결정**이다(D-207).
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
