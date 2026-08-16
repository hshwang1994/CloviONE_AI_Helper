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
# PowerShell 의 -match 는 **대소문자를 구분하지 않는다.** 제품명(ClovirONE)과 경로 식별자
# (clovirone-web-assistant)를 구분하려면 반드시 -cnotmatch 여야 한다 — 안 그러면 정상적으로
# 남아 있어야 할 배포 경로가 "옛 제품명 잔존"으로 잘못 잡힌다.
function Assert-NoMatchCase([string]$text, [string]$pattern, [string]$msg) {
    if ($text -cmatch $pattern) { throw "$msg (대소문자 구분 패턴 '$pattern' 이 있으면 안 된다)" }
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

# ★ stdin 은 **반드시 UTF-8 로 명시 디코딩**한다. `[Console]::In` 은 콘솔 입력 인코딩(이 호스트는
#   cp949)으로 디코딩해서 한글 프롬프트가 통째로 깨진다 — 그러면 "프롬프트에 이 지시가 들어갔는가"
#   를 검증하는 테스트가 **런너 결함이 아니라 harness 결함으로** 실패한다. 실제 claude.exe 는
#   UTF-8 로 읽으므로(운영에서 한글 프롬프트가 정상 동작) 이쪽이 현실에 맞는 구현이다.
#   같은 이유로 기록도 BOM 없는 UTF-8 로 직접 쓴다(Add-Content -Encoding utf8 은 5.1에서 BOM을 넣는다).
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$stdin = ""
try {
    $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), $utf8NoBom)
    $stdin = $reader.ReadToEnd()
    $reader.Close()
} catch { $stdin = "" }
[System.IO.File]::AppendAllText((Join-Path $stubDir "args.log"), ("#{0} {1}`r`n" -f $n, ($args -join ' ')), $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $stubDir "last_prompt.txt"), $stdin, $utf8NoBom)
[System.IO.File]::AppendAllText((Join-Path $stubDir "prompts.log"), ("=== #{0} ===`r`n{1}`r`n" -f $n, $stdin), $utf8NoBom)

$scenarioFile = Join-Path $stubDir "scenario.txt"
$scenario = "success"
if (Test-Path $scenarioFile) {
    $lines = @(Get-Content $scenarioFile | Where-Object { $_.Trim() -ne "" })
    if ($lines.Count -gt 0) {
        if ($n -le $lines.Count) { $scenario = $lines[$n - 1].Trim() } else { $scenario = $lines[-1].Trim() }
    }
}

# 실제 Runner 는 --output-format stream-json 을 쓴다 → stub 도 NDJSON 으로 낸다.
# (마지막 유효 줄이 type=result 객체라는 계약을 end-to-end 로 검증하기 위함이다.)
function Emit-Line([string]$line) { [Console]::Out.WriteLine($line); [Console]::Out.Flush() }
function Emit-Json([string]$subtype, [string]$isError, [string]$reason) {
    Emit-Line '{"type":"system","subtype":"init","permissionMode":"bypassPermissions"}'
    Emit-Line '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read"}]}}'
    Emit-Line ('{"type":"result","subtype":"' + $subtype + '","is_error":' + $isError +
               ',"terminal_reason":"' + $reason + '","result":"stub","num_turns":3,"permission_denials":[],' +
               '"modelUsage":{"m":{"canonicalModel":"claude-stub-1"}}}')
}
function Git-Q { & git -C $repo @args 2>&1 | Out-Null }

switch -Regex ($scenario) {
    '^success$'   { Emit-Json "success" "false" "completed"; exit 0 }
    '^fail$'      { [Console]::Error.Write("stub generic failure"); Emit-Json "error" "true" "error"; exit 2 }
    '^error-json$'{ Emit-Json "error_during_execution" "true" "error"; exit 0 }
    '^malformed$' { [Console]::Out.Write("{not json at all"); exit 0 }
    '^empty$'     { exit 0 }
    '^hang$'      { Start-Sleep -Seconds 600; exit 0 }
    # 출력을 꾸준히 내면서 오래 도는 Worker — 활동 기반 idle timeout 이 이것을 죽이면 안 된다.
    # (실제 운영에서 240분 벽시계 timeout 이 일하는 Worker 를 자르던 병목의 회귀 테스트)
    '^slow-working$' {
        Emit-Line '{"type":"system","subtype":"init"}'
        for ($i = 0; $i -lt 10; $i++) {
            Emit-Line ('{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Edit"}]},"i":' + $i + '}')
            Start-Sleep -Milliseconds 900
        }
        Emit-Json "success" "false" "completed"; exit 0
    }
    # 워킹트리를 더럽힌 채 끝나는 Worker — 다음 회차가 "사람이 편집 중일지도" 라며 기다리면 안 된다.
    '^dirty-then-success$' {
        Add-Content -Path (Join-Path $repo "app\main.py") -Value "# worker left this uncommitted" -Encoding utf8
        Emit-Json "success" "false" "completed"; exit 0
    }
    '^ratelimit$' { [Console]::Error.Write("API Error: 429 Too Many Requests (rate_limit_error)"); exit 1 }
    '^network$'   { [Console]::Error.Write("fetch failed: ECONNRESET"); exit 1 }
    '^authfail$'  { [Console]::Error.Write("Authentication failed: invalid api key"); exit 1 }
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
    # 검증 재감사가 "새로 구현할 것 없음" 으로 끝나는 경우 — run_all 의 수렴 조건이다.
    '^audit-clean-complete$' {
        & "$PSScriptRoot\make_valid_audit.ps1" -Repo $repo -Clean
        Emit-Json "success" "false" "completed"; exit 0
    }
    # 사람 승인 대기로 미룬 항목이 있는 Handoff — 완료 Gate 가 거부해야 한다.
    '^audit-deferred-to-human$' {
        & "$PSScriptRoot\make_valid_audit.ps1" -Repo $repo -DeferToHuman
        Emit-Json "success" "false" "completed"; exit 0
    }
    # Worker 가 스스로 AUDIT_BLOCKED 를 기록 — 사람 없이 자동 복구돼야 한다.
    '^audit-selfblock$' {
        Set-Content -Path (Join-Path $repo "var\product-audit\AUDIT_BLOCKED") `
            -Value "blocked_at=now`nreason=브라우저를 못 띄워서 확인 불가" -Encoding utf8
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
        # visual_change_required 인 RC 수만큼 시각 검증을 했다고 남긴다(완료 Gate 가 대조한다).
        $hf = Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"
        $vc = 0
        if (Test-Path $hf) { $vc = ([regex]::Matches((Get-Content $hf -Raw), '(?im)^\s*visual_change_required\s*[:=]\s*true\s*$')).Count }
        Set-Content -Path (Join-Path $repo "var\product-audit\IMPLEMENTATION_CONSUMED") `
            -Value "cycle_id=$cyc`nconsumed_at=$(Get-Date -Format o)`nfinal_commit=abc1234`nverification=stub`nvisual_change_rcs=$vc`nvisually_verified_rcs=$vc" -Encoding utf8
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
param([string]$Repo, [switch]$Clean, [switch]$DeferToHuman)
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

$rcCount   = $(if ($Clean) { 0 } else { 1 })
$deferred  = $(if ($DeferToHuman) { 2 } else { 0 })

# ── Deep UI/UX Design Audit 판정 18종 ──
# 기본: dashboard 는 REDESIGN(PA-RC-0001 참조), 나머지는 근거 있는 KEEP.
# -Clean: 전부 KEEP(재설계 0건).
$surfaces = @("app-shell","global-header","sidebar","navigation-ia","dashboard","home",
              "admin-console","list-screens","detail-screens","table-screens","forms",
              "modal-drawer","settings","ai-assistant-chat","empty-state","error-state",
              "loading-state","key-workflows")
$long = "controlled test 가 만든 충분한 길이의 판정 근거 문장이다. 실제 화면을 보고 적은 것으로 간주한다."
$designBlocks = ""
foreach ($sf in $surfaces) {
    $isRedesign = ((-not $Clean) -and $sf -eq "dashboard")
    $v   = $(if ($isRedesign) { "REDESIGN" } else { "KEEP" })
    $rcl = $(if ($isRedesign) { "PA-RC-0001" } else { "해당 없음 — KEEP 이라 구현 계약이 필요 없다" })
    $designBlocks += @"

<!-- DESIGN-VERDICT-BEGIN $sf -->
surface: $sf
layout_family: $sf
deep_audited: true
skills_applied: ui-ux-pro-max, redesign-existing-projects, impeccable
verdict: $v
current_state: $sf 의 현재 구조를 실측한 내용이다. $long
user_problem: 사용자가 겪는 문제를 적은 것이다. $long
target_design: 처음부터 만든다면 이렇게 만든다는 목표 설계다. $long
rationale: 이 판정을 내린 근거다. $long
browser_evidence: dist/ui_qa/$sf-1920-light.png 및 3840 dark 스크린샷으로 확인했다. $long
rc_ids: $rcl
<!-- DESIGN-VERDICT-END -->
"@
}
Set-Content -Path (Join-Path $d "PRODUCT_AUDIT_DESIGN.md") -Value @"
# DESIGN
cycle_id=$cid
$filler
$designBlocks
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
l_axis_visual_observed=18
l_axis_deep_design_audited=18
l_axis_design_verdict_complete=18
-->
"@ -Encoding utf8

$rcBlock = @"

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
quality_rubric: ui-ux-pro-max — 정보 위계 3단계
evidence_refs: FINDINGS#F-001
current_state: 현재 Dashboard 는 13개 섹션이 같은 무게로 나열돼 있다. $long
user_problem: 지금 조치해야 할 것이 무엇인지 첫 화면에서 안 보인다. $long
design_verdict: REDESIGN
target_state: 조치 필요 항목이 최상단에 단독으로 보인다. $long
target_design: 상단 액션 존 + 3열 지표 + 하단 상세 링크 구조로 재구성한다. $long
visual_change_required: true
target_visual_delta: 섹션 13개 → 3개 존으로 줄고 스크롤 길이가 절반이 된다. $long
affected_surfaces: dashboard, home
affected_components: DashboardPage.jsx, MetricCard.jsx
workflow_change: 조치까지 클릭 3회 → 1회
navigation_impact: 없음 — 메뉴 구조는 그대로다
data_impact: 없음 — 같은 API 응답을 다르게 배치할 뿐이다
api_impact: 없음 — API 계약 변경 없음
rbac_impact: 없음 — 역할별 노출 규칙 유지
browser_verification: 1920/2560/3840 라이트·다크에서 스크린샷으로 스크롤 길이와 위계 확인
<!-- PA-RC-END -->
"@
$rc = @"
# HANDOFF
cycle_id=$cid

<!-- HANDOFF-SUMMARY
cycle_id=$cid
actionable_root_causes=$rcCount
redesign_root_causes=$rcCount
deferred_for_human_approval=$deferred
-->

$filler
$(if ($Clean) { "" } else { $rcBlock })
$(if ($DeferToHuman) { "RD-9 대시보드 재설계는 업무 흐름이 바뀌므로 사람 승인 필요 — 제안으로만 기록한다." } else { "" })
"@
Set-Content -Path (Join-Path $d "PRODUCT_AUDIT_HANDOFF.md") -Value $rc -Encoding utf8

& git -C $Repo add "docs/product-audit" 2>&1 | Out-Null
& git -C $Repo commit -q -m "audit: final docs" 2>&1 | Out-Null
$final = (& git -C $Repo rev-parse HEAD 2>&1 | Out-String).Trim()

if (-not $Clean) {
    Set-Content -Path (Join-Path $Repo "var\product-audit\IMPLEMENTATION_REQUIRED") -Value @"
cycle_id=$cid
created_at=$(Get-Date -Format o)
baseline_sha=$base
handoff=docs/product-audit/PRODUCT_AUDIT_HANDOFF.md
root_causes=$rcCount
audit_commit=$final
"@ -Encoding utf8
} else {
    Remove-Item (Join-Path $Repo "var\product-audit\IMPLEMENTATION_REQUIRED") -Force -ErrorAction SilentlyContinue
}

Set-Content -Path (Join-Path $Repo "var\product-audit\AUDIT_COMPLETE") -Value @"
cycle_id=$cid
baseline_sha=$base
final_commit=$final
implementation_required=$(if ($Clean) { 'false' } else { 'true' })
root_causes=$rcCount
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

# 테스트 기본값 주의:
#  - MaxConsecutiveFailures 를 3 으로 낮춘다. production 기본값(10)은 밤샘 실행이 순간적
#    네트워크 장애로 죽지 않게 하려는 값이고, 상태 전이 자체를 확인하는 테스트에는 3 이 낫다.
#    production 기본값이 실제로 높다는 것은 T52 가 따로 고정한다.
#  - DirtyQuietSeconds=0: 테스트가 방금 만든 dirty 파일도 "조용함"으로 보게 한다. dirty 대기
#    동작 자체는 T18/T18B/T18C 가 명시적인 값으로 검증한다.
#  - SkipTestServerProbe: controlled test 에서 실제 사내망 SSH 를 건드리지 않는다.
function Invoke-Autonomous([string]$repo, [hashtable]$extra) {
    $defaults = [ordered]@{
        MaxIterationsPerLaunch = 2; MaxRuntimeMinutes = 1; IdleTimeoutMinutes = 1
        ProgressIntervalSeconds = 1; DirtyPollSeconds = 1; DirtyQuietSeconds = 0; MaxDirtyWaits = 2
        MaxConsecutiveFailures = 3
        RateLimitBaseBackoffSeconds = 1; RateLimitMaxBackoffSeconds = 2
        NetworkBaseBackoffSeconds = 1; NetworkMaxBackoffSeconds = 2
        FailureBaseBackoffSeconds = 1; FailureMaxBackoffSeconds = 2
    }
    $a = Build-Args $AutonomousScript $repo $defaults $extra @("SkipTestServerProbe")
    $out = & $PsHost @a 2>&1 | Out-String
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $out }
}
function Invoke-Audit([string]$repo, [hashtable]$extra, [string[]]$switches) {
    $defaults = [ordered]@{
        MaxIterationsPerLaunch = 2; MaxRuntimeMinutes = 1; IdleTimeoutMinutes = 1
        ProgressIntervalSeconds = 1; DirtyRetrySeconds = 1; DirtyQuietSeconds = 0; MaxDirtyWaits = 2
        MaxConsecutiveFailures = 3
        RateLimitBaseBackoffSeconds = 1; RateLimitMaxBackoffSeconds = 2
        NetworkBaseBackoffSeconds = 1; NetworkMaxBackoffSeconds = 2
        FailureBaseBackoffSeconds = 1; FailureMaxBackoffSeconds = 2
    }
    $sw = @("SkipTestServerProbe")
    if ($switches) { $sw += $switches }
    $a = Build-Args $AuditScript $repo $defaults $extra $sw
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
    Assert-Match $log 'exit=0 class=ok exitSource=os' "OS exit code 를 직접 읽어야 한다(.Handle 캐시 효과)"
    Assert-Match $log 'handleCached=True' "프로세스 핸들이 캐시돼야 한다"
    Assert-Match $log 'PROJECT_COMPLETE 없음 — 대기 없이' "exit=0 은 종료 조건이 아니어야 한다"
    Assert-NoMatch $log 'exit=125' "정상 종료가 125(판정불가)로 떨어지면 안 된다"
    # NDJSON(stream-json) 마지막 줄에서 result 를 읽어 실제 모델까지 복구해야 한다
    Assert-Match $log 'actualModel=claude-stub-1' "stream-json 마지막 result 줄에서 modelUsage 를 읽어야 한다"
}

Test-Case "T11" "RUN CONTEXT 가 프롬프트에 주입된다" {
    param($repo)
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 })
    $p = Read-TextOrEmpty (Join-Path $repo "var\stub\last_prompt.txt")
    Assert-Match $p 'TEST PROMPT' "프롬프트 override 본문이 전달돼야 한다"
    Assert-Match $p 'runner=autonomous_runner\.ps1' "RUN CONTEXT 가 붙어야 한다"
    Assert-Match $p 'implementation_required=false' "Audit 계약 상태가 전달돼야 한다"
    Assert-Match $p 'resume_mode=COLD' "첫 회차는 COLD 로 접지해야 한다"
    Assert-Match $p 'test_server_authority=full' "TEST SERVER 자율 권한이 매 회차 전달돼야 한다"
    Assert-Match $p 'unresolved_backlog_index=\d+' "대형 문서 대신 쓸 compact index 가 전달돼야 한다"
    Assert (Test-Path (Join-Path $repo "var\runner\active_state.json")) "active state cache 가 만들어져야 한다"
    Assert (Test-Path (Join-Path $repo "var\runner\unresolved_index.json")) "unresolved index cache 가 만들어져야 한다"
}

