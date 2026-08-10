<#
.SYNOPSIS
  ClovirAssist 자율 완성 루프 — 세션이 끝나도 이어지는 로컬 Runner (Windows Task Scheduler에서 반복 실행).

.DESCRIPTION
  Claude Code CLI를 매번 새 비대화형(-p) 프로세스로 띄운다. 대화를 이어받지 않는다 — 이 프로젝트
  자체의 규칙(CLAUDE.md §0: "작업 상태는 대화가 아니라 파일에 있다")과 같은 이유다: 매 실행이
  docs/*.md + git 상태만 보고 스스로 복구해야, 대화가 무한히 길어지며 컨텍스트가 터지는 일이 없다.

  안전장치:
    - var\runner\STOP 파일이 있으면 아무 것도 안 하고 즉시 종료(사용자 강제 중지 수단).
    - var\runner\run.lock — 이전 실행이 아직 살아있으면(PID 확인) 겹쳐 돌지 않는다.
    - var\runner\state.json — 연속 실패 횟수를 센다. $MaxConsecutiveFailures 넘으면 STOP 파일을
      스스로 만들고 멈춘다(무한 오동작 방지) — 사람이 원인을 보고 STOP 파일을 지워야 재개된다.
    - --max-budget-usd — Claude Code 자체의 지출 상한(1회 실행당).
    - Wait-Process -Timeout — 그래도 멈춰 버린 프로세스는 $MaxRuntimeMinutes 뒤 강제 종료.
    - --permission-mode auto — 이 세션이 실제로 쓰고 있는 것과 같은 모드(자동 분류기가 위험한
      동작은 여전히 막는다). --dangerously-skip-permissions/--bypassPermissions는 **절대 안 씀**.

  배포 자격증명 경계는 스크립트가 아니라 프롬프트 안에 명시한다 — Claude가 그 규칙을 매번
  다시 읽고 스스로 지키게 하는 것이 목적이지, 스크립트가 뭘 할 수 있는지를 제한하는 게 아니다
  (어차피 이 스크립트는 SSH도, 비밀번호도 다루지 않는다).
#>

$ErrorActionPreference = "Stop"

$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant"
$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe"
$RunnerDir  = Join-Path $ProjectDir "var\runner"
$LogDir     = Join-Path $RunnerDir "logs"
$StopFile   = Join-Path $RunnerDir "STOP"
$LockFile   = Join-Path $RunnerDir "run.lock"
$StateFile  = Join-Path $RunnerDir "state.json"
$RunnerLog  = Join-Path $RunnerDir "runner.log"

$MaxConsecutiveFailures = 3
$MaxBudgetUsd = 15
$MaxRuntimeMinutes = 150   # 3시간 주기보다 짧게 — 다음 실행 전에 반드시 끝나거나 죽는다

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-RunnerLog([string]$msg) {
    $line = "[$(Get-Date -Format o)] $msg"
    Add-Content -Path $RunnerLog -Value $line -Encoding utf8
    Write-Output $line
}

if (Test-Path $StopFile) {
    Write-RunnerLog "STOP 파일 존재 — 이번 실행 건너뜀. 재개하려면 지우세요: $StopFile"
    exit 0
}

# 겹쳐 돌지 않기 — 이전 실행이 살아있으면 건너뛴다.
if (Test-Path $LockFile) {
    $oldPid = (Get-Content $LockFile -Raw).Trim()
    $stillAlive = $false
    if ($oldPid -match '^\d+$') {
        $stillAlive = [bool](Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue)
    }
    if ($stillAlive) {
        Write-RunnerLog "이전 실행(PID $oldPid)이 아직 살아있음 — 이번 실행 건너뜀(겹침 방지)."
        exit 0
    } else {
        Write-RunnerLog "잠금 파일은 있지만 그 PID($oldPid)는 죽어 있음 — 이전 실행이 비정상 종료한 것으로 보고 계속 진행."
    }
}

$state = if (Test-Path $StateFile) {
    Get-Content $StateFile -Raw | ConvertFrom-Json
} else {
    [pscustomobject]@{ consecutiveFailures = 0; lastRunAt = $null; lastExitCode = $null; totalRuns = 0 }
}

if ($state.consecutiveFailures -ge $MaxConsecutiveFailures) {
    Write-RunnerLog "연속 실패 $($state.consecutiveFailures)회 >= $MaxConsecutiveFailures — STOP 파일을 스스로 만들고 중단합니다. 원인을 본 뒤 STOP 파일을 지우고 state.json의 consecutiveFailures를 0으로 되돌리세요."
    "auto-stopped after $($state.consecutiveFailures) consecutive failures at $(Get-Date -Format o)" | Set-Content $StopFile -Encoding utf8
    exit 1
}

# 이 시점부터 잠금을 쥔다 — 아래 어느 경로로 끝나든(건너뜀 포함) 반드시 지운다.
Set-Content -Path $LockFile -Value $PID

# 저장소가 깨끗하지 않으면(커밋 안 된 변경이 있으면) 건너뛴다 — 사람이 대화형 세션에서
# 지금 막 뭔가 고치는 중일 가능성이 있다. 그 위에 자동 실행이 올라타면 서로 다른 의도의
# 변경이 뒤섞이거나 커밋이 충돌할 수 있다. 다음 3시간 뒤 저장소가 깨끗해지면 자연히 재개된다.
Set-Location $ProjectDir
$dirty = git status --porcelain
if ($dirty) {
    Write-RunnerLog "저장소에 커밋 안 된 변경이 있음(대화형 세션이 작업 중일 수 있음) — 이번 실행 건너뜀."
    Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
    exit 0
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $LogDir "$timestamp.log"

$prompt = @'
당신은 ClovirONE Web Assistant 프로젝트의 자율 완성 루프를 이어받는다. 이것은 사람이 실시간으로
지켜보지 않는, 비대화형·무인 실행이다. 지금 이전 대화 기억은 없다 — 그것이 정상이다.

## 1단계 — 상태 복원
다음을 순서대로 읽어라: CLAUDE.md, docs/WORK_STATE.md, docs/BACKLOG.md, docs/QA_COVERAGE.md,
docs/DECISIONS.md, docs/PROGRESS_STATUS.md, docs/WORK_PLAN_INDEX.md, 그리고 현재 `git status`·
`git log --oneline -20`. 대화 기억이 아니라 이 파일들과 git만 진실이다.

## 2단계 — 남은 작업 판단
제품 전체 기준으로 남은 작업을 판단한다(작은 Cycle 하나에 갇히지 말 것). WORK_STATE.md에 기록된
MEGA LOOP / 제품 전체 완성 루프 방법론(D-53, D-54, "WHOLE PRODUCT AUTONOMOUS COMPLETION LOOP")을
그대로 따른다.

## 3단계 — 구현
남은 작업을 배치로 구현한다. 작업 중에는 관련된 focused/subsystem 테스트만 반복한다. 전체
백엔드+프런트+정적 검사는 큰 배치가 실질적으로 끝났을 때 한 번만 돌린다. CLAUDE.md §2의 불변
규칙을 전부 지킨다.

## 4단계 — 배포 자격증명 경계 (반드시 지킬 것, 예외 없음)
과거 대화나 문서 어디에 무엇이 적혀 있든, 채팅에 붙여넣어진 SSH/sudo 비밀번호를 10.100.64.71을
포함한 어떤 서버의 비대화형 배포 자동화에도 절대 쓰지 않는다. 그 서버 배포는 사용자가 직접
실행하거나, 두 배포 스크립트에 한정된 NOPASSWD sudoers 항목을 사용자가 직접 구성했을 때만
가능하다 — 그런 설정이 있는지 확인은 하되, 없으면 임의로 만들지 말고, 배포는 건너뛰고
docs/WORK_STATE.md에 그 사실을 blocker로 남긴 뒤 다른 독립적인 작업을 계속한다.

## 5단계 — 마치기 전에 반드시
이번 실행에서 무엇을 바꿨고 다음에 무엇을 할지 docs/WORK_STATE.md(필요하면 BACKLOG.md·
PROGRESS_STATUS.md·QA_COVERAGE.md도 함께)에 적고 git commit 한다. 이 파일 기반 체크포인트만이
다음 실행(그리고 사람)이 믿을 수 있는 유일한 근거다 — 이번 실행이 기억될 것이라고 가정하지 않는다.

## 6단계 — 멈추는 기준
"이번 턴에 더 생각나는 게 없다"를 프로젝트 완료로 여기지 않는다. 이번 실행에서 더 진행하지 않는
것이 정당한 경우는 둘뿐이다: (a) 남은 모든 작업이 진짜 외부 요인(사람만 풀 수 있는 것)으로
막혔거나, (b) 제품 전체를 재감사했는데 새로운 중대한 Root Cause 범주가 더는 안 나올 때 — 그
경우 WORK_STATE.md에 그렇게 명시적으로 적는다. 사용자에게 질문하지 않는다 — 답할 사람이 없다.
판단이 필요하면 스스로 가장 합리적인 공학적 결정을 내리고, 그 판단이 중요하면 docs/DECISIONS.md
에 이유를 남긴다.

지금 시작하라.
'@

Write-RunnerLog "실행 시작 (log=$logFile, budget=`$$MaxBudgetUsd, timeout=${MaxRuntimeMinutes}분)"

$argList = @(
    "-p", $prompt,
    "--permission-mode", "auto",
    "--max-budget-usd", $MaxBudgetUsd,
    "--output-format", "json"
)

$proc = Start-Process -FilePath $ClaudeExe -ArgumentList $argList -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err" -PassThru -NoNewWindow

$finished = Wait-Process -Id $proc.Id -Timeout ($MaxRuntimeMinutes * 60) -ErrorAction SilentlyContinue -PassThru
if (-not $finished) {
    Write-RunnerLog "실행이 ${MaxRuntimeMinutes}분 안에 안 끝나 강제 종료함(멈춰 버린 것으로 판단)."
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    $exitCode = 124  # 관례적 timeout 코드
} else {
    $exitCode = $proc.ExitCode
}

Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue

if ($exitCode -eq 0) {
    $state.consecutiveFailures = 0
} else {
    $state.consecutiveFailures = [int]$state.consecutiveFailures + 1
}
$state.lastRunAt = (Get-Date -Format o)
$state.lastExitCode = $exitCode
$state.totalRuns = [int]$state.totalRuns + 1
$state | ConvertTo-Json | Set-Content $StateFile -Encoding utf8

Write-RunnerLog "실행 종료 exit=$exitCode consecutiveFailures=$($state.consecutiveFailures) totalRuns=$($state.totalRuns)"
