<#
.SYNOPSIS
  ClovirAssist 자율 완성 루프 — PHASE 2 구현 Supervisor(Primary Continuous Worker).

.DESCRIPTION
  사용자가 PowerShell 에서 한 번 시작한 **이 프로세스 자체**가 Primary Continuous Supervisor 다.
  Windows Task Scheduler 의존은 폐기됐다(CLAUDE.md §0) — 이 루프를 되살려 주는 scheduled task도,
  heartbeat도, fallback continuity도 없다. 한 invocation 이 끝나면 성공이든 실패든
  `PROJECT_COMPLETE` 가 기계 Gate 를 통과할 때까지 sleep 없이 곧장 다음 invocation 으로 간다.

  각 invocation 은 새 비대화형(-p) 프로세스를 띄우지만 `--resume` 으로 **같은 Worker Session**
  을 이어받는다(OS 프로세스 재시작과 대화 연속성은 별개다). 세션 id 는 var\runner\session_id.txt.

  ══════════════════════════════════════════════════════════════════════════════
  === 2026-08-13 처리량 개선: 실제 운영 로그에서 측정한 병목 4개를 제거했다 ===
  ══════════════════════════════════════════════════════════════════════════════
  측정 근거는 var\runner\runner.log 2026-08-12 19:32 ~ 2026-08-13 10:43 구간이다.

  B1. **고정 240분 벽시계 timeout 이 일하고 있는 Worker 를 잘랐다.**
      invocation #2/#3/#4 가 **전부** `exit=124 exitSource=timeout` 이었고 셋 다 그 사이
      커밋을 남기고 있었다. timeout 이 hang 을 잡은 게 아니라 정확히 4시간마다 작업을 끊은
      것이다. → **활동 기반 idle timeout** 으로 교체했다(출력이 자라는 동안은 자르지 않는다).
      `--output-format stream-json --verbose` 로 바꿔 stdout 이 실시간으로 자라게 만들었고,
      그 파일 길이가 활동 신호다(2026-08-13 실측으로 동시 읽기 가능 확인).

  B2. **그 강제 종료가 만든 dirty 워킹트리를 다음 회차가 5분 30초씩 기다렸다.**
      로그에 30+60+120+120초 대기가 두 구간 그대로 남아 있다. 기다린 대상은 **우리가 방금
      죽인 우리 Worker 가 남긴 파일**이었다. → dirty 판정을 **파일 mtime + 우리가 만든
      변경인지** 기준으로 바꿨다. 사람이 실제로 편집 중이면(=mtime 이 계속 갱신) 여전히
      기다리고, 아니면 첫 확인에서 곧장 진행한다.

  B3. **매 invocation 이 대형 문서 전체를 다시 읽었다.**
      프롬프트가 CLAUDE.md + WORK_STATE(5,190줄) + BACKLOG(3,287줄) + QA_COVERAGE +
      DECISIONS(1,338줄) + PROGRESS_STATUS + WORK_PLAN_INDEX 를 **매번** 읽으라고 지시했다.
      invocation #4 는 06:22 에 시작해 **07:15 에야 첫 커밋**을 남겼다(53분).
      → COLD(새 세션·session 회전·gate 거부 후·주기적 재접지)와 WARM(정상 --resume)을
      구분한다. WARM 은 대형 문서를 다시 읽지 않고 Supervisor 가 만든 compact RUN CONTEXT
      (직전 HEAD 이후 커밋·dirty·미해결 index 요약)만 보고 즉시 이어서 일한다.

  B4. **`--permission-mode auto` 가 무인 실행에서 도구를 실제로 거부했다.**
      2026-08-13 controlled probe: 같은 프롬프트로 `auto` 는 Write/Bash 를 각각 거부해
      (`permission_denials` 2건) 파일이 하나도 안 만들어졌고, `bypassPermissions` 는 거부 0건
      으로 둘 다 성공했다. 무인 Supervisor 에는 승인해 줄 사람이 없으므로 거부는 그대로
      작업 실패다. → `--permission-mode bypassPermissions` 로 바꿨다.

  그 밖의 구조 변경:
    - 실패를 **유형별로** 분류한다(rate-limit / overload / network / resume / auth / hang /
      spawn / 진척있음 / generic). 인프라성 실패는 AUTO_STOP 카운터를 소모하지 않고, 대신
      **같은 실패 지문이 반복되면** 그때 수렴한다. "일반 실패 3회"로 밤샘 실행이 죽지 않는다.
    - rate limit 은 stream 의 `rate_limit_event.resetsAt`(unix epoch, 실측 확인)까지 기다린다.
      지수 백오프로는 몇 시간짜리 구독 한도를 절대 못 맞춘다.
    - model/effort 는 **사용자 지시(2026-08-13)로 sonnet + max 고정**이다. 매 invocation 에
      명시적으로 넘긴다(안 넘기면 사용자 settings 나 세션에 저장된 과거 값에 좌우된다).
      동적 정책 코드는 남아 있지만 `-DynamicEffort $true` 없이는 동작하지 않는다.
    - 진행 상황 heartbeat 를 콘솔에 주기 출력한다("느림"과 "hang" 구분).
    - invocation 마다 구간별 소요 시간을 var\runner\timings.jsonl 에 남긴다.

  === 2026-08-12 심층 검수에서 고친 결함(전부 유지) ===
  A. Windows PowerShell 5.1 `ExitCode=$null` → `Start-Process -PassThru` 직후 `.Handle` 캐시.
  B. PS 5.1 에서 git 호출이 Supervisor 를 죽이던 문제 → 모든 git 은 `Invoke-Git` 경유.
  C. PROJECT_COMPLETE 기계 Gate 가 문서에만 있고 코드에 없던 문제 → Supervisor 가 검증/격리.
  D. state.json 스키마 변경 시 속성 대입에서 죽던 문제 → 정규화.
  E. rate-limit 오탐이 실패 카운터를 우회해 무한 백오프로 돌던 문제 → 판정 축소 + 상한.
  F. timeout 시 루트만 죽여 자식이 살아남던 문제 → 트리 강제 종료.
  G. dirty 대기 고정 2분 x 5회 → (B2 에서 다시 정확한 판정으로 교체)

  안전장치(전부 유지):
    - var\runner\STOP        — 사용자만 만든다. 있으면 Worker 를 한 번도 안 띄우고 exit 3.
    - var\runner\AUTO_STOP   — 스크립트의 자동 정지 흔적. 수동 재시작을 확인으로 보고 정리한다.
    - var\runner\PROJECT_COMPLETE — 내용이 있어야 하고 기계 Gate 를 통과해야 유효하다.
    - var\runner\run.lock    — 배타 파일 핸들. product_audit_runner.ps1 과 **공유**한다.
    - Process 강제 종료      — 진짜 멈춘 invocation 만 죽인다(루프는 안 죽는다).
    - Stop hook(stop_guard.py) — 보조 제동. Supervisor 를 대체하지 않는다.
#>