Test-Case "T12" "hang(출력 없음) → idle timeout 으로 exit=124, 프로세스 트리 강제 종료, JSON fallback 미적용" {
    param($repo)
    Set-Scenario $repo @("hang")
    $r = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; MaxRuntimeMinutes = 0; IdleTimeoutMinutes = 0.05 }
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'exit=124 class=idle-timeout exitSource=timeout' "출력이 전혀 없는 hang 은 idle-timeout 으로 분류돼야 한다"
    Assert-Match $log '프로세스 트리를 강제 종료' "트리 강제 종료 경로를 타야 한다"
    Assert-NoMatch $log 'claude-json-fallback' "timeout 에는 JSON fallback 을 적용하면 안 된다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 0 })
    Assert ($st.consecutiveFailures -eq 1) "hang 은 일반 실패로 1회 계산돼야 한다"
}

Test-Case "T12B" "출력이 계속 나오는 긴 invocation 은 idle timeout 이 죽이지 않는다 (B1 회귀)" {
    param($repo)
    # 실제 운영에서 240분 벽시계 timeout 이 **커밋을 남기고 있던** Worker 를 세 번 연속 잘랐다.
    # idle timeout(3초)보다 훨씬 오래(약 9초) 도는 Worker 가 출력만 계속 내면 살아남아야 한다.
    Set-Scenario $repo @("slow-working")
    $r = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; MaxRuntimeMinutes = 0; IdleTimeoutMinutes = 0.05 }
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'exit=0 class=ok' "출력이 계속 나오는 동안에는 자르면 안 된다: $log"
    Assert-NoMatch $log 'exit=124' "활동 중인 Worker 를 timeout 으로 죽이면 안 된다"
    Assert-Match $log 'tools=\d+' "stream 이벤트에서 도구 사용 횟수를 관측해야 한다"

    # 진행 상황 heartbeat — "작업이 느림"과 "프로세스가 hang"을 사람이 구분할 수 있어야 한다.
    Assert-Match $r.Output '▶ #1' "진행 heartbeat 가 콘솔에 나와야 한다"
    Assert-Match $r.Output '경과 .*이벤트 \d+.*도구 \d+회' "heartbeat 에 경과/이벤트/도구 수가 있어야 한다"
    Assert-Match $r.Output '최근 Edit' "지금 무슨 도구를 쓰고 있는지 보여야 한다"
    Assert-Match $r.Output '마지막 활동 \d+초 전' "마지막 활동 시각이 보여야 hang 을 구분할 수 있다"
    # Claude JSON 전체를 콘솔에 덤프하지 않는다(로그 파일 redirect 안정성 유지)
    Assert-NoMatch $r.Output '"type":"assistant"' "stream 원본 JSON 을 콘솔에 덤프하면 안 된다"
}

Test-Case "T13" "rate limit → 실패 카운터를 올리지 않고 백오프" {
    param($repo)
    Set-Scenario $repo @("ratelimit")
    [void](Invoke-Autonomous $repo $null)
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'class=rate-limit' "rate-limit 으로 분류돼야 한다"
    Assert-Match $log '백오프|기다린다' "백오프가 적용돼야 한다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 0; consecutiveRateLimitHits = 0; consecutiveInfraRetries = 0 })
    Assert ($st.consecutiveFailures -eq 0) "rate-limit 은 consecutiveFailures 를 올리면 안 된다"
    Assert ($st.consecutiveRateLimitHits -ge 2) "rate-limit 카운터는 올라가야 한다"
    Assert ($st.consecutiveInfraRetries -ge 2) "인프라 재시도 카운터로도 상한이 걸려야 한다(무한 백오프 방지)"
}

Test-Case "T13B" "network/auth 는 rate-limit·일반 실패와 각각 다르게 분류된다" {
    param($repo)
    Set-Scenario $repo @("network")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 })
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'class=network' "일시적 네트워크 장애는 network 로 분류돼야 한다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\runner\state.json") -Defaults ([ordered]@{ consecutiveFailures = 0; consecutiveInfraRetries = 0 })
    Assert ($st.consecutiveFailures -eq 0) "네트워크 장애로 AUTO_STOP 카운터를 소모하면 안 된다(실제 밤샘 실행이 이걸로 죽었다)"
    Assert ($st.consecutiveInfraRetries -eq 1) "대신 인프라 카운터로 상한을 건다"

    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("authfail")
    $r2 = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }
    $log2 = Get-RunnerLog $repo "impl"
    Assert-Match $log2 'class=auth' "인증 실패는 auth 로 분류돼야 한다"
    Assert-Match $r2.Output '인증/자격증명' "사람이 봐야 하는 문제는 크게 알려야 한다"
}

Test-Case "T14" "resume 실패 → 실패로 세지 않고 session_id 를 지우고 새 세션으로 즉시 재시작" {
    param($repo)
    [void](Write-TextFile (Join-Path $repo "var\runner\session_id.txt") ([guid]::NewGuid().ToString()))
    Set-Scenario $repo @("resumefail", "success")
    [void](Invoke-Autonomous $repo $null)
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log 'class=resume-failure' "resume 실패를 감지해야 한다"
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

Test-Case "T18" "dirty: clean → 즉시 진행" {
    param($repo)
    Set-Scenario $repo @("success")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; DirtyQuietSeconds = 3600; DirtyPollSeconds = 5 })
    $sw.Stop()
    Assert ((Get-StubCount $repo) -eq 1) "clean 이면 Worker 가 떠야 한다"
    $log = Get-RunnerLog $repo "impl"
    Assert-NoMatch $log '사람이 편집 중으로 보임' "clean 인데 기다리면 안 된다"
}

Test-Case "T18B" "dirty: 고정된(오래된) dirty → 기다리지 않고 곧장 진행 (B2 회귀)" {
    param($repo)
    # 예전 판정은 서명이 N회 연속 같은지만 봤고, 그래서 고정 dirty 하나에 매 invocation 마다
    # 30+60+120+120=330초를 태웠다(실제 운영 로그에 두 구간 그대로 남아 있다).
    # 이제는 파일 mtime 이 오래됐으면 첫 확인에서 곧장 진행해야 한다.
    Add-Content -Path (Join-Path $repo "app\main.py") -Value "# stale uncommitted" -Encoding utf8
    $f = Get-Item (Join-Path $repo "app\main.py")
    $f.LastWriteTimeUtc = [DateTime]::UtcNow.AddHours(-2)     # 2시간 전에 마지막으로 편집됨
    Set-Scenario $repo @("success")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; DirtyQuietSeconds = 90; DirtyPollSeconds = 30; MaxDirtyWaits = 10 })
    $sw.Stop()
    Assert ((Get-StubCount $repo) -eq 1) "고정 dirty 에서도 Worker 가 떠야 한다"
    Assert ($sw.Elapsed.TotalSeconds -lt 25) "고정 dirty 때문에 기다리면 안 된다(경과 $([int]$sw.Elapsed.TotalSeconds)초)"
    $log = Get-RunnerLog $repo "impl"
    Assert-NoMatch $log '사람이 편집 중으로 보임' "mtime 이 오래된 dirty 를 사람 편집으로 오판하면 안 된다"
}

Test-Case "T18C" "dirty: 방금 수정된 파일 → 사람 편집으로 보고 기다린다(충돌 방지)" {
    param($repo)
    Add-Content -Path (Join-Path $repo "app\main.py") -Value "# being edited right now" -Encoding utf8
    Set-Scenario $repo @("success")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; DirtyQuietSeconds = 3600; DirtyPollSeconds = 2; MaxDirtyWaits = 3 })
    $sw.Stop()
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log '사람이 편집 중으로 보임' "방금 수정된 파일이 있으면 기다려야 한다"
    Assert ($sw.Elapsed.TotalSeconds -ge 4) "실제로 기다려야 한다(경과 $([int]$sw.Elapsed.TotalSeconds)초)"
    Assert-Match $log '무한 대기 방지' "그래도 상한에서는 진행해야 한다"
    Assert ((Get-StubCount $repo) -eq 1) "상한 뒤에는 결국 Worker 가 떠야 한다"
}

