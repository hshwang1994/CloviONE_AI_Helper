# CLAUDE.md — ClovirONE Web Assistant
> Claude Code가 이 저장소에서 세션을 시작할 때 읽는 **최상위 실행 규칙**이다.
> 과거 작업 이력·진행률·긴 사고 기록은 여기에 쌓지 않는다. 동적 상태는 `docs/`에서 복원한다.
> 목표는 Area/Cycle/Batch 몇 개가 아니라 **제품 전체를 실제로 완료하는 것**이다.

## 0. 최우선 실행 원칙
- **PROJECT 전체가 유일한 작업 단위다.** Product Area / Mega Cycle / Batch / Slice / Iteration은 조사·정리·병렬화용 라벨일 뿐 종료 단위가 아니다.
- 정상 종료 조건은 `PROJECT_COMPLETE`뿐이다. 실행 가능한 일이 남아 있으면 즉시 다음 작업으로 계속한다.
- commit, clean working tree, focused test green, 문서 갱신, “iteration complete”, “next candidate”, recap/summary는 Stop Condition이 아니다.
- 사용자 확인은 실제 MFA·외부 승인·접근 불가·상충 요구·되돌릴 수 없는 Production 결정처럼 사람이 필요한 경우에만 요청한다.
- 한 blocker가 있어도 독립적으로 가능한 작업은 계속한다.
- **Windows Task Scheduler 기반 실행은 폐기한다.** 새 scheduled task / idle tick / 시간 간격 재실행을 만들지 않는다. 기존 Task Scheduler 항목 삭제는 사용자가 직접 처리한다.

## 1. 세션 시작 / Context 복구
세션 시작, `/compact` 이후, 장시간 작업 후 방향이 불확실할 때 다음을 교차 대조한다.
1. `docs/WORK_STATE.md` — 현재 위치 / resume pointer
2. `docs/WORK_PLAN_INDEX.md` — MASTER PLAN / 전체 목표 / 완료 기준
3. `docs/PROGRESS_STATUS.md` — 최신 전체 Snapshot
4. `docs/BACKLOG.md` — **파일 전체 unresolved 상태 inventory**
5. `docs/QA_COVERAGE.md` — **파일 전체 미검증 route/axis inventory**
6. Git status / diff / 최근 커밋
7. 실제 Source / Tests
8. `docs/DECISIONS.md` — 현재 작업 관련 결정
9. `docs/BUILD_LOG.md` — 과거 경위가 필요할 때만
큰 MD를 매번 통째로 컨텍스트에 덤프할 필요는 없다. 검색/작은 파서로 전체 상태를 집계하고 필요한 구간을 읽는다. 단 **상단 몇 줄이나 “next candidate”만 보고 다음 작업을 정하지 않는다.**
문서와 Source/Git/Test가 충돌하면 실제 코드와 검증 결과를 확인해 문서를 정정한다. 오래된 감사 결과는 구현 전에 재현/재검증한다.

## 2. 프로젝트 핵심 구조
- Python 3.12, FastAPI **sync**, SQLAlchemy 2.0 **sync**, Alembic, SQLite **WAL**
- React 18 + Vite + HashRouter, 소스 `frontend/`, 산출물 `app/static/react/`
- 런타임 외부 CDN/폰트 의존 금지, CSP `script-src 'self'`
- n8n + Claude Runner + Notion 연동을 포함한 사내 업무 자동화 플랫폼
- 주요 디렉터리: `app/`, `frontend/`, `runner/`, `alembic/`, `scripts/`, `deploy/`, `docs/`, `tests/`
실제 저장소 구조가 문서와 다르면 Source를 정본으로 보고 문서를 갱신한다.

