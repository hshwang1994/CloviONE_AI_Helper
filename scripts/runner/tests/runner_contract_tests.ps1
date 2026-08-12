<#
.SYNOPSIS
  두 Supervisor(autonomous_runner.ps1 / product_audit_runner.ps1)의 상태 전이 controlled test.

.DESCRIPTION
  **실제 스크립트를 사본이 아니라 그대로** 실행한다. 대상 저장소만 격리된 scratch git 저장소로
  바꾼다(-ProjectDir). Claude 호출은 프로세스 경계 계약만 필요한 곳에서는 stub 프로세스로,
  순수 판정 로직은 함수 단위로 직접 검증한다.

  실 저장소는 절대 건드리지 않는다 — scratch 는 임시 폴더에 만들고 끝나면 지운다.

  실행:
    powershell -NoProfile -File scripts\runner\tests\runner_contract_tests.ps1     # 5.1
    pwsh       -NoProfile -File scripts\runner\tests\runner_contract_tests.ps1     # 7
    ... -Only T14            # 특정 테스트만
    ... -KeepWork            # 실패 원인 조사용으로 scratch 를 남긴다

  종료 코드: 0 = 전부 통과, 1 = 하나라도 실패.
#>

param(
    [string]$WorkRoot = "",
    [string]$Only = "",
    [switch]$KeepWork
)

$ErrorActionPreference = "Stop"
if (Test-Path Variable:\PSNativeCommandUseErrorActionPreference) {
    $global:PSNativeCommandUseErrorActionPreference = $false
}

# 이 파일은 scripts/runner/tests/ 에 있다 → 부모가 scripts/runner/
$RunnerDir = Split-Path -Parent $PSScriptRoot
$AutonomousScript = Join-Path $RunnerDir "autonomous_runner.ps1"
$AuditScript      = Join-Path $RunnerDir "product_audit_runner.ps1"
$CommonScript     = Join-Path $RunnerDir "runner_common.ps1"

foreach ($f in @($AutonomousScript, $AuditScript, $CommonScript)) {
    if (-not (Test-Path $f)) { throw "대상 스크립트를 찾을 수 없다: $f" }
}
. $CommonScript

if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    $WorkRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("clovir-runner-tests-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
}
$PsHost = (Get-Process -Id $PID).Path

$script:Pass = 0
$script:Fail = 0
$script:Results = New-Object System.Collections.Generic.List[string]

function Test-Case([string]$id, [string]$name, [scriptblock]$body) {
    if ($Only -and $id -ne $Only) { return }
    $repo = ""
    try {
        $repo = New-ScratchRepo $id
        & $body $repo
        $script:Pass++
        $script:Results.Add("PASS  $id  $name")
        Write-Host "PASS  $id  $name" -ForegroundColor Green
    } catch {
        $script:Fail++
        $msg = $_.Exception.Message
        $script:Results.Add("FAIL  $id  $name  -> $msg")
        Write-Host "FAIL  $id  $name" -ForegroundColor Red
        Write-Host "      $msg" -ForegroundColor Red
        if ($repo) { Write-Host "      scratch: $repo" -ForegroundColor DarkGray }
    }
}

function Assert([bool]$cond, [string]$msg) { if (-not $cond) { throw $msg } }
function Assert-Match([string]$text, [string]$pattern, [string]$msg) {
    if ($text -notmatch $pattern) { throw "$msg (패턴 '$pattern' 없음)" }
}
function Assert-NoMatch([string]$text, [string]$pattern, [string]$msg) {
    if ($text -match $pattern) { throw "$msg (패턴 '$pattern' 이 있으면 안 된다)" }
}

# ── scratch 저장소 ────────────────────────────────────────────────────────────
function New-ScratchRepo([string]$id) {
    $repo = Join-Path $WorkRoot $id
    New-Item -ItemType Directory -Force -Path $repo | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "app") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "docs\product-audit") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "var\stub") | Out-Null

    Set-Content -Path (Join-Path $repo ".gitignore") -Value "var/`n" -Encoding ascii
    Set-Content -Path (Join-Path $repo "app\main.py") -Value "print('product source')`n" -Encoding ascii
    Set-Content -Path (Join-Path $repo "docs\BACKLOG.md") -Value "# BACKLOG`n" -Encoding ascii
    Set-Content -Path (Join-Path $repo "docs\QA_COVERAGE.md") -Value "# QA`n" -Encoding ascii
    Set-Content -Path (Join-Path $repo "docs\DECISIONS.md") -Value "# DECISIONS`n" -Encoding ascii

    [void](Invoke-Git -RepoDir $repo "init" "-q")
    [void](Invoke-Git -RepoDir $repo "config" "user.email" "runner-test@example.invalid")
    [void](Invoke-Git -RepoDir $repo "config" "user.name" "runner test")
    [void](Invoke-Git -RepoDir $repo "config" "commit.gpgsign" "false")
    [void](Invoke-Git -RepoDir $repo "add" "-A")
    [void](Invoke-Git -RepoDir $repo "commit" "-q" "-m" "seed")

    # 주의: 함수 안의 모든 미할당 출력은 반환값에 섞인다. 여기서 한 글자라도 새면
    # $repo 가 배열이 되어 이후 모든 테스트가 엉뚱한 경로를 쓴다(실제로 한 번 당했다).
    New-StubClaude $repo | Out-Null
    # var/ 는 gitignore 대상이다 — 테스트 보조 파일이 dirty guard 를 건드리지 않게 한다.
    Set-Content -Path (Join-Path $repo "var\prompt_override.txt") -Value "TEST PROMPT" -Encoding ascii
    return $repo
}

