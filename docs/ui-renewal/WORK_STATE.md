# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-19T12:45:00+09:00
- wave: W0
- wave_status: 완료 — Exit Gate 전부 충족. 다음 세션이 W1(Brand Foundation)을 시작한다
- build_index_sha256: 9ab4d470163e475a — 서버가 서브 중인 것이자 **Before 의 지문**.
  지문은 원격 shell 을 직접 받아 계산한다(D-175). 로컬 빌드는 `export` 추가분만 다르다
- coverage_gate: `--stage plan` **PASS** · `--stage wave` **PASS** (억제 0건)
- static_checks: **STATIC_CHECKS_OK** (`.git` 위생 포함 — D-178)
- surfaces_total: 92 (route 68 · tab 14 · state_variant 4 · widget 6). 전부 Archetype 분류,
  전부 Before 캡처 연결, 주요 82개 전부 요구사항 매핑
- harness_routes: 84 화면 + 별칭 4 (별칭은 화면이 아니다 — D-170)
- archetype_gap: 19 Surface 의 현재 모습이 목표 Archetype 과 다르다 (list_table 49→35)
- functional_flows: 1,212 / 88 Surface (27개 범주 전수, `NOT_AUDITED` 초기값)
- before_capture: `--label before-renewal` 1,494장(84 Route × 2테마 × 9뷰포트) 실행 완료.
  커밋본은 대표 3조합 252장(12MB) — 1920 light/dark + 3840 light. 전량은
  `dist/ui-qa/before-renewal/`(gitignore)에 있고 각 행의 `results_json` 이 가리킨다
- open_findings: 227 (Before 측정에서 파생) + F-0100(High, W12).
  `ROUTE_COVERAGE.w0_open_questions` 에 판단 대기 12건
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 접속·배포·QA 값은
  `dist/ops/server.env`(gitignore). sudo 확인됨 — 배포는 사람 없이 돈다.
  QA 계정 `hshwang@goodmit.co.kr`(system_admin, Notion verified) → `내 …` 화면 실데이터
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
W0 이 끝났다. Gate 가 소스를 직접 읽고 판정하며 `--stage wave` 가 통과한다.
**제품 화면 코드는 한 줄도 바뀌지 않았다** — `AdminRoutes.jsx`·`SettingsShell.jsx` 변경은
`export` 키워드뿐이라 렌더 결과가 같다. Before 는 진짜 Before 다.

Before 측정이 지시서의 진단을 숫자로 확인했다 (1,494페이지):
`brand_presence` **1,452 fail / 42 pass** — 통과한 42장은 전부 로그인 화면이다.
제품 Brand Language 의 정본이 로그인에만 있고 앱 내부가 그것을 배신한다는 계획서 판단이
측정으로 재현됐다. 그 다음: `control_baseline_mismatch` 826 · `dead_blank_region` 348 ·
`numeric_alignment` 182 · `plain_dropdown_for_entity` 180(**pass 0**) ·
`oversized_empty_surface` 105 · `equal_column_split` 76 · `vertical_text_collapse` 22.
`header_cell_alignment_mismatch` 와 `mascot_visible_size` 는 fail 0.

Gate 를 세우며 커버리지가 거짓말하던 자리를 찾았다(D-170~D-173). 가장 무거운 것:
`/admin-notifications`(사이드바 '관리 알림')가 하네스에도 커버리지에도 없어 한 번도 캡처된
적이 없었고, 하네스의 `admin_notifications` 는 존재하지 않는 `/admin#/notifications` 를 찍어
**catch-all 404 위에서 21개 검사를 통과**시키고 있었다.

## NEXT
1. **W1 Brand Foundation** — `frontend/src/ui/theme.js` → `scripts/generate_design_tokens.mjs`
   → 두 `tokens.css` → `theme-contract.test.js`·`tokens-generated.test.js` 재작성.
   **한 에이전트·한 커밋 시퀀스**(공유 파일 충돌 위험). 값은 PLAN «Design Direction —
   인디고 계측면» 이 hex·대비값까지 정해 뒀다: `palette.chrome` 신설 · `brand` 6키 추가 ·
   새 기본 Accent `#5A4FCF` · 중립 램프 인디고화 · Typography 7슬롯 재배치 · Radius `{6,8,14,999}`.
   **반증 가능한 판정 기준**: `blue(chrome.shell) − red(chrome.shell) ≥ 24`
   (현재 `#E7EAEE` → 7 ✗ / 목표 `#1E2758` → 88 ✓). 이 단언이 없어서 지금 상태가 통과했다.
   Exit Gate: smoke set × 두 테마에서 `brand_presence ≥ 5/7`, `theme-contract` 원래 강도 통과.
2. 그 뒤 W2(Global Shell) → W3(Navigation·Icon) → W4(공유 Primitive) → W5·W5B(Filter 설계·
   기능 정확성) → W6(Table·Inline Edit) → W7(Empty·Clovi·Detail) → W8(Pilot 8종) → W9~W15.
   순서와 소유 파일은 PLAN «Wave 계획» 표가 정본이다.
3. Wave 마다: 구현 → focused test → 배포(sudo 확보됨) → 실브라우저 재캡처 →
   `--stage wave` → 구현하지 않은 에이전트의 독립 Visual/Requirement Reviewer.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
