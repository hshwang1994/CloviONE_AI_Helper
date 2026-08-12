# 무인 Supervisor 두 단계 — Product Audit → 구현 완성

> 사용자가 자는 동안 사람 개입 없이 제품을 끝까지 밀고 가기 위한 로컬 실행 구조다.
> **이 PowerShell 프로세스 자체가 Primary Continuous Supervisor**다 — Windows Task Scheduler
> 의존은 폐기됐고(CLAUDE.md §0), 이 루프를 되살려 주는 heartbeat도 fallback도 없다.

```
PHASE 1                                   PHASE 2
product_audit_runner.ps1                  autonomous_runner.ps1
전수조사 · 근거 수집 · Root Cause 정규화   →   구현 · 테스트 · 회귀 · 배포 · Chrome E2E
제품 코드 수정 금지                            Handoff 를 입력으로 사용
AUDIT_COMPLETE (기계 Gate)                    PROJECT_COMPLETE (기계 Gate)
        └── PRODUCT_AUDIT_HANDOFF.md + IMPLEMENTATION_REQUIRED ──┘
```

두 Supervisor는 **`var/runner/run.lock` 을 공유한다 — 동시에 실행할 수 없다.**
두 번째로 뜬 프로세스는 이유를 크게 출력하고 물러난다(Audit은 exit 4, 구현 Runner는 exit 0).

## 구성 파일

| 파일 | 역할 |
|---|---|
| `product_audit_runner.ps1` | PHASE 1. 전수조사 Supervisor. 제품 코드를 고치지 않는다 |
| `autonomous_runner.ps1` | PHASE 2. 구현 Supervisor(Primary Continuous Worker) |
| `runner_common.ps1` | 두 Supervisor가 **똑같이 틀리면 안 되는** 원시 계층(종료 상태 판정, git 호출, state 정규화, 잠금, marker 격리) |
| `stop_guard.py` | Stop hook 보조 제동. Supervisor를 대체하지 않는다 |
| `tests/runner_contract_tests.ps1` | 격리된 scratch 저장소에 **실제 스크립트를 그대로** 돌리는 상태 전이 controlled test |
| `install_task.ps1` | 과거 유물. 이 구조의 일부가 아니다 |

런타임 산출물(전부 git 추적 안 됨):
`var/runner/` — 구현 Runner의 logs·runner.log·state.json·session_id.txt·STOP·AUTO_STOP·PROJECT_COMPLETE·run.lock·quarantine
`var/product-audit/` — Audit의 logs·runner.log·state.json·session_id.txt·cycle.json·STOP·AUTO_STOP·AUDIT_COMPLETE·AUDIT_BLOCKED·IMPLEMENTATION_REQUIRED·IMPLEMENTATION_CONSUMED·quarantine

## 실행

```powershell
cd C:\Users\hshwa\clovirone-web-assistant

# PHASE 1 — 제품 전체 전수조사 (기본 opus / effort max / invocation당 $20)
.\scripts\runner\product_audit_runner.ps1

# 완료(AUDIT_COMPLETE Gate 통과) 후 PHASE 2 — 구현 (기본 sonnet / effort max / invocation당 $15)
.\scripts\runner\autonomous_runner.ps1
```

Audit을 처음부터 새 Cycle로 다시 하려면 `-ResetAudit`, `AUDIT_BLOCKED` 원인을 사람이 해결한 뒤
이어가려면 `-ResumeBlocked`.

## 종료 코드

| 코드 | 뜻 |
|---|---|
| 0 | 정상 완료(`AUDIT_COMPLETE`/`PROJECT_COMPLETE`가 기계 Gate 통과), 또는 test override 상한 도달 |
| 3 | 사용자 `STOP` |
| 4 | 다른 Supervisor가 잠금 보유(Audit Runner) |
| 5 | `AUDIT_BLOCKED` |
| 6 | 연속 실패 / 완료 Gate 반복 거부로 `AUTO_STOP` |
| 7 | 전제조건 실패(claude 실행 파일 없음, git 저장소 아님) |

## 멈추는 방법

- **사용자가 명시적으로**: `var\runner\STOP`(구현) 또는 `var\product-audit\STOP`(Audit) 파일을 만든다.
  빈 파일이어도 된다. **이 파일은 오직 사람만 만든다** — 스크립트는 절대 여기에 쓰지 않는다.
- **연속 실패 시**: 스크립트가 `AUTO_STOP`(STOP이 아니다)을 만들고 멈춘다. 로그로 원인을 본 뒤
  **그냥 다시 실행하면 된다** — 수동 재시작 자체를 그 실패에 대한 확인으로 보고 흔적을 크게
  알린 뒤 정리하고 카운터를 0으로 되돌린다.
