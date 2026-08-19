# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-19T11:35:00+09:00
- head: 0287d26d + 미커밋 W0 작업
- wave: W0 — Baseline & Control Plane
- wave_goal: Gate 를 실제로 작동시키고, 제품 코드를 건드리기 전에 Before 를 전량 캡처한다
- build_index_sha256: 9ab4d470163e475a — **서버가 서브 중인 것**. 지문은 이제 원격 shell 을
  직접 받아 계산한다(D-175). 로컬 빌드는 1a4b20a852580a31 이고 `export` 추가분만 다르다
- coverage_gate: `--stage plan` PASS · `--stage wave` FAIL 1종 (Before 캡처 82건, 실행 중)
- static_checks: **STATIC_CHECKS_OK** (`.git` 위생 포함 — D-178)
- surfaces_total: 92 (route 68 · tab 14 · state_variant 4 · widget 6 — App Shell 2 신설)
- harness_routes: 84 화면 + 별칭 4 (별칭은 화면이 아니다 — D-170)
- archetype_gap: 19 Surface 의 현재 모습이 목표 Archetype 과 다르다 (list_table 49→35)
- functional_flows: 1,199 / 88 Surface (27개 범주 전부 등장, 1건 FAIL, 나머지 `NOT_AUDITED`)
- requirements_total: 161 (89개가 화면에 매핑, 나머지는 Gate·계획 절차라 화면에 살지 않는다)
- open_findings: F-0100 (High, W12) — `ROUTE_COVERAGE.w0_open_questions` 에 판단 대기 12건
- test_server: https://clovirassist.gooddi.lab = https://10.100.64.71 (DNS 는 이 이름만 뜬다)
  · 접속·배포 값은 `dist/ops/server.env` (gitignore). sudo 확인 완료 — 배포는 사람 없이 돈다
  · QA 계정은 `hshwang@goodmit.co.kr`(system_admin, Notion verified) — `내 …` 화면 실데이터 확보
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
Gate 가 소스를 직접 읽고 판정한다 — `--stage wave` 가 496건에서 **Before 캡처 하나**로 줄었다.
그 캡처가 지금 돌고 있다(1,494장, 약 90분). 제품 화면 코드는 아직 바뀌지 않았다:
`AdminRoutes.jsx`·`SettingsShell.jsx` 변경은 `export` 키워드뿐이라 렌더 결과가 같다.

Gate 를 세우는 과정에서 **커버리지가 거짓말하던 자리**를 실제로 찾았다(D-170~D-173).
가장 무거운 것: `/admin-notifications`(사이드바 '관리 알림')가 하네스에도 커버리지에도 없어
한 번도 캡처된 적이 없었고, 하네스의 `admin_notifications` 는 존재하지 않는
`/admin#/notifications` 를 찍어 **catch-all 404 위에서 21개 검사를 통과**시키고 있었다.

새 Assertion 13종이 처음으로 실제 화면을 잰다. 초기 240페이지 표본에서
`brand_presence` 는 **전 페이지 실패**(설계 충돌을 가시화하는 것이 목적 — 계획대로),
`control_baseline_mismatch` 132 · `dead_blank_region` 31 · `plain_dropdown_for_entity` 26 ·
`numeric_alignment` 12 · `equal_column_split` 7. 표본 둘을 열어 오탐이 아님을 확인했다.

## NEXT
1. 캡처 종료 → `collect_evidence.py --label before-renewal --into before` →
   Surface 마다 `before_capture` 채우기 → `--stage wave` PASS 확인.
2. `bash scripts/static_checks.sh` 초록 → W0 커밋.
3. **W1 Brand Foundation** — `theme.js` → 생성기 → 두 `tokens.css` → Contract Test 재작성.
   한 에이전트·한 커밋 시퀀스. Exit Gate: smoke set × 두 테마에서 `brand_presence >= 5/7`.
4. W1 이후로는 Wave 마다 서버에 배포하고 실브라우저로 확인한다 —
   `SERVER`/`SUDO_PW` 는 `dist/ops/server.env`, 절차는 `scripts/stage-static-update.sh`.

## BLOCKERS
- 없음. `.git` 위생(PA-RC-0003)은 정리했다 — 사고 경위는 값 없이 D-178 에 남기고
  `stash@{0}` 삭제 + 도달 불가 확인 후 `git gc --prune=now`. `static_checks.sh` 초록,
  Gate 예외·Suppression 은 하나도 추가하지 않았다. 비밀번호는 사용자 지시대로 회전하지 않았다.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
