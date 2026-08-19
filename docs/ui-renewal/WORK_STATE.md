# WORK STATE — ClovirAssist UI/UX 리뉴얼

<!-- 이 파일은 덮어쓴다. 날짜 절, 이력 표, 완료 목록을 추가하지 않는다.
     이력은 이 파일의 git log 다. 최대 120줄 - 초과하면 Gate 가 실패한다. -->

## CHECKPOINT
- checkpoint_at: 2026-08-19T10:20:00+09:00
- head: a2439eb1 (docs/ 복구·삭제 확정 + ui-renewal Artifact 추가 예정)
- wave: W0 — Baseline & Control Plane (문서 산출물만 선행 완료)
- wave_goal: 소스에서 파생한 Control Plane 을 세우고, 제품 코드를 건드리기 전에 Before 를 전량 캡처한다
- build_index_sha256: 9ab4d470163e475a
- last_qa_label: deploy3
- last_qa_results: dist/ui-qa/deploy3/results.json
- last_qa_fail_classes: vertical_text_collapse(6)
- coverage_gate: PASS (--stage plan, 2026-08-19)
- route_coverage_sha256: 8a53e197f839a568
- requirement_matrix_sha256: 481f147bde72d136
- functional_coverage_sha256: 4bb994389e582dd7
- surfaces_total: 89   done: 0   open_findings_critical_high: 10
- requirements_total: 161   done: 0
- plan: docs/ui-renewal/PLAN.md (정본), docs/ui-renewal/DIRECTIVE_v7.txt (원 지시서)

## NOW
계획 세션이 끝났다. 제품 코드는 아직 한 줄도 바뀌지 않았다.
`docs/ui-renewal/` 에 PLAN·REQUIREMENT_MATRIX(161)·ROUTE_COVERAGE(89 Surface)·
FUNCTIONAL_COVERAGE·QA_SUPPRESSIONS 를 만들었고 `scripts/check_ui_renewal_coverage.py`
의 `--stage plan` 이 통과한다. `--stage wave` 와 `--stage complete` 는 아직 미구현이며
종료 코드 2로 정직하게 멈춘다 — W0 에서 C1~C14 를 구현해야 한다.
지켜야 할 불변: ROUTE_COVERAGE 는 **소스에서 파생**한다. 손으로 Surface 를 추가하지 않는다.

## NEXT
1. `git log --oneline -3 && git status --short`
2. `.venv/Scripts/python.exe scripts/check_ui_renewal_coverage.py --stage plan`
3. `bash scripts/static_checks.sh` — 지금 빨갛다. 원인은 `scripts/check_traceability.py` 가
   삭제된 `docs/UI_RENEWAL_TRACEABILITY.md` 를 요구하는 것. 새 Gate 로 교체하고
   `static_checks.sh` 의 해당 단계를 바꾼다. (외부 Blocker 아님 - 우리가 고친다)
4. `.venv/Scripts/python.exe -m scripts.ui_qa.run --list` 로 `routes.py` 와 소스 Route 대조.
   `/my-approvals`, `/my-display` 추가. `/system`·`/notion-console`·`/llm-console`·`/maintenance`
   를 alias 로 재분류. `/settings?tab=` 4개와 TabShell 탭 본문 10개를 Surface 로 추가.
5. 관리자 `Notion 사용자 연결` 로 QA 계정 매핑 수리 → Real Data 상태 확보 →
   `--label before-renewal` 전 Surface × light/dark × 9뷰포트 전량 캡처 →
   `collect_evidence.py --into before` 로 썸네일 커밋.
6. Assertion 13종을 `scripts/ui_qa/assertions.py` 에 Advisory 로 추가하고 Gate C1~C14 구현.

## BLOCKERS
- 없음.
<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
