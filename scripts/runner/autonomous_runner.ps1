<#
.SYNOPSIS
  ClovirONE Web Assistant 자율 완성 루프 — PHASE 2 구현 Supervisor(Primary Continuous Worker).

.DESCRIPTION
  사용자가 PowerShell 에서 한 번 시작한 **이 프로세스 자체**가 Primary Continuous Supervisor 다.
  Windows Task Scheduler 의존은 폐기됐다(CLAUDE.md §0) — 이 루프를 되살려 주는 scheduled task도,
  heartbeat도, fallback continuity도 없다. 한 invocation 이 끝나면 성공이든 실패든
  `PROJECT_COMPLETE` 가 기계 Gate 를 통과할 때까지 sleep 없이 곧장 다음 invocation 으로 간다.

  각 invocation 은 새 비대화형(-p) 프로세스를 띄우지만 `--resume` 으로 **같은 Worker Session**
  을 이어받는다(OS 프로세스 재시작과 대화 연속성은 별개다). 세션 id 는 var\runner\session_id.txt.

  2026-08-12 실측으로 확인된 세션 계약(설치 CLI 2.1.228):
    - `--session-id <신규 UUID>` 로 시작 → 응답 JSON 의 session_id 가 요청값과 일치.
    - 같은 UUID 로 `--resume` 재호출(새 프로세스) → 이전 대화를 실제로 기억.
    - 없는 UUID 로 `--resume` → exit != 0, stderr "No conversation found with session ID: ...".

  === 2026-08-12 심층 검수에서 실제로 고친 결함 ===
  A. **Windows PowerShell 5.1 ExitCode=$null 의 근본 원인 수정.** `Start-Process -PassThru` 직후
     `$proc.Handle` 을 한 번 읽어 핸들을 캐시하면 5.1 에서도 정확한 exit code 가 나온다(실측:
     핸들 미접근 → `<null>`, 접근 → 7). 운영 로그를 보면 **모든** invocation 이 OS exit code 를
     못 읽고 있었고, JSON fallback 도입 전에는 그 때문에 연속 3회 실패로 AUTO_STOP 까지 갔다
     (13:23~14:15 구간). 엄격한 JSON fallback 은 그대로 유지하되 이제 심층 방어다.
  B. **PS 5.1 에서 git 호출이 Supervisor 를 통째로 죽일 수 있었다.** `$ErrorActionPreference='Stop'`
     + native 명령 + stderr 리다이렉트는 5.1 에서 terminating error 다(실측). `git rev-parse
     --short HEAD 2>$null` 한 줄로 밤샘 루프가 끝날 수 있었다(git 이 dubious-ownership 경고 등
     stderr 를 한 줄만 뱉어도 발생). 모든 git 호출을 `Invoke-Git` 으로 옮겼다.
  C. **PROJECT_COMPLETE 기계 Gate 가 문서에만 있고 코드에 없었다.** CLAUDE.md §11/§13 은
     "IMPLEMENTATION_REQUIRED 가 유효한 동안 PROJECT_COMPLETE 를 인정하지 않고 premature marker
     를 제거한다"고 적어 놨지만 실제 코드에는 그 검사가 **하나도 없었다** — Claude 가 내용 있는
     파일 하나만 만들면 프로젝트가 끝났다. 이제 Supervisor 가 검증하고, 거부하면 marker 를
     격리(삭제 아님)한 뒤 **거부 사유를 다음 invocation 프롬프트에 되먹여** 계속 진행한다.
  D. **state.json 스키마가 바뀌면 죽었다.** `[pscustomobject]` 는 없는 속성에 대입하면 throw 한다
     (실측). 게다가 예전 `Load-State` 는 try/catch 도 없어 손상된 JSON 하나로 루프가 끝났다.
  E. rate-limit 오탐(로그 어딘가의 "429" 숫자)이 실패 카운터를 우회해 **무한 백오프**로 돌 수
     있었다. 판정을 좁히고 연속 rate-limit 상한을 두었다.
  F. timeout 시 루트 프로세스만 죽여 claude 의 자식들이 살아남을 수 있었다 → 트리 강제 종료.
  G. dirty 대기가 매 launch 마다 고정 2분 x 5회였다 → 사람이 편집 중이면 내용이 변하므로,
     짧게 시작해 늘리는 backoff 로 바꿔 유령 dirty 에서 낭비를 줄였다(상한은 그대로).

  안전장치(전부 유지):
    - var\runner\STOP        — 사용자만 만든다. 있으면 Worker 를 한 번도 안 띄우고 exit 3.
    - var\runner\AUTO_STOP   — 스크립트의 자동 정지 흔적. 수동 재시작을 확인으로 보고 정리한다.
    - var\runner\PROJECT_COMPLETE — 내용이 있어야 하고 기계 Gate 를 통과해야 유효하다.
    - var\runner\run.lock    — 배타 파일 핸들. product_audit_runner.ps1 과 **공유**한다.
    - --max-budget-usd       — **기본 0(무제한)**. 양수를 주면 invocation 당 상한이 걸리지만,
                               그건 지출 가드가 아니라 일을 문장 중간에서 자르는 장치였다.
    - Process.WaitForExit(ms)— 멈춘 invocation 만 죽인다(루프는 안 죽는다).
    - --permission-mode auto — `--dangerously-skip-permissions`/`bypassPermissions` 는 절대 안 씀.
    - Stop hook(stop_guard.py) — 보조 제동. Supervisor 를 대체하지 않는다.
#>