Test-Case "T18D" "dirty: 우리 Worker 가 남긴 dirty 는 다음 회차가 기다리지 않는다 (B2 핵심)" {
    param($repo)
    # 실제 운영에서 낭비된 5분 30초 x 2구간이 정확히 이 경우였다 — 우리가 죽인 우리 Worker 가
    # 남긴 파일을 다음 회차가 "사람이 편집 중일지도 모른다"며 기다렸다.
    Set-Scenario $repo @("dirty-then-success", "success")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 2; DirtyQuietSeconds = 3600; DirtyPollSeconds = 20; MaxDirtyWaits = 10 })
    $sw.Stop()
    Assert ((Get-StubCount $repo) -eq 2) "두 번째 invocation 이 떠야 한다(실제 $(Get-StubCount $repo))"
    Assert ($sw.Elapsed.TotalSeconds -lt 25) "우리가 만든 dirty 를 기다리면 안 된다(경과 $([int]$sw.Elapsed.TotalSeconds)초)"
    $log = Get-RunnerLog $repo "impl"
    Assert-NoMatch $log '사람이 편집 중으로 보임' "self-caused dirty 를 사람 편집으로 오판하면 안 된다"
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
    # MaxWriteGuardRecoveries=0 → 자동 복구 없이 즉시 수렴시켜 **탐지 자체**를 검증한다.
    # (자동 복구 경로는 T69 가 따로 본다.)
    [void](Invoke-Audit $repo @{ MaxWriteGuardRecoveries = 0 } $null)
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
    [void](Invoke-Audit $repo @{ MaxWriteGuardRecoveries = 0 } $null)
    $blocked = Read-TextOrEmpty (Join-Path $repo "var\product-audit\AUDIT_BLOCKED")
    Assert ($blocked -ne "") "touch-and-revert 도 AUDIT_BLOCKED 여야 한다"
    Assert-Match $blocked 'commit:.*app/main\.py' "어느 커밋이 금지 경로를 건드렸는지 남아야 한다"
}

Test-Case "T23" "history rewrite(reset --hard)도 탐지" {
    param($repo)
    Set-Scenario $repo @("audit-history-rewrite")
    [void](Invoke-Audit $repo @{ MaxWriteGuardRecoveries = 0 } $null)
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
    $ra = Invoke-Audit $repo @{ MaxWriteGuardRecoveries = 0 } $null
    Assert ($ra.ExitCode -eq 5) "AUDIT_BLOCKED 는 exit 5 여야 한다(실제 $($ra.ExitCode))"
    # 그리고 BLOCKED 상태로 다시 실행하면 실행하지 않고 5 로 끝난다
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    $rb = Invoke-Audit $repo @{ MaxWriteGuardRecoveries = 0; MaxBlockedRecoveries = 0 } $null
    Assert ($rb.ExitCode -eq 5) "BLOCKED 상태의 재실행도 exit 5"
    Assert ((Get-StubCount $repo) -eq 0) "BLOCKED 상태에서는 Worker 를 띄우면 안 된다"
}

Test-Case "T46" "진척(커밋)이 있으면 exit!=0 이어도 연속 실패로 세지 않는다" {
    param($repo)
    # AUTO_STOP 의 의미는 "종료 코드가 0이 아니다"가 아니라 "진척이 없다"여야 한다.
    # 시나리오: 허용 경로에 커밋을 남기고 exit 2 로 끝나는 Worker.
    Set-Content -Path (Join-Path $repo "var\stub\scenario.txt") -Value "audit-good-then-fail" -Encoding ascii
    $stub = Join-Path $repo "var\stub\claude_stub.ps1"
    $t = [System.IO.File]::ReadAllText($stub, [System.Text.Encoding]::UTF8)
    $t = $t.Replace("    '^audit-good$' {", @"
    '^audit-good-then-fail$' {
        Set-Content -Path (Join-Path `$repo "docs\product-audit\PRODUCT_AUDIT_STATE.md") -Value "# state`n" -Encoding utf8
        Git-Q add "docs/product-audit/PRODUCT_AUDIT_STATE.md"
        Git-Q commit -q -m "audit: progress then fail"
        [Console]::Error.Write("network blip"); exit 2
    }
    '^audit-good$' {
"@)
    [System.IO.File]::WriteAllText($stub, $t, (New-Object System.Text.UTF8Encoding($true)))

    # 1회만 돈다: 같은 시나리오가 두 번째로 돌면 커밋할 내용이 없어 진척이 안 생기고,
    # 그건 이 테스트가 보려는 것이 아니다.
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1; FailureBaseBackoffSeconds = 1; FailureMaxBackoffSeconds = 1 } $null)
    $log = Get-RunnerLog $repo "audit"
    Assert-Match $log '진척이 있으므로 연속 실패로 세지 않는다' "커밋을 남긴 invocation 은 실패 사슬을 끊어야 한다"
    $st = Get-NormalizedState -Path (Join-Path $repo "var\product-audit\state.json") -Defaults ([ordered]@{ consecutiveFailures = 9 })
    Assert ($st.consecutiveFailures -eq 0) "진척이 있었으므로 연속 실패는 0이어야 한다(실제 $($st.consecutiveFailures))"
    Assert (-not (Test-Path (Join-Path $repo "var\product-audit\AUTO_STOP"))) "진척이 있는 한 AUTO_STOP 되면 안 된다"
}

Test-Case "T47" "진척 없는 일반 실패는 즉시 재시도하지 않고 간격을 둔다" {
    param($repo)
    # 예전엔 대기가 0이라 네트워크가 잠깐 끊기면 몇 초 만에 3연속 실패 → AUTO_STOP 이었다.
    Set-Scenario $repo @("fail")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 3; FailureBaseBackoffSeconds = 2; FailureMaxBackoffSeconds = 4 })
    $sw.Stop()
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log '초 대기 후 재시도\(순간 장애를 넘기기 위한 간격\)' "일반 실패에도 재시도 간격이 있어야 한다"
    Assert ($sw.Elapsed.TotalSeconds -ge 4) "실제로 대기해야 한다(경과 $([int]$sw.Elapsed.TotalSeconds)초)"
}

function New-RunAllProbe([string]$repo, [string]$name, [string]$extra) {
    # 배열 인자는 argv 로 넘기면 앞의 '-' 때문에 파라미터로 오인된다 — probe 스크립트 안에서
    # 진짜 PowerShell 배열로 넘긴다. 상한을 반드시 준다: 무제한으로 두면 Gate 가 한 번만
    # 어긋나도 테스트가 영원히 돈다(실제로 스위트를 10분 타임아웃시켰다).
    $probe = Join-Path $repo "var\$name.ps1"
    $body = @"
& '$(Join-Path $RunnerDir "run_all.ps1")' -ProjectDir '$repo' -ClaudeExe '$(Get-StubCmd $repo)' ``
    -RetryWaitMinutes 0.01 $extra ``
    -AuditArgs @('-MaxIterationsPerLaunch','1','-IdleTimeoutMinutes','1','-DirtyRetrySeconds','1','-DirtyQuietSeconds','0','-MaxDirtyWaits','2','-SkipTestServerProbe') ``
    -ImplementArgs @('-MaxIterationsPerLaunch','1','-IdleTimeoutMinutes','1','-DirtyPollSeconds','1','-DirtyQuietSeconds','0','-SkipTestServerProbe')
"EXITCODE=`$LASTEXITCODE"
"@
    [System.IO.File]::WriteAllText($probe, $body, (New-Object System.Text.UTF8Encoding($true)))
    return $probe
}

Test-Case "T48" "run_all: Audit 완료 → 구현 → 재감사까지 사람 없이 이어진다" {
    param($repo)
    # audit-full-complete → impl-consume-complete → (검증 재감사) audit-full-complete-clean
    Set-Scenario $repo @("audit-full-complete", "impl-consume-complete", "audit-clean-complete")
    $probe = New-RunAllProbe $repo "runall_probe" "-MaxCycles 3"
    $out = & $PsHost -NoProfile -ExecutionPolicy Bypass -File $probe 2>&1 | Out-String
    $code = if ($out -match 'EXITCODE=(-?\d+)') { [int]$Matches[1] } else { -999 }
    Assert-Match $out 'PHASE 1 \(Product Audit\) 완료' "Audit 완료를 알려야 한다"
    Assert (Test-MarkerValid (Join-Path $repo "var\runner\PROJECT_COMPLETE")) "구현까지 자동으로 이어져야 한다. 출력: $out"
    Assert-Match $out 'PHASE 3' "구현 완료 뒤 검증 재감사로 넘어가야 한다(예전엔 이 단계가 아예 없었다)"
    Assert-Match $out '전체 수렴 완료' "재감사가 깨끗하면 수렴으로 끝나야 한다"
    Assert ($code -eq 0) "수렴 완료는 exit 0 이어야 한다(실제 $code). 출력: $out"
}

Test-Case "T49" "run_all: marker 없이 끝난 Phase 를 사람 없이 자동 재시도한다 (Human Gate 제거)" {
    param($repo)
    # 예전 구조: marker 없이 exit 0 이면 "완료가 아니라 중단입니다 / 다시 실행하세요" → exit 10.
    # 그 재실행이 사람 손이었다. 이제는 전략을 바꿔 가며 스스로 다시 돈다.
    # 1~2회차는 marker 를 안 만들고, 3회차에 만든다.
    Set-Scenario $repo @("success", "success", "audit-full-complete", "impl-consume-complete", "audit-clean-complete")
    $probe = New-RunAllProbe $repo "runall_probe2" "-MaxCycles 3 -MaxPhaseRetries 5"
    $out = & $PsHost -NoProfile -ExecutionPolicy Bypass -File $probe 2>&1 | Out-String
    $code = if ($out -match 'EXITCODE=(-?\d+)') { [int]$Matches[1] } else { -999 }

    Assert-NoMatch $out '완료가 아니라 중단입니다' "사람에게 재실행을 요구하면 안 된다"
    Assert-NoMatch $out '다시 실행하세요' "사람에게 재실행을 요구하면 안 된다"
    Assert-Match $out '다시 시도합니다.*사람을 기다리지 않습니다' "스스로 재시도한다고 알려야 한다"
    Assert ($code -ne 10) "예전의 '중단' exit 10 경로가 남아 있으면 안 된다"
    Assert (Test-MarkerValid (Join-Path $repo "var\runner\PROJECT_COMPLETE")) "재시도 끝에 완료까지 가야 한다. 출력: $out"
}

Test-Case "T49B" "run_all: 재감사에서 새 Root Cause 가 나오면 자동으로 구현으로 되돌아간다" {
    param($repo)
    # Audit → 구현(완료) → 재감사가 **또 구현거리를 냄** → 구현 → 재감사(깨끗) → 수렴.
    Set-Scenario $repo @("audit-full-complete", "impl-consume-complete",
                         "audit-full-complete", "impl-consume-complete", "audit-clean-complete")
    $probe = New-RunAllProbe $repo "runall_probe3" "-MaxCycles 4"
    $out = & $PsHost -NoProfile -ExecutionPolicy Bypass -File $probe 2>&1 | Out-String
    $code = if ($out -match 'EXITCODE=(-?\d+)') { [int]$Matches[1] } else { -999 }
    $cycles = ([regex]::Matches($out, '=== CYCLE \d+')).Count
    Assert ($cycles -ge 3) "재감사 → 구현 → 재감사로 최소 3 Cycle 돌아야 한다(실제 $cycles). 출력: $out"
    Assert-Match $out 'Audit 이 구현 계약을 넘겼습니다' "재감사가 낸 구현거리를 다시 구현해야 한다"
    Assert ($code -eq 0) "결국 수렴해야 한다(실제 $code)"
}

