<#
.SYNOPSIS
  PHASE 1(Audit) → PHASE 2(구현)를 한 번의 수동 시작으로 끝까지 이어 가는 바깥 루프.

.DESCRIPTION
  두 Supervisor 는 각자 자기 Phase 안에서는 멈추지 않지만, **Phase 경계와 AUTO_STOP 에서는
  사람이 다시 시작해 줘야** 했다. "볼 게 없을 때까지 계속 돌리고 싶다"는 목적에는 그 두 지점이
  구멍이다. 이 스크립트가 그 둘만 메운다.

    Audit 완료(exit 0) ──▶ 구현 시작 ──▶ PROJECT_COMPLETE(exit 0) ──▶ 끝
           │                    │
           └── AUTO_STOP(6) ────┴──▶ 잠깐 기다렸다가 같은 Phase 재시작 (상한까지)

  **의미가 바뀌는 지점이 하나 있으니 알고 쓰세요.** 원래 `AUTO_STOP` 은 "사람이 원인을 보고
  직접 다시 시작하는 것"을 확인 절차로 삼는 장치다. 이 스크립트는 그 재시작을 자동화한다 —
  대신 ① 횟수 상한(`-MaxRestarts`) ② 재시작 간격(`-RestartWaitMinutes`) ③ 매 재시작마다 큰
  경고 출력으로 제한한다. 두 Runner 를 직접 실행하면 원래 의미 그대로다.

  자동 재시작하지 **않는** 종료(사람이 봐야 하는 것):
    3 = 사용자 STOP        4 = 다른 Supervisor 가 잠금 보유
    5 = AUDIT_BLOCKED      7 = 전제조건 실패

  실행:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\runner\run_all.ps1
    ... -AuditOnly          # PHASE 1 만
    ... -ImplementOnly      # PHASE 2 만
    ... -MaxRestarts 0      # AUTO_STOP 자동 재시작 끄기(원래 의미 그대로)
#>

param(
    [string]$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant",
    [string]$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe",
    [switch]$AuditOnly,
    [switch]$ImplementOnly,
    [int]$MaxRestarts = 5,
    [double]$RestartWaitMinutes = 10,
    # 두 Runner 에 그대로 전달할 추가 인자(예: -Model sonnet)
    [string[]]$AuditArgs = @(),
    [string[]]$ImplementArgs = @()
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runner_common.ps1")

$AuditScript      = Join-Path $PSScriptRoot "product_audit_runner.ps1"
$AutonomousScript = Join-Path $PSScriptRoot "autonomous_runner.ps1"
$ChainLog         = Join-Path $ProjectDir "var\runner\run_all.log"

function Write-ChainLog([string]$m) { Write-LogLine $ChainLog $m }

# 자동 재시작해도 되는 종료 코드는 AUTO_STOP 하나뿐이다. 나머지는 사람이 봐야 한다.
$RestartableExit = 6

function Invoke-Phase([string]$name, [string]$script, [string[]]$extraArgs) {
    $psHost = (Get-Process -Id $PID).Path
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script,
           "-ProjectDir", $ProjectDir, "-ClaudeExe", $ClaudeExe)
    if ($extraArgs) { $a += $extraArgs }
    Write-ChainLog "$name 시작: $script"
    # ★ `| Out-Host` 가 없으면 자식의 **모든 콘솔 출력이 이 함수의 반환값에 섞인다** — 그러면
    #   호출부의 $auditCode 가 배열이 되어 `-ne 0` 이 항상 참이 되고, 정상 완료(exit 0)를
    #   실패로 오판해 구현 단계로 넘어가지 않는다(controlled test T48 이 실제로 잡았다).
    #   Out-Host 는 화면 출력은 그대로 두면서 파이프라인 출력만 만들지 않는다.
    & $psHost @a | Out-Host
    $code = $LASTEXITCODE
    Write-ChainLog "$name 종료 exit=$code"
    return $code
}

function Invoke-PhaseWithRestarts([string]$name, [string]$script, [string[]]$extraArgs) {
    $restarts = 0
    while ($true) {
        $code = Invoke-Phase $name $script $extraArgs
        if ($code -ne $RestartableExit) { return $code }

        if ($restarts -ge $MaxRestarts) {
            Write-Banner @(
                "$name 이 AUTO_STOP 으로 멈췄고 자동 재시작 상한($MaxRestarts 회)에 도달했습니다.",
                "원인을 확인하세요: var\runner\logs\ 또는 var\product-audit\logs\",
                "고친 뒤 같은 명령으로 다시 실행하면 됩니다."
            )
            Write-ChainLog "$name AUTO_STOP — 재시작 상한 $MaxRestarts 도달, 중단."
            return $code
        }

        $restarts += 1
        $waitSec = [int][Math]::Max(1, $RestartWaitMinutes * 60)
        Write-Banner @(
            "$name 이 연속 실패로 AUTO_STOP 했습니다 — $([int]$RestartWaitMinutes)분 뒤 자동 재시작합니다($restarts/$MaxRestarts).",
            "원래 AUTO_STOP 은 사람이 원인을 보고 재시작하라는 신호입니다. 이 자동 재시작은",
            "run_all.ps1 이 '밤새 계속 돌린다'는 목적으로 제한적으로 대신하는 것입니다.",
            "정말로 멈추려면 var\runner\STOP 또는 var\product-audit\STOP 파일을 만드세요."
        )
        Write-ChainLog "$name AUTO_STOP — ${waitSec}초 뒤 자동 재시작($restarts/$MaxRestarts)."
        Start-Sleep -Seconds $waitSec
    }
}

Write-ChainLog "run_all 시작 PID=$PID auditOnly=$AuditOnly implementOnly=$ImplementOnly maxRestarts=$MaxRestarts"

$auditCode = 0
if (-not $ImplementOnly) {
    $auditCode = Invoke-PhaseWithRestarts "PHASE 1 (Product Audit)" $AuditScript $AuditArgs
    if ($auditCode -ne 0) {
        Write-Banner @(
            "PHASE 1 이 exit=$auditCode 로 끝나 여기서 멈춥니다(사람이 봐야 하는 상태).",
            "  3=사용자 STOP · 4=다른 Supervisor 가 잠금 보유 · 5=AUDIT_BLOCKED · 6=AUTO_STOP · 7=전제조건",
            "구현 단계로 넘어가지 않습니다 — Audit 결과가 확정되지 않았기 때문입니다."
        )
        Write-ChainLog "run_all 종료: PHASE 1 exit=$auditCode"
        exit $auditCode
    }
    Write-Banner @("PHASE 1 (Product Audit) 완료 — 기계 Gate 통과. PHASE 2(구현)로 넘어갑니다.")
}

if ($AuditOnly) {
    Write-ChainLog "run_all 종료: -AuditOnly 지정, PHASE 1 만 수행하고 정상 종료."
    exit 0
}

$implCode = Invoke-PhaseWithRestarts "PHASE 2 (구현)" $AutonomousScript $ImplementArgs
if ($implCode -eq 0) {
    Write-Banner @(
        "PHASE 2 완료 — PROJECT_COMPLETE 가 기계 Gate 를 통과했습니다.",
        "근거: var\runner\PROJECT_COMPLETE"
    )
} else {
    Write-Banner @(
        "PHASE 2 가 exit=$implCode 로 끝났습니다(사람이 봐야 하는 상태).",
        "  3=사용자 STOP · 4=잠금 · 6=AUTO_STOP · 7=전제조건"
    )
}
Write-ChainLog "run_all 종료: PHASE 2 exit=$implCode"
exit $implCode