param(
    [string]$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant",
    [string]$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe",

    # controlled test seam — 평소엔 비운다. 이름 주의: PowerShell 변수는 대소문자를 구분하지
    # 않는다. 루프 안의 per-invocation 변수와 같은 이름을 쓰면 파라미터가 조용히 덮어써진다
    # (2026-08-12 실제로 당했다 — 테스트 프롬프트 대신 내장 프롬프트가 나갔다).
    [string]$PromptOverrideFile = "",

    # Worker 품질 계약(D-65/D-66): 매 invocation 에 **명시적으로** 넘긴다. 새 세션이든 --resume
    # 이든 항상 넘긴다. 안 넘기면 사용자 settings 의 effortLevel 이나 세션에 저장된 과거 model 에
    # 좌우된다(실측 확인). 설치 CLI 가 허용하는 effort: low|medium|high|xhigh|max.
    #
    # ★ 2026-08-13 사용자 지시로 **고정**한다: 구현 Runner 는 Sonnet + max.
    #   (동적 effort 정책을 설계했었지만 사용자가 고정을 선택했다. 아래 Dynamic* 파라미터는
    #    기본 꺼짐이고, 켜지 않는 한 매 invocation 에 이 값이 그대로 나간다.)
    #   effort 는 새 세션이든 --resume 이든 **항상 명시적으로** 넘긴다 — 안 넘기면 사용자
    #   settings 의 effortLevel 이나 세션에 저장된 과거 model 에 좌우된다(실측 확인).
    [string]$Model  = "sonnet",
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$Effort = "max",
    # 아래 셋은 기본 꺼짐. 나중에 동적 정책을 다시 켜고 싶을 때만 쓴다(-DynamicEffort $true).
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$HighRiskEffort = "max",
    [string]$HighRiskModel = "",
    [bool]$DynamicEffort = $false,
    # 과부하 시 CLI 가 알아서 다른 모델로 넘어가게 하려면 지정한다(기본 꺼짐 — 조용한 모델
    # 교체는 requestedModel/actualModel 로그를 모호하게 만들고 품질을 바꿀 수 있다).
    [string]$FallbackModel = "",

    # 0 = 무제한(production 기본). invocation 횟수는 Supervisor 종료 조건이 **아니다**.
    [int]$MaxIterationsPerLaunch = 0,

    # ── 실패 상한 ──
    # 예전 값 3 은 "네트워크가 잠깐 끊긴 밤"에 밤샘 실행을 끝내기에 충분한 숫자였다. 숫자만
    # 키우면 진짜 결정적 실패를 오래 태우게 되므로, **유형 분류 + 같은 지문 반복 감지**와
    # 함께 올린다(무한 재시도 방지는 MaxIdenticalFailures 가 담당한다).
    [int]$MaxConsecutiveFailures = 10,
    [int]$MaxIdenticalFailures = 4,          # 같은 실패 지문이 연속 N회 = 결정적 실패로 수렴
    [int]$MaxInfraRetries = 60,              # rate-limit/network/overload/resume 연속 상한
    [int]$MaxCompletionRejections = 5,       # premature PROJECT_COMPLETE 반복 생성 방지

    # ★ 0 = 무제한(기본). 이 값은 "지출 가드"가 아니었다 — invocation 횟수가 무제한이라 총액을
    #   막지 못하면서 실질적으로는 **일을 문장 중간에서 자르는** 장치로만 동작했다.
    [int]$MaxBudgetUsd = 0,

    # ── 실행 시간 ──
    # MaxRuntimeMinutes 는 이제 **0(무제한)이 기본**이다. 일하고 있는 Worker 를 벽시계로 자르는
    # 것이 B1 병목이었다. hang 보호는 IdleTimeoutMinutes 가 담당한다 — 출력이 이 시간 동안
    # 단 한 바이트도 안 늘면 그건 느린 게 아니라 멈춘 것이다.
    [double]$MaxRuntimeMinutes = 0,
    [double]$IdleTimeoutMinutes = 25,
    [double]$ProgressIntervalSeconds = 60,
    [int]$ProgressLogEverySeconds = 900,     # 콘솔은 자주, runner.log 는 가끔(로그 오염 방지)

    # ── dirty 워킹트리 ──
    [int]$DirtyQuietSeconds = 90,            # 최근 수정이 이만큼 오래됐으면 아무도 편집 중이 아니다
    [int]$DirtyPollSeconds = 15,
    [int]$MaxDirtyWaits = 40,                # 최대 10분까지 사람 편집을 기다린 뒤 진행

    # ── 백오프 ──
    [int]$RateLimitBaseBackoffSeconds = 60,
    [int]$RateLimitMaxBackoffSeconds = 1800,
    [int]$RateLimitMaxWaitSeconds = 21600,   # reset 시각을 알면 최대 6시간까지 기다린다
    [int]$NetworkBaseBackoffSeconds = 15,
    [int]$NetworkMaxBackoffSeconds = 300,
    [int]$FailureBaseBackoffSeconds = 30,
    [int]$FailureMaxBackoffSeconds = 600,

    # ── 재오리엔테이션 정책 ──
    [int]$ColdRefreshEvery = 12,             # 이 횟수마다 한 번은 전체 상태 재접지(WARM 표류 방지)

    # ── TEST SERVER 자율 실행 ──
    # 대상 host 는 하드코딩하지 않는다(CLAUDE.md §9). 비우면 저장소 설정에서 찾는다.
    [string]$TestServerTarget = "",
    [switch]$SkipTestServerProbe,
    # sudo 비밀번호는 **runtime 에만** 존재한다. 저장소·문서·argv·로그에 절대 남기지 않는다
    # (CLAUDE.md §3.4). 이 환경변수로 넘기거나 -PromptForSudoPassword 로 시작 시 한 번 입력한다.
    [string]$SudoPasswordEnvName = "CLOVIR_TEST_SUDO_PASSWORD",
    [switch]$PromptForSudoPassword
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
$TimingLog  = Join-Path $RunnerDir "timings.jsonl"
$GateRejectionFile = Join-Path $RunnerDir "last_completion_rejection.txt"
$SessionIdFile = Join-Path $RunnerDir "session_id.txt"  # secret 아님(불투명 UUID), var/ 는 gitignore
$NextHintFile  = Join-Path $RunnerDir "next_invocation.json"
$ResumeContextFile = Join-Path $RunnerDir "resume_context.txt"
# TEST SERVER sudo 비밀번호의 로컬 runtime 경로. var/ 는 .gitignore 대상이라 git 에 절대 들어가지
# 않는다 — 환경변수를 매번 넣지 않아도 무인 실행이 되게 하면서 §3.4(추적 파일 금지)를 지킨다.
$SudoPasswordFile = Join-Path $RunnerDir "test_server_sudo"

# Product Audit(PHASE 1)이 넘긴 계약
$AuditDir = Join-Path $ProjectDir "var\product-audit"
$ImplementationRequiredFile = Join-Path $AuditDir "IMPLEMENTATION_REQUIRED"
$ImplementationConsumedFile = Join-Path $AuditDir "IMPLEMENTATION_CONSUMED"
$AuditCompleteFile = Join-Path $AuditDir "AUDIT_COMPLETE"
$HandoffRel = "docs/product-audit/PRODUCT_AUDIT_HANDOFF.md"
$HandoffFile = Join-Path $ProjectDir "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"

$StateDefaults = [ordered]@{
    consecutiveFailures       = 0
    consecutiveInfraRetries   = 0
    consecutiveRateLimitHits  = 0
    identicalFailureCount     = 0
    lastFailureSignature      = ""
    completionRejections      = 0
    sessionRotatedForStreak   = $false
    invocationsSinceCold      = 999          # 첫 회차는 항상 COLD
    lastRunAt                 = $null
    lastExitCode              = $null
    lastFailureClass          = ""
    lastHeadSha               = ""
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
            "흔적을 지우고 실패 카운터를 0으로 되돌린 뒤 계속 진행합니다.",
            "정말로 멈춰 두려면 대신 $StopFile 을 만드세요."
        )
        Write-RunnerLog "AUTO_STOP 흔적 발견 — 수동 재시작을 확인으로 보고 정리한 뒤 진행. 내용: $autoBody"
        Remove-Item -LiteralPath $AutoStopFile -Force -ErrorAction SilentlyContinue
        $s = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        $s.consecutiveFailures = 0
        $s.consecutiveInfraRetries = 0
        $s.consecutiveRateLimitHits = 0
        $s.identicalFailureCount = 0
        $s.lastFailureSignature = ""
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
    $script:EnvSnapshot = Save-EnvSnapshot @("CLOVIR_SUPERVISED", "CLOVIR_PRODUCT_AUDIT",
                                             "CLOVIR_SUPERVISOR_PID", $SudoPasswordEnvName)
    Remove-Item Env:CLOVIR_PRODUCT_AUDIT -ErrorAction SilentlyContinue
    $env:CLOVIR_SUPERVISED = "1"
    $env:CLOVIR_SUPERVISOR_PID = "$PID"

    # ── TEST SERVER 자율 실행 준비 ────────────────────────────────────────────
    # CLAUDE.md §9 는 승인된 TEST SERVER(10.100.64.X)에서 Claude/Runner 가 직접 deploy/modify/
    # test 하는 것을 허용한다. 예전 프롬프트의 "배포 자격증명" 절은 그것을 정면으로 막고 있었다
    # (배포를 수행하지 말고 blocker 로만 남기라는 지시) — 그 절을 통째로 제거하고, 대신
    # **사실**(접속 가능 여부·sudo 가능 여부)을 미리 확인해 Worker 에게 준다.
    if ([string]::IsNullOrWhiteSpace($TestServerTarget)) {
        $TestServerTarget = Get-TestServerTargetFromRepo -ProjectDir $ProjectDir
    }
    $script:ServerAccess = [pscustomobject]@{ Probed = $false; SshOk = $false; SudoNoPassword = $false; Detail = "" }
    if (-not $SkipTestServerProbe -and -not [string]::IsNullOrWhiteSpace($TestServerTarget)) {
        $script:ServerAccess = Test-TestServerAccess -Target $TestServerTarget
        Write-RunnerLog "TEST SERVER 접근 확인 target=$TestServerTarget ssh=$($script:ServerAccess.SshOk) sudoNoPassword=$($script:ServerAccess.SudoNoPassword)"
    }

    # sudo 비밀번호: **runtime 에만** 존재한다. 저장하지 않고, argv 에 넣지 않고, 로그에 남기지
    # 않는다(CLAUDE.md §3.4). 자식 프로세스는 환경변수로 상속받고, Worker 는 그것을 stdin 으로만
    # 쓴다. 값 자체는 이 스크립트 어디에서도 출력되지 않는다.
    if ($PromptForSudoPassword) {
        $sec = Read-Host -Prompt "TEST SERVER($TestServerTarget) sudo 비밀번호 (입력값은 저장·로그되지 않습니다)" -AsSecureString
        try {
            $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
            $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            if (-not [string]::IsNullOrEmpty($plain)) { Set-Item -LiteralPath ("Env:" + $SudoPasswordEnvName) -Value $plain }
            $plain = $null
        } catch { Write-RunnerLog "sudo 비밀번호 입력을 처리하지 못했다(형식 문제) — 없는 것으로 계속 진행한다." }
    }
    $cred = Resolve-SudoCredential -EnvName $SudoPasswordEnvName -FilePath $SudoPasswordFile
    $script:SudoCredentialAvailable = $cred.Available
    Write-RunnerLog "TEST SERVER sudo credential 확보=$($cred.Available) 출처=$($cred.Source) (값은 로그·저장소 어디에도 남기지 않는다)"

    if ($script:ServerAccess.Probed -and -not $script:ServerAccess.SshOk) {
        Write-Banner @(
            "승인된 TEST SERVER($TestServerTarget)에 비대화형 SSH 로 닿지 않습니다.",
            "  probe: $($script:ServerAccess.Detail)",
            "배포·실환경 E2E 가 필요한 작업은 이번 실행에서 막힐 수 있습니다. 그 외 작업은 계속 진행합니다."
        )
    } elseif ($script:ServerAccess.SshOk -and -not $script:ServerAccess.SudoNoPassword -and -not $script:SudoCredentialAvailable) {
        Write-Banner @(
            "TEST SERVER($TestServerTarget) SSH 는 되지만 sudo 에 비밀번호가 필요하고, runtime 자격증명이 없습니다.",
            "  sudo 가 필요한 작업(패키지 설치·systemd·nginx·배포 적용)은 이번 실행에서 수행할 수 없습니다.",
            "  넘기는 방법 — 아래 중 하나(값은 git 에 절대 들어가지 않습니다):",
            "    (권장, 한 번만) 비밀번호를 이 파일에 한 줄로 저장:  $SudoPasswordFile",
            "    (이번 실행만)   `$env:$SudoPasswordEnvName = '<비밀번호>'   또는  -PromptForSudoPassword",
            "sudo 가 필요 없는 모든 작업은 그대로 계속 진행합니다."
        )
    }

    # ══════════════════════════════════════════════════════════════════════════
    # 프롬프트 — COLD(전체 재접지) / WARM(즉시 이어서) 두 모드로 나뉜다
    # ══════════════════════════════════════════════════════════════════════════

    $promptCold = @'
## 1단계 — 상태 복원 (이번 회차는 COLD: 실제로 전부 다시 확인한다)

이번 호출은 새 Worker Session 이거나, 세션이 회전됐거나, 완료 Gate 거부 직후이거나,
주기적 재접지 회차다. 그래서 **이번에는** 다음을 실제로 읽고 교차 대조한다.

CLAUDE.md · docs/WORK_STATE.md · docs/BACKLOG.md · docs/QA_COVERAGE.md · docs/DECISIONS.md ·
docs/PROGRESS_STATUS.md · docs/WORK_PLAN_INDEX.md · `git status` · `git log --oneline -20`.

대화 기억이 아니라 이 파일들과 git 이 진실이다. WORK_STATE.md 의 "다음 후보" 몇 줄만 보지 말고
BACKLOG.md · QA_COVERAGE.md 전체와 대조해 실제로 남은 작업 전체를 기준으로 판단한다.
아래 RUN CONTEXT 의 `unresolved_top` 은 Supervisor 가 BACKLOG.md 에서 기계적으로 뽑은
**보조 index** 일 뿐이다 — COLD 회차에서는 원본으로 검증하라.

이 재접지는 **이번 호출에서 한 번만** 한다. 같은 호출 안에서 이미 읽은 문서를 다시 읽지 마라.
'@

    $promptWarm = @'
## 1단계 — 상태 복원 (이번 회차는 WARM: 대형 문서를 다시 읽지 마라)

이번 호출은 **직전 호출과 같은 Worker Session** 을 정상적으로 이어받았다. 너는 직전까지 무엇을
하고 있었는지 이미 알고 있다. 그러니 **재오리엔테이션을 다시 하지 마라.**

- docs/WORK_STATE.md · docs/BACKLOG.md · docs/QA_COVERAGE.md · docs/PROGRESS_STATUS.md ·
  docs/WORK_PLAN_INDEX.md · docs/DECISIONS.md 를 **전체 통독하지 마라.** 이것이 이 프로젝트에서
  측정된 가장 큰 시간 낭비였다(직전 구조에서는 invocation 시작부터 첫 커밋까지 53분이 걸렸다).
- 아래 RUN CONTEXT 에 직전 HEAD 이후의 커밋, 현재 dirty, 미해결 index 요약, 직전 종료 사유가
  이미 들어 있다. 그것으로 위치를 확인하고 **곧바로 작업을 이어서 하라.**
- 특정 파일의 특정 절이 지금 하는 작업에 실제로 필요할 때만 그 구간을 열어라(예: 방금 고른
  Root Cause 의 BACKLOG 행, 관련 DECISIONS 항목 하나).
- 예외 — 아래 중 하나에 해당하면 그때는 필요한 문서를 전체 수준으로 다시 조사하라:
    · 지금 후보가 고갈돼 새 Root Cause 군을 골라야 한다
    · RUN CONTEXT 와 실제 저장소 상태가 모순된다
    · whole-product 재감사 단계에 들어간다
    · 완료(PROJECT_COMPLETE) 직전 최종 교차 확인
'@

    $promptCore = @'
당신은 ClovirAssist 프로젝트를 **끝까지 완성**하는 작업을 이어받는다. 이것은 사람이
실시간으로 지켜보지 않는, 비대화형·무인 실행이다.

**작업 단위는 PROJECT 전체 하나뿐이다.** 지금 이 프로세스 호출(invocation)은 work unit이 아니다 —
"이번 회차", "이번 batch", "이번 turn 범위", "iteration 완료" 같은 단위는 존재하지 않는다. 한
Root Cause를 닫았으면 곧바로 같은 호출 안에서 다음 Root Cause로 넘어간다. 호출 자체가
context 한계로 끝나는 것은 허용되지만, 그때도 PROJECT가 끝난 것이 아니며 로컬 PowerShell
Supervisor가 지연 없이 같은 Worker Session을 즉시 resume한다.

## 0단계 — 설계 결정은 네가 내린다. 승인 대기라는 단계는 없다
이 파이프라인에는 사람에게 판단을 넘기는 Gate가 **없다.** 아래는 전부 금지다.

- 사람 승인 필요 / 사용자 승인 필요 / 승인 후 구현
- 사람 판단 필요 / 사용자 판단 필요 / 정책 결정 필요 / 설계 결정 대기
- 사용자에게 질문 · 선택지 제시 후 대기 · "어느 안으로 할까요" · "진행해도 될까요"
- ADR 승인 필요 (ADR/DECISIONS는 **선행조건이 아니다**)
- 제안으로만 기록하고 구현하지 않음
- "업무 흐름이 바뀌므로" / "UI/UX 변경이 크므로" / "아키텍처 변경이므로" 사람이 정해야 함

근거가 충분하면 **네가 결정하고 바로 구현한다.** 여러 선택지가 있어도 묻지 않는다. 기준:

사용자 업무 성공 · 기존 제품 의도 · 기능 정확성 · 데이터 정합성 · RBAC/보안 경계 유지 ·
단순성 · 일관성 · 유지보수성 · 접근성 · 테스트 가능성 · 회귀 위험 · UI/UX 품질 ·
현재 코드와 아키텍처의 방향성

**근거가 부족하면 질문하지 말고 조사를 더 해라.** 코드·테스트·스키마·API·RBAC·문서·실제 브라우저
동작·DB 상태·로그를 더 본다. 조사가 결정을 만든다.

**문서는 Gate가 아니다.** `조사 → 결정 → 구현 → 검증 → 근거를 docs/DECISIONS.md에 사후 기록`
순서로 진행한다. 문서를 먼저 쓰거나 승인을 기다리느라 구현을 멈추지 마라.

변경 규모가 크다는 것은 승인 사유가 아니라 **회귀 테스트를 더 촘촘히 쓸 이유**다.

예외는 하나뿐이다: **네게 실제 권한이 없는 외부 행위**(자격증명 회전, 외부 운영시스템 변경,
조직 업무 정책 자체의 변경). 그것은 하지 않은 사실과 영향만 정직하게 적고, 그것과 독립적으로
가능한 모든 작업은 계속한다. **하지 않은 외부 행위를 한 것처럼 꾸미지 마라.**

사용자에게 질문하지 않는다 — 답할 사람이 없다.

__STATE_RESTORE_SECTION__

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
locality 순). 하나를 닫으면 멈추지 말고 context/tool 상황이 허용하는 동안 곧바로 다음
영향도 높은 Root Cause로 넘어간다 — "다음 호출에서 하겠다"는 선택지는 없다.