Test-Case "T45" "MaxBudgetUsd=0 이면 --max-budget-usd 를 argv 에 붙이지 않는다(일을 자르지 않음)" {
    param($repo)
    # 예산 상한은 지출 가드가 아니라 실질적으로 '일을 문장 중간에서 자르는' 장치였다.
    # 0 = 무제한이 argv 수준에서 실제로 관철되는지 stub 의 args.log 로 확인한다.
    # 0 을 CLI 에 그대로 넘기면 "$0 예산"으로 해석될 수 있으므로 **플래그 자체가 없어야** 한다.
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; MaxBudgetUsd = 0 })
    $a = Read-TextOrEmpty (Join-Path $repo "var\stub\args.log")
    Assert-NoMatch $a '--max-budget-usd' "0 이면 플래그가 아예 없어야 한다. 실제 argv: $a"
    Assert-Match $a '\-p .*--output-format stream-json --verbose' "나머지 인자는 그대로여야 한다"

    # 양수를 주면 예전처럼 상한이 걸린다(선택지가 사라지지 않았음을 고정한다)
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1; MaxBudgetUsd = 7 })
    $a2 = Read-TextOrEmpty (Join-Path $repo "var\stub\args.log")
    Assert-Match $a2 '--max-budget-usd 7' "양수는 그대로 전달돼야 한다"

    # Audit Runner 도 같은 규칙
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Remove-Item (Join-Path $repo "var\stub\args.log") -Force -ErrorAction SilentlyContinue
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1; MaxBudgetUsd = 0 } $null)
    $a3 = Read-TextOrEmpty (Join-Path $repo "var\stub\args.log")
    Assert-NoMatch $a3 '--max-budget-usd' "Audit Runner 도 0 이면 플래그가 없어야 한다. 실제: $a3"
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
    -IdleTimeoutMinutes 1 -DirtyPollSeconds 1 -DirtyQuietSeconds 0 -SkipTestServerProbe | Out-Null
'AFTER_IMPL supervised=[' + `$env:CLOVIR_SUPERVISED + '] audit=[' + `$env:CLOVIR_PRODUCT_AUDIT + ']'
& '$AuditScript' -ProjectDir '$repo' -ClaudeExe '$(Get-StubCmd $repo)' ``
    -PromptOverrideFile '$repo\var\prompt_override.txt' -MaxIterationsPerLaunch 1 ``
    -IdleTimeoutMinutes 1 -DirtyRetrySeconds 1 -DirtyQuietSeconds 0 -MaxDirtyWaits 2 -SkipTestServerProbe | Out-Null
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
# 6) 2026-08-13 처리량 개선의 계약 — 여기가 회귀하면 밤샘 실행이 다시 느려지거나 죽는다
# ══════════════════════════════════════════════════════════════════════════════

function Get-ScriptParamDefault([string]$path, [string]$name) {
    $errors = $null; $tokens = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    $p = $ast.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -eq $name }
    if (-not $p) { return $null }
    if ($null -eq $p.DefaultValue) { return $null }
    return $p.DefaultValue.Extent.Text
}

Test-Case "T50" "stream-json(NDJSON) 출력에서도 종료 판정·모델·통계를 정확히 읽는다" {
    param($repo)
    $tmp = Join-Path $repo "var\nd"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    function W2([string]$n, [string]$c) { $p = Join-Path $tmp $n; [void](Write-TextFile $p $c); return $p }

    $nd = @(
        '{"type":"system","subtype":"init","permissionMode":"bypassPermissions"}'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Edit"}]}}'
        '{"type":"result","subtype":"success","is_error":false,"terminal_reason":"completed","num_turns":42,"total_cost_usd":1.25,"permission_denials":[],"modelUsage":{"a":{"canonicalModel":"claude-sonnet-5"}}}'
    ) -join "`n"
    $p = W2 "ok.ndjson" $nd
    $r = Get-ClaudeJsonExitResolution $p
    Assert ($r.Resolved -and $r.ExitCode -eq 0) "NDJSON 마지막 result 줄로 success 를 확정해야 한다"
    Assert ((Get-ActualModel $p) -eq "claude-sonnet-5") "NDJSON 에서도 실제 모델을 읽어야 한다"
    $s = Get-ClaudeResultStats $p
    Assert ($s.NumTurns -eq 42) "turn 수를 읽어야 한다(실제 $($s.NumTurns))"

    # 중간 줄에 "success" 문자열이 있어도 마지막 result 가 error 면 실패로 확정한다
    $nd2 = @(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"success!"}]}}'
        '{"type":"result","subtype":"error_during_execution","is_error":true,"terminal_reason":"error"}'
    ) -join "`n"
    $r2 = Get-ClaudeJsonExitResolution (W2 "err.ndjson" $nd2)
    Assert ($r2.Resolved -and $r2.ExitCode -eq 1) "마지막 result 줄이 판정 기준이어야 한다"

    # 잘린 NDJSON(강제 종료로 마지막 줄이 불완전) → 성공을 추측하면 안 된다
    $r3 = Get-ClaudeJsonExitResolution (W2 "cut.ndjson" ('{"type":"assistant"}' + "`n" + '{"type":"resu'))
    Assert (-not $r3.Resolved) "잘린 스트림에서 성공을 추측하면 안 된다"

    # 단일 JSON(구 --output-format json) 도 그대로 읽혀야 한다(하위 호환)
    $r4 = Get-ClaudeJsonExitResolution (W2 "single.json" '{"subtype":"success","is_error":false,"terminal_reason":"completed"}')
    Assert ($r4.Resolved -and $r4.ExitCode -eq 0) "구 단일 JSON 형식도 계속 읽혀야 한다"
}

Test-Case "T51" "rate limit 은 추측 백오프가 아니라 CLI 가 준 실제 reset 시각을 쓴다" {
    param($repo)
    $tmp = Join-Path $repo "var\rl"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $future = (Get-UnixNow) + 3600
    $nd = @(
        '{"type":"system","subtype":"init"}'
        ('{"type":"rate_limit_event","rate_limit_info":{"status":"rejected","resetsAt":' + $future +
         ',"rateLimitType":"seven_day","utilization":1.0}}')
        '{"type":"result","subtype":"error","is_error":true,"terminal_reason":"error"}'
    ) -join "`n"
    $p = Join-Path $tmp "rl.ndjson"
    [void](Write-TextFile $p $nd)

    $info = Get-RateLimitInfoFromLog $p
    Assert ($info.Found) "rate_limit_event 를 찾아야 한다"
    Assert ($info.ResetsAt -eq $future) "resetsAt(unix epoch)을 그대로 읽어야 한다(실제 $($info.ResetsAt))"
    Assert ($info.Type -eq "seven_day") "한도 종류를 읽어야 한다"

    # 이벤트가 없으면 0(모름)이어야 한다 — 추측하지 않는다
    $p2 = Join-Path $tmp "none.ndjson"
    [void](Write-TextFile $p2 '{"type":"result","subtype":"success","is_error":false,"terminal_reason":"completed"}')
    Assert (-not (Get-RateLimitInfoFromLog $p2).Found) "이벤트가 없으면 못 찾았다고 해야 한다"
    Assert ((Get-RateLimitResetFromText "그냥 실패 메시지") -eq 0) "텍스트에 근거가 없으면 시각을 지어내면 안 된다"
}

Test-Case "T52" "실패 유형 분류 — 인프라성 실패가 AUTO_STOP 카운터를 소모하지 않는다" {
    param($repo)
    $cases = @(
        @{ exit = 0;  prog = $false; err = "";                                    want = "ok";             counts = $false }
        @{ exit = 2;  prog = $true;  err = "network blip";                        want = "progress";       counts = $false }
        @{ exit = 1;  prog = $false; err = "API Error: 429 Too Many Requests";    want = "rate-limit";     counts = $false }
        @{ exit = 1;  prog = $false; err = "Error: overloaded_error 529";         want = "overload";       counts = $false }
        @{ exit = 1;  prog = $false; err = "fetch failed: ECONNRESET";            want = "network";        counts = $false }
        @{ exit = 1;  prog = $false; err = "Authentication failed: invalid token"; want = "auth";          counts = $true  }
        @{ exit = 2;  prog = $false; err = "some unexpected failure";             want = "generic";        counts = $true  }
    )
    foreach ($c in $cases) {
        $fc = Get-InvocationFailureClass -ExitCode $c.exit -Progressed $c.prog -IsNewSession $false `
            -TimeoutKind "" -Source "os" -StdErrText $c.err -StdOutText ""
        Assert ($fc.Class -eq $c.want) "'$($c.err)' 은 $($c.want) 로 분류돼야 한다(실제 $($fc.Class))"
        Assert ($fc.CountsAsFailure -eq $c.counts) "$($c.want) 의 AUTO_STOP 카운터 반영은 $($c.counts) 여야 한다"
    }
    # ★ 실측 기반 회귀: 정상 스트림에도 rate_limit_event(status=allowed_warning)가 섞여 온다.
    #   그 **JSON 키 이름** 때문에 무관한 실패가 rate-limit 으로 오분류되면, 실패 카운터가
    #   영원히 안 올라가고 백오프만 반복한다(= 진짜 실패를 숨긴다).
    $benignStream = '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed_warning",' +
                    '"resetsAt":1786744800,"rateLimitType":"seven_day","utilization":0.88}}'
    Assert (-not (Test-IsRateLimitFailure $benignStream)) "정상 rate_limit_event 를 rate-limit 실패로 보면 안 된다"
    $fcBenign = Get-InvocationFailureClass -ExitCode 2 -Progressed $false -IsNewSession $false -TimeoutKind "" `
        -Source "os" -StdErrText "TypeError: cannot read property" -StdOutText $benignStream
    Assert ($fcBenign.Class -eq "generic") "스트림에 rate_limit_event 가 있어도 무관한 실패는 generic 이어야 한다(실제 $($fcBenign.Class))"
    Assert ($fcBenign.CountsAsFailure) "그래야 진짜 실패가 숨지 않는다"
    # 반대로 진짜 차단 신호는 놓치지 않는다
    Assert (Test-IsRateLimitFailure '{"rate_limit_info":{"status":"rejected"}}') "실제 차단 status 는 잡아야 한다"
    Assert (Test-IsRateLimitFailure 'Claude usage limit reached') "사람이 읽는 한도 문구도 잡아야 한다"

    # resume 실패는 새 세션일 때는 resume 실패가 아니다(첫 호출에서 오분류 금지)
    $fcNew = Get-InvocationFailureClass -ExitCode 1 -Progressed $false -IsNewSession $true -TimeoutKind "" `
        -Source "os" -StdErrText "No conversation found with session ID: x" -StdOutText ""
    Assert ($fcNew.Class -ne "resume-failure") "새 세션에서는 resume 실패로 분류하면 안 된다"
    # hang 은 진짜 실패다
    $fcHang = Get-InvocationFailureClass -ExitCode 124 -Progressed $false -IsNewSession $false -TimeoutKind "idle" `
        -Source "timeout" -StdErrText "" -StdOutText ""
    Assert ($fcHang.Class -eq "idle-timeout" -and $fcHang.CountsAsFailure) "출력이 멈춘 hang 은 실패로 세야 한다"
}

Test-Case "T53" "같은 실패가 결정적으로 반복되면 무한 재시도 대신 증거를 남기고 수렴한다" {
    param($repo)
    # 인프라 유형은 AUTO_STOP 카운터를 안 쓰지만, **같은 지문**이 반복되면 결국 멈춰야 한다.
    Set-Scenario $repo @("network")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 10; MaxIdenticalFailures = 3; MaxConsecutiveFailures = 99 })
    $auto = Read-TextOrEmpty (Join-Path $repo "var\runner\AUTO_STOP")
    Assert ($auto -ne "") "결정적 반복은 결국 AUTO_STOP 으로 수렴해야 한다"
    Assert-Match $auto 'identical failure repeated' "무엇이 반복됐는지 증거가 남아야 한다"
    $log = Get-RunnerLog $repo "impl"
    Assert-Match $log '동일 실패 반복 상한 도달' "로그에도 남아야 한다"
    Assert (-not (Test-Path (Join-Path $repo "var\runner\STOP"))) "스크립트는 절대 STOP 을 만들면 안 된다(사용자 전용)"
}