# ── Claude stub ───────────────────────────────────────────────────────────────
# scenario.txt 의 N번째 줄이 N번째 invocation 의 시나리오다(모자라면 마지막 줄을 반복).
function New-StubClaude([string]$repo) {
    $stubDir = Join-Path $repo "var\stub"
    $ps1 = Join-Path $stubDir "claude_stub.ps1"
    $cmd = Join-Path $stubDir "claude_stub.cmd"

    $body = @'
$ErrorActionPreference = "Continue"
if (Test-Path Variable:\PSNativeCommandUseErrorActionPreference) { $global:PSNativeCommandUseErrorActionPreference = $false }
$repo    = (Get-Location).Path
$stubDir = Join-Path $repo "var\stub"
New-Item -ItemType Directory -Force -Path $stubDir | Out-Null

$counterFile = Join-Path $stubDir "counter.txt"
$n = 0
if (Test-Path $counterFile) { $n = [int](Get-Content $counterFile -Raw).Trim() }
$n = $n + 1
Set-Content -Path $counterFile -Value $n -Encoding ascii

Add-Content -Path (Join-Path $stubDir "args.log") -Value ("#{0} {1}" -f $n, ($args -join ' ')) -Encoding utf8
try { $stdin = [Console]::In.ReadToEnd() } catch { $stdin = "" }
Set-Content -Path (Join-Path $stubDir "last_prompt.txt") -Value $stdin -Encoding utf8
Add-Content -Path (Join-Path $stubDir "prompts.log") -Value ("=== #{0} ===" -f $n) -Encoding utf8
Add-Content -Path (Join-Path $stubDir "prompts.log") -Value $stdin -Encoding utf8

$scenarioFile = Join-Path $stubDir "scenario.txt"
$scenario = "success"
if (Test-Path $scenarioFile) {
    $lines = @(Get-Content $scenarioFile | Where-Object { $_.Trim() -ne "" })
    if ($lines.Count -gt 0) {
        if ($n -le $lines.Count) { $scenario = $lines[$n - 1].Trim() } else { $scenario = $lines[-1].Trim() }
    }
}

function Emit-Json([string]$subtype, [string]$isError, [string]$reason) {
    $json = '{"type":"result","subtype":"' + $subtype + '","is_error":' + $isError +
            ',"terminal_reason":"' + $reason + '","result":"stub",' +
            '"modelUsage":{"m":{"canonicalModel":"claude-stub-1"}}}'
    [Console]::Out.Write($json)
}
function Git-Q { & git -C $repo @args 2>&1 | Out-Null }

switch -Regex ($scenario) {
    '^success$'   { Emit-Json "success" "false" "completed"; exit 0 }
    '^fail$'      { [Console]::Error.Write("stub generic failure"); Emit-Json "error" "true" "error"; exit 2 }
    '^error-json$'{ Emit-Json "error_during_execution" "true" "error"; exit 0 }
    '^malformed$' { [Console]::Out.Write("{not json at all"); exit 0 }
    '^empty$'     { exit 0 }
    '^hang$'      { Start-Sleep -Seconds 600; exit 0 }
    '^ratelimit$' { [Console]::Error.Write("API Error: 429 Too Many Requests (rate_limit_error)"); exit 1 }
    '^resumefail$'{ [Console]::Error.Write("No conversation found with session ID: 00000000-0000-0000-0000-000000000000"); exit 1 }

    '^audit-good$' {
        Set-Content -Path (Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_STATE.md") -Value "# state`n" -Encoding utf8
        Add-Content -Path (Join-Path $repo "docs\BACKLOG.md") -Value "- audit note" -Encoding utf8
        Git-Q add "docs/product-audit/PRODUCT_AUDIT_STATE.md" "docs/BACKLOG.md"
        Git-Q commit -q -m "audit: allowed write"
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^audit-bad-worktree$' {
        Add-Content -Path (Join-Path $repo "app\main.py") -Value "# auditor touched product code" -Encoding utf8
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^audit-bad-commit-revert$' {
        # 금지 경로를 고쳐 커밋한 뒤 되돌려 커밋한다 → 순 변화 0. 예전 guard 가 놓치던 경로.
        Add-Content -Path (Join-Path $repo "app\main.py") -Value "# sneaky" -Encoding utf8
        Git-Q add "app/main.py"; Git-Q commit -q -m "sneaky change"
        $c = Get-Content (Join-Path $repo "app\main.py") | Where-Object { $_ -ne "# sneaky" }
        Set-Content -Path (Join-Path $repo "app\main.py") -Value $c -Encoding utf8
        Git-Q add "app/main.py"; Git-Q commit -q -m "revert sneaky"
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^audit-history-rewrite$' {
        $before = (& git -C $repo rev-parse HEAD 2>&1 | Out-String).Trim()
        Add-Content -Path (Join-Path $repo "docs\BACKLOG.md") -Value "- x" -Encoding utf8
        Git-Q add -A; Git-Q commit -q -m "tmp"
        Git-Q reset --hard $before
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^audit-premature-complete$' {
        Set-Content -Path (Join-Path $repo "var\product-audit\AUDIT_COMPLETE") -Value "다 했습니다" -Encoding utf8
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^audit-full-complete$' {
        & "$PSScriptRoot\make_valid_audit.ps1" -Repo $repo
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^impl-premature-complete$' {
        Set-Content -Path (Join-Path $repo "var\runner\PROJECT_COMPLETE") -Value "프로젝트 끝났습니다 $(Get-Date -Format o)" -Encoding utf8
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^impl-consume-complete$' {
        $req = Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED"
        $cyc = ""
        if (Test-Path $req) {
            $m = [regex]::Match((Get-Content $req -Raw), '(?im)^\s*cycle_id\s*=\s*(\S+)')
            if ($m.Success) { $cyc = $m.Groups[1].Value }
            Remove-Item $req -Force
        }
        Set-Content -Path (Join-Path $repo "var\product-audit\IMPLEMENTATION_CONSUMED") `
            -Value "cycle_id=$cyc`nconsumed_at=$(Get-Date -Format o)`nfinal_commit=abc1234`nverification=stub" -Encoding utf8
        Set-Content -Path (Join-Path $repo "var\runner\PROJECT_COMPLETE") -Value "완료 근거 $(Get-Date -Format o)" -Encoding utf8
        Emit-Json "success" "false" "completed"; exit 0
    }
    default { Emit-Json "success" "false" "completed"; exit 0 }
}
'@
    [System.IO.File]::WriteAllText($ps1, $body, (New-Object System.Text.UTF8Encoding($true)))

    $cmdBody = "@echo off`r`n`"$PsHost`" -NoProfile -ExecutionPolicy Bypass -File `"$ps1`" %*`r`nexit /b %ERRORLEVEL%`r`n"
    [System.IO.File]::WriteAllText($cmd, $cmdBody, (New-Object System.Text.ASCIIEncoding))

    # audit-full-complete 시나리오가 쓰는 헬퍼(유효한 Audit 산출물 일습을 만든다)
    $helper = Join-Path $stubDir "make_valid_audit.ps1"
    [System.IO.File]::WriteAllText($helper, (Get-ValidAuditMakerBody), (New-Object System.Text.UTF8Encoding($true)))
}

function Get-ValidAuditMakerBody {
@'
param([string]$Repo)
$ErrorActionPreference = "Continue"
if (Test-Path Variable:\PSNativeCommandUseErrorActionPreference) { $global:PSNativeCommandUseErrorActionPreference = $false }
$cyc = (Get-Content (Join-Path $Repo "var\product-audit\cycle.json") -Raw | ConvertFrom-Json)
$cid = $cyc.cycleId
$base = $cyc.baselineSha
$d = Join-Path $Repo "docs\product-audit"
$filler = ("이 문서는 controlled test 가 만든 유효 형식의 Audit 산출물이다. " * 20)

foreach ($n in @("PRODUCT_AUDIT_INVENTORY","PRODUCT_AUDIT_FEATURE_CONTRACTS","PRODUCT_AUDIT_FINDINGS","PRODUCT_AUDIT_REPORT")) {
    Set-Content -Path (Join-Path $d "$n.md") -Value "# $n`ncycle_id=$cid`n$filler" -Encoding utf8
}
Set-Content -Path (Join-Path $d "PRODUCT_AUDIT_STATE.md") -Value @"
# STATE
cycle_id=$cid
$filler
blind_pass=1 cycle_id=$cid new_critical_high_categories=0 at=$(Get-Date -Format o)
blind_pass=2 cycle_id=$cid new_critical_high_categories=0 at=$(Get-Date -Format o)
"@ -Encoding utf8

Set-Content -Path (Join-Path $d "PRODUCT_AUDIT_COVERAGE.md") -Value @"
# COVERAGE
$filler
<!-- COVERAGE-SUMMARY
cycle_id=$cid
total_cells=100
unseen=0
unseen_without_reason=0
static_only=20
observed=30
executed=40
blocked=5
not_applicable=5
-->
"@ -Encoding utf8

$rc = @"
# HANDOFF
cycle_id=$cid
$filler

<!-- PA-RC-BEGIN PA-RC-0001 -->
rc_id: PA-RC-0001
severity: High
priority: P1
confidence: Confirmed
problem: stub 이 만든 예시 Root Cause
expected: 기대 동작
actual: 실제 동작
intent_evidence: docs/BACKLOG.md
findings: F-001
feature_contracts: FC-001
routes: /me
frontend: Home.jsx
api: GET /api/home
backend: app/main.py
data: none
rbac: user
integration: none
state_transition: none
user_impact: 낮음
implementation_direction: 방향
constraints: CLAUDE.md 불변 규칙
regression_risk: 낮음
acceptance_criteria: 조건 1
required_tests: test_x
qa_gaps: QA-1
evidence_refs: FINDINGS#F-001
<!-- PA-RC-END -->
"@
Set-Content -Path (Join-Path $d "PRODUCT_AUDIT_HANDOFF.md") -Value $rc -Encoding utf8

& git -C $Repo add "docs/product-audit" 2>&1 | Out-Null
& git -C $Repo commit -q -m "audit: final docs" 2>&1 | Out-Null
$final = (& git -C $Repo rev-parse HEAD 2>&1 | Out-String).Trim()

Set-Content -Path (Join-Path $Repo "var\product-audit\IMPLEMENTATION_REQUIRED") -Value @"
cycle_id=$cid
created_at=$(Get-Date -Format o)
baseline_sha=$base
handoff=docs/product-audit/PRODUCT_AUDIT_HANDOFF.md
root_causes=1
audit_commit=$final
"@ -Encoding utf8

Set-Content -Path (Join-Path $Repo "var\product-audit\AUDIT_COMPLETE") -Value @"
cycle_id=$cid
baseline_sha=$base
final_commit=$final
implementation_required=true
root_causes=1
blind_reaudit_consecutive_clean=2
completed_at=$(Get-Date -Format o)
전수조사를 마쳤다(controlled test stub).
"@ -Encoding utf8
'@
}

function Set-Scenario([string]$repo, [string[]]$lines) {
    Set-Content -Path (Join-Path $repo "var\stub\scenario.txt") -Value ($lines -join "`n") -Encoding ascii
}
function Get-StubCmd([string]$repo)   { return (Join-Path $repo "var\stub\claude_stub.cmd") }
function Get-StubCount([string]$repo) {
    $f = Join-Path $repo "var\stub\counter.txt"
    if (-not (Test-Path $f)) { return 0 }
    return [int](Get-Content $f -Raw).Trim()
}
function Get-RunnerLog([string]$repo, [string]$which) {
    $p = if ($which -eq "audit") { Join-Path $repo "var\product-audit\runner.log" } else { Join-Path $repo "var\runner\runner.log" }
    return (Read-TextOrEmpty $p)
}

# ── 실제 스크립트 실행 ────────────────────────────────────────────────────────
# 같은 파라미터를 두 번 넘기면 PowerShell 이 바인딩 오류를 낸다 — 기본값 위에 override 를
# 병합한 뒤 한 번만 방출한다.
function Build-Args([string]$script, [string]$repo, [System.Collections.IDictionary]$defaults,
                    [hashtable]$extra, [string[]]$switches) {
    $merged = [ordered]@{}
    foreach ($k in $defaults.Keys) { $merged[$k] = $defaults[$k] }
    if ($extra) { foreach ($k in $extra.Keys) { $merged[$k] = $extra[$k] } }

    $exe = Get-StubCmd $repo
    if ($merged.Contains("ClaudeExe")) { $exe = [string]$merged["ClaudeExe"]; $merged.Remove("ClaudeExe") }

    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script,
           "-ProjectDir", $repo, "-ClaudeExe", $exe,
           "-PromptOverrideFile", (Join-Path $repo "var\prompt_override.txt"))
    foreach ($k in $merged.Keys) { $a += @("-$k", "$($merged[$k])") }
    if ($switches) { foreach ($s in $switches) { $a += "-$s" } }
    return $a
}

