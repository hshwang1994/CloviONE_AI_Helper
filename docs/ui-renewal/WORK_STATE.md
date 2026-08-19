# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-19T16:10:00+09:00
- wave: W1
- wave_status: 완료 — Exit Gate E1~E7 충족. 다음 세션이 **W2(Global Shell)** 를 시작한다
- build_index_sha256: `104e49366bf030f4` — 서버가 서브 중인 것이자 **After 의 지문**.
  원격 shell 로 직접 계산(D-175). Before 는 `9ab4d470163e475a` — 둘이 달라야 before/after 다
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(W1) **PASS** (억제 0건)
- static_checks: **STATIC_CHECKS_OK** — 신규 2종 포함
  (`check_brand_tokens.py` BRAND_TOKENS_OK · `check_test_strength.py` TEST_STRENGTH_OK)
- tests: frontend `npx vitest run` **2,246 PASS / 0 FAIL** ·
  backend `run_full_regression.sh` **FULL_REGRESSION_OK**(2,903건, 32m30s)
- after_capture: `--label w1-after` 전 84 Route × 2테마 × 1920 = 166페이지
  (`dist/ui-qa/w1-after/`, gitignore). Before 는 W0 의 1,494장 그대로 유효하다
- brand 실측 (1920 기준, Before 332p → After 166p 이므로 **비율**로 읽는다)
  · `brand_presence` fail **96.4% → 43.4%** (pass 12 → 94)
  · `brand_role_coverage`(신설, 있는 role 이 전부 Brand) pass 78 / fail 88
  · 남은 실패는 **아직 만들지 않은 자리**다: `highlight` 38(W4) · `selected_state` 52(W6) ·
    `ai_surface` 2(W7) · `primary_action` 4
  · `control_baseline_mismatch` fail **55.4% → 9.6%** (CONTROL 높이 통일의 부수 효과)
- reviewers: 구현하지 않은 독립 에이전트 **5 렌즈 × 81 에이전트**, 전 Finding 적대적 검증
  (Workflow `wf_75399743-a02`). 제기 76 · **확인 46** · 반증 30.
  확인분 + 실측 대조 2건 = 48건을 `ROUTE_COVERAGE.w1_review_findings` 에 등록했고
  **W1 소유 OPEN 0건**(14건 W1 내 해소, 34건은 소유 Wave 로 라우팅)
- open_findings: 227(W0 Before 측정 파생) + F-0100(High, W12) + 위 34건
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71 (두 이름 모두 200).
  접속·배포·QA 값은 `dist/ops/server.env`(gitignore). 배포는 사람 없이 돈다 —
  `scripts/apply-static-update.sh`(정적) · `scripts/apply-app-update.sh`(템플릿·파이썬, 헬스게이트+롤백)
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
W1(Brand Foundation) 이 끝났다. **제품이 인디고 하우징을 갖는다** — 상단바와 사이드바가 같은
`chrome.shell` 이고, 캔버스·판·실선이 인디고 계열 중립 램프이며, Brand 는 사용자 Accent 로
지울 수 없는 별도 계층(`palette.chrome`·`brand`·`gradient`·`chart`)이 됐다. 방향 전환의
근거·유지한 것·뒤집은 것은 `docs/DECISIONS.md` **D-179**, 측정 해석은 **D-180**.

계획서의 W1 Exit Gate `brand_presence ≥5/7` 은 **도달 불가여서 정정했다**(D-180): Before
1,494페이지에서 role 존재 수가 5를 넘는 페이지가 **0개**였다. 기준을 낮추는 대신 같은 측정에서
질문을 하나 더 만들었다 — `brand_role_coverage`("있는 자리는 전부 Brand 인가"). 절대 기준은
W15 완료 조건으로 남는다. 그것을 초록으로 만드는 유일한 정직한 길은 W4·W6·W7 이 빠진 role 을
실제로 **만드는** 것이다.

독립 리뷰가 W1 을 통과시키지 않고 **실제 결함 넷을 잡았고 그 자리에서 고쳤다**:
① 인디고 셸 위 워드마크 "Assist" 대비 **2.32:1**(옛 셸에서는 3.88) → `chrome.wordmark`
`#B7C4FA`(6.85~10.06)를 CSS 변수 상속으로 배선 ② 라이트에서 셸 위 포커스 링이 **1.38~1.83:1**
로 사실상 소실 → `--clovir-focus-ring` 상속(9.15:1), 덤으로 '본문 바로가기' 링크가 UA 기본
외곽선을 쓰던 것도 해소 ③ `brand_presence` 프로브가 근사 검정 본문 잉크(`#161A2C`)를 Brand 로
세던 위양성 → 극단 명도 가드 추가(이 수정으로 `highlight` 실패가 12→38 로 **늘었다** — 숫자가
나빠지는 방향이 정직한 방향이다) ④ 비활성 버튼을 주요 행동으로 세던 위양성.

## NEXT
1. **W2 Global Shell** 을 시작한다. 소유 파일 `frontend/src/app/AppShell.jsx`(셸부) ·
   `TopSearch.jsx` · `TopBrand.jsx` · `styles/root.css`. 전제 W1 충족.
   **입력이 이미 준비돼 있다** — `ROUTE_COVERAGE.w1_review_findings` 에서
   `owner_wave == "W2"` 5건이 W2 의 작업 목록이다. 가장 무거운 것(F-W1R-13, High):
   *인디고 하우징에 순백 구멍* — `TopSearch.jsx:40` · `AppShell.jsx:328`(메뉴 찾기) ·
   `Mascot.jsx:264`(클로비 버튼)이 아직 `background.plate` 를 쓴다. 라이트에서는 셸 안에서
   가장 밝은 면이 되고 다크에서는 셸에 묻힌다. **토큰은 이미 있다**: `chrome.track`(.08/.10) ·
   `chrome.trackSelected` · `chrome.edge` — `theme.js` 의 그 주석이 소비처로 "ConsoleSwitch·
   **검색 inset**"을 명시하는데 W1 은 둘 중 하나만 배선했다.
   함께: `chrome.shellImage`(사이드바 `backgroundImage`)와 `chrome.aiWash`(상단바 우상단)가
   소비처 0이라 셸이 아직 평평하다(F-W1R-39) · main padding·content width·`narrow_main` 3840 ·
   `topbar-contract.test.jsx` 재작성 · 워드마크가 제품명을 'Clovir Assist' 두 단어로 그리는 건
   (F-W1R-34).
2. Wave 마다: 구현 → focused test → 배포(`apply-static-update.sh`) → 실브라우저 재캡처
   (`--routes all --themes light dark --viewports 1920x1080 --label w2-after`) →
   `--stage wave` → **구현하지 않은 에이전트**의 독립 Visual/Requirement Reviewer.
   리뷰 Workflow 는 `…/workflows/scripts/w1-brand-foundation-review-*.js` 를 복제해 쓴다 —
   렌즈 5개와 적대적 검증 단계가 그대로 재사용된다.
3. 그 뒤 W3(Navigation·Icon) → W4(공유 Primitive) → W5·W5B(Filter 설계·기능 정확성) →
   W6(Table·Inline Edit) → W7(Empty·Clovi·Chart) → W8(Pilot 8종) → W9~W15.
   순서와 소유 파일은 PLAN «Wave 계획» 표가 정본이다.
4. 승격 예정 Gate: `brand_role_coverage` → **W6** 부터 `--fail-on`(선택 표현 계약이 정해진 뒤) ·
   `mascot_visible_size` → W7 · `isolated_control_row`·`control_baseline_mismatch` → W5 ·
   Table 4종 → W6.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
