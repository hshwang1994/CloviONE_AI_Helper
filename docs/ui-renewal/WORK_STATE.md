# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-20T13:57:31+09:00
- wave: W5
- wave_status: **완료** — 구현·측정·독립 검수 반영·Exit Gate 까지 끝났다. 다음은 W5B
- build_index_sha256: `08b5525cb2f52618` — 서버가 서브 중인 것이자 **After 의 지문**.
  W4 `1a48d92ee9e55127` · W3 `c03113861aaa5138` · W2 `344ce7e7fc221246` · W1 `104e49366bf030f4`
  · Before `9ab4d470163e475a`. 소스 지문 `BUILD_STAMP.source_hash` `bc8008f97def`
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W5**) **PASS** (억제 0건).
  이 Wave 가 게이트에 둘을 더했다. **C10c** — 「승격된 Assertion 이 실제로 `--fail-on` 으로
  걸린 채 돌았는가」. W0~W4 는 승격을 **선언만** 하고 한 번도 그 플래그를 안 붙였고, 그래서
  W0 승격 세 검사는 계속 빨간 채였다(아무도 몰랐다). **C0** — 「선언한 After 가 이번 Wave 의
  전량 실행인가」. `capture_labels.after` 는 W1 이 적은 `w1-after` 그대로여서 **W2·W3·W4 의
  게이트가 W1 의 측정을 보고 초록이 됐다.** 뿌리는 손이 둘이었다는 것이다 — 증거를 모으는
  손과 가리키는 손이 달라 갈라졌다. 이제 `collect_evidence --into after` 가 둘을 함께 갱신한다
- static_checks: **STATIC_CHECKS_OK** (신규 `check_label_above.py` · `check_qa_target_host.py` 포함)
- tests: frontend `npx vitest run` **2,409 PASS / 0 FAIL**(W4 대비 +62, 파일 322) ·
  `check_test_strength.py --base 1c7d8c07` **OK** · runner `test_assistant.py` **293 PASS** ·
  backend `run_full_regression.sh` **FULL_REGRESSION_OK**(unit·regression·security·integration
  4청크). W5 는 `app/**/*.py` diff 0 이다
- 프로브 반례: `probe_selftest` **PROBE_SELFTEST_OK (19 사례)** — 판정 규칙을 고친 커밋에서
  «결함은 잡히고 정상은 안 잡힌다» 를 합성 DOM 으로 확인한다. 이 Wave 는 규칙을 **여덟 번
  좁히고 세 번 넓혔다 — 한 번도 끄지 않았다**
- 공유 계층 실브라우저 **재검증**(최종 빌드): `filter_e2e`(신설) **면 계약 32/32 + 키보드 사슬
  PASS** · `shell_e2e` 12 Flow(9건 사슬 4/4) · `nav_e2e` **18/18** · `kit_e2e` **40/40 · 판 안의
  판 0자리**. 캡처가 증명하는 것은 Assertion 재측정이지 셸·kit 고유 계약이 아니다(D-184)
- 실측 (`w5-after` {ROUTES} Route × 2테마 × **9뷰포트** = **{PAGES}페이지**)
  — **W1~W4 가 한 번도 안 돌린 9뷰포트 전량 실행이다**(F-W4-21). 5개 뷰포트가 W0 이후 처음 측정
  · **승격 다섯 중 넷이 fail 0** — `header_cell_alignment_mismatch` 578/0 ·
    `plain_dropdown_for_entity` 306/0(W4 는 fail 80) · `isolated_control_row` 1,089/0
    (W4 는 **구조적으로 잴 수 없었다**) · `control_baseline_mismatch` **1,381/0**(W4 는 fail 134).
    다섯째 `numeric_alignment` 는 18/182 — 13 Route 의 표 정렬 부채로 W6 소유다
  · `control_baseline_mismatch` 의 skip 은 112 뿐이다 — 독립 검수가 잡은 실명을 고친 뒤
    **W4 보다 더 많이 재고도 fail 0** 이다(눈멀었던 판정은 874/0/620 이었다). 「위반 0」 이
    「안 재고 통과」 가 아님을 이 숫자가 말한다
  · **W4→W5 셀 대조**(겹치는 4뷰포트): fail→아님 **254** · 신규 fail **68** ·
    skip→실측 **282** · 실측→skip **400**
  · 신규 fail 68 은 전부 advisory 계열이고 대부분 **문턱을 넓혀 처음 보이게 된** 자리다.
    실측→skip 400 중 `equal_column_split` 254 는 **결함이 사라져 잴 대상이 없어진** 것이다
    (필터의 균등 격자가 없어졌다 · 같은 클래스 fail 32 동시 종료). 전부 소유 Wave 로 등록
  · 처음 잰 5뷰포트 중 **고유 정보를 낸 것은 둘**(2560x1440 · 768x1024)이라 그 둘만 커밋
    증거에 넣었다 — 측정 원본 `results.json` 에는 9뷰포트 전량이 있다
