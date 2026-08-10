<#
.SYNOPSIS
  ClovirAssist 자율 Runner를 Windows 작업 스케줄러에 등록/제거한다.

.DESCRIPTION
  3시간마다 autonomous_runner.ps1을 실행하도록 등록한다. 로그온한 사용자 계정으로만 실행되고
  (비밀번호를 작업 스케줄러에 저장하지 않는다 — 로그아웃/재부팅 중에는 안 돈다는 뜻이다, 그게
  더 안전한 기본값이다), 최소 권한(/RL LIMITED)으로 등록한다.

.PARAMETER Uninstall
  등록된 작업을 완전히 제거한다(중지 수단 — STOP 파일보다 강하다: 아예 다시 안 뜬다).

.EXAMPLE
  .\install_task.ps1
  .\install_task.ps1 -Uninstall
#>
param(
    [switch]$Uninstall
)

$TaskName = "ClovirAssistAutonomousRunner"
$ScriptPath = Join-Path $PSScriptRoot "autonomous_runner.ps1"
# 반드시 pwsh(PowerShell 7+)를 쓴다 — 이름만 "powershell"인 구버전(5.1)은 BOM 없는 스크립트를
# 시스템 코드페이지(CP949 등)로 읽어 한글 문자열이 실행 시점에 이미 깨진다(직접 확인함:
# powershell.exe로 이 스크립트를 실행했더니 로그의 모든 한글이 mojibake로 남았다).
$PwshExe = "C:\Program Files\PowerShell\7\pwsh.exe"
if (-not (Test-Path $PwshExe)) {
    throw "pwsh.exe(PowerShell 7+)를 못 찾았습니다: $PwshExe — 설치돼 있는지 확인하세요."
}

if ($Uninstall) {
    schtasks /Delete /TN $TaskName /F
    Write-Output "제거됨: $TaskName"
    exit 0
}

$Action = "`"$PwshExe`" -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

schtasks /Create /TN $TaskName /TR $Action /SC HOURLY /MO 3 /RL LIMITED /F

Write-Output "등록됨: $TaskName (3시간마다, 로그온 중에만 실행)"
Write-Output "확인: schtasks /Query /TN $TaskName /V /FO LIST"
Write-Output "즉시 한 번 실행해서 배선 확인: schtasks /Run /TN $TaskName"
Write-Output "중지(임시): var\runner\STOP 파일을 만든다"
Write-Output "중지(영구): .\install_task.ps1 -Uninstall"