param(
    [string]$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant",
    [string]$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe",

    # controlled test seam — 평소엔 비운다. 이름 주의: PowerShell 변수는 대소문자를 구분하지
    # 않는다. 루프 안의 per-invocation 변수와 같은 이름을 쓰면 파라미터가 조용히 덮어써진다
    # (2026-08-12 실제로 당했다 — 테스트 프롬프트 대신 내장 프롬프트가 나갔다).
    [string]$PromptOverrideFile = "",

    # Worker 품질 계약(D-65): 매 invocation 에 **명시적으로** 넘긴다. 새 세션이든 --resume 이든
    # 항상 넘긴다. 안 넘기면 사용자 settings 의 effortLevel 이나 세션에 저장된 과거 model 에
    # 좌우된다(실측 확인). 설치 CLI 가 허용하는 effort: low|medium|high|xhigh|max.
    [string]$Model  = "sonnet",
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$Effort = "max",

    # 0 = 무제한(production 기본). invocation 횟수는 Supervisor 종료 조건이 **아니다**.
    [int]$MaxIterationsPerLaunch = 0,
    [int]$MaxConsecutiveFailures = 3,
    # 구독(CLI) 사용량 한도에 걸리면 몇 시간 대기가 정상이다. 예전 값(8)이면 약 2시간 만에
    # 일반 실패로 전환돼 밤중에 AUTO_STOP 됐다. 대기 한도만 늘린 것이고, 진짜 실패는 여전히
    # 별도로 분류되어 MaxConsecutiveFailures 에서 멈춘다.
    [int]$MaxConsecutiveRateLimitHits = 20,
    [int]$MaxCompletionRejections = 5,       # premature PROJECT_COMPLETE 반복 생성 방지

    # ★ 0 = 무제한(기본). 이 값은 "지출 가드"가 아니었다 — invocation 횟수가 무제한이라 총액을
    #   막지 못하면서 실질적으로는 **일을 문장 중간에서 자르는** 장치로만 동작했다(실측: 실제
    #   invocation 들이 $13.83 / $13.27 에서 terminal_reason=completed — 상한에 닿아서 종료).
    #   잘릴 때마다 다음 invocation 이 상태 문서 전체를 다시 읽는 비용을 새로 낸다.
    #   양수를 주면 예전처럼 invocation 당 상한이 걸린다.
    [int]$MaxBudgetUsd = 0,

    # double 인 이유는 controlled test 가 timeout 경로를 몇 초로 실제 실행해 보기 위함이다.
    # 예산 상한을 없애면 실질 절단점이 이쪽으로 옮겨오므로 함께 넉넉히 잡는다. hang 보호는
    # 남긴다 — 멈춘 프로세스를 밤새 방치하는 것이 더 나쁘다. 0 = 무제한(hang 보호 없음).
    [double]$MaxRuntimeMinutes = 240,
    [int]$DirtyRetrySeconds = 120,
    [int]$MaxUnchangedDirtyWaits = 5,
    # 노출 이유는 위와 같다(test seam). production 기본값은 그대로다.
    [int]$RateLimitBaseBackoffSeconds = 60,
    [int]$RateLimitMaxBackoffSeconds = 1800
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runner_common.ps1")

$RunnerDir  = Join-Path $ProjectDir "var\runner"
$LogDir     = Join-Path $RunnerDir "logs"
$QuarantineDir = Join-Path $RunnerDir "quarantine"
$StopFile   = Join-Path $RunnerDir "STOP"            # 사용자만 만든다
$AutoStopFile = Join-Path $RunnerDir "AUTO_STOP"     # 자동 실패 흔적
$CompleteFile = Join-Path $RunnerDir "PROJECT_COMPLETE"
$LockFile   = Join-Path $RunnerDir "run.lock"
$StateFile  = Join-Path $RunnerDir "state.json"
$RunnerLog  = Join-Path $RunnerDir "runner.log"
$GateRejectionFile = Join-Path $RunnerDir "last_completion_rejection.txt"
$SessionIdFile = Join-Path $RunnerDir "session_id.txt"  # secret 아님(불투명 UUID), var/ 는 gitignore

# Product Audit(PHASE 1)이 넘긴 계약
$AuditDir = Join-Path $ProjectDir "var\product-audit"
$ImplementationRequiredFile = Join-Path $AuditDir "IMPLEMENTATION_REQUIRED"
$ImplementationConsumedFile = Join-Path $AuditDir "IMPLEMENTATION_CONSUMED"
$AuditCompleteFile = Join-Path $AuditDir "AUDIT_COMPLETE"
$HandoffRel = "docs/product-audit/PRODUCT_AUDIT_HANDOFF.md"
$HandoffFile = Join-Path $ProjectDir "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"

$StateDefaults = [ordered]@{
    consecutiveFailures       = 0
    consecutiveRateLimitHits  = 0
    completionRejections      = 0
    sessionRotatedForStreak   = $false
    lastRunAt                 = $null
    lastExitCode              = $null
    totalRuns                 = 0
    totalIterationsThisLaunch = 0
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-RunnerLog([string]$msg) { Write-LogLine $RunnerLog $msg }

# ── 완료 Gate ─────────────────────────────────────────────────────────────────
# stop_guard.py 의 project_complete() 와 **같은 기본 규칙**(존재만으로는 부족, 내용 필수)에
# Product Audit Handoff 계약을 더한 것이다. Stop hook 은 이 추가 규칙을 모르지만, 그래도
# 최종 판정은 Supervisor 가 한다(CLAUDE.md §11/§13).
function Test-ProjectCompletionGate {
    $fail = New-Object System.Collections.Generic.List[string]

    if (-not (Test-MarkerValid $CompleteFile)) {
        $fail.Add("PROJECT_COMPLETE 가 없거나 비어 있다(빈 marker 는 완료로 인정하지 않는다).")
        return [pscustomobject]@{ Passed = $false; Failures = @($fail.ToArray()) }
    }

    if (Test-MarkerValid $ImplementationRequiredFile) {
        $reqText  = Read-TextOrEmpty $ImplementationRequiredFile
        $reqCycle = Get-KeyValueFromText $reqText "cycle_id"
        $reqCount = Get-KeyValueFromText $reqText "root_causes"
        $fail.Add("Product Audit 의 IMPLEMENTATION_REQUIRED 가 아직 유효하다(cycle_id='$reqCycle', root_causes='$reqCount'). " +
                  "현재 Handoff 의 actionable Root Cause 와 Acceptance Criteria 를 모두 닫고 검증한 뒤 " +
                  "이 marker 를 제거하고 IMPLEMENTATION_CONSUMED 를 남겨야 완료다(CLAUDE.md §13).")

        if (-not (Test-MarkerValid $HandoffFile)) {
            $fail.Add("계약 오류: IMPLEMENTATION_REQUIRED 는 있는데 $HandoffRel 이 없거나 비어 있다. " +
                      "marker 를 임의로 지우지 말고 Audit 계약 오류로 기록한 뒤 독립적으로 가능한 작업을 계속하라.")
        }

        $consumedText  = Read-TextOrEmpty $ImplementationConsumedFile
        $consumedCycle = Get-KeyValueFromText $consumedText "cycle_id"
        if ($consumedCycle -and $consumedCycle -eq $reqCycle) {
            $fail.Add("IMPLEMENTATION_CONSUMED(cycle_id='$consumedCycle')는 있는데 IMPLEMENTATION_REQUIRED 가 아직 남아 있다. " +
                      "구현이 정말 끝났다면 REQUIRED marker 를 제거하라.")
        }
    }

    return [pscustomobject]@{ Passed = ($fail.Count -eq 0); Failures = @($fail.ToArray()) }
}

# ── 잠금(Product Audit Runner 와 공유) ────────────────────────────────────────
$lock = Open-ExclusiveLock -LockFile $LockFile
if (-not $lock.Acquired) {
    Write-Banner @(
        "이미 살아있는 Supervisor(PID=$($lock.Holder))가 이 저장소를 잡고 있어 이 프로세스는 아무 것도 하지 않고 종료합니다.",
        "autonomous_runner.ps1 과 product_audit_runner.ps1 은 같은 잠금을 공유합니다 — 동시에 돌 수 없습니다.",
        "두 Writer 가 같은 워킹트리를 동시에 고치지 않게 하기 위한 의도된 동작입니다. 사유: $($lock.Reason)",
        "그 Supervisor 를 멈추려면: var\runner\STOP 파일을 만들거나(다음 invocation 전에 확인) 해당 PID 를 종료하세요."
    )
    Write-RunnerLog "잠금 획득 실패(보유 PID=$($lock.Holder)) — 이 프로세스는 종료한다. 사유: $($lock.Reason)"
    exit 0
}

# 종료 코드로 무인 실행의 결과를 구분한다(사람이 로그를 안 봐도 상태를 알 수 있게):
#   0 = PROJECT_COMPLETE(Gate 통과), test-override 상한, 또는 다른 Supervisor 가 잠금 보유
#   3 = 사용자 STOP        6 = 연속 실패/완료 Gate 반복 거부로 AUTO_STOP     7 = 전제조건 실패
$script:FinalExit = 0

try {
    $problems = @(Test-RunnerPrerequisites -ProjectDir $ProjectDir -ClaudeExe $ClaudeExe)
    if ($problems.Count -gt 0) {
        Write-Banner (@("Supervisor 를 시작할 수 없습니다 — 전제조건이 맞지 않습니다:") + $problems)
        Write-RunnerLog "전제조건 실패 — 실행하지 않고 종료: $($problems -join ' | ')"
        $script:FinalExit = 7; exit $script:FinalExit
    }

    # ── STOP(사용자) vs AUTO_STOP(자동 실패 흔적) ──
    # 이 둘을 같은 파일로 뭉개면 "사용자가 명시적으로 멈춘 것"과 "예전에 자동으로 멈춘 흔적"을
    # 구분할 수 없다. 2026-08-11 에 실제로 그 때문에 12시간 넘게 조용한 no-op 였다.
    if (Test-Path -LiteralPath $StopFile) {
        $stopBody = (Read-TextOrEmpty $StopFile).Trim()
        Write-Banner @(
            "STOP 파일이 있어 이번 실행은 Worker 를 한 번도 띄우지 않고 종료합니다.",
            "  경로: $StopFile",
            "  내용: $(if ($stopBody) { $stopBody } else { '(비어 있음)' })",
            "이 파일은 '사용자가 명시적으로 Supervisor 를 멈춘 상태'를 뜻합니다.",
            "재개하려면 이 파일을 지우고 이 스크립트를 다시 실행하세요."
        )
        Write-RunnerLog "STOP 파일 있음 — 아무 invocation 도 실행하지 않고 종료: $StopFile"
        $script:FinalExit = 3; exit $script:FinalExit
    }

    if (Test-Path -LiteralPath $AutoStopFile) {
        # 사람이 이 스크립트를 **직접 다시 시작한 것** 자체를 그 실패에 대한 확인으로 본다.
        $autoBody = (Read-TextOrEmpty $AutoStopFile).Trim()
        Write-Banner @(
            "이전 실행이 연속 실패로 스스로 멈춘 흔적(AUTO_STOP)이 있습니다:",
            "  $autoBody",
            "사용자가 직접 이 스크립트를 다시 시작했으므로 그 실패를 확인한 것으로 보고,",
            "흔적을 지우고 연속 실패 카운터를 0으로 되돌린 뒤 계속 진행합니다.",
            "정말로 멈춰 두려면 대신 $StopFile 을 만드세요."
        )
        Write-RunnerLog "AUTO_STOP 흔적 발견 — 수동 재시작을 확인으로 보고 정리한 뒤 진행. 내용: $autoBody"
        Remove-Item -LiteralPath $AutoStopFile -Force -ErrorAction SilentlyContinue
        $s = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        $s.consecutiveFailures = 0
        $s.consecutiveRateLimitHits = 0
        $s.completionRejections = 0
        [void](Save-StateFile $StateFile $s)
    }

    # Product Audit 계약 상태를 시작 시 한 번 크게 알린다(조용한 오해 방지).
    $implRequired = Test-MarkerValid $ImplementationRequiredFile
    if ($implRequired) {
        $reqText = Read-TextOrEmpty $ImplementationRequiredFile
        $reqCycle = Get-KeyValueFromText $reqText "cycle_id"
        $reqCount = Get-KeyValueFromText $reqText "root_causes"
        if (Test-MarkerValid $HandoffFile) {
            Write-Banner @(
                "Product Audit 이 넘긴 구현 계약이 있습니다 — 이번 실행은 그것을 반드시 입력으로 씁니다.",
                "  cycle_id=$reqCycle  root_causes=$reqCount",
                "  Handoff: $HandoffRel",
                "이 marker 가 유효한 동안 PROJECT_COMPLETE 는 인정되지 않습니다."
            )
        } else {
            Write-Banner @(
                "계약 오류: IMPLEMENTATION_REQUIRED 는 있는데 $HandoffRel 이 없거나 비어 있습니다.",
                "marker 를 임의로 지우지 않습니다. Audit 계약 오류로 기록하고 독립적으로 가능한 작업을 계속합니다."
            )
        }
        Write-RunnerLog "Product Audit Handoff 감지: cycle_id=$reqCycle rootCauses=$reqCount handoffValid=$(Test-MarkerValid $HandoffFile)"
    } elseif (Test-MarkerValid $AuditCompleteFile) {
        Write-RunnerLog "Product Audit 은 완료됐고 구현 필요 marker 는 없다(IMPLEMENTATION_REQUIRED 없음)."
    }

    # Supervisor 가 띄운 Worker 임을 표시한다 — Stop hook(stop_guard.py)이 이 표시를 보고만
    # 동작한다. 이 프로세스 환경에 넣어 두면 Start-Process 로 띄우는 child 가 그대로 상속한다.
    # Audit Runner 가 남겼을 수 있는 표시는 지운다(역할 혼동 방지).
    # 끝날 때 finally 에서 원래 값으로 되돌린다 — 안 그러면 이 값이 **호출한 셸에 남아**,
    # 같은 창에서 시작한 사람의 대화형 Claude 세션까지 Stop hook 이 붙잡는다(실제로 발생).
    # CLOVIR_SUPERVISOR_PID 를 함께 넘기는 이유: Ctrl+C 로 멈추면 아래 finally 의 환경 복원이
    # 보장되지 않는다. Stop hook 이 "표시 + 그 PID 가 실제로 살아 있는가"를 함께 보게 해서,
    # 죽은 Supervisor 가 셸에 남긴 흔적이 사람의 대화형 세션을 붙잡지 못하게 한다.
    $script:EnvSnapshot = Save-EnvSnapshot @("CLOVIR_SUPERVISED", "CLOVIR_PRODUCT_AUDIT", "CLOVIR_SUPERVISOR_PID")
    Remove-Item Env:CLOVIR_PRODUCT_AUDIT -ErrorAction SilentlyContinue
    $env:CLOVIR_SUPERVISED = "1"
    $env:CLOVIR_SUPERVISOR_PID = "$PID"

    $prompt = @'
당신은 ClovirONE Web Assistant 프로젝트를 **끝까지 완성**하는 작업을 이어받는다. 이것은 사람이
실시간으로 지켜보지 않는, 비대화형·무인 실행이다.

**작업 단위는 PROJECT 전체 하나뿐이다.** 지금 이 프로세스 호출(invocation)은 work unit이 아니다 —
"이번 회차", "이번 batch", "이번 turn 범위", "iteration 완료" 같은 단위는 존재하지 않는다. 한
Root Cause를 닫았으면 곧바로 같은 호출 안에서 다음 Root Cause로 넘어간다. 호출 자체가
budget/context 한계로 끝나는 것은 허용되지만, 그때도 PROJECT가 끝난 것이 아니며 로컬 PowerShell
Supervisor가 지연 없이 같은 Worker Session을 즉시 resume한다.

이 호출은 이전과 같은 Worker Session을 이어받은 것일 수도(대화 기억 있음), 방금 새로 시작된
것일 수도 있다(대화 기억 없음 — 정상). 어느 쪽이든 아래 1단계부터 실제로 다시 확인하고 시작하라 —
대화 기억이 있어도 그것을 저장소의 실제 현재 상태보다 우선 신뢰하지 마라.

## 1단계 — 상태 복원(대화 기억이 있어도 실제로 다시 확인)
다음을 순서대로 읽어라: CLAUDE.md, docs/WORK_STATE.md, docs/BACKLOG.md, docs/QA_COVERAGE.md,
docs/DECISIONS.md, docs/PROGRESS_STATUS.md, docs/WORK_PLAN_INDEX.md, 그리고 현재 `git status`·
`git log --oneline -20`. 대화 기억이 아니라 이 파일들과 git만 진실이다. WORK_STATE.md의
"다음 후보" 몇 줄만 보지 말고 BACKLOG.md·QA_COVERAGE.md 전체와 대조해 실제로 남은 작업
전체를 기준으로 판단한다.

## 1-A단계 — Product Audit Handoff 계약 (있으면 반드시 사용)
아래 RUN CONTEXT의 `implementation_required=true` 이거나 BACKLOG.md 항목이 `PA-RC-` 를
참조하면, **docs/product-audit/PRODUCT_AUDIT_HANDOFF.md 를 구현 입력으로 반드시 사용한다.**
Backlog 한 줄만 보고 구현하지 마라.

- 먼저 Handoff의 PA-RC 목록(Index)만 훑고, 지금 고를 Root Cause의 블록 상세를 읽어라.
  각 블록에는 problem / expected / actual / intent_evidence / 영향 범위(routes·frontend·api·
  backend·data·rbac·integration·state_transition) / implementation_direction / constraints /
  regression_risk / acceptance_criteria / required_tests / qa_gaps / evidence_refs 가 있다.
- 필요하면 evidence_refs가 가리키는 PRODUCT_AUDIT_FINDINGS.md ·
  PRODUCT_AUDIT_FEATURE_CONTRACTS.md · PRODUCT_AUDIT_COVERAGE.md 의 **해당 구간만** 추적하라.
  매번 전체를 컨텍스트에 덤프하지 마라.
- **Audit 결과를 맹신하지 마라.** 구현 직전에 현재 Source에서 그 문제가 여전히 재현되는지
  확인하라. 이미 다른 작업으로 해결됐다면 중복 수정하지 말고, 그 근거(커밋/테스트/파일:줄)를
  BACKLOG.md와 WORK_STATE.md에 남겨라.
- Audit 문서는 감사 시점의 **증거 Snapshot**이다. 구현 결과에 맞추려고 Findings/Contracts를
  임의로 지우거나 사실을 다시 쓰지 마라. 해결 상태는 BACKLOG.md·QA_COVERAGE.md·WORK_STATE.md와
  실제 테스트 증거에 기록한다.
- 각 PA-RC의 `acceptance_criteria`를 **구현 완료 기준에 그대로 포함**한다. 하나라도 검증하지
  못했으면 그 Root Cause는 완료가 아니다.
- 현재 Handoff의 actionable Root Cause를 전부 닫고 각 Acceptance Criteria를 검증한 뒤에만
  var/product-audit/IMPLEMENTATION_REQUIRED 를 제거하고, 같은 시점에
  var/product-audit/IMPLEMENTATION_CONSUMED 를 아래 키로 만든다.
      cycle_id=<Handoff의 cycle_id와 동일>
      consumed_at=<ISO8601>
      final_commit=<최종 구현 commit SHA>
      verification=<무엇을 어떻게 검증했는지 한 줄 요약>
  REQUIRED가 있는데 Handoff가 없거나 비어 있으면 marker를 지우지 마라 — Audit 계약 오류로
  기록하고 독립적으로 가능한 다른 작업을 계속하라.

## 2단계 — 남은 작업 판단과 즉시 실행
제품 전체 기준으로 영향도가 가장 높은 Root Cause를 스스로 고르고 **묻지 않고 즉시 시작**한다
(Critical/High, Master Plan 의존관계, 큰 미검증 영역, Root Cause 레버리지, 현재 작업과의
locality 순). 하나를 닫으면 멈추지 말고 context/budget/tool 상황이 허용하는 동안 곧바로 다음
영향도 높은 Root Cause로 넘어간다 — "다음 호출에서 하겠다"는 선택지는 없다.

Backlog ID는 **inventory/evidence이지 실행 단위가 아니다.** ID를 한 건씩 기계적으로 처리하지
말고, 같은 Root Cause를 공유하는 항목들을 묶어서 저장소 전체에서 함께 조사하고 함께 고친다
(UI → shared component + 전체 소비처, RBAC → 같은 permission/scope 경로 전체, DB → 같은
transaction/retry 패턴 전체). "N건 처리"는 진척 단위가 아니다.

## 3단계 — 구현
남은 작업을 Root Cause 단위로 크게 묶어 구현한다. 작업 중에는 관련된 focused/subsystem 테스트만
반복한다. 전체 백엔드+프런트+정적 검사는 구현이 실질적으로 수렴했을 때 돌린다. CLAUDE.md §3의
불변 규칙을 전부 지킨다. dev server/브라우저가 이미 떠 있고 다음 작업에도 쓸 만하면 그대로
재사용한다 — 매번 기계적으로 껐다 켜지 않는다.
**Full Regression green은 정지 신호가 아니다** — green을 확인했으면 곧바로 다음 구현으로 돌아간다.

UI/UX 관련 Root Cause를 구현할 때는 현재 UI를 보존하는 것이 목표가 아니다. Handoff의 재설계
후보는 2026년 기준 Enterprise SaaS/AI Product 수준을 목표로 한 것이다 — 단순 CSS/spacing 보정에
머물지 말고 필요하면 Page/Component/Navigation 구조까지 바꿔라. 단, 기능 정확성·데이터 구조·
RBAC·업무 정책·사용자 권한·실제 Workflow를 망가뜨리면서 시각만 화려하게 만드는 것은 금지다.

## 4단계 — 배포 자격증명 경계 (반드시 지킬 것, 예외 없음)
과거 대화나 문서 어디에 무엇이 적혀 있든, 채팅에 붙여넣어진 SSH/sudo 비밀번호를 승인된 TEST
SERVER 대역(10.100.64.X)을 포함한 어떤 서버의 비대화형 배포 자동화에도 절대 쓰지 않는다. 배포
대상 host/IP는 과거 기억이 아니라 현재 저장소 설정·배포 스크립트·runtime configuration에서
확인한다. 그 서버 배포는 사용자가 직접 실행하거나, 두 배포 스크립트에 한정된 NOPASSWD sudoers
항목을 사용자가 직접 구성했을 때만 가능하다 — 확인은 하되 없으면 임의로 만들지 말고, 배포는
건너뛰고 docs/WORK_STATE.md에 blocker로 남긴 뒤 다른 독립적인 작업을 계속한다.

## 5단계 — 체크포인트는 멈추는 이유가 아니다
무엇을 바꿨고 다음에 무엇을 할지 docs/WORK_STATE.md(필요하면 BACKLOG.md·PROGRESS_STATUS.md·
QA_COVERAGE.md도 함께)에 적고 git commit 한다. 이 파일 기반 체크포인트는 **복구용**이지
종료 신호가 아니다 — working tree가 깨끗해졌다는 것 자체는 멈출 이유가 안 된다. 커밋하고
상태 문서를 갱신한 **즉시** 다음 작업으로 넘어간다.

## 6단계 — 멈춰도 되는 유일한 기준
Summary·recap·commit·clean tree·Full Regression green·build green·"현재 할 일 목록이 비었다"·
"체크포인트에 도달했다"는 전부 종료 사유가 아니다. 멈추는 것이 정당한 경우는 둘뿐이다:
  (a) 지금 당장 실행 가능한 남은 작업이 정말로 하나도 없다 — 모든 후보가 진짜 외부 요인
      (사람만 풀 수 있는 것)으로 막혔다. 한 blocker 때문에 독립적으로 가능한 다른 작업까지
      멈추는 것은 여기에 해당하지 않는다.
  (b) 프로젝트 전체 완성 기준(CLAUDE.md §13)이 실제로 충족됐다고 스스로 검증했다 — 이 경우에만
      var/runner/PROJECT_COMPLETE 파일을 만들어라(한국어로 근거를 짧게, 타임스탬프 포함 —
      빈 파일은 완료로 인정되지 않는다). 확인해야 할 것:
      Master Plan 주요 목표 완료 · 주요 Backlog 완료/정당한 정리 · 전체 구현 수렴 ·
      Design/UX 완료(토큰 정리 수준이 아니라 실제 페이지 UX) · Frontend/Backend/API/DB/RBAC
      전부 연결 · QA Coverage 주요 공백 해소 · Full Regression green · Build green ·
      통합 Deploy 완료 · Chrome Whole-product E2E · Console/Network 검증 · 발견 문제 수정
      및 재검증 · Final Whole Product Re-Audit에서 새로운 중대한 Root Cause 범주가 거의 없음 ·
      **그리고 var/product-audit/IMPLEMENTATION_REQUIRED 가 남아 있지 않을 것.**

Supervisor는 PROJECT_COMPLETE를 그대로 믿지 않는다. 내용 유무와 Product Audit Handoff 소진
여부를 기계적으로 검사하고, 통과하지 못하면 marker를 격리한 뒤 거부 사유를 다음 invocation
프롬프트에 그대로 전달하고 작업을 계속시킨다. 그러니 애초에 정확히 만들어라.

(a)라고 판단되면 WORK_STATE.md에 어떤 작업이 어떤 외부 요인으로 막혔는지 구체적으로 적어라.
그 외에는 항상 다음 작업으로 계속한다. 사용자에게 질문하지 않는다 — 답할 사람이 없다. 판단이
필요하면 스스로 가장 합리적인 공학적 결정을 내리고, 중요하면 docs/DECISIONS.md에 이유를 남긴다.

참고: PROJECT_COMPLETE 없이 끝내려 하면 Stop hook이 한 번 제동을 걸어 계속하라고 되돌린다.
그 제동은 보조 장치일 뿐이니 그것에 기대지 말고 애초에 스스로 계속하라.

지금 시작하라.
'@

    $iterationsThisLaunch = 0
    $dirtySignature = $null      # 직전에 본 워킹트리 상태(내용이 바뀌는지 보려고 들고 있다)
    $unchangedDirtyWaits = 0
    Write-RunnerLog "Supervisor 시작 PID=$PID projectDir=$ProjectDir (CLOVIR_SUPERVISED=1, Stop hook 보조 제동 활성)"

    while ($true) {
        if (Test-Path -LiteralPath $StopFile) {
            Write-RunnerLog "STOP 파일 발견(사용자 명시적 중단) — 루프 종료. 재개하려면 지우세요: $StopFile"
            $script:FinalExit = 3
            break
        }

        # 완료 판정: 존재 + 내용 + Product Audit Handoff 소진까지 기계적으로 확인한다.
        if (Test-Path -LiteralPath $CompleteFile) {
            $gate = Test-ProjectCompletionGate
            if ($gate.Passed) {
                Write-Banner @(
                    "PROJECT_COMPLETE 가 기계 Gate 를 통과했습니다 — 루프를 정상 종료합니다.",
                    (Read-TextOrEmpty $CompleteFile).Trim()
                )
                Write-RunnerLog "PROJECT_COMPLETE 유효 + Gate 통과 — 루프 정상 종료."
                $script:FinalExit = 0
                break
            }

            $reasons = ($gate.Failures -join [Environment]::NewLine)
            $q = Move-MarkerToQuarantine -MarkerPath $CompleteFile -QuarantineDir $QuarantineDir -Reasons $reasons
            [void](Write-TextFile $GateRejectionFile ("rejected_at=$(Get-Date -Format o)" + [Environment]::NewLine + $reasons))
            $st = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
            $st.completionRejections = (Get-IntOr $st.completionRejections) + 1
            [void](Save-StateFile $StateFile $st)
            Write-Banner @(
                "PROJECT_COMPLETE 가 기계 Gate 를 통과하지 못해 격리했습니다($($st.completionRejections)/$MaxCompletionRejections): $q",
                $reasons,
                "거부 사유를 다음 invocation 프롬프트에 전달하고 작업을 계속합니다."
            )
            Write-RunnerLog "PROJECT_COMPLETE Gate 거부($($st.completionRejections)/$MaxCompletionRejections): $($gate.Failures -join ' | ')"

            if ((Get-IntOr $st.completionRejections) -ge $MaxCompletionRejections) {
                $msg = "auto-stopped: PROJECT_COMPLETE rejected $($st.completionRejections) times at $(Get-Date -Format o)"
                [void](Write-TextFile $AutoStopFile $msg)
                Write-Banner @(
                    "Worker 가 완료 Gate 를 만족하지 못한 채 PROJECT_COMPLETE 를 $($st.completionRejections)회 반복 생성했습니다.",
                    "마지막 거부 사유: $GateRejectionFile",
                    "원인을 확인하고 고친 뒤 이 스크립트를 다시 실행하면 AUTO_STOP 은 자동으로 정리됩니다."
                )
                Write-RunnerLog "완료 Gate 반복 거부 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
                $script:FinalExit = 6
                break
            }
        }

        # invocation 횟수는 production 에서 종료 조건이 **아니다**($MaxIterationsPerLaunch=0).
        if ($MaxIterationsPerLaunch -gt 0 -and $iterationsThisLaunch -ge $MaxIterationsPerLaunch) {
            Write-Banner @(
                "Worker invocation $MaxIterationsPerLaunch 회 상한에 도달해 종료합니다(test override).",
                "이것은 PROJECT_COMPLETE 가 아닙니다 — 프로젝트는 끝나지 않았습니다.",
                "production 기본값은 무제한(0)입니다. 자동으로 이어받는 장치는 없으니 계속하려면 다시 실행하세요."
            )
            Write-RunnerLog "invocation 상한 $MaxIterationsPerLaunch 도달(test override) — 종료(PROJECT_COMPLETE 아님)."
            $script:FinalExit = 0
            break
        }

        $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        if ((Get-IntOr $state.consecutiveFailures) -ge $MaxConsecutiveFailures) {
            $msg = "auto-stopped after $($state.consecutiveFailures) consecutive failures at $(Get-Date -Format o)"
            # STOP(사용자 전용)이 아니라 AUTO_STOP 에 쓴다 — 다음 수동 재시작이 이 흔적 때문에
            # 조용히 무력화되지 않게 하기 위함이다.
            [void](Write-TextFile $AutoStopFile $msg)
            Write-Banner @(
                "연속 실패 $($state.consecutiveFailures)회 >= $MaxConsecutiveFailures — 원인 없이 계속 태우지 않기 위해 중단합니다.",
                "각 invocation 의 원본 출력은 $LogDir 에 있습니다. 원인을 확인하세요.",
                "고친 뒤에는 이 스크립트를 그냥 다시 실행하면 됩니다 — AUTO_STOP 은 자동으로 정리됩니다."
            )
            Write-RunnerLog "연속 실패 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            $script:FinalExit = 6
            break
        }

        # ── dirty 워킹트리 ──
        # 목적은 "사람이 지금 편집 중일 때 충돌하지 않는 것"이다. 사람이 편집 중이면 내용이
        # 계속 변한다 → 기다린다. 내용이 전혀 변하지 않으면 사람이 편집 중이 아니다 → 진행한다
        # (2026-08-12: CRLF/LF 정규화 때문에 영원히 modified 로 보이는 파일 하나로 Supervisor 가
        #  Claude 를 **한 번도** 못 띄운 채 조용히 멈춰 있었다).
        $statusResult = Invoke-Git -RepoDir $ProjectDir "status" "--porcelain"
        $dirty = $statusResult.StdOut.Trim()
        if ($dirty) {
            if ($dirty -eq $dirtySignature) { $unchangedDirtyWaits += 1 }
            else { $dirtySignature = $dirty; $unchangedDirtyWaits = 1 }

            if ($unchangedDirtyWaits -ge $MaxUnchangedDirtyWaits) {
                Write-RunnerLog "워킹트리가 dirty 하지만 $unchangedDirtyWaits 회 연속으로 내용이 전혀 변하지 않음 — 사람이 편집 중이 아니라고 보고 그대로 진행한다(무한 대기 방지). 현재 상태: $($dirty -replace '\s+', ' ')"
            } else {
                $wait = [int][Math]::Min($DirtyRetrySeconds, 30 * [Math]::Pow(2, $unchangedDirtyWaits - 1))
                Write-RunnerLog "저장소에 커밋 안 된 변경이 있음(대화형 세션이 작업 중일 수 있음) — ${wait}초 뒤 다시 확인 ($unchangedDirtyWaits/$MaxUnchangedDirtyWaits)."
                Start-Sleep -Seconds $wait
                continue
            }
        } else {
            $dirtySignature = $null
            $unchangedDirtyWaits = 0
        }

        # 같은 초에 두 invocation 이 시작되면 로그 파일 이름이 겹쳐 서로 덮어썼다 — 순번을 붙인다.
        $timestamp = "{0}-{1:d3}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), ($iterationsThisLaunch + 1)
        $logFile = Join-Path $LogDir "$timestamp.log"
        $errFile = "$logFile.err"
        $invocationPromptFile = Join-Path $LogDir "$timestamp.prompt.txt"
        $budgetLabel  = if ($MaxBudgetUsd -gt 0) { "`$$MaxBudgetUsd" } else { "무제한" }
        $timeoutLabel = if ($MaxRuntimeMinutes -gt 0) { "${MaxRuntimeMinutes}분" } else { "무제한" }
        Write-RunnerLog "Worker invocation 시작 #$($iterationsThisLaunch + 1) requestedModel=$Model requestedEffort=$Effort (log=$logFile, budget=$budgetLabel, timeout=$timeoutLabel)"

        # 프롬프트는 반드시 파일 → stdin 리다이렉트로 넘긴다(2026-08-11 장애: -ArgumentList 로
        # 넘긴 멀티라인 프롬프트가 커맨드라인 재조립에서 깨져 "unknown option '--oneline'").
        $promptBody = $prompt
        if ($PromptOverrideFile -and (Test-Path -LiteralPath $PromptOverrideFile)) {
            $promptBody = Read-TextOrEmpty $PromptOverrideFile
        }

        $lastRejection = Read-TextOrEmpty $GateRejectionFile
        $ctx = New-Object System.Collections.Generic.List[string]
        $ctx.Add("")
        $ctx.Add("======================================================================")
        $ctx.Add("RUN CONTEXT (Supervisor 가 매 invocation 에 주입한다)")
        $ctx.Add("======================================================================")
        $ctx.Add("runner=autonomous_runner.ps1")
        $ctx.Add("invocation=$($iterationsThisLaunch + 1)")
        $ctx.Add("started_at=$(Get-Date -Format o)")
        $implRequiredNow = Test-MarkerValid $ImplementationRequiredFile
        $ctx.Add("implementation_required=$(if ($implRequiredNow) { 'true' } else { 'false' })")
        if ($implRequiredNow) {
            $reqText = Read-TextOrEmpty $ImplementationRequiredFile
            $ctx.Add("audit_cycle_id=$(Get-KeyValueFromText $reqText 'cycle_id')")
            $ctx.Add("audit_root_causes=$(Get-KeyValueFromText $reqText 'root_causes')")
            $ctx.Add("handoff_path=$HandoffRel")
            $ctx.Add("handoff_present=$(Test-MarkerValid $HandoffFile)")
        }
        if (-not [string]::IsNullOrWhiteSpace($lastRejection)) {
            $ctx.Add("")
            $ctx.Add("--- 직전 PROJECT_COMPLETE 가 기계 Gate 에서 거부된 사유(반드시 먼저 해소하라) ---")
            $ctx.Add($lastRejection.Trim())
        }
        $ctx.Add("======================================================================")
        $promptBody = $promptBody + [Environment]::NewLine + ($ctx -join [Environment]::NewLine) + [Environment]::NewLine

        if (-not (Write-TextFile $invocationPromptFile $promptBody)) {
            Write-RunnerLog "프롬프트 파일을 쓰지 못했다($invocationPromptFile) — 이 invocation 을 실패로 세고 재시도한다."
            $state.consecutiveFailures = (Get-IntOr $state.consecutiveFailures) + 1
            [void](Save-StateFile $StateFile $state)
            $iterationsThisLaunch += 1
            continue
        }

        # Persistent Worker Session: 저장된 session_id 가 있으면 이어받고(--resume), 없으면
        # 새로 시작하며 **호출 전에** 저장한다(프로세스가 죽어도 다음 반복이 무엇을 시도했는지 안다).
        $sessionId = Read-SessionId $SessionIdFile
        $isNewSession = $false
        if ($null -eq $sessionId) {
            $sessionId = [guid]::NewGuid().ToString()
            $isNewSession = $true
            [void](Write-TextFile $SessionIdFile $sessionId)
            Write-RunnerLog "저장된 Worker Session 이 없음 — 새 session_id=$sessionId 로 시작."
        } else {
            Write-RunnerLog "기존 Worker Session 을 이어받음(--resume) session_id=$sessionId"
        }

        # 주의: 이 배열에 빈 문자열("") 원소를 넣지 마라. Windows 에서 -ArgumentList 가 배열을
        # 커맨드라인으로 재조립할 때 빈 원소를 누락시켜 뒤 인자가 한 칸씩 밀리고,
        # --session-id/--resume 가 엉뚱한 값에 붙는 것까지 2026-08-12 에 실제로 재현했다.
        $argList = @(
            "-p",
            "--permission-mode", "auto",
            "--output-format", "json"
        )
        # 0 이면 플래그 자체를 붙이지 않는다(CLI 가 0 을 "무제한"으로 해석한다는 근거가 없다).
        if ($MaxBudgetUsd -gt 0) { $argList += @("--max-budget-usd", "$MaxBudgetUsd") }
        if ($isNewSession) { $argList += @("--session-id", $sessionId) }
        else               { $argList += @("--resume", $sessionId) }
        if ($Model)  { $argList += @("--model", $Model) }
        if ($Effort) { $argList += @("--effort", $Effort) }

        $outcome = Invoke-ClaudeWorker -ClaudeExe $ClaudeExe -ArgList $argList -WorkingDirectory $ProjectDir `
            -PromptFile $invocationPromptFile -StdOutFile $logFile -StdErrFile $errFile `
            -TimeoutMinutes $MaxRuntimeMinutes -LogPath $RunnerLog
        $exitCode = $outcome.ExitCode

        # rate-limit/overload 와 session resume 실패만 따로 잡는다 — 그 외 일반 실패는 즉시
        # 재시도하고 연속 상한이 최종 안전망이다(일반 작업엔 idle timer 를 쓰지 않는다).
        $isRateLimit = $false
        $isResumeFailure = $false
        if ($exitCode -ne 0) {
            $errText = (Read-TextOrEmpty $errFile)
            $outText = (Read-TextOrEmpty $logFile)
            if ((-not $isNewSession) -and (Test-IsResumeFailure ($errText + "`n" + $outText))) {
                $isResumeFailure = $true
            } elseif (Test-IsRateLimitFailure ($errText + "`n" + $outText)) {
                $isRateLimit = $true
            }
        }

        if ($isResumeFailure) {
            Write-RunnerLog "저장된 session_id=$sessionId 를 더 이상 resume 할 수 없음(세션 인프라 문제 — 작업 실패 아님) — 지우고 다음 반복에서 새 Worker Session 으로 즉시 재시작."
            Remove-Item -LiteralPath $SessionIdFile -Force -ErrorAction SilentlyContinue
        }

        $iterationsThisLaunch += 1
        $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        if ($exitCode -eq 0) {
            $state.consecutiveFailures = 0
            $state.consecutiveRateLimitHits = 0
            $state.sessionRotatedForStreak = $false
        } elseif ($isResumeFailure) {
            # consecutiveFailures 도 rate-limit 카운터도 안 올린다 — session resume 인프라 문제는
            # "이 작업이 틀렸다"는 신호가 아니고, 새 세션으로 즉시 재시도하면 되기 때문이다.
        } elseif ($isRateLimit) {
            $hits = (Get-IntOr $state.consecutiveRateLimitHits) + 1
            $state.consecutiveRateLimitHits = $hits
            if ($hits -gt $MaxConsecutiveRateLimitHits) {
                # 무한 백오프 방지: rate-limit 처럼 보이는 실패가 계속되면 결국 실패로 센다.
                $state.consecutiveFailures = (Get-IntOr $state.consecutiveFailures) + 1
                Write-RunnerLog "연속 rate-limit 판정이 $hits 회로 상한($MaxConsecutiveRateLimitHits)을 넘어 일반 실패로 계산한다(무한 백오프 방지)."
            }
        } else {
            $state.consecutiveFailures = (Get-IntOr $state.consecutiveFailures) + 1
            # 같은 세션이 결정적으로 계속 실패하면(오염된 세션) 상한 도달 전에 한 번만 회전시킨다.
            # 실패 카운터는 그대로 둔다 — 원인이 다른 데 있으면 예정대로 AUTO_STOP 에 도달해야 한다.
            if ((Get-IntOr $state.consecutiveFailures) -ge ($MaxConsecutiveFailures - 1) -and
                (-not $state.sessionRotatedForStreak) -and (-not $isNewSession)) {
                Remove-Item -LiteralPath $SessionIdFile -Force -ErrorAction SilentlyContinue
                $state.sessionRotatedForStreak = $true
                Write-RunnerLog "같은 Worker Session 에서 연속 실패가 이어져 session_id 를 한 번 회전한다(오염된 세션 복구 시도)."
            }
        }
        $state.lastRunAt = (Get-Date -Format o)
        $state.lastExitCode = $exitCode
        $state.totalRuns = (Get-IntOr $state.totalRuns) + 1
        $state.totalIterationsThisLaunch = $iterationsThisLaunch
        [void](Save-StateFile $StateFile $state)

        # §11 이 요구하는 증거를 한 줄에 모은다. secret 은 남기지 않는다(session_id 는 불투명 UUID).
        $headSha = Get-GitHeadSha -RepoDir $ProjectDir -Short
        $actualModel = Get-ActualModel $logFile
        $completeMarkerPresent = Test-Path -LiteralPath $CompleteFile
        Write-RunnerLog ("Worker invocation 종료 #$iterationsThisLaunch exit=$exitCode exitSource=$($outcome.Source) " +
            "handleCached=$($outcome.HandleCached) session=$sessionId requestedModel=$Model requestedEffort=$Effort " +
            "actualModel=$actualModel rateLimit=$isRateLimit resumeFailure=$isResumeFailure " +
            "consecutiveFailures=$($state.consecutiveFailures) totalRuns=$($state.totalRuns) headSha=$headSha " +
            "PROJECT_COMPLETE_marker=$completeMarkerPresent")
        if (-not $completeMarkerPresent) {
            Write-RunnerLog "PROJECT_COMPLETE 없음 — 대기 없이 곧바로 다음 Worker invocation 을 시작한다(exit=$exitCode 는 종료 조건이 아니다)."
        }

        if ($isRateLimit) {
            $backoff = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveRateLimitHits) `
                -BaseSeconds $RateLimitBaseBackoffSeconds -MaxSeconds $RateLimitMaxBackoffSeconds
            Write-RunnerLog "rate-limit/overload 로 보임 — ${backoff}초 대기 후 재시도(진짜 기다릴 이유가 있는 경우만 백오프)."
            Start-Sleep -Seconds $backoff
        }
        # 성공했거나(exit=0) 일반 실패/resume 실패면 sleep 없이 곧장 다음 반복으로 — 이것이 핵심이다.
    }
    exit $script:FinalExit
} finally {
    Restore-EnvSnapshot $script:EnvSnapshot
    Close-ExclusiveLock -Lock $lock -LockFile $LockFile
    Write-RunnerLog "Supervisor 종료 PID=$PID (invocations=$iterationsThisLaunch) exit=$script:FinalExit"
}