Test-Case "T54" "COLD 는 전체 재접지, WARM 은 대형 문서 재독 금지 (B3 회귀)" {
    param($repo)
    Set-Scenario $repo @("success", "success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 2 })
    $prompts = Read-TextOrEmpty (Join-Path $repo "var\stub\prompts.log")
    Assert-Match $prompts 'resume_mode=COLD' "첫 회차는 COLD 여야 한다"
    Assert-Match $prompts 'resume_mode=WARM' "같은 세션을 정상 resume 한 두 번째 회차는 WARM 이어야 한다"
    Assert-Match $prompts '대형 문서 재독 금지' "WARM 회차에 재독 금지를 명시해야 한다"

    # 내장 프롬프트(override 없이 실제로 나가는 본문)에 두 모드가 모두 정의돼 있어야 한다
    $src = Read-TextOrEmpty $AutonomousScript
    Assert-Match $src '\$promptCold\s*=\s*@' "COLD 프롬프트가 정의돼야 한다"
    Assert-Match $src '\$promptWarm\s*=\s*@' "WARM 프롬프트가 정의돼야 한다"
    Assert-Match $src '전체 통독하지 마라' "WARM 프롬프트가 대형 문서 통독을 금지해야 한다"
    Assert-Match $src '__STATE_RESTORE_SECTION__' "모드별 섹션이 프롬프트에 주입돼야 한다"
    $asrc = Read-TextOrEmpty $AuditScript
    Assert-Match $asrc '__STATE_RESTORE_SECTION__' "Audit 프롬프트도 모드별 섹션을 주입해야 한다"
    Assert-Match $asrc '미조사\(UNSEEN\)·STATIC_ONLY 칸부터 이어서' "Audit WARM 은 증분으로 이어져야 한다"
}

Test-Case "T55" "무인 실행 계약: bypassPermissions · stream-json · 벽시계 상한 없음 · 모델/effort 고정" {
    param($repo)
    foreach ($s in @($AutonomousScript, $AuditScript)) {
        $src = Read-TextOrEmpty $s
        Assert-Match $src '"--permission-mode", "bypassPermissions"' `
            "무인 실행에서 auto 는 실제로 도구를 거부한다(2026-08-13 실측) — bypassPermissions 여야 한다: $s"
        Assert-NoMatch $src '"--permission-mode", "auto"' "auto 가 남아 있으면 안 된다: $s"
        Assert-Match $src '"--output-format", "stream-json"' "활동 신호·진행 표시를 위해 stream-json 이어야 한다: $s"
        Assert-Match $src '"--verbose"' "CLI 가 stream-json 과 함께 --verbose 를 요구한다: $s"
    }
    # 사용자가 지정한 고정 정책
    Assert ((Get-ScriptParamDefault $AutonomousScript "Model")  -eq '"sonnet"') "구현 Runner 기본 모델은 sonnet 고정"
    Assert ((Get-ScriptParamDefault $AutonomousScript "Effort") -eq '"max"')    "구현 Runner 기본 effort 는 max 고정"
    Assert ((Get-ScriptParamDefault $AuditScript "Model")  -eq '"opus"') "Audit Runner 기본 모델은 opus 고정"
    Assert ((Get-ScriptParamDefault $AuditScript "Effort") -eq '"max"')  "Audit Runner 기본 effort 는 max 고정"
    Assert ((Get-ScriptParamDefault $AutonomousScript "DynamicEffort") -eq '$false') "동적 effort 는 기본 꺼짐이어야 한다"
    Assert ((Get-ScriptParamDefault $AuditScript "DynamicEffort") -eq '$false') "동적 effort 는 기본 꺼짐이어야 한다"
    # 일하는 Worker 를 벽시계로 자르지 않는다
    Assert ((Get-ScriptParamDefault $AutonomousScript "MaxRuntimeMinutes") -eq '0') "hard timeout 기본값은 0(무제한)이어야 한다"
    Assert ((Get-ScriptParamDefault $AuditScript "MaxRuntimeMinutes") -eq '0') "hard timeout 기본값은 0(무제한)이어야 한다"
    Assert ([int](Get-ScriptParamDefault $AutonomousScript "MaxConsecutiveFailures") -ge 10) "일반 실패 3회로 밤샘 실행이 죽으면 안 된다"
    Assert ([int](Get-ScriptParamDefault $AuditScript "MaxConsecutiveFailures") -ge 10) "일반 실패 3회로 밤샘 Audit 이 죽으면 안 된다"
}

Test-Case "T56" "TEST SERVER 자율 권한: 낡은 차단 문구가 하나도 남아 있지 않다" {
    param($repo)
    $legacy = @(
        '배포 자격증명 경계',
        '배포는 건너뛰고',
        '채팅에 붙여넣어진 SSH/sudo 비밀번호',
        'NOPASSWD sudoers',
        '운영 자격증명을 임의로 사용하지 마라',
        '사용자가 직접 실행하거나'
    )
    foreach ($s in @($AutonomousScript, $AuditScript)) {
        $src = Read-TextOrEmpty $s
        foreach ($l in $legacy) {
            Assert-NoMatch $src ([regex]::Escape($l)) "CLAUDE.md §9 와 충돌하는 낡은 문구가 남아 있다('$l'): $s"
        }
    }
    $src = Read-TextOrEmpty $AutonomousScript
    Assert-Match $src '완전 자율 실행 권한' "TEST SERVER 자율 권한 절이 있어야 한다"
    Assert-Match $src '직접 설치하고 계속한다' "package 부재를 blocker 로 만들면 안 된다"
    Assert-Match $src '직접 만들고 계속한다' "QA 계정/데이터 부재를 blocker 로 만들면 안 된다"
    Assert-Match $src 'stdin으로만' "sudo 비밀번호는 stdin 으로만 넘겨야 한다"
    Assert-Match $src 'sshpass. 금지|sshpass` 금지' "sshpass 금지는 유지돼야 한다(CLAUDE.md §3.4)"

    # RUN CONTEXT 로 실제 권한 사실이 전달되는지
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 })
    $p = Read-TextOrEmpty (Join-Path $repo "var\stub\last_prompt.txt")
    Assert-Match $p 'test_server_authority=full' "자율 권한이 RUN CONTEXT 에 있어야 한다"
    Assert-Match $p 'sudo_credential=' "자격증명 가용 여부가 사실로 전달돼야 한다"
}

Test-Case "T57" "sudo 자격증명은 로그·프롬프트·argv 어디에도 남지 않는다" {
    param($repo)
    $sentinel = "S3nt1nel-DoNotLeak-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
    $prev = [Environment]::GetEnvironmentVariable("CLOVIR_TEST_SUDO_PASSWORD", 'Process')
    $env:CLOVIR_TEST_SUDO_PASSWORD = $sentinel
    try {
        Set-Scenario $repo @("success")
        $r = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }
        foreach ($f in @(
            (Join-Path $repo "var\runner\runner.log"),
            (Join-Path $repo "var\stub\args.log"),
            (Join-Path $repo "var\stub\last_prompt.txt"),
            (Join-Path $repo "var\runner\resume_context.txt"),
            (Join-Path $repo "var\runner\active_state.json")
        )) {
            Assert-NoMatch (Read-TextOrEmpty $f) ([regex]::Escape($sentinel)) "자격증명이 파일에 유출됐다: $f"
        }
        Assert-NoMatch $r.Output ([regex]::Escape($sentinel)) "자격증명이 콘솔 출력에 유출됐다"
        $log = Get-RunnerLog $repo "impl"
        Assert-Match $log 'sudo credential 확보=True 출처=env:' "존재 여부와 출처만 로그에 남겨야 한다"
    } finally {
        if ($null -eq $prev) { Remove-Item Env:CLOVIR_TEST_SUDO_PASSWORD -ErrorAction SilentlyContinue }
        else { $env:CLOVIR_TEST_SUDO_PASSWORD = $prev }
    }
}

Test-Case "T61" "품질 rubric이 Audit → 구현으로 실제로 넘어간다(두 Phase가 같은 자를 쓴다)" {
    param($repo)
    # 발견된 공백: Audit 프롬프트는 Skill 을 22곳에서 지시하는데 구현 프롬프트는 0곳이었고,
    # Handoff 에도 "무슨 기준으로 판정했는가"를 넘기는 필드가 없었다. 그러면 구현이
    # acceptance_criteria 의 글자만 만족시키고 Audit 이 재던 품질 기준은 빗나간다.

    # (1) Handoff 계약이 rubric 을 필수로 요구한다
    $asrc = Read-TextOrEmpty $AuditScript
    Assert-Match $asrc '"qa_gaps", "quality_rubric", "evidence_refs"' "quality_rubric 이 PA-RC 필수 필드여야 한다"
    Assert-Match $asrc 'quality_rubric: 이 Root Cause를 판정할 때' "Handoff 템플릿에 필드 설명이 있어야 한다"
    Assert-Match $asrc '설치되지 않은 Skill 이름을 적으면 그것은 조작이다' "미설치 Skill 을 적는 것을 금지해야 한다"

    # (2) 구현 프롬프트가 그 rubric 을 **만들기 전에** 적용하라고 지시한다
    $isrc = Read-TextOrEmpty $AutonomousScript
    Assert-Match $isrc 'Skill 사용 계약' "구현 프롬프트에 Skill 계약 절이 있어야 한다"
    # 줄바꿈이 끼어도 통과해야 한다(프롬프트는 사람이 읽기 좋게 줄을 나눠 쓴다)
    Assert-Match $isrc '(?s)`quality_rubric` 필드가 그 Root Cause를 판정할\s+때 쓴 기준이다' "Handoff 필드를 입력으로 쓰라고 해야 한다"
    Assert-Match $isrc '\*\*하기 전에\*\* 부른다' "사후 검사가 아니라 설계 단계 기준으로 쓰라고 해야 한다"
    Assert-Match $isrc '다 만든 뒤에 검사하는' "왜 먼저 부르는지 근거가 있어야 한다"
    Assert-Match $isrc '이름을 기억으로 추측하지 마라' "이름 추측 금지가 두 Phase 모두에 있어야 한다"
    Assert-Match $isrc 'PostToolUse hook으로 자동도 돌지만' "자동 hook 이 rubric 을 대신하지 않는다고 명시해야 한다"
    # 두 Phase 의 우선순위 문장이 **같아야** 한다 — 다르면 Handoff 가 무의미해진다
    $order = '사용자 업무 성공 > 기능 정확성 > 데이터/RBAC/보안 경계 > 명확한 UX >'
    Assert-Match $asrc ([regex]::Escape($order)) "Audit 의 우선순위 문장"
    Assert-Match $isrc ([regex]::Escape($order)) "구현도 **같은** 우선순위를 써야 한다"

    # (4) 핵심 다섯 Skill 이 **양쪽 프롬프트에 이름으로** 있어야 한다.
    #     "설치돼 있으니 알아서 쓰겠지"는 648턴 무인 실행에서 성립하지 않는다.
    foreach ($sk in @('ui-ux-pro-max', 'redesign-existing-projects', 'impeccable', 'ux-writing', 'humanize-korean')) {
        Assert-Match $asrc ([regex]::Escape($sk)) "Audit 프롬프트에 $sk 가 이름으로 있어야 한다"
        Assert-Match $isrc ([regex]::Escape($sk)) "구현 프롬프트에도 $sk 가 이름으로 있어야 한다(여기가 비어 있었다)"
    }
    Assert-Match $asrc '`Skill` 도구다' "Skill 확인은 파일시스템 추측이 아니라 도구 목록이어야 한다"
    Assert-Match $isrc '`Skill` 도구 목록이 정본이다' "구현도 런타임 확인을 해야 한다"

    # (5) 저 다섯 개**만** 쓰라는 게 아니다 — 지금 하는 작업에 맞는 걸 고르라는 일반 계약이어야 한다.
    foreach ($sk in @('python-patterns', 'python-testing', 'api-design', 'security-review',
                      'database-migrations', 'frontend-patterns', 'e2e-testing',
                      'superpowers:systematic-debugging')) {
        Assert-Match $isrc ([regex]::Escape($sk)) "스택에 맞는 $sk 도 구현 프롬프트에 있어야 한다"
    }
    Assert-Match $isrc '이 표가 전부가 아니다' "표를 닫힌 목록으로 오해하게 두면 안 된다"
    Assert-Match $asrc '이 다섯이 전부가 아니다' "Audit 도 마찬가지"

    # (6) 스택이 다른 Skill 오적용 경고 — django/postgres 조언을 FastAPI+SQLite 에 붙이면 틀린다
    foreach ($src2 in @($isrc, $asrc)) {
        Assert-Match $src2 '스택이 다른 Skill을 억지로 적용하지 마라' "오적용 경고가 있어야 한다"
        Assert-Match $src2 'FastAPI \+ SQLite' "이 제품의 실제 스택을 명시해야 한다"
    }

    # (7) 제품명은 ClovirAssist 다. 단 배포 경로 식별자 `clovirone-web-assistant` 는 **그대로
    #     둔다** — systemd unit·nginx conf·/opt 경로가 그 이름이라 바꾸면 실서버가 깨진다.
    Assert-Match $isrc 'ClovirAssist' "제품명은 ClovirAssist 다"
    Assert-NoMatchCase $isrc 'ClovirONE' "옛 제품명이 남아 있으면 안 된다"
    Assert-NoMatchCase $asrc 'ClovirONE' "옛 제품명이 남아 있으면 안 된다"
    Assert-Match $isrc 'clovirone-web-assistant' "경로 식별자는 유지돼야 한다(실서버가 이 이름을 쓴다)"

    # (3) rubric 이 빠진 Handoff 는 완료 Gate 가 거부한다
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Assert (Test-MarkerValid (Join-Path $repo "var\product-audit\AUDIT_COMPLETE")) "정상 Handoff 는 통과해야 한다"

    $handoff = Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"
    $body = Read-TextOrEmpty $handoff
    [void](Write-TextFile $handoff ($body -replace '(?m)^quality_rubric:.*$', ''))
    [void](Invoke-Git -RepoDir $repo "add" "docs/product-audit/PRODUCT_AUDIT_HANDOFF.md")
    [void](Invoke-Git -RepoDir $repo "commit" "-q" "-m" "drop quality_rubric")
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("success")
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } $null)
    $rej = Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt")
    Assert-Match $rej "필수 필드 'quality_rubric'" "rubric 이 빠지면 Gate 가 거부해야 한다. 실제: $rej"
}