function Invoke-Autonomous([string]$repo, [hashtable]$extra) {
    $defaults = [ordered]@{
        MaxIterationsPerLaunch = 2; MaxRuntimeMinutes = 1; DirtyRetrySeconds = 1
        RateLimitBaseBackoffSeconds = 1; RateLimitMaxBackoffSeconds = 2
    }
    $a = Build-Args $AutonomousScript $repo $defaults $extra $null
    $out = & $PsHost @a 2>&1 | Out-String
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $out }
}
function Invoke-Audit([string]$repo, [hashtable]$extra, [string[]]$switches) {
    $defaults = [ordered]@{
        MaxIterationsPerLaunch = 2; MaxRuntimeMinutes = 1; DirtyRetrySeconds = 1; MaxDirtyWaits = 2
        RateLimitBaseBackoffSeconds = 1; RateLimitMaxBackoffSeconds = 2
    }
    $a = Build-Args $AuditScript $repo $defaults $extra $switches
    $out = & $PsHost @a 2>&1 | Out-String
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $out }
}

Write-Host ""
Write-Host "=== Runner contract tests  (PSVersion=$($PSVersionTable.PSVersion))  workRoot=$WorkRoot ===" -ForegroundColor Cyan
Write-Host ""

# ══════════════════════════════════════════════════════════════════════════════
# 1) 순수 판정 로직 — 프로세스 없이 직접 검증(실제 CLI 없이 확인 가능한 부분)
# ══════════════════════════════════════════════════════════════════════════════

Test-Case "T01" "Claude JSON exit resolution: success/error/malformed/empty/부분필드" {
    param($repo)
    $tmp = Join-Path $repo "var\json"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    function W([string]$n, [string]$c) { $p = Join-Path $tmp $n; [void](Write-TextFile $p $c); return $p }

    $r = Get-ClaudeJsonExitResolution (W "ok.json" '{"subtype":"success","is_error":false,"terminal_reason":"completed"}')
    Assert ($r.Resolved -and $r.ExitCode -eq 0) "명시적 success 3조건은 exit 0 으로 복구돼야 한다"

    foreach ($bad in @(
        '{"subtype":"success","is_error":false}',                                  # terminal_reason 없음
        '{"subtype":"success","terminal_reason":"completed"}',                     # is_error 없음
        '{"is_error":false,"terminal_reason":"completed"}',                        # subtype 없음
        '{"subtype":"success","is_error":false,"terminal_reason":"max_budget"}',   # 완료가 아님
        '{"subtype":"success","is_error":"false","terminal_reason":"completed"}'   # 문자열 false
    )) {
        $r2 = Get-ClaudeJsonExitResolution (W "p.json" $bad)
        Assert (-not ($r2.Resolved -and $r2.ExitCode -eq 0)) "세 조건이 전부 명시적으로 참이 아니면 success 로 복구하면 안 된다: $bad"
    }

    $r3 = Get-ClaudeJsonExitResolution (W "err.json" '{"subtype":"success","is_error":true,"terminal_reason":"completed"}')
    Assert ($r3.Resolved -and $r3.ExitCode -eq 1) "is_error=true 는 failure 로 확정돼야 한다"

    $r4 = Get-ClaudeJsonExitResolution (W "err2.json" '{"subtype":"error_during_execution","is_error":false}')
    Assert ($r4.Resolved -and $r4.ExitCode -eq 1) "error 계열 subtype 은 failure 로 확정돼야 한다"

    foreach ($u in @('{not json', '', '   ', '{"foo":1}')) {
        $r5 = Get-ClaudeJsonExitResolution (W "u.json" $u)
        Assert (-not $r5.Resolved) "판정 불가 JSON 은 unresolved 여야 한다: [$u]"
    }
    $r6 = Get-ClaudeJsonExitResolution (Join-Path $tmp "does-not-exist.json")
    Assert (-not $r6.Resolved) "파일이 없으면 unresolved 여야 한다"
}