- 승격 결과: `isolated_control_row`·`control_baseline_mismatch` 가 W5 에서 `--fail-on` 으로
  승격돼 **1,494페이지 전량에서 초록**이다. W0 승격 세 검사도 이번에 처음으로 그 플래그를 달고
  돌았다 — 그중 둘은 초록, `numeric_alignment` 만 빨갛고 그 부채는 W6 소유로 등록돼 있다
- open_findings: Surface Finding **339건 전수** — 이번 실행이 **60건을 닫고 16건을 새로
  등록**했다. 별도 원장 **173건**(착수 전 12렌즈 조사 165 + 종료 검수 8) 중 **81건 CLOSED**,
  남은 92건은 **전부 소유 Wave 가 있다**(W8 26 · W6 20 · W12 13 · W10 11 · W15 6 · W13 4 ·
  W14 4 · W9 4 · W7 4). W5 소유 잔여 **0** — 화면 소유 작업 11건은 이유를 적어 이관했다
- reviewers: 구현하지 않은 독립 3 렌즈가 **24건** 제기 → 상위 10건을 반증 시도 에이전트가
  검증 → **확정 6 · 기각 4**(F-W5R-01~07). 확정 여섯을 전부 고쳤고 그 과정에서 같은 뿌리의
  결함 넷이 더 드러났다. 핵심은 «내가 만든 검사가 내가 만든 결함을 못 봤다» — 노치 라벨이
  absolute 라 **모든 MUI 입력**이 «두 줄» 로 세져 탈락률 100% 였고, 반례 17 사례는 전부 맨
  `<button>` 이라 그 실명을 구조적으로 못 잡았다. 기각 넷은 수치는 실재하나 결론이 안 따라왔다
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 접속·배포·QA 값은
  `dist/ops/server.env`(gitignore). 배포는 사람 없이 돈다 — `scripts/apply-static-update.sh`
- commit: `{COMMIT}` (W5 전체 — 소스 · 번들 · 캡처 · Control Plane)
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
W5(Search/Filter/Form). **탐색 줄은 판이 아니고, 폭은 종류가 정하고, Entity 는 고르는 것이다.**

필터를 감싸던 `c-toolbar-card` 를 걷어냈다(`/policies` 의 1610×108 판은 잉크 폭 비 0.43).
그 자리를 대신하는 것은 아래 실선 하나와 **결과 줄**이다 — 「조건 N개, 결과 M건」이 필터와
목록 **사이**에 서서 둘의 관계를 만든다. 폭은 균등 격자가 아니라 종류가 정한다
(`CONTROL_KIND` 일곱) — 「상태: 전체」와 「P. SK 하이닉스 [용인 클러스터 대비]」가 같은 255px 를
받던 상태가 사라졌다.

**Entity 는 고르는 것이지 옮겨 적는 것이 아니다.** 「‘사용자’ 화면에서 ID를 복사해 붙여
넣으세요」가 열두 자리 있었다. 후보가 실재하는 열 자리를 검색형 Combobox 로 바꾸고, 후보가
**세상에 없는** 자리는 `freeTextReason` 에 이유를 문장으로 선언한다 — 그 문장이 DOM 에 그대로
남아 프로브가 같은 판단을 공유한다. 억제가 아니다: `plain_dropdown_for_entity` 는 끌 수 없는
검사이고, 여기서 말하는 것은 «이 칸은 애초에 선택기가 될 수 없다» 다.