Test-Case "T64" "사람 승인 대기로 미룬 Handoff 는 완료 Gate 가 거부한다 (RD-5/RD-6 재발 방지)" {
    param($repo)
    # 재설계가 필요하다는 것을 정확히 찾아 놓고 "업무 흐름이 바뀌니 사람 승인이 필요하다"며
    # 제안으로만 남기면 그 Root Cause 는 영원히 구현되지 않는다. 개별 항목을 예외 처리하는
    # 대신 **그런 결론 자체가 Gate 를 통과하지 못하게** 막는다.
    Set-Scenario $repo @("audit-deferred-to-human", "success")
    [void](Invoke-Audit $repo $null $null)
    Assert (-not (Test-Path (Join-Path $repo "var\product-audit\AUDIT_COMPLETE"))) "거부돼 격리돼야 한다"
    $rej = Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt")
    Assert-Match $rej 'deferred_for_human_approval=2' "미룬 항목 수를 근거로 거부해야 한다. 실제: $rej"
    Assert-Match $rej '사람 승인 Gate 가 없다' "왜 거부하는지 알려야 한다"
    Assert-Match $rej '사람에게 미루는 표현' "본문의 미루는 표현도 함께 잡아야 한다"
    $prompts = Read-TextOrEmpty (Join-Path $repo "var\stub\prompts.log")
    Assert-Match $prompts 'deferred_for_human_approval' "거부 사유가 다음 invocation 에 되먹여져야 한다"
}

Test-Case "T65" "Human Gate 표현 탐지기는 제품의 '승인 워크플로' 기능을 오탐하지 않는다" {
    param($repo)
    # 이 제품에는 approval 이라는 **기능**이 있다. 기능 서술을 미루는 표현으로 오인하면
    # 정상 Handoff 가 통과하지 못한다.
    foreach ($ok in @(
        "승인 워크플로에서 결재자가 반려하면 상태가 rejected 로 간다",
        "approval_e2e.py 가 승인 처리 경로를 검증한다",
        "관리자 승인 후 문서가 발행되는 것이 의도된 동작이다",
        "승인 대기 목록 화면의 빈 상태 문구가 없다"
    )) {
        Assert (@(Get-HumanGateLanguage $ok).Count -eq 0) "제품 기능 서술을 오탐하면 안 된다: $ok"
    }
    foreach ($bad in @(
        "업무 흐름이 바뀌므로 사람 승인 필요",
        "제안으로만 기록하고 구현 대상에서 제외한다",
        "이 설계는 사용자 판단이 필요하다",
        "구현 보류 — 정책 결정 후 진행",
        "Deferred: approval required from product owner",
        "awaiting human decision"
    )) {
        Assert (@(Get-HumanGateLanguage $bad).Count -ge 1) "미루는 표현은 잡아야 한다: $bad"
    }
}

Test-Case "T66" "AUDIT_BLOCKED 는 사람 호출 상태가 아니다 — 전략을 바꿔 자동 복구한다" {
    param($repo)
    # 예전: blocked → exit 5 → 사람이 고치고 -ResumeBlocked 로 재실행해야 이어졌다.
    Set-Scenario $repo @("audit-selfblock", "audit-full-complete")
    $r = Invoke-Audit $repo @{ MaxIterationsPerLaunch = 3; MaxBlockedRecoveries = 3 } $null
    $log = Get-RunnerLog $repo "audit"
    Assert-Match $log 'blocked 자동 복구' "사람을 기다리지 않고 복구해야 한다: $log"
    Assert-Match $r.Output '사람을 기다리지 않습니다' "복구 사실을 알려야 한다"
    $q = @(Get-ChildItem (Join-Path $repo "var\product-audit\quarantine") -File -ErrorAction SilentlyContinue)
    Assert ($q.Count -ge 1) "BLOCKED marker 는 삭제가 아니라 격리돼야 한다(증거 보존)"
    # 되먹임은 **다음 invocation 프롬프트에 실제로 도착**해야 의미가 있다.
    # (last_gate_rejection.txt 는 Gate 통과 시 정리되므로 그 파일로 확인하면 안 된다.)
    $prompts = Read-TextOrEmpty (Join-Path $repo "var\stub\prompts.log")
    Assert-Match $prompts '같은 방법을 반복하지 마라' "다른 전략을 쓰라는 지시가 다음 invocation 에 되먹여져야 한다"
    Assert-Match $prompts '사람이 풀어 주는 Gate 가 없다' "사람 대기가 선택지가 아님을 Worker 에게 알려야 한다"
    Assert ((Get-StubCount $repo) -ge 2) "복구 후 조사를 계속해야 한다(실제 $(Get-StubCount $repo))"

    # 상한을 넘기면 그때는 정말로 수렴한다(무한 반복 금지).
    # -ResetAudit 을 줘야 1부가 남긴 유효한 AUDIT_COMPLETE 때문에 조사를 건너뛰지 않는다.
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("audit-selfblock")
    $r2 = Invoke-Audit $repo @{ MaxIterationsPerLaunch = 6; MaxBlockedRecoveries = 1 } @("ResetAudit")
    Assert ($r2.ExitCode -eq 5) "자동 복구 상한을 넘으면 exit 5 로 수렴해야 한다(실제 $($r2.ExitCode))"
    $log2 = Get-RunnerLog $repo "audit"
    Assert-Match $log2 '자동 복구 상한' "상한 도달을 근거로 수렴해야 한다(무한 재시도 금지)"
}

Test-Case "T67" "세 Runner 어디에도 '사람이 재시작/승인해야 진행' 하는 실행 분기가 없다" {
    param($repo)
    # 문자열 제거가 목적이 아니라 **실행 흐름**에 사람 개입 지점이 없어야 한다.
    # 그래서 "예전에는 이랬다"고 설명하는 블록 주석(<# #>)은 걷어내고 **코드만** 본다 —
    # 안 그러면 제거 사실을 문서화한 주석이 스스로 테스트를 깨뜨린다(실제로 두 번 당했다).
    function Strip-BlockComments([string]$t) { return ($t -replace '(?s)<#.*?#>', '') }
    $runAll = Strip-BlockComments (Read-TextOrEmpty (Join-Path $RunnerDir "run_all.ps1"))
    $impl   = Read-TextOrEmpty $AutonomousScript
    $audit  = Read-TextOrEmpty $AuditScript

    # run_all: 예전의 "완료가 아니라 중단입니다 / 다시 실행하세요 → exit 10" 경로가 사라져야 한다
    Assert-NoMatch $runAll '완료가 아니라 중단입니다' "marker 없는 종료를 사람에게 넘기면 안 된다"
    # 주석에서 "예전에는 exit 10 이었다"고 설명하는 것은 괜찮다 — **실행문**이 없어야 한다.
    Assert-NoMatch $runAll '(?m)^\s*exit\s+10\s*$' "사람 재실행을 요구하던 exit 10 실행 경로가 남아 있으면 안 된다"
    Assert-NoMatch $runAll '같은 명령을 다시 실행하세요' "사람 재실행 안내가 남아 있으면 안 된다"
    Assert-Match $runAll 'Invoke-PhaseUntilMarker' "marker 가 생길 때까지 스스로 도는 구조여야 한다"
    Assert-Match $runAll 'PHASE 3' "구현 후 재감사 단계가 있어야 한다"
    Assert-Match $runAll '\$TerminalExitCodes = @\(3, 7\)' "사람 개입 종료는 STOP·전제조건 둘뿐이어야 한다"

    # audit: -ResumeBlocked 를 **사람이 쳐야만** 재개되는 구조가 아니어야 한다
    Assert-Match $audit 'Invoke-BlockedAutoRecovery' "BLOCKED 자동 복구 경로가 있어야 한다"
    Assert-Match $audit '\[bool\]\$AutoResolveBlockers = \$true' "자동 복구가 기본값이어야 한다"
    Assert-NoMatch $audit '-ResumeBlocked 옵션으로 다시 실행하세요' "사람 재실행 안내가 남아 있으면 안 된다"
    Assert-NoMatch $audit '사람이 확인하고 해결한 뒤' "사람 조치를 전제한 안내가 남아 있으면 안 된다"

    # 두 Worker 프롬프트: 사람 승인/질문 금지가 명시돼야 한다
    foreach ($p in @($impl, $audit)) {
        Assert-Match $p '사람 승인 필요' "금지 목록에 명시적으로 있어야 한다(그래야 모델이 인식한다)"
        Assert-Match $p '근거가 부족하면 질문하지 말고' "질문 대신 조사를 더 하라고 해야 한다"
    }
    Assert-Match $impl 'ADR/DECISIONS는 \*\*선행조건이 아니다\*\*' "문서가 Gate 가 되면 안 된다"
    Assert-Match $impl '사후 기록' "결정 → 구현 → 사후 문서화 순서여야 한다"
    Assert-Match $audit '재설계 필요 발견 → 근거 조사' "재설계를 제안이 아니라 구현 계약으로 만들어야 한다"
}

