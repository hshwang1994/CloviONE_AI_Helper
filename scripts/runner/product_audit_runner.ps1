<#
.SYNOPSIS
  ClovirONE Web Assistant Whole Product Audit — PHASE 1 무인 Supervisor.

.DESCRIPTION
  이 스크립트는 제품을 구현하거나 수정하는 Runner가 **아니다**. 제품 전체를 반복 조사해서
  현재 Backlog에 없는 문제, 의도와 다른 동작, 기능/UX 누락, 데이터/RBAC/통합/복구/테스트 공백,
  사용자 노출 문구 문제까지 Root Cause 기준으로 찾아내고 근거화한다. 실제 구현은 PHASE 2인
  `autonomous_runner.ps1`가 `PRODUCT_AUDIT_HANDOFF.md`를 입력으로 받아 수행한다.

  두 Supervisor는 `var/runner/run.lock` 을 **공유**한다 — 동시에 돌 수 없다.

  === 2026-08-12 심층 검수에서 실제로 고친 결함 ===
  A. **PS 5.1에서 git 호출이 Supervisor를 죽였다.** `$ErrorActionPreference='Stop'` + native
     명령 + stderr 리다이렉트는 5.1에서 terminating error다(실측). `git rev-parse HEAD 2>$null`
     하나로 루프 전체가 끝났다 — 커밋 없는 저장소, 잘못된 rev 범위, dubious-ownership 경고 등
     git이 stderr에 한 줄만 써도 발생. 모든 git 호출을 `Invoke-Git`(runner_common.ps1)로 옮겼다.
  B. **write guard가 touch-and-revert를 놓쳤다.** 예전 판정은 `git diff before..after` 하나로
     **순 변화**만 봤다 — Worker가 제품 코드를 고쳐 커밋한 뒤 되돌려 커밋하면 순 변화가 0이라
     탐지되지 않았다. 이제 `rev-list`로 구간의 **모든 커밋을 하나씩** 검사하고, history rewrite
     (before가 after의 조상이 아님), 브랜치 전환, reflog의 reset/rebase/checkout 흔적까지 본다.
  C. **AUDIT_COMPLETE를 무조건 믿었다.** Claude가 marker 하나 만들면 그대로 성공 종료했다.
     이제 Supervisor가 필수 문서 7종의 존재/최소 분량/commit 여부, cycle_id·baseline 일치,
     Coverage 요약의 자기모순, Blind Re-Audit 2회 연속 수렴, HANDOFF의 PA-RC 블록 필수 필드,
     IMPLEMENTATION_REQUIRED 정합성까지 기계적으로 검증한다. 실패하면 marker를 격리(삭제 아님)
     하고 **거부 사유를 다음 invocation 프롬프트에 되먹여** 계속 조사한다.
  D. **Cycle 격리가 없었다.** 과거 Audit 결과/과거 Blind PASS가 새 Cycle의 완료 근거로 그대로
     재사용될 수 있었다. cycle_id + baseline SHA를 `var/product-audit/cycle.json`에 고정하고,
     모든 marker와 산출물이 현재 cycle에 속하는지 검증한다.
  E. **HANDOFF 산출물 자체가 없었다.** CLAUDE.md는 `PRODUCT_AUDIT_HANDOFF.md`를 구현 입력
     계약으로 참조하는데 프롬프트는 그 파일을 만들지 않았다. 이제 필수 산출물이며 각 PA-RC는
     기계 검증 가능한 블록으로 쓴다.
  F. **필수 Skill 부재가 전체 Audit을 하드 블록했다.** Skill 5종 중 하나만 없어도 밤샘 실행이
     통째로 AUDIT_BLOCKED로 끝나는 구조였다. Skill은 **가속기**이고 축(axis) 자체가 필수다 —
     없으면 내장 rubric으로 수행하고 SKILL_GAP으로 기록한다. 축을 아예 못 덮을 때만 BLOCKED.
  G. **사용자가 남겨 둔 dirty 파일 때문에 Audit이 시작조차 못 했다.** 이제 내용이 변하지 않는
     외부 dirty는 "안정된 사전 상태"로 기록하고 진행하되, invocation 전후 스냅샷을 해시로
     비교해 **Worker가 건드린 것**만 위반으로 판정한다.
  H. rate-limit 오탐(로그 어딘가의 "429" 숫자)이 실패 카운터를 우회해 무한 백오프로 돌 수
     있었다. 판정을 좁히고 연속 rate-limit 상한을 두었다.
  I. state.json 스키마가 바뀌면 속성 대입에서 죽었다(실측: 없는 속성 대입은 throw). 정규화 도입.

  === 2026-08-13 처리량 개선 (정확성 Gate 는 하나도 약화하지 않았다) ===
  J. **고정 벽시계 timeout → 활동 기반 idle timeout.** 구현 Runner 와 같은 병목이었다.
     `--output-format stream-json --verbose` 로 stdout 이 실시간으로 자라게 하고, 그 파일이
     자라는 동안은 살아 있는 것으로 본다. 진짜로 멈춘 프로세스만 죽인다.
  K. **`--permission-mode auto` → `bypassPermissions`.** 2026-08-13 controlled probe 에서
     `auto` 가 무인 실행 중 Write/Bash 를 실제로 거부하는 것을 확인했다(승인해 줄 사람이 없다).
     Audit 은 여전히 **제품 코드를 쓰지 않는다** — 그 경계는 permission mode 가 아니라
     write guard(워킹트리 해시 + 구간의 모든 커밋 + 이력 무결성)가 강제한다. 그쪽이 원본이고
     훨씬 강하다.
  L. **매 invocation 전체 재조사 금지.** 프롬프트가 매번 CLAUDE.md·WORK_STATE·BACKLOG 전체·
     QA_COVERAGE 전체를 다시 읽으라고 지시했다. 이제 COLD(새 세션·gate 거부 후·주기 재접지)
     에서만 전체 접지를 하고, WARM 은 COVERAGE 의 미조사 칸부터 **이어서** 판다.
     이미 STRONG/CONFIRMED 증거를 얻은 surface 를 근거 없이 다시 조사하지 않는다.
  M. **실패 유형 분류 + 실제 rate-limit reset 시각 대기 + 진행 상황 heartbeat + 구간 타이밍**을
     구현 Runner 와 **같은 공용 계층**(runner_common.ps1)에서 쓴다.
  N. dirty 판정을 파일 mtime 기반으로 교체 — 고정된 사용자 dirty 하나에 매번 수 분씩 태우던
     경로를 없앴다. 사람이 실제로 편집 중이면(mtime 갱신) 여전히 기다린다.

  PowerShell 호환성: Windows PowerShell 5.1과 PowerShell 7 모두에서 controlled test 통과.
  실제 운영 환경은 5.1이다(var/runner의 UTF-8 BOM이 그 증거).
#>

param(
    [string]$ProjectDir = "C:\Users\hshwa\clovirone-web-assistant",
    [string]$ClaudeExe  = "C:\Users\hshwa\.local\bin\claude.exe",

    # controlled test seam — 평소엔 비운다(내장 프롬프트 사용). 이름 주의: PowerShell 변수는
    # 대소문자를 구분하지 않으므로 루프 안의 per-invocation 변수와 같은 이름을 쓰면 파라미터가
    # 조용히 덮어써진다(2026-08-12 실제로 당한 함정).
    [string]$PromptOverrideFile = "",

    # ★ 2026-08-13 사용자 지시로 **고정**한다: 설계·발견 작업인 Audit 은 Opus + max.
    #   (동적 effort 정책 코드는 남아 있지만 `-DynamicEffort $true` 없이는 동작하지 않는다.)
    [string]$Model = "opus",
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$Effort = "max",
    [ValidateSet("low", "medium", "high", "xhigh", "max")]
    [string]$HighRiskEffort = "max",
    [string]$HighRiskModel = "",
    [bool]$DynamicEffort = $false,
    [string]$FallbackModel = "",

    # 0 = 무제한(production 기본). invocation 횟수는 Audit 완료 단위가 아니다.
    [int]$MaxIterationsPerLaunch = 0,
    # 예전 값 3 은 순간적 네트워크 장애 세 번이면 밤샘 Audit 을 끝냈다. 유형 분류 + 같은 지문
    # 반복 감지와 함께 올린다(무한 재시도 방지는 MaxIdenticalFailures 가 담당).
    [int]$MaxConsecutiveFailures = 10,
    [int]$MaxIdenticalFailures = 4,
    [int]$MaxInfraRetries = 60,
    [int]$MaxConsecutiveRateLimitHits = 20,
    [int]$MaxCompletionGateRejections = 5,     # 잘못된 AUDIT_COMPLETE 반복 생성 방지

    # ★ 0 = 무제한(기본). 이 값은 "지출 가드"가 아니었다 — invocation 횟수가 무제한이라 총액을
    #   막지 못하면서, 실질적으로는 **일을 문장 중간에서 자르는** 장치로만 동작했다.
    #   실측 근거: 실제 invocation 들이 $13.83 / $13.27 에서 terminal_reason=completed 로 끝났다
    #   — 일을 마쳐서가 아니라 상한에 닿아서다. 자를 때마다 다음 invocation 이 CLAUDE.md ·
    #   WORK_STATE(2,792줄) · BACKLOG(3,238줄) · QA_COVERAGE · DECISIONS 를 다시 읽는
    #   재오리엔테이션 비용을 새로 낸다. 양수를 주면 예전처럼 invocation 당 상한이 걸린다.
    [int]$MaxBudgetUsd = 0,

    # MaxRuntimeMinutes 는 이제 0(무제한)이 기본이다 — 일하고 있는 Worker 를 벽시계로 자르는 것이
    # 병목이었다. hang 보호는 IdleTimeoutMinutes 가 한다(출력이 그 시간 동안 한 바이트도 안 늘면
    # 느린 게 아니라 멈춘 것이다). double 인 이유는 controlled test 가 몇 초로 실제 실행해
    # 보기 위함이다.
    [double]$MaxRuntimeMinutes = 0,
    [double]$IdleTimeoutMinutes = 25,
    [double]$ProgressIntervalSeconds = 60,
    [int]$ProgressLogEverySeconds = 900,

    [int]$DirtyQuietSeconds = 90,
    [int]$DirtyRetrySeconds = 15,
    [int]$MaxDirtyWaits = 40,
    # 노출 이유는 위와 같다(test seam). production 기본값은 그대로다.
    [int]$RateLimitBaseBackoffSeconds = 60,
    [int]$RateLimitMaxBackoffSeconds = 1800,
    [int]$RateLimitMaxWaitSeconds = 21600,
    [int]$NetworkBaseBackoffSeconds = 15,
    [int]$NetworkMaxBackoffSeconds = 300,
    # 일반 실패(진척 없음)의 재시도 간격. 예전엔 0이라 순간적 네트워크 장애 하나로
    # 3연속 실패가 몇 초 만에 쌓여 AUTO_STOP 됐다.
    [int]$FailureBaseBackoffSeconds = 30,
    [int]$FailureMaxBackoffSeconds = 600,

    [int]$ColdRefreshEvery = 12,

    # 승인된 TEST SERVER 관측(읽기 전용 검증)에 쓴다. 하드코딩하지 않는다 — 비우면 저장소에서 찾는다.
    [string]$TestServerTarget = "",
    [switch]$SkipTestServerProbe,
    [string]$SudoPasswordEnvName = "CLOVIR_TEST_SUDO_PASSWORD",

    # 완료된 Audit을 새 Cycle로 다시 시작할 때 사용한다.
    [switch]$ResetAudit,

    # AUDIT_BLOCKED 원인을 사람이 해결한 뒤 이어서 실행할 때 사용한다.
    [switch]$ResumeBlocked
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "runner_common.ps1")

# ── 경로 ──────────────────────────────────────────────────────────────────────
$AuditDir   = Join-Path $ProjectDir "var\product-audit"
$LogDir     = Join-Path $AuditDir "logs"
$QuarantineDir = Join-Path $AuditDir "quarantine"
$StopFile   = Join-Path $AuditDir "STOP"               # 사용자만 만든다
$AutoStopFile = Join-Path $AuditDir "AUTO_STOP"        # 스크립트의 자동 정지 흔적
$AuditCompleteFile = Join-Path $AuditDir "AUDIT_COMPLETE"
$AuditBlockedFile  = Join-Path $AuditDir "AUDIT_BLOCKED"
$ImplementationRequiredFile = Join-Path $AuditDir "IMPLEMENTATION_REQUIRED"
$ImplementationConsumedFile = Join-Path $AuditDir "IMPLEMENTATION_CONSUMED"
$CycleFile  = Join-Path $AuditDir "cycle.json"
$GateRejectionFile = Join-Path $AuditDir "last_gate_rejection.txt"
$StateFile  = Join-Path $AuditDir "state.json"
$RunnerLog  = Join-Path $AuditDir "runner.log"
$TimingLog  = Join-Path $AuditDir "timings.jsonl"
$SessionIdFile = Join-Path $AuditDir "session_id.txt"
$NextHintFile  = Join-Path $AuditDir "next_invocation.json"
$ResumeContextFile = Join-Path $AuditDir "resume_context.txt"

# 구현 Runner와 동시 실행을 막기 위해 **의도적으로 같은 lock** 을 쓴다.
$SharedRunnerDir = Join-Path $ProjectDir "var\runner"
$SharedLockFile  = Join-Path $SharedRunnerDir "run.lock"
$ProjectCompleteFile = Join-Path $SharedRunnerDir "PROJECT_COMPLETE"

$AuditDocsRel = "docs/product-audit"
$AuditDocsDir = Join-Path $ProjectDir "docs\product-audit"

