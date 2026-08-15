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

## 완전 자율 상태 머신 (D-74)

`run_all.ps1` 을 **한 번** 시작하면 수렴할 때까지 사람이 다시 실행할 일이 없다.

```
      ┌──────────────────────────────────────────────────────────┐
      ▼                                                          │
    AUDIT ──(IMPLEMENTATION_REQUIRED)──▶ IMPLEMENT ──▶ VERIFY(새 Audit Cycle)
      │                                      │                   │
      └──(구현거리 없음 + PROJECT_COMPLETE)──▶ CONVERGED ◀────────┘
                                                    (새 Root Cause 0건)
```

- **구현 완료가 끝이 아니다.** 구현이 `PROJECT_COMPLETE` 를 만들면 `-ResetAudit` 로 **새 Audit
  Cycle** 을 돌려 독립 검증한다. 거기서 새 Root Cause 가 나오면 자동으로 구현으로 돌아간다.
- 어느 Phase 든 **완료 marker 없이 끝나면 사람을 기다리지 않고 그 Phase 를 다시 돌린다.**
  예전에는 여기서 `exit 10` + "같은 명령을 다시 실행하세요" 였다 — 그 재실행이 사람 손이었다.
- 무한 반복은 하지 않는다. 재시도마다 **전략을 바꾼다**: Runner 내부 session 회전/유형별 백오프 →
  `-ResumeBlocked`(BLOCKED 격리) → `-ResetAudit`(관점 자체를 새 Cycle 로). 상한을 넘으면 수렴한다.

| 상한 | 기본값 | 뜻 |
|---|---|---|
| `-MaxCycles` | 12 | Audit↔구현 왕복 |
| `-MaxPhaseRetries` | 6 | 같은 Phase 를 전략 바꿔 가며 재시도 |
| `-RequiredCleanVerifications` | 1 | 재감사가 깨끗해야 하는 연속 횟수 |
| `-MaxTotalHours` | 0(무제한) | 전체 실행 시간 |

**사람이 개입해야 끝나는 경우는 둘뿐이다**: `3`=사용자 STOP(사용자만 만든다), `7`=전제조건 실패
(claude 실행 파일 없음 / git 저장소 아님). 그 외(`5` Audit 미수렴, `6` 구현 미수렴, `8` 시간 상한,
`9` Cycle 상한)는 전부 **상한까지 스스로 시도한 뒤** 증거를 남기고 끝난 상태다.

### Human Gate 를 기계적으로 막는 장치

재설계가 필요하다는 것을 정확히 찾아 놓고 "업무 흐름이 바뀌니 사람 승인이 필요하다"며 제안으로만
남기면 그 Root Cause 는 영원히 구현되지 않는다. 개별 항목을 예외 처리하는 대신 **그런 결론 자체가
완료 Gate 를 통과하지 못하게** 막는다.

| 장치 | 무엇 |
|---|---|
| `HANDOFF-SUMMARY` 의 `deferred_for_human_approval` | **반드시 0.** 아니면 `AUDIT_COMPLETE` 거부 |
| `Get-HumanGateLanguage` | HANDOFF 본문에서 `제안으로만`·`사람 승인`·`사용자 판단이 필요`·`구현 보류`·`approval required` 등 **미루는 표현**을 찾아 거부. 제품 기능인 '승인 워크플로'는 오탐하지 않는다 |
| `Invoke-BlockedAutoRecovery` | `AUDIT_BLOCKED`·gate 반복 거부·write guard 위반을 **사람 호출 상태로 쓰지 않는다.** marker 를 격리(증거 보존)하고 session 을 회전한 뒤 "같은 방법을 반복하지 마라 + 대체 경로 목록"을 다음 invocation 에 되먹인다. 상한(`-MaxBlockedRecoveries` 3 / `-MaxWriteGuardRecoveries` 2)을 넘으면 수렴 |
| 두 프롬프트의 금지 목록 | 사람 승인·질문·선택지 대기·ADR 승인·제안으로만 을 명시적으로 금지하고, 대신 쓸 판단 기준 13가지를 준다 |