## 3. 불변 규칙
1. **Sync 일관성** — 임의의 FastAPI `async def` 핸들러나 `aiosqlite`를 추가하지 않는다.
2. **Outbound HTTP 단일 관문** — 외부 호출은 `app/core/http_client.py`의 `OutboundClient`를 경유한다. 임의 `httpx` 직접 사용 금지.
3. **Secret 비노출** — secret은 DB/응답/로그/감사에 평문 저장·노출하지 않는다.
4. **Credential 비영구화** — 비밀번호/토큰을 Git, tracked docs, source, config, 명령행, 불필요한 로그에 남기지 않는다. 가능한 stdin/프롬프트/승인된 runtime secret 경로를 사용한다. `sshpass` 금지.
5. **Session/RBAC** — opaque session + CSRF 규약 유지. 권한 판단은 서버가 정본이며 프런트 권한 표시는 보조일 뿐이다.
6. **XSS/CSP** — 서버 데이터를 `innerHTML`로 주입하지 않는다. inline script / `onclick=` 금지.
7. **UTC 저장** — Asia/Seoul은 표시·cron 평가에만 사용한다.
8. **제품 기능 경계** — Runner 코드 웹 편집, 임의 shell 실행, secret 평문 표시, 범용 systemd 제어 기능을 제품 기능으로 추가하지 않는다.
9. **공유 서비스 보호** — unrelated n8n / 기존 Claude Runner / 공유 nginx 설정을 ClovirONE 작업 때문에 임의 변경하지 않는다.
10. **DB transaction 의미 보존** — `app/core/db.py`의 명시적 transaction/BEGIN 규약을 우회하거나 pysqlite implicit transaction 동작에 다시 의존하지 않는다. SAVEPOINT/`begin_nested()`는 실제 outer transaction 안에서 동작해야 한다.
SQLite write conflict/busy/locked 판정은 기존 공용 classifier/retry 규약을 재사용한다. 다른 Session/Connection이 쓴 상태를 읽을 때 필요한 commit 경계를 확인한다. `:memory:` DB로 WAL/멀티커넥션 의미를 대체하지 않는다.

## 4. 작업 선택 / 구현 방식
Backlog ID를 한 건씩 기계적으로 처리하지 않는다. 문제 하나를 보면 Repository 전체에서 같은 패턴과 Root Cause를 찾는다.
- UI 문제 → shared component + 전체 소비처
- RBAC 문제 → 같은 permission/scope/IDOR 경로 전체
- API 오류 → 공통 client/error contract
- DB race/transaction 문제 → 같은 transaction/retry 패턴 전체
- Design 문제 → token/variant/shared component + 실제 화면 소비처
우선순위는 대체로 **Critical/Security/DataLoss/RBAC/Integrity → 큰 Root Cause → High 사용자 영향 → 큰 QA 공백 → 나머지**다.
독립적인 조사/수정은 subagent, background agent, worktree로 병렬화할 수 있다. Main Agent가 최종 diff, wiring, integration, permission impact, test evidence를 검토한다.
주요 기능은 가능하면 `Screen → Action → API → Backend → DB/Data → Result → Related Screen → Reload/State → Permission/RBAC`까지 닫는다.
UI-only, Backend-only, 프런트 role gate만 있는 권한 처리, 페이지가 열리기만 하는 검증은 완료로 보지 않는다.

## 5. Frontend / Product UX도 필수
Frontend와 실제 Product UX는 선택사항이 아니다. Backend/API/DB와 동일한 필수 완료 범위다.
필요 시 Dashboard, Navigation/IA, User/Admin hierarchy, Page Header, Layout/max-width/density, Card/Table/Filter/Form, Modal/Drawer, Action hierarchy, Typography, Accessibility, Keyboard/Focus, FHD/QHD/4K, Responsive, Light/Dark까지 실제 화면 수준에서 개선한다.
Token/CSS/shared primitive 정리만으로 “Design 완료”라고 하지 않는다. 가능하면 per-page 예외보다 shared token/variant/component를 우선하며 기존 shared infrastructure도 맹신하지 않는다.

## 6. 테스트 전략 — 작은 검증은 자주, 전체 검증은 수렴 후 크게
구현 중에는 변경 영역과 직접 관련된 focused/subsystem test를 반복한다.
- Backend: unit/integration/API/security
- DB: transaction/integrity/concurrency/retry/migration
- Frontend: component/route/helper/interaction
- RBAC: allow/deny/scope/cross-org·cross-department negative case
- AI/Runner: state/intent/job/conversation
- Shared UI: component + 대표 소비자 regression
회귀 결함은 가능하면 **수정 전 실패 → 수정 후 통과(revert-to-verify)** 를 확인한다.
**작은 변경마다 전체 backend/frontend/runner/static/build를 돌리지 않는다.** 전체 구현이 충분히 수렴했을 때 Full Regression을 통합 실행한다.
예외: auth/RBAC, transaction layer, migration, security, shared framework처럼 영향 반경이 큰 고위험 기반 변경은 Root Cause 묶음을 고친 뒤 전체 회귀를 조기에 한 번 돌릴 수 있다.
Full Regression 실패 시 `실패 전체 수집 → Root Cause grouping → 대량 수정 → focused test → Full Regression 재실행` 순서로 처리한다.