Backlog ID는 **inventory/evidence이지 실행 단위가 아니다.** ID를 한 건씩 기계적으로 처리하지
말고, 같은 Root Cause를 공유하는 항목들을 묶어서 저장소 전체에서 함께 조사하고 함께 고친다
(UI → shared component + 전체 소비처, RBAC → 같은 permission/scope 경로 전체, DB → 같은
transaction/retry 패턴 전체). "N건 처리"는 진척 단위가 아니다.

## 3단계 — 구현: 크게 묶어서, 빠르게

### 절대 어기면 안 되는 것 (CLAUDE.md §3 불변 규칙 — 요약본을 매 호출에 함께 보낸다)
WARM 회차는 CLAUDE.md를 다시 읽지 않고, 긴 세션은 context가 압축되기도 한다. 그래서 **참조가
아니라 내용**을 여기 둔다. 애매하면 CLAUDE.md 원문 §3이 정본이다.

1. **Sync 일관성** — FastAPI `async def` 핸들러나 `aiosqlite`를 새로 추가하지 않는다.
2. **Outbound HTTP 단일 관문** — 외부 호출은 `app/core/http_client.py`의 `OutboundClient`를
   경유한다. 임의 `httpx` 직접 사용 금지.
3. **Secret 비노출** — secret을 DB·응답·로그·감사에 평문으로 저장하거나 노출하지 않는다.
4. **Credential 비영구화** — 비밀번호/토큰을 Git·추적 문서·source·config·명령행·불필요한 로그에
   남기지 않는다. stdin/승인된 runtime 경로만 쓴다. `sshpass` 금지.
5. **Session/RBAC** — opaque session + CSRF 규약 유지. 권한 판단은 **서버가 정본**이고 프런트
   권한 표시는 보조일 뿐이다. 버튼을 숨기는 것은 authorization이 아니다.
6. **XSS/CSP** — 서버 데이터를 `innerHTML`로 주입하지 않는다. inline script / `onclick=` 금지.
7. **UTC 저장** — Asia/Seoul은 표시와 cron 평가에만 쓴다.
8. **제품 기능 경계** — Runner 코드 웹 편집, 임의 shell 실행, secret 평문 표시, 범용 systemd
   제어를 제품 기능으로 추가하지 않는다.
9. **공유 서비스 보호** — ClovirAssist과 **무관한** n8n/서비스/공유 nginx 설정을 이 작업 때문에
   임의로 바꾸지 않는다(ClovirAssist 관련 것은 4단계 권한 범위 안이다).
10. **DB transaction 의미 보존** — `app/core/db.py`의 명시적 transaction/BEGIN 규약을 우회하거나
    pysqlite implicit transaction 동작에 다시 의존하지 않는다. SAVEPOINT/`begin_nested()`는 실제
    outer transaction 안에서 동작해야 한다. SQLite busy/locked 판정은 기존 공용 classifier/retry를
    재사용하고, `:memory:` DB로 WAL/멀티커넥션 의미를 대체하지 않는다.

남은 작업을 Root Cause 단위로 크게 묶어 구현한다.
dev server/브라우저가 이미 떠 있고 다음 작업에도 쓸 만하면 그대로 재사용한다 — 매번 기계적으로
껐다 켜지 않는다.
**Full Regression green은 정지 신호가 아니다** — green을 확인했으면 곧바로 다음 구현으로 돌아간다.

### 작업 단위 크기 (사용자 지시 — 잘게 쪼개지 마라)
`조사 → 구현 → 테스트 → 문서 → 커밋` 사이클을 **항목마다 반복하지 마라.** 그게 이 프로젝트에서
가장 큰 시간 낭비다. 한 사이클은 다음 크기로 잡는다.

- **한 사이클 = Root Cause 여러 개의 묶음.** 같은 층·같은 패턴·같은 파일군을 건드리는 것들을
  전부 모아 한 번에 고친다. 예: "shared component 하나 + 그걸 쓰는 화면 12곳"은 12개 작업이
  아니라 **1개 작업**이다. "같은 permission 경로를 쓰는 엔드포인트 8개"도 1개다.
- **먼저 전체 소비처를 다 찾고 나서 한 번에 고쳐라.** 한 곳 고치고 테스트하고, 또 한 곳 고치고
  테스트하는 식으로 돌지 마라.
- **커밋은 복구 가치가 있는 묶음 단위.** 항목마다 커밋하지 마라. 다만 몇 시간 동안 아무
  체크포인트도 남기지 않는 것도 금지다 — 크래시 복구가 불가능해진다. 큰 묶음이 끝났을 때,
  위험한 기반 변경 직후, 또는 장시간 작업 중간에 한 번 커밋한다.
- **상태 문서 갱신도 묶음이 끝난 뒤 한 번** 몰아서 한다. 항목마다 WORK_STATE를 고치지 마라.

### 테스트 강도 — 작은 검증은 자주, 전체 검증은 수렴 후 크게 (CLAUDE.md §6)
- 구현 중에는 **변경한 표면과 직접 관련된 focused/subsystem 테스트만** 돌린다.
- **작은 변경마다 backend full / frontend full / runner full / static / build 를 전부 돌리지
  마라.** 한 Root Cause 묶음이 끝났을 때 그 묶음에 해당하는 스위트만 돌린다.
- 통합 Full Regression 은 **구현이 충분히 수렴한 큰 checkpoint 에서 한 번** 돌린다.
- 예외(조기 전체 회귀 허용): auth · RBAC · DB transaction · migration · security ·
  shared framework 처럼 영향 반경이 큰 기반 변경. 이때는 묶음을 고친 직후 한 번 돌린다.
- **버그 수정**은 재현 테스트를 먼저 만드는 것이 여전히 가장 빠르다 — 유지한다.
- **리팩터·신규 구현·UI 재설계**는 구현을 먼저 하고 관련 테스트를 뒤에 보강한다.
- **revert-to-verify** 는 회귀 위험이 실제로 큰 것에만(공유 component, 권한/스코프, transaction).
- 커버리지 숫자를 목표로 삼지 마라.