function Get-DesignDoc([string]$repo) { return (Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_DESIGN.md") }
function Edit-DesignDoc([string]$repo, [scriptblock]$transform) {
    # 유효한 Audit 산출물을 만든 뒤 DESIGN 문서만 망가뜨리고 다시 Gate 를 태운다.
    # 주의: Gate 가 거부하면 AUDIT_COMPLETE 가 격리돼 사라진다 — 그러면 다음 호출에서
    # 시작 시점 Gate 가 아예 안 돌아 직전 거부 사유를 그대로 다시 읽게 된다(테스트가 통과한
    # 것처럼 보이거나, 두 번째 변형이 검증되지 않는다). 매번 marker 를 되살려 Gate 를 태운다.
    $mk = Join-Path $repo "var\product-audit\AUDIT_COMPLETE"
    if (Test-MarkerValid $mk) { $script:SavedAuditComplete = Read-TextOrEmpty $mk }
    elseif ($script:SavedAuditComplete) { [void](Write-TextFile $mk $script:SavedAuditComplete) }
    $p = Get-DesignDoc $repo
    [void](Write-TextFile $p (& $transform (Read-TextOrEmpty $p)))
    [void](Invoke-Git -RepoDir $repo "add" "docs/product-audit")
    [void](Invoke-Git -RepoDir $repo "commit" "-q" "-m" "design tweak")
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("success")
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } $null)
    return (Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt"))
}

Test-Case "T70" "일반 browser sweep 만으로는 L축 디자인 판정을 세울 수 없다 (deep_audited)" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Assert (Test-MarkerValid (Join-Path $repo "var\product-audit\AUDIT_COMPLETE")) "정상 판정은 통과해야 한다"

    # sweep 만 돌린 상태를 흉내낸다: deep_audited=false + UI Skill 미적용
    $rej = Edit-DesignDoc $repo {
        param($t)
        ($t -replace '(?m)^deep_audited: true[ 	]*?$', 'deep_audited: false') `
           -replace '(?m)^skills_applied: .*$', 'skills_applied: 없음 — sweep_all.py 만 실행'
    }
    Assert-Match $rej 'deep_audited=true 가 아니다' "sweep 만으로 판정을 세우면 거부해야 한다. 실제: $rej"
    Assert-Match $rej '일반 browser sweep' "왜 거부하는지 알려야 한다"
    Assert-Match $rej 'skills_applied' "UI/UX Skill 미적용도 잡아야 한다"
}

Test-Case "T71" "필수 Surface 판정 누락 — App Shell/Dashboard/Sidebar/IA 는 반드시 독립 판정" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    # 핵심 4개 Surface 블록을 지운다
    $rej = Edit-DesignDoc $repo {
        param($t)
        foreach ($s in @('app-shell', 'dashboard', 'sidebar', 'navigation-ia')) {
            $t = $t -replace ("(?s)<!--\s*DESIGN-VERDICT-BEGIN\s+" + [regex]::Escape($s) + "\s*-->.*?<!--\s*DESIGN-VERDICT-END\s*-->"), ''
        }
        return $t
    }
    foreach ($s in @('app-shell', 'dashboard', 'sidebar', 'navigation-ia')) {
        Assert-Match $rej ("필수 Surface '" + [regex]::Escape($s) + "' 의 디자인 판정이 없다") "$s 판정 누락을 잡아야 한다"
    }
    Assert-Match $rej '제품 전체 구조를 결정하므로' "핵심 영역임을 알려야 한다"
}

Test-Case "T72" "REDESIGN/REBUILD 가 Handoff PA-RC 로 안 내려가면 Gate 실패 (RD-5/RD-6 구조적 재발 방지)" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    # 판정은 REBUILD 인데 구현 계약 참조를 지운다 = "판정만 하고 구현 안 함"
    $rej = Edit-DesignDoc $repo {
        param($t)
        ($t -replace '(?m)^verdict: REDESIGN[ 	]*?$', 'verdict: REBUILD') `
           -replace '(?m)^rc_ids: PA-RC-0001[ 	]*?$', 'rc_ids: 아직 정하지 않음'
    }
    Assert-Match $rej 'rc_ids 에 PA-RC 참조가 없다' "판정만 하고 구현으로 안 내려가면 거부해야 한다. 실제: $rej"
    Assert-Match $rej '영원히 구현되지 않는다' "왜 막는지 알려야 한다"

    # 존재하지 않는 PA-RC 를 가리키는 것도 잡는다
    $rej2 = Edit-DesignDoc $repo { param($t) $t -replace '(?m)^rc_ids: 아직 정하지 않음[ 	]*?$', 'rc_ids: PA-RC-9999' }
    Assert-Match $rej2 'PA-RC-9999 가 HANDOFF 에 없다' "허수 참조도 잡아야 한다. 실제: $rej2"
}

Test-Case "T73" "UI Root Cause 는 Target Design 필드를 반드시 들고 간다" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    # Handoff 의 UI 필드를 지운다(Bottom-up 으로 되돌아가는 경로)
    $hf = Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"
    $t = Read-TextOrEmpty $hf
    foreach ($f in @('target_design', 'target_visual_delta', 'workflow_change', 'navigation_impact')) {
        $t = $t -replace ("(?m)^" + [regex]::Escape($f) + ": .*$"), ''
    }
    [void](Write-TextFile $hf $t)
    [void](Invoke-Git -RepoDir $repo "add" "docs/product-audit")
    [void](Invoke-Git -RepoDir $repo "commit" "-q" "-m" "strip ui fields")
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("success")
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } $null)
    $rej = Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt")
    foreach ($f in @('target_design', 'target_visual_delta', 'workflow_change', 'navigation_impact')) {
        Assert-Match $rej ("필수 필드 '" + $f + "' 가 없다") "UI RC 의 $f 누락을 잡아야 한다. 실제: $rej"
    }
    Assert-Match $rej 'Bottom-up' "왜 필요한지 알려야 한다"
}

Test-Case "T74" "visual_change_required=true 인데 화면 검증 근거가 없으면 Gate 실패" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    $hf = Join-Path $repo "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"
    # lint/test 만 적어 둔다 — 화면을 안 본 것이다
    [void](Write-TextFile $hf ((Read-TextOrEmpty $hf) -replace '(?m)^browser_verification: .*$', 'browser_verification: eslint 통과 및 단위테스트 green'))
    [void](Invoke-Git -RepoDir $repo "add" "docs/product-audit")
    [void](Invoke-Git -RepoDir $repo "commit" "-q" "-m" "weak verification")
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    Set-Scenario $repo @("success")
    [void](Invoke-Audit $repo @{ MaxIterationsPerLaunch = 1 } $null)
    $rej = Read-TextOrEmpty (Join-Path $repo "var\product-audit\last_gate_rejection.txt")
    Assert-Match $rej 'browser_verification 이 실제 화면 검증' "lint/test 만으로는 시각 검증이 아니다. 실제: $rej"
    Assert-Match $rej 'lint/test/token 수정만으로 완료할 수 없는' "왜 막는지 알려야 한다"
    # 순수 함수 양방향 확인
    Assert (Test-VisualVerificationEvidence "1920/3840 라이트·다크 스크린샷 비교") "화면 어휘가 있으면 인정"
    Assert (-not (Test-VisualVerificationEvidence "eslint 통과, 단위테스트 green")) "lint/test 는 인정하면 안 된다"
}

Test-Case "T75" "구현 쪽: visual_change_required 작업을 화면 확인 없이 완료 처리할 수 없다" {
    param($repo)
    Set-Scenario $repo @("audit-full-complete")
    [void](Invoke-Audit $repo $null $null)
    Assert (Test-MarkerValid (Join-Path $repo "var\product-audit\IMPLEMENTATION_REQUIRED")) "Handoff 준비"

    # CONSUMED 에 시각 검증 수를 안 적고 완료를 선언한다
    Set-Content -Path (Join-Path $repo "var\stub\counter.txt") -Value 0 -Encoding ascii
    $stub = Join-Path $repo "var\stub\claude_stub.ps1"
    $t = [System.IO.File]::ReadAllText($stub, [System.Text.Encoding]::UTF8)
    $t = $t.Replace('visually_verified_rcs=$vc', 'visually_verified_rcs=0')
    [System.IO.File]::WriteAllText($stub, $t, (New-Object System.Text.UTF8Encoding($true)))
    Set-Scenario $repo @("impl-consume-complete", "success")
    [void](Invoke-Autonomous $repo $null)
    Assert (-not (Test-Path (Join-Path $repo "var\runner\PROJECT_COMPLETE"))) "시각 검증 없는 완료는 격리돼야 한다"
    $rej = Read-TextOrEmpty (Join-Path $repo "var\runner\last_completion_rejection.txt")
    Assert-Match $rej '시각 검증이 부족하다' "무엇이 부족한지 알려야 한다. 실제: $rej"
    Assert-Match $rej '브라우저로 확인하지 않은' "왜 거부인지 알려야 한다"
}

Test-Case "T76" "두 Runner 프롬프트에 '기능은 보존, UI는 보존하지 않는다' 계약이 있다" {
    param($repo)
    $audit = Read-TextOrEmpty $AuditScript
    $impl  = Read-TextOrEmpty $AutonomousScript

    # 판정 어휘와 REBUILD 를 정상 선택지로 다룰 것
    foreach ($src in @($audit, $impl)) {
        foreach ($v in @('KEEP', 'REFINE', 'REDESIGN', 'REBUILD')) {
            Assert-Match $src $v "판정 어휘 $v 가 있어야 한다"
        }
        Assert-Match $src '기존 UI와 너무 달라진다' "재설계를 막는 변명을 명시적으로 금지해야 한다"
        Assert-Match $src '보존 의무 없음' "보존/비보존 경계표가 있어야 한다"
    }
    # Audit: Target Design 우선(Bottom-up 금지) + 5 Skill 순서 + 필수 Surface
    Assert-Match $audit '먼저 Target Design을 만든다' "Top-down 설계가 먼저여야 한다"
    Assert-Match $audit 'Bottom-up 방식만 쓰지 마라' "Bottom-up 금지"
    Assert-Match $audit 'DESIGN-VERDICT-BEGIN' "판정 블록 형식이 프롬프트에 있어야 한다"
    Assert-Match $audit 'REBUILD는 정상적인 선택지다' "REBUILD 를 정상 선택지로 둬야 한다"
    foreach ($s in @('app-shell', 'dashboard', 'sidebar', 'navigation-ia', 'ai-assistant-chat', 'key-workflows')) {
        Assert-Match $audit ([regex]::Escape($s)) "필수 Surface $s 가 프롬프트에 있어야 한다"
    }
    # QA 와 Deep Audit 분리
    Assert-Match $audit '전부 QA 이지 UI/UX Deep Audit 이 아니다' "QA 와 디자인 감사를 분리해야 한다"
    Assert-Match $audit 'VISUAL_OBSERVED' "L축 상태 어휘가 있어야 한다"
    Assert-Match $audit 'DESIGN_VERDICT_COMPLETE' "L축 상태 어휘가 있어야 한다"
    Assert-Match $audit 'VISUALLY_VERIFIED' "L축 상태 어휘가 있어야 한다"
    # 과거 Finding 재판정
    Assert-Match $audit '판정 없이 과거 Finding이 사라지는 것은 허용하지 않는다' "과거 UI Finding 재판정 규칙"
    # 구현: REBUILD 권한 + 기반작업을 결과로 착각 금지
    Assert-Match $impl '기존 UI 구조를 \*\*폐기하고\*\*' "REBUILD 권한이 명시돼야 한다"
    Assert-Match $impl '기반 작업이지 결과가 아니다' "token/lint 정리를 결과로 보면 안 된다"
    Assert-Match $impl 'PRODUCT_AUDIT_DESIGN\.md' "구현이 판정 문서를 읽어야 한다"
    Assert-Match $impl 'visually_verified_rcs' "시각 검증 수를 남기게 해야 한다"
}

Test-Case "T69" "write guard 위반도 사람을 부르지 않는다 — 증거 보존 + 세션 회전 + 계속, 반복되면 수렴" {
    param($repo)
    # 안전장치를 없애는 게 아니다: 탐지는 그대로, **자동 revert 도 여전히 안 한다**.
    # 달라진 것은 "사람이 고치고 -ResumeBlocked 로 재실행" 이라는 대기가 사라진 것뿐이다.
    Set-Scenario $repo @("audit-bad-worktree", "audit-full-complete")
    $r = Invoke-Audit $repo @{ MaxIterationsPerLaunch = 3; MaxWriteGuardRecoveries = 2 } $null
    $log = Get-RunnerLog $repo "audit"
    Assert-Match $log 'write-guard 자동 복구' "사람을 기다리지 않고 복구해야 한다: $log"
    # 사용자/Worker 변경은 절대 되돌리지 않는다
    Assert-Match (Read-TextOrEmpty (Join-Path $repo "app\main.py")) 'auditor touched' "자동 revert 하면 안 된다(변경 보존)"
    # 증거는 격리 보관돼야 한다
    $q = @(Get-ChildItem (Join-Path $repo "var\product-audit\quarantine") -File -ErrorAction SilentlyContinue)
    Assert ($q.Count -ge 1) "위반 증거가 격리 보관돼야 한다"
    $qtext = ($q | ForEach-Object { Read-TextOrEmpty $_.FullName }) -join "`n"
    Assert-Match $qtext 'app/main\.py' "어떤 경로를 건드렸는지 증거에 남아야 한다"
    # 오염된 세션은 회전하고, 강한 교정 지시가 다음 invocation 에 간다
    $prompts = Read-TextOrEmpty (Join-Path $repo "var\stub\prompts.log")
    Assert-Match $prompts '제품 코드/테스트/설정/배포 코드를 절대 건드리지 마라' "교정 지시가 되먹여져야 한다"
    Assert ((Get-StubCount $repo) -ge 2) "복구 후 조사를 계속해야 한다"
}