**자동 revert 는 여전히 하지 않는다.** write guard 위반이 감지돼도 변경 내용은 워킹트리와 이력에
그대로 보존한다 — 사용자 변경 보호가 자율성보다 우선이다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `product_audit_runner.ps1` | PHASE 1. 전수조사 Supervisor. 제품 코드를 고치지 않는다 |
| `autonomous_runner.ps1` | PHASE 2. 구현 Supervisor(Primary Continuous Worker) |
| `run_all.ps1` | **바깥 루프.** PHASE 1 완료 → PHASE 2 자동 연결 + `AUTO_STOP` 제한적 자동 재시작. 한 번 시작해 두면 두 Phase 경계에서 사람을 기다리지 않는다 |
| `runner_common.ps1` | 두 Supervisor가 **똑같이 틀리면 안 되는** 원시 계층(종료 상태 판정, git 호출, dirty 판정, stream 증분 파싱, 실패 유형 분류, rate-limit reset 파싱, state 정규화, 잠금, marker 격리, resume context cache) |
| `stop_guard.py` | Stop hook 보조 제동. Supervisor를 대체하지 않는다 |
| `tests/runner_contract_tests.ps1` | 격리된 scratch 저장소에 **실제 스크립트를 그대로** 돌리는 상태 전이 controlled test |
| `install_task.ps1` | 과거 유물. 이 구조의 일부가 아니다 |

런타임 산출물(전부 git 추적 안 됨):
`var/runner/` — 구현 Runner의 logs·runner.log·state.json·session_id.txt·STOP·AUTO_STOP·PROJECT_COMPLETE·run.lock·quarantine
`var/product-audit/` — Audit의 logs·runner.log·state.json·session_id.txt·cycle.json·STOP·AUTO_STOP·AUDIT_COMPLETE·AUDIT_BLOCKED·IMPLEMENTATION_REQUIRED·IMPLEMENTATION_CONSUMED·quarantine

**cache/index (Source of Truth 아님 — 원본 문서에서 언제든 재생성된다):**

| 파일 | 무엇 |
|---|---|
| `var/runner/active_state.json` | HEAD·branch·dirty·최근 커밋·문서별 줄 수와 수정 시각·미해결 수 |
| `var/runner/unresolved_index.json` | `docs/BACKLOG.md`에서 기계 추출한 **미해결 항목만** (실측 86건 / 26 ms) |
| `var/runner/resume_context.txt` | 직전 invocation에 실제로 주입된 RUN CONTEXT 전문 |
| `var/runner/timings.jsonl` | invocation별 구간 소요 시간·turns·costUsd |

> 이 파일들 때문에 **원본 문서를 지우거나 축약하지 않는다.** 역사 증거는 그대로 두고,
> "매번 읽지는 않는다"로 해결한다. 실측: cache 40 KB vs 예전 프롬프트가 매 회차 강제로
> 읽히던 문서 1.34 MB — **3.0%**.

## 실행

```powershell
# 권장 — 한 번만 시작하면 Audit → 구현까지 이어진다
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\runner\run_all.ps1

# 단계별로 직접 돌리고 싶으면
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\runner\product_audit_runner.ps1   # PHASE 1 (opus/max)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\runner\autonomous_runner.ps1      # PHASE 2 (sonnet/max)
```

모델/effort는 사용자 지시(2026-08-13)로 **고정**이다 — Audit=`opus`/`max`, 구현=`sonnet`/`max`.
매 invocation에 명시적으로 넘긴다(안 넘기면 사용자 settings의 effortLevel이나 세션에 저장된 과거
model에 좌우된다). 동적 정책 코드는 `-DynamicEffort $true` 뒤에 있고 기본은 꺼짐이다.