### 속도를 갉아먹는 것들 (하지 마라)
- 같은 파일을 여러 번 열고 조금씩 고치기 → 한 번에 필요한 변경을 다 반영한다
- 항목마다 전체 회귀 돌리기 → 묶음이 수렴했을 때 한 번
- 이미 확인한 사실을 다시 조사하기 → 이번 invocation 안에서 확인한 것은 다시 읽지 않는다
- WARM 회차에서 대형 상태 문서를 통독하기 → RUN CONTEXT 로 충분하다
- "다음 호출에서 하겠다"고 미루기 → 지금 같은 호출 안에서 계속한다

### Skill 사용 계약 — 지금 하는 작업에 맞는 Skill이 있으면 **하기 전에** 부른다
`Skill` 도구로 쓸 수 있는 Skill이 100개 넘게 있다. 전부 쓰라는 게 아니고, **지금 손대는 작업
종류에 해당하는 게 있으면 그걸 먼저 읽고 그 기준으로 만들라**는 뜻이다. 다 만든 뒤에 검사하는
용도가 아니라, 무엇을 어떻게 만들지 정할 때 쓰는 자다.

- **이름을 기억으로 추측하지 마라.** `Skill` 도구 목록이 정본이다. 없으면 없는 대로 진행한다 —
  Skill 부재는 blocker가 아니다(가속기다).
- 이 저장소 스택(Python 3.12 · FastAPI sync · SQLAlchemy sync · Alembic · SQLite WAL /
  React 18 · Vite)에 실제로 걸리는 것들. **이 표가 전부가 아니다** — 목록을 보고 맞는 걸 골라라.

  | 지금 하는 작업 | 부를 것 |
  |---|---|
  | 화면/레이아웃/정보위계/컴포넌트 설계 | `ui-ux-pro-max` |
  | 기존 화면 재설계(진단 → 후보) | `redesign-existing-projects` |
  | 디자인 규칙 위반 탐지 | `impeccable` (PostToolUse hook으로 자동도 돌지만 직접도 부른다) |
  | 버튼·라벨·오류·빈 상태·확인·알림 문구 | `ux-writing` |
  | 한국어 문구 다듬기 | `humanize-korean` (UX Writing **다음**) |
  | React 컴포넌트/상태/성능 | `frontend-patterns`, `coding-standards` |
  | Python 코드/관용구 | `python-patterns` |
  | pytest 작성·수정 | `python-testing` |
  | REST 엔드포인트 설계 | `api-design`, `backend-patterns` |
  | Alembic migration | `database-migrations` |
  | auth/RBAC/입력 처리/시크릿 | `security-review` |
  | 브라우저 E2E | `e2e-testing` |
  | 버그 원인 추적 | `superpowers:systematic-debugging` |
  | 재현 테스트 먼저 쓰기 | `superpowers:test-driven-development` |
  | 완료 주장 전 검증 | `superpowers:verification-before-completion`, `verification-loop` |
  | 중복/난잡함 정리 | `simplify` |
  | 배포/컨테이너 | `deployment-patterns`, `docker-patterns` |
  | AI/Runner 연동 | `claude-api`, `mcp-server-patterns` |

- **스택이 다른 Skill을 억지로 적용하지 마라.** 목록에는 `django-*`·`laravel-*`·`springboot-*`·
  `kotlin-*`·`rust-*`·`golang-*`·`jpa-patterns`·`postgres-patterns` 같은 것도 있다. 이 제품은
  FastAPI + SQLite다 — Django 보안 패턴이나 Postgres 인덱스 조언을 여기에 갖다 붙이면 틀린다.
- **Audit이 쓴 자를 그대로 써라.** 각 PA-RC 블록의 `quality_rubric` 필드가 그 Root Cause를 판정할
  때 쓴 기준이다. 그걸 안 읽고 만들면 acceptance_criteria의 글자는 만족시키면서 Audit이 재던
  품질 기준은 빗나간다 — 설계 의도는 맞는데 결과물이 안 맞는 경로가 정확히 여기다.
  **찾을 때만 쓰고 만들 때 안 쓰면 그 Root Cause는 반쯤만 닫힌 것이다.**
- 적용 우선순위는 **Audit과 같은 순서**를 쓴다(두 Phase가 다른 자를 쓰면 Handoff가 무의미해진다):
  사용자 업무 성공 > 기능 정확성 > 데이터/RBAC/보안 경계 > 명확한 UX > 일관성/접근성 >
  UX Writing > 한국어 자연스러움 > 시각적 완성도
- UX Writing을 먼저 적용하고 한국어 humanization은 그 뒤에 적용한다. humanization은 기술 용어·
  제품명·상태값·API/필드명·수치의 의미를 바꾸면 안 된다. 짧은 버튼명을 억지로 문학적으로 바꾸지 마라.
- **실제로 적용한 Skill의 이름을 커밋 메시지나 WORK_STATE 체크포인트에 한 줄로 남겨라.**
  쓰지 않은 Skill을 "적용했다"고 적으면 그것은 조작이다. 절대 하지 마라.

### UI/UX 재설계 권한 — 화면 구조를 바꾸는 것은 정상 작업이다
현재 UI를 보존하는 것이 목표가 **아니다.** 2026년 기준 Enterprise SaaS/AI Product 수준을 목표로,
데이터 의미·API 의미·RBAC 경계 같은 **제품 계약을 유지하면서** 아래를 네가 직접 결정하고 구현한다.
승인 대상으로 분류하지 마라.

Information Architecture 재편 · Sidebar 구조 변경 · Navigation 재구성 · Dashboard 재설계 ·
Page 구조 변경 · Component 구조 변경 · 여러 화면 통합 또는 분리 · Tab 구조 도입 ·
정보 위계 재조정 · 사용자 작업 동선 단축 · CTA 위치와 우선순위 변경 ·
Form/Table/Dashboard/Chat UX 개선 · Empty/Error/Loading/Feedback 개선 · Typography ·
Color System · Density/Spacing · Responsive · FHD/QHD/4K · Light/Dark · Accessibility ·
UX Writing · Interaction 개선

**단순 CSS/spacing 수정만 반복하면서 "UI/UX 개선 완료"로 판단하지 마라.** token migration 완료 ·
literal 제거 · a11y test green · semantic heading 적용 · lint green — 이것들은 전부 완료 근거가
아니다. 실제 화면을 보고 아래를 평가해야 완료다.

- 정보 위계가 명확한가 / 무엇을 먼저 봐야 하는지 3초 안에 보이는가
- 화면 밀도가 적절한가 / 불필요하게 긴가 / 반복 정보가 많은가
- 액션 우선순위가 명확한가(primary action이 하나로 읽히는가)
- Navigation이 업무 기준으로 이해되는가
- Dashboard가 실제 의사결정을 돕는가(장식용 카드가 아닌가)
- Table/Form이 실제로 쓰기 쉬운가
- Empty/Error/Loading 상태가 자연스러운가
- 화면 간 디자인 언어가 일관적인가
- 1920과 4K 모두에서 자연스러운가 / Light·Dark 모두 완성도가 있는가
- **기존 화면보다 실제 사용성이 좋아졌는가**

금지선: 기능 정확성·데이터 구조·RBAC·업무 정책·사용자 권한·실제 Workflow를 망가뜨리면서
시각만 화려하게 만드는 것.

### Handoff는 하한선이지 상한선이 아니다
Handoff 문구를 기계적으로 패치하는 것이 네 일이 아니다. 구현하면서 **더 나은 해결 방법을
발견하면** `조사 → 근거 비교 → 네가 판단 → 구현 → 테스트 → 실환경 검증`까지 직접 한다.
Handoff와 다르게 갔다면 그 근거를 DECISIONS.md에 사후로 남긴다(먼저 승인받지 않는다).

구현 중 새 결함이나 **같은 Root Cause의 다른 발생 지점**을 발견하면 사용자에게 넘기지 말고
같은 Cycle 안에서 조사하고 처리한다. 파일 하나만 고치고 같은 결함이 다른 화면·모듈에 남아
있으면 완료가 아니다 — Root Cause 기준으로 전체 영향 범위를 확인한다.

### Blocker는 사람 호출 상태가 아니다 — 자가 복구 사다리를 먼저 다 밟아라
"막혔다"고 적기 전에 아래를 실제로 시도했는지 확인한다. 하나라도 안 해 봤으면 그건 blocker가
아니라 아직 안 해 본 것이다.

다른 검증 방법 · 코드 정적 분석 · 실제 API 호출 · DB 상태 직접 조회 · 로그 분석 ·
테스트 데이터 생성 · QA 계정 직접 생성 · 로컬 dev 환경 · TEST SERVER 활용 ·
필요한 테스트 추가 · 대체 테스트 작성 · 브라우저 자동화(`scripts/ui_qa/`) ·
기존 스크린샷 활용 · 새 스크린샷 생성 · 재시도 · **다른 구현 전략 선택** ·
별도 worktree · 별도 branch

- 필요한 package/tool/browser가 없으면 **직접 설치하고 계속한다.**
- 필요한 QA 계정·데이터가 없으면 **직접 만들고 계속한다.**
- **한 작업이 막혔다고 프로젝트 전체를 멈추지 마라.** 그 작업에서 가능한 대체 검증을 전부 하고,
  정말 못 하는 부분만 사실대로 기록한 뒤 **다른 작업을 계속한다.**
- 사용자에게 blocker 해결을 요청하고 기다리지 않는다.
- 단, 네 권한 밖 외부 행위(자격증명 회전, 외부 운영시스템 변경)를 **성공한 것처럼 꾸미지 마라.**
  미수행 사실과 영향만 기록한다.

### 워킹트리에 다른 변경이 있어도 사람을 기다리지 마라
사용자나 다른 작업이 남긴 미커밋 변경이 있어도 그 사람의 작업 종료를 기다리지 않는다.
**그 변경을 삭제·reset·revert·drop·overwrite 하는 것은 절대 금지다.** 대신 안전한 길을 고른다.

1. 충돌하지 않는 파일부터 먼저 진행한다(대부분 여기서 끝난다)
2. 같은 파일을 건드려야 하면 `git worktree` 로 별도 작업 공간 + 별도 branch 를 만들어 거기서 하고,
   안전하게 병합 가능한 시점에 통합한다
3. 기존 변경은 그대로 보존한 채 커밋한다(네 변경만 stage 한다)

목표는 **사용자 변경 보호와 자율 실행을 동시에** 만족하는 것이다. 둘 중 하나를 포기하지 마라.