Test-Case "T02" "state.json 손상/스키마 누락에서 죽지 않고 복구" {
    param($repo)
    $sf = Join-Path $repo "var\state.json"
    $defaults = [ordered]@{ consecutiveFailures = 0; consecutiveRateLimitHits = 0; totalRuns = 0 }

    [void](Write-TextFile $sf "{ this is not json")
    $s = Get-NormalizedState -Path $sf -Defaults $defaults
    Assert ($s.consecutiveFailures -eq 0) "손상된 state 는 기본값으로 복구돼야 한다"

    [void](Write-TextFile $sf '{"consecutiveFailures":7}')      # 나머지 키 없음
    $s2 = Get-NormalizedState -Path $sf -Defaults $defaults
    Assert ($s2.consecutiveFailures -eq 7) "기존 값은 보존돼야 한다"
    $s2.consecutiveRateLimitHits = 3      # 없는 속성 대입은 정규화 없으면 throw 한다
    $s2.totalRuns = 1
    Assert ($s2.consecutiveRateLimitHits -eq 3) "누락 키가 채워져 대입이 가능해야 한다"

    $s3 = Get-NormalizedState -Path (Join-Path $repo "var\no-such-state.json") -Defaults $defaults
    Assert ($s3.totalRuns -eq 0) "없는 파일도 기본값 객체를 돌려줘야 한다"
}

Test-Case "T03" "git 헬퍼가 PS5.1에서 terminating error 를 내지 않는다(없는 repo/잘못된 rev)" {
    param($repo)
    $r1 = Invoke-Git -RepoDir "C:\__no_such_repo_for_tests__" "rev-parse" "HEAD"
    Assert (-not $r1.Ok) "없는 저장소는 실패로 보고돼야 한다(예외로 죽으면 안 된다)"
    $r2 = Invoke-Git -RepoDir $repo "diff" "--name-only" "deadbeefdeadbeef..HEAD"
    Assert (-not $r2.Ok) "잘못된 rev 범위는 실패로 보고돼야 한다"
    $r3 = Invoke-Git -RepoDir $repo "status" "--porcelain"
    Assert ($r3.Ok) "정상 저장소의 status 는 성공해야 한다"
    Assert ((Get-GitHeadSha -RepoDir "C:\__no_such_repo_for_tests__") -eq "") "없는 저장소의 HEAD 는 빈 문자열이어야 한다"
}