> **`-ExecutionPolicy Bypass` 가 필요한 이유**: Windows PowerShell 5.1과 PowerShell 7은 실행 정책
> 레지스트리 키가 **서로 다르다.** 이 PC는 7이 `RemoteSigned`, 5.1이 `Undefined`(=Restricted)라
> 5.1 창에서 `.\스크립트`로 바로 실행하면 차단된다. 영구히 풀려면
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`(관리자 권한 불필요).

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
| dirty 워킹트리 대기(**파일 mtime 기준**) | 사람의 대화형 세션과 충돌 방지. 최근 수정이 `DirtyQuietSeconds`(90초)보다 오래됐거나 **직전 invocation이 스스로 만든 dirty**면 기다리지 않는다. 사람이 실제로 타이핑 중이면 mtime이 계속 갱신돼 계속 기다린다(상한 10분) |
| **idle timeout**(`IdleTimeoutMinutes` 25분) | **출력이 그 시간 동안 한 바이트도 안 늘어난** invocation만 강제 종료(프로세스 트리째). `MaxRuntimeMinutes`는 기본 `0`(무제한) — 벽시계로 자르면 일하는 Worker를 자른다 |
| 실패 유형 분류 | `rate-limit`/`overload`/`network`/`resume-failure`는 AUTO_STOP 카운터를 소모하지 않는다(순간 장애로 밤샘 실행이 죽지 않게). 대신 `MaxInfraRetries`(60)와 `MaxIdenticalFailures`(4)가 무한 재시도를 막는다 |
| rate-limit reset 시각 대기 | 지수 백오프로는 몇 시간짜리 구독 한도를 못 맞춘다. stream의 `rate_limit_event.resetsAt`(unix epoch)을 읽어 **그 시각까지** 기다린다(상한 6시간) |
| rate-limit 판정에서 **JSON 키 이름 제외** | 정상 스트림에도 `rate_limit_event`/`rate_limit_info`/`rateLimitType`이 섞여 온다. 키 이름에 걸려 무관한 실패가 rate-limit으로 오분류되면 진짜 실패가 영원히 숨는다 |
| `--permission-mode bypassPermissions` | 무인 실행에는 승인해 줄 사람이 없다. 2026-08-13 실측: 같은 프롬프트로 `auto`는 Write/Bash를 각각 거부(`permission_denials` 2건, 파일 0개 생성), `bypassPermissions`는 거부 0건으로 둘 다 성공. Auditor의 쓰기 경계는 permission mode가 아니라 **write guard**가 강제한다 |
| `--output-format stream-json --verbose` | 활동 신호(idle timeout)·진행 heartbeat·rate-limit reset 시각을 얻는다. 마지막 줄은 여전히 `type=result`라 종료 판정·actualModel 파싱은 그대로 동작한다. `--verbose`는 CLI가 함께 요구한다 |
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
- **승인된 TEST SERVER(CLAUDE.md §9)에서는 Worker가 직접 SSH·sudo·package 설치·systemd/nginx·
  DB·n8n/Runner·배포·E2E를 수행한다.** 예전의 "배포 자격증명 경계"(배포를 건너뛰고 blocker로만
  남기라던 프롬프트 절)는 CLAUDE.md §9와 정면으로 충돌해서 제거했다.
  단 **sudo 비밀번호는 runtime에만 존재한다.** 실측(2026-08-13): SSH는 키 인증으로 비대화형
  접속이 되지만(`BatchMode=yes`, 2초) `sudo -n`은 비밀번호를 요구한다. 그래서 Supervisor는
  시작 전에 환경변수로 받은 값을 자식 프로세스에 물려주기만 하고, 저장소·문서·argv·로그
  어디에도 남기지 않는다(계약 테스트 T57이 이걸 고정한다).

  ```powershell
  $env:CLOVIR_TEST_SUDO_PASSWORD = '<비밀번호>'      # 또는 -PromptForSudoPassword
  .\scripts\runner\run_all.ps1
  ```

  값이 없으면 sudo가 필요한 작업만 못 하고 나머지는 그대로 진행한다(그 blocker 때문에 다른
  작업까지 멈추지 않는다). 접속 대상 host는 하드코딩하지 않고 저장소 설정에서 찾는다
  (`Get-TestServerTargetFromRepo`, 승인 대역 `10.100.64.X` 밖은 절대 반환하지 않는다).
- **누적 지출/사용량 상한이 없다.** `MaxBudgetUsd` 기본값은 이제 `0`(무제한)이다 — 그 값은
  지출을 막지 못하면서(invocation 횟수가 무제한이므로) 작업만 문장 중간에서 잘랐고, 잘릴 때마다
  다음 invocation이 상태 문서 전체를 다시 읽는 비용을 새로 냈다. 실측: 실제 invocation들이
  `$13.83`/`$13.27`에서 `terminal_reason=completed`로 끝났다 — 일을 마쳐서가 아니라 상한에
  닿아서다. 지금 실질 경계는 `MaxRuntimeMinutes`(hang 보호)뿐이다. 총량을 제한하려면
  `runner.log`의 `totalRuns`를 보고 `STOP` 파일을 만들거나, 각 invocation JSON의
  `total_cost_usd`를 누적하는 상한을 추가해야 한다(아직 없다). 이제 invocation마다
  `var/runner/timings.jsonl`에 `costUsd`가 남으므로 집계 자체는 가능하다.
- 완료 Gate는 **형식과 정합성**을 검증하지 실제 Audit/구현 품질을 검증하지 못한다. 문서가
  형식을 갖췄다고 조사가 깊다는 뜻은 아니다.
- 두 Supervisor는 여전히 `run.lock`을 공유해 **동시에 돌지 않는다.** 메인 워킹트리에 Writer를
  하나로 유지하는 것이 목적이고, 그 계약은 유지했다. "구현 중에 다음 Root Cause를 별도
  worktree에서 read-only로 미리 조사한다"는 겹치기 실행은 안전하게 가능하지만(Audit Worker가
  `git worktree` 사본에서 읽기만 하면 된다) marker/cycle/state 파일이 전부 `var/` 단일 경로를
  가정하고 있어 그 경로 분리까지 함께 해야 한다 — 이번 변경에서는 넣지 않았다. 대신 구현
  Worker가 **자기 invocation 안에서** subagent/background agent/별도 worktree로 독립 조사를
  병렬화하도록 프롬프트에 명시했다(메인 통합 writer는 여전히 하나).

## 품질 계약 — 두 Phase가 같은 자를 쓴다 (D-73)

Audit이 Skill의 rubric으로 문제를 **찾고**, 구현이 그 rubric을 안 읽고 **만들면** 설계 의도는
맞아도 결과물 품질이 빗나간다. 그 비대칭이 실제로 있었다(Audit 프롬프트의 Skill 언급 22곳,
구현 0곳). 두 지점으로 막는다.

| 지점 | 무엇 |
|---|---|
| Handoff의 `quality_rubric` 필드 | Audit이 그 Root Cause를 판정할 때 **실제로 쓴 자**(Skill 실제 이름 + 구체 항목). PA-RC 필수 필드라 비면 완료 Gate가 거부한다 |
| 구현 프롬프트의 Skill 사용 계약 | 지금 하는 작업에 해당하는 Skill이 있으면 **만들기 전에** 부른다. 다 만든 뒤 검사가 아니다 |

- 다섯 개만 쓰라는 계약이 **아니다.** `Skill` 도구 목록(실측 144개)이 정본이고, 작업 종류별로
  이 스택(FastAPI+SQLite / React+Vite)에 걸리는 것을 고른다 — UI/UX·문구 축의
  `ui-ux-pro-max`·`redesign-existing-projects`·`impeccable`·`ux-writing`·`humanize-korean`,
  그리고 `python-patterns`·`python-testing`·`api-design`·`backend-patterns`·
  `database-migrations`·`security-review`·`frontend-patterns`·`e2e-testing`·
  `superpowers:systematic-debugging` 등.
- **다른 스택 Skill을 억지로 적용하지 않는다** — 목록에는 `django-*`·`laravel-*`·`springboot-*`·
  `postgres-patterns`도 있다. 이 제품은 FastAPI + SQLite다.
- Skill 확인은 **파일시스템 경로 추측이 아니라 `Skill` 도구 목록**이다(경로가 프로젝트/사용자/
  플러그인 세 군데에 흩어져 있어 추측하면 틀린다).
- 우선순위는 두 Phase가 같은 문장을 쓴다: 사용자 업무 성공 > 기능 정확성 > 데이터/RBAC/보안 경계
  > 명확한 UX > 일관성/접근성 > UX Writing > 한국어 자연스러움 > 시각적 완성도.

### 무인 실행에는 브라우저 MCP 도구가 없다

실측: `-p` 비대화형 세션에는 Chrome/browser MCP가 **하나도 붙지 않는다.** 그런데 CLAUDE.md §10은
Chrome Whole-product E2E를 필수 완료 Gate로 요구한다. 저장소의 Playwright 하네스를 쓴다.

- `scripts/ui_qa/` — 화면 × 라이트/다크 × 뷰포트 행렬을 실제 로그인 상태로 순회하며 스크린샷·
  레이아웃·콘솔·접근성을 검사하고 HTML 리포트를 만든다. `contrast.py`·`keyboard.py`·
  `failure_states.py`·`hostile_data.py`·`fab_occlusion.py` 등 축별 모듈이 이미 있다.
  사용법 정본은 `scripts/ui_qa/README.md`, 산출물은 `dist/`(gitignore).
- 새로 만들지 말고 **확장**한다. 브라우저 바이너리가 없으면 직접 설치하고 계속한다(§9 권한).

### WARM 회차를 위해 프롬프트에 인라인된 것

WARM은 CLAUDE.md를 다시 읽지 않고 긴 세션은 context가 압축된다. 참조만 남기면 규칙 **내용**이
사라지므로, 항상 전송되는 core 프롬프트에 다음을 인라인한다: CLAUDE.md §3 불변 규칙 10개 요약,
배포 흐름 순서(§9), Responsive/Light-Dark/Accessibility 축. 애매하면 CLAUDE.md 원문이 정본이다.

## 진행 상황 보기 / 성능 측정

Worker의 stdout은 여전히 `var/runner/logs/<타임스탬프>.log`로 redirect된다(안정성 유지). 대신
Supervisor가 그 파일의 증가분만 증분 파싱해 콘솔에 짧은 heartbeat를 찍는다 — Claude JSON을
콘솔에 덤프하지 않는다.

```
  ▶ #1 sonnet/max · 경과 12.4분 · 이벤트 843 · 도구 61회 (최근 Edit) · 출력 4.2MB · 마지막 활동 3초 전 · PID 20636
```

"마지막 활동 N초 전"이 **느림**과 **hang**을 구분하는 축이다. 그 값이 `IdleTimeoutMinutes`에
도달하면 그때만 죽인다.

`var/runner/timings.jsonl`에는 invocation마다 구간별 소요 시간이 한 줄 JSON으로 남는다
(`dirtyCheckMs`/`contextBuildMs`/`promptPrepMs`/`workerStartupMs`/`workerRunMs`/`postCheckMs`/
`backoffMs`/`totalMs`/`turns`/`costUsd`). 2026-08-13 실측(실제 CLI, 실제 저장소):
Supervisor orchestration 총합은 invocation당 **약 1.2초**이고 나머지는 전부 Claude 실행이다 —
"PowerShell이 느리다"는 가설은 수치로 기각됐다.
