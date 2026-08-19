# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-19T18:10:00+09:00
- wave: W2
- wave_status: 완료 — Exit Gate E1~E7 충족. 다음 세션이 **W3(Navigation & Icon)** 를 시작한다
- build_index_sha256: `344ce7e7fc221246` — 서버가 서브 중인 것이자 **After 의 지문**.
  W1 은 `104e49366bf030f4`, Before 는 `9ab4d470163e475a` — 셋이 서로 달라야 before/after 다
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(W2) **PASS** (억제 0건)
- static_checks: **STATIC_CHECKS_OK**
- tests: frontend `npx vitest run` **2,303 PASS / 0 FAIL**(W1 대비 +57, 파일 +2) ·
  backend `run_full_regression.sh` **FULL_REGRESSION_OK**(unit·regression·security·
  integration 4청크, 29m43s) — W2 는 백엔드를 안 건드렸지만 QA 도구 3개를 고쳤다
- after_capture: `--label w2-after` 전 83 Route × 2테마 × **4뷰포트**(390/1366/1920/3840)
  = 664페이지. 썸네일 664장을 `docs/ui-renewal/captures/after/` 에 커밋했다
- 실측 (Before → W2 after, 뷰포트별 pass/fail)
  · `brand_presence` 1920 **6/160 → 94/72** · 3840 6/160 → 92/74 · 390 0/166 → 6/160
  · `control_baseline_mismatch` 1920 **92 → 16 fail** · 3840 94 → 50 · 390 90 → 26
  · `narrow_main` 3840 166/166 **PASS** (W2 가 폭 캡 층에 `c-content` 이름을 줘서
    프로브가 처음으로 진짜 열을 잰다 — `content=None` → `content=3080px`)
  · `dead_blank_region` 146 → **138 fail** (1366 8 · 1920 34 · 3840 86 · 390 10)
  · `console_errors` 2 → **0** · `surface_repetition` 390 2 → 0 · `isolated_control_row` 3840 1 → 0
- functional: `scripts/ui_qa/shell_e2e.py`(신규) 가 `shell_topbar` 7 Flow 를 실브라우저에서
  네트워크와 함께 돌린다 — 6건 사슬 4/4 **PASS**, FF-1189(테마 토글)만 IN_PROGRESS
  (서버 왕복이 구조적으로 없다 — 첫 페인트 전 결정, FOUC 방지)
- reviewers: 구현하지 않은 독립 에이전트 **3 렌즈 + 적대적 검증 10건**
  (Workflow `wf_9de9cf72-00f`). 제기 22 · **확인 5** · 반증 5 · 미검증 12.
  확인·미검증 중 **W2 소유 전부를 이번 Wave 에서 고쳤고**(D-183), 남의 Wave 소유 4건은
  `ROUTE_COVERAGE.surfaces[shell_topbar].findings` 에 `F-W2R-01~04` 로 라우팅했다
- open_findings: **259 OPEN / 40 CLOSED**(Surface Finding 299건 전수 — Critical 4 · High 185 · Medium 69 · Low 1). `scripts/merge_qa_findings.py`(신규)가 매 실행마다 재측정한 것만 판정해 갱신·신규·종료를 남긴다 — 고쳐진 것을 안 닫는 쪽이 더 나쁜 거짓말이다.
  여기에 W1 독립 리뷰 잔여 34건 + F-0100(High, W12)이 별도로 있다
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 접속·배포·QA 값은
  `dist/ops/server.env`(gitignore). 배포는 사람 없이 돈다 — `scripts/apply-static-update.sh`