$RequiredAuditDocs = @(
    "docs/product-audit/PRODUCT_AUDIT_STATE.md",
    "docs/product-audit/PRODUCT_AUDIT_INVENTORY.md",
    "docs/product-audit/PRODUCT_AUDIT_FEATURE_CONTRACTS.md",
    "docs/product-audit/PRODUCT_AUDIT_FINDINGS.md",
    "docs/product-audit/PRODUCT_AUDIT_COVERAGE.md",
    "docs/product-audit/PRODUCT_AUDIT_REPORT.md",
    "docs/product-audit/PRODUCT_AUDIT_HANDOFF.md"
)
$MinDocChars = 400

# 각 PA-RC 블록이 반드시 담아야 하는 기계 필드(사용자가 지정한 Handoff 최소 정보와 1:1).
$RequiredRcFields = @(
    "rc_id", "severity", "priority", "confidence", "problem", "expected", "actual",
    "intent_evidence", "findings", "feature_contracts", "routes", "frontend", "api",
    "backend", "data", "rbac", "integration", "state_transition", "user_impact",
    "implementation_direction", "constraints", "regression_risk", "acceptance_criteria",
    "required_tests", "qa_gaps", "evidence_refs"
)

$StateDefaults = [ordered]@{
    consecutiveFailures        = 0
    consecutiveInfraRetries    = 0
    consecutiveRateLimitHits   = 0
    identicalFailureCount      = 0
    lastFailureSignature       = ""
    lastFailureClass           = ""
    completionGateRejections   = 0
    sessionRotatedForStreak    = $false
    invocationsSinceCold       = 999          # 첫 회차는 항상 COLD
    lastRunAt                  = $null
    lastExitCode               = $null
    lastHeadSha                = ""
    totalRuns                  = 0
    totalIterationsThisLaunch  = 0
}

New-Item -ItemType Directory -Force -Path $AuditDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $SharedRunnerDir | Out-Null
New-Item -ItemType Directory -Force -Path $AuditDocsDir | Out-Null

function Write-AuditLog([string]$msg) { Write-LogLine $RunnerLog $msg }

# ── Audit write allowlist ─────────────────────────────────────────────────────
# Product Auditor가 tracked 파일 중 건드려도 되는 곳. 제품 코드/테스트/설정/migration/
# dependency lock/build artifact/deployment code는 전부 금지다.
function Test-IsAuditOwnedPath([string]$path) {
    if ([string]::IsNullOrWhiteSpace($path)) { return $false }
    $p = $path.Trim().Replace('\', '/')
    if ($p.StartsWith("$AuditDocsRel/")) { return $true }
    if ($p -eq 'docs/BACKLOG.md')     { return $true }
    if ($p -eq 'docs/QA_COVERAGE.md') { return $true }
    if ($p -eq 'docs/DECISIONS.md')   { return $true }
    return $false
}

# ── 워킹트리 스냅샷(무단 변경 탐지의 축) ──────────────────────────────────────
# "이미 더러웠던 경로"와 "Worker가 새로 건드린 경로"를 구분한다. 사용자가 남겨 둔 변경 때문에
# Audit이 시작조차 못 하는 것을 막으면서, Worker의 무단 수정은 놓치지 않기 위함이다.
function Get-UnauthorizedSnapshot {
    $snap = @{}
    foreach ($e in @(Get-GitStatusEntries -RepoDir $ProjectDir)) {
        if (Test-IsAuditOwnedPath $e.Path) { continue }
        if (-not $snap.ContainsKey($e.Path)) {
            $snap[$e.Path] = (Get-PathSignature -RepoDir $ProjectDir -RelPath $e.Path)
        }
    }
    return $snap
}

function Get-SnapshotSignatureText($snap) {
    if ($null -eq $snap -or $snap.Count -eq 0) { return "" }
    return (($snap.Keys | Sort-Object | ForEach-Object { "$_=$($snap[$_])" }) -join ';')
}

function Compare-UnauthorizedSnapshot($before, $after) {
    # Worker가 만든 델타만 돌려준다. 사라진 경로도 위반이다(사용자 변경을 되돌린 것).
    $violations = New-Object System.Collections.Generic.List[string]
    foreach ($k in $after.Keys) {
        if (-not $before.ContainsKey($k)) { $violations.Add("added:$k") }
        elseif ($before[$k] -ne $after[$k]) { $violations.Add("modified:$k") }
    }
    foreach ($k in $before.Keys) {
        if (-not $after.ContainsKey($k)) { $violations.Add("reverted-or-removed:$k") }
    }
    return @($violations.ToArray() | Sort-Object -Unique)
}

# ── 커밋 이력 위반 탐지 ───────────────────────────────────────────────────────
# 예전 판정(`git diff before..after`)은 **순 변화**만 봤다 — 금지 경로를 고쳐 커밋한 뒤
# 되돌려 커밋하면 순 변화가 0이라 탐지되지 않았다. 구간의 커밋을 하나씩 본다.
function Get-CommittedGuardViolations([string]$beforeSha, [string]$afterSha) {
    $bad = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrWhiteSpace($beforeSha) -or [string]::IsNullOrWhiteSpace($afterSha)) { return @() }
    if ($beforeSha -eq $afterSha) { return @() }

    $revs = Invoke-Git -RepoDir $ProjectDir "rev-list" "--reverse" "$beforeSha..$afterSha"
    if (-not $revs.Ok) {
        # 범위 자체가 성립하지 않는다 = history가 다시 쓰였거나 다른 계보로 옮겨갔다.
        $bad.Add("history:rev-list-failed($beforeSha..$afterSha)")
        return @($bad.ToArray())
    }
    foreach ($sha in $revs.Lines) {
        $s = $sha.Trim()
        if ([string]::IsNullOrWhiteSpace($s)) { continue }
        $names = Invoke-Git -RepoDir $ProjectDir "diff-tree" "--no-commit-id" "--name-only" "-r" "-m" $s
        foreach ($p in $names.Lines) {
            $clean = $p.Trim()
            if ([string]::IsNullOrWhiteSpace($clean)) { continue }
            if (-not (Test-IsAuditOwnedPath $clean)) {
                $bad.Add("commit:$($s.Substring(0, [Math]::Min(8, $s.Length))):$clean")
            }
        }
    }
    return @($bad.ToArray() | Sort-Object -Unique)
}

function Get-HistoryIntegrityViolations([string]$beforeSha, [string]$afterSha, [string]$beforeBranch, [string]$afterBranch) {
    $bad = New-Object System.Collections.Generic.List[string]
    if ($beforeBranch -ne $afterBranch) {
        $bad.Add("branch-switched:$beforeBranch->$afterBranch")
    }
    if (-not [string]::IsNullOrWhiteSpace($beforeSha)) {
        if (-not (Test-GitAncestor -RepoDir $ProjectDir -Ancestor $beforeSha -Descendant $afterSha)) {
            # reset --hard / rebase / amend / checkout 로 이력이 다시 쓰였다.
            $bad.Add("history-rewritten:$beforeSha-not-ancestor-of-$afterSha")
        }
    }
    # reflog 로 되돌리기 흔적을 한 번 더 본다(순 변화가 0이라 위 검사만으로 안 잡히는 경우).
    # 주의: $beforeSha 가 빈 문자열이면(커밋이 하나도 없는 저장소) Substring 이 예외를 던지고
    # Supervisor 가 통째로 죽는다. 빈 문자열로 만든 정규식은 모든 줄에 매치되기도 한다.
    if ($beforeSha.Length -ge 7) {
        $shortBefore = $beforeSha.Substring(0, 7)
        $reflog = Invoke-Git -RepoDir $ProjectDir "reflog" "--date=iso" "-n" "40"
        foreach ($line in $reflog.Lines) {
            if ($line -match '(?i):\s*(reset|rebase|checkout|revert|merge --abort|commit \(amend\))') {
                if ($line -match [regex]::Escape($shortBefore)) {
                    $bad.Add("reflog:$($line.Trim())")
                }
            }
        }
    }
    return @($bad.ToArray() | Sort-Object -Unique)
}

function Write-AuditBlocked([string[]]$reasons) {
    $body = @("blocked_at=$(Get-Date -Format o)", "cycle_id=$($script:CycleId)")
    foreach ($r in $reasons) { $body += $r }
    [void](Write-TextFile $AuditBlockedFile (($body -join [Environment]::NewLine)))
    Write-AuditLog "AUDIT_BLOCKED 기록: $($reasons -join ' | ')"
}

# ── Audit Cycle ───────────────────────────────────────────────────────────────
# 새 Cycle이 과거 Audit 완료 결과나 과거 Blind PASS를 근거로 재사용하지 못하게 한다.
function New-AuditCycle([string]$reason) {
    $sha = Get-GitHeadSha -RepoDir $ProjectDir
    $branch = Get-GitBranch -RepoDir $ProjectDir
    $id = "PA-{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
    $cycle = [pscustomobject]@{
        cycleId        = $id
        startedAt      = (Get-Date -Format o)
        startReason    = $reason
        baselineSha    = $sha
        baselineBranch = $branch
        foreignDirty   = @()          # 안정된 사전 dirty(사용자 것) — Audit 한계로 문서에 남긴다
    }
    [void](Write-TextFile $CycleFile ($cycle | ConvertTo-Json -Depth 5))
    Write-AuditLog "새 Audit Cycle 시작 cycle_id=$id baseline=$sha branch=$branch reason=$reason"
    return $cycle
}

function Get-AuditCycle {
    $text = Read-TextOrEmpty $CycleFile
    if (-not [string]::IsNullOrWhiteSpace($text)) {
        try {
            $c = $text | ConvertFrom-Json
            if ($c.cycleId) { return $c }
        } catch { Write-AuditLog "cycle.json 파싱 실패 — 새 Cycle을 만든다: $($_.Exception.Message)" }
    }
    return (New-AuditCycle "no-existing-cycle")
}

function Save-AuditCycle($cycle) { [void](Write-TextFile $CycleFile ($cycle | ConvertTo-Json -Depth 5)) }

function Set-CycleForeignDirty($cycle, [string[]]$paths) {
    <#  cycle.json 을 **재구성해서** 저장한다. `$cycle.foreignDirty = ...` 처럼 직접 대입하면
        예전 스키마로 저장된 cycle.json 에 그 속성이 없을 때 throw 한다([pscustomobject] 는
        없는 속성 대입을 허용하지 않는다 — 실측). 무인 실행 중 죽는 경로를 하나 지운다. #>
    $rebuilt = [pscustomobject]@{
        cycleId        = [string]$cycle.cycleId
        startedAt      = [string]$cycle.startedAt
        startReason    = [string]$cycle.startReason
        baselineSha    = [string]$cycle.baselineSha
        baselineBranch = [string]$cycle.baselineBranch
        foreignDirty   = @($paths | Sort-Object -Unique)
    }
    Save-AuditCycle $rebuilt
    return $rebuilt
}