- **정상 완료**: 완료 marker가 기계 Gate를 통과했을 때만.

## 완료 marker를 그대로 믿지 않는다

Claude가 marker 파일 하나를 만들었다는 이유로 종료하지 않는다. Supervisor가 확인하는 것:

**AUDIT_COMPLETE** — 필수 문서 7종(STATE/INVENTORY/FEATURE_CONTRACTS/FINDINGS/COVERAGE/REPORT/
HANDOFF)의 존재·최소 분량·commit 여부, marker의 `cycle_id`·`baseline_sha`가 현재 Cycle과 일치,
`final_commit`이 HEAD에서 도달 가능, Audit allowlist 밖 dirty 없음, COVERAGE 요약의 자기모순
(`unseen_without_reason=0`, 본문 UNSEEN 수와 요약 수치 대조), 현재 Cycle의 `blind_pass` 기록이
2회 이상이고 마지막 두 회 모두 신규 Critical/High 범주 0, HANDOFF의 각 `PA-RC-XXXX` 블록이
26개 필수 필드를 전부 채웠고 confidence가 Confirmed/Strong, `IMPLEMENTATION_REQUIRED` 정합성.

**PROJECT_COMPLETE** — 내용이 있을 것, 그리고 `IMPLEMENTATION_REQUIRED`가 유효한 동안에는
인정하지 않는다. 현재 Handoff의 Root Cause와 Acceptance Criteria를 모두 닫고 marker를 제거한 뒤
`IMPLEMENTATION_CONSUMED`를 남겨야 완료다.

Gate를 통과하지 못한 marker는 **삭제가 아니라 격리**(`quarantine/`)하고, 거부 사유를 다음
invocation 프롬프트에 그대로 되먹여 작업을 계속시킨다. 반복 거부는 상한에서 `AUTO_STOP` /
`AUDIT_BLOCKED`로 수렴한다(무한 루프 금지).

## Audit write guard

Product Auditor가 tracked 파일 중 건드려도 되는 곳은 `docs/product-audit/**`, `docs/BACKLOG.md`,
`docs/QA_COVERAGE.md`, `docs/DECISIONS.md` 뿐이다. Supervisor는 invocation 전후로 다음을 본다.

1. **워킹트리 스냅샷 해시 비교** — 새로 생긴 경로, 내용이 바뀐 경로, 사라진 경로 전부 위반.
   Audit 시작 전부터 사용자가 남겨 둔 dirty는 "안정된 사전 상태"로 `cycle.json`에 기록하고
   진행하되, 그 뒤에 변하면 위반이다(사용자 파일 하나 때문에 밤샘 Audit이 죽지 않게).
2. **구간의 모든 커밋을 하나씩 검사** — `rev-list before..after` + `diff-tree`. 고쳐 커밋했다가
   되돌려 커밋해서 순 변화가 0이어도 탐지된다.
3. **이력 무결성** — 브랜치 전환, `before`가 `after`의 조상이 아님(reset/rebase/amend),
   reflog의 reset/rebase/checkout/revert 흔적.

위반 시 **자동 revert하지 않는다.** 무엇이 바뀌었는지 증거를 남기고 `AUDIT_BLOCKED`로 멈춘다.

## Audit Cycle 격리

각 Audit은 `cycle_id`(예: `PA-20260812-160158-d518f1ed`)와 baseline SHA를 갖는다. 과거 Cycle의
`AUDIT_COMPLETE`나 Blind Re-Audit PASS는 새 Cycle의 완료 근거가 되지 못한다 — 모든 marker와
산출물이 현재 `cycle_id`에 속하는지 확인한다. `-ResetAudit`은 runtime 상태만 새 Cycle로
초기화하고 `docs/product-audit` 아래 과거 증거는 지우지 않는다.

## 안전장치 요약

