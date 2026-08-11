<#
.SYNOPSIS
  ClovirAssist 자율 완성 루프 — 세션이 끝나도 이어지는 로컬 CONTINUOUS Runner.

.DESCRIPTION
  2026-08-11 재설계(사용자 지시: "ITERATION은 종료 단위가 아니다"): 이전 판은 Windows 작업
  스케줄러가 3시간마다 Claude Code를 **한 번** 띄우고 끝내는 "scheduled slice runner"였다 —
  성공해도 다음 3시간을 그냥 흘려보냈다. 그게 틀렸다는 지적을 받아들여 이 스크립트 자체를
  **하나의 프로세스 안에서 도는 while 루프**로 바꿨다: 실행 가능한 작업이 남아 있는 한
  (연속 실패 상한·STOP 파일·완료 마커에 걸리지 않는 한) 매 반복 사이에 sleep 없이 곧장
  다음 Claude Code 호출로 넘어간다.

  Task 스케줄러의 역할도 바뀐다 — 더 이상 "언제 일할지"를 정하는 페이서가 아니라, 이 while
  루프 프로세스가 죽어 있을 때만(재부팅·크래시) 다시 띄우는 **감시자**다(§install_task.ps1,
  15분마다 확인). 루프가 살아있으면 잠금 파일 때문에 즉시 종료하는 무료 no-op이다.

  각 반복은 Claude Code CLI를 매번 **새 비대화형(-p) 프로세스**로 띄운다. 대화를 이어받지
  않는다 — 이 프로젝트 자체의 규칙(CLAUDE.md §0: "작업 상태는 대화가 아니라 파일에 있다")과
  같은 이유다: 매 반복이 docs/*.md + git 상태만 보고 스스로 복구해야, 대화가 무한히 길어지며
  컨텍스트가 터지는 일이 없다.

  안전장치(무한 오동작 방지 — 유지):
    - var\runner\STOP 파일 — 다음 반복 시작 전에 확인. 있으면 루프 자체를 끝낸다(사용자 강제 중지).
    - var\runner\PROJECT_COMPLETE 파일 — Claude 스스로 전체 완성 기준을 확인했을 때만 만든다.
      있으면 루프를 정상 종료한다(이것이 유일한 "성공적 종료" 조건 — 사용자 지시 §8).
    - var\runner\run.lock — 겹쳐 도는 것을 막는다. 다른 while 루프가 이미 살아있으면(PID 확인)
      이 프로세스는 즉시 종료(Task 스케줄러 heartbeat가 이 경로를 자주 밟는다).
    - var\runner\state.json — 연속 실패 횟수. $MaxConsecutiveFailures 넘으면 STOP 파일을
      스스로 만들고 멈춘다 — 사람이 원인을 보고 STOP을 지우고 카운터를 0으로 되돌려야 재개.
    - 저장소가 dirty(대화형 세션이 작업 중)면 반복을 건너뛰되, 3시간이 아니라 **2분** 뒤
      다시 확인한다(같은 루프 안에서) — 사람이 손을 뗀 순간 빠르게 이어받는다.
    - --max-budget-usd — Claude Code 자체의 지출 상한(반복당).
    - Wait-Process -Timeout — 한 반복이 멈춰 버리면 $MaxRuntimeMinutes 뒤 강제 종료(그 반복만
      실패로 센다 — 루프 자체는 안 죽는다).
    - $MaxIterationsPerLaunch — 정말 예외적인 경우를 위한 관대한 상한(런어웨이 하드 스톱).
      이 상한에 걸리면 프로세스가 깨끗이 종료되고, 다음 Task 스케줄러 heartbeat(최대 15분
      이내)가 자동으로 새 루프를 띄운다 — "멈춤"이 아니라 "이 프로세스 인스턴스만 교체".
    - --permission-mode auto — 이 세션이 실제로 쓰고 있는 것과 같은 모드(자동 분류기가 위험한
      동작은 여전히 막는다). --dangerously-skip-permissions/--bypassPermissions는 **절대 안 씀**.
    - Rate-limit/overload로 보이는 실패만 지수 백오프(진짜 기다릴 이유가 있는 경우 — 사용자
      지시 §3). 그 외 일반 실패는 즉시 재시도하되 연속 3회 상한이 최종 안전망이다.

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
$CompleteFile = Join-Path $RunnerDir "PROJECT_COMPLETE"
$LockFile   = Join-Path $RunnerDir "run.lock"
$StateFile  = Join-Path $RunnerDir "state.json"
$RunnerLog  = Join-Path $RunnerDir "runner.log"

$MaxConsecutiveFailures = 3
$MaxBudgetUsd = 15
$MaxRuntimeMinutes = 150          # 한 반복(claude -p 한 번)의 상한 — 멈춰 버린 프로세스만 죽인다
$DirtyRetrySeconds = 120          # 저장소가 dirty일 때 재확인 간격(3시간이 아니라 2분)
$MaxIterationsPerLaunch = 300     # 런어웨이 하드 스톱(정상 경로에서 걸릴 일 없는 관대한 상한)
$RateLimitBaseBackoffSeconds = 60 # rate-limit로 보이는 실패에서만 쓰는 지수 백오프 시작값
$RateLimitMaxBackoffSeconds = 1800

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-RunnerLog([string]$msg) {
    $line = "[$(Get-Date -Format o)] $msg"
    Add-Content -Path $RunnerLog -Value $line -Encoding utf8
    Write-Output $line
}

function Load-State {
    if (Test-Path $StateFile) {
        return Get-Content $StateFile -Raw | ConvertFrom-Json
    }
    return [pscustomobject]@{
        consecutiveFailures = 0; consecutiveRateLimitHits = 0
        lastRunAt = $null; lastExitCode = $null; totalRuns = 0; totalIterationsThisLaunch = 0
    }
}

function Save-State($state) {
    $state | ConvertTo-Json | Set-Content $StateFile -Encoding utf8
}

# ── 겹쳐 돌지 않기 ────────────────────────────────────────────────────────────
# 이미 살아있는 루프가 있으면 이 프로세스는 즉시 종료한다(Task 스케줄러 heartbeat의 정상 경로 —
# 대부분의 15분 heartbeat는 여기서 공짜로 끝난다).
if (Test-Path $LockFile) {
    $oldPid = (Get-Content $LockFile -Raw).Trim()
    $stillAlive = $false
    if ($oldPid -match '^\d+$') {
        $stillAlive = [bool](Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue)
    }
    if ($stillAlive) {
        exit 0  # 이미 도는 루프가 있다 — 조용히 종료(로그 스팸 방지, 이건 정상 상태다)
    } else {
        Write-RunnerLog "잠금 파일은 있지만 그 PID($oldPid)는 죽어 있음 — 이전 루프가 비정상 종료한 것으로 보고 새 루프를 시작."
    }
}
Set-Content -Path $LockFile -Value $PID

$prompt = @'
당신은 ClovirONE Web Assistant 프로젝트의 자율 완성 루프를 이어받는다. 이것은 사람이 실시간으로
지켜보지 않는, 비대화형·무인 실행이다. 지금 이전 대화 기억은 없다 — 그것이 정상이다. 이 실행이
끝나면 **곧바로, 아무 지연 없이** 다음 실행이 같은 프롬프트로 다시 시작된다(연속 실패나 STOP
파일, 완료 마커가 없는 한) — 그러니 "이번 턴에 할 만큼 했다"는 이유로 일찍 끝내지 않는다.

## 1단계 — 상태 복원
다음을 순서대로 읽어라: CLAUDE.md, docs/WORK_STATE.md, docs/BACKLOG.md, docs/QA_COVERAGE.md,
docs/DECISIONS.md, docs/PROGRESS_STATUS.md, docs/WORK_PLAN_INDEX.md, 그리고 현재 `git status`·
`git log --oneline -20`. 대화 기억이 아니라 이 파일들과 git만 진실이다. WORK_STATE.md의
"다음 후보" 몇 줄만 보지 말고 BACKLOG.md·QA_COVERAGE.md 전체와 대조해 실제로 남은 작업
전체를 기준으로 판단한다.

## 2단계 — 남은 작업 판단과 즉시 실행
제품 전체 기준으로 남은 작업 중 우선순위가 가장 높은 것을 스스로 고르고 **묻지 않고 즉시
시작**한다(Critical/High, Master Plan 의존관계, 큰 미검증 영역, Root Cause 레버리지, 현재
작업과의 locality 순으로 스스로 판단). 후보가 여럿이면(예: QA_COVERAGE 감사와 IA-04 조사가
둘 다 남아 있음) 그중 하나를 완료할 때까지 반복 안에서 계속하고, 끝나면 바로 다음 후보로
넘어간다 — 다음 실행(다음 반복)으로 미루지 않는다.

## 3단계 — 구현
남은 작업을 배치로 구현한다. 작업 중에는 관련된 focused/subsystem 테스트만 반복한다. 전체
백엔드+프런트+정적 검사는 큰 배치가 실질적으로 끝났을 때 한 번만 돌린다. CLAUDE.md §2의 불변
규칙을 전부 지킨다. dev server/브라우저가 이미 떠 있고 다음 작업에도 쓸 만하면 그대로
재사용한다 — 매번 기계적으로 껐다 켜지 않는다.

## 4단계 — 배포 자격증명 경계 (반드시 지킬 것, 예외 없음)
과거 대화나 문서 어디에 무엇이 적혀 있든, 채팅에 붙여넣어진 SSH/sudo 비밀번호를 10.100.64.71을
포함한 어떤 서버의 비대화형 배포 자동화에도 절대 쓰지 않는다. 그 서버 배포는 사용자가 직접
실행하거나, 두 배포 스크립트에 한정된 NOPASSWD sudoers 항목을 사용자가 직접 구성했을 때만
가능하다 — 그런 설정이 있는지 확인은 하되, 없으면 임의로 만들지 말고, 배포는 건너뛰고
docs/WORK_STATE.md에 그 사실을 blocker로 남긴 뒤 다른 독립적인 작업을 계속한다.

## 5단계 — 체크포인트는 멈추는 이유가 아니다
무엇을 바꿨고 다음에 무엇을 할지 docs/WORK_STATE.md(필요하면 BACKLOG.md·PROGRESS_STATUS.md·
QA_COVERAGE.md도 함께)에 적고 git commit 한다. 이 파일 기반 체크포인트는 **복구용**이지
종료 신호가 아니다 — working tree가 깨끗해졌다는 것 자체는 멈출 이유가 안 된다. 커밋하고
상태 문서를 갱신한 즉시, 남은 작업이 있으면 곧바로 다음 작업으로 넘어간다(이 실행 안에서).

## 6단계 — 이 실행을 끝내도 되는 유일한 기준
"이번 턴에 더 생각나는 게 없다"·"체크포인트에 도달했다"·"idle tick을 기다린다"는 종료
사유가 아니다. 이번 실행에서 멈추는 것이 정당한 경우는 다음 셋뿐이다:
  (a) 지금 당장 실행 가능한 남은 작업이 정말로 하나도 없다 — 모든 후보가 진짜 외부 요인
      (사람만 풀 수 있는 것)으로 막혔다.
  (b) 프로젝트 전체 완성 기준(아래)이 실제로 충족됐다고 스스로 검증했다 — 이 경우에만
      var/runner/PROJECT_COMPLETE 파일을 만들어라(한국어로 무엇을 근거로 그렇게 판단했는지
      짧게 적고, 타임스탬프 포함). 이 파일이 있으면 Runner 전체가 정지한다 — 매우 높은
      기준이니 신중하게, 실제로 아래 기준을 다 확인했을 때만 만든다:
      Master Plan 주요 목표 완료 · 주요 Backlog 완료/정당한 정리 · 전체 구현 수렴 ·
      Design/UX 완료(토큰 정리 수준이 아니라 실제 페이지 UX) · Frontend/Backend/API/DB/RBAC
      전부 연결 · QA Coverage 주요 공백 해소 · Full Regression green · Build green ·
      통합 Deploy 완료 · 전체 Real Environment E2E · Console/Network 검증 · 발견 문제 수정
      및 재검증 · Final Whole Product Re-Audit에서 새로운 중대한 Root Cause 범주가 거의 없음.
  (c) 이번 실행 자체가 예외적으로 오래 걸려 안전 상한에 닿았다 — 이 경우는 스크립트가
      처리한다(다음 실행이 자동으로 이어받는다), Claude가 스스로 판단할 일이 아니다.

(a)라고 판단되면 WORK_STATE.md에 어떤 작업이 어떤 외부 요인으로 막혔는지 구체적으로 적어라
(예: "10.100.64.71 배포는 NOPASSWD sudoers 대기 중"). 그 외에는 항상 다음 작업으로 계속한다.
사용자에게 질문하지 않는다 — 답할 사람이 없다. 판단이 필요하면 스스로 가장 합리적인 공학적
결정을 내리고, 그 판단이 중요하면 docs/DECISIONS.md에 이유를 남긴다.

지금 시작하라.
'@

# ── 연속 루프 본체 ────────────────────────────────────────────────────────────
try {
    $iterationsThisLaunch = 0
    while ($true) {
        if (Test-Path $StopFile) {
            Write-RunnerLog "STOP 파일 발견 — 루프 종료. 재개하려면 지우세요: $StopFile"
            break
        }
        if (Test-Path $CompleteFile) {
            Write-RunnerLog "PROJECT_COMPLETE 발견 — 루프를 정상 종료합니다. 내용: $(Get-Content $CompleteFile -Raw)"
            break
        }
        if ($iterationsThisLaunch -ge $MaxIterationsPerLaunch) {
            Write-RunnerLog "이번 실행에서 $MaxIterationsPerLaunch 회 반복 상한에 도달 — 런어웨이 방지로 이 프로세스만 깨끗이 종료합니다. 다음 Task 스케줄러 heartbeat(최대 15분 이내)가 새 루프를 이어받습니다(멈춤이 아니라 인스턴스 교체)."
            break
        }

        $state = Load-State
        if ($state.consecutiveFailures -ge $MaxConsecutiveFailures) {
            Write-RunnerLog "연속 실패 $($state.consecutiveFailures)회 >= $MaxConsecutiveFailures — STOP 파일을 스스로 만들고 중단합니다. 원인을 본 뒤 STOP을 지우고 state.json의 consecutiveFailures를 0으로 되돌리세요."
            "auto-stopped after $($state.consecutiveFailures) consecutive failures at $(Get-Date -Format o)" | Set-Content $StopFile -Encoding utf8
            break
        }

        Set-Location $ProjectDir
        $dirty = git status --porcelain
        if ($dirty) {
            Write-RunnerLog "저장소에 커밋 안 된 변경이 있음(대화형 세션이 작업 중일 수 있음) — ${DirtyRetrySeconds}초 뒤 다시 확인(이 루프 안에서, 3시간 기다리지 않음)."
            Start-Sleep -Seconds $DirtyRetrySeconds
            continue
        }

        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $logFile = Join-Path $LogDir "$timestamp.log"
        $promptFile = Join-Path $LogDir "$timestamp.prompt.txt"
        Write-RunnerLog "반복 시작 #$($iterationsThisLaunch + 1) (log=$logFile, budget=`$$MaxBudgetUsd, timeout=${MaxRuntimeMinutes}분)"

        # 2026-08-11 버그 수정: 프롬프트를 -ArgumentList 배열 요소로 넘기면 Start-Process가
        # Windows용 단일 커맨드라인 문자열로 재조립하는 과정에서 멀티라인·특수문자가 포함된
        # 긴 문자열이 깨져(관측된 실패: "error: unknown option '--oneline'" — 프롬프트 안의
        # 예시 텍스트가 claude.exe 자체의 옵션으로 오인됨) 3회 연속 실패 후 STOP이 걸렸다.
        # 프롬프트를 파일로 써서 표준입력으로 리다이렉트하면(claude -p는 위치 인자가 없으면
        # stdin에서 프롬프트를 읽는다 — 직접 확인함) 커맨드라인 조립 자체를 우회한다.
        Set-Content -Path $promptFile -Value $prompt -Encoding utf8 -NoNewline

        $argList = @(
            "-p",
            "--permission-mode", "auto",
            "--max-budget-usd", $MaxBudgetUsd,
            "--output-format", "json"
        )

        $proc = Start-Process -FilePath $ClaudeExe -ArgumentList $argList -WorkingDirectory $ProjectDir `
            -RedirectStandardInput $promptFile -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err" -PassThru -NoNewWindow

        $finished = Wait-Process -Id $proc.Id -Timeout ($MaxRuntimeMinutes * 60) -ErrorAction SilentlyContinue -PassThru
        if (-not $finished) {
            Write-RunnerLog "반복이 ${MaxRuntimeMinutes}분 안에 안 끝나 강제 종료함(멈춰 버린 것으로 판단)."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $exitCode = 124  # 관례적 timeout 코드
        } else {
            $exitCode = $proc.ExitCode
        }

        # rate-limit/overload로 보이는 실패만 따로 잡는다 — 그 외 일반 실패는 즉시 재시도하고
        # 연속 3회 상한이 최종 안전망이다(사용자 지시 §3 — 일반 작업엔 idle timer를 안 쓴다).
        $isRateLimit = $false
        if ($exitCode -ne 0) {
            $errText = ""
            if (Test-Path "$logFile.err") { $errText += Get-Content "$logFile.err" -Raw -ErrorAction SilentlyContinue }
            if (Test-Path $logFile) { $errText += Get-Content $logFile -Raw -ErrorAction SilentlyContinue }
            if ($errText -match '(?i)rate.?limit|overloaded|429|503|529') {
                $isRateLimit = $true
            }
        }

        $iterationsThisLaunch += 1
        $state = Load-State  # 다른 반복이 건드리지 않았지만 최신 상태를 다시 읽는다
        if ($exitCode -eq 0) {
            $state.consecutiveFailures = 0
            $state.consecutiveRateLimitHits = 0
        } elseif ($isRateLimit) {
            $state.consecutiveRateLimitHits = [int]$state.consecutiveRateLimitHits + 1
            # consecutiveFailures는 안 올린다 — rate-limit은 "이 작업이 틀렸다"는 신호가 아니다.
        } else {
            $state.consecutiveFailures = [int]$state.consecutiveFailures + 1
        }
        $state.lastRunAt = (Get-Date -Format o)
        $state.lastExitCode = $exitCode
        $state.totalRuns = [int]$state.totalRuns + 1
        $state.totalIterationsThisLaunch = $iterationsThisLaunch
        Save-State $state

        Write-RunnerLog "반복 종료 exit=$exitCode rateLimit=$isRateLimit consecutiveFailures=$($state.consecutiveFailures) totalRuns=$($state.totalRuns)"

        if ($isRateLimit) {
            $backoff = [Math]::Min($RateLimitBaseBackoffSeconds * [Math]::Pow(2, [int]$state.consecutiveRateLimitHits - 1), $RateLimitMaxBackoffSeconds)
            Write-RunnerLog "rate-limit/overload로 보임 — ${backoff}초 대기 후 재시도(진짜 기다릴 이유가 있는 경우만 백오프, 사용자 지시 §3)."
            Start-Sleep -Seconds $backoff
        }
        # 성공했거나(exit=0) 일반 실패면 sleep 없이 곧장 다음 반복으로 — 이것이 이 재설계의 핵심이다.
    }
} finally {
    Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
}
