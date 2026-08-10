<#
.SYNOPSIS
  ClovirAssist 자율 Runner를 Windows 작업 스케줄러에 등록/제거한다.

.DESCRIPTION
  2026-08-11 재설계: autonomous_runner.ps1 자체가 이제 연속 while 루프다(반복 사이에 sleep
  없음, 완료/STOP/연속실패 상한에 걸릴 때까지 계속 돈다). 그래서 작업 스케줄러는 더 이상
  "언제 일할지"를 정하는 페이서가 아니라 **감시자(supervisor)** 다 — 15분마다 확인해서,
  루프가 이미 살아있으면(잠금 파일) 그 즉시 아무 것도 안 하고 끝나는 공짜 heartbeat이고,
  루프가 죽어 있으면(크래시·재부팅) 새 루프를 다시 띄운다. 즉 정상 상태에서는 96번의
  heartbeat 중 거의 전부가 no-op이고, 루프가 죽었을 때만 실제로 재시작이 일어난다 — 최악의
  경우에도 재시작까지 15분을 넘지 않는다.

  로그온한 사용자 계정으로만 실행되고(비밀번호를 작업 스케줄러에 저장하지 않는다 —
  로그아웃/재부팅 중에는 안 돈다는 뜻이다, 그게 더 안전한 기본값이다), 최소 권한
  (/RL LIMITED)으로 등록한다.

.PARAMETER Uninstall
  등록된 작업을 완전히 제거한다. 이미 돌고 있는 루프 프로세스가 있으면 그것도 같이 멈춘다
  (중지 수단 — STOP 파일보다 강하다: 아예 다시 안 뜬다).

.EXAMPLE
  .\install_task.ps1
  .\install_task.ps1 -Uninstall
#>
param(
    [switch]$Uninstall
)

$TaskName = "ClovirAssistAutonomousRunner"
$ScriptPath = Join-Path $PSScriptRoot "autonomous_runner.ps1"
$LockFile = Join-Path $PSScriptRoot "..\..\var\runner\run.lock"
# 반드시 pwsh(PowerShell 7+)를 쓴다 — 이름만 "powershell"인 구버전(5.1)은 BOM 없는 스크립트를
# 시스템 코드페이지(CP949 등)로 읽어 한글 문자열이 실행 시점에 이미 깨진다(직접 확인함:
# powershell.exe로 이 스크립트를 실행했더니 로그의 모든 한글이 mojibake로 남았다).
$PwshExe = "C:\Program Files\PowerShell\7\pwsh.exe"
if (-not (Test-Path $PwshExe)) {
    throw "pwsh.exe(PowerShell 7+)를 못 찾았습니다: $PwshExe — 설치돼 있는지 확인하세요."
}

if ($Uninstall) {
    schtasks /Delete /TN $TaskName /F
    if (Test-Path $LockFile) {
        $runningPid = (Get-Content $LockFile -Raw).Trim()
        if ($runningPid -match '^\d+$') {
            Stop-Process -Id ([int]$runningPid) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
    }
    Write-Output "제거됨: $TaskName (돌고 있던 루프도 함께 중지)"
    exit 0
}

$Action = "`"$PwshExe`" -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# MINUTE/MO 15 — 실제 작업 주기가 아니라 "루프가 살아있는지" 확인 주기다. 정상 상태에서는
# autonomous_runner.ps1 시작부의 잠금 파일 검사가 즉시 종료시키므로 비용이 거의 0이다.
schtasks /Create /TN $TaskName /TR $Action /SC MINUTE /MO 15 /RL LIMITED /F

Write-Output "등록됨: $TaskName (15분마다 감시 — 루프가 살아있으면 즉시 no-op, 죽어 있으면 재시작)"
Write-Output "확인: schtasks /Query /TN $TaskName /V /FO LIST"
Write-Output "즉시 루프 시작: schtasks /Run /TN $TaskName"
Write-Output "루프 살아있는지 확인: var\runner\run.lock의 PID가 살아있는 프로세스인지"
Write-Output "중지(임시, 지금 반복이 끝나는 대로): var\runner\STOP 파일을 만든다"
Write-Output "중지(즉시+영구): .\install_task.ps1 -Uninstall"
