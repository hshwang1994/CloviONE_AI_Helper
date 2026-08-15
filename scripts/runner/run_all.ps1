<#
.SYNOPSIS
  ClovirAssist 완전 자율 상태 머신 — Audit → 구현 → 재감사를 수렴할 때까지 스스로 돈다.

.DESCRIPTION
  사용자가 **한 번** 시작하면 `PROJECT_COMPLETE` 가 기계 Gate 를 통과하고 재감사에서 새 Root
  Cause 가 안 나올 때까지 사람 개입 없이 계속 돈다. 사람이 다시 실행해야 다음 단계로 넘어가는
  구조는 전부 제거했다(D-74).

  ── 상태 전이 ────────────────────────────────────────────────────────────────

      ┌─────────────────────────────────────────────────────────────┐
      │                                                             │
      ▼                                                             │
    AUDIT ──(IMPLEMENTATION_REQUIRED=true)──▶ IMPLEMENT ──▶ VERIFY(재감사)
      │                                           │              │
      │                                    (PROJECT_COMPLETE)    │
      │                                                          │
      └──(구현할 것 없음 & PROJECT_COMPLETE 유효)──▶ CONVERGED ───┘
                                                        ▲
                                        (재감사에서 새 Root Cause 0건)

  - AUDIT 이 구현거리를 내놓으면 자동으로 IMPLEMENT 로 간다.
  - IMPLEMENT 가 PROJECT_COMPLETE 를 만들면 **거기서 끝내지 않고** 새 Audit Cycle 을 돌려
    (`-ResetAudit`) 정말 수렴했는지 독립 검증한다. 새 Root Cause 가 나오면 다시 IMPLEMENT.
  - 어느 Phase 든 marker 없이 끝나면(중단·상한 도달) **사람을 기다리지 않고 그 Phase 를 다시**
    시작한다. 예전에는 여기서 exit 10 으로 끝나고 사람이 다시 눌러야 했다.
  - AUTO_STOP(6) 도, AUDIT_BLOCKED(5) 도 자동 복구 대상이다. 각각 상한이 있고, 상한을 넘으면
    그때만 사람이 볼 상태로 끝난다.

  ── 무한 반복은 어떻게 막나 ──────────────────────────────────────────────────
  단순 재시도를 무한히 하지 않는다. 같은 실패가 반복되면 **전략을 바꾼다.**
    1회차 재시도 → 그대로
    2회차       → (각 Runner 안에서) Worker Session 회전 · 실패 유형별 백오프
    3회차 이후  → Audit 이면 새 Cycle(`-ResetAudit`)로 관점 자체를 바꿈,
                  BLOCKED 였으면 `-ResumeBlocked` 로 격리하고 다른 전략 지시를 되먹임
    상한 초과   → 수렴(사람이 볼 상태). 같은 지문이 계속 나온다 = 진짜 결정적 실패다.
  전체 Cycle 수와 전체 실행 시간에도 상한이 있다.

  ── 사람이 개입해야 끝나는 유일한 경우 ──────────────────────────────────────
    3 = 사용자 STOP (사용자만 만든다)      7 = 전제조건 실패 (claude 없음/저장소 아님)
  그 외에는 전부 자동으로 회복하거나, 상한까지 시도한 뒤 증거를 남기고 수렴한다.

  ── 종료 코드 ────────────────────────────────────────────────────────────────
    0 = 수렴 완료(또는 -AuditOnly/-ImplementOnly 정상 종료)   3 = 사용자 STOP
    5 = Audit 이 수렴하지 못함      6 = 구현이 수렴하지 못함   7 = 전제조건 실패
    8 = 전체 실행 시간 상한         9 = Cycle 상한(수렴 실패)

  실행:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\runner\run_all.ps1
    ... -AuditOnly            # PHASE 1 만
    ... -ImplementOnly        # PHASE 2 만
    ... -SkipVerifyAudit      # 완료 후 재감사 검증을 건너뛴다(권장하지 않음)
    ... -MaxCycles 8          # Audit↔구현 왕복 상한
#>