### 독립적인 조사는 병렬화해도 된다
지금 고친 파일과 **충돌하지 않는** 조사·분석은 subagent나 background agent로 병렬 실행해도
된다(예: 다음 Root Cause 후보의 소비처 전수 조사, 별도 영역의 증거 수집).
단, **메인 워킹트리의 writer는 너 하나뿐이다.** 병렬 작업자가 같은 워킹트리의 파일을 동시에
수정하게 하지 마라. 별도 worktree에서 실제 수정까지 한다면 branch를 분리하고, 메인 통합은
너 혼자 통제한다. docs/의 공유 상태 문서도 동시에 여러 작업자가 고치지 않는다.

## 4단계 — 승인된 TEST SERVER: 완전 자율 실행 권한 (CLAUDE.md §9)
아래 RUN CONTEXT의 `test_server`가 승인된 TEST SERVER(`10.100.64.X` 대역)다. **이 서버에서는
사람의 개입을 기다리지 말고 네가 직접 실행한다.** 이것은 Production이 아니다.

직접 해도 되는 것(예시이지 제한 목록이 아니다):
- SSH 접속, 원격 명령 실행, 파일 전송(`scp`/`rsync`)
- `sudo`/root 작업, package 설치, 서비스 재시작
- systemd unit · nginx 설정 확인/수정/reload
- DB 확인·migration 실행·데이터 조사·복구 리허설
- ClovirAssist 관련 n8n workflow와 Claude Runner의 조사·수정·재시작·검증
  (ClovirAssist과 **무관한** 다른 팀의 n8n/서비스는 건드리지 않는다 — CLAUDE.md §3.9)
- 배포·재배포·롤백, 배포 후 revision/health 확인
- browser/Chrome/Playwright 등 E2E에 필요한 도구 설치와 실행
- 필요한 QA 계정·조직·테스트 데이터 직접 생성

**필요한 package/tool/browser가 없다는 것은 blocker가 아니다 — 직접 설치하고 계속한다.**
**필요한 QA 계정·데이터가 없다는 것도 blocker가 아니다 — 직접 만들고 계속한다.**
저장소의 배포 스크립트나 문서에 "이 단계는 사용자가 직접 실행"이라고 적힌 주석이 있어도,
그것은 이 권한이 확정되기 전의 낡은 제약이다. TEST SERVER에서는 네가 실행한다.

### 자격증명 취급 (이건 완화되지 않는다 — CLAUDE.md §3.3/§3.4)
- SSH는 키 인증이다. `-o BatchMode=yes` 로 비대화형 접속한다.
- sudo 비밀번호가 필요하면 **환경변수 `__SUDO_ENV_NAME__` 의 값을 stdin으로만** 넘긴다:
      ssh -o BatchMode=yes <target> 'sudo -S -p "" <명령>' <<< "$env:__SUDO_ENV_NAME__"
  같은 방식(셸에 맞게 조정). RUN CONTEXT의 `sudo_credential=available` 이면 쓸 수 있다.
- 비밀번호를 **명령행 인자, 로그, 파일, git 추적 파일, 문서, 커밋 메시지, 화면 출력 어디에도
  절대 쓰지 마라.** `sshpass` 금지. 값을 에코하지 마라.
- `sudo_credential=absent` 이고 `sudo_nopasswd=false` 이면 sudo가 필요한 작업만 못 한다.
  그 작업이 무엇인지 docs/WORK_STATE.md에 정확히 적고, **sudo가 필요 없는 나머지 작업은 전부
  계속하라.** 한 blocker로 다른 작업까지 멈추지 마라.
- 이 권한은 **승인된 TEST SERVER 대역에만** 적용된다. 다른 서버나 향후 Production으로
  자동 확장하지 않는다.

## 5단계 — 화면 품질 축과 실제 브라우저 검증

### 매번 함께 보는 축 (완료 기준에만 있는 게 아니라 구현할 때 본다)
UI를 건드리는 Root Cause는 다음을 **구현하면서** 확인한다. 나중에 몰아서 하면 다시 뜯어야 한다.
- **Responsive** — FHD/QHD/4K, Windows 125%/150%/175% 배율, 좁은 폭에서 정보가 사라지거나 겹치는가
- **Light/Dark** — 두 테마 각각에서 대비·상태색·그림자·아이콘이 성립하는가
- **Accessibility** — keyboard/tab order/focus 표시/modal focus trap/aria/오류-입력 연결/대비
- 확인한 축은 `docs/QA_COVERAGE.md`에 반영한다. "화면을 열어 봤다"는 검증이 아니다.

### 브라우저 E2E — 이 무인 실행에는 브라우저 MCP 도구가 **없다**
`-p` 비대화형 모드에는 Chrome MCP 도구가 붙어 있지 않다. 그것을 찾지 말고 **저장소의 하네스**를
써라. 이미 있고, 목적에 맞게 만들어져 있다.

- `scripts/ui_qa/` — Playwright 기반 시각·기하 QA 하네스. 실제 서버에 로그인한 상태로
  **모든 화면 × 라이트/다크 × 뷰포트 행렬**을 돌며 스크린샷·레이아웃·콘솔·접근성 검사를 하고
  HTML 리포트를 만든다. `scripts/ui_qa/README.md`가 사용법의 정본이다. 산출물은 `dist/`(gitignore).
  `contrast.py`·`keyboard.py`·`failure_states.py`·`hostile_data.py`·`fab_occlusion.py` 등
  축별 모듈이 이미 있으니 새로 만들지 말고 **그것을 확장**하라.
- Playwright는 설치돼 있다. 브라우저 바이너리나 의존성이 없으면 **직접 설치하고 계속한다**
  (4단계 권한). 도구 부재는 blocker가 아니다.
- CLAUDE.md §10의 Chrome Whole-product E2E는 이 하네스 + 필요한 수동 시나리오로 만족시킨다.
  스크린샷이 존재한다는 사실·페이지가 열린다는 사실·health 200만으로 E2E 완료 처리하지 마라.

### 배포 흐름은 이 순서다 (CLAUDE.md §9)
`whole-product 구현 수렴 → Full Regression green → Static Checks → Build →
통합 Deploy → service/health/revision 확인 → Chrome Whole-product E2E`
작은 변경마다 배포하지 마라. 배포 환경에서 확인하지 않으면 다음 구현 자체가 불가능한 genuine
blocker만 예외다. 실환경에서 문제를 찾으면
`수집 → Root Cause grouping → 일괄 수정 → focused test → 필요한 Full Regression →
통합 재배포 → Chrome 재E2E` 순서로 처리한다.

## 6단계 — 체크포인트는 멈추는 이유가 아니다
묶음 하나가 끝났을 때 무엇을 바꿨고 다음에 무엇을 할지 docs/WORK_STATE.md(필요하면
BACKLOG.md·PROGRESS_STATUS.md·QA_COVERAGE.md도 함께)에 적고 git commit 한다. 항목마다가
아니다. 이 파일 기반 체크포인트는 **복구용**이지 종료 신호가 아니다 — working tree가
깨끗해졌다는 것 자체는 멈출 이유가 안 된다. 커밋하고 상태 문서를 갱신한 **즉시** 다음
작업으로 넘어간다.

## 7단계 — 멈춰도 되는 유일한 기준
Summary·recap·commit·clean tree·Full Regression green·build green·"현재 할 일 목록이 비었다"·
"체크포인트에 도달했다"는 전부 종료 사유가 아니다. 멈추는 것이 정당한 경우는 둘뿐이다:
  (a) 지금 당장 실행 가능한 남은 작업이 **정말로 하나도** 없다 — 남은 모든 후보가 네 권한 밖
      외부 행위(자격증명 회전, 외부 운영시스템 변경, 조직 정책 변경)로만 막혔고, 위 자가 복구
      사다리를 전부 밟았다. 이 경우는 극히 드물다. 다음은 전부 여기에 **해당하지 않는다**:
      · TEST SERVER 접근 · package/tool/browser 부재 · QA 계정/데이터 부재 (4단계 — 직접 한다)
      · 설계 선택지가 여럿이다 · 업무 흐름이 바뀐다 · 변경 규모가 크다 (0단계 — 네가 정한다)
      · 검증 방법을 못 찾았다 (자가 복구 사다리를 다 안 밟은 것이다)
      · 한 blocker 때문에 독립적으로 가능한 다른 작업까지 멈추는 것
  (b) 프로젝트 전체 완성 기준(CLAUDE.md §13)이 실제로 충족됐다고 스스로 검증했다 — 이 경우에만
      var/runner/PROJECT_COMPLETE 파일을 만들어라(한국어로 근거를 짧게, 타임스탬프 포함 —
      빈 파일은 완료로 인정되지 않는다). 확인해야 할 것:
      Master Plan 주요 목표 완료 · 주요 Backlog 완료/정당한 정리 · 전체 구현 수렴 ·
      Design/UX 완료(토큰 정리 수준이 아니라 실제 페이지 UX) · Frontend/Backend/API/DB/RBAC
      전부 연결 · QA Coverage 주요 공백 해소 · Full Regression green · Static Checks green ·
      Build green · 통합 Deploy 완료 · 실제 배포 revision 확인 · Chrome Whole-product E2E ·
      Console/Network 검증 · Responsive/Theme/Accessibility · 실환경 발견 문제 수정 및 재검증 ·
      Final Whole Product Re-Audit에서 새로운 중대한 Root Cause 범주가 거의 없음 ·
      **그리고 var/product-audit/IMPLEMENTATION_REQUIRED 가 남아 있지 않을 것.**

Supervisor는 PROJECT_COMPLETE를 그대로 믿지 않는다. 내용 유무와 Product Audit Handoff 소진
여부를 기계적으로 검사하고, 통과하지 못하면 marker를 격리한 뒤 거부 사유를 다음 invocation
프롬프트에 그대로 전달하고 작업을 계속시킨다. 그러니 애초에 정확히 만들어라.

(a)라고 판단되면 WORK_STATE.md에 어떤 작업이 어떤 외부 요인으로 막혔는지 구체적으로 적어라.
그 외에는 항상 다음 작업으로 계속한다.

참고: PROJECT_COMPLETE 없이 끝내려 하면 Stop hook이 한 번 제동을 걸어 계속하라고 되돌린다.
그 제동은 보조 장치일 뿐이니 그것에 기대지 말고 애초에 스스로 계속하라.