이번 Wave 가 배운 것 셋.

**하나 — 잴 수 없던 자리가 잴 수 있는 자리보다 위험하다.** 승격했다고 적힌 검사가 한 번도
`--fail-on` 으로 걸린 적이 없었고(C10c), 게이트가 읽는 After 포인터는 세 Wave 낡아 있었으며
(C0), `plain_dropdown_for_entity` 는 `select` 만 순회해 **가장 나쁜 형태**(맨 텍스트 상자)를
664 page-instance 에서 전부 skip 했다. 셋 다 «위반 0» 으로 보였다.

**둘 — 프로브를 좁히는 것과 끄는 것은 다르다.** 실브라우저의 «위반» 다섯 화면 중 넷이
위양성이었고(문서 밖 서랍 · 흐름에 없는 것 · 접힌 글 · 키가 다른 둘의 중심선), 좁힌 자리마다
반례를 넣었으며 같은 손으로 **세 번 넓혔다**. 전량 실행이 하나를 더 잡았다: 작은 텍스트
버튼(30)과 작은 아이콘 버튼(34)이 **토큰 때문에** 갈렸는데 1920 에서는 차이가 정확히 4.0 이라
문턱을 아슬아슬하게 통과하고 2560(루트 18px)에서만 드러났다. `size` 가 높이를 정하게 고쳤다.

**셋 — 검사가 눈을 감으면 «위반 0» 이 «결함 0» 처럼 보인다.** 독립 검수가 그것을 잡았다:
「두 줄로 접힌 글은 컨트롤이 아니다」 규칙이 **모든 MUI 입력**을 함께 떨어뜨렸고(노치 라벨이
absolute 다), 반례 17 사례는 전부 맨 `<button>` 이라 그 실명을 구조적으로 못 잡았다.
눈을 뜨자 같은 함정이 화면 머리에서 네 자리 더 나왔다. 근거는 **D-186**.

## NEXT
1. **W5B(필터 결과 정확성)** 를 시작한다. C7 계약 — 고른 조건이 서버 질의와 결과에 실제로
   반영되는가, 조합 필터가 서로를 지우지 않는가, 주소 복원이 같은 결과를 주는가.
   입력이 준비돼 있다: `filter_e2e.py` 가 이미 한 사슬(combobox → 주소 → 질의 → 결과)을
   재고 있고, 그 축을 화면 전체로 넓히는 것이 W5B 다.
2. Wave 마다: **CHECKPOINT 의 `wave:` 를 먼저 올린다** → 구현 → focused test → 배포 →
   실브라우저 재캡처 → `collect_evidence --into after`(이제 `after_capture`·`capture_labels`
   까지 스스로 갱신한다) → `merge_qa_findings --write` → `--stage wave` → **구현하지 않은
   에이전트**의 독립 검수. 종료 시험 셋(PLAN:992) — `run_full_regression.sh` · `npm test` ·
   runner `test_assistant.py`. 공유 파일 Wave 면 9뷰포트 × 2테마. `check_test_strength.py` 는
   `--base <직전 Wave 커밋>`. 리뷰 Workflow 는 `…/scratchpad/w5-review.js` 를 복제해 쓴다.
3. 그 뒤 W6 → W7 → W8(Pilot 8종) → W9~W15. **W5 가 넘긴 것 92건은 전부 소유 Wave 가 있다**.
   W6(20) — `numeric_alignment` 부채 · `equal_column_split` · 폼 치수 토큰 · `ModalActions` 패딩 ·
   **문턱 단위**(F-W5D-165: 허용오차가 절대 px 인데 컨트롤은 rem 이라 같은 DOM 이 2560 에서만
   걸린다 — 문턱을 완화하는 변경을 «초록이 됐다» 는 커밋에 넣으면 그것이 골대 옮기기라 안 고쳤다).
   W8(26) — Archetype · `/sprint`. W14(4) — 모달 내부(F-W5D-130·80·162). W9(4) — 폼 화면.
4. 승격 예정 Gate: `equal_column_split`·`column_width_vs_content`·`brand_role_coverage` → W6 ·
   `mascot_visible_size` → W7 · `detail_side_imbalance` → W9.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