param(
    [string]$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant",
    [string]$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe",
    [switch]$AuditOnly,
    [switch]$ImplementOnly,

    # Audit ↔ 구현 왕복 상한. 수렴하면 그 전에 끝난다. 0 = 무제한(권장하지 않음).
    [int]$MaxCycles = 12,
    # 한 Phase 가 marker 없이 끝났을 때 같은 Phase 를 다시 시도하는 상한(전략을 바꿔 가며).
    [int]$MaxPhaseRetries = 6,
    # 재시도 사이 간격. 각 Runner 안에 실패 유형별 백오프가 따로 있으므로 여기선 숨 고르기만.
    [double]$RetryWaitMinutes = 2,
    # 전체 실행 상한(시간). 0 = 무제한. 밤샘 실행을 상정한 값이다.
    [double]$MaxTotalHours = 0,

    # 구현이 PROJECT_COMPLETE 를 만든 뒤 **새 Audit Cycle 로 독립 검증**한다. 끄지 마라 —
    # 이게 "재감사에서 새 문제가 나오면 다시 구현" 을 만드는 장치다.
    [switch]$SkipVerifyAudit,
    # 검증 재감사가 새 구현거리를 내놓지 않은 상태가 이만큼 연속되면 수렴으로 본다.
    [int]$RequiredCleanVerifications = 1,

    # 두 Runner 에 그대로 전달할 추가 인자(예: -Model sonnet)
    [string[]]$AuditArgs = @(),
    [string[]]$ImplementArgs = @()
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runner_common.ps1")

$AuditScript      = Join-Path $PSScriptRoot "product_audit_runner.ps1"
$AutonomousScript = Join-Path $PSScriptRoot "autonomous_runner.ps1"
$ChainLog         = Join-Path $ProjectDir "var\runner\run_all.log"
$ChainStateFile   = Join-Path $ProjectDir "var\runner\run_all_state.json"

$AuditCompleteFile   = Join-Path $ProjectDir "var\product-audit\AUDIT_COMPLETE"
$AuditBlockedFile    = Join-Path $ProjectDir "var\product-audit\AUDIT_BLOCKED"
$ImplRequiredFile    = Join-Path $ProjectDir "var\product-audit\IMPLEMENTATION_REQUIRED"
$ProjectCompleteFile = Join-Path $ProjectDir "var\runner\PROJECT_COMPLETE"
$UserStopFiles       = @((Join-Path $ProjectDir "var\runner\STOP"),
                         (Join-Path $ProjectDir "var\product-audit\STOP"))

function Write-ChainLog([string]$m) { Write-LogLine $ChainLog $m }

# 사람이 개입해야만 하는 종료 코드. 이 둘 말고는 전부 자동 복구를 시도한다.
#   3 = 사용자 STOP(사용자만 만든다)   7 = 전제조건 실패(claude 없음 / git 저장소 아님)
$TerminalExitCodes = @(3, 7)

function Test-UserStop {
    foreach ($f in $UserStopFiles) { if (Test-Path -LiteralPath $f) { return $true } }
    return $false
}

function Invoke-Phase {
    param([string]$Name, [string]$Script, [string[]]$ExtraArgs)
    $psHost = (Get-Process -Id $PID).Path
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script,
           "-ProjectDir", $ProjectDir, "-ClaudeExe", $ClaudeExe)
    if ($ExtraArgs) { $a += $ExtraArgs }
    Write-ChainLog "$Name 시작: $Script $($ExtraArgs -join ' ')"
    # ★ `| Out-Host` 가 없으면 자식의 **모든 콘솔 출력이 이 함수의 반환값에 섞인다** — 그러면
    #   호출부의 코드 비교가 배열 비교가 되어 정상 완료(exit 0)를 실패로 오판한다
    #   (controlled test T48 이 실제로 잡았다). Out-Host 는 화면 출력은 그대로 두면서
    #   파이프라인 출력만 만들지 않는다.
    & $psHost @a | Out-Host
    $code = $LASTEXITCODE
    Write-ChainLog "$Name 종료 exit=$code"
    return $code
}

function Get-RecoveryArgs {
    <#  같은 Phase 를 다시 돌릴 때 **전략을 바꾼다.** 똑같은 명령을 무한 재시도하지 않는다.
        attempt 가 올라갈수록 개입 강도를 높인다. #>
    param([string]$Phase, [int]$Attempt)
    $extra = @()
    if ($Phase -eq "audit") {
        # AUDIT_BLOCKED 였다면 격리하고 이어서 간다(Runner 안에도 자동 복구가 있지만,
        # 바깥에서 한 번 더 확실히 풀어 준다 — 사람이 -ResumeBlocked 를 칠 일이 없어야 한다).
        if (Test-Path -LiteralPath $AuditBlockedFile) { $extra += "-ResumeBlocked" }
        # 3회 이상 같은 자리에서 막히면 관점 자체를 바꾼다 — 새 Cycle 로 다시 본다.
        if ($Attempt -ge 3) { $extra += "-ResetAudit" }
    }
    return $extra
}