Test-Case "T04" "두 Supervisor 스크립트가 UTF-8 BOM(5.1 파서 요구)을 유지한다" {
    param($repo)
    foreach ($f in @($AutonomousScript, $AuditScript, $CommonScript)) {
        $b = [System.IO.File]::ReadAllBytes($f)
        Assert ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) `
            "BOM 이 없으면 Windows PowerShell 5.1 이 한글 주석을 cp949 로 오독해 파싱이 깨진다: $f"
    }
}

# ══════════════════════════════════════════════════════════════════════════════
# 2) autonomous_runner.ps1 프로세스 상태 전이
# ══════════════════════════════════════════════════════════════════════════════

Test-Case "T10" "정상 exit=0 → 종료하지 않고 다음 invocation 을 즉시 시작" {
    param($repo)
    Set-Scenario $repo @("success")
    $r = Invoke-Autonomous $repo $null
    $log = Get-RunnerLog $repo "impl"
    Assert ((Get-StubCount $repo) -eq 2) "MaxIterations=2 이므로 Worker 가 두 번 떠야 한다(실제 $(Get-StubCount $repo))"
    Assert-Match $log 'exit=0 exitSource=os' "OS exit code 를 직접 읽어야 한다(.Handle 캐시 효과)"
    Assert-Match $log 'handleCached=True' "프로세스 핸들이 캐시돼야 한다"
    Assert-Match $log 'PROJECT_COMPLETE 없음 — 대기 없이' "exit=0 은 종료 조건이 아니어야 한다"
    Assert-NoMatch $log 'exit=125' "정상 종료가 125(판정불가)로 떨어지면 안 된다"
}

Test-Case "T11" "RUN CONTEXT 가 프롬프트에 주입된다" {
    param($repo)
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 })
    $p = Read-TextOrEmpty (Join-Path $repo "var\stub\last_prompt.txt")
    Assert-Match $p 'TEST PROMPT' "프롬프트 override 본문이 전달돼야 한다"
    Assert-Match $p 'runner=autonomous_runner\.ps1' "RUN CONTEXT 가 붙어야 한다"
    Assert-Match $p 'implementation_required=false' "Audit 계약 상태가 전달돼야 한다"
}

Test-Case "T12" "timeout → exit=124, 프로세스 트리 강제 종료, JSON fallback 미적용" {
    param($repo)
    Set-Scenario $repo @("hang")
    $r = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; MaxRuntimeMinutes = 0.05 }
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'exit=124 exitSource=timeout' "timeout 은 124/timeout 으로 기록돼야 한다"
    Assert-Match $log '프로세스 트리를 강제 종료' "트리 강제 종료 경로를 타야 한다"
    Assert-NoMatch $log 'claude-json-fallback' "timeout 에는 JSON fallback 을 적용하면 안 된다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 0 })
    Assert ($st.consecutiveFailures -eq 1) "timeout 은 일반 실패로 1회 계산돼야 한다"
}

Test-Case "T13" "rate limit → 실패 카운터를 올리지 않고 백오프" {
    param($repo)
    Set-Scenario $repo @("ratelimit")
    [void](Invoke-Autonomous $repo $null)
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'rateLimit=True' "rate-limit 으로 분류돼야 한다"
    Assert-Match $log '대기 후 재시도' "백오프가 적용돼야 한다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 0; consecutiveRateLimitHits = 0 })
    Assert ($st.consecutiveFailures -eq 0) "rate-limit 은 consecutiveFailures 를 올리면 안 된다"
    Assert ($st.consecutiveRateLimitHits -ge 2) "rate-limit 카운터는 올라가야 한다"
}

Test-Case "T14" "resume 실패 → 실패로 세지 않고 session_id 를 지우고 새 세션으로 즉시 재시작" {
    param($repo)
    [void](Write-TextFile (Join-Path $repo "var\runner\session_id.txt") ([guid]::NewGuid().ToString()))
    Set-Scenario $repo @("resumefail", "success")
    [void](Invoke-Autonomous $repo $null)
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'resumeFailure=True' "resume 실패를 감지해야 한다"
    Assert-Match $log '새 Worker Session 으로 즉시 재시작|저장된 Worker Session 이 없음' "세션을 새로 시작해야 한다"
    $args = Read-TextOrEmpty (Join-Path $repo "var\stub\args.log")
    Assert-Match $args '#1 .*--resume' "1회차는 --resume 이어야 한다"
    Assert-Match $args '#2 .*--session-id' "2회차는 새 --session-id 여야 한다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 0 })
    Assert ($st.consecutiveFailures -eq 0) "resume 실패는 작업 실패가 아니므로 카운터를 소모하면 안 된다"
}

Test-Case "T15" "연속 일반 실패 → AUTO_STOP(STOP 아님) 후 중단, 수동 재시작으로 복구" {
    param($repo)
    Set-Scenario $repo @("fail")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 5 })
    Assert (Test-Path (Join-Path $repo "var\runner\AUTO_STOP")) "연속 실패 상한에서 AUTO_STOP 이 생겨야 한다"
    Assert (-not (Test-Path (Join-Path $repo "var\runner\STOP"))) "스크립트는 절대 STOP 을 만들면 안 된다(사용자 전용)"

    Set-Scenario $repo @("success")
    $r2 = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }
    Assert-Match $r2.Output 'AUTO_STOP' "수동 재시작 시 흔적을 크게 알려야 한다"
    Assert (-not (Test-Path (Join-Path $repo "var\runner\AUTO_STOP"))) "재시작이 확인 역할을 하므로 정리돼야 한다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 9 })
    Assert ($st.consecutiveFailures -eq 0) "카운터가 0으로 복구돼야 한다"
}

Test-Case "T16" "사용자 STOP → Worker 0회, exit 3, 조용한 no-op 아님" {
    param($repo)
    [void](Write-TextFile (Join-Path $repo "var\runner\STOP") "사용자가 멈춤")
    $r = Invoke-Autonomous $repo $null
    Assert ($r.ExitCode -eq 3) "STOP 이면 exit 3 이어야 한다(실제 $($r.ExitCode))"
    Assert ((Get-StubCount $repo) -eq 0) "Worker 를 한 번도 띄우면 안 된다"
    Assert-Match $r.Output 'STOP 파일' "이유를 크게 출력해야 한다"
}

Test-Case "T17" "손상된 session_id 파일 → 새 세션으로 취급(영구 정지 없음)" {
    param($repo)
    [void](Write-TextFile (Join-Path $repo "var\runner\session_id.txt") "not-a-uuid!!")
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 })
    $args = Read-TextOrEmpty (Join-Path $repo "var\stub\args.log")
    Assert-Match $args '--session-id' "손상된 세션 파일은 새 세션으로 시작해야 한다"
    Assert-NoMatch $args '--resume' "손상된 값으로 resume 하면 안 된다"
}

Test-Case "T18" "dirty 워킹트리 → 내용이 변하지 않으면 상한 뒤 진행(무한 대기 없음)" {
    param($repo)
    Add-Content -Path (Join-Path $repo "app\main.py") -Value "# uncommitted" -Encoding utf8
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; MaxUnchangedDirtyWaits = 2 })
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log '내용이 전혀 변하지 않음' "유령 dirty 에서 빠져나와야 한다"
    Assert ((Get-StubCount $repo) -eq 1) "결국 Worker 가 떠야 한다"
}

Test-Case "T19" "두 Runner 동시 실행 차단(같은 lock 공유)" {
    param($repo)
    $lockFile = Join-Path $repo "var\runner\run.lock"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $lockFile) | Out-Null
    $held = Open-ExclusiveLock -LockFile $lockFile
    Assert ($held.Acquired) "테스트가 먼저 잠금을 잡아야 한다"
    try {
        Set-Scenario $repo @("success")
        $r1 = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }
        Assert-Match $r1.Output '이미 살아있는 Supervisor' "구현 Runner 가 물러나야 한다"
        $r2 = Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } $null
        Assert ($r2.ExitCode -eq 4) "Audit Runner 는 exit 4 로 물러나야 한다(실제 $($r2.ExitCode))"
        Assert-Match $r2.Output '동시에' "동시 실행 금지를 알려야 한다"
        Assert ((Get-StubCount $repo) -eq 0) "둘 다 Worker 를 띄우면 안 된다"
    } finally { Close-ExclusiveLock -Lock $held -LockFile $lockFile }
}

# ══════════════════════════════════════════════════════════════════════════════
# 3) product_audit_runner.ps1 — write guard / cycle / 완료 Gate
# ══════════════════════════════════════════════════════════════════════════════

Test-Case "T20" "Audit allowlist 안 write/commit 은 통과하고 계속 진행한다" {
    param($repo)
    Set-Scenario $repo @("audit-good")
    [void](Invoke-Audit $repo $null $null)
    $log = Get-RunnerLog $repo "audit"
    Assert-NoMatch $log 'AUDIT WRITE GUARD|write guard 위반' "허용 경로 변경은 위반이 아니다"
    Assert (-not (Test-Path (Join-Path $repo "var\product-audit\AUDIT_BLOCKED"))) "차단되면 안 된다"
    Assert ((Get-StubCount $repo) -eq 2) "계속 진행해야 한다"
}

Test-Case "T21" "Audit 이 제품 코드를 워킹트리에서 고치면 AUDIT_BLOCKED (자동 revert 없음)" {
    param($repo)
    Set-Scenario $repo @("audit-bad-worktree")
    [void](Invoke-Audit $repo $null $null)
    $blocked = Read-TextOrEmpty (Join-Path $repo "var\product-audit\AUDIT_BLOCKED")
    Assert ($blocked -ne "") "AUDIT_BLOCKED 가 생겨야 한다"
    Assert-Match $blocked 'app/main\.py' "어떤 경로가 변경됐는지 증거가 남아야 한다"
    $src = Read-TextOrEmpty (Join-Path $repo "app\main.py")
    Assert-Match $src 'auditor touched' "자동 revert 하면 안 된다(사용자 변경 보호)"
    Assert ((Get-StubCount $repo) -eq 1) "위반 즉시 멈춰야 한다"
}

Test-Case "T22" "commit 했다가 되돌린 금지 경로 변경도 탐지(순 변화 0) — 예전 guard 의 사각지대" {
    param($repo)
    Set-Scenario $repo @("audit-bad-commit-revert")
    [void](Invoke-Audit $repo $null $null)
    $blocked = Read-TextOrEmpty (Join-Path $repo "var\product-audit\AUDIT_BLOCKED")
    Assert ($blocked -ne "") "touch-and-revert 도 AUDIT_BLOCKED 여야 한다"
    Assert-Match $blocked 'commit:.*app/main\.py' "어느 커밋이 금지 경로를 건드렸는지 남아야 한다"
}

Test-Case "T23" "history rewrite(reset --hard)도 탐지" {
    param($repo)
    Set-Scenario $repo @("audit-history-rewrite")
    [void](Invoke-Audit $repo $null $null)
    $blocked = Read-TextOrEmpty (Join-Path $repo "var\product-audit\AUDIT_BLOCKED")
    Assert ($blocked -ne "") "이력 재작성은 AUDIT_BLOCKED 여야 한다"
    Assert-Match $blocked 'history-rewritten|reflog|rev-list-failed' "이력 무결성 위반 증거가 남아야 한다"
}

Test-Case "T24" "내용만 있고 근거 없는 AUDIT_COMPLETE 는 기계 Gate 가 거부하고 격리한다" {
    param($repo)
    Set-Scenario $repo @("audit-premature-complete", "success")
    [void](Invoke-Audit $repo $null $null)
    Assert (-not (Test-Path (Join-Path $repo "var\product-audit\AUDIT_COMPLETE"))) "가짜 marker 는 남아 있으면 안 된다"
    $q = @(Get-ChildItem (Join-Path $repo "var\product-audit\quarantine") -File -ErrorAction SilentlyContinue)
    Assert ($q.Count -ge 1) "거부된 marker 는 삭제가 아니라 격리돼야 한다"
    $rej = Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt")
    Assert-Match $rej 'cycle_id' "거부 사유가 기록돼야 한다"
    $log = Get-RunnerLog $repo "audit"
    Assert-Match $log 'Gate 거부' "거부가 로그에 남아야 한다"
    $prompts = Read-TextOrEmpty (Join-Path $repo "var\stub\prompts.log")
    Assert-Match $prompts '거부된 사유' "거부 사유가 다음 invocation 프롬프트로 되먹여져야 한다"
}

Test-Case "T25" "형식을 갖춘 AUDIT_COMPLETE 는 Gate 를 통과하고 Handoff 로 넘어간다" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    $r = Invoke-Audit $repo $null $null
    $log = Get-RunnerLog $repo "audit"
    Assert-Match $log 'AUDIT_COMPLETE Gate 통과' "유효한 marker 는 통과해야 한다: $log"
    Assert (Test-MarkerValid (Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED")) "구현 필요 marker 가 있어야 한다"
    Assert ((Get-StubCount $repo) -eq 1) "완료 후 추가 invocation 을 띄우면 안 된다"
}

Test-Case "T26" "Audit 완료 시 과거 PROJECT_COMPLETE 는 archive 후 제거된다" {
    param($repo)
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "var\runner") | Out-Null
    [void](Write-TextFile (Join-Path $repo "var\runner\PROJECT_COMPLETE") "예전에 완료했다고 적어 둔 내용")
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Assert (-not (Test-Path (Join-Path $repo "var\runner\PROJECT_COMPLETE"))) "새 Backlog 가 생겼으므로 과거 완료 marker 는 제거돼야 한다"
    $arch = @(Get-ChildItem (Join-Path $repo "var\product-audit") -Filter "previous_PROJECT_COMPLETE_*.txt" -ErrorAction SilentlyContinue)
    Assert ($arch.Count -ge 1) "제거 전에 archive 해야 한다"
}

Test-Case "T27" "-ResetAudit → 새 cycle_id, 과거 Cycle 의 AUDIT_COMPLETE 는 재사용되지 않는다" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    $c1 = (Read-TextOrEmpty (Join-Path $repo "var\product-audit\cycle.json") | ConvertFrom-Json).cycleId
    Assert (Test-Path (Join-Path $repo "var\product-audit\AUDIT_COMPLETE")) "1차 Cycle 은 완료 marker 를 가진다"

    Set-Scenario $repo @("success")
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } @("ResetAudit"))
    $c2 = (Read-TextOrEmpty (Join-Path $repo "var\product-audit\cycle.json") | ConvertFrom-Json).cycleId
    Assert ($c1 -ne $c2) "새 Cycle 은 다른 cycle_id 를 가져야 한다($c1 vs $c2)"
    Assert ((Get-StubCount $repo) -ge 2) "새 Cycle 은 과거 완료를 근거로 종료하지 않고 실제로 조사해야 한다"
}

Test-Case "T28" "과거 Cycle 의 AUDIT_COMPLETE 가 남아 있어도 cycle_id 불일치로 거부된다" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    $done = Read-TextOrEmpty (Join-Path $repo "var\product-audit\AUDIT_COMPLETE")
    Assert ($done -ne "") "1차 완료 marker 확보"

    # cycle 만 새로 만들고(=새 Cycle) 과거 marker 를 그대로 되살린다
    Remove-Item (Join-Path $repo "var\product-audit\cycle.json") -Force
    Set-Scenario $repo @("success")
    [void](Write-TextFile (Join-Path $repo "var\product-audit\AUDIT_COMPLETE") $done)
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } $null)
    $rej = Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt")
    Assert-Match $rej 'cycle_id' "과거 Cycle marker 는 cycle_id 불일치로 거부돼야 한다"
}

Test-Case "T29" "Audit 시작 전부터 있던 사용자 dirty 는 Audit 을 죽이지 않고 기록된다" {
    param($repo)
    Add-Content -Path (Join-Path $repo "app\main.py") -Value "# 사용자가 남겨 둔 변경" -Encoding utf8
    Set-Scenario $repo @("success")
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1; MaxDirtyWaits = 2 } $null)
    $log = Get-RunnerLog $repo "audit"
    Assert-Match $log '안정된 사전 상태' "사용자 dirty 는 사전 상태로 기록하고 진행해야 한다"
    Assert ((Get-StubCount $repo) -eq 1) "사용자 파일 하나 때문에 밤샘 Audit 이 죽으면 안 된다"
    $cy = Read-TextOrEmpty (Join-Path $repo "var\product-audit\cycle.json")
    Assert-Match $cy 'app/main\.py' "사전 dirty 가 cycle 에 기록돼야 한다"
    $p = Read-TextOrEmpty (Join-Path $repo "var\stub\last_prompt.txt")
    Assert-Match $p 'pre_existing_dirty_paths' "Worker 에게 그 한계를 알려야 한다"
}

# ══════════════════════════════════════════════════════════════════════════════
# 4) Audit → Implementation Handoff 소비
# ══════════════════════════════════════════════════════════════════════════════

Test-Case "T30" "IMPLEMENTATION_REQUIRED 가 유효하면 premature PROJECT_COMPLETE 를 차단한다" {
    param($repo)
    # 먼저 Audit 을 완주시켜 실제 Handoff/marker 를 만든다
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Assert (Test-MarkerValid (Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED")) "Handoff marker 준비"

    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("impl-premature-complete", "success")
    [void](Invoke-Autonomous $repo $null)
    Assert (-not (Test-Path (Join-Path $repo "var\runner\PROJECT_COMPLETE"))) "premature 완료 marker 는 격리돼야 한다"
    $rej = Read-TextOrEmpty (Join-Path $repo "var\runner\last_completion_rejection.txt")
    Assert-Match $rej 'IMPLEMENTATION_REQUIRED' "거부 사유가 Audit 계약이어야 한다"
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'PROJECT_COMPLETE Gate 거부' "거부가 로그에 남아야 한다"
    Assert ((Get-StubCount $repo) -eq 2) "거부 후 작업을 계속해야 한다"
}

Test-Case "T31" "Handoff 를 소진(CONSUMED)한 뒤의 PROJECT_COMPLETE 는 정상 종료" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("impl-consume-complete")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 3 })
    Assert (Test-MarkerValid (Join-Path $repo "var\runner\PROJECT_COMPLETE")) "정상 완료 marker 는 유지돼야 한다"
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'Gate 를 통과했습니다|Gate 통과' "Gate 를 통과해야 한다"
    Assert ((Get-StubCount $repo) -eq 1) "완료 뒤에는 더 띄우면 안 된다"
}

Test-Case "T32" "구현 Runner 가 Handoff 존재를 인지하고 프롬프트에 전달한다" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("success")
    $r = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }
    Assert-Match $r.Output 'Product Audit 이 넘긴 구현 계약' "시작 시 Handoff 를 크게 알려야 한다"
    $p = Read-TextOrEmpty (Join-Path $repo "var\stub\last_prompt.txt")
    Assert-Match $p 'implementation_required=true' "프롬프트에 계약 상태가 있어야 한다"
    Assert-Match $p 'handoff_path=docs/product-audit/PRODUCT_AUDIT_HANDOFF\.md' "Handoff 경로가 전달돼야 한다"
    Assert-Match $p 'audit_cycle_id=PA-' "cycle_id 가 전달돼야 한다"
}

Test-Case "T33" "IMPLEMENTATION_REQUIRED 는 있는데 Handoff 가 없으면 계약 오류로 알리고 계속한다" {
    param($repo)
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "var\product-audit") | Out-Null
    [void](Write-TextFile (Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED") "cycle_id=PA-x`nroot_causes=3")
    Set-Scenario $repo @("impl-premature-complete", "success")
    $r = Invoke-Autonomous $repo $null
    Assert-Match $r.Output '계약 오류' "Handoff 부재를 계약 오류로 알려야 한다"
    Assert (Test-MarkerValid (Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED")) "marker 를 임의로 지우면 안 된다"
    $rej = Read-TextOrEmpty (Join-Path $repo "var\runner\last_completion_rejection.txt")
    Assert-Match $rej 'PRODUCT_AUDIT_HANDOFF' "거부 사유에 Handoff 부재가 있어야 한다"
    Assert ((Get-StubCount $repo) -eq 2) "계약 오류가 있어도 독립 작업은 계속돼야 한다"
}

Test-Case "T34" "premature PROJECT_COMPLETE 반복 생성 → 무한 루프 대신 AUTO_STOP" {
    param($repo)
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "var\product-audit") | Out-Null
    [void](Write-TextFile (Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED") "cycle_id=PA-x`nroot_causes=3")
    [void](Write-TextFile (Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md") "cycle_id=PA-x")
    Set-Scenario $repo @("impl-premature-complete")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 10; MaxCompletionRejections = 3 })
    Assert (Test-Path (Join-Path $repo "var\runner\AUTO_STOP")) "반복 거부는 결국 AUTO_STOP 으로 끝나야 한다"
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log '완료 Gate 반복 거부 상한' "상한 도달이 로그에 남아야 한다"
}

# ══════════════════════════════════════════════════════════════════════════════
# 5) 전제조건 / 종료 코드 — 사람이 로그를 안 봐도 결과를 구분할 수 있어야 한다
# ══════════════════════════════════════════════════════════════════════════════

Test-Case "T40" "claude 실행 파일이 없으면 3회 헛돌지 않고 즉시 이유를 알리고 exit 7" {
    param($repo)
    $r1 = Invoke-Autonomous $repo @{ ClaudeExe = (Join-Path $repo "var\no_such_claude.cmd") }
    Assert ($r1.ExitCode -eq 7) "구현 Runner 는 exit 7 이어야 한다(실제 $($r1.ExitCode))"
    Assert-Match $r1.Output '전제조건' "왜 못 도는지 알려야 한다"
    Assert ((Get-StubCount $repo) -eq 0) "Worker 를 띄우면 안 된다"

    $r2 = Invoke-Audit $repo @{ ClaudeExe = (Join-Path $repo "var\no_such_claude.cmd") } $null
    Assert ($r2.ExitCode -eq 7) "Audit Runner 도 exit 7 이어야 한다(실제 $($r2.ExitCode))"
}

Test-Case "T41" "git 저장소가 아니면 전제조건 실패로 즉시 종료" {
    param($repo)
    # 반드시 scratch **저장소 바깥**이어야 한다. 저장소 하위 디렉터리는 git 이 부모 저장소를
    # 찾아내므로 `rev-parse --is-inside-work-tree` 가 성공한다(테스트가 실제로 그렇게 틀렸었다).
    $notRepo = Join-Path $WorkRoot "T41-notrepo"
    New-Item -ItemType Directory -Force -Path (Join-Path $notRepo "var") | Out-Null
    Copy-Item (Join-Path $repo "var\stub") (Join-Path $notRepo "var\stub") -Recurse -Force
    Copy-Item (Join-Path $repo "var\prompt_override.txt") (Join-Path $notRepo "var\prompt_override.txt") -Force
    $r = Invoke-Autonomous $notRepo $null
    Assert ($r.ExitCode -eq 7) "git 저장소가 아니면 exit 7 이어야 한다(실제 $($r.ExitCode))"
    Assert-Match $r.Output 'git 저장소가 아니거나' "이유가 명확해야 한다"
}

Test-Case "T42" "종료 코드로 상태를 구분한다: 정상/STOP/AUTO_STOP/BLOCKED" {
    param($repo)
    # 정상(테스트 상한 도달) = 0
    Set-Scenario $repo @("success")
    Assert ((Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }).ExitCode -eq 0) "정상 진행은 0"

    # 연속 실패 → AUTO_STOP = 6
    Set-Scenario $repo @("fail")
    $r = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 5 }
    Assert ($r.ExitCode -eq 6) "AUTO_STOP 은 exit 6 이어야 한다(실제 $($r.ExitCode))"

    # 사용자 STOP = 3
    [void](Write-TextFile (Join-Path $repo "var\runner\STOP") "멈춤")
    Assert ((Invoke-Autonomous $repo $null).ExitCode -eq 3) "STOP 은 exit 3"
    Remove-Item (Join-Path $repo "var\runner\STOP") -Force

    # Audit write guard 위반 → BLOCKED = 5
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("audit-bad-worktree")
    $ra = Invoke-Audit $repo $null $null
    Assert ($ra.ExitCode -eq 5) "AUDIT_BLOCKED 는 exit 5 여야 한다(실제 $($ra.ExitCode))"
    # 그리고 BLOCKED 상태로 다시 실행하면 실행하지 않고 5 로 끝난다
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    $rb = Invoke-Audit $repo $null $null
    Assert ($rb.ExitCode -eq 5) "BLOCKED 상태의 재실행도 exit 5"
    Assert ((Get-StubCount $repo) -eq 0) "BLOCKED 상태에서는 Worker 를 띄우면 안 된다"
}

Test-Case "T43" "Supervisor 가 호출한 셸의 CLOVIR_* 환경을 오염시키지 않는다" {
    param($repo)
    # 사용자의 실제 상황을 그대로 재현한다: 같은 PowerShell 창에서 Runner 를 돌리고(같은 프로세스),
    # Ctrl+C/종료 뒤 그 창에서 대화형 Claude 를 시작한다. Runner 가 자기 프로세스 환경에 넣은
    # CLOVIR_SUPERVISED 가 남아 있으면 그 대화형 세션이 supervised worker 로 오인되어 Stop hook 이
    # 사람의 작업을 막는다 — 2026-08-12 검수 세션이 실제로 그 상태였다.
    Set-Scenario $repo @("success")
    $probe = Join-Path $repo "var\env_probe.ps1"
    $body = @"
`$ErrorActionPreference = 'Continue'
# 깨끗한 사용자 셸을 시뮬레이션한다. 이 harness 자체가 오염된 셸에서 돌 수 있으므로
# (검수 세션이 실제로 그랬다) 명시적으로 지우지 않으면 단언이 무의미해진다.
Remove-Item Env:CLOVIR_SUPERVISED -ErrorAction SilentlyContinue
Remove-Item Env:CLOVIR_PRODUCT_AUDIT -ErrorAction SilentlyContinue
Remove-Item Env:CLOVIR_SUPERVISOR_PID -ErrorAction SilentlyContinue
& '$AutonomousScript' -ProjectDir '$repo' -ClaudeExe '$(Get-StubCmd $repo)' ``
    -PromptOverrideFile '$repo\var\prompt_override.txt' -MaxIterationsPerLaunch 1 ``
    -MaxRuntimeMinutes 1 -DirtyRetrySeconds 1 | Out-Null
'AFTER_IMPL supervised=[' + `$env:CLOVIR_SUPERVISED + '] audit=[' + `$env:CLOVIR_PRODUCT_AUDIT + ']'
& '$AuditScript' -ProjectDir '$repo' -ClaudeExe '$(Get-StubCmd $repo)' ``
    -PromptOverrideFile '$repo\var\prompt_override.txt' -MaxIterationsPerLaunch 1 ``
    -MaxRuntimeMinutes 1 -DirtyRetrySeconds 1 -MaxDirtyWaits 2 | Out-Null
'AFTER_AUDIT supervised=[' + `$env:CLOVIR_SUPERVISED + '] audit=[' + `$env:CLOVIR_PRODUCT_AUDIT + ']'
"@
    [System.IO.File]::WriteAllText($probe, $body, (New-Object System.Text.UTF8Encoding($true)))
    $out = & $PsHost -NoProfile -ExecutionPolicy Bypass -File $probe 2>&1 | Out-String

    Assert-Match $out 'AFTER_IMPL supervised=\[\] audit=\[\]' `
        "구현 Runner 가 끝난 뒤 호출한 셸에 CLOVIR_SUPERVISED 가 남으면 안 된다. 실제: $out"
    Assert-Match $out 'AFTER_AUDIT supervised=\[\] audit=\[\]' `
        "Audit Runner 가 끝난 뒤 호출한 셸에 CLOVIR_PRODUCT_AUDIT 가 남으면 안 된다. 실제: $out"
}

Test-Case "T44" "Stop hook: 죽은 Supervisor 가 남긴 환경 표시로 사람 세션을 붙잡지 않는다" {
    param($repo)
    # 환경 복원(T43)은 Ctrl+C 경로에서 보장되지 않는다. 그래서 hook 자체가 "표시 + 그 PID 가
    # 실제로 살아 있는가"를 함께 본다. 이 저장소의 실제 stop_guard.py 를 그대로 호출해 판정한다.
    $guard = Join-Path (Split-Path -Parent $RunnerDir) "runner\stop_guard.py"
    if (-not (Test-Path $guard)) { $guard = Join-Path $RunnerDir "stop_guard.py" }
    Assert (Test-Path $guard) "stop_guard.py 를 찾을 수 없다: $guard"

    function Invoke-Guard([hashtable]$envs, [string]$stdinJson) {
        $prev = @{}
        foreach ($k in @("CLOVIR_SUPERVISED", "CLOVIR_SUPERVISOR_PID")) {
            $prev[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
            Remove-Item -LiteralPath ("Env:" + $k) -ErrorAction SilentlyContinue
        }
        foreach ($k in $envs.Keys) { Set-Item -LiteralPath ("Env:" + $k) -Value $envs[$k] }
        try { $o = ($stdinJson | & python $guard 2>&1 | Out-String) } catch { $o = "EXC:$($_.Exception.Message)" }
        foreach ($k in @($prev.Keys)) {
            if ($null -eq $prev[$k]) { Remove-Item -LiteralPath ("Env:" + $k) -ErrorAction SilentlyContinue }
            else { Set-Item -LiteralPath ("Env:" + $k) -Value $prev[$k] }
        }
        return $o
    }
    $payload = '{"stop_hook_active": false}'

    # (a) 표시 없음 = 사람 세션 → 통과
    Assert-NoMatch (Invoke-Guard @{} $payload) 'decision' "표시가 없으면 아무 것도 하지 않아야 한다"

    # (b) 표시는 있는데 PID 가 없음(예전 Supervisor 가 셸에 남긴 흔적) → 통과
    Assert-NoMatch (Invoke-Guard @{ CLOVIR_SUPERVISED = "1" } $payload) 'decision' `
        "PID 가 없는 stale 표시로 사람 세션을 막으면 안 된다"

    # (c) 표시 + 죽은 PID → 통과
    Assert-NoMatch (Invoke-Guard @{ CLOVIR_SUPERVISED = "1"; CLOVIR_SUPERVISOR_PID = "999999" } $payload) 'decision' `
        "죽은 Supervisor PID 로 사람 세션을 막으면 안 된다"

    # (d) 표시 + 살아있는 PID + PROJECT_COMPLETE 없음 → 제동 1회
    Assert-Match (Invoke-Guard @{ CLOVIR_SUPERVISED = "1"; CLOVIR_SUPERVISOR_PID = "$PID" } $payload) '"decision"\s*:\s*"block"' `
        "살아있는 Supervisor 의 Worker 는 완료 marker 없이 끝내려 하면 제동해야 한다"

    # (e) 표시 + 살아있는 PID + stop_hook_active=true → 통과(무한 block 금지)
    Assert-NoMatch (Invoke-Guard @{ CLOVIR_SUPERVISED = "1"; CLOVIR_SUPERVISOR_PID = "$PID" } '{"stop_hook_active": true}') 'decision' `
        "이미 제동한 continuation 은 통과시켜야 한다"
}

# ══════════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "───────────────────────────────────────────────────────────────" -ForegroundColor Cyan
foreach ($r in $script:Results) {
    $c = if ($r.StartsWith("PASS")) { "Green" } else { "Red" }
    Write-Host $r -ForegroundColor $c
}
Write-Host "───────────────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host ("PSVersion={0}  PASS={1}  FAIL={2}" -f $PSVersionTable.PSVersion, $script:Pass, $script:Fail) `
    -ForegroundColor $(if ($script:Fail -eq 0) { "Green" } else { "Red" })

if (-not $KeepWork -and $script:Fail -eq 0) {
    try { Remove-Item -LiteralPath $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue } catch { }
} else {
    Write-Host "scratch 유지: $WorkRoot" -ForegroundColor DarkGray
}
exit $(if ($script:Fail -eq 0) { 0 } else { 1 })