Test-Case "T68" "UI/UX 재설계 권한과 완료 판정이 두 Phase 프롬프트에 실제로 있다" {
    param($repo)
    $impl  = Read-TextOrEmpty $AutonomousScript
    $audit = Read-TextOrEmpty $AuditScript
    foreach ($item in @('Information Architecture 재편', 'Sidebar 구조 변경', 'Navigation 재구성',
                        'Dashboard 재설계', 'Tab 구조 도입', '정보 위계 재조정', 'CTA 위치')) {
        Assert-Match $impl ([regex]::Escape($item)) "구현 프롬프트에 '$item' 권한이 있어야 한다"
        Assert-Match $audit ([regex]::Escape($item)) "Audit 프롬프트에 '$item' 권한이 있어야 한다"
    }
    # 얕은 완료 판정 금지
    Assert-Match $impl 'token migration 완료' "얕은 완료 근거를 명시적으로 부정해야 한다"
    Assert-Match $impl '기존 화면보다 실제 사용성이 좋아졌는가' "실제 화면 기준 평가 항목이 있어야 한다"
    Assert-Match $impl '단순 CSS/spacing 수정만 반복' "CSS 보정만으로 완료 처리 금지"
    # Blocker 자가 복구 사다리
    Assert-Match $impl 'Blocker는 사람 호출 상태가 아니다' "구현 쪽 자가 복구 사다리"
    Assert-Match $audit 'Blocker는 사람 호출 상태가 아니다' "Audit 쪽 자가 복구 사다리"
    # dirty worktree: 사람 대기 금지 + 사용자 변경 보호 동시 만족
    Assert-Match $impl 'git worktree' "충돌 시 별도 worktree 전략이 있어야 한다"
    Assert-Match $impl 'reset·revert·drop·overwrite 하는 것은 절대 금지' "사용자 변경 보호는 유지해야 한다"
}

Test-Case "T62" "WARM이 CLAUDE.md를 다시 안 읽어도 불변 규칙이 매 호출에 함께 간다" {
    param($repo)
    # COLD/WARM 분리의 부작용: WARM 회차는 CLAUDE.md를 다시 읽지 않고, 긴 세션은 context가
    # 압축된다. 참조("CLAUDE.md §3을 지켜라")만 남기면 규칙 **내용**이 사라질 수 있다.
    # 그래서 요약본을 항상 보내는 core 프롬프트에 인라인한다.
    $src = Read-TextOrEmpty $AutonomousScript
    Assert-Match $src '절대 어기면 안 되는 것' "불변 규칙 절이 core 프롬프트에 있어야 한다"
    foreach ($rule in @('Sync 일관성', 'OutboundClient', 'Secret 비노출', 'Credential 비영구화',
                        'opaque session', 'innerHTML', 'UTC 저장', '제품 기능 경계',
                        '공유 서비스 보호', 'DB transaction 의미 보존')) {
        Assert-Match $src ([regex]::Escape($rule)) "불변 규칙 '$rule' 내용이 프롬프트에 있어야 한다"
    }
    Assert-Match $src '(?s)\*\*참조가\s*\r?\n?아니라 내용\*\*' "왜 인라인하는지 근거가 있어야 한다"

    # WARM 회차 프롬프트에도 실제로 실려 나가는지 (override 없이 본문이 나가는 경로를 고정)
    Assert-Match $src '\$promptCore\s*=\s*@' "core 프롬프트가 존재해야 한다"
    $coreStart = $src.IndexOf('$promptCore')
    $warnStart = $src.IndexOf('절대 어기면 안 되는 것')
    Assert ($warnStart -gt $coreStart) "불변 규칙은 COLD 전용이 아니라 core(항상 전송)에 있어야 한다"
}

Test-Case "T63" "브라우저 MCP가 없는 무인 실행에서 E2E를 어떻게 하는지 지시가 있다" {
    param($repo)
    # 실측: `-p` 비대화형 세션에는 Chrome/browser MCP 도구가 하나도 붙지 않는다.
    # 그런데 CLAUDE.md §10은 Chrome Whole-product E2E를 필수 완료 Gate로 요구한다.
    # 저장소에는 Playwright 기반 scripts/ui_qa 하네스가 이미 있는데 프롬프트가 안 가리켰다.
    $src = Read-TextOrEmpty $AutonomousScript
    Assert-Match $src '브라우저 MCP 도구가 \*\*없다\*\*' "도구가 없다는 사실을 알려야 한다(찾아 헤매지 않게)"
    Assert-Match $src 'scripts/ui_qa/' "실제 하네스를 가리켜야 한다"
    Assert-Match $src 'scripts/ui_qa/README\.md' "사용법 정본을 가리켜야 한다"
    Assert-Match $src '새로 만들지 말고 \*\*그것을 확장\*\*' "기존 축별 모듈을 재사용하라고 해야 한다"
    Assert-Match $src '스크린샷이 존재한다는 사실' "스크린샷 존재만으로 E2E 완료 처리 금지"
    # 화면 품질 축이 완료 기준에만 있는 게 아니라 구현 지시로 있어야 한다
    foreach ($axis in @('Responsive', 'Light/Dark', 'Accessibility')) {
        Assert-Match $src ([regex]::Escape($axis)) "$axis 축이 구현 지시에 있어야 한다"
    }
    Assert-Match $src 'QA_COVERAGE\.md.*반영|반영한다' "검증한 축을 QA_COVERAGE에 반영하라고 해야 한다"
    # 배포 순서(CLAUDE.md §9)
    Assert-Match $src 'Full Regression green.*Static Checks.*Build' "배포 흐름 순서가 있어야 한다"
}

Test-Case "T57B" "sudo 자격증명을 gitignore 되는 runtime 파일에서도 받는다(매번 환경변수 안 넣어도 무인 실행)" {
    param($repo)
    $sentinel = "FileCred-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
    $credFile = Join-Path $repo "var\runner\test_server_sudo"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $credFile) | Out-Null
    # 개행이 붙어도 그대로 살아야 한다(에디터가 붙인다). 단 Trim() 은 쓰지 않는다 — 비밀번호에
    # 공백이 들어갈 수 있다.
    [void](Write-TextFile $credFile ($sentinel + "`r`n"))

    $prev = [Environment]::GetEnvironmentVariable("CLOVIR_TEST_SUDO_PASSWORD", 'Process')
    Remove-Item Env:CLOVIR_TEST_SUDO_PASSWORD -ErrorAction SilentlyContinue
    try {
        $r = Resolve-SudoCredential -EnvName "CLOVIR_TEST_SUDO_PASSWORD" -FilePath $credFile
        Assert ($r.Available) "runtime 파일에서 자격증명을 확보해야 한다"
        Assert ($r.Source -like "file:*") "출처가 파일이어야 한다(실제 $($r.Source))"
        Assert ($env:CLOVIR_TEST_SUDO_PASSWORD -eq $sentinel) "개행만 벗기고 값은 그대로여야 한다"
        Assert ($r.PSObject.Properties.Name -notcontains "Value") "함수가 값 자체를 돌려주면 안 된다(로그 유출 경로 차단)"

        # 환경변수가 이미 있으면 그쪽이 우선이고 파일을 읽지 않는다
        $env:CLOVIR_TEST_SUDO_PASSWORD = "from-env"
        $r2 = Resolve-SudoCredential -EnvName "CLOVIR_TEST_SUDO_PASSWORD" -FilePath $credFile
        Assert ($r2.Source -like "env:*") "환경변수가 우선이어야 한다(실제 $($r2.Source))"
        Assert ($env:CLOVIR_TEST_SUDO_PASSWORD -eq "from-env") "기존 값을 덮어쓰면 안 된다"

        # 없으면 없다고 정직하게 말한다
        Remove-Item Env:CLOVIR_TEST_SUDO_PASSWORD -ErrorAction SilentlyContinue
        $r3 = Resolve-SudoCredential -EnvName "CLOVIR_TEST_SUDO_PASSWORD" -FilePath (Join-Path $repo "var\runner\no_such_file")
        Assert (-not $r3.Available) "없으면 없다고 해야 한다"
        Assert ($r3.Source -eq "none") "출처도 none 이어야 한다"

        # 그리고 그 값이 Supervisor 산출물 어디에도 새지 않아야 한다
        Remove-Item Env:CLOVIR_TEST_SUDO_PASSWORD -ErrorAction SilentlyContinue
        Set-Scenario $repo @("success")
        $run = Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 }
        foreach ($f in @((Join-Path $repo "var\runner\runner.log"), (Join-Path $repo "var\stub\args.log"),
                         (Join-Path $repo "var\stub\last_prompt.txt"), (Join-Path $repo "var\runner\resume_context.txt"))) {
            Assert-NoMatch (Read-TextOrEmpty $f) ([regex]::Escape($sentinel)) "파일 출처 자격증명이 유출됐다: $f"
        }
        Assert-NoMatch $run.Output ([regex]::Escape($sentinel)) "자격증명이 콘솔에 유출됐다"
        Assert-Match (Get-RunnerLog $repo "impl") 'sudo credential 확보=True 출처=file:' "출처만 로그에 남겨야 한다"
    } finally {
        if ($null -eq $prev) { Remove-Item Env:CLOVIR_TEST_SUDO_PASSWORD -ErrorAction SilentlyContinue }
        else { $env:CLOVIR_TEST_SUDO_PASSWORD = $prev }
    }
}

Test-Case "T58" "invocation 구간별 소요 시간이 timings.jsonl 에 남는다(추측 대신 측정)" {
    param($repo)
    Set-Scenario $repo @("success")
    [void](Invoke-Autonomous $repo @{ MaxIterationsPerLaunch = 1 })
    $t = Read-TextOrEmpty (Join-Path $repo "var\runner\timings.jsonl")
    Assert ($t -ne "") "timings.jsonl 이 있어야 한다"
    $rec = ($t -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1) | ConvertFrom-Json
    foreach ($k in @("dirtyCheckMs", "contextBuildMs", "promptPrepMs", "workerRunMs", "postCheckMs", "backoffMs", "totalMs")) {
        Assert ($rec.PSObject.Properties.Name -contains $k) "구간 '$k' 가 기록돼야 한다"
    }
    Assert ($rec.mode -eq "COLD") "모드도 함께 남아야 한다"
    Assert ($rec.failureClass -eq "ok") "실패 유형도 함께 남아야 한다"
}

Test-Case "T59" "미해결 Backlog index 를 BACKLOG.md 에서 기계 추출한다(원본은 그대로 둔다)" {
    param($repo)
    $body = @"
# BACKLOG

| ID | 문제 | 상태 |
|---|---|---|
| ``AA-01`` | 아직 안 고친 것 | 작업예정 |
| ``AA-02`` | ~~이미 끝난 것~~ | ✅ 실환경검증완료 |
| ``BB-77`` | Critical 인 것 | 발견 |
"@
    [void](Write-TextFile (Join-Path $repo "docs\BACKLOG.md") $body)
    $items = @(Get-UnresolvedBacklogIndex (Join-Path $repo "docs\BACKLOG.md"))
    $ids = @($items | ForEach-Object { $_.id })
    Assert ($ids -contains "AA-01") "미해결 항목은 index 에 있어야 한다"
    Assert ($ids -contains "BB-77") "미해결 항목은 index 에 있어야 한다"
    Assert ($ids -notcontains "AA-02") "완료 항목은 index 에서 빠져야 한다"
    Assert (@($items | Where-Object { $_.id -eq "BB-77" })[0].severity -eq "Critical") "심각도를 추출해야 한다"

    # cache 는 Source of Truth 가 아니다 — 원본은 손대지 않는다
    $before = Read-TextOrEmpty (Join-Path $repo "docs\BACKLOG.md")
    [void](New-RunnerContextCache -ProjectDir $repo -OutDir (Join-Path $repo "var\runner") -Extra $null)
    Assert ((Read-TextOrEmpty (Join-Path $repo "docs\BACKLOG.md")) -eq $before) "index 생성이 원본 문서를 바꾸면 안 된다"
}

Test-Case "T60" "긴 백오프 중에도 사용자 STOP 이 즉시 먹힌다" {
    param($repo)
    # 예전엔 통짜 Start-Sleep 이라 사용량 한도 대기(최대 몇 시간) 중에 STOP 을 만들어도
    # 다음 확인까지 그대로 잤다. 이제는 짧게 쪼개 자면서 STOP 을 본다.
    $stop = Join-Path $repo "var\runner\STOP"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stop) | Out-Null
    $job = Start-Job -ScriptBlock {
        param($p)
        Start-Sleep -Seconds 3
        [System.IO.File]::WriteAllText($p, "사용자 중단")
    } -ArgumentList $stop
    try {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $ok = Start-InterruptibleSleep -Seconds 60 -StopFile $stop -Reason "테스트"
        $sw.Stop()
        Assert (-not $ok) "STOP 을 감지하면 $false 를 돌려줘야 한다"
        Assert ($sw.Elapsed.TotalSeconds -lt 20) "60초를 다 자면 안 된다(실제 $([int]$sw.Elapsed.TotalSeconds)초)"
    } finally { Remove-Job $job -Force -ErrorAction SilentlyContinue }
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