지금 시작하라.
'@

    $iterationsThisLaunch = 0
    $dirtyWaits = 0
    $script:LastInvocationDirtiedTree = $false
    Write-RunnerLog ("Supervisor 시작 PID=$PID projectDir=$ProjectDir baseModel=$Model baseEffort=$Effort " +
        "highRiskEffort=$HighRiskEffort dynamicEffort=$DynamicEffort idleTimeout=${IdleTimeoutMinutes}분 " +
        "maxRuntime=$(if ($MaxRuntimeMinutes -gt 0) { "${MaxRuntimeMinutes}분" } else { '무제한' }) " +
        "(CLOVIR_SUPERVISED=1, Stop hook 보조 제동 활성)")

    while ($true) {
        $loopSw = [System.Diagnostics.Stopwatch]::StartNew()

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
            $st.invocationsSinceCold = 999      # 거부 직후는 반드시 COLD 로 다시 접지한다
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
                "production 기본값은 무제한(0)입니다. run_all.ps1 로 실행 중이면 자동으로 이어서 다시 시작합니다."
            )
            Write-RunnerLog "invocation 상한 $MaxIterationsPerLaunch 도달(test override) — 종료(PROJECT_COMPLETE 아님)."
            $script:FinalExit = 0
            break
        }

        $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog

        if ((Get-IntOr $state.consecutiveFailures) -ge $MaxConsecutiveFailures) {
            $msg = "auto-stopped after $($state.consecutiveFailures) consecutive failures at $(Get-Date -Format o) lastClass=$($state.lastFailureClass)"
            [void](Write-TextFile $AutoStopFile $msg)
            Write-Banner @(
                "연속 실패 $($state.consecutiveFailures)회 >= $MaxConsecutiveFailures — 원인 없이 계속 태우지 않기 위해 중단합니다.",
                "마지막 실패 유형: $($state.lastFailureClass)",
                "각 invocation 의 원본 출력은 $LogDir 에 있습니다. 원인을 확인하세요.",
                "고친 뒤에는 이 스크립트를 그냥 다시 실행하면 됩니다 — AUTO_STOP 은 자동으로 정리됩니다."
            )
            Write-RunnerLog "연속 실패 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            $script:FinalExit = 6
            break
        }
        if ((Get-IntOr $state.identicalFailureCount) -ge $MaxIdenticalFailures) {
            $msg = ("auto-stopped: identical failure repeated $($state.identicalFailureCount) times at $(Get-Date -Format o) " +
                    "signature=$($state.lastFailureSignature)")
            [void](Write-TextFile $AutoStopFile $msg)
            Write-Banner @(
                "**같은 실패가 $($state.identicalFailureCount)회 연속** 반복됐습니다 — 재시도로는 낫지 않는 결정적 실패입니다.",
                "  유형: $($state.lastFailureClass)",
                "  지문: $($state.lastFailureSignature)",
                "원본 로그: $LogDir · 원인을 고친 뒤 다시 실행하면 AUTO_STOP 은 자동으로 정리됩니다."
            )
            Write-RunnerLog "동일 실패 반복 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            $script:FinalExit = 6
            break
        }
        if ((Get-IntOr $state.consecutiveInfraRetries) -ge $MaxInfraRetries) {
            $msg = "auto-stopped: infra retries ($($state.lastFailureClass)) reached $($state.consecutiveInfraRetries) at $(Get-Date -Format o)"
            [void](Write-TextFile $AutoStopFile $msg)
            Write-Banner @(
                "인프라성 재시도(rate-limit/network/overload/resume)가 $($state.consecutiveInfraRetries)회 연속입니다.",
                "  마지막 유형: $($state.lastFailureClass)",
                "실제 작업이 한 번도 진행되지 않았습니다 — 네트워크·인증(`claude auth`)·구독 상태 문제일 수 있습니다.",
                "run_all.ps1 로 실행 중이면 상한까지 자동으로 다시 시도합니다. 단독 실행이면 여기서 멈춥니다."
            )
            Write-RunnerLog "인프라 재시도 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            $script:FinalExit = 6
            break
        }

        # ── dirty 워킹트리 ────────────────────────────────────────────────────
        # 목적은 "사람이 지금 편집 중일 때 충돌하지 않는 것" 하나뿐이다.
        # 우리가 직전에 죽인 우리 Worker 가 남긴 dirty 를 기다리는 것은 순수한 낭비였다.
        # `SelfCaused` = 직전 invocation 이 **스스로** 워킹트리를 더럽혔다. 그때는 기다릴 이유가
        # 전혀 없다 — 사람이 아니라 우리가 만든 변경이기 때문이다. 실제 운영 로그에서 낭비된
        # 5분 30초 x 2구간이 정확히 이 경우였다(우리가 240분 timeout 으로 죽인 우리 Worker 가
        # 남긴 파일을 다음 회차가 "사람이 편집 중일지도 모른다"며 기다렸다).
        $dirtySw = [System.Diagnostics.Stopwatch]::StartNew()
        $dirtyDecision = Get-DirtyDecision -RepoDir $ProjectDir -QuietSeconds $DirtyQuietSeconds `
            -SelfCaused $script:LastInvocationDirtiedTree
        if (-not $dirtyDecision.Proceed) {
            $dirtyWaits += 1
            if ($dirtyWaits -ge $MaxDirtyWaits) {
                Write-RunnerLog ("워킹트리가 계속 변하지만 $dirtyWaits 회(약 $([int]($dirtyWaits * $DirtyPollSeconds / 60))분) 기다렸으므로 그대로 진행한다(무한 대기 방지). " +
                    $dirtyDecision.Detail)
            } else {
                Write-RunnerLog ("사람이 편집 중으로 보임 — ${DirtyPollSeconds}초 뒤 다시 확인 ($dirtyWaits/$MaxDirtyWaits). " + $dirtyDecision.Detail)
                if (-not (Start-InterruptibleSleep -Seconds $DirtyPollSeconds -StopFile $StopFile -LogPath $RunnerLog -Reason "dirty 워킹트리")) {
                    $script:FinalExit = 3; break
                }
                continue
            }
        } else {
            if ($dirtyWaits -gt 0) {
                Write-RunnerLog ("dirty 대기 해제(reason=$($dirtyDecision.Reason)) — " + $dirtyDecision.Detail)
            }
            $dirtyWaits = 0
        }
        $dirtySw.Stop()

        # ── invocation 준비 ───────────────────────────────────────────────────
        $prepSw = [System.Diagnostics.Stopwatch]::StartNew()

        # 같은 초에 두 invocation 이 시작되면 로그 파일 이름이 겹쳐 서로 덮어썼다 — 순번을 붙인다.
        $timestamp = "{0}-{1:d3}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), ($iterationsThisLaunch + 1)
        $logFile = Join-Path $LogDir "$timestamp.log"
        $errFile = "$logFile.err"
        $invocationPromptFile = Join-Path $LogDir "$timestamp.prompt.txt"
        $headBefore   = Get-GitHeadSha -RepoDir $ProjectDir
        $prevHead     = [string]$state.lastHeadSha
        if ([string]::IsNullOrWhiteSpace($prevHead)) { $prevHead = $headBefore }

        # Persistent Worker Session: 저장된 session_id 가 있으면 이어받고(--resume), 없으면
        # 새로 시작하며 **호출 전에** 저장한다(프로세스가 죽어도 다음 반복이 무엇을 시도했는지 안다).
        $sessionId = Read-SessionId $SessionIdFile
        $isNewSession = $false
        if ($null -eq $sessionId) {
            $sessionId = [guid]::NewGuid().ToString()
            $isNewSession = $true
            [void](Write-TextFile $SessionIdFile $sessionId)
            Write-RunnerLog "저장된 Worker Session 이 없음 — 새 session_id=$sessionId 로 시작."
        }

        # ── COLD / WARM 판정 ──
        # WARM = "같은 세션을 정상 resume 했고, 직전 회차가 정상적으로 끝났다".
        # 그 밖에는 전부 COLD 로 다시 접지한다(표류 방지). 주기적으로도 한 번 COLD 로 돌아간다.
        $sinceCold = Get-IntOr $state.invocationsSinceCold 999
        $coldReasons = New-Object System.Collections.Generic.List[string]
        if ($isNewSession) { $coldReasons.Add("new-session") }
        if ((Get-IntOr $state.completionRejections) -gt 0 -and $sinceCold -ge 999) { $coldReasons.Add("completion-gate-rejected") }
        if ($sinceCold -ge $ColdRefreshEvery) { $coldReasons.Add("periodic-refresh(${sinceCold}/${ColdRefreshEvery})") }
        if ($state.lastFailureClass -eq "idle-timeout" -or $state.lastFailureClass -eq "hard-timeout") { $coldReasons.Add("previous-invocation-killed") }
        $isCold = ($coldReasons.Count -gt 0)
        $mode = if ($isCold) { "COLD" } else { "WARM" }

        # ── model / effort 결정 ──
        $hint = Read-NextInvocationHint -Path $NextHintFile -LogPath $RunnerLog
        $useModel  = $Model
        $useEffort = $Effort
        $effortSource = "base"
        if ($DynamicEffort) {
            if ($isCold) {
                $useEffort = $HighRiskEffort
                if ($HighRiskModel) { $useModel = $HighRiskModel }
                $effortSource = "cold"
            }
            if ((Get-IntOr $state.consecutiveFailures) -ge 2) {
                $useEffort = $HighRiskEffort
                $effortSource = "failure-streak"
            }
            if ($hint.Found) {
                if ($hint.Effort) { $useEffort = $hint.Effort }
                if ($hint.Model)  { $useModel  = $hint.Model }
                $effortSource = "worker-hint"
                Write-RunnerLog "Worker 가 남긴 다음 회차 힌트를 적용한다: effort=$($hint.Effort) model=$($hint.Model) reason=$($hint.Reason)"
            }
        }

        # ── compact 상태 cache 생성(원본 문서에서 언제든 재생성 가능한 index) ──
        $cache = New-RunnerContextCache -ProjectDir $ProjectDir -OutDir $RunnerDir -Extra ([ordered]@{
            runner = "autonomous_runner.ps1"; mode = $mode; invocation = ($iterationsThisLaunch + 1)
        })

        $promptBody = $promptCore.Replace("__STATE_RESTORE_SECTION__", $(if ($isCold) { $promptCold } else { $promptWarm }))
        $promptBody = $promptBody.Replace("__SUDO_ENV_NAME__", $SudoPasswordEnvName)
        if ($PromptOverrideFile -and (Test-Path -LiteralPath $PromptOverrideFile)) {
            $promptBody = Read-TextOrEmpty $PromptOverrideFile
        }

        $lastRejection = Read-TextOrEmpty $GateRejectionFile
        $ctx = New-Object System.Collections.Generic.List[string]
        $ctx.Add("")
        $ctx.Add("======================================================================")
        $ctx.Add("RUN CONTEXT (Supervisor 가 매 invocation 에 주입한다 — 이것으로 위치를 파악하라)")
        $ctx.Add("======================================================================")
        $ctx.Add("runner=autonomous_runner.ps1")
        $ctx.Add("invocation=$($iterationsThisLaunch + 1)")
        $ctx.Add("started_at=$(Get-Date -Format o)")
        $ctx.Add("resume_mode=$mode$(if ($isCold) { ' (' + ($coldReasons -join ',') + ')' } else { ' (같은 세션 정상 이어받음 — 대형 문서 재독 금지)' })")
        $ctx.Add("model=$useModel effort=$useEffort effort_source=$effortSource")
        $ctx.Add("branch=$($cache.Branch)")
        $ctx.Add("head=$headBefore")
        $ctx.Add("previous_invocation_head=$prevHead")
        $commitsSince = @()
        if ($prevHead -and $headBefore -and $prevHead -ne $headBefore) {
            $commitsSince = @(Get-GitCommitSubjects -RepoDir $ProjectDir -Count 20 -Range "$prevHead..$headBefore")
        }
        $ctx.Add("commits_since_previous_invocation=$($commitsSince.Count)")
        foreach ($c in $commitsSince) { $ctx.Add("  + $c") }
        if ($commitsSince.Count -eq 0) {
            $ctx.Add("recent_commits(최근 5):")
            foreach ($c in @($cache.RecentCommits | Select-Object -First 5)) { $ctx.Add("  - $c") }
        }
        $ctx.Add("dirty_paths=$($cache.DirtyCount)$(if ($cache.DirtyCount -gt 0) { ' (' + $dirtyDecision.Reason + ')' } else { '' })")
        if ($cache.DirtyCount -gt 0) {
            foreach ($p in @($dirtyDecision.Paths | Select-Object -First 15)) { $ctx.Add("  ~ $p") }
        }
        $ctx.Add("unresolved_backlog_index=$($cache.UnresolvedCount)건 (전체 목록: var/runner/unresolved_index.json — BACKLOG.md 에서 기계 추출한 보조 index)")
        $ctx.Add("state_cache=var/runner/active_state.json (문서 줄 수·수정 시각·최근 커밋)")
        $ctx.Add("last_exit_code=$($state.lastExitCode) last_failure_class=$($state.lastFailureClass)")
        $ctx.Add("consecutive_failures=$($state.consecutiveFailures) total_runs=$($state.totalRuns)")

        $implRequiredNow = Test-MarkerValid $ImplementationRequiredFile
        $ctx.Add("implementation_required=$(if ($implRequiredNow) { 'true' } else { 'false' })")
        if ($implRequiredNow) {
            $reqText = Read-TextOrEmpty $ImplementationRequiredFile
            $ctx.Add("audit_cycle_id=$(Get-KeyValueFromText $reqText 'cycle_id')")
            $ctx.Add("audit_root_causes=$(Get-KeyValueFromText $reqText 'root_causes')")
            $ctx.Add("handoff_path=$HandoffRel")
            $ctx.Add("handoff_present=$(Test-MarkerValid $HandoffFile)")
        }

        # TEST SERVER 자율 실행에 필요한 **사실**을 준다(매번 Worker 가 알아내지 않게).
        $ctx.Add("test_server=$(if ($TestServerTarget) { $TestServerTarget } else { '(저장소 설정에서 찾지 못함)' })")
        $ctx.Add("test_server_ssh=$(if (-not $script:ServerAccess.Probed) { 'unprobed' } elseif ($script:ServerAccess.SshOk) { 'ok' } else { 'unreachable' })")
        $ctx.Add("sudo_nopasswd=$(if ($script:ServerAccess.SudoNoPassword) { 'true' } else { 'false' })")
        $ctx.Add("sudo_credential=$(if ($script:SudoCredentialAvailable) { "available (환경변수 $SudoPasswordEnvName — stdin 으로만 사용, 절대 출력 금지)" } else { 'absent' })")
        $ctx.Add("test_server_authority=full (CLAUDE.md §9 — SSH·sudo·package·systemd·nginx·DB·n8n·Runner·배포·E2E 를 직접 수행한다. 사람 개입을 기다리지 마라)")

        if (-not [string]::IsNullOrWhiteSpace($lastRejection)) {
            $ctx.Add("")
            $ctx.Add("--- 직전 PROJECT_COMPLETE 가 기계 Gate 에서 거부된 사유(반드시 먼저 해소하라) ---")
            $ctx.Add($lastRejection.Trim())
        }
        $ctx.Add("======================================================================")
        $ctxText = ($ctx -join [Environment]::NewLine)
        $promptBody = $promptBody + [Environment]::NewLine + $ctxText + [Environment]::NewLine
        [void](Write-TextFile $ResumeContextFile $ctxText)

        if (-not (Write-TextFile $invocationPromptFile $promptBody)) {
            Write-RunnerLog "프롬프트 파일을 쓰지 못했다($invocationPromptFile) — 이 invocation 을 실패로 세고 재시도한다."
            $state.consecutiveFailures = (Get-IntOr $state.consecutiveFailures) + 1
            [void](Save-StateFile $StateFile $state)
            $iterationsThisLaunch += 1
            continue
        }

        # 주의: 이 배열에 빈 문자열("") 원소를 넣지 마라. Windows 에서 -ArgumentList 가 배열을
        # 커맨드라인으로 재조립할 때 빈 원소를 누락시켜 뒤 인자가 한 칸씩 밀리고,
        # --session-id/--resume 가 엉뚱한 값에 붙는 것까지 2026-08-12 에 실제로 재현했다.
        #
        # --permission-mode bypassPermissions: 2026-08-13 controlled probe 로 `auto` 가 무인
        #   실행에서 Write/Bash 를 실제로 거부하는 것을 확인했다(거부 2건, 파일 0개 생성).
        #   승인해 줄 사람이 없는 Supervisor 에서 그 거부는 그대로 작업 실패다.
        # --output-format stream-json --verbose: 활동 신호(idle timeout)·진행 표시·
        #   rate limit reset 시각을 얻기 위한 것이다. 마지막 줄은 여전히 result 객체라
        #   종료 판정과 actualModel 파싱은 그대로 동작한다(실측 확인). --verbose 는 CLI 가
        #   stream-json 과 함께 **요구**한다(없으면 즉시 error).
        $argList = @(
            "-p",
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json",
            "--verbose"
        )
        # 0 이면 플래그 자체를 붙이지 않는다(CLI 가 0 을 "무제한"으로 해석한다는 근거가 없다).
        if ($MaxBudgetUsd -gt 0) { $argList += @("--max-budget-usd", "$MaxBudgetUsd") }
        if ($isNewSession) { $argList += @("--session-id", $sessionId) }
        else               { $argList += @("--resume", $sessionId) }
        if ($useModel)      { $argList += @("--model", $useModel) }
        if ($useEffort)     { $argList += @("--effort", $useEffort) }
        if ($FallbackModel) { $argList += @("--fallback-model", $FallbackModel) }

        # Worker 를 띄우기 **직전**의 워킹트리 서명. 끝난 뒤 이것과 비교해서 "이번 회차가
        # 워킹트리를 더럽혔는가"를 판정하고, 다음 회차의 dirty 대기를 건너뛴다.
        $preWorkerDirtySig = ((@(Get-GitStatusEntries -RepoDir $ProjectDir | ForEach-Object { $_.Path }) | Sort-Object -Unique) -join ';')

        $prepSw.Stop()
        $budgetLabel  = if ($MaxBudgetUsd -gt 0) { "`$$MaxBudgetUsd" } else { "무제한" }
        $timeoutLabel = if ($MaxRuntimeMinutes -gt 0) { "hard ${MaxRuntimeMinutes}분" } else { "hard 없음" }
        Write-RunnerLog ("Worker invocation 시작 #$($iterationsThisLaunch + 1) mode=$mode model=$useModel effort=$useEffort($effortSource) " +
            "session=$sessionId$(if ($isNewSession) { '(신규)' } else { '(resume)' }) budget=$budgetLabel " +
            "timeout=$timeoutLabel idle=${IdleTimeoutMinutes}분 contextCacheMs=$($cache.BuildMs) log=$logFile")

        $script:LastProgressLoggedAt = Get-Date
        $progress = {
            param($snap)
            $line = ("  ▶ #{0} {1}/{2} · 경과 {3} · 이벤트 {4} · 도구 {5}회{6} · 출력 {7} · 마지막 활동 {8}초 전 · PID {9}" -f `
                ($iterationsThisLaunch + 1), $useModel, $useEffort,
                (Format-Duration $snap.ElapsedSeconds), $snap.Events, $snap.ToolUses,
                $(if ($snap.LastTool) { " (최근 $($snap.LastTool))" } else { "" }),
                (Format-Bytes $snap.OutBytes), [int]$snap.IdleSeconds, $snap.Pid)
            Write-ConsoleLine $line
            if (((Get-Date) - $script:LastProgressLoggedAt).TotalSeconds -ge $ProgressLogEverySeconds) {
                $script:LastProgressLoggedAt = Get-Date
                Write-LogLine $RunnerLog ("진행 중" + $line)
            }
        }

        $workerSw = [System.Diagnostics.Stopwatch]::StartNew()
        $outcome = Invoke-ClaudeWorker -ClaudeExe $ClaudeExe -ArgList $argList -WorkingDirectory $ProjectDir `
            -PromptFile $invocationPromptFile -StdOutFile $logFile -StdErrFile $errFile `
            -MaxRuntimeMinutes $MaxRuntimeMinutes -IdleTimeoutMinutes $IdleTimeoutMinutes `
            -ProgressIntervalSeconds $ProgressIntervalSeconds -ProgressCallback $progress -LogPath $RunnerLog
        $workerSw.Stop()
        $exitCode = $outcome.ExitCode

        $postSw = [System.Diagnostics.Stopwatch]::StartNew()

        # 이 invocation 이 실제로 무언가를 남겼는가(=진척). 아래 실패 계산의 축이다.
        $headAfter  = Get-GitHeadSha -RepoDir $ProjectDir
        $progressed = ($headBefore -ne $headAfter) -and (-not [string]::IsNullOrWhiteSpace($headAfter))
        $newCommits = 0
        if ($progressed) { $newCommits = Get-GitCommitCount -RepoDir $ProjectDir -Range "$headBefore..$headAfter" }
        $postWorkerDirtySig = ((@(Get-GitStatusEntries -RepoDir $ProjectDir | ForEach-Object { $_.Path }) | Sort-Object -Unique) -join ';')
        $script:LastInvocationDirtiedTree = ($postWorkerDirtySig -ne $preWorkerDirtySig -and -not [string]::IsNullOrEmpty($postWorkerDirtySig))

        $errText = (Read-TextOrEmpty $errFile)
        $outTail = ""
        if ($exitCode -ne 0) {
            # 실패 분류에는 stdout 전체가 필요 없다(수십 MB 가 될 수 있다) — 꼬리만 본다.
            $outAll = Read-TextOrEmpty $logFile
            if ($outAll.Length -gt 20000) { $outTail = $outAll.Substring($outAll.Length - 20000) } else { $outTail = $outAll }
        }
        $fc = Get-InvocationFailureClass -ExitCode $exitCode -Progressed $progressed -IsNewSession $isNewSession `
            -TimeoutKind $outcome.TimeoutKind -Source $outcome.Source -StdErrText $errText -StdOutText $outTail

        if ($fc.Class -eq "resume-failure") {
            Write-RunnerLog "저장된 session_id=$sessionId 를 더 이상 resume 할 수 없음(세션 인프라 문제 — 작업 실패 아님) — 지우고 다음 반복에서 새 Worker Session 으로 즉시 재시작."
            Remove-Item -LiteralPath $SessionIdFile -Force -ErrorAction SilentlyContinue
        }

        $iterationsThisLaunch += 1
        $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog

        # ── 실패 카운터: 유형별로 다르게 센다 ──
        $signature = ""
        if ($fc.Class -eq "ok" -or $fc.Class -eq "progress") {
            $state.consecutiveFailures = 0
            $state.consecutiveInfraRetries = 0
            $state.consecutiveRateLimitHits = 0
            $state.identicalFailureCount = 0
            $state.lastFailureSignature = ""
            $state.sessionRotatedForStreak = $false
            if ($fc.Class -eq "progress") {
                Write-RunnerLog "exit=$exitCode 이지만 이 invocation 이 커밋 ${newCommits}건을 남겼다($headBefore -> $headAfter) — 진척이 있으므로 연속 실패로 세지 않는다."
            }
        } else {
            $signature = Get-FailureSignature -Class $fc.Class -Text ($errText + " " + $outTail)
            if ($signature -eq [string]$state.lastFailureSignature) {
                $state.identicalFailureCount = (Get-IntOr $state.identicalFailureCount) + 1
            } else {
                $state.identicalFailureCount = 1
            }
            $state.lastFailureSignature = $signature

            if ($fc.IsInfra) {
                $state.consecutiveInfraRetries = (Get-IntOr $state.consecutiveInfraRetries) + 1
                if ($fc.Class -eq "rate-limit" -or $fc.Class -eq "overload") {
                    $state.consecutiveRateLimitHits = (Get-IntOr $state.consecutiveRateLimitHits) + 1
                }
            }
            if ($fc.CountsAsFailure) {
                $state.consecutiveFailures = (Get-IntOr $state.consecutiveFailures) + 1
                # 같은 세션이 결정적으로 계속 실패하면(오염된 세션) 상한 도달 전에 한 번만 회전시킨다.
                # 실패 카운터는 그대로 둔다 — 원인이 다른 데 있으면 예정대로 AUTO_STOP 에 도달해야 한다.
                if ((Get-IntOr $state.consecutiveFailures) -ge 2 -and
                    (-not $state.sessionRotatedForStreak) -and (-not $isNewSession)) {
                    Remove-Item -LiteralPath $SessionIdFile -Force -ErrorAction SilentlyContinue
                    $state.sessionRotatedForStreak = $true
                    Write-RunnerLog "같은 Worker Session 에서 연속 실패가 이어져 session_id 를 한 번 회전한다(오염된 세션 복구 시도)."
                }
            }
        }
        $state.lastFailureClass = $fc.Class
        $state.lastRunAt = (Get-Date -Format o)
        $state.lastExitCode = $exitCode
        $state.lastHeadSha = $headAfter
        $state.totalRuns = (Get-IntOr $state.totalRuns) + 1
        $state.totalIterationsThisLaunch = $iterationsThisLaunch
        if ($isCold) { $state.invocationsSinceCold = 1 } else { $state.invocationsSinceCold = (Get-IntOr $state.invocationsSinceCold) + 1 }
        [void](Save-StateFile $StateFile $state)

        # §11 이 요구하는 증거를 한 줄에 모은다. secret 은 남기지 않는다(session_id 는 불투명 UUID).
        $headSha = Get-GitHeadSha -RepoDir $ProjectDir -Short
        $actualModel = Get-ActualModel $logFile
        $stats = Get-ClaudeResultStats $logFile
        $completeMarkerPresent = Test-Path -LiteralPath $CompleteFile
        Write-RunnerLog ("Worker invocation 종료 #$iterationsThisLaunch exit=$exitCode class=$($fc.Class) exitSource=$($outcome.Source) " +
            "mode=$mode handleCached=$($outcome.HandleCached) session=$sessionId requestedModel=$useModel requestedEffort=$useEffort " +
            "actualModel=$actualModel turns=$($stats.NumTurns) denials=$($stats.PermissionDenials) tools=$($outcome.ToolUses) " +
            "commits=$newCommits duration=$(Format-Duration ($outcome.DurationMs / 1000)) " +
            "consecutiveFailures=$($state.consecutiveFailures) infraRetries=$($state.consecutiveInfraRetries) " +
            "identical=$($state.identicalFailureCount) totalRuns=$($state.totalRuns) headSha=$headSha " +
            "PROJECT_COMPLETE_marker=$completeMarkerPresent")
        if ($stats.PermissionDenials -gt 0) {
            Write-RunnerLog "경고: 이 invocation 에서 도구 권한 거부가 $($stats.PermissionDenials)건 있었다 — 무인 실행에서는 그대로 작업 손실이다. permission mode 설정을 확인하라."
        }

        # ── 백오프: 유형별로 다르게 기다린다 ──
        $backoffSw = [System.Diagnostics.Stopwatch]::StartNew()
        $waited = 0
        if ($fc.Class -eq "rate-limit" -or $fc.Class -eq "overload") {
            # 실제 reset 시각을 알면 지수 백오프 대신 그 시각까지 기다린다. 구독 사용량 한도는
            # 몇 시간 단위라 지수 백오프로는 절대 못 맞춘다(그게 밤중 AUTO_STOP 의 원인이었다).
            $rl = Get-RateLimitInfoFromLog $logFile
            $resetAt = 0
            if ($rl.Found -and $rl.ResetsAt -gt 0) { $resetAt = $rl.ResetsAt }
            if ($resetAt -le 0) { $resetAt = Get-RateLimitResetFromText ($errText + " " + $outTail) }
            $now = Get-UnixNow
            if ($resetAt -gt $now) {
                $waited = [int][Math]::Min($RateLimitMaxWaitSeconds, ($resetAt - $now) + 20)
                Write-RunnerLog ("사용량 한도 — CLI 가 알려준 reset 시각까지 기다린다: type=$($rl.Type) utilization=$($rl.Utilization) " +
                    "resetsAt=$resetAt → $(Format-Duration $waited) 대기")
            } else {
                $waited = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveRateLimitHits) `
                    -BaseSeconds $RateLimitBaseBackoffSeconds -MaxSeconds $RateLimitMaxBackoffSeconds
                Write-RunnerLog "rate-limit/overload 로 보이지만 reset 시각을 알 수 없다 — $(Format-Duration $waited) 지수 백오프."
            }
        } elseif ($fc.Class -eq "network") {
            $waited = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveInfraRetries) `
                -BaseSeconds $NetworkBaseBackoffSeconds -MaxSeconds $NetworkMaxBackoffSeconds
            Write-RunnerLog "일시적 네트워크 장애 — $(Format-Duration $waited) 뒤 같은 작업을 그대로 재시도한다."
        } elseif ($fc.Class -eq "resume-failure") {
            $waited = 0        # 세션만 회전하면 되므로 기다릴 이유가 없다
        } elseif ($fc.Class -eq "auth") {
            Write-Banner @(
                "인증/자격증명 문제로 Worker 가 실패했습니다 — 기다려도 저절로 낫지 않습니다.",
                "  $($errText.Trim() -replace '\s+', ' ')",
                "`claude auth` 상태를 확인하세요. 같은 실패가 $MaxIdenticalFailures 회 반복되면 자동 중단합니다."
            )
            $waited = 60
        } elseif ((Get-IntOr $state.consecutiveFailures) -gt 0) {
            # ★ 예전엔 일반 실패에 대기가 **전혀 없었다.** 네트워크가 10초만 끊겨도 즉시 재시도 →
            #   즉시 실패가 3연속으로 쌓여 **3초 만에 AUTO_STOP** 되고 밤샘 실행이 끝났다.
            $waited = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveFailures) `
                -BaseSeconds $FailureBaseBackoffSeconds -MaxSeconds $FailureMaxBackoffSeconds
            Write-RunnerLog "일반 실패 $($state.consecutiveFailures)회 연속(진척 없음, class=$($fc.Class)) — $(Format-Duration $waited) 대기 후 재시도(순간 장애를 넘기기 위한 간격)."
        }
        if ($waited -gt 0) {
            if (-not (Start-InterruptibleSleep -Seconds $waited -StopFile $StopFile -LogPath $RunnerLog -Reason $fc.Class)) {
                $script:FinalExit = 3
                $backoffSw.Stop(); $postSw.Stop(); $loopSw.Stop()
                break
            }
        }
        $backoffSw.Stop()
        $postSw.Stop()
        $loopSw.Stop()

        [void](Write-TimingRecord -Path $TimingLog -Fields ([ordered]@{
            at             = (Get-Date -Format o)
            runner         = "autonomous"
            invocation     = $iterationsThisLaunch
            mode           = $mode
            model          = $useModel
            effort         = $useEffort
            effortSource   = $effortSource
            exitCode       = $exitCode
            failureClass   = $fc.Class
            commits        = $newCommits
            turns          = $stats.NumTurns
            costUsd        = $stats.CostUsd
            toolUses       = $outcome.ToolUses
            dirtyCheckMs   = [int]$dirtySw.ElapsedMilliseconds
            contextBuildMs = $cache.BuildMs
            promptPrepMs   = [int]$prepSw.ElapsedMilliseconds
            workerStartupMs = $outcome.FirstOutputMs
            workerRunMs    = [int]$workerSw.ElapsedMilliseconds
            postCheckMs    = [int]$postSw.ElapsedMilliseconds
            backoffMs      = [int]$backoffSw.ElapsedMilliseconds
            totalMs        = [int]$loopSw.ElapsedMilliseconds
        }))

        if (-not $completeMarkerPresent) {
            Write-RunnerLog "PROJECT_COMPLETE 없음 — 대기 없이 곧바로 다음 Worker invocation 을 시작한다(exit=$exitCode 는 종료 조건이 아니다)."
        }
        # 성공했거나 진척이 있었으면 sleep 없이 곧장 다음 반복으로 — 이것이 이 설계의 핵심이다.
    }
    exit $script:FinalExit
} finally {
    Restore-EnvSnapshot $script:EnvSnapshot
    Close-ExclusiveLock -Lock $lock -LockFile $LockFile
    # Ctrl+C 로 중단해도 여기까지 오고 exit 코드는 0 이다 — 로그만 보고 "완료"로 오해하지 않도록
    # 완료 marker 유효 여부를 같은 줄에 남긴다.
    Write-RunnerLog "Supervisor 종료 PID=$PID (invocations=$iterationsThisLaunch) exit=$script:FinalExit PROJECT_COMPLETE=$(Test-MarkerValid $CompleteFile)"
}