# ── AUDIT_COMPLETE 기계 Gate ──────────────────────────────────────────────────
# Claude가 marker 하나 만들었다는 이유로 완료를 믿지 않는다. 확인 가능한 것은 전부 확인한다.
function Test-AuditCompletionGate {
    $fail = New-Object System.Collections.Generic.List[string]
    $marker = Read-TextOrEmpty $AuditCompleteFile
    if ([string]::IsNullOrWhiteSpace($marker)) {
        $fail.Add("AUDIT_COMPLETE 가 비어 있다(내용 없는 marker 는 완료로 인정하지 않는다).")
        return [pscustomobject]@{ Passed = $false; Failures = @($fail.ToArray()) }
    }

    $mCycle    = Get-KeyValueFromText $marker "cycle_id"
    $mBaseline = Get-KeyValueFromText $marker "baseline_sha"
    $mFinal    = Get-KeyValueFromText $marker "final_commit"
    $mImplReq  = (Get-KeyValueFromText $marker "implementation_required").ToLowerInvariant()
    $mRcCount  = Get-KeyValueFromText $marker "root_causes"
    $mBlind    = Get-KeyValueFromText $marker "blind_reaudit_consecutive_clean"

    if ($mCycle -ne $script:CycleId) {
        $fail.Add("AUDIT_COMPLETE 의 cycle_id='$mCycle' 가 현재 Cycle '$($script:CycleId)' 와 다르다(과거 Cycle 결과 재사용 금지).")
    }
    if ($mBaseline -ne $script:CycleBaselineSha) {
        $fail.Add("AUDIT_COMPLETE 의 baseline_sha='$mBaseline' 가 현재 baseline '$($script:CycleBaselineSha)' 와 다르다.")
    }
    if ($mImplReq -ne "true" -and $mImplReq -ne "false") {
        $fail.Add("AUDIT_COMPLETE 의 implementation_required 가 true/false 가 아니다('$mImplReq').")
    }
    if ($mRcCount -notmatch '^\d+$') {
        $fail.Add("AUDIT_COMPLETE 의 root_causes 가 정수가 아니다('$mRcCount').")
    }
    if ($mBlind -notmatch '^\d+$' -or [int]$mBlind -lt 2) {
        $fail.Add("Blind Re-Audit 연속 수렴이 2회 미만이다(blind_reaudit_consecutive_clean='$mBlind').")
    }

    # 필수 산출물: 존재 + 최소 분량 + commit 됨
    foreach ($rel in $RequiredAuditDocs) {
        $abs = Join-Path $ProjectDir ($rel -replace '/', '\')
        $body = Read-TextOrEmpty $abs
        if ([string]::IsNullOrWhiteSpace($body)) { $fail.Add("필수 Audit 문서가 없거나 비어 있다: $rel"); continue }
        if ($body.Length -lt $MinDocChars) { $fail.Add("필수 Audit 문서가 실질 내용이라기엔 너무 짧다($($body.Length)자 < $MinDocChars): $rel") }
    }
    $dirtyDocs = @(Get-GitStatusEntries -RepoDir $ProjectDir | Where-Object { $RequiredAuditDocs -contains $_.Path })
    if ($dirtyDocs.Count -gt 0) {
        $fail.Add("최종 Audit 문서가 commit 되지 않았다: $(($dirtyDocs | ForEach-Object { $_.Path }) -join ', ')")
    }

    # final_commit 이 실제로 존재하고 HEAD에서 도달 가능한가
    if ([string]::IsNullOrWhiteSpace($mFinal)) {
        $fail.Add("AUDIT_COMPLETE 에 final_commit 이 없다.")
    } else {
        $head = Get-GitHeadSha -RepoDir $ProjectDir
        if (-not (Test-GitAncestor -RepoDir $ProjectDir -Ancestor $mFinal -Descendant $head)) {
            $fail.Add("final_commit='$mFinal' 가 현재 HEAD 에서 도달 가능한 커밋이 아니다.")
        }
    }

    # Audit 외부 dirty 가 남아 있지 않은가(사전에 기록한 안정 dirty 제외)
    $nowSnap = Get-UnauthorizedSnapshot
    $extra = @($nowSnap.Keys | Where-Object { -not ($script:StableForeignDirty.ContainsKey($_)) })
    if ($extra.Count -gt 0) {
        $fail.Add("Audit allowlist 밖 경로가 dirty 하다: $($extra -join ', ')")
    }

    # Coverage 요약 블록
    $covPath = Join-Path $ProjectDir "docs\product-audit\PRODUCT_AUDIT_COVERAGE.md"
    $cov = Read-TextOrEmpty $covPath
    if ($cov) {
        $covCycle = Get-KeyValueFromText $cov "cycle_id"
        $unseen   = Get-KeyValueFromText $cov "unseen"
        $unseenNo = Get-KeyValueFromText $cov "unseen_without_reason"
        if ($covCycle -ne $script:CycleId) { $fail.Add("COVERAGE 의 cycle_id='$covCycle' 가 현재 Cycle 과 다르다.") }
        if ($unseenNo -notmatch '^\d+$')   { $fail.Add("COVERAGE 요약에 unseen_without_reason 정수 값이 없다.") }
        elseif ([int]$unseenNo -ne 0)      { $fail.Add("이유 없는 UNSEEN 이 $unseenNo 건 남아 있다(전수조사 미완).") }
        if ($unseen -match '^\d+$') {
            # 자기모순 탐지: 요약은 0이라는데 본문에 UNSEEN 이 잔뜩 있으면 요약을 믿지 않는다.
            # 여유 5는 범례/표 머리글/산문에서 이 낱말이 자연스럽게 나오는 몫이다.
            $rawUnseen = ([regex]::Matches($cov, 'UNSEEN')).Count
            if ($rawUnseen -gt ([int]$unseen + 5)) {
                $fail.Add("COVERAGE 요약(unseen=$unseen)과 본문의 UNSEEN 출현 수($rawUnseen)가 맞지 않는다. " +
                          "요약 블록의 수치를 실제 표와 일치시키거나, 남은 UNSEEN 칸에 이유를 적어 해소하라.")
            }
        } else { $fail.Add("COVERAGE 요약에 unseen 정수 값이 없다.") }
    }

    # Blind Re-Audit 기록(최근 2회가 모두 신규 Critical/High 범주 0)
    $statePath = Join-Path $ProjectDir "docs\product-audit\PRODUCT_AUDIT_STATE.md"
    $stateDoc = Read-TextOrEmpty $statePath
    $passes = @([regex]::Matches($stateDoc, '(?im)^\s*blind_pass\s*=\s*(\d+)\s+cycle_id\s*=\s*(\S+)\s+new_critical_high_categories\s*=\s*(\d+)'))
    $mine = @($passes | Where-Object { $_.Groups[2].Value -eq $script:CycleId })
    if ($mine.Count -lt 2) {
        $fail.Add("PRODUCT_AUDIT_STATE.md 에 현재 Cycle 의 blind_pass 기록이 2회 미만이다($($mine.Count)회).")
    } else {
        $lastTwo = @($mine | Select-Object -Last 2)
        foreach ($m in $lastTwo) {
            if ([int]$m.Groups[3].Value -ne 0) {
                $fail.Add("마지막 두 Blind Pass 중 신규 Critical/High 범주가 0이 아닌 회차가 있다(pass=$($m.Groups[1].Value)).")
            }
        }
    }

    # HANDOFF: PA-RC 블록의 필수 필드
    $handoffPath = Join-Path $ProjectDir "docs\product-audit\PRODUCT_AUDIT_HANDOFF.md"
    $handoff = Read-TextOrEmpty $handoffPath
    $blocks = @([regex]::Matches($handoff, '(?s)<!--\s*PA-RC-BEGIN\s+(PA-RC-\d{4})\s*-->(.*?)<!--\s*PA-RC-END\s*-->'))
    $hCycle = Get-KeyValueFromText $handoff "cycle_id"
    if ($hCycle -ne $script:CycleId) { $fail.Add("HANDOFF 의 cycle_id='$hCycle' 가 현재 Cycle 과 다르다.") }

    if ($mImplReq -eq "true") {
        if ($blocks.Count -lt 1) {
            $fail.Add("implementation_required=true 인데 HANDOFF 에 PA-RC 블록이 하나도 없다.")
        }
        if ($mRcCount -match '^\d+$' -and [int]$mRcCount -ne $blocks.Count) {
            $fail.Add("root_causes=$mRcCount 와 HANDOFF 의 PA-RC 블록 수($($blocks.Count))가 다르다.")
        }
        if (-not (Test-MarkerValid $ImplementationRequiredFile)) {
            $fail.Add("implementation_required=true 인데 var/product-audit/IMPLEMENTATION_REQUIRED 가 없거나 비어 있다.")
        } else {
            $reqCycle = Get-KeyValueFromText (Read-TextOrEmpty $ImplementationRequiredFile) "cycle_id"
            if ($reqCycle -ne $script:CycleId) { $fail.Add("IMPLEMENTATION_REQUIRED 의 cycle_id='$reqCycle' 가 현재 Cycle 과 다르다.") }
        }
    } elseif ($mImplReq -eq "false") {
        if (Test-Path -LiteralPath $ImplementationRequiredFile) {
            $fail.Add("implementation_required=false 인데 IMPLEMENTATION_REQUIRED marker 가 남아 있다.")
        }
    }

    foreach ($b in $blocks) {
        $rcId = $b.Groups[1].Value
        $body = $b.Groups[2].Value
        foreach ($f in $RequiredRcFields) {
            $v = Get-KeyValueFromText $body $f
            if ([string]::IsNullOrWhiteSpace($v)) {
                $fail.Add("HANDOFF $rcId 블록에 필수 필드 '$f' 가 없거나 비어 있다.")
            }
        }
        if ((Get-KeyValueFromText $body "rc_id") -ne $rcId) {
            $fail.Add("HANDOFF $rcId 블록의 rc_id 필드가 블록 ID와 다르다.")
        }
        $conf = (Get-KeyValueFromText $body "confidence")
        if ($conf -notmatch '(?i)^(confirmed|strong)$') {
            $fail.Add("HANDOFF $rcId 의 confidence='$conf' — Confirmed/Strong 이 아닌 항목은 구현 Handoff 로 승격하지 않는다.")
        }
    }

    return [pscustomobject]@{ Passed = ($fail.Count -eq 0); Failures = @($fail.ToArray()) }
}

# ── Audit → Implementation lifecycle ──────────────────────────────────────────
function Sync-ImplementationLifecycle {
    # 새 구현 Backlog가 확정된 이상, 과거 PROJECT_COMPLETE 는 더 이상 현재 상태를 표현하지
    # 않는다. 내용을 archive 한 뒤 그 marker만 제거한다(사용자 작업물은 건드리지 않는다).
    if (-not (Test-MarkerValid $ImplementationRequiredFile)) { return }
    if (-not (Test-MarkerValid $ProjectCompleteFile)) { return }

    $archive = Join-Path $AuditDir ("previous_PROJECT_COMPLETE_{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    [void](Write-TextFile $archive (Read-TextOrEmpty $ProjectCompleteFile))
    Remove-Item -LiteralPath $ProjectCompleteFile -Force -ErrorAction SilentlyContinue
    Write-AuditLog "Audit 이 새 구현 Root Cause 를 확정해 과거 PROJECT_COMPLETE 를 archive 후 제거: $archive"
}

# ── 단일 Writer 잠금(구현 Runner와 공유) ──────────────────────────────────────
# 주의: -ResetAudit/-ResumeBlocked 의 상태 변경은 **잠금을 잡은 뒤** 한다. 잠금 밖에서 marker 를
# 건드리면 이미 돌고 있는 Supervisor 의 상태를 밖에서 지우게 된다.
$lock = Open-ExclusiveLock -LockFile $SharedLockFile
if (-not $lock.Acquired) {
    Write-Banner @(
        "다른 Supervisor(PID=$($lock.Holder))가 이미 이 저장소를 잡고 있습니다.",
        "autonomous_runner.ps1 과 product_audit_runner.ps1 은 **절대 동시에** 실행하면 안 됩니다.",
        "이 프로세스는 아무 작업도 하지 않고 종료합니다. 사유: $($lock.Reason)",
        "그 Supervisor 를 멈추려면 해당 STOP 파일을 만들거나 그 PID 를 종료하세요."
    )
    Write-AuditLog "잠금 획득 실패(보유 PID=$($lock.Holder)) — 종료. 사유: $($lock.Reason)"
    exit 4
}

# 구현 Runner용 Stop hook 표시가 상속돼 들어온 경우를 명시적으로 제거한다.
# Audit Worker 는 PROJECT_COMPLETE 규칙의 대상이 아니다(별도 marker를 쓴다).
# 끝날 때 finally 에서 원래 값으로 되돌린다 — 이 프로세스 환경 변경은 **호출한 셸에도 남기** 때문에,
# 되돌리지 않으면 같은 창에서 시작한 사람의 대화형 Claude 세션에까지 영향을 준다(실제로 발생).
$script:EnvSnapshot = Save-EnvSnapshot @("CLOVIR_SUPERVISED", "CLOVIR_PRODUCT_AUDIT", "CLOVIR_SUPERVISOR_PID")
Remove-Item Env:CLOVIR_SUPERVISED -ErrorAction SilentlyContinue
Remove-Item Env:CLOVIR_SUPERVISOR_PID -ErrorAction SilentlyContinue
$env:CLOVIR_PRODUCT_AUDIT = "1"

# 승인된 TEST SERVER 관측 권한에 필요한 **사실**을 시작 시 한 번만 확인한다(매 invocation 마다
# Worker 가 같은 것을 다시 알아내지 않도록). 자격증명은 이 확인에 들어가지 않는다 — 키 인증
# 접속 가능 여부와 `sudo -n` 가능 여부만 본다.
if ([string]::IsNullOrWhiteSpace($TestServerTarget)) {
    $TestServerTarget = Get-TestServerTargetFromRepo -ProjectDir $ProjectDir
}
$script:ServerAccess = [pscustomobject]@{ Probed = $false; SshOk = $false; SudoNoPassword = $false; Detail = "" }
if (-not $SkipTestServerProbe -and -not [string]::IsNullOrWhiteSpace($TestServerTarget)) {
    $script:ServerAccess = Test-TestServerAccess -Target $TestServerTarget
}
$script:SudoCredentialAvailable = -not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($SudoPasswordEnvName, 'Process'))

$promptCold = @'
매 invocation 시작 시 대화 기억보다 저장소의 실제 현재 상태를 우선한다.
**이번 회차는 COLD** — 새 Session이거나, Session이 회전됐거나, 완료 Gate 거부 직후이거나,
주기적 재접지 회차다. 그래서 이번에는 다음을 실제로 읽고 교차 대조한다.

1) CLAUDE.md
2) docs/WORK_STATE.md
3) docs/BACKLOG.md 전체
4) docs/QA_COVERAGE.md 전체
5) docs/DECISIONS.md
6) docs/PROGRESS_STATUS.md
7) docs/WORK_PLAN_INDEX.md
8) docs/product-audit/** 기존 산출물 (특히 PRODUCT_AUDIT_STATE.md, PRODUCT_AUDIT_COVERAGE.md)
9) git status / git log --oneline -20
10) 실제 route/API/schema/test 구조

Audit 문서가 없으면 생성하고, 있으면 이어서 사용한다. 이 재접지는 **이번 호출에서 한 번만**
한다 — 같은 호출 안에서 이미 읽은 문서를 다시 읽지 마라.
'@

$promptWarm = @'
**이번 회차는 WARM** — 직전 호출과 같은 Session을 정상적으로 이어받았다. 너는 직전까지 무엇을
조사하고 있었는지 이미 알고 있다.

- CLAUDE.md · docs/WORK_STATE.md · docs/BACKLOG.md · docs/QA_COVERAGE.md · docs/DECISIONS.md ·
  docs/PROGRESS_STATUS.md · docs/WORK_PLAN_INDEX.md 를 **전체 통독하지 마라.**
- docs/product-audit/PRODUCT_AUDIT_COVERAGE.md 의 **미조사(UNSEEN)·STATIC_ONLY 칸부터 이어서**
  판다. 이미 EXECUTED/OBSERVED 로 증거가 확보된 surface 를 근거 없이 처음부터 다시 조사하지 마라.
- 아래 RUN CONTEXT에 cycle_id·baseline·직전 HEAD 이후 커밋·현재 dirty·직전 Gate 거부 사유가
  들어 있다. 그것으로 위치를 확인하고 곧바로 조사를 이어서 하라.
- Inventory 도 cycle 안에서 **증분**으로 이어 간다. 이미 만든 Inventory 항목을 다시 만들지 말고,
  새로 발견한 surface 만 추가한다.
- 예외 — 아래 중 하나면 그때는 해당 문서를 전체 수준으로 다시 조사하라:
    · 현재 조사 후보가 고갈돼 새 축/영역을 골라야 한다
    · RUN CONTEXT와 실제 저장소 상태가 모순된다
    · **Blind Re-Audit pass 를 수행한다**(이건 원래 "처음 보는 Auditor처럼" 하는 것이다)
    · AUDIT_COMPLETE 직전 최종 교차 확인
'@

$prompt = @'
당신은 ClovirONE Web Assistant의 Whole Product Audit을 수행하는 독립적인 Product Auditor다.
이 작업은 구현 작업이 아니다. 제품 전체를 실제 코드, 테스트, 실행 가능한 검증 환경, 브라우저 동작,
API/DB/RBAC/통합 경로, 사용자 문구까지 근거 기반으로 전수조사해서 현재 Backlog에 없는 문제,
놓친 UX, 의도와 다른 동작, 미완성 기능, 검증 공백을 Root Cause 기준으로 찾아내는 것이 목적이다.

사람이 실시간으로 답하지 않는 비대화형 무인 Audit이다. 질문하지 말고 저장소와 실행 가능한 증거로
스스로 판단한다. 다만 근거가 없으면 의도를 지어내지 말고 UNKNOWN 또는 BLOCKED로 남긴다.

======================================================================
0. 역할 경계 — 당신은 AUDITOR다. IMPLEMENTER가 아니다
======================================================================

절대 제품 소스 코드를 수정하지 마라.
절대 테스트 코드를 추가/수정하지 마라.
절대 설정, migration, build artifact, dependency lockfile, 배포 코드를 수정하지 마라.
절대 문제를 발견했다고 바로 고치지 마라.

tracked write가 허용되는 위치는 아래뿐이다.

- docs/product-audit/**
- docs/BACKLOG.md
- docs/QA_COVERAGE.md
- docs/DECISIONS.md

var/product-audit/** 의 marker/log/state는 runtime 산출물이므로 작성 가능하다.

Supervisor가 매 invocation 전후로 워킹트리 스냅샷(경로별 해시)과 **구간의 모든 커밋**을
검사한다. 금지 경로를 고쳤다가 되돌려도, 중간 커밋에서만 건드려도, branch를 바꾸거나 reset/
rebase로 이력을 다시 써도 탐지된다. 위반이 감지되면 Audit은 AUDIT_BLOCKED로 즉시 중단된다.
자동 revert는 하지 않는다 — 사용자의 변경을 지우지 않기 위해서다.

제품 코드 변경이 필요하다는 결론이 나면 코드 대신 Finding과 Root Cause, 기대 동작, 영향 범위,
구현 방향, 필요한 회귀 테스트를 기록한다. 실제 구현은 이후 autonomous_runner.ps1가 한다.

명령 실행 때문에 tracked 파일이 우연히 변할 수 있는 작업(빌드, 번들 재생성, 스냅샷 갱신,
마이그레이션)은 **아예 하지 마라**. 읽기 전용 검증과 기존 테스트 실행만 한다.

그럼에도 tracked 파일이 우연히 변했다면, 이 invocation 을 끝내기 **전에** `git status` 로 확인하고
**네가 만든 그 변경만** `git checkout -- <경로>` 로 되돌려라. Audit 시작 전부터 있던 사용자의
변경(RUN CONTEXT 의 pre_existing_dirty_paths)은 **절대 건드리지 마라.** 되돌리지 않고 끝내면
Supervisor 가 위반으로 판정해 AUDIT_BLOCKED 로 밤샘 실행 전체를 중단시킨다.

======================================================================
1. 작업 단위와 Continuity
======================================================================

작업 단위는 PRODUCT AUDIT 전체 하나뿐이다.
이번 invocation, 이번 turn, 이번 budget은 완료 단위가 아니다.
context 때문에 호출이 끝나는 것은 정상이며 PowerShell Supervisor가 같은 Session을
지연 없이 --resume한다.

__STATE_RESTORE_SECTION__

이미 조사한 것을 무의미하게 반복하지 말고 Coverage의 미조사 영역과 불확실한 Root Cause부터
진행한다. **이미 CONFIRMED/STRONG 증거를 확보한 surface×axis 칸을 근거 없이 다시 조사하는 것은
전수조사가 아니라 낭비다.** 다시 조사해야 한다면 왜 그 증거를 못 믿는지 COVERAGE에 적어라.

중간 Summary, commit, clean tree, 한 Round 완료는 정지 이유가 아니다.
AUDIT_COMPLETE 또는 AUDIT_BLOCKED가 아니면 다음 조사로 계속한다.
한 invocation에서 한 Round만 하고 멈추지 마라.

======================================================================
2. Skill 사용 계약 — 이름을 추측하지 마라
======================================================================

전수조사에 도움이 되는 Skill이 **실제로 설치되어 있는지 런타임에 확인**한다. 확인 방법은
파일 시스템이다. 최소 다음 위치를 직접 본다.

- 프로젝트: .claude/skills/*/SKILL.md
- 프로젝트: .agents/skills/*/SKILL.md
- 사용자: ~/.claude/skills/*/SKILL.md
- 플러그인: ~/.claude/plugins/cache/*/*/*/.claude/skills/*/SKILL.md 및 */skills/*/SKILL.md
- 활성화 여부: ~/.claude/settings.json, .claude/settings.json 의 enabledPlugins

각 Skill의 **실제 이름(SKILL.md frontmatter의 name), 실제 경로, 버전(있으면)** 을
PRODUCT_AUDIT_COVERAGE.md의 Skill 절에 그대로 적는다.
설치되지 않은 Skill을 "적용했다"고 기록하면 그것은 조작이다. 절대 하지 마라.

관심 대상(있으면 쓰고, 없으면 없다고 적는다):
ui-ux-pro-max / impeccable / redesign-existing-projects / ux-writing /
humanize-korean 계열(im-not-ai) / frontend-design / a11y-debugging / chrome-devtools

참고 — 2026-08-12 18시 시점에 **실제로 확인된** 설치 위치다. 이것을 사실로 가정하지 말고 매번
다시 확인하라(사용자가 지웠거나 옮겼을 수 있다 — 실제로 이 목록은 같은 날 한 번 바뀌었다).
  .claude/skills/ui-ux-pro-max/                             (프로젝트 scope)
  .claude/skills/impeccable/                                (프로젝트 scope, + settings.local.json hook)
  ~/.claude/skills/redesign-existing-projects/              (사용자 전역, Taste 계열)
  ~/.claude/skills/ux-writing/                              (사용자 전역, 참고 리소스 9개 포함)
  ~/.claude/plugins/cache/im-not-ai/humanize-korean/2.1.0/  (.claude/settings.json 에서 활성화)
다섯 개 모두 설치되어 있으므로 UI/UX · UX Writing · 한국어 축에서 **skill_gap 을 쓸 이유가 없다.**
그런데도 못 쓰겠다면 그 이유를 구체적으로 적어라(추측으로 "미설치"라고 쓰지 마라).

**Skill이 없다고 해서 Audit을 멈추지 마라.** Skill은 가속기이고, 축(axis) 자체가 필수다.
없으면 이 프롬프트의 내장 rubric으로 그 축을 수행하고, COVERAGE에 다음을 남긴다.

  skill_gap: <이름> — 미설치, 대체 방법=<무엇으로 대신했는지>, 신뢰도 영향=<서술>

축 자체를 어떤 방법으로도 덮을 수 없을 때만 BLOCKED다.

적용 우선순위:
사용자 업무 성공 > 기능 정확성 > 데이터/RBAC/보안 경계 > 명확한 UX >
일관성/접근성 > UX Writing > 한국어 자연스러움 > 시각적 완성도

UX Writing을 먼저 적용하고 한국어 humanization은 그 뒤에 적용한다. humanization은 기술 용어,
제품명, 상태값, API/필드명, 수치의 의미를 바꾸면 안 된다. 짧은 버튼명을 억지로 문학적으로
바꾸지 않는다.

======================================================================
3. 사실과 '의도된 기능' 판단 규칙
======================================================================

현재 코드의 동작을 곧바로 제품 의도라고 간주하지 마라.
Expected Behavior와 Actual Behavior를 분리한다.

의도 판단 근거 우선순위:
1) 명시적 제품 정책, 요구사항, 승인된 설계/업무 규칙
2) 현재 CLAUDE.md와 프로젝트 SSOT 문서
3) API schema/contract와 공식 데이터 모델
4) 신뢰할 수 있는 테스트가 표현하는 계약
5) 서로 일치하는 Frontend/Backend 흐름
6) 코드 주석/명명/관례

1~4의 근거가 없고 코드 자체밖에 없으면 의도를 확정하지 마라. Expected Behavior를 INFERRED로
표시하고 confidence를 낮춘다. 문서와 코드가 충돌하면 문서를 옳다고 가정하지 말고 Conflict
Finding으로 기록한다.

Feature Contract 최소 필드: Feature/Workflow 이름, Actor/Role, 목적, Entry point, Precondition,
Allowed state, Input/validation, Expected transition/effect, Success feedback/navigation,
Failure behavior/recovery, Forbidden behavior, Data/API/RBAC/integration dependencies,
Intent evidence, Confidence.

======================================================================
4. Inventory와 Coverage
======================================================================

제품 전체 Surface Inventory를 만든다. 단순 Route 목록으로 끝내지 마라.

최소 Inventory: User/Admin route와 page · Layout/navigation/sidebar/header/tab/breadcrumb ·
Dialog/drawer/popover/menu · Form/action/button/bulk action · Search/filter/sort/pagination ·
Empty/loading/error/success/permission-denied state · Frontend service/API client ·
Backend endpoint/service/job/worker · DB entity/relation/transaction · RBAC role/permission/scope ·
상태값과 state transition · 외부 integration · background/async job · notification/audit/history ·
user-facing text source · feature flag/configuration · 기존 unit/integration/e2e/regression/static
checks · dead/orphan/mock/stub/TODO 후보 · 배포/설정/migration/health 경로 · 스케줄/만료/타임존 로직.

Coverage 문서에서 각 (Surface x Audit Axis) 의 상태를 명시한다.
UNSEEN / STATIC_ONLY / OBSERVED / EXECUTED / BLOCKED / NOT_APPLICABLE

'봤다'와 '실제로 동작을 검증했다'를 혼동하지 마라. 정적 분석만 한 영역을 EXECUTED로 적지 마라.
UNSEEN으로 남기는 칸에는 반드시 이유를 같이 적는다. 이유 없는 UNSEEN이 하나라도 남아 있으면
Supervisor의 완료 Gate가 거부한다.

PRODUCT_AUDIT_COVERAGE.md 안에 아래 기계 요약 블록을 **정확히 이 형식으로** 유지한다.

<!-- COVERAGE-SUMMARY
cycle_id=<현재 Cycle ID>
total_cells=<정수>
unseen=<정수>
unseen_without_reason=<정수>
static_only=<정수>
observed=<정수>
executed=<정수>
blocked=<정수>
not_applicable=<정수>
-->

======================================================================
5. Audit Axis — 전부 덮어야 한다
======================================================================

Round 번호를 기계적으로 한 번씩 돌고 끝내지 마라. Inventory/Coverage 기반으로 미조사와 위험이
높은 영역을 반복해서 판다. 각 축의 결과는 다른 축의 새 조사 대상을 만든다.

A. Baseline / Inventory / 기존 증거
B. Product Intent / Feature Contract
C. Functional (create/read/update/delete, search, filter, sort, pagination, upload/download,
   approval/reject, schedule/cancel/retry, bulk action, navigation, refresh)
D. Workflow — 개별 기능이 정상이어도 end-to-end 업무 흐름이 끊기는 곳
E. Frontend / API / Backend / DB 일관성 — 같은 정책을 네 층이 같게 표현하는가
F. RBAC / Scope / State — UI에서 버튼을 숨기는 것과 실제 API authorization을 구분한다.
   direct URL/direct API, organization/resource scope, admin/user 경계, state machine의
   허용/금지 transition
G. Integration — 외부 연동(n8n, Claude Runner, Notion 등) 경계와 실패 전파
H. Negative / Edge — 빈 값, 잘못된 값, 너무 긴 값, 중복, 없는 ID, 삭제된 객체
I. Recovery / Retry / Idempotency — 실패 후 재시도, rollback, stale state, duplicate job,
   중복 제출, 부분 실패. 사용자가 실패 후 무엇을 해야 하는지 알 수 있는가
J. Concurrency — 동시 수정, race, transaction 경계, lock, WAL/busy 처리
K. AI / Runner / Job — 대화 상태, intent, job 수명주기, 취소/재시도/타임아웃
L. UI / UX  (아래 6절에서 별도로 상세히 규정한다 — 이번 Audit의 중점 축이다)
M. Accessibility — keyboard/focus/tab order/aria/contrast/modal focus trap/error association
N. Responsive / Windows 배율 — FHD/QHD/4K, 125%/150%/175% 배율, 좁은 폭, 축소/확대
O. Light / Dark — 두 테마에서 대비, 상태색, 그림자, 이미지/아이콘, 깨짐과 정보 손실
P. UX Writing — button, label, helper, validation, error, confirmation, empty, loading,
   success, notification, tooltip, onboarding, permission denied. 존재하는 문구뿐 아니라
   **없어서 문제인 문구**를 찾는다
Q. Terminology — 같은 개념이 화면마다 다른 용어로 불리는가
R. Korean naturalness — 번역투, AI 문체, 어색한 조사/어미. 기술적 정확성은 절대 희생하지 않는다
S. Performance — 체감 성능, 불필요한 request/re-render, 큰 list/table, N+1, loading feedback
T. Observability — error → log → correlation → history/audit trail 추적 가능성
U. Security Behavior — authorization bypass, IDOR, 민감정보 노출, 과도한 error detail,
   session/upload 경계. 침투 테스트를 흉내 내지 말고 코드와 안전한 범위의 behavior audit만 한다
V. Deploy / Configuration / Migration / Health — 배포 스크립트, 설정 기본값, migration 순서와
   되돌리기, health/readiness, 롤백 경로
W. Timezone / DST / Schedule / Expiration — UTC 저장 규약 위반, Asia/Seoul 표시, cron 평가,
   만료/보존기간 계산
X. Dead / Stub / Mock / Orphan — 메뉴 없는 route, route 없는 메뉴, UI 없는 API, Backend 없는 UI,
   dead dialog, TODO/mock/hardcoding, 구현하다 만 feature
Y. Regression Gap — 기능이 망가져도 현재 테스트가 잡는가. 테스트가 존재한다는 사실이 아니라
   실제 계약을 검증하는지 본다
Z. Documentation Drift — docs가 현재 구현과 다른 곳, 이미 해결됐는데 미해결로 남은 행,
   해결 안 됐는데 완료로 적힌 행

======================================================================
6. UI/UX 축 — 현재 UI 보존은 목표가 아니다 (사용자 지시)
======================================================================

**현재 구현을 기준점으로만 사용하라. 지키는 것이 목표가 아니다.**
2026년 기준의 현대적인 Enterprise SaaS / AI Product 수준에서 전체 UI/UX를 다시 평가하라.

IA, Layout, Navigation, Page Structure, Component, Typography, Color System, Density,
Interaction, Motion, Empty State, Loading, Feedback, Form, Table, Dashboard, Chat UI가
낡았거나 제품 완성도를 떨어뜨린다면 **기존 구현을 과감하게 재설계하는 후보를 제안하라.**

단순 CSS 보정이나 spacing 조정 수준에 머물지 마라. 필요하면 Page 구조, Component 구조,
Navigation 구조, Workflow 자체까지 다시 설계하는 안을 내라.

목표:
- 더 현대적이고 세련된 시각 디자인
- 더 명확한 정보 위계
- 더 좋은 업무 흐름
- 더 적은 클릭과 인지 부담
- 더 일관된 Component System
- 더 완성도 높은 Light/Dark Theme
- 더 좋은 Responsive / FHD / QHD / 4K 대응
- 더 좋은 Accessibility
- 더 자연스러운 UX Writing
- AI Product에 어울리는 세련된 Interaction
- Enterprise 제품답지만 올드하지 않은 디자인

현재 구현이 이 목표를 방해한다면 기존 Component나 Page를 유지할 필요가 없다.

**절대 금지선(이건 재설계 자유의 예외다):** 기능 정확성, 데이터 구조, RBAC, 업무 정책,
사용자 권한, 실제 제품 Workflow를 망가뜨리면서 시각적으로만 화려하게 만드는 제안은 하지 마라.
재설계 후보마다 "이 변경이 기능/데이터/권한/업무 흐름을 바꾸는가"를 명시하고, 바꾼다면 그것이
의도된 개선인지 부작용인지 구분해서 적는다.

ui-ux-pro-max / impeccable / redesign-existing-projects(Taste) / ux-writing 이 설치되어 있으면
**적극적으로** 사용한다. redesign 계열은 Scan/Diagnose만이 아니라 재설계 후보 도출에도 쓴다.
다만 **직접 코드를 고치지는 않는다** — 이 Runner에서는 제안과 근거까지만 만든다.

Skill이 없을 때 쓰는 내장 rubric(최소 이 목록으로 각 주요 화면을 평가한다):
1) 첫 화면에서 "지금 무엇을 해야 하는가"가 3초 안에 보이는가
2) 페이지의 primary action이 정확히 하나이고 시각적으로 그렇게 보이는가
3) 정보 위계가 3단계 이내로 읽히는가(제목 → 요약 → 상세)
4) 같은 의미가 같은 component/pattern으로 표현되는가(다르면 Root Cause 후보)
5) 표/목록: 밀도, 정렬, 열 우선순위, 빈 상태, 로딩, 오류, 페이지네이션, 대량 데이터
6) 폼: 라벨/도움말/검증 시점/오류 연결/키보드 흐름/저장 피드백
7) 대시보드: 지표가 의사결정으로 이어지는가, 장식용 카드가 아닌가
8) Chat/AI UI: 상태(대기/생성중/실패/취소), 스트리밍 피드백, 재시도, 컨텍스트 표시
9) 과도한 card/radius/icon tile/gradient, 약한 위계 등 AI-generated SaaS 냄새
10) Motion: 목적 있는 전환인가, 지연을 늘리기만 하는가
11) Light/Dark 각각에서 대비와 상태색이 성립하는가
12) 좁은 폭/고배율에서 정보가 사라지거나 겹치는가

이 축의 Finding은 다른 축과 같은 방식으로 Root Cause로 병합한다. 화면 30개에서 같은 문제가
보인다고 Backlog 30건을 만들지 마라 — 공통 component/토큰/패턴 하나가 Root Cause다.

======================================================================
7. 실제 동작 검증과 안전 경계
======================================================================

정적 코드만 보고 '동작한다'고 단정하지 마라. 실행 가능한 기존 test/harness/browser/dev server가
있으면 실제로 사용한다. Observed와 Inferred를 구분한다.

### 승인된 TEST SERVER에서의 관측 권한 (CLAUDE.md §9)
아래 RUN CONTEXT의 `test_server`가 승인된 TEST SERVER(`10.100.64.X` 대역)다. Production이 아니다.
**관측·검증을 위해 필요한 것은 사람을 기다리지 말고 네가 직접 한다.**

- SSH 비대화형 접속(`-o BatchMode=yes`), 원격 상태 조회, 로그·설정·DB 읽기
- 서비스/health/revision 확인, nginx·systemd 상태 확인
- 검증에 필요한 도구(browser/Playwright 등) 설치와 실행
- 검증에 필요한 QA 계정·테스트 데이터 생성 — 없다는 이유로 BLOCKED로 미루지 마라
- sudo가 필요하면 `sudo_credential=available`일 때 환경변수 `__SUDO_ENV_NAME__`의 값을
  **stdin으로만** 넘긴다(`sudo -S -p ""`). 비밀번호를 명령행·로그·파일·문서·커밋 어디에도
  절대 쓰지 마라. `sshpass` 금지. 값을 에코하지 마라.
- 이 권한은 승인된 TEST SERVER 대역에만 적용된다. 다른 서버로 확장하지 않는다.

### 그럼에도 Auditor의 역할 경계는 그대로다 (이건 자격증명 문제가 아니라 역할 문제다)
- **배포/재배포/롤백을 실행하지 마라.** 그것은 PHASE 2(구현 Runner)의 일이다. Audit은 배포
  경로·스크립트·설정을 **읽고 평가**하되 실제 배포를 트리거하지 않는다.
- **제품 상태를 바꾸는 destructive action을 강행하지 마라** — 실사용자 데이터 삭제, 승인 처리,
  외부 시스템(Notion 등) 쓰기. 격리된 test fixture·전용 QA 계정·disposable 데이터를 우선한다.
- 저장소의 제품 코드/테스트/설정/migration은 절대 수정하지 않는다(0절 write guard).

필수 Workflow를 안전한 환경에서 실제 검증할 방법이 전혀 없고 정적/기존 테스트로도 동등한 증거를
확보할 수 없다면 그 칸을 BLOCKED로 기록한다. 다른 독립 Audit은 계속하고, 마지막까지 필수
Coverage가 남으면 그때 AUDIT_BLOCKED를 만든다. **한 blocker 때문에 다른 조사를 멈추지 마라.**

======================================================================
8. Finding과 Root Cause
======================================================================

현상 하나마다 Backlog 한 건을 만들지 마라. Finding은 증거이고 Root Cause가 구현 단위다.

각 Finding 최소 필드: Finding ID · Root Cause ID · Type(defect / intent-mismatch / ux-gap /
redesign / improvement / content / test-gap / tech-debt / blocker) · Severity(Critical/High/
Medium/Low) · Confidence(Confirmed/Strong/Probable/Hypothesis/Blocked) · Surface/Actor/State ·
Expected · Actual · Evidence · Reproduction 또는 static trace · User/Business impact ·
Root Cause 또는 hypothesis · Affected scope · Implementation direction ·
Required regression tests · Related existing Backlog IDs.

같은 공통 component, permission path, API contract, state transition, terminology rule, UX rule,
error handling 때문에 여러 페이지에서 같은 현상이 생기면 **하나의 Root Cause로 병합**하고
영향 페이지를 나열한다.

Confirmed/Strong이 아닌 Hypothesis를 구현 Handoff로 승격하지 마라. 추가 조사로 신뢰도를 높이거나
PRODUCT_AUDIT_FINDINGS.md에만 남긴다.

======================================================================
9. Audit 문서 SSOT
======================================================================

1) docs/product-audit/PRODUCT_AUDIT_STATE.md
   현재 상태 · 마지막으로 확인한 사실 · 다음 조사 후보 · 현재 blocker ·
   Blind Re-Audit pass 기록. Blind pass는 아래 형식의 줄을 **정확히** 남긴다.
       blind_pass=<회차> cycle_id=<현재 Cycle> new_critical_high_categories=<정수> at=<ISO8601>
2) docs/product-audit/PRODUCT_AUDIT_INVENTORY.md   — 제품 전체 Surface Inventory
3) docs/product-audit/PRODUCT_AUDIT_FEATURE_CONTRACTS.md — 근거 기반 Feature/Workflow Contract
4) docs/product-audit/PRODUCT_AUDIT_FINDINGS.md    — 모든 Finding과 Root Cause mapping
5) docs/product-audit/PRODUCT_AUDIT_COVERAGE.md    — Surface x Axis Coverage + Skill 절 + 요약 블록
6) docs/product-audit/PRODUCT_AUDIT_REPORT.md      — 최종 요약, Root Cause 분포, 미해결 blocker,
   구현 우선순위, 검증 한계
7) docs/product-audit/PRODUCT_AUDIT_HANDOFF.md     — 구현 계약(아래 10절)

Audit checkpoint마다 필요한 문서를 갱신하고 git commit한다. Commit에는 allowlist 경로만 포함한다.

======================================================================
10. PRODUCT_AUDIT_HANDOFF.md — 구현으로 넘기는 계약
======================================================================

BACKLOG에 한 줄만 넘기고 Audit의 깊은 조사 결과를 버리면 안 된다. 구현 가능한 Root Cause마다
아래 블록을 만든다. **주석 구분자와 필드 이름은 기계가 검증하므로 정확히 지켜라.**

문서 맨 위에 다음 한 줄을 둔다.
    cycle_id=<현재 Cycle ID>

각 Root Cause:

<!-- PA-RC-BEGIN PA-RC-0001 -->
rc_id: PA-RC-0001
severity: Critical|High|Medium|Low
priority: P0|P1|P2|P3
confidence: Confirmed|Strong
problem: 한 문단으로 문제 정의
expected: 기대 동작(근거와 함께)
actual: 실제 동작
intent_evidence: 의도의 근거(문서/스키마/테스트/정책). 없으면 INFERRED 라고 쓰고 이유
findings: 관련 Finding ID 목록
feature_contracts: 관련 Feature Contract 이름 목록
routes: 영향 Route/Page 목록
frontend: 영향 Frontend Component/파일
api: 영향 API endpoint
backend: 영향 Backend 모듈/서비스
data: 영향 DB/데이터 구조
rbac: 영향 RBAC/Scope
integration: 영향 외부 연동
state_transition: 영향 상태 전이
user_impact: 사용자/업무 영향
implementation_direction: 구현 방향
constraints: 구현 시 반드시 지켜야 할 제약(CLAUDE.md 불변 규칙 포함)
regression_risk: 회귀 위험과 그 범위
acceptance_criteria: 구현 완료로 인정하기 위한 검증 가능한 조건(항목별로)
required_tests: 반드시 추가/실행해야 하는 테스트
qa_gaps: 관련 QA_COVERAGE 공백
evidence_refs: 원본 증거 위치(FINDINGS/CONTRACTS/COVERAGE의 절, 파일:줄)
<!-- PA-RC-END -->

모든 필드는 **비어 있으면 안 된다**. 해당 없음이면 "해당 없음 — <이유>" 라고 적는다.
confidence는 Confirmed 또는 Strong만 허용된다(그 외는 Handoff로 승격하지 않는다).
PA-RC ID는 안정적이어야 한다 — 한 번 부여한 번호를 재사용하거나 바꾸지 마라.

======================================================================
11. Backlog Handoff
======================================================================

Audit이 수렴하기 전에 docs/BACKLOG.md를 발견 즉시 수백 건으로 오염시키지 마라. 먼저
PRODUCT_AUDIT_FINDINGS에서 중복 제거와 Root Cause merge를 끝낸다.

최종 Handoff 시:
- 기존 BACKLOG 전체와 대조해서 이미 있는 Root Cause는 중복 생성하지 않는다.
- 기존 항목에 새 영향 범위/증거를 붙일 수 있으면 갱신한다.
- 새 Confirmed/Strong 미해결 Root Cause만 승격하고, 각 행에 `PA-RC-XXXX` 와
  `docs/product-audit/PRODUCT_AUDIT_HANDOFF.md` 참조를 남긴다.
- QA gap은 docs/QA_COVERAGE.md에 반영한다.
- 중요한 제품 정책/설계 결정이 새로 확정된 경우에만 docs/DECISIONS.md를 갱신한다.
- 구현이 필요한 항목이 하나라도 있으면 var/product-audit/IMPLEMENTATION_REQUIRED 를 만든다.
  내용은 정확히 아래 키를 포함한다.
      cycle_id=<현재 Cycle ID>
      created_at=<ISO8601>
      baseline_sha=<현재 Cycle baseline>
      handoff=docs/product-audit/PRODUCT_AUDIT_HANDOFF.md
      root_causes=<PA-RC 블록 수>
      audit_commit=<최종 audit commit SHA>

======================================================================
12. 완료 Gate — Supervisor가 기계적으로 검증한다
======================================================================

'문서 많이 씀', 'Backlog 많이 찾음', '테스트 green', '한 번 둘러봄'은 완료가 아니다.

AUDIT_COMPLETE를 만들기 전에 최소 다음을 모두 확인한다.

A. Inventory — 발견 가능한 주요 Surface가 모두 inventory에 있고, 이유 없는 UNSEEN이 없다.
B. Intent — 주요 Feature/Workflow가 Intent evidence와 confidence를 가진 Contract를 가진다.
   의도를 알 수 없는 부분은 UNKNOWN/Conflict/Blocked로 정직하게 남겼다.
C. Axis — 5절 A~Z 축이 모두 Coverage에 반영됐다.
D. Evidence — 정적 추정과 실행 증거가 구분되어 있고, Confirmed/Strong에는 재현 또는 trace가 있다.
   Finding이 Root Cause 기준으로 병합되어 있다.
E. Skill — 사용 가능한 Skill을 실제로 적용했고, 미설치 Skill은 skill_gap과 대체 방법이 적혀 있다.
F. Blind Re-Audit 수렴 — 서로 다른 진입점/Workflow로 처음 보는 Auditor처럼 다시 조사한 pass를
   **2회 연속** 수행했고, 두 pass 모두 새로운 Critical/High Root Cause '범주'가 0이다.
   기존 Finding 목록을 다시 읽으며 체크하는 것은 Blind Pass가 아니다.
   새 Medium/Low가 나오면 무시하지 말고 기록/병합한다.
G. Handoff — REPORT가 있고, Confirmed/Strong actionable Root Cause가 BACKLOG에 중복 없이
   반영됐으며, HANDOFF의 PA-RC 블록이 완전하고, QA gap이 반영됐고, marker가 정확하다.

모든 Gate를 만족하면 **최종 문서를 먼저 commit한 뒤** var/product-audit/AUDIT_COMPLETE 를 만든다.
내용은 아래 키를 정확히 포함하고(기계가 파싱한다), 그 아래에 한국어 요약을 덧붙인다.

    cycle_id=<현재 Cycle ID>
    baseline_sha=<현재 Cycle baseline>
    final_commit=<방금 만든 최종 audit commit SHA>
    implementation_required=true|false
    root_causes=<HANDOFF의 PA-RC 블록 수>
    blind_reaudit_consecutive_clean=<2 이상>
    completed_at=<ISO8601>

요약에는 Inventory/Coverage 요약, Root Cause severity 분포, Blind Re-Audit 결과, 적용한 Skill의
실제 이름/경로, 남은 BLOCKED가 없다는 사실, IMPLEMENTATION_REQUIRED 여부를 적는다.

Supervisor는 이 marker를 그대로 믿지 않는다. 필수 문서 7종의 존재/분량/commit 여부, cycle_id와
baseline 일치, final_commit 도달 가능성, Coverage 요약의 자기모순, blind_pass 기록, HANDOFF의
PA-RC 필수 필드, IMPLEMENTATION_REQUIRED 정합성을 전부 검사한다. 하나라도 어긋나면 marker는
격리되고 **거부 사유가 다음 invocation 프롬프트에 그대로 전달되며** Audit은 계속된다.
그러니 애초에 정확히 만들어라.

필수 Coverage가 사람/환경 때문에 끝내 막히면 AUDIT_COMPLETE를 만들지 말고, 남은 모든 실행 가능한
조사를 끝낸 뒤 var/product-audit/AUDIT_BLOCKED 에 다음을 적는다.
    blocked_at / 막힌 Coverage / 정확한 이유 / 이미 확보한 대체 증거 / 사람이 해야 할 최소 조치

marker를 만든 뒤에는 추가 조사나 코드 수정 없이 invocation을 종료한다.

지금 시작하라.
'@

# ── 루프 본체 ─────────────────────────────────────────────────────────────────
# 종료 코드로 무인 실행의 결과를 구분한다(사람이 로그를 안 봐도 상태를 알 수 있게):
#   0 = AUDIT_COMPLETE(Gate 통과) 또는 test-override 상한 도달
#   3 = 사용자 STOP        4 = 다른 Supervisor 가 잠금 보유
#   5 = AUDIT_BLOCKED      6 = 연속 실패로 AUTO_STOP      7 = 전제조건 실패
$script:FinalExit = 0

try {
    if (Test-Path -LiteralPath $StopFile) {
        $body = (Read-TextOrEmpty $StopFile).Trim()
        Write-Banner @(
            "Product Audit STOP 파일이 있어 실행하지 않습니다.",
            "  경로: $StopFile",
            "  내용: $(if ($body) { $body } else { '(비어 있음)' })",
            "이 파일은 사용자만 만듭니다. 재개하려면 지우고 다시 실행하세요."
        )
        Write-AuditLog "STOP 파일 있음 — Worker 를 한 번도 띄우지 않고 종료: $StopFile"
        $script:FinalExit = 3; exit $script:FinalExit
    }

    if ($ResetAudit) {
        # runtime marker/session/state 만 새 Cycle 로 초기화한다. 과거 Audit 증거
        # (docs/product-audit)는 **절대 지우지 않는다** — 증거는 보존하고, 유효성은
        # '현재 Cycle 소속인가'로 판정한다.
        foreach ($f in @($AuditCompleteFile, $AuditBlockedFile, $ImplementationRequiredFile,
                         $ImplementationConsumedFile, $AutoStopFile, $StateFile, $SessionIdFile,
                         $GateRejectionFile, $CycleFile)) {
            if (Test-Path -LiteralPath $f) {
                [void](Move-MarkerToQuarantine -MarkerPath $f -QuarantineDir $QuarantineDir `
                    -Reasons "reset-audit: 새 Cycle 시작으로 이전 Cycle runtime 상태를 격리")
            }
        }
        Write-Banner @(
            "새 Product Audit Cycle 을 시작합니다 — runtime marker/session/state 를 격리하고 초기화했습니다.",
            "docs/product-audit 아래의 과거 산출물은 증거 보존을 위해 삭제하지 않았습니다.",
            "과거 Cycle 의 Blind Re-Audit PASS 는 새 Cycle 의 완료 근거로 사용되지 않습니다."
        )
        Write-AuditLog "-ResetAudit — 이전 Cycle 의 runtime marker/state/session 을 격리하고 새 Cycle 을 시작한다."
    }

    if ($ResumeBlocked -and (Test-Path -LiteralPath $AuditBlockedFile)) {
        [void](Move-MarkerToQuarantine -MarkerPath $AuditBlockedFile -QuarantineDir $QuarantineDir `
            -Reasons "resume-blocked: 사용자가 원인 해결을 확인하고 재개")
        Write-AuditLog "-ResumeBlocked 지정 — AUDIT_BLOCKED marker 를 격리하고 이어서 진행한다."
        $s = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        $s.consecutiveFailures = 0
        $s.consecutiveRateLimitHits = 0
        $s.completionGateRejections = 0
        [void](Save-StateFile $StateFile $s)
    }

    $problems = @(Test-RunnerPrerequisites -ProjectDir $ProjectDir -ClaudeExe $ClaudeExe)
    if ($problems.Count -gt 0) {
        Write-Banner (@("Product Audit 을 시작할 수 없습니다 — 전제조건이 맞지 않습니다:") + $problems)
        Write-AuditLog "전제조건 실패 — 실행하지 않고 종료: $($problems -join ' | ')"
        $script:FinalExit = 7; exit $script:FinalExit
    }

    $cycle = Get-AuditCycle
    $script:CycleId = [string]$cycle.cycleId
    $script:CycleBaselineSha = [string]$cycle.baselineSha
    $script:StableForeignDirty = @{}
    foreach ($p in @($cycle.foreignDirty)) { if ($p) { $script:StableForeignDirty[[string]$p] = $true } }

    # BLOCKED 를 COMPLETE 보다 먼저 본다 — 둘 다 있으면 "막혔다"가 우선이다(안전한 쪽).
    if (Test-MarkerValid $AuditBlockedFile) {
        Write-Banner @(
            "AUDIT_BLOCKED 상태입니다. 필수 전수조사 Coverage 를 현재 조건에서 완료할 수 없습니다.",
            (Read-TextOrEmpty $AuditBlockedFile),
            "원인을 해결한 뒤 -ResumeBlocked 옵션으로 다시 실행하세요."
        )
        Write-AuditLog "AUDIT_BLOCKED 유효 — 실행하지 않고 종료."
        $script:FinalExit = 5; exit $script:FinalExit
    }

    if (Test-MarkerValid $AuditCompleteFile) {
        $gate = Test-AuditCompletionGate
        if ($gate.Passed) {
            Sync-ImplementationLifecycle
            Write-Banner @(
                "AUDIT_COMPLETE 가 유효하고 기계 Gate 를 통과했습니다(cycle_id=$($script:CycleId)).",
                "다음 단계는 구현입니다: .\scripts\runner\autonomous_runner.ps1",
                "새 Audit Cycle 을 시작하려면 -ResetAudit 로 실행하세요."
            )
            Write-AuditLog "AUDIT_COMPLETE 유효 + Gate 통과 — 새 조사를 실행하지 않고 종료."
            $script:FinalExit = 0; exit $script:FinalExit
        }
        $reasons = ($gate.Failures -join [Environment]::NewLine)
        $q = Move-MarkerToQuarantine -MarkerPath $AuditCompleteFile -QuarantineDir $QuarantineDir -Reasons $reasons
        [void](Write-TextFile $GateRejectionFile ("rejected_at=$(Get-Date -Format o)" + [Environment]::NewLine + $reasons))
        Write-Banner @(
            "기존 AUDIT_COMPLETE 가 기계 Gate 를 통과하지 못해 격리했습니다: $q",
            "사유:", $reasons,
            "Audit 을 계속 진행합니다."
        )
        Write-AuditLog "시작 시점 AUDIT_COMPLETE Gate 거부 — 격리 후 Audit 계속. 사유: $($gate.Failures -join ' | ')"
    }

    if (Test-Path -LiteralPath $AutoStopFile) {
        # 사람이 이 스크립트를 **직접 다시 시작한 것** 자체를 그 실패에 대한 확인으로 본다.
        $autoBody = (Read-TextOrEmpty $AutoStopFile).Trim()
        Write-Banner @(
            "이전 Product Audit 이 연속 실패로 스스로 멈춘 흔적(AUTO_STOP)이 있습니다:",
            "  $autoBody",
            "사용자가 직접 다시 시작했으므로 확인한 것으로 보고 흔적을 정리하고 계속 진행합니다.",
            "정말로 멈춰 두려면 대신 $StopFile 을 만드세요."
        )
        Write-AuditLog "AUTO_STOP 흔적 발견 — 수동 재시작을 확인으로 보고 정리 후 진행. 내용: $autoBody"
        Remove-Item -LiteralPath $AutoStopFile -Force -ErrorAction SilentlyContinue
        $s = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        $s.consecutiveFailures = 0
        $s.consecutiveRateLimitHits = 0
        [void](Save-StateFile $StateFile $s)
    }

    $iterationsThisLaunch = 0
    $foreignDirtyWaits = 0

    Write-AuditLog ("Product Audit Supervisor 시작 PID=$PID projectDir=$ProjectDir cycle_id=$($script:CycleId) " +
        "baseline=$($script:CycleBaselineSha) model=$Model effort=$Effort idleTimeout=${IdleTimeoutMinutes}분 " +
        "maxRuntime=$(if ($MaxRuntimeMinutes -gt 0) { "${MaxRuntimeMinutes}분" } else { '무제한' }) " +
        "testServer=$(if ($TestServerTarget) { $TestServerTarget } else { '(미확인)' }) ssh=$($script:ServerAccess.SshOk) sudoNoPasswd=$($script:ServerAccess.SudoNoPassword)")

    while ($true) {
        $loopSw = [System.Diagnostics.Stopwatch]::StartNew()
        if (Test-Path -LiteralPath $StopFile) {
            Write-AuditLog "STOP 발견(사용자 명시적 중단) — Product Audit 종료: $StopFile"
            $script:FinalExit = 3
            break
        }
        if (Test-MarkerValid $AuditBlockedFile) {
            Write-AuditLog "AUDIT_BLOCKED 유효 — 루프 종료."
            $script:FinalExit = 5
            break
        }
        if ($MaxIterationsPerLaunch -gt 0 -and $iterationsThisLaunch -ge $MaxIterationsPerLaunch) {
            Write-Banner @(
                "controlled test 용 invocation 상한 $MaxIterationsPerLaunch 회에 도달했습니다.",
                "이것은 AUDIT_COMPLETE 가 아닙니다. production 기본값은 0(무제한)입니다."
            )
            Write-AuditLog "invocation 상한 도달(test override) — 종료(AUDIT_COMPLETE 아님)."
            $script:FinalExit = 0
            break
        }

        $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
        if ((Get-IntOr $state.consecutiveFailures) -ge $MaxConsecutiveFailures) {
            $msg = "auto-stopped after $($state.consecutiveFailures) consecutive failures at $(Get-Date -Format o) lastClass=$($state.lastFailureClass)"
            [void](Write-TextFile $AutoStopFile $msg)
            Write-Banner @(
                "Product Audit Worker 가 연속 $($state.consecutiveFailures)회 실패해 자동 중단합니다.",
                "마지막 실패 유형: $($state.lastFailureClass)",
                "원본 로그: $LogDir",
                "원인을 확인하고 고친 뒤 이 스크립트를 다시 실행하면 AUTO_STOP 은 자동으로 정리됩니다."
            )
            Write-AuditLog "연속 실패 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
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
            Write-AuditLog "동일 실패 반복 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            $script:FinalExit = 6
            break
        }
        if ((Get-IntOr $state.consecutiveInfraRetries) -ge $MaxInfraRetries) {
            $msg = "auto-stopped: infra retries ($($state.lastFailureClass)) reached $($state.consecutiveInfraRetries) at $(Get-Date -Format o)"
            [void](Write-TextFile $AutoStopFile $msg)
            Write-Banner @(
                "인프라성 재시도(rate-limit/network/overload/resume)가 $($state.consecutiveInfraRetries)회 연속입니다.",
                "실제 조사가 한 번도 진행되지 않고 있으므로 사람이 확인해야 합니다(네트워크·인증·구독 상태)."
            )
            Write-AuditLog "인프라 재시도 상한 도달 — AUTO_STOP 기록 후 중단: $msg"
            $script:FinalExit = 6
            break
        }
        if ((Get-IntOr $state.completionGateRejections) -ge $MaxCompletionGateRejections) {
            Write-AuditBlocked @(
                "reason=AUDIT_COMPLETE machine gate rejected $($state.completionGateRejections) times",
                "detail=Worker 가 완료 Gate 를 반복해서 만족시키지 못한다. 마지막 거부 사유는 $GateRejectionFile 참고.",
                "action=거부 사유를 사람이 확인하고 해결한 뒤 -ResumeBlocked 로 재개"
            )
            Write-Banner @(
                "AUDIT_COMPLETE 가 기계 Gate 에서 $($state.completionGateRejections)회 거부되어 중단합니다.",
                "마지막 거부 사유: $GateRejectionFile",
                "원인 해결 후 -ResumeBlocked 로 재개하세요."
            )
            $script:FinalExit = 5
            break
        }

        # ── Audit 외부 dirty 처리 ──
        # 목적은 "사람이 지금 편집 중일 때 충돌하지 않는 것" 하나뿐이다. 예전 판정은 서명이
        # N회 연속 같은지만 봤고, 그래서 고정된 사용자 dirty 하나에 매 invocation 마다 수 분씩
        # 태웠다. 이제 **파일 mtime** 을 본다 — 사람이 실제로 타이핑 중이면 mtime 이 계속 갱신되고,
        # 아니면 첫 확인에서 곧장 진행한다. (예전 판은 여기서 무조건 BLOCKED 로 끝나기도 했다 —
        # 사용자가 남겨 둔 파일 하나로 밤샘 실행이 통째로 죽는 구조였다.)
        $dirtySw = [System.Diagnostics.Stopwatch]::StartNew()
        $preSnapshot = Get-UnauthorizedSnapshot
        $newForeign = @($preSnapshot.Keys | Where-Object { -not $script:StableForeignDirty.ContainsKey($_) })
        if ($newForeign.Count -gt 0) {
            $dirtyDecision = Get-DirtyDecision -RepoDir $ProjectDir -QuietSeconds $DirtyQuietSeconds -SelfCaused $false
            if ($dirtyDecision.Proceed) {
                foreach ($p in $newForeign) { $script:StableForeignDirty[$p] = $true }
                $cycle = Set-CycleForeignDirty $cycle @($script:StableForeignDirty.Keys)
                $foreignDirtyWaits = 0
                Write-AuditLog ("Audit allowlist 밖 dirty 경로가 최근 $($dirtyDecision.NewestAgeSeconds)초 동안 변하지 않았다 — 사람이 편집 중이 아니라고 보고 " +
                    "'안정된 사전 상태'로 기록하고 진행한다(이후 이 경로가 변하면 위반으로 판정). 경로: $($newForeign -join ', ')")
            } else {
                $foreignDirtyWaits += 1
                if ($foreignDirtyWaits -ge $MaxDirtyWaits) {
                    foreach ($p in $newForeign) { $script:StableForeignDirty[$p] = $true }
                    $cycle = Set-CycleForeignDirty $cycle @($script:StableForeignDirty.Keys)
                    Write-AuditLog ("dirty 경로가 계속 변하지만 약 $([int]($foreignDirtyWaits * $DirtyRetrySeconds / 60))분을 기다렸으므로 사전 상태로 기록하고 진행한다(무한 대기 방지): " +
                        $dirtyDecision.Detail)
                } else {
                    Write-AuditLog "사람이 편집 중으로 보임 — ${DirtyRetrySeconds}초 뒤 재확인 ($foreignDirtyWaits/$MaxDirtyWaits): $($dirtyDecision.Detail)"
                    if (-not (Start-InterruptibleSleep -Seconds $DirtyRetrySeconds -StopFile $StopFile -LogPath $RunnerLog -Reason "dirty 워킹트리")) {
                        $script:FinalExit = 3; break
                    }
                    continue
                }
            }
            $preSnapshot = Get-UnauthorizedSnapshot     # 대기 뒤 상태로 다시 스냅샷을 잡는다
        } else {
            $foreignDirtyWaits = 0
        }
        $dirtySw.Stop()

        # ── invocation 준비 ──
        $prepSw = [System.Diagnostics.Stopwatch]::StartNew()
        $timestamp = "{0}-{1:d3}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), ($iterationsThisLaunch + 1)
        $logFile = Join-Path $LogDir "$timestamp.log"
        $errFile = "$logFile.err"
        $invocationPromptFile = Join-Path $LogDir "$timestamp.prompt.txt"

        # Persistent Worker Session
        $sessionId = Read-SessionId $SessionIdFile
        $isNewSession = $false
        if ($null -eq $sessionId) {
            $sessionId = [guid]::NewGuid().ToString()
            $isNewSession = $true
            [void](Write-TextFile $SessionIdFile $sessionId)   # 호출 **전에** 저장한다
            Write-AuditLog "새 Product Audit Worker Session 시작 session_id=$sessionId"
        } else {
            Write-AuditLog "기존 Product Audit Worker Session 이어받음(--resume) session_id=$sessionId"
        }

        # ── COLD / WARM 판정 ──
        # WARM = "같은 Session 을 정상 resume 했고 직전 회차가 정상적으로 끝났다".
        # 그 밖에는 COLD 로 다시 접지한다(표류 방지). 주기적으로도 한 번 COLD 로 돌아간다.
        $sinceCold = Get-IntOr $state.invocationsSinceCold 999
        $coldReasons = New-Object System.Collections.Generic.List[string]
        if ($isNewSession) { $coldReasons.Add("new-session") }
        if ($sinceCold -ge $ColdRefreshEvery) { $coldReasons.Add("periodic-refresh(${sinceCold}/${ColdRefreshEvery})") }
        if ($state.lastFailureClass -eq "idle-timeout" -or $state.lastFailureClass -eq "hard-timeout") { $coldReasons.Add("previous-invocation-killed") }
        if (-not [string]::IsNullOrWhiteSpace((Read-TextOrEmpty $GateRejectionFile))) { $coldReasons.Add("gate-rejected") }
        $isCold = ($coldReasons.Count -gt 0)
        $mode = if ($isCold) { "COLD" } else { "WARM" }

        # model/effort: 사용자 지시로 opus/max 고정. -DynamicEffort $true 일 때만 조정된다.
        $useModel  = $Model
        $useEffort = $Effort
        $effortSource = "fixed"
        if ($DynamicEffort) {
            $hint = Read-NextInvocationHint -Path $NextHintFile -LogPath $RunnerLog
            if ($isCold) {
                $useEffort = $HighRiskEffort
                if ($HighRiskModel) { $useModel = $HighRiskModel }
                $effortSource = "cold"
            }
            if ($hint.Found) {
                if ($hint.Effort) { $useEffort = $hint.Effort }
                if ($hint.Model)  { $useModel  = $hint.Model }
                $effortSource = "worker-hint"
                Write-AuditLog "Worker 힌트 적용: effort=$($hint.Effort) model=$($hint.Model) reason=$($hint.Reason)"
            }
        }

        $promptBody = $prompt.Replace("__STATE_RESTORE_SECTION__", $(if ($isCold) { $promptCold } else { $promptWarm }))
        $promptBody = $promptBody.Replace("__SUDO_ENV_NAME__", $SudoPasswordEnvName)
        if ($PromptOverrideFile -and (Test-Path -LiteralPath $PromptOverrideFile)) {
            $promptBody = Read-TextOrEmpty $PromptOverrideFile
        }

        $headBefore   = Get-GitHeadSha -RepoDir $ProjectDir
        $branchBefore = Get-GitBranch  -RepoDir $ProjectDir
        $prevHead     = [string]$state.lastHeadSha
        if ([string]::IsNullOrWhiteSpace($prevHead)) { $prevHead = $headBefore }

        # 런타임 컨텍스트를 프롬프트 뒤에 붙인다 — Worker 가 cycle_id / baseline / 직전 Gate
        # 거부 사유를 알아야 정확한 marker 를 만들 수 있다.
        $lastRejection = Read-TextOrEmpty $GateRejectionFile
        $ctx = New-Object System.Collections.Generic.List[string]
        $ctx.Add("")
        $ctx.Add("======================================================================")
        $ctx.Add("RUN CONTEXT (Supervisor 가 매 invocation 에 주입한다 — 이 값을 그대로 써라)")
        $ctx.Add("======================================================================")
        $ctx.Add("runner=product_audit_runner.ps1")
        $ctx.Add("invocation=$($iterationsThisLaunch + 1)")
        $ctx.Add("started_at=$(Get-Date -Format o)")
        $ctx.Add("resume_mode=$mode$(if ($isCold) { ' (' + ($coldReasons -join ',') + ')' } else { ' (같은 Session 정상 이어받음 — 대형 문서 재독 금지, COVERAGE 미조사 칸부터 이어서)' })")
        $ctx.Add("model=$useModel effort=$useEffort")
        $ctx.Add("cycle_id=$($script:CycleId)")
        $ctx.Add("baseline_sha=$($script:CycleBaselineSha)")
        $ctx.Add("baseline_branch=$($cycle.baselineBranch)")
        $ctx.Add("head=$headBefore")
        $ctx.Add("previous_invocation_head=$prevHead")
        $commitsSince = @()
        if ($prevHead -and $headBefore -and $prevHead -ne $headBefore) {
            $commitsSince = @(Get-GitCommitSubjects -RepoDir $ProjectDir -Count 20 -Range "$prevHead..$headBefore")
        }
        $ctx.Add("commits_since_previous_invocation=$($commitsSince.Count)")
        foreach ($c in $commitsSince) { $ctx.Add("  + $c") }
        $ctx.Add("audit_docs_dir=$AuditDocsRel")
        $ctx.Add("handoff_path=$AuditDocsRel/PRODUCT_AUDIT_HANDOFF.md")
        $ctx.Add("test_server=$(if ($TestServerTarget) { $TestServerTarget } else { '(저장소 설정에서 찾지 못함)' })")
        $ctx.Add("test_server_ssh=$(if (-not $script:ServerAccess.Probed) { 'unprobed' } elseif ($script:ServerAccess.SshOk) { 'ok' } else { 'unreachable' })")
        $ctx.Add("sudo_nopasswd=$(if ($script:ServerAccess.SudoNoPassword) { 'true' } else { 'false' })")
        $ctx.Add("sudo_credential=$(if ($script:SudoCredentialAvailable) { "available (환경변수 $SudoPasswordEnvName — stdin 으로만 사용, 절대 출력 금지)" } else { 'absent' })")
        if ($script:StableForeignDirty.Count -gt 0) {
            $ctx.Add("pre_existing_dirty_paths=$(($script:StableForeignDirty.Keys | Sort-Object) -join ', ')")
            $ctx.Add("note=위 경로는 Audit 시작 전부터 사용자가 남겨 둔 변경이다. 건드리지 말고, Audit 한계로 REPORT 에 기록하라.")
        }
        if (-not [string]::IsNullOrWhiteSpace($lastRejection)) {
            $ctx.Add("")
            $ctx.Add("--- 직전 AUDIT_COMPLETE 가 기계 Gate 에서 거부된 사유(반드시 먼저 해소하라) ---")
            $ctx.Add($lastRejection.Trim())
        }
        $ctx.Add("======================================================================")
        $ctxText = ($ctx -join [Environment]::NewLine)
        $promptBody = $promptBody + [Environment]::NewLine + $ctxText + [Environment]::NewLine
        [void](Write-TextFile $ResumeContextFile $ctxText)

        if (-not (Write-TextFile $invocationPromptFile $promptBody)) {
            Write-AuditLog "프롬프트 파일을 쓰지 못했다($invocationPromptFile) — 이 invocation 을 실패로 세고 재시도한다."
            $state.consecutiveFailures = (Get-IntOr $state.consecutiveFailures) + 1
            [void](Save-StateFile $StateFile $state)
            $iterationsThisLaunch += 1
            continue
        }

        # --permission-mode bypassPermissions: 2026-08-13 controlled probe 로 `auto` 가 무인
        #   실행에서 Write/Bash 를 실제로 거부하는 것을 확인했다. 승인해 줄 사람이 없는
        #   Supervisor 에서 그 거부는 그대로 조사 실패다. Auditor 의 쓰기 경계는 permission
        #   mode 가 아니라 write guard(워킹트리 해시 + 구간의 모든 커밋 + 이력 무결성)가 강제한다.
        # --output-format stream-json --verbose: 활동 신호·진행 표시·rate limit reset 시각용.
        $argList = @(
            "-p",
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json",
            "--verbose"
        )
        # 0 이면 플래그 자체를 붙이지 않는다. CLI 가 `--max-budget-usd 0` 을 "무제한"으로
        # 해석한다는 근거가 없다(오히려 "$0 예산"으로 즉시 중단될 수 있다) — 넘기지 않으면
        # 그 해석에 의존할 필요가 없다.
        if ($MaxBudgetUsd -gt 0) { $argList += @("--max-budget-usd", "$MaxBudgetUsd") }
        if ($isNewSession) { $argList += @("--session-id", $sessionId) }
        else               { $argList += @("--resume", $sessionId) }
        if ($useModel)      { $argList += @("--model", $useModel) }
        if ($useEffort)     { $argList += @("--effort", $useEffort) }
        if ($FallbackModel) { $argList += @("--fallback-model", $FallbackModel) }

        $prepSw.Stop()
        $budgetLabel = if ($MaxBudgetUsd -gt 0) { "`$$MaxBudgetUsd" } else { "무제한" }
        $timeoutLabel = if ($MaxRuntimeMinutes -gt 0) { "hard ${MaxRuntimeMinutes}분" } else { "hard 없음" }
        Write-AuditLog ("Audit Worker invocation 시작 #$($iterationsThisLaunch + 1) mode=$mode model=$useModel effort=$useEffort " +
            "budget=$budgetLabel timeout=$timeoutLabel idle=${IdleTimeoutMinutes}분 headBefore=$headBefore branch=$branchBefore")

        $script:LastProgressLoggedAt = Get-Date
        $progress = {
            param($snap)
            $line = ("  ▶ audit #{0} {1}/{2} · 경과 {3} · 이벤트 {4} · 도구 {5}회{6} · 출력 {7} · 마지막 활동 {8}초 전 · PID {9}" -f `
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

        # ── write guard: 워킹트리 + 구간의 모든 커밋 + 이력 무결성 ──
        $headAfter   = Get-GitHeadSha -RepoDir $ProjectDir
        $branchAfter = Get-GitBranch  -RepoDir $ProjectDir
        $postSnapshot = Get-UnauthorizedSnapshot

        $violations = New-Object System.Collections.Generic.List[string]
        foreach ($v in @(Compare-UnauthorizedSnapshot $preSnapshot $postSnapshot)) { $violations.Add("worktree:$v") }
        foreach ($v in @(Get-CommittedGuardViolations $headBefore $headAfter))     { $violations.Add($v) }
        foreach ($v in @(Get-HistoryIntegrityViolations $headBefore $headAfter $branchBefore $branchAfter)) { $violations.Add($v) }

        if ($violations.Count -gt 0) {
            $reasons = @(
                "reason=audit worker touched tracked paths outside the audit allowlist (or rewrote history)",
                "violations=$($violations -join ' | ')",
                "head_before=$headBefore",
                "head_after=$headAfter",
                "branch_before=$branchBefore",
                "branch_after=$branchAfter",
                "action=변경 내용을 사람이 직접 확인하고 필요한 것만 복구하라. Supervisor 는 자동 revert 하지 않는다."
            )
            Write-AuditBlocked $reasons
            Write-Banner @(
                "AUDIT WRITE GUARD 위반을 감지했습니다.",
                "Product Auditor 가 수정하면 안 되는 경로를 변경했거나 이력을 다시 썼습니다:",
                ($violations -join [Environment]::NewLine),
                "안전을 위해 자동 revert 하지 않고 AUDIT_BLOCKED 로 중단합니다."
            )
            $script:FinalExit = 5
            break
        }

        # ── 실패 분류(유형별) ──
        $progressed = ($headAfter -ne $headBefore) -and (-not [string]::IsNullOrWhiteSpace($headAfter))
        $errText = (Read-TextOrEmpty $errFile)
        $outTail = ""
        if ($exitCode -ne 0) {
            # stdout 은 수십 MB 가 될 수 있다 — 분류에는 꼬리만 본다.
            $outAll = Read-TextOrEmpty $logFile
            if ($outAll.Length -gt 20000) { $outTail = $outAll.Substring($outAll.Length - 20000) } else { $outTail = $outAll }
        }
        $fc = Get-InvocationFailureClass -ExitCode $exitCode -Progressed $progressed -IsNewSession $isNewSession `
            -TimeoutKind $outcome.TimeoutKind -Source $outcome.Source -StdErrText $errText -StdOutText $outTail

        if ($fc.Class -eq "resume-failure") {
            Write-AuditLog "저장된 session_id=$sessionId 를 더 이상 resume 할 수 없다(세션 인프라 문제 — 작업 실패 아님) — 지우고 다음 반복에서 새 Session 으로 즉시 재시작."
            Remove-Item -LiteralPath $SessionIdFile -Force -ErrorAction SilentlyContinue
        }

        $iterationsThisLaunch += 1
        $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog

        if ($fc.Class -eq "ok" -or $fc.Class -eq "progress") {
            $state.consecutiveFailures = 0
            $state.consecutiveInfraRetries = 0
            $state.consecutiveRateLimitHits = 0
            $state.identicalFailureCount = 0
            $state.lastFailureSignature = ""
            $state.sessionRotatedForStreak = $false
            if ($fc.Class -eq "progress") {
                # ★ AUTO_STOP 의 의미는 "종료 코드가 0이 아니다"가 아니라 **"진척이 없다"** 여야 한다.
                Write-AuditLog "exit=$exitCode 이지만 이 invocation 이 커밋을 남겼다($headBefore -> $headAfter) — 진척이 있으므로 연속 실패로 세지 않는다."
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
                # 같은 세션이 결정적으로 계속 실패하면(오염된 세션) 상한 도달 전에 한 번 회전시킨다.
                if ((Get-IntOr $state.consecutiveFailures) -ge 2 -and
                    (-not $state.sessionRotatedForStreak) -and (-not $isNewSession)) {
                    Remove-Item -LiteralPath $SessionIdFile -Force -ErrorAction SilentlyContinue
                    $state.sessionRotatedForStreak = $true
                    Write-AuditLog "같은 Worker Session 에서 연속 실패가 이어져 session_id 를 한 번 회전한다(오염된 세션 복구 시도). 실패 카운터는 그대로 유지한다."
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

        $actualModel = Get-ActualModel $logFile
        $stats = Get-ClaudeResultStats $logFile
        Write-AuditLog ("Audit Worker invocation 종료 #$iterationsThisLaunch exit=$exitCode class=$($fc.Class) exitSource=$($outcome.Source) " +
            "mode=$mode handleCached=$($outcome.HandleCached) session=$sessionId requestedModel=$useModel requestedEffort=$useEffort " +
            "actualModel=$actualModel turns=$($stats.NumTurns) denials=$($stats.PermissionDenials) tools=$($outcome.ToolUses) " +
            "duration=$(Format-Duration ($outcome.DurationMs / 1000)) consecutiveFailures=$($state.consecutiveFailures) " +
            "infraRetries=$($state.consecutiveInfraRetries) identical=$($state.identicalFailureCount) " +
            "totalRuns=$($state.totalRuns) headAfter=$headAfter cycle_id=$($script:CycleId)")
        if ($stats.PermissionDenials -gt 0) {
            Write-AuditLog "경고: 이 invocation 에서 도구 권한 거부가 $($stats.PermissionDenials)건 있었다 — 무인 실행에서는 그대로 조사 손실이다."
        }

        # ── AUDIT_COMPLETE 기계 Gate ──
        if (Test-Path -LiteralPath $AuditCompleteFile) {
            $gate = Test-AuditCompletionGate
            if ($gate.Passed) {
                Sync-ImplementationLifecycle
                Remove-Item -LiteralPath $GateRejectionFile -Force -ErrorAction SilentlyContinue
                $implReq = Test-MarkerValid $ImplementationRequiredFile
                Write-Banner @(
                    "AUDIT_COMPLETE 가 기계 Gate 를 통과했습니다(cycle_id=$($script:CycleId)).",
                    "IMPLEMENTATION_REQUIRED=$implReq",
                    "다음 단계: .\scripts\runner\autonomous_runner.ps1 (PHASE 2 구현)"
                )
                Write-AuditLog "AUDIT_COMPLETE Gate 통과 — Handoff 처리 후 정상 종료. implementationRequired=$implReq"
                $script:FinalExit = 0
                break
            }

            $reasons = ($gate.Failures -join [Environment]::NewLine)
            $q = Move-MarkerToQuarantine -MarkerPath $AuditCompleteFile -QuarantineDir $QuarantineDir -Reasons $reasons
            [void](Write-TextFile $GateRejectionFile ("rejected_at=$(Get-Date -Format o)" + [Environment]::NewLine + $reasons))
            $state = Get-NormalizedState -Path $StateFile -Defaults $StateDefaults -LogPath $RunnerLog
            $state.completionGateRejections = (Get-IntOr $state.completionGateRejections) + 1
            [void](Save-StateFile $StateFile $state)
            Write-Banner @(
                "AUDIT_COMPLETE 가 기계 Gate 를 통과하지 못했습니다($($state.completionGateRejections)/$MaxCompletionGateRejections). 격리: $q",
                $reasons,
                "거부 사유를 다음 invocation 프롬프트에 전달하고 Audit 을 계속합니다."
            )
            Write-AuditLog "AUDIT_COMPLETE Gate 거부($($state.completionGateRejections)/$MaxCompletionGateRejections): $($gate.Failures -join ' | ')"
        }

        if (Test-MarkerValid $AuditBlockedFile) {
            Write-Banner @(
                "Audit Worker 가 필수 Coverage blocker 를 기록했습니다.",
                (Read-TextOrEmpty $AuditBlockedFile),
                "원인을 해결한 뒤 -ResumeBlocked 로 다시 실행하세요."
            )
            Write-AuditLog "Worker 가 AUDIT_BLOCKED 를 기록 — 루프 종료."
            $script:FinalExit = 5
            break
        }

        # ── 백오프: 유형별로 다르게 기다린다 ──
        $backoffSw = [System.Diagnostics.Stopwatch]::StartNew()
        $waited = 0
        if ($fc.Class -eq "rate-limit" -or $fc.Class -eq "overload") {
            # 실제 reset 시각을 알면 지수 백오프 대신 그 시각까지 기다린다(구독 한도는 몇 시간이다).
            $rl = Get-RateLimitInfoFromLog $logFile
            $resetAt = 0
            if ($rl.Found -and $rl.ResetsAt -gt 0) { $resetAt = $rl.ResetsAt }
            if ($resetAt -le 0) { $resetAt = Get-RateLimitResetFromText ($errText + " " + $outTail) }
            $now = Get-UnixNow
            if ($resetAt -gt $now) {
                $waited = [int][Math]::Min($RateLimitMaxWaitSeconds, ($resetAt - $now) + 20)
                Write-AuditLog ("사용량 한도 — CLI 가 알려준 reset 시각까지 기다린다: type=$($rl.Type) utilization=$($rl.Utilization) " +
                    "resetsAt=$resetAt → $(Format-Duration $waited) 대기")
            } else {
                $waited = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveRateLimitHits) `
                    -BaseSeconds $RateLimitBaseBackoffSeconds -MaxSeconds $RateLimitMaxBackoffSeconds
                Write-AuditLog "rate-limit/overload 로 보이지만 reset 시각을 알 수 없다 — $(Format-Duration $waited) 지수 백오프."
            }
        } elseif ($fc.Class -eq "network") {
            $waited = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveInfraRetries) `
                -BaseSeconds $NetworkBaseBackoffSeconds -MaxSeconds $NetworkMaxBackoffSeconds
            Write-AuditLog "일시적 네트워크 장애 — $(Format-Duration $waited) 뒤 같은 조사를 그대로 재시도한다."
        } elseif ($fc.Class -eq "resume-failure") {
            $waited = 0
        } elseif ($fc.Class -eq "auth") {
            Write-Banner @(
                "인증/자격증명 문제로 Audit Worker 가 실패했습니다 — 기다려도 저절로 낫지 않습니다.",
                "  $($errText.Trim() -replace '\s+', ' ')",
                "`claude auth` 상태를 확인하세요. 같은 실패가 $MaxIdenticalFailures 회 반복되면 자동 중단합니다."
            )
            $waited = 60
        } elseif ((Get-IntOr $state.consecutiveFailures) -gt 0) {
            # ★ 예전엔 일반 실패에 대기가 **전혀 없었다.** 네트워크가 10초만 끊겨도 즉시 재시도 →
            #   즉시 실패가 3연속으로 쌓여 몇 초 만에 AUTO_STOP 되고 밤샘 Audit 이 끝났다.
            $waited = Get-BackoffSeconds -Hits (Get-IntOr $state.consecutiveFailures) `
                -BaseSeconds $FailureBaseBackoffSeconds -MaxSeconds $FailureMaxBackoffSeconds
            Write-AuditLog "일반 실패 $($state.consecutiveFailures)회 연속(진척 없음, class=$($fc.Class)) — $(Format-Duration $waited) 대기 후 재시도."
        }
        if ($waited -gt 0) {
            if (-not (Start-InterruptibleSleep -Seconds $waited -StopFile $StopFile -LogPath $RunnerLog -Reason $fc.Class)) {
                $script:FinalExit = 3
                $backoffSw.Stop(); $loopSw.Stop()
                break
            }
        }
        $backoffSw.Stop()
        $loopSw.Stop()

        [void](Write-TimingRecord -Path $TimingLog -Fields ([ordered]@{
            at              = (Get-Date -Format o)
            runner          = "product-audit"
            invocation      = $iterationsThisLaunch
            mode            = $mode
            model           = $useModel
            effort          = $useEffort
            exitCode        = $exitCode
            failureClass    = $fc.Class
            progressed      = $progressed
            turns           = $stats.NumTurns
            costUsd         = $stats.CostUsd
            toolUses        = $outcome.ToolUses
            dirtyCheckMs    = [int]$dirtySw.ElapsedMilliseconds
            promptPrepMs    = [int]$prepSw.ElapsedMilliseconds
            workerStartupMs = $outcome.FirstOutputMs
            workerRunMs     = [int]$workerSw.ElapsedMilliseconds
            backoffMs       = [int]$backoffSw.ElapsedMilliseconds
            totalMs         = [int]$loopSw.ElapsedMilliseconds
        }))
        # 성공했거나 진척이 있었으면 대기 없이 곧장 다음 invocation 으로 이어간다.
    }
    exit $script:FinalExit
} finally {
    Restore-EnvSnapshot $script:EnvSnapshot
    Close-ExclusiveLock -Lock $lock -LockFile $SharedLockFile
    # Ctrl+C 로 중단해도 여기까지 오고 exit 코드는 0 이다 — 로그만 보고 "완료"로 오해하지 않도록
    # 완료 marker 유효 여부를 같은 줄에 남긴다.
    Write-AuditLog "Product Audit Supervisor 종료 PID=$PID exit=$script:FinalExit AUDIT_COMPLETE=$(Test-MarkerValid $AuditCompleteFile)"
}
