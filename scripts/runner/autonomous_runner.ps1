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

  2026-08-12 재설계(사용자 지시: "Persistent Worker Session — 매 반복마다 새 세션을 만들지
  마라, 하나의 Worker Session을 계속 이어가라"): 이전 판은 매 반복을 완전히 새 비대화형(-p)
  세션으로 띄우고 docs/*.md + git만으로 복구했다. 그 이유(컨텍스트 무한 증가 방지)는 여전히
  유효한 우려지만, Claude Code CLI는 세션을 서버 측에 유지하며 자동 압축(auto-compact)하므로
  **하나의 세션을 --resume으로 계속 이어가면서도** 그 문제를 겪지 않는다 — 실제로 확인함
  (아래 참고). 이제 각 반복은:
    - var\runner\session_id.txt 에 저장된 session_id가 있으면 `--resume <id>` 로 그 대화를
      이어받는다 — Claude는 이전 반복의 대화 기억을 그대로 갖고 시작한다.
    - 없으면(최초 실행, 또는 resume 실패로 지워진 뒤) 새 GUID를 만들어 `--session-id <id>`
      로 새 Worker Session을 시작하고 즉시 파일에 저장한다(호출 전에 저장 — 프로세스가
      죽어도 다음 반복이 무엇을 시도했는지 안다).
    - resume가 실패하면(저장된 session_id가 더 이상 유효하지 않음) exit code != 0 이고
      stderr에 정확히 "No conversation found with session ID: <id>" 가 찍힌다 — 2026-08-12
      실제 CLI 호출로 이 시그니처를 확인함(견본: `claude -p --resume <가짜 UUID>
      --output-format json --tools ""` → exit=1, stdout 비어있음, stderr에 위 문구).
      이 경우 consecutiveFailures를 올리지 않고(작업 실패가 아니라 세션 인프라 문제)
      session_id.txt를 지운 뒤 sleep 없이 즉시 다음 반복에서 새 세션으로 재시작한다.
    - 그래도 CLAUDE.md §0("작업 상태는 대화가 아니라 파일에 있다")은 프롬프트에 그대로
      남긴다 — 대화 기억이 있어도 그것보다 저장소의 실제 상태(docs/git/source)를 우선
      신뢰하라고 매 반복 다시 지시한다. 대화가 길게 이어지며 사람이 저장소를 직접 건드렸을
      가능성, 또는 이전 반복의 판단이 틀렸을 가능성을 매번 재확인하기 위함이다.

  검증(2026-08-12, 실제 API 호출로 확인 — var/runner를 건드리지 않는 격리된 호출):
    1) `--session-id <신규 UUID>` 로 세션 시작 → 응답 JSON의 session_id가 요청한 UUID와
       일치, "코드워드를 기억해라"라고 지시.
    2) 같은 UUID로 `--resume <UUID>` 재호출(새 프로세스) → 실제로 그 코드워드를 정확히
       그대로 답함(result="PINEAPPLE42") — 대화가 프로세스 경계를 넘어 실제로 이어짐을
       증명. cache_read_input_tokens가 1차 호출의 cache_creation_input_tokens와 일치.
    3) 존재하지 않는 UUID로 `--resume` → exit=1, stderr="No conversation found with
       session ID: ...", stdout 비어있음 — 위 실패 감지 로직의 근거.

  각 반복은 Claude Code CLI를 매번 **새 비대화형(-p) 프로세스**로 띄우지만(OS 프로세스는
  매번 새로 뜬다), `--resume`으로 같은 대화(Worker Session)를 이어받는다 — OS 프로세스
  재시작과 대화 연속성은 별개다.

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
    - Process.WaitForExit(ms) — 한 invocation 이 멈춰 버리면 $MaxRuntimeMinutes 뒤 강제 종료
      (그 invocation 만 실패로 센다 — 루프 자체는 안 죽는다). `Wait-Process -PassThru` 로는
      타임아웃을 판정할 수 없다(실패해도 객체를 돌려준다) — 2026-08-12 수정.
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

  2026-08-12 보정(Continuity Bootstrap, D-64) — 실제로 관측된 continuity 구멍 네 개를 막는다:
    1) **Stop hook 보조 제동**. Worker child에 `CLOVIR_SUPERVISED=1`을 상속시킨다(이 프로세스
       환경에 설정 → Start-Process가 그대로 물려준다). `.claude/settings.json`의 Stop hook
       (`scripts/runner/stop_guard.py`)이 그 표시를 보고, PROJECT_COMPLETE가 없는데 Claude가
       Summary 쓰고 끝내려 하면 **invocation당 한 번** block한다. 사람이 직접 쓰는 대화형
       세션에는 이 변수가 없어 아무 영향이 없다. 어디까지나 보조 장치이고, process 경계를
       넘는 continuity의 1차 책임은 여전히 이 while 루프다(CLAUDE.md §11).
    2) **STOP과 자동 실패 흔적의 분리**. 예전엔 연속 실패 상한에 걸리면 스크립트가 스스로
       `STOP`을 만들었다 — 그래서 사용자의 명시적 중단과 "과거에 자동으로 멈춘 흔적"이 같은
       파일로 뭉개졌고, 원인을 고친 뒤 수동 재시작해도 stale STOP 때문에 아무 일도 안 일어났다
       (2026-08-11 실제로 12시간 넘게 이 상태였다 — runner.log). 이제 자동 정지는
       `AUTO_STOP`에 쓰고, 사람이 **직접 수동 시작**하는 것 자체를 그 실패의 확인으로 본다:
       AUTO_STOP은 크게 출력한 뒤 지우고 카운터를 0으로 되돌리고 진행한다. `STOP`은 오직
       사용자만 만들며, 있으면 크게 이유를 출력하고 종료한다(조용한 no-op 금지).
    3) **dirty 워킹트리 무한 대기 제거**. 예전엔 커밋 안 된 변경이 있으면 2분마다 무한히
       다시 확인했다. `app/worker_main.py`가 CRLF/LF 정규화 때문에 `git status`에는 영원히
       modified로 보이지만 실제 내용 차이는 0인 상태였고(2026-08-12 확인), 그 결과 루프가
       영원히 한 번도 Claude를 띄우지 못하는 조용한 정지에 빠졌다. 이제 워킹트리 내용이
       **변하지 않은 채로** $MaxUnchangedDirtyWaits 회 반복되면 "사람이 편집 중이 아니다"로
       보고 크게 로그를 남긴 뒤 그대로 진행한다.
    4) **런어웨이 상한의 거짓 안내 수정**. 예전 메시지는 "작업 스케줄러 heartbeat가 새 루프를
       이어받는다"고 했지만 Task Scheduler 의존은 폐기됐다(CLAUDE.md §0) — 그 상한에 닿으면
       실제로는 아무도 이어받지 않는다. 이제 그 사실을 정확히 알린다.
  파라미터를 노출한 이유는 controlled test가 **이 스크립트 자체**(사본이 아니라)를 격리된
  scratch 저장소를 대상으로 실행할 수 있게 하기 위함이다. 기본값은 실제 운영값 그대로다.
#>

param(
    [string]$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant",
    [string]$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe",
    # 아래 둘은 controlled test용 seam — 평소 실행에서는 비워 둔다(내장 프롬프트/기본 모델 사용).
    # 이름 주의: PowerShell 변수는 대소문자를 구분하지 않는다. 루프 안의 per-invocation 변수
    # `$promptFile` 과 같은 이름을 쓰면 파라미터가 조용히 덮어써진다(2026-08-12 실제로 당함 —
    # 테스트 프롬프트 대신 내장 프롬프트가 나갔고, 로그만 봐서는 알 수 없었다).
    [string]$PromptOverrideFile = "",
    [string]$Model              = "",
    [int]$MaxIterationsPerLaunch = 300,   # 런어웨이 하드 스톱(정상 경로에서 걸릴 일 없는 상한)
    [int]$MaxConsecutiveFailures = 3,
    [int]$MaxBudgetUsd = 15,
    [int]$MaxRuntimeMinutes = 150,        # 한 invocation의 상한 — 멈춰 버린 프로세스만 죽인다
    [int]$DirtyRetrySeconds = 120,        # 워킹트리가 dirty일 때 재확인 간격
    [int]$MaxUnchangedDirtyWaits = 5      # 내용이 안 변한 채 이만큼 반복되면 그냥 진행한다
)

$ErrorActionPreference = "Stop"

$RunnerDir  = Join-Path $ProjectDir "var\runner"
$LogDir     = Join-Path $RunnerDir "logs"
$StopFile   = Join-Path $RunnerDir "STOP"            # 사용자만 만든다
$AutoStopFile = Join-Path $RunnerDir "AUTO_STOP"     # 스크립트가 연속 실패로 멈출 때만 만든다
$CompleteFile = Join-Path $RunnerDir "PROJECT_COMPLETE"
$LockFile   = Join-Path $RunnerDir "run.lock"
$StateFile  = Join-Path $RunnerDir "state.json"
$RunnerLog  = Join-Path $RunnerDir "runner.log"
$SessionIdFile = Join-Path $RunnerDir "session_id.txt"  # secret 아님(불투명 UUID) — git엔 안 올라감(var/ 전체 gitignore)

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

# ── Persistent Worker Session id ──────────────────────────────────────────────
function Load-SessionId {
    if (-not (Test-Path $SessionIdFile)) { return $null }
    $v = (Get-Content $SessionIdFile -Raw -ErrorAction SilentlyContinue)
    if ($null -eq $v) { return $null }
    $v = $v.Trim()
    if ($v -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') { return $v }
    return $null  # 손상/빈 파일 — 새 세션으로 취급(영구 정지 방지)
}

function Save-SessionId([string]$id) {
    Set-Content -Path $SessionIdFile -Value $id -Encoding utf8 -NoNewline
}

function Clear-SessionId {
    Remove-Item -Path $SessionIdFile -Force -ErrorAction SilentlyContinue
}

# ── 완료 Gate ─────────────────────────────────────────────────────────────────
# stop_guard.py 의 project_complete() 와 **같은 규칙**이어야 한다: 존재만으로는 부족하고
# 내용이 있어야 한다(빈 파일이 실수로 생겨 프로젝트가 조용히 끝나는 것을 막는다).
function Test-ProjectComplete {
    if (-not (Test-Path $CompleteFile)) { return $false }
    $content = Get-Content $CompleteFile -Raw -ErrorAction SilentlyContinue
    return -not [string]::IsNullOrWhiteSpace($content)
}

# 실행할 수 없는 이유는 로그 한 줄이 아니라 눈에 띄게 출력한다(사용자 지시 §9 — 조용한 no-op 금지).
function Write-Banner([string[]]$lines) {
    $bar = "=" * 78
    Write-Output ""; Write-Output $bar
    foreach ($l in $lines) { Write-Output $l }
    Write-Output $bar; Write-Output ""
}

# ── 겹쳐 돌지 않기(단일 Writer) ───────────────────────────────────────────────
# 2026-08-12: 예전엔 잠금 파일에 적힌 PID 가 살아있는지 보는 방식이었다 — PID 재사용에 취약하고,
# "확인 후 기록" 사이의 경쟁 구간도 열려 있었다. 이제 잠금 파일 핸들 자체를 **배타 열기**로 잡고
# 프로세스가 사는 동안 계속 들고 있는다: 두 번째 인스턴스는 열기 자체가 실패하므로 경쟁 구간이
# 없고, 크래시/강제 종료 시에는 OS 가 핸들을 회수하므로 stale lock 이 남지 않는다.
# FileShare::Read 로 열어 두는 이유는 두 번째 인스턴스가 "누가 잡고 있는지"(PID)를 읽어서 안내할
# 수 있게 하기 위함이다.
$lockStream = $null
try {
    $lockStream = [System.IO.File]::Open(
        $LockFile, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    $lockWriter = New-Object System.IO.StreamWriter($lockStream)
    $lockWriter.WriteLine($PID)
    $lockWriter.Flush()   # 스트림은 닫지 않는다 — 닫는 순간 잠금이 풀린다
} catch [System.IO.IOException] {
    $holder = "(알 수 없음)"
    try { $holder = (Get-Content $LockFile -Raw -ErrorAction SilentlyContinue).Trim() } catch {}
    Write-Banner @(
        "이미 살아있는 Supervisor(PID=$holder)가 이 저장소를 잡고 있어 이 프로세스는 아무 것도 하지 않고 종료합니다.",
        "두 Writer 가 같은 워킹트리를 동시에 고치지 않게 하기 위한 의도된 동작입니다.",
        "그 Supervisor 를 멈추려면: var\runner\STOP 파일을 만들거나(다음 invocation 전에 확인) 해당 PID 를 종료하세요."
    )
    Write-RunnerLog "다른 Supervisor(PID=$holder)가 잠금을 보유 중 — 이 프로세스는 종료한다."
    exit 0
}

# ── STOP(사용자) vs AUTO_STOP(자동 실패 흔적) ─────────────────────────────────
# 이 둘을 같은 파일로 뭉개면 "사용자가 명시적으로 멈춘 것"과 "예전에 자동으로 멈춘 흔적"을
# 구분할 수 없다(사용자 지시 §9). STOP 은 오직 사람만 만든다.
if (Test-Path $StopFile) {
    $stopBody = ""
    try { $stopBody = (Get-Content $StopFile -Raw -ErrorAction SilentlyContinue).Trim() } catch {}
    Write-Banner @(
        "STOP 파일이 있어 이번 실행은 Worker 를 한 번도 띄우지 않고 종료합니다.",
        "  경로: $StopFile",
        "  내용: $(if ($stopBody) { $stopBody } else { '(비어 있음)' })",
        "이 파일은 '사용자가 명시적으로 Supervisor 를 멈춘 상태'를 뜻합니다.",
        "재개하려면 이 파일을 지우고 이 스크립트를 다시 실행하세요."
    )
    Write-RunnerLog "STOP 파일 있음 — 아무 invocation 도 실행하지 않고 종료: $StopFile"
    if ($lockStream) { $lockStream.Close() }
    Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
    exit 3
}
if (Test-Path $AutoStopFile) {
    # 사람이 이 스크립트를 **직접 다시 시작한 것** 자체를 그 실패에 대한 확인으로 본다 —
    # 원인을 고치고 재시작했는데 옛 흔적 때문에 또 아무 일도 안 일어나는 것이 이 구조의
    # 실제 실패 사례였다(2026-08-11). 크게 알리고, 지우고, 카운터를 되돌리고 진행한다.
    $autoBody = ""
    try { $autoBody = (Get-Content $AutoStopFile -Raw -ErrorAction SilentlyContinue).Trim() } catch {}
    Write-Banner @(
        "이전 실행이 연속 실패로 스스로 멈춘 흔적(AUTO_STOP)이 있습니다:",
        "  $autoBody",
        "사용자가 직접 이 스크립트를 다시 시작했으므로 그 실패를 확인한 것으로 보고,",
        "흔적을 지우고 연속 실패 카운터를 0으로 되돌린 뒤 계속 진행합니다.",
        "정말로 멈춰 두려면 대신 var\runner\STOP 파일을 만드세요."
    )
    Write-RunnerLog "AUTO_STOP 흔적 발견 — 수동 재시작을 확인으로 보고 정리한 뒤 진행. 내용: $autoBody"
    Remove-Item -Path $AutoStopFile -Force -ErrorAction SilentlyContinue
    $s = Load-State
    $s.consecutiveFailures = 0
    $s.consecutiveRateLimitHits = 0
    Save-State $s
}

# Supervisor 가 띄운 Worker 임을 표시한다 — Stop hook(stop_guard.py)이 이 표시를 보고만
# 동작한다. 이 프로세스의 환경에 넣어 두면 Start-Process 로 띄우는 child 가 그대로 상속한다
# (PowerShell 버전에 따라 지원 여부가 갈리는 Start-Process -Environment 를 쓰지 않는 이유).
$env:CLOVIR_SUPERVISED = "1"

$prompt = @'
당신은 ClovirONE Web Assistant 프로젝트를 **끝까지 완성**하는 작업을 이어받는다. 이것은 사람이
실시간으로 지켜보지 않는, 비대화형·무인 실행이다.

**작업 단위는 PROJECT 전체 하나뿐이다.** 지금 이 프로세스 호출(invocation)은 work unit이 아니다 —
"이번 회차", "이번 batch", "이번 turn 범위", "iteration 완료" 같은 단위는 존재하지 않는다. 한
Root Cause를 닫았으면 곧바로 같은 호출 안에서 다음 Root Cause로 넘어간다. 호출 자체가
budget/context 한계로 끝나는 것은 허용되지만, 그때도 PROJECT가 끝난 것이 아니며 로컬 PowerShell
Supervisor가 지연 없이 같은 Worker Session을 즉시 resume한다.

이 호출은 이전과 같은 Worker Session을 이어받은 것일 수도(대화 기억 있음), 방금 새로 시작된
것일 수도 있다(대화 기억 없음 — 정상, 이전 세션이 resume 불가능해졌을 때 자동으로 새로 시작된다).
어느 쪽이든 아래 1단계부터 실제로 다시 확인하고 시작하라 — 대화 기억이 있어도 그것을 저장소의
실제 현재 상태보다 우선 신뢰하지 마라(사람이 그 사이 저장소를 직접 건드렸을 수 있고, 이전
판단이 틀렸을 수도 있다).

## 1단계 — 상태 복원(대화 기억이 있어도 실제로 다시 확인)
다음을 순서대로 읽어라: CLAUDE.md, docs/WORK_STATE.md, docs/BACKLOG.md, docs/QA_COVERAGE.md,
docs/DECISIONS.md, docs/PROGRESS_STATUS.md, docs/WORK_PLAN_INDEX.md, 그리고 현재 `git status`·
`git log --oneline -20`. 대화 기억이 아니라 이 파일들과 git만 진실이다. WORK_STATE.md의
"다음 후보" 몇 줄만 보지 말고 BACKLOG.md·QA_COVERAGE.md 전체와 대조해 실제로 남은 작업
전체를 기준으로 판단한다.

## 2단계 — 남은 작업 판단과 즉시 실행
제품 전체 기준으로 남은 작업 중 우선순위가 가장 높은 것을 스스로 고르고 **묻지 않고 즉시
시작**한다(Critical/High, Master Plan 의존관계, 큰 미검증 영역, Root Cause 레버리지, 현재
작업과의 locality 순으로 스스로 판단). 하나를 끝내면 멈추지 말고 곧바로 다음 후보로 넘어간다 —
"다음 호출에서 하겠다"는 선택지는 없다.

## 3단계 — 구현
남은 작업을 Root Cause 단위로 크게 묶어 구현한다. 작업 중에는 관련된 focused/subsystem 테스트만
반복한다. 전체 백엔드+프런트+정적 검사는 구현이 실질적으로 수렴했을 때 돌린다. CLAUDE.md §3의
불변 규칙을 전부 지킨다. dev server/브라우저가 이미 떠 있고 다음 작업에도 쓸 만하면 그대로
재사용한다 — 매번 기계적으로 껐다 켜지 않는다.
**Full Regression green은 정지 신호가 아니다** — green을 확인했으면 곧바로 다음 구현으로 돌아간다.

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
상태 문서를 갱신한 **즉시** 다음 작업으로 넘어간다. 문서 갱신이나 commit 직후에 멈추지 마라.

## 6단계 — 멈춰도 되는 유일한 기준
Summary·recap·commit·clean tree·Full Regression green·build green·"현재 할 일 목록이 비었다"·
"체크포인트에 도달했다"는 전부 종료 사유가 아니다. 멈추는 것이 정당한 경우는 둘뿐이다:
  (a) 지금 당장 실행 가능한 남은 작업이 정말로 하나도 없다 — 모든 후보가 진짜 외부 요인
      (사람만 풀 수 있는 것)으로 막혔다. 한 blocker 때문에 독립적으로 가능한 다른 작업까지
      멈추는 것은 여기에 해당하지 않는다.
  (b) 프로젝트 전체 완성 기준(CLAUDE.md §13)이 실제로 충족됐다고 스스로 검증했다 — 이 경우에만
      var/runner/PROJECT_COMPLETE 파일을 만들어라(한국어로 무엇을 근거로 그렇게 판단했는지
      짧게 적고, 타임스탬프 포함 — 빈 파일은 완료로 인정되지 않는다). 이 파일이 있어야만
      Supervisor와 Stop hook이 정지를 허용한다 — 매우 높은 기준이니, 실제로 아래를 다
      확인했을 때만 만든다:
      Master Plan 주요 목표 완료 · 주요 Backlog 완료/정당한 정리 · 전체 구현 수렴 ·
      Design/UX 완료(토큰 정리 수준이 아니라 실제 페이지 UX) · Frontend/Backend/API/DB/RBAC
      전부 연결 · QA Coverage 주요 공백 해소 · Full Regression green · Build green ·
      통합 Deploy 완료 · Chrome Whole-product E2E · Console/Network 검증 · 발견 문제 수정
      및 재검증 · Final Whole Product Re-Audit에서 새로운 중대한 Root Cause 범주가 거의 없음.

(a)라고 판단되면 WORK_STATE.md에 어떤 작업이 어떤 외부 요인으로 막혔는지 구체적으로 적어라
(예: "10.100.64.71 배포는 NOPASSWD sudoers 대기 중"). 그 외에는 항상 다음 작업으로 계속한다.
사용자에게 질문하지 않는다 — 답할 사람이 없다. 판단이 필요하면 스스로 가장 합리적인 공학적
결정을 내리고, 그 판단이 중요하면 docs/DECISIONS.md에 이유를 남긴다.

참고: PROJECT_COMPLETE 없이 끝내려 하면 Stop hook이 한 번 제동을 걸어 계속하라고 되돌린다.
그 제동은 보조 장치일 뿐이니, 그것에 기대지 말고 애초에 스스로 계속하라.

지금 시작하라.
'@

# ── 연속 루프 본체 ────────────────────────────────────────────────────────────
try {
    $iterationsThisLaunch = 0
    $dirtySignature = $null      # 직전에 본 워킹트리 상태(내용이 바뀌는지 보려고 들고 있는다)
    $unchangedDirtyWaits = 0
    Write-RunnerLog "Supervisor 시작 PID=$PID projectDir=$ProjectDir (CLOVIR_SUPERVISED=1, Stop hook 보조 제동 활성)"

    while ($true) {
        if (Test-Path $StopFile) {
            Write-RunnerLog "STOP 파일 발견(사용자 명시적 중단) — 루프 종료. 재개하려면 지우세요: $StopFile"
            break
        }
        if (Test-ProjectComplete) {
            Write-RunnerLog "PROJECT_COMPLETE 유효 — 루프를 정상 종료합니다. 내용: $(Get-Content $CompleteFile -Raw)"
            break
        }
        if ($iterationsThisLaunch -ge $MaxIterationsPerLaunch) {
            # 2026-08-12 정정: 예전 메시지는 "작업 스케줄러 heartbeat 가 새 루프를 이어받는다"고
            # 했지만 Task Scheduler 의존은 폐기됐다(CLAUDE.md §0) — 여기서 끊기면 실제로는
            # 아무도 이어받지 않는다. 거짓 안심을 주지 말고 사실대로 알린다.
            Write-Banner @(
                "이번 실행에서 Worker invocation $MaxIterationsPerLaunch 회 상한에 도달해 종료합니다(런어웨이 방지).",
                "이것은 PROJECT_COMPLETE 가 아닙니다 — 프로젝트는 끝나지 않았습니다.",
                "자동으로 이어받는 장치는 없습니다(Task Scheduler 의존 폐기). 계속하려면 이 스크립트를 다시 실행하세요."
            )
            Write-RunnerLog "invocation 상한 $MaxIterationsPerLaunch 도달 — 종료(PROJECT_COMPLETE 아님, 수동 재시작 필요)."
            break
        }

        $state = Load-State
        if ($state.consecutiveFailures -ge $MaxConsecutiveFailures) {
            $msg = "auto-stopped after $($state.consecutiveFailures) consecutive failures at $(Get-Date -Format o)"
            # STOP(사용자 전용)이 아니라 AUTO_STOP 에 쓴다 — 다음 수동 재시작이 이 흔적 때문에
            # 조용히 무력화되지 않게 하기 위함(사용자 지시 §9).
            $msg | Set-Content $AutoStopFile -Encoding utf8
            Write-Banner @(
                "연속 실패 $($state.consecutiveFailures)회 >= $MaxConsecutiveFailures — 원인 없이 계속 태우지 않기 위해 중단합니다.",
                "각 invocation 의 원본 출력은 var\runner\logs\ 에 있습니다. 원인을 확인하세요.",
                "고친 뒤에는 이 스크립트를 그냥 다시 실행하면 됩니다 — AUTO_STOP 은 자동으로 정리됩니다."
            )
            Write-RunnerLog "연속 실패 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            break
        }

        Set-Location $ProjectDir
        $dirty = (git status --porcelain | Out-String).Trim()
        if ($dirty) {
            # 2026-08-12: 예전엔 여기서 무한히 2분씩 기다렸다. 실제로 `app/worker_main.py` 가
            # CRLF/LF 정규화 때문에 내용 차이가 0인데도 영원히 modified 로 보이는 상태였고,
            # 그 결과 Supervisor 가 Claude 를 **한 번도** 띄우지 못한 채 조용히 멈춰 있었다.
            # 이 대기의 목적은 "사람이 지금 편집 중일 때 충돌하지 않는 것"이므로, 워킹트리가
            # 전혀 변하지 않은 채 반복되면 사람이 편집 중인 게 아니다 — 그러면 진행한다.
            if ($dirty -eq $dirtySignature) { $unchangedDirtyWaits += 1 }
            else { $dirtySignature = $dirty; $unchangedDirtyWaits = 1 }

            if ($unchangedDirtyWaits -ge $MaxUnchangedDirtyWaits) {
                Write-RunnerLog "워킹트리가 dirty 하지만 $unchangedDirtyWaits 회 연속으로 내용이 전혀 변하지 않음 — 사람이 편집 중이 아니라고 보고 그대로 진행한다(무한 대기 방지). 현재 상태: $($dirty -replace '\s+', ' ')"
            } else {
                Write-RunnerLog "저장소에 커밋 안 된 변경이 있음(대화형 세션이 작업 중일 수 있음) — ${DirtyRetrySeconds}초 뒤 다시 확인 ($unchangedDirtyWaits/$MaxUnchangedDirtyWaits)."
                Start-Sleep -Seconds $DirtyRetrySeconds
                continue
            }
        } else {
            $dirtySignature = $null
            $unchangedDirtyWaits = 0
        }

        # 같은 초에 두 invocation 이 시작되면 예전엔 로그 파일 이름이 겹쳐 서로 덮어썼다
        # (2026-08-11 로그에 실제로 20260811-085932.log 가 두 번 나온다) — 순번을 붙여 분리한다.
        $timestamp = "{0}-{1:d3}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), ($iterationsThisLaunch + 1)
        $logFile = Join-Path $LogDir "$timestamp.log"
        $promptFile = Join-Path $LogDir "$timestamp.prompt.txt"
        Write-RunnerLog "Worker invocation 시작 #$($iterationsThisLaunch + 1) (log=$logFile, budget=`$$MaxBudgetUsd, timeout=${MaxRuntimeMinutes}분)"

        # 2026-08-11 버그 수정: 프롬프트를 -ArgumentList 배열 요소로 넘기면 Start-Process가
        # Windows용 단일 커맨드라인 문자열로 재조립하는 과정에서 멀티라인·특수문자가 포함된
        # 긴 문자열이 깨져(관측된 실패: "error: unknown option '--oneline'" — 프롬프트 안의
        # 예시 텍스트가 claude.exe 자체의 옵션으로 오인됨) 3회 연속 실패 후 STOP이 걸렸다.
        # 프롬프트를 파일로 써서 표준입력으로 리다이렉트하면(claude -p는 위치 인자가 없으면
        # stdin에서 프롬프트를 읽는다 — 직접 확인함) 커맨드라인 조립 자체를 우회한다.
        # -PromptOverrideFile 은 controlled test seam이다(평소엔 비어 있어 내장 프롬프트를 쓴다).
        if ($PromptOverrideFile -and (Test-Path $PromptOverrideFile)) {
            Copy-Item -Path $PromptOverrideFile -Destination $promptFile -Force
        } else {
            Set-Content -Path $promptFile -Value $prompt -Encoding utf8 -NoNewline
        }

        # Persistent Worker Session: 저장된 session_id가 있으면 이어받고(--resume), 없으면
        # 새로 시작하며 즉시 저장한다(프로세스가 죽어도 다음 반복이 무엇을 시도했는지 안다).
        $sessionId = Load-SessionId
        $isNewSession = $false
        if ($null -eq $sessionId) {
            $sessionId = [guid]::NewGuid().ToString()
            $isNewSession = $true
            Save-SessionId $sessionId
            Write-RunnerLog "저장된 Worker Session이 없음 — 새 session_id=$sessionId 로 시작."
        } else {
            Write-RunnerLog "기존 Worker Session을 이어받음(--resume) session_id=$sessionId"
        }
        $sessionArgs = if ($isNewSession) { @("--session-id", $sessionId) } else { @("--resume", $sessionId) }

        # 주의: 이 배열에 빈 문자열("") 요소를 넣지 마라(예: 과거 --tools "" 실험). Windows에서
        # Start-Process -ArgumentList가 배열을 커맨드라인 문자열로 재조립할 때 빈 문자열 요소를
        # 누락시켜 뒤따르는 모든 인자가 한 칸씩 밀리는 것을 2026-08-12 실제로 재현/확인함(그
        # 결과 --session-id/--resume가 전혀 다른 값으로 오인되어 엉뚱한 세션에 붙는 것까지
        # 확인) — 이전 "--oneline 오인식" 버그와 같은 계열의 함정이다.
        $argList = @(
            "-p",
            "--permission-mode", "auto",
            "--max-budget-usd", $MaxBudgetUsd,
            "--output-format", "json"
        ) + $sessionArgs
        if ($Model) { $argList += @("--model", $Model) }   # controlled test seam

        $proc = Start-Process -FilePath $ClaudeExe -ArgumentList $argList -WorkingDirectory $ProjectDir `
            -RedirectStandardInput $promptFile -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err" -PassThru -NoNewWindow

        # 2026-08-12 버그 수정: 예전엔 `Wait-Process -Timeout ... -PassThru` 의 반환값으로
        # 타임아웃을 판정했다. 그런데 -PassThru 는 **기다림이 실패해도** 프로세스 객체를 그대로
        # 돌려준다 — 그래서 `-not $finished` 가 참이 되는 일이 없었고, 강제 종료 분기 전체가
        # 죽은 코드였다. 실제 증상(2026-08-12 controlled test에서 재현): 5분 상한을 넘긴
        # invocation 이 죽지 않은 채 로그에는 `exit=`(빈 값)만 남고, Supervisor 는 다음
        # invocation 을 띄워 **같은 세션에 두 프로세스가 붙는** 상태가 됐다.
        # .NET 의 WaitForExit(ms) 는 timeout 여부를 bool 로 정확히 알려 준다.
        $exited = $proc.WaitForExit($MaxRuntimeMinutes * 60 * 1000)
        if (-not $exited) {
            Write-RunnerLog "이 invocation 이 ${MaxRuntimeMinutes}분 안에 안 끝나 강제 종료함(멈춰 버린 것으로 판단)."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            try { [void]$proc.WaitForExit(10000) } catch {}
            $exitCode = 124  # 관례적 timeout 코드
        } else {
            $exitCode = $proc.ExitCode
            if ($null -eq $exitCode) {
                # 정상 종료했는데 exit code 를 못 읽는 경우 — 성공으로 오인하지 않는다.
                Write-RunnerLog "경고: 프로세스가 종료했지만 exit code 를 읽지 못함 — 실패로 간주한다."
                $exitCode = 125
            }
        }

        # rate-limit/overload, 그리고 session resume 실패만 따로 잡는다 — 그 외 일반 실패는
        # 즉시 재시도하고 연속 3회 상한이 최종 안전망이다(사용자 지시 §3 — 일반 작업엔 idle
        # timer를 안 쓴다). resume 실패 시그니처는 2026-08-12 실제 CLI 호출로 확인함:
        # exit != 0, stdout 비어있음, stderr == "No conversation found with session ID: <id>".
        $isRateLimit = $false
        $isResumeFailure = $false
        if ($exitCode -ne 0) {
            $errText = ""
            if (Test-Path "$logFile.err") { $errText += Get-Content "$logFile.err" -Raw -ErrorAction SilentlyContinue }
            if (Test-Path $logFile) { $errText += Get-Content $logFile -Raw -ErrorAction SilentlyContinue }
            if ((-not $isNewSession) -and ($errText -match '(?i)No conversation found with session ID')) {
                $isResumeFailure = $true
            } elseif ($errText -match '(?i)rate.?limit|overloaded|429|503|529') {
                $isRateLimit = $true
            }
        }

        if ($isResumeFailure) {
            Write-RunnerLog "저장된 session_id=$sessionId 를 더 이상 resume할 수 없음(세션 인프라 문제 — 작업 실패 아님) — 지우고 다음 반복에서 새 Worker Session으로 즉시 재시작."
            Clear-SessionId
        }

        $iterationsThisLaunch += 1
        $state = Load-State  # 다른 반복이 건드리지 않았지만 최신 상태를 다시 읽는다
        if ($exitCode -eq 0) {
            $state.consecutiveFailures = 0
            $state.consecutiveRateLimitHits = 0
        } elseif ($isResumeFailure) {
            # consecutiveFailures도 rate-limit 카운터도 안 올린다 — session resume 인프라
            # 문제는 "이 작업이 틀렸다"는 신호가 아니고, 새 세션으로 즉시 재시도하면 되므로
            # 반복 상한을 소모시킬 이유가 없다(단, $iterationsThisLaunch 런어웨이 상한은 그대로 적용).
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

        # §11 이 요구하는 증거를 한 줄에 모은다: invocation 번호·session·exit code·재시도 사유·
        # Git SHA·PROJECT_COMPLETE 상태. secret 은 남기지 않는다(session_id 는 불투명 UUID).
        $headSha = (git -C $ProjectDir rev-parse --short HEAD 2>$null)
        $isComplete = Test-ProjectComplete
        Write-RunnerLog "Worker invocation 종료 #$iterationsThisLaunch exit=$exitCode session=$sessionId rateLimit=$isRateLimit resumeFailure=$isResumeFailure consecutiveFailures=$($state.consecutiveFailures) totalRuns=$($state.totalRuns) headSha=$headSha PROJECT_COMPLETE=$isComplete"
        if (-not $isComplete) {
            Write-RunnerLog "PROJECT_COMPLETE=false — 대기 없이 곧바로 다음 Worker invocation 을 시작한다(exit=$exitCode 는 종료 조건이 아니다)."
        }

        if ($isRateLimit) {
            $backoff = [Math]::Min($RateLimitBaseBackoffSeconds * [Math]::Pow(2, [int]$state.consecutiveRateLimitHits - 1), $RateLimitMaxBackoffSeconds)
            Write-RunnerLog "rate-limit/overload로 보임 — ${backoff}초 대기 후 재시도(진짜 기다릴 이유가 있는 경우만 백오프, 사용자 지시 §3)."
            Start-Sleep -Seconds $backoff
        }
        # 성공했거나(exit=0) 일반 실패/resume 실패면 sleep 없이 곧장 다음 반복으로 — 이것이 이 재설계의 핵심이다.
    }
} finally {
    # 잠금은 핸들로 잡고 있었다 — 먼저 닫아야 파일을 지울 수 있다. 프로세스가 크래시해
    # 여기까지 못 와도 OS 가 핸들을 회수하므로 stale lock 으로 남지 않는다.
    if ($lockStream) { try { $lockStream.Close() } catch {} }
    Remove-Item -Path $LockFile -Force -ErrorAction SilentlyContinue
    Write-RunnerLog "Supervisor 종료 PID=$PID (invocations=$iterationsThisLaunch)"
}