function Save-ChainState {
    param([int]$Cycle, [string]$Phase, [string]$Note)
    [void](Write-TextFile $ChainStateFile (([pscustomobject]@{
        updatedAt = (Get-Date -Format o)
        cycle     = $Cycle
        phase     = $Phase
        note      = $Note
        pid       = $PID
    }) | ConvertTo-Json -Depth 3))
}

function Invoke-PhaseUntilMarker {
    <#  한 Phase 를 **완료 marker 가 생길 때까지** 돌린다.

        예전 구조의 Human Gate: marker 없이 exit 0 으로 끝나면(Ctrl+C·상한 도달) exit 10 으로
        전체를 끝내고 "같은 명령을 다시 실행하세요" 라고 안내했다. 그 재실행이 사람 손이었다.
        이제는 전략을 바꿔 가며 스스로 다시 돌린다.

        돌려주는 값: @{ Ok=<bool>; Code=<int>; Reason=<string> } #>
    param([string]$Name, [string]$Phase, [string]$Script, [string]$MarkerFile, [string[]]$BaseArgs)

    for ($attempt = 1; $attempt -le [Math]::Max(1, $MaxPhaseRetries); $attempt++) {
        if (Test-UserStop) { return @{ Ok = $false; Code = 3; Reason = "user-stop" } }

        $recovery = @(Get-RecoveryArgs -Phase $Phase -Attempt $attempt)
        $extra = @($BaseArgs) + $recovery
        if ($attempt -gt 1) {
            Write-Banner @(
                "$Name 를 다시 시도합니다($attempt/$MaxPhaseRetries) — 사람을 기다리지 않습니다.",
                "  전략: $(if ($recovery.Count -gt 0) { $recovery -join ' ' } else { '동일 인자로 재시도(Runner 내부에서 session 회전/백오프가 동작한다)' })",
                "  직전 회차가 완료 marker 를 만들지 못했거나 자동 정지했습니다."
            )
        }
        $code = Invoke-Phase -Name $Name -Script $Script -ExtraArgs $extra

        if ($TerminalExitCodes -contains $code) {
            return @{ Ok = $false; Code = $code; Reason = "terminal-exit" }
        }
        if (Test-MarkerValid $MarkerFile) {
            return @{ Ok = $true; Code = $code; Reason = "marker-valid" }
        }

        # marker 가 없다 = 아직 안 끝났다. exit 0(상한 도달/중단)·5(BLOCKED)·6(AUTO_STOP)
        # 전부 여기로 온다. 사람에게 넘기지 않고 전략을 바꿔 다시 돈다.
        Write-ChainLog "$Name exit=$code 이지만 $(Split-Path -Leaf $MarkerFile) 가 없다 — 자동 재시도($attempt/$MaxPhaseRetries)."
        if ($attempt -lt $MaxPhaseRetries) {
            $waitSec = [int][Math]::Max(1, $RetryWaitMinutes * 60)
            if (-not (Start-InterruptibleSleep -Seconds $waitSec -StopFile $UserStopFiles[0] -LogPath $ChainLog -Reason "$Name 재시도 대기")) {
                return @{ Ok = $false; Code = 3; Reason = "user-stop" }
            }
        }
    }
    return @{ Ok = $false; Code = 6; Reason = "phase-retries-exhausted" }
}

function Add-ResetAudit([string[]]$argsIn) {
    return @(@($argsIn | Where-Object { $_ -ne "-ResetAudit" }) + @("-ResetAudit"))
}

# ══════════════════════════════════════════════════════════════════════════════
$startedAt = Get-Date
Write-ChainLog ("run_all 시작 PID=$PID auditOnly=$AuditOnly implementOnly=$ImplementOnly " +
    "maxCycles=$MaxCycles maxPhaseRetries=$MaxPhaseRetries verifyAudit=$(-not $SkipVerifyAudit)")

Write-Banner @(
    "ClovirAssist 완전 자율 상태 머신을 시작합니다.",
    "  Audit → 구현 → 재감사 를 수렴할 때까지 반복합니다. 사람이 다시 실행할 필요가 없습니다.",
    "  멈추려면: var\runner\STOP 또는 var\product-audit\STOP 파일을 만드세요."
)