- commit: `1af4f20d` (W2 전체 — 소스 · 번들 · 캡처 664장 · Control Plane)
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
W2(Global Shell) 가 끝났다. **하우징 위의 물건들이 하우징의 재료를 쓴다** — 상단바 채움이
사이드바 Gradient 의 첫 stop 이 되어 L 자가 한 물체로 읽히고(독립 검수 164페이지 전수 이음매
0건), 셸 위 컨트롤 넷이 캔버스 판에서 chrome 반전 트랙으로 옮겨져 상단바의 밝은 픽셀 비율이
25.76% → 2.36% 로 떨어졌다. 제품명은 한 단어 `ClovirAssist` 이고 로고 영역은 부제를 빼서
216×37 → 194×23(면적 -36%)이 됐다 — 글자 크기는 못 줄인다(부제가 `tiny_text` 12px 하한에
걸려 있다), 유일한 레버가 줄 수였다.

이번 Wave 가 배운 것 하나가 남는다: **"선언은 있는데 화면에는 없다"** 가 세 자리에서 나왔다.
MUI 의 border 스타일 함수는 논리 속성(`borderInlineStart: 2`)을 펴 주지 않아 `-style` 없는
무효 선언이 되고, `borderInlineStartColor: "primary.main"` 은 팔레트를 안 풀어 준다. 사이드바
바깥 모서리와 팔레트 선택 레일이 그렇게 한 픽셀도 안 그려진 채 시험은 초록이었다. 이제
`shell-surface-contract.test.js` 가 그 형태 자체를 금지하고, **자기 정규식이 좁아지는 것까지**
스스로 시험한다 — 첫 판이 문자열 철자만 잡아 콜백 철자 되돌림을 통과시켰기 때문이다
(독립 검수자가 변이로 실증했다). 근거·수치·되돌린 것은 `docs/DECISIONS.md` **D-181 · D-182 · D-183**.

## NEXT
1. **W3(Navigation & Icon)** 을 시작한다. 소유 파일 `frontend/src/app/navConfig.js` ·
   `navIcons.js` · `AppShell.jsx` **사이드바부**(W2 커밋 뒤) · `CommandPalette.jsx`.
   **입력이 준비돼 있다** — `ROUTE_COVERAGE.surfaces[shell_topbar].findings` 의
   `F-W2R-02`(3840 에서 사이드바 아이콘과 라벨이 맞붙는다 — `minWidth: 30` px 칸을 rem
   아이콘이 채우고, 같은 줄 `size={18}` 은 MUI SvgIcon 에 안 먹는 죽은 prop)와
   `w1_review_findings` 의 `owner_wave == "W3"` 2건(F-W1R-05 · F-W1R-18)이 그 목록이다.
   PLAN W3 Exit Gate 의 "Nav 라벨 시작선 42px 단언" 이 F-W2R-02 를 그대로 닫는다.
   사이드바 하단 38~50%가 빈 면이라 Gradient 이동량의 절반이 빈 자리에 쓰인다는 관찰도 같은 소유.
2. Wave 마다: 구현 → focused test → 배포(`apply-static-update.sh`) → 실브라우저 재캡처
   (`--routes all --themes light dark --viewports 390x844 1366x768 1920x1080 3840x2160
   --label w3-after`) → `collect_evidence --into after` → `merge_qa_findings --write` →
   `--stage wave` → **구현하지 않은 에이전트**의 독립 검수.
   리뷰 Workflow 는 `…/scratchpad/w2-review.js` 를 복제해 쓴다 — 3 렌즈 + 적대적 검증
   10건이 실제로 결함 다섯을 잡았고 그럴듯한 다섯을 기각했다.
3. 그 뒤 W4(공유 Primitive — `F-W2R-01` 이 입력이다: `kit.jsx` 의 논리 테두리 3자리가
   안 그려져 MetricStrip 칸 구분선이 배포본에 없다) → W5·W5B → W6 → W7 → W8(Pilot 8종) → W9~W15.
4. 승격 예정 Gate: `brand_role_coverage` → **W6** · `mascot_visible_size` → W7 ·
   `isolated_control_row`·`control_baseline_mismatch` → W5 · Table 4종 → W6.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
