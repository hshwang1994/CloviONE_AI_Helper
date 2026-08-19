# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-19T23:40:00+09:00
- wave: W3
- wave_status: 완료 — Exit Gate E1~E7 충족. 다음 세션이 **W4(공유 Layout Primitive)** 를 시작한다
- build_index_sha256: `c03113861aaa5138` — 서버가 서브 중인 것이자 **After 의 지문**.
  W2 `344ce7e7fc221246` · W1 `104e49366bf030f4` · Before `9ab4d470163e475a` — 넷이 서로 다르다
- coverage_gate: `--stage plan` **PASS** · `--stage wave`(**W3**) **PASS** (억제 0건).
  W2 CHECKPOINT 를 안 올린 채 돌리면 게이트가 조용히 W2 를 다시 검사한다 — 독립 검수가 그
  구멍을 잡았고(F-W3R-03), 그래서 CHECKPOINT 를 먼저 올리고 W3 범위로 다시 돌린 결과가 이 줄이다
- static_checks: **STATIC_CHECKS_OK** (신규 `check_icon_props.py` 포함)
- tests: frontend `npx vitest run` **2,327 PASS / 0 FAIL**(W2 대비 +24, 파일 +1) ·
  backend `run_full_regression.sh` **FULL_REGRESSION_OK**(31m51s) — W3 은 백엔드를 안 건드렸다
- after_capture: `--label w3-after` 전 83 Route × 2테마 × 4뷰포트 = 664페이지.
  썸네일 664장을 `docs/ui-renewal/captures/after/` 에 갱신했다
- 실측 (W2 → W3, 뷰포트별 fail) — **악화 0 · 개선 2**
  · 셀 단위(route × theme × viewport × assertion 5,312칸) 대조 — **신규 fail 0 · fail→pass 2**
    (`admin_audit-detail` 3840 light·dark `vertical_text_collapse`). 총 fail 1,250 → 1,248
  · 사이드바 기하 `dist/ui-qa/w3-nav-e2e/anatomy.json` **18/18 조합 PASS** —
    390·1366·1920·3840 × light·dark × 사용자·관리자 + 팔레트 두 테마.
    라벨 시작선 42(4K 정규화 후 42) · 레일 3px@inline-start 0 · 자식 글리프 0 ·
    활성/비활성 굵기 500 동일 · 포커스 링 -2px · 스크롤 없이 안 보이는 랜드마크 0건
- functional: `scripts/ui_qa/nav_e2e.py`(신규) 가 `shell_sidebar` 7 Flow 를 실브라우저에서
  네트워크와 함께 돌린다 — 5건 사슬 4/4 **PASS**, FF-1201(그룹 접힘 유지)·FF-1202(메뉴 찾기)만
  IN_PROGRESS(서버 왕복이 **구조적으로** 없다 — localStorage · 순수 함수). C11 다섯 축 중 넷은
  사이드바 필터에 존재하지 않아 `exists:false` 로 선언했다(FF-1208~1211)
- reviewers: 구현하지 않은 독립 에이전트가 **두 번** 돌았다. ① 검수 3 렌즈 + 적대적 검증 10건
  (`wf_6fca7af0-570`): 제기 22 · **확인 7** · 반증 3 · 미검증 12. ② 그 7건의 처리 결과를 다시
  독립 재검증(`wf_9c8f1032-de5`): **4건 종결 · 3건 반려**. 반려 셋이 진짜였다 — 자동 접힘 판정이
  localStorage 에 굳어 결함이 되돌아오는 경로, 게이트가 CHECKPOINT 를 그냥 믿는 기제, 그리고
  프로브가 접힌 행을 세어 빈 면을 8~16pp 작게 적은 것. 셋 다 이 Wave 에서 다시 고쳤다 —
  `ROUTE_COVERAGE.w3_review_findings`
- open_findings: **258 OPEN / 43 CLOSED**(Surface Finding 301건 전수 — Critical 4 · High 184 ·
  Medium 69 · Low 1). W1 독립 리뷰 잔여 31건(3건 W3 종결) + F-0100(High, W12)이 별도로 있다
- test_server: https://clovirassist.gooddi.lab = 10.100.64.71. 접속·배포·QA 값은
  `dist/ops/server.env`(gitignore). 배포는 사람 없이 돈다 — `scripts/apply-static-update.sh`