$cycle = 0
$cleanVerifications = 0
$finalExit = 0
$finalNote = ""

try {
    while ($true) {
        if (Test-UserStop) {
            Write-Banner @("사용자 STOP 파일을 발견해 종료합니다.")
            Write-ChainLog "사용자 STOP — run_all 종료."
            $finalExit = 3; $finalNote = "user-stop"; break
        }
        if ($MaxTotalHours -gt 0 -and ((Get-Date) - $startedAt).TotalHours -ge $MaxTotalHours) {
            Write-Banner @("전체 실행 상한 $MaxTotalHours 시간에 도달해 종료합니다(완료 아님).")
            Write-ChainLog "전체 실행 시간 상한 도달 — 종료."
            $finalExit = 8; $finalNote = "time-limit"; break
        }
        $cycle += 1
        if ($MaxCycles -gt 0 -and $cycle -gt $MaxCycles) {
            Write-Banner @(
                "Audit↔구현 왕복이 $MaxCycles Cycle 에 도달했습니다 — 수렴하지 않아 종료합니다.",
                "완료가 아닙니다. var\runner\run_all.log 와 각 Phase 로그를 확인하세요."
            )
            Write-ChainLog "Cycle 상한 $MaxCycles 도달 — 종료(수렴 실패)."
            $finalExit = 9; $finalNote = "cycle-limit"; break
        }

        # ASCII 로 쓴다 — 콘솔/파이프 인코딩(cp949)에서 박스 문자는 깨져서 로그 대조가 안 된다.
        Write-Banner @("=== CYCLE $cycle$(if ($MaxCycles -gt 0) { "/$MaxCycles" } else { '' }) ===")

        # ── PHASE 1: Product Audit ────────────────────────────────────────────
        if (-not $ImplementOnly) {
            Save-ChainState -Cycle $cycle -Phase "audit" -Note "running"
            $r = Invoke-PhaseUntilMarker -Name "PHASE 1 (Product Audit)" -Phase "audit" `
                -Script $AuditScript -MarkerFile $AuditCompleteFile -BaseArgs $AuditArgs
            if (-not $r.Ok) {
                if ($r.Code -eq 3) { $finalExit = 3; $finalNote = "user-stop"; break }
                Write-Banner @(
                    "PHASE 1 이 재시도 상한까지 완료 marker 를 만들지 못했습니다(exit=$($r.Code), $($r.Reason)).",
                    "  Audit 이 수렴하지 못하는 상태입니다 — var\product-audit\logs\ 를 확인하세요."
                )
                Write-ChainLog "run_all 종료: PHASE 1 수렴 실패 ($($r.Reason), exit=$($r.Code))"
                $finalExit = $(if ($TerminalExitCodes -contains $r.Code) { $r.Code } else { 5 })
                $finalNote = "audit-not-converged"; break
            }
            Write-Banner @("PHASE 1 (Product Audit) 완료 — 기계 Gate 통과.")
        }
        if ($AuditOnly) {
            Write-ChainLog "run_all 종료: -AuditOnly 지정, PHASE 1 만 수행하고 정상 종료."
            $finalExit = 0; $finalNote = "audit-only"; break
        }

        # ── 구현할 것이 있는가 ────────────────────────────────────────────────
        $implRequired = Test-MarkerValid $ImplRequiredFile
        if (-not $implRequired) {
            # Audit 이 "구현할 것 없음" 이라고 판정했다. 그럼 이미 완료 상태여야 한다.
            if (Test-MarkerValid $ProjectCompleteFile) {
                $cleanVerifications += 1
                Write-Banner @(
                    "Audit 이 새 구현 Root Cause 를 내놓지 않았고 PROJECT_COMPLETE 도 유효합니다.",
                    "  깨끗한 검증 $cleanVerifications/$RequiredCleanVerifications 회"
                )
                Write-ChainLog "clean verification $cleanVerifications/$RequiredCleanVerifications"
                if ($cleanVerifications -ge $RequiredCleanVerifications) {
                    $finalExit = 0; $finalNote = "converged"; break
                }
                Write-ChainLog "추가 검증을 위해 새 Audit Cycle 을 시작한다."
                $AuditArgs = Add-ResetAudit $AuditArgs
                continue
            }
            # 구현거리는 없다는데 완료 marker 도 없다 → 구현 Phase 가 완료 근거를 만들어야 한다.
            Write-ChainLog "IMPLEMENTATION_REQUIRED 없음 + PROJECT_COMPLETE 없음 — 구현 Phase 로 완료 근거를 만들게 한다."
        } else {
            Write-Banner @("Audit 이 구현 계약을 넘겼습니다 — PHASE 2(구현)로 넘어갑니다.")
        }

        # ── PHASE 2: 구현 ─────────────────────────────────────────────────────
        Save-ChainState -Cycle $cycle -Phase "implement" -Note "running"
        $ri = Invoke-PhaseUntilMarker -Name "PHASE 2 (구현)" -Phase "implement" `
            -Script $AutonomousScript -MarkerFile $ProjectCompleteFile -BaseArgs $ImplementArgs
        if (-not $ri.Ok) {
            if ($ri.Code -eq 3) { $finalExit = 3; $finalNote = "user-stop"; break }
            Write-Banner @(
                "PHASE 2 가 재시도 상한까지 PROJECT_COMPLETE 를 만들지 못했습니다(exit=$($ri.Code), $($ri.Reason)).",
                "  var\runner\logs\ 와 var\runner\last_completion_rejection.txt 를 확인하세요."
            )
            Write-ChainLog "run_all 종료: PHASE 2 수렴 실패 ($($ri.Reason), exit=$($ri.Code))"
            $finalExit = $(if ($TerminalExitCodes -contains $ri.Code) { $ri.Code } else { 6 })
            $finalNote = "implement-not-converged"; break
        }
        Write-Banner @("PHASE 2 완료 — PROJECT_COMPLETE 가 기계 Gate 를 통과했습니다.")

        if ($ImplementOnly) {
            Write-ChainLog "run_all 종료: -ImplementOnly 지정, PHASE 2 만 수행하고 정상 종료."
            $finalExit = 0; $finalNote = "implement-only"; break
        }
        if ($SkipVerifyAudit) {
            Write-ChainLog "run_all 종료: -SkipVerifyAudit 지정 — 재감사 없이 종료."
            $finalExit = 0; $finalNote = "completed-without-verify"; break
        }

        # ── PHASE 3: 검증 재감사 ──────────────────────────────────────────────
        # 여기가 예전 구조에 **아예 없던 단계**다. 구현이 스스로 "끝났다"고 한 것을 독립적인
        # 새 Audit Cycle 로 다시 본다. 새 Root Cause 가 나오면 다음 Cycle 이 다시 구현한다.
        Write-Banner @(
            "PHASE 3 — 구현이 정말 수렴했는지 **새 Audit Cycle** 로 독립 검증합니다.",
            "  여기서 새 Root Cause 가 나오면 자동으로 다시 구현 Phase 로 돌아갑니다."
        )
        Write-ChainLog "검증 재감사 시작(새 Cycle)."
        Save-ChainState -Cycle $cycle -Phase "verify-audit" -Note "running"
        $AuditArgs = Add-ResetAudit $AuditArgs
        # 다음 루프 반복이 PHASE 1 을 새 Cycle 로 돌린다. 그 결과에 따라 구현으로 되돌아가거나
        # clean verification 으로 수렴한다.
    }
} finally {
    $elapsed = ((Get-Date) - $startedAt)
    Save-ChainState -Cycle $cycle -Phase "finished" -Note $finalNote
    Write-ChainLog ("run_all 종료 exit=$finalExit note=$finalNote cycles=$cycle " +
        "elapsed=$(Format-Duration $elapsed.TotalSeconds) " +
        "AUDIT_COMPLETE=$(Test-MarkerValid $AuditCompleteFile) " +
        "PROJECT_COMPLETE=$(Test-MarkerValid $ProjectCompleteFile)")
}

if ($finalExit -eq 0 -and $finalNote -eq "converged") {
    Write-Banner @(
        "전체 수렴 완료 — Audit 이 새 Root Cause 를 내놓지 않고 PROJECT_COMPLETE 가 유효합니다.",
        "  Cycle $cycle 회 · 경과 $(Format-Duration ((Get-Date) - $startedAt).TotalSeconds)",
        "  근거: var\runner\PROJECT_COMPLETE · var\product-audit\AUDIT_COMPLETE"
    )
}
exit $finalExit