## 7. 상태 문서 / Checkpoint
- 새 문제 → `BACKLOG.md`
- 새 Route/기능 검증 → `QA_COVERAGE.md`
- 중요한 설계 판단 → `DECISIONS.md`
- 현재 위치/Blocker → `WORK_STATE.md`
- 전체 Snapshot → `PROGRESS_STATUS.md`
- 오래된 상세 이력 → `BUILD_LOG.md`
완료 사실과 검증 근거는 보존하되 Active Context는 compact하게 유지한다. 의미 있는 Root Cause 묶음이나 복구 가치가 있는 시점에 checkpoint/commit한다. **문서 갱신이나 commit 직후 멈추지 말고 즉시 다음 runnable work로 계속한다.**

## 8. Whole-product 재감사
상당량 구현한 뒤 Repository 전체를 다시 감사한다: Routes, Screens, Components, API, Backend, DB, RBAC, AI/Runner, Admin/User workflow, Design/UX, Responsive/Theme, Integrations/Operations, Tests, QA Coverage.
찾아야 할 것: half implementation, wiring 누락, dead path, stale docs, 이미 해결됐는데 미완료 표시, 잘못된 오래된 감사, duplicate logic, 새로운 shared Root Cause, unbounded list/pagination 누락, accessibility/focus/contrast 공통 문제.
새로운 중대한 Root Cause 범주가 계속 나오면 아직 수렴하지 않은 것이다. 계속 수정한다.

## 9. 승인된 TEST SERVER 배포
승인된 TEST SERVER는 **`10.100.64.X` 대역**이다. 특정 마지막 octet을 과거 기억으로 하드코딩하지 않는다.
실제 배포 대상 host/IP는 현재 Repository 설정, deployment scripts, runtime configuration 또는 사용자가 제공한 최신 값에서 확인한다. 이 대역을 Production으로 취급하지 않는다.
사용자가 승인한 범위에서 Claude/Runner는 해당 TEST SERVER에 자동 deploy/modify/test할 수 있다. 필요한 SSH/sudo credential은 **runtime에서만** 사용하며 저장소나 문서에 기록하지 않는다. 이 권한을 다른 서버/향후 Production으로 자동 확장하지 않는다.
기본 흐름은:
`whole-product implementation convergence → Full Regression green → Build → 통합 Deploy → service/health/revision 확인 → Chrome Whole-product E2E`
작은 변경마다 배포하지 않는다. 배포 환경에서 확인하지 않으면 다음 구현 자체가 불가능한 genuine blocker는 예외다.

## 10. Chrome Whole-product E2E — 최종 필수 Gate
통합 배포 후 **실제 Chrome 기반 브라우저 E2E**를 수행한다. 몇 화면을 열어보는 smoke test로 끝내지 않는다.
Route map + `QA_COVERAGE.md` + 주요 Workflow 기준으로 사용자 콘솔과 관리자 콘솔을 가능한 범위까지 순회한다.
가능한 주요 Flow에서 `Screen → User Action → Network Request → API → Backend → DB/Data → UI Result → Related Screen → Reload → Permission/RBAC`까지 검증한다.
Chrome/DevTools 기준으로 Console error/warning, Network failure/4xx/5xx, Empty/Loading/Error/Retry, role/permission denied, Long/Many data, Navigation/deep-link/refresh/state retention, Modal/Drawer/Form, Keyboard/Focus, Responsive, Light/Dark를 확인한다.
Screenshot 존재, 페이지 오픈, health 200만으로 E2E 완료 처리하지 않는다.
실환경 문제는 가능한 범위까지 먼저 수집한 뒤 `collect → Root Cause grouping → bulk fix → focused test → 필요한 Full Regression → integrated redeploy → Chrome re-E2E`로 처리한다.
**Chrome Whole-product E2E가 충분히 끝나지 않으면 `PROJECT_COMPLETE=true`로 만들지 않는다.**