- commit: `ab2bc618` (W3 전체 — 소스 · 번들 · 캡처 664장 · Control Plane · 독립 검수 2라운드)
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
W3(Navigation & Icon) 이 끝났다. **라벨은 한 열, 신호는 둘, 글리프는 랜드마크당 하나.**
그룹 60px / 자식 64px 두 격자가 42px 한 열로 합쳐졌고(`NAV_ANATOMY` 하나가 정본이다),
활성 신호가 넷(2px 레일 + 굵기 700/600 + 색 + 아이콘 opacity)에서 둘(하우징 가장자리에 붙는
3px 레일 + 행 채움·잉크)로 줄었으며, 목적지마다 붙어 `ticket` 4곳·`report` 4곳으로 반복되던
글리프 49개가 사라지고 그룹 글리프 10개만 남았다. `ICON = {nav 20, inline 18, action 20,
hero 24}` + `remPx()` 가 크기의 정본이고, MUI `SvgIcon` 에 없는 `size=`/`strokeWidth=` 는
`check_icon_props.py` 가 막는다(그 검사기는 자기 자신을 먼저 시험한다).

이번 Wave 가 배운 것 둘. **하나 — 한 뷰포트의 실측을 전 뷰포트의 규칙으로 쓰면 안 된다.**
"사용자 콘솔은 펼침 기본" 을 1920 실측만 보고 정했더니 1366x768 에서 «내 정보» 랜드마크가
통째로 스크롤 밖으로 나갔다(독립 검수가 배포본 픽셀로 22행 중 17행을 셌다). 이제 셸이 전부
펼친 높이를 **재서** 정하고, 프로브가 "스크롤 없이 안 보이는 랜드마크 0건" 을 네 뷰포트에서
확인한다. **둘 — 프로브를 대상보다 먼저 의심한다.** 이 Wave 의 신규 프로브가 낸 첫 실패 셋 중
둘이 프로브 자신의 결함이었다(하네스 시딩 스크립트가 지운 localStorage 를 제품이 잃었다고
읽었고, 포털된 임시 Drawer 를 `#app-sidebar` 안에서 찾았다). 셋째만 진짜였고 — 전역
`:focus-visible` 이 이겨서 포커스 링이 하우징 밖으로 새고 있었다.
근거·수치·되돌린 것은 `docs/DECISIONS.md` **D-184**.

## NEXT
1. **W4(공유 Layout Primitive)** 를 시작한다. 소유 파일 `frontend/src/ui/kit.jsx` ·
   `kit.css` · `adminKit.jsx` · `density.js` · `screens.css`. **입력이 준비돼 있다** —
   `F-W2R-01`(`kit.jsx` 논리 테두리 3자리가 선언만 있고 안 그려져 MetricStrip 칸 구분선이
   배포본에 없다) · `F-W2R-04`(AI 앵커 컨트롤 리듬) · `w1_review_findings` 의
   `owner_wave == "W4"` 7건. W2·W3 이 각각 자기 파일에서 같은 **논리 속성 미전개** 함정을
   밟았으니 `kit.jsx` 세 자리도 같은 형태로 고친다.
2. Wave 마다: **CHECKPOINT 의 `wave:` 를 먼저 올린다** → 구현 → focused test →
   배포(`apply-static-update.sh`) → 실브라우저 재캡처(`--routes all --themes light dark
   --viewports 390x844 1366x768 1920x1080 3840x2160 --label w4-after`) →
   `collect_evidence --into after` → `merge_qa_findings --write` → `--stage wave` →
   **구현하지 않은 에이전트**의 독립 검수. 리뷰 Workflow 는 `…/scratchpad/w3-review.js` 를
   복제해 쓴다 — 3 렌즈 + 적대적 검증 10건이 결함 일곱(High 둘)을 잡고 그럴듯한 셋을 기각했다.
3. 그 뒤 W5·W5B → W6 → W7 → W8(Pilot 8종) → W9~W15.
   W7 입력에 `F-W3R-01` 이 추가됐다 — 사이드바 하단 빈 면(3840 사용자 42.9% · 관리자 54.6%,
   admin_audit 는 73.1%)은 PLAN «Clovi 계약» 의 사이드바 도우미 카드가 채우기로 돼 있다.
4. 승격 예정 Gate: `brand_role_coverage` → **W6** · `mascot_visible_size` → W7 ·
   `isolated_control_row`·`control_baseline_mismatch` → W5 · Table 4종 → W6.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