| 장치 | 막는 것 |
|---|---|
| `STOP`(사용자 전용) | 사용자가 원할 때 확실히 멈춘다. 있으면 새 시작도 이유를 크게 출력하고 exit 3 |
| `AUTO_STOP`(스크립트 전용) | 같은 원인으로 무한 재시도하지 않는다. 수동 재시작 시 자동 정리 — stale STOP이 재시작을 조용히 무력화하던 사고의 재발 방지 |
| `run.lock`(배타 파일 핸들, 두 Runner 공유) | 두 Writer가 같은 워킹트리를 동시에 고치지 않는다. 크래시해도 OS가 핸들을 회수하므로 stale lock이 다음 시작을 막지 않는다 |
| 완료 marker 기계 Gate | Claude의 자기 신고만으로 프로젝트/Audit이 끝나지 않는다 |
| Audit write guard | Auditor가 제품 코드·테스트·설정·배포 코드를 고치지 못한다(touch-and-revert·history rewrite 포함) |
| `.Handle` 캐시 + 엄격한 JSON fallback | Windows PowerShell 5.1에서 exit code를 못 읽어 성공을 실패로 세던 문제. success는 `subtype=success` + `is_error`가 **진짜 boolean** false + `terminal_reason=completed` 세 조건이 모두 맞을 때만 인정, timeout에는 절대 적용 안 함 |
| `Invoke-Git` 단일 관문 | PS 5.1에서 `$ErrorActionPreference='Stop'` + native 명령 + stderr 리다이렉트가 terminating error가 되어 Supervisor를 통째로 죽이던 경로 |
| 프로세스 트리 강제 종료 | timeout 시 claude의 자식 프로세스가 살아남아 저장소를 계속 건드리는 것 |
| rate-limit 판정 축소 + 연속 상한 | 로그 속 "429" 같은 숫자를 rate-limit으로 오인해 실패 카운터를 우회하고 무한 백오프로 도는 것 |
| session 회전 | 오염된 Worker Session이 결정적으로 계속 실패하는 것(실패 카운터는 그대로 두어 AUTO_STOP은 예정대로 도달) |
| dirty 워킹트리 대기 + 상한 | 사람의 대화형 세션과 충돌 방지 + 유령 dirty로 인한 무한 대기 방지 |
| `--max-budget-usd` | invocation당 API 지출 상한. **PROJECT work unit이 아니다** — 예산으로 한 Worker가 끝나도 곧바로 다음 invocation이 같은 세션을 resume한다 |
| `--permission-mode auto` | `--dangerously-skip-permissions`/`bypassPermissions`는 **절대 쓰지 않는다** |
| Stop hook(`stop_guard.py`) | 완료 marker 없이 끝내려는 Worker를 invocation당 한 번 되돌린다(보조 장치, fail-open) |
| `CLOVIR_SUPERVISOR_PID` 생존 확인 | Supervisor가 자기 프로세스 환경에 넣은 `CLOVIR_SUPERVISED=1`은 **그 창에 그대로 남는다.** Ctrl+C로 멈춘 뒤 같은 창에서 시작한 사람의 대화형 Claude 세션이 Stop hook에 붙잡히던 문제(실제 발생). Supervisor는 종료 시 환경을 원래대로 되돌리고, hook은 PID가 실제로 살아 있을 때만 제동한다 |
| stdin BOM 제거 | `stop_guard.py`가 stdin의 UTF-8 BOM으로 JSON 파싱에 실패해 **조용히 fail-open**하던 경로(제동 장치가 아무도 모르게 무력화됨) |

## 스크립트를 고칠 때

```powershell
powershell -NoProfile -File scripts\runner\tests\runner_contract_tests.ps1   # Windows PowerShell 5.1
pwsh       -NoProfile -File scripts\runner\tests\runner_contract_tests.ps1   # PowerShell 7
```

**두 버전 모두** 통과해야 한다. 실제 운영 호스트는 5.1이다(`var/runner/state.json`의 UTF-8 BOM이
그 증거 — PS 7은 BOM 없이 쓴다).

이 스크립트들은 한글 주석을 담고 있으므로 **UTF-8 BOM으로 저장한다.** BOM이 없으면 5.1이 ANSI
(cp949)로 오독해 파싱 자체가 깨진다. `tests/runner_contract_tests.ps1`의 T04가 이걸 지킨다.

## 알려진 한계 (정직하게 남긴다)

- 이 PowerShell 프로세스가 살아 있는 동안만 돈다. 창을 닫거나 로그아웃·재부팅하면 멈춘다 —
  **자동으로 되살리는 장치는 없다.** 다시 시작하려면 사용자가 같은 명령을 한 번 더 실행한다
  (상태는 git과 `docs/`에서 복원된다).
- 실제 배포(승인된 TEST SERVER 대역)는 이 Runner가 자동으로 못 한다(비밀번호 경계) — 사용자가
  NOPASSWD sudoers를 구성하기 전까지는 구현·테스트·문서화까지만 자동으로 진행된다.
- 연속 실행이 API 지출을 빠르게 누적시킨다(invocation당 상한은 있지만 **횟수 상한은 없다**).
  `--max-budget-usd`는 invocation 단위 상한이지 일일/누적 상한이 아니다. 이것은 의도된 설계다
  (횟수 때문에 프로젝트가 중간에 멈추지 않게 하려는 것). 지출이 걱정되면 `runner.log`의
  `totalRuns`를 보고 필요할 때 `STOP` 파일을 만든다.
- 완료 Gate는 **형식과 정합성**을 검증하지 실제 Audit/구현 품질을 검증하지 못한다. 문서가
  형식을 갖췄다고 조사가 깊다는 뜻은 아니다.