## 11. Primary Runner / Supervisor — Local OS-level Continuous Worker
**Primary execution mechanism은 로컬 `autonomous_runner.ps1` Continuous Supervisor다.**
`/loop`, ScheduleWakeup, Claude Code scheduled task, cron, Windows Task Scheduler는 Primary Supervisor가 아니며 이 구조를 대체하지 않는다.
사용자가 `autonomous_runner.ps1`을 한 번 수동 시작하면 그 PowerShell 프로세스 자체가 `PROJECT_COMPLETE`까지 계속 살아 있으면서 Claude invocation을 관리해야 한다.
정상 흐름:
`restore/cross-check → invoke/resume Claude → Claude exit → persist checkpoint → PROJECT_COMPLETE 검사 → false면 즉시 다음 invocation`
- Claude invocation의 exit code 0, clean tree, commit, current task list empty, iteration complete, recap/summary는 종료 조건이 아니다.
- `PROJECT_COMPLETE=false`이면 정상 작업 성공 후 sleep/idle tick/ScheduleWakeup 없이 **즉시** 다음 invocation을 시작한다.
- backoff는 rate limit, transient outage, 실제 외부 시간 의존성, human-only MFA/approval처럼 진짜 기다릴 이유가 있을 때만 허용한다.
- Claude 세션 내부 `/loop`/ScheduleWakeup은 필요하면 보조 기능으로만 사용할 수 있으며 project continuity의 근거로 삼지 않는다.
- 동시에 두 Supervisor가 같은 Repository를 수정하지 않도록 single-instance lock을 둔다.
- 사용자가 Ctrl+C/명시적 stop signal로 안전하게 수동 중단할 수 있어야 하고 다음 수동 시작에서 Git+docs로 복구 가능해야 한다.
- stale STOP/lock이 새 수동 시작을 조용히 무력화하지 않게 한다. 시작 불가 상태면 이유를 명확히 출력하고 종료한다.
- 시작 시각, invocation 번호, Git SHA, exit code, retry 이유, last checkpoint, `PROJECT_COMPLETE` 상태를 기록하되 secret은 로그에 남기지 않는다.
- Windows Task Scheduler 항목의 생성/수정/삭제에 의존하지 않는다. 기존 Scheduler 삭제는 사용자가 직접 한다.
Claude Code CLI의 resume/continue/noninteractive/session 옵션은 과거 기억으로 하드코딩하지 않는다. **현재 설치 버전의 `claude --help`를 확인한 뒤** 실제 지원되는 방식으로 구현한다.
기존 `autonomous_runner.ps1`의 multi-line prompt는 argv에 직접 끼워 넣지 않는다. 현재 검증된 **stdin 전달 방식**을 유지한다.
Supervisor 변경 시 controlled test로 최소 다음을 실제 증명한다:
`Claude invocation 종료 → PROJECT_COMPLETE=false → Supervisor가 즉시 다음 Claude invocation 실행`
Claude의 자연어 `"project complete"`만으로 종료하지 않는다. 가능한 한 아래 완료 Gate를 근거로 엄격한 machine-readable state/marker를 사용한다.

## 12. 대표 검증 명령
현재 Repository의 실제 scripts/package 설정을 우선 확인한다.
- Backend focused: `.venv/Scripts/python -m pytest <path-or-nodeid>`
- Backend full: `.venv/Scripts/python -m pytest`
- Runner full: `cd runner/claude-work-assistant && ../../.venv/Scripts/python -m pytest`
- Frontend: `cd frontend && npm test`
- Static checks: `bash scripts/static_checks.sh`
- Build bundle: `bash scripts/build-bundle.sh`
테스트 개수나 과거 출력 숫자를 CLAUDE.md에 고정하지 않는다.

## 13. PROJECT_COMPLETE
정상 종료 전 최소 다음을 만족해야 한다:
MASTER PLAN 주요 목표, Critical/High 및 주요 Backlog, Frontend/Backend/API/DB wiring, RBAC/IDOR/Data scope, DB transaction/concurrency/integrity, AI/Runner 주요 flow, 실제 Product Design/UX, Admin/User 주요 workflow, Integrations/Operations, QA Coverage 주요 공백, Backend/Frontend/Runner Full Regression green, Static Checks + Build green, 승인된 TEST SERVER 통합 Deploy, 실제 배포 revision 확인, **Chrome Whole-product E2E**, Console/Network, Responsive/Theme/Accessibility, 실환경 발견 문제 수정/재검증, Final Whole-product Re-Audit 수렴.
마지막 재감사에서 새로운 중대한 Root Cause 범주가 나오면 `PROJECT_COMPLETE=false`다.

## 14. 마지막 규칙
**AREA를 끝내지 마라. CYCLE을 끝내지 마라. ITERATION을 끝내지 마라. BACKLOG 몇 건을 끝내지 마라. 제품 전체를 끝내라.**
조사는 넓게. 수정은 Root Cause 단위로 크게. Frontend/Backend/DB/RBAC/AI/UX/QA 모두 필수. 관련 테스트는 자주. 전체 테스트는 수렴 후 크게. 배포는 마지막에 통합해서. 실환경 검증은 Chrome 기반 제품 전체로.
Checkpoint 후 멈추지 마라. Claude invocation이 끝나도 `PROJECT_COMPLETE=false`이면 Primary Local Supervisor가 즉시 이어가라.