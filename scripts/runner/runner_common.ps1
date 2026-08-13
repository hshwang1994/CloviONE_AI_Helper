<#
.SYNOPSIS
  두 Supervisor(autonomous_runner.ps1 / product_audit_runner.ps1)가 공유하는 원시 계층.

.DESCRIPTION
  이 파일은 정책을 담지 않는다. 정책(무엇을 완료로 볼 것인가, 무엇을 쓰면 안 되는가)은 각
  Supervisor 안에 있고, 여기에는 **두 Supervisor가 똑같이 틀리면 안 되는 기계적 사실**만 둔다.

  왜 분리하는가: 2026-08-12 검수 시점에 두 스크립트에 같은 로직이 복사돼 있었고 **이미 갈라져
  있었다** — `Load-State` 의 try/catch 가 audit 쪽에만 있어서, 손상된 state.json 하나로
  autonomous_runner 는 죽고 product_audit_runner 는 살아남는 상태였다. 한쪽만 고치는 사고를
  구조적으로 막는다.

  --- 이 파일이 의존하는, 실측으로 확인한 플랫폼 사실 (2026-08-12 / 2026-08-13 재확인) ---
  1) **Windows PowerShell 5.1에서 `Start-Process -PassThru` 자식의 `ExitCode` 가 `$null` 이
     되는 근본 원인은 프로세스 핸들 미캐시다.** 시작 직후 `$proc.Handle` 을 한 번 읽어
     핸들을 캐시하면 5.1에서도 정확한 exit code 가 나온다. 실측(probe1):
       PS 7.6.3 : 핸들 미접근 ExitCode=7 / 접근 ExitCode=7
       PS 5.1   : 핸들 미접근 ExitCode=<null> / **접근 ExitCode=7**
  2) **PS 5.1에서 `$ErrorActionPreference='Stop'` + native 명령 + stderr 리다이렉트는
     terminating error 다.** git 이 stderr 에 한 줄만 뱉어도(dubious ownership 경고, 없는
     리비전 등) Supervisor 가 통째로 죽던 경로였다. 모든 git 호출은 `Invoke-Git` 을 경유한다.
  3) `[pscustomobject]` 에 **없는 속성을 대입하면 throw 한다**(5.1/7 공통, 실측). state.json
     스키마가 바뀌면 조용히 죽으므로 읽을 때 반드시 정규화한다.
  4) `exit` 는 `try{}finally{}` 의 finally 를 실행하고 종료 코드도 보존한다(5.1/7 공통, 실측).
  5) PS 5.1 `Set-Content -Encoding utf8` 은 **BOM 을 쓴다**(7은 안 쓴다). marker/state/prompt
     를 두 버전이 번갈아 써도 같게 보이도록 BOM 없는 UTF-8 로 통일하고, 읽을 때는 BOM 을 벗긴다.
  6) **(2026-08-13 신규 실측) `Start-Process -RedirectStandardOutput` 이 쓰는 중인 파일을
     부모가 `FileShare::ReadWrite` 로 동시에 열어 길이를 읽을 수 있다.** 8회 폴링 동안
     209 → 1672 바이트로 자라는 것을 실제로 관측했다. 이 사실 위에 **활동 기반 idle timeout**
     과 진행 상황 heartbeat 가 서 있다.
  7) **(2026-08-13 신규 실측) `claude -p --output-format stream-json` 은 `--verbose` 를
     요구하고(없으면 즉시 error), 붙이면 NDJSON 이벤트를 파일로 **실시간 flush** 한다.**
     마지막 줄이 기존 `--output-format json` 과 동일한 `type=result` 객체다 — 종료 판정과
     actualModel 파싱은 그대로 쓰면서 활동 신호·진행 표시·rate limit reset 시각을 함께 얻는다.
  8) **(2026-08-13 신규 실측) NDJSON 안에 `type=rate_limit_event` 가 온다.**
     `{"rate_limit_info":{"status":"allowed_warning","resetsAt":1786744800,
       "rateLimitType":"seven_day","utilization":0.88}}` — `resetsAt` 은 unix epoch 초다.
     추측 백오프 대신 **실제 reset 시각까지** 기다릴 수 있다.
#>

# Set-StrictMode 는 **일부러 켜지 않는다**. dot-source 하면 호출한 Supervisor 전체 스코프에
# 적용되고, "없는 속성 참조"까지 치명적 오류로 만든다 — 무인 운영에서 죽는 경로를 늘리는 것은
# 이 파일의 목적과 정반대다. 대신 모든 함수가 스스로 방어하고 절대 throw 하지 않는다.

# PS 7.3+ 의 native 명령 실패 → terminating error 승격을 끈다. 이 스크립트는 native 명령의
# 실패를 **값으로** 다루고 스스로 판단한다(git 실패는 정상적인 관측 결과다). 5.1 에는 이
# 변수가 없으므로 존재할 때만 건드린다.
if (Test-Path Variable:\PSNativeCommandUseErrorActionPreference) {
    $script:PSNativeCommandUseErrorActionPreference = $false
    $global:PSNativeCommandUseErrorActionPreference = $false
}

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# ── 파일 I/O: BOM 없는 UTF-8 로 통일 ──────────────────────────────────────────

function Read-TextOrEmpty {
    <#  없는 파일 / 읽기 실패 / BOM 을 전부 흡수한다. 절대 throw 하지 않는다. #>
    param([string]$Path)
    try {
        if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
        $text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
        if ($null -eq $text) { return "" }
        return $text.TrimStart([char]0xFEFF)
    } catch { return "" }
}

function Write-TextFile {
    <#  디렉터리 자동 생성 + BOM 없는 UTF-8. 실패는 호출부가 판단할 수 있게 bool 로 돌려준다. #>
    param([string]$Path, [string]$Content)
    try {
        $dir = Split-Path -Parent $Path
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        [System.IO.File]::WriteAllText($Path, [string]$Content, $script:Utf8NoBom)
        return $true
    } catch { return $false }
}

function Test-MarkerValid {
    <#  marker 는 **존재만으로는 부족하고 내용이 있어야** 유효하다. 빈 파일이 실수로 생겨
        프로젝트나 Audit 이 조용히 끝나는 것을 막는다. stop_guard.py 의 판정과 같은 규칙. #>
    param([string]$Path)
    return -not [string]::IsNullOrWhiteSpace((Read-TextOrEmpty $Path))
}

function Write-LogLine {
    <#  append-only 로그. 다른 프로세스가 같은 파일을 잡고 있어도 로깅 때문에 죽지 않는다. #>
    param([string]$Path, [string]$Message)
    $line = "[$(Get-Date -Format o)] $Message"
    for ($i = 0; $i -lt 3; $i++) {
        try {
            $dir = Split-Path -Parent $Path
            if ($dir -and -not (Test-Path -LiteralPath $dir)) {
                New-Item -ItemType Directory -Force -Path $dir | Out-Null
            }
            [System.IO.File]::AppendAllText($Path, $line + [Environment]::NewLine, $script:Utf8NoBom)
            break
        } catch { Start-Sleep -Milliseconds 120 }
    }
    Write-Host $line
}

function Write-ConsoleLine {
    <#  **콘솔에만** 쓴다. 진행 상황 heartbeat 처럼 1분마다 나오는 것을 runner.log 에 그대로
        쌓으면 로그가 heartbeat 로 뒤덮여 정작 상태 전이를 못 찾는다. "작업이 느림"과
        "프로세스가 hang" 을 사람이 실시간으로 구분하게 하는 것이 목적이므로 화면이면 충분하다. #>
    param([string]$Message)
    Write-Host $Message
}

function Write-Banner {
    <#  실행할 수 없는 이유는 로그 한 줄이 아니라 눈에 띄게 출력한다(조용한 no-op 금지). #>
    param([string[]]$Lines)
    $bar = "=" * 78
    Write-Host ""
    Write-Host $bar
    foreach ($l in $Lines) { Write-Host $l }
    Write-Host $bar
    Write-Host ""
}

function Get-UnixNow {
    try { return [long][DateTimeOffset]::UtcNow.ToUnixTimeSeconds() } catch { return 0 }
}

# ── git: PS 5.1 terminating-error 함정을 통과하는 유일한 관문 ──────────────────

function Invoke-Git {
    <#  git 을 호출하고 결과를 **값으로** 돌려준다. 어떤 경우에도 throw 하지 않는다.

        core.quotepath=false: git 은 기본적으로 비ASCII 경로를 "\355\225\234" 처럼 이스케이프해서
        내보낸다. 이 저장소에는 한글 문서명이 있을 수 있고, 이스케이프된 경로는 allowlist 대조를
        조용히 빗나가게 만든다(=금지 경로 변경을 놓친다). 항상 끈다. #>
    param(
        [string]$RepoDir,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs
    )

    $result = [pscustomobject]@{
        ExitCode = -1
        Ok       = $false
        StdOut   = ""
        StdErr   = ""
        Lines    = @()
    }
    if ($null -eq $GitArgs) { $GitArgs = @() }

    $full = @()
    if (-not [string]::IsNullOrWhiteSpace($RepoDir)) { $full += @("-C", $RepoDir) }
    $full += @("-c", "core.quotepath=false")
    # 빈 문자열 원소는 커맨드라인 재조립에서 누락되어 뒤 인자를 한 칸씩 민다(실측된 함정).
    foreach ($a in $GitArgs) { if (-not [string]::IsNullOrEmpty($a)) { $full += $a } }

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = New-Object System.Collections.Generic.List[string]
    $err = New-Object System.Collections.Generic.List[string]
    try {
        $global:LASTEXITCODE = 0
        & git @full 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $err.Add([string]$_) }
            else { $out.Add([string]$_) }
        }
        $result.ExitCode = [int]$LASTEXITCODE
    } catch {
        $err.Add("invoke-git-exception: " + $_.Exception.Message)
        $result.ExitCode = -1
    } finally {
        $ErrorActionPreference = $prevEap
    }

    $result.Lines  = @($out.ToArray())
    $result.StdOut = ($out -join [Environment]::NewLine)
    $result.StdErr = ($err -join [Environment]::NewLine)
    $result.Ok     = ($result.ExitCode -eq 0)
    return $result
}

function Get-GitHeadSha {
    # 주의: 함수 안에서 `$args` 는 자동 변수다(남은 인자). 절대 지역 변수명으로 쓰지 않는다.
    param([string]$RepoDir, [switch]$Short)
    $gitArgs = @("rev-parse")
    if ($Short) { $gitArgs += "--short" }
    $gitArgs += "HEAD"
    $r = Invoke-Git -RepoDir $RepoDir @gitArgs
    if (-not $r.Ok) { return "" }   # 커밋이 하나도 없는 저장소 등 — 빈 문자열로 알린다
    return $r.StdOut.Trim()
}

function Get-GitBranch {
    <#  detached HEAD 면 "HEAD" 를 돌려준다 — 호출부가 브랜치 전환을 판정할 수 있다. #>
    param([string]$RepoDir)
    $r = Invoke-Git -RepoDir $RepoDir "rev-parse" "--abbrev-ref" "HEAD"
    if (-not $r.Ok) { return "" }
    return $r.StdOut.Trim()
}

function Test-GitAncestor {
    <#  $Ancestor 가 $Descendant 의 조상인가. history rewrite(reset/rebase/amend)를 감지하는 축.
        판정 불가(둘 중 하나가 없는 객체 등)는 **거짓**으로 돌려준다 — 안전한 쪽. #>
    param([string]$RepoDir, [string]$Ancestor, [string]$Descendant)
    if ([string]::IsNullOrWhiteSpace($Ancestor) -or [string]::IsNullOrWhiteSpace($Descendant)) { return $false }
    if ($Ancestor -eq $Descendant) { return $true }
    $r = Invoke-Git -RepoDir $RepoDir "merge-base" "--is-ancestor" $Ancestor $Descendant
    return ($r.ExitCode -eq 0)
}

function Get-GitStatusEntries {
    <#  porcelain v1 을 파싱해 (XY, Path) 목록으로 돌려준다.
        - 이름 변경 `R  old -> new` 는 **양쪽 다** 돌려준다(원본 삭제도 변경이다).
        - 따옴표로 감싼 경로는 벗긴다(core.quotepath=false 라 이스케이프는 없다).
        - 추적되지 않은 디렉터리는 `path/` 형태로 접힌 채 온다 — 호출부가 서명으로 다룬다. #>
    param([string]$RepoDir)
    $r = Invoke-Git -RepoDir $RepoDir "status" "--porcelain"
    $entries = New-Object System.Collections.Generic.List[object]
    if (-not $r.Ok) { return @($entries.ToArray()) }

    foreach ($line in $r.Lines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line.Length -lt 4) { continue }
        $xy = $line.Substring(0, 2)
        $rest = $line.Substring(3)
        $paths = @()
        if ($rest -match '^(.*?)\s->\s(.*)$') { $paths = @($Matches[1], $Matches[2]) }
        else { $paths = @($rest) }
        foreach ($p in $paths) {
            $clean = $p.Trim()
            if ($clean.StartsWith('"') -and $clean.EndsWith('"') -and $clean.Length -ge 2) {
                $clean = $clean.Substring(1, $clean.Length - 2)
            }
            if ([string]::IsNullOrWhiteSpace($clean)) { continue }
            $entries.Add([pscustomobject]@{ Status = $xy; Path = $clean.Replace('\', '/') })
        }
    }
    return @($entries.ToArray())
}

function Get-GitCommitSubjects {
    <#  최근 커밋 제목 N개. resume context 를 만들 때 "직전에 무엇을 했나"를 대형 문서 재독
        없이 알려주는 가장 싼 증거다. #>
    param([string]$RepoDir, [int]$Count = 10, [string]$Range = "")
    $gitArgs = @("log", "--no-merges", ("--format=%h %ad %s"), "--date=format:%m-%d %H:%M", "-n", "$Count")
    if (-not [string]::IsNullOrWhiteSpace($Range)) { $gitArgs += $Range }
    $r = Invoke-Git -RepoDir $RepoDir @gitArgs
    if (-not $r.Ok) { return @() }
    return @($r.Lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Get-GitCommitCount {
    param([string]$RepoDir, [string]$Range)
    if ([string]::IsNullOrWhiteSpace($Range)) { return 0 }
    $r = Invoke-Git -RepoDir $RepoDir "rev-list" "--count" $Range
    if (-not $r.Ok) { return 0 }
    return (Get-IntOr $r.StdOut.Trim() 0)
}

function Get-PathSignature {
    <#  워킹트리 경로 하나의 "내용 서명". 목적은 **이미 더러웠던 경로를 Worker 가 추가로
        건드렸는지** 구분하는 것이다(사용자가 남겨 둔 변경 때문에 Audit 이 못 도는 것을 막으면서,
        Worker 의 무단 수정은 놓치지 않기 위함).
        디렉터리는 해시할 수 없으므로 파일 수/총 바이트로 서명한다(상한 5000개). #>
    param([string]$RepoDir, [string]$RelPath)
    try {
        $full = Join-Path $RepoDir ($RelPath -replace '/', '\')
        if ($RelPath.EndsWith('/')) {
            if (-not (Test-Path -LiteralPath $full)) { return "dir:missing" }
            $files = @(Get-ChildItem -LiteralPath $full -Recurse -File -Force -ErrorAction SilentlyContinue |
                       Select-Object -First 5001)
            if ($files.Count -gt 5000) { return "dir:>5000" }
            $bytes = 0
            foreach ($f in $files) { $bytes += $f.Length }
            return "dir:$($files.Count):$bytes"
        }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { return "missing" }
        $h = Get-FileHash -LiteralPath $full -Algorithm SHA256 -ErrorAction Stop
        return "sha256:" + $h.Hash
    } catch { return "unreadable" }
}

function Get-PathNewestWriteAgeSeconds {
    <#  경로(파일 또는 접힌 디렉터리)의 **가장 최근 수정 시각**이 몇 초 전인가.
        사람이 지금 편집 중인지 판정하는 축이다 — "서명이 N회 연속 같은가"보다 훨씬 정확하고
        훨씬 빠르다(예전 판정은 그 확인만으로 매번 330초를 태웠다).
        판정 불가는 아주 큰 값(=오래됨)으로 돌려준다: 알 수 없다는 이유로 무한 대기하지 않는다. #>
    param([string]$RepoDir, [string]$RelPath)
    $unknown = 86400
    try {
        $full = Join-Path $RepoDir ($RelPath -replace '/', '\')
        $newest = $null
        if ($RelPath.EndsWith('/')) {
            if (-not (Test-Path -LiteralPath $full)) { return $unknown }
            $files = @(Get-ChildItem -LiteralPath $full -Recurse -File -Force -ErrorAction SilentlyContinue |
                       Select-Object -First 2000)
            foreach ($f in $files) {
                if ($null -eq $newest -or $f.LastWriteTimeUtc -gt $newest) { $newest = $f.LastWriteTimeUtc }
            }
        } else {
            if (-not (Test-Path -LiteralPath $full)) { return $unknown }   # 삭제된 파일 = 편집 중 아님
            $newest = (Get-Item -LiteralPath $full -Force -ErrorAction Stop).LastWriteTimeUtc
        }
        if ($null -eq $newest) { return $unknown }
        $age = ([DateTime]::UtcNow - $newest).TotalSeconds
        if ($age -lt 0) { $age = 0 }          # 시계 오차/미래 타임스탬프
        return [int][Math]::Round($age)
    } catch { return $unknown }
}

# ── dirty 워킹트리 판정 ───────────────────────────────────────────────────────

function Get-DirtyDecision {
    <#  "지금 Worker 를 띄워도 되는가"를 한 번에 판정한다.

        예전 판정은 `git status --porcelain` 문자열이 **N회 연속 같은지**만 봤다. 그래서
        고정된 dirty 파일 하나가 있으면 30+60+120+120 = 330초를 매 invocation 마다 태웠고,
        실제 운영 로그에서 그 낭비가 그대로 관측됐다(2026-08-13 02:11·06:16 두 구간).
        게다가 그 dirty 는 대부분 **직전에 우리가 죽인 우리 Worker** 가 남긴 것이었다.

        새 판정의 축은 셋이다.
          (1) clean            → 즉시 진행
          (2) 우리가 만든 dirty → 즉시 진행 (SelfCaused: 직전 invocation 전후로 서명이 변했다)
          (3) 그 외            → **가장 최근 수정 시각**을 본다. QuietSeconds 보다 오래됐으면
                                 아무도 지금 타이핑하고 있지 않다 → 진행. 아니면 짧게 기다린다.

        사람이 실제로 편집 중이면 파일 mtime 이 계속 갱신되므로 (3)에서 계속 대기하게 된다. #>
    param(
        [string]$RepoDir,
        [int]$QuietSeconds = 90,
        [bool]$SelfCaused = $false
    )

    $entries = @(Get-GitStatusEntries -RepoDir $RepoDir)
    $paths = @($entries | ForEach-Object { $_.Path } | Sort-Object -Unique)
    $signature = ($paths -join ';')

    $decision = [pscustomobject]@{
        Proceed         = $true
        Reason          = "clean"
        Signature       = $signature
        Paths           = $paths
        NewestAgeSeconds = -1
        Detail          = ""
    }
    if ($paths.Count -eq 0) { return $decision }

    $newest = 999999
    foreach ($p in $paths) {
        $age = Get-PathNewestWriteAgeSeconds -RepoDir $RepoDir -RelPath $p
        if ($age -lt $newest) { $newest = $age }
    }
    $decision.NewestAgeSeconds = $newest
    $decision.Detail = "paths=$($paths.Count) newestWriteAge=${newest}s: " + (($paths | Select-Object -First 8) -join ', ')

    if ($SelfCaused) {
        $decision.Proceed = $true
        $decision.Reason  = "self-caused"
        return $decision
    }
    if ($newest -ge $QuietSeconds) {
        $decision.Proceed = $true
        $decision.Reason  = "stable-quiet"
        return $decision
    }
    $decision.Proceed = $false
    $decision.Reason  = "active-edit"
    return $decision
}

# ── state.json: 스키마가 바뀌어도 죽지 않게 ───────────────────────────────────

function Get-NormalizedState {
    <#  파일이 없거나/손상됐거나/스키마가 달라도 **항상 모든 키가 있는** 객체를 돌려준다.
        [pscustomobject] 는 없는 속성에 대입하면 throw 하므로(실측), 이 정규화가 없으면
        스키마가 한 번 바뀔 때마다 Supervisor 가 조용히 죽는다. #>
    # [ordered] 를 그대로 받도록 IDictionary 로 받는다([hashtable] 로 받으면 순서가 사라져
    # state.json 의 키 순서가 실행마다 뒤바뀐다).
    param([string]$Path, [System.Collections.IDictionary]$Defaults, [string]$LogPath)

    $raw = $null
    $text = Read-TextOrEmpty $Path
    if (-not [string]::IsNullOrWhiteSpace($text)) {
        try { $raw = $text | ConvertFrom-Json }
        catch {
            if ($LogPath) { Write-LogLine $LogPath "state 파일을 파싱하지 못해 기본값으로 복구한다($Path): $($_.Exception.Message)" }
            $raw = $null
        }
    }

    $out = [ordered]@{}
    foreach ($key in $Defaults.Keys) {
        $value = $Defaults[$key]
        if ($null -ne $raw) {
            try {
                if ($raw.PSObject.Properties.Name -contains $key) { $value = $raw.$key }
            } catch { }
        }
        $out[$key] = $value
    }
    return [pscustomobject]$out
}

function Save-StateFile {
    param([string]$Path, $State)
    return (Write-TextFile $Path ($State | ConvertTo-Json -Depth 6))
}

function Get-IntOr {
    <#  JSON 에서 온 값은 null / 문자열 / double 일 수 있다. 산술 전에 항상 통과시킨다. #>
    param($Value, [int]$Default = 0)
    if ($null -eq $Value) { return $Default }
    try { return [int]$Value } catch { return $Default }
}

# ── Persistent Worker Session id ──────────────────────────────────────────────

function Read-SessionId {
    param([string]$Path)
    $v = (Read-TextOrEmpty $Path).Trim()
    if ($v -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') { return $v }
    return $null   # 손상/빈 파일은 새 세션으로 취급한다(영구 정지 방지)
}

# ── Claude 출력 파싱: --output-format json 과 stream-json 을 모두 받는다 ──────

function Get-ClaudeResultObject {
    <#  Worker stdout 에서 **최종 result 객체**를 꺼낸다.

        두 형식을 모두 받는다.
          - `--output-format json`        : 파일 전체가 하나의 JSON
          - `--output-format stream-json` : NDJSON. 마지막 유효 줄이 `type=result` 객체다.
        하나의 파서로 통일해 두어야 출력 형식을 바꿀 때 종료 판정과 모델 판정이 갈라지지 않는다.
        (실측으로 확인: stream-json 의 result 줄에도 subtype/is_error/terminal_reason/modelUsage
         가 그대로 있다.)
        판정 불가는 $null 을 돌려준다 — 성공을 절대 추측하지 않는다. #>
    param([string]$LogPath)
    try {
        $raw = Read-TextOrEmpty $LogPath
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }

        # 1) 파일 전체가 하나의 JSON 인 경우
        try {
            $whole = $raw | ConvertFrom-Json -ErrorAction Stop
            if ($null -ne $whole -and $whole -isnot [array]) { return $whole }
            if ($whole -is [array] -and $whole.Count -gt 0) { return $whole[-1] }
        } catch { }

        # 2) NDJSON — 뒤에서부터 첫 번째로 파싱되는 `type=result` 줄
        $lines = $raw -split "`n"
        for ($i = $lines.Count - 1; $i -ge 0; $i--) {
            $line = $lines[$i].Trim()
            if ($line.Length -lt 2) { continue }
            if (-not $line.StartsWith("{")) { continue }
            try {
                $obj = $line | ConvertFrom-Json -ErrorAction Stop
                if ($null -eq $obj) { continue }
                $names = @($obj.PSObject.Properties.Name)
                if ($names -contains "type" -and [string]$obj.type -eq "result") { return $obj }
                # type 이 없는 단일 객체 형식도 result 로 인정한다(구 형식 호환).
                if (-not ($names -contains "type") -and ($names -contains "subtype")) { return $obj }
            } catch { continue }
        }
        return $null
    } catch { return $null }
}

function Get-ClaudeJsonExitResolution {
    <#  OS exit code 를 못 읽은 경우에만 쓰는 **보조** 증거. `.Handle` 캐시 도입 이후로는
        정상 경로가 아니라 심층 방어다.

        안전 원칙(사용자 지시):
          - OS exit code 가 있으면 그것이 최우선이다(호출부 책임).
          - timeout 에는 절대 적용하지 않는다(호출부 책임).
          - success 는 subtype=success + is_error=false + terminal_reason=completed
            **세 조건이 모두 명시적으로 참**일 때만 인정한다.
          - 명시적 is_error=true 또는 error 계열 subtype 이면 failure(1).
          - 그 밖의 모든 것(부재/손상/불완전/알 수 없는 형태)은 unresolved 로 남긴다. #>
    param([string]$JsonLogPath)

    $unresolved = [pscustomobject]@{
        Resolved = $false; ExitCode = $null; Source = "unresolved"
        Subtype = $null; IsError = $null; TerminalReason = $null
    }

    try {
        $result = Get-ClaudeResultObject $JsonLogPath
        if ($null -eq $result) { return $unresolved }

        $subtype = $null; $isError = $null; $terminalReason = $null
        $names = @($result.PSObject.Properties.Name)
        if ($names -contains "subtype")         { $subtype        = [string]$result.subtype }
        if ($names -contains "is_error")        { $isError        = $result.is_error }
        if ($names -contains "terminal_reason") { $terminalReason = [string]$result.terminal_reason }

        # ★ `$isError -eq $false` 로만 쓰면 안 된다. PowerShell 의 -eq 는 **왼쪽 피연산자의
        #   타입**으로 오른쪽을 변환하므로, is_error 가 문자열 "false" 로 오면 $false 가 "False"
        #   로 변환되어 대소문자 무시 비교에서 **참**이 된다 — 즉 문자열 "false" 가 진짜 boolean
        #   false 로 통과한다(controlled test T01 이 실제로 잡았다). 진짜 boolean 만 인정한다.
        $isErrorIsBool = ($isError -is [bool])
        if ($subtype -eq "success" -and $isErrorIsBool -and (-not $isError) -and $terminalReason -eq "completed") {
            return [pscustomobject]@{
                Resolved = $true; ExitCode = 0; Source = "claude-json-fallback"
                Subtype = $subtype; IsError = $isError; TerminalReason = $terminalReason
            }
        }
        if (($isErrorIsBool -and $isError) -or $subtype -match '^(?i:error|failed|failure)') {
            return [pscustomobject]@{
                Resolved = $true; ExitCode = 1; Source = "claude-json-fallback"
                Subtype = $subtype; IsError = $isError; TerminalReason = $terminalReason
            }
        }
        return [pscustomobject]@{
            Resolved = $false; ExitCode = $null; Source = "unresolved"
            Subtype = $subtype; IsError = $isError; TerminalReason = $terminalReason
        }
    } catch { return $unresolved }
}

function Get-ActualModel {
    <#  응답에서 **실제로 쓰인** 모델을 읽는다. 요청값과 별개로 남겨 두면 나중에
        "정말 그 모델로 돌았나"를 로그만으로 확인할 수 있다. 추측하지 않는다. #>
    param([string]$JsonLogPath)
    try {
        $result = Get-ClaudeResultObject $JsonLogPath
        if ($null -eq $result) { return "unknown" }
        $usage = $result.modelUsage
        if (-not $usage) { return "unknown" }
        $names = @($usage.PSObject.Properties | ForEach-Object { $_.Value.canonicalModel } |
                   Where-Object { $_ } | Sort-Object -Unique)
        if ($names.Count -eq 0) { $names = @($usage.PSObject.Properties.Name) }
        if ($names.Count -eq 0) { return "unknown" }
        return ($names -join ',')
    } catch { return "unknown" }
}

function Get-ClaudeResultStats {
    <#  로그에 남길 만한 수치 몇 개(추측 없음, 없으면 빈 값). 성능 전후 비교의 재료다. #>
    param([string]$JsonLogPath)
    $out = [pscustomobject]@{ NumTurns = 0; CostUsd = 0.0; DurationMs = 0; StopReason = ""; PermissionDenials = 0 }
    try {
        $r = Get-ClaudeResultObject $JsonLogPath
        if ($null -eq $r) { return $out }
        $n = @($r.PSObject.Properties.Name)
        if ($n -contains "num_turns")      { $out.NumTurns = Get-IntOr $r.num_turns 0 }
        if ($n -contains "total_cost_usd") { try { $out.CostUsd = [double]$r.total_cost_usd } catch { } }
        if ($n -contains "duration_ms")    { $out.DurationMs = Get-IntOr $r.duration_ms 0 }
        if ($n -contains "stop_reason")    { $out.StopReason = [string]$r.stop_reason }
        if ($n -contains "permission_denials" -and $r.permission_denials) {
            $out.PermissionDenials = @($r.permission_denials).Count
        }
    } catch { }
    return $out
}

function Get-RateLimitInfoFromLog {
    <#  stream-json 안의 `type=rate_limit_event` 를 뒤에서부터 찾아 **실제 reset 시각**을 얻는다.

        2026-08-13 실측 형태:
          {"type":"rate_limit_event","rate_limit_info":{"status":"allowed_warning",
           "resetsAt":1786744800,"rateLimitType":"seven_day","utilization":0.88,...}}

        `resetsAt` 은 unix epoch(초)다. 이것이 있으면 추측 백오프 대신 그 시각까지 기다린다 —
        구독 한도는 몇 시간 단위라 지수 백오프로는 절대 못 맞춘다(그게 밤중 AUTO_STOP 의 원인이었다). #>
    param([string]$LogPath)
    $out = [pscustomobject]@{ Found = $false; ResetsAt = 0; Type = ""; Utilization = -1.0; Status = "" }
    try {
        $raw = Read-TextOrEmpty $LogPath
        if ([string]::IsNullOrWhiteSpace($raw)) { return $out }
        if ($raw -notmatch 'rate_limit') { return $out }
        $lines = $raw -split "`n"
        for ($i = $lines.Count - 1; $i -ge 0; $i--) {
            $line = $lines[$i]
            if ($line -notmatch 'rate_limit_event') { continue }
            $t = $line.Trim()
            if (-not $t.StartsWith("{")) { continue }
            try {
                $obj = $t | ConvertFrom-Json -ErrorAction Stop
                $info = $obj.rate_limit_info
                if ($null -eq $info) { continue }
                $out.Found = $true
                $names = @($info.PSObject.Properties.Name)
                if ($names -contains "resetsAt")      { $out.ResetsAt    = [long](Get-IntOr $info.resetsAt 0) }
                if ($names -contains "rateLimitType") { $out.Type        = [string]$info.rateLimitType }
                if ($names -contains "status")        { $out.Status      = [string]$info.status }
                if ($names -contains "utilization")   { try { $out.Utilization = [double]$info.utilization } catch { } }
                return $out
            } catch { continue }
        }
    } catch { }
    return $out
}

function Get-RateLimitResetFromText {
    <#  stream 이벤트가 없을 때의 보조 경로 — 에러 문구 안의 epoch/시각 표현을 본다.
        형태를 추측하지 않는다: 확실히 읽히는 것만 인정하고, 아니면 0(모름)을 돌려준다. #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 0 }
    $m = [regex]::Match($Text, '(?i)"?(?:resetsAt|reset_at|resets_at|retry_after_epoch)"?\s*[:=]\s*"?(\d{10})\b')
    if ($m.Success) { return [long]$m.Groups[1].Value }
    # "resets at 3pm" 류의 사람 문구는 타임존이 모호해 신뢰하지 않는다(추측 금지).
    return 0
}

# ── stream-json tail: 증분만 읽어 진행 상황을 만든다 ──────────────────────────

function New-StreamTailState {
    <#  진행 상황 추적 상태. 매번 파일 전체를 다시 읽지 않기 위해 오프셋을 들고 다닌다
        (invocation 하나가 수십 MB NDJSON 을 만들 수 있다). #>
    return [pscustomobject]@{
        Offset      = [long]0
        Events      = 0
        ToolUses    = 0
        LastTool    = ""
        LastEvent   = ""
        Partial     = ""
        Growing     = $false
    }
}

function Update-StreamTailState {
    <#  마지막으로 읽은 오프셋 이후의 바이트만 읽어 이벤트를 센다. 절대 throw 하지 않는다.
        파일이 없거나(아직 안 만들어짐) 읽을 수 없으면 상태를 그대로 둔다. #>
    param($State, [string]$LogPath)
    if ($null -eq $State) { return $State }
    $State.Growing = $false
    try {
        if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) { return $State }
        $fs = [System.IO.File]::Open($LogPath, [System.IO.FileMode]::Open,
                                     [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            if ($fs.Length -le $State.Offset) { return $State }
            $count = [int][Math]::Min(4194304, ($fs.Length - $State.Offset))   # 한 번에 최대 4MB
            [void]$fs.Seek($State.Offset, [System.IO.SeekOrigin]::Begin)
            $buf = New-Object byte[] $count
            $read = $fs.Read($buf, 0, $count)
            if ($read -le 0) { return $State }
            $State.Offset = $State.Offset + $read
            $State.Growing = $true
            $chunk = $State.Partial + [System.Text.Encoding]::UTF8.GetString($buf, 0, $read)
            $lines = $chunk -split "`n"
            # 마지막 조각은 아직 완성되지 않았을 수 있다 — 다음 폴링으로 넘긴다.
            $State.Partial = $lines[$lines.Count - 1]
            for ($i = 0; $i -lt $lines.Count - 1; $i++) {
                $line = $lines[$i].Trim()
                if ($line.Length -lt 2) { continue }
                $State.Events = $State.Events + 1
                # 전체 JSON 파싱은 비싸다(줄당 수십 KB). 필요한 것만 정규식으로 집는다.
                if ($line -match '"type"\s*:\s*"tool_use"') {
                    $State.ToolUses = $State.ToolUses + 1
                    $m = [regex]::Matches($line, '"type"\s*:\s*"tool_use"\s*,\s*"name"\s*:\s*"([^"]+)"')
                    if ($m.Count -eq 0) { $m = [regex]::Matches($line, '"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"') }
                    if ($m.Count -gt 0) { $State.LastTool = $m[$m.Count - 1].Groups[1].Value }
                    $State.LastEvent = "tool_use"
                } elseif ($line -match '"type"\s*:\s*"result"') {
                    $State.LastEvent = "result"
                } elseif ($line -match '"type"\s*:\s*"rate_limit_event"') {
                    $State.LastEvent = "rate_limit"
                } elseif ($line -match '"type"\s*:\s*"assistant"') {
                    $State.LastEvent = "assistant"
                } elseif ($line -match '"type"\s*:\s*"user"') {
                    $State.LastEvent = "tool_result"
                }
            }
        } finally { $fs.Close() }
    } catch { }
    return $State
}

function Format-Duration {
    param([double]$Seconds)
    if ($Seconds -lt 60) { return ("{0:N0}초" -f $Seconds) }
    if ($Seconds -lt 3600) { return ("{0:N1}분" -f ($Seconds / 60)) }
    return ("{0:N1}시간" -f ($Seconds / 3600))
}

function Format-Bytes {
    param([long]$Bytes)
    if ($Bytes -lt 1024) { return "${Bytes}B" }
    if ($Bytes -lt 1048576) { return ("{0:N0}KB" -f ($Bytes / 1024)) }
    return ("{0:N1}MB" -f ($Bytes / 1048576))
}

# ── Claude Worker 실행 ────────────────────────────────────────────────────────

function Stop-ProcessTreeSafe {
    <#  claude.exe 는 자식(node, hook 프로세스 등)을 남긴다. 루트만 죽이면 남은 자식이 계속
        저장소를 건드릴 수 있으므로 트리 전체를 죽인다. taskkill 이 실패하면 루트만이라도. #>
    param([int]$ProcessId, [string]$LogPath)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $global:LASTEXITCODE = 0
        & taskkill.exe /PID $ProcessId /T /F 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0 -and $LogPath) {
            Write-LogLine $LogPath "taskkill /T /F 가 exit=$LASTEXITCODE — 루트 프로세스만 강제 종료로 대체한다(PID=$ProcessId)."
        }
    } catch {
        if ($LogPath) { Write-LogLine $LogPath "taskkill 예외: $($_.Exception.Message)" }
    } finally { $ErrorActionPreference = $prevEap }

    try { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue } catch { }
}

function Invoke-ClaudeWorker {
    <#  Claude Code 를 한 번 띄우고 **정확한 종료 상태**를 돌려준다.

        프롬프트는 반드시 파일 → stdin 리다이렉트로 넘긴다. -ArgumentList 배열 원소로 넘기면
        Windows 커맨드라인 재조립 과정에서 멀티라인/특수문자가 깨져 프롬프트 안의 예시 텍스트가
        claude.exe 자신의 옵션으로 오인된다(2026-08-11 실제 장애: "unknown option '--oneline'").
        같은 이유로 $ArgList 에 **빈 문자열 원소를 넣지 마라** — 재조립 때 누락되어 뒤 인자가
        한 칸씩 밀리고, --session-id/--resume 가 엉뚱한 값에 붙는 것까지 확인된 함정이다.

        ★ 2026-08-13 구조 변경 — **고정 벽시계 timeout 을 활동 기반 idle timeout 으로 바꿨다.**
          실제 운영 로그에서 invocation #2/#3/#4 가 **전부** 240분 상한에 걸려 강제 종료됐고,
          셋 다 그 사이에 커밋을 남기고 있었다. 즉 timeout 이 hang 을 잡은 게 아니라 **일하고
          있는 Worker 를 정확히 4시간마다 잘랐다.** 자를 때마다 (a) 진행 중인 작업이 날아가고
          (b) 워킹트리가 dirty 로 남아 다음 회차가 dirty 대기를 태우고 (c) 다음 회차가 상태를
          다시 읽는 재오리엔테이션 비용을 새로 낸다.
          이제는 stdout(NDJSON)이 자라는 동안은 **살아 있는 것으로 보고 자르지 않는다.**
          진짜로 멈춘 프로세스(출력이 IdleTimeoutMinutes 동안 한 바이트도 안 늘어남)만 죽인다.
          MaxRuntimeMinutes 는 0(무제한)이 기본이며, 주고 싶으면 여전히 절대 상한으로 동작한다. #>
    param(
        [string]$ClaudeExe,
        [string[]]$ArgList,
        [string]$WorkingDirectory,
        [string]$PromptFile,
        [string]$StdOutFile,
        [string]$StdErrFile,
        # double 인 이유: controlled test 가 몇 초 단위로 timeout 경로를 실제로 밟아 볼 수 있게
        # 하기 위함이다. 0 = 무제한.
        [double]$MaxRuntimeMinutes = 0,
        [double]$IdleTimeoutMinutes = 30,
        [double]$ProgressIntervalSeconds = 60,
        [scriptblock]$ProgressCallback,
        [string]$LogPath
    )

    $outcome = [pscustomobject]@{
        ExitCode = 125; Source = "unresolved"; TimedOut = $false; TimeoutKind = ""
        HandleCached = $false; StartedAt = (Get-Date); Subtype = $null
        IsError = $null; TerminalReason = $null; Pid = 0
        DurationMs = 0; FirstOutputMs = -1; Events = 0; ToolUses = 0
        LastTool = ""; IdleSecondsAtEnd = 0; OutBytes = 0
    }

    # 프로세스를 못 띄우는 것(실행 파일 없음/권한/경로)은 Supervisor 를 죽일 이유가 아니다 —
    # 실패로 세고 다음 반복으로 넘겨서, 연속 실패 상한이 정상적으로 AUTO_STOP 을 만들게 한다.
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $proc = $null
    try {
        $proc = Start-Process -FilePath $ClaudeExe -ArgumentList $ArgList -WorkingDirectory $WorkingDirectory `
            -RedirectStandardInput $PromptFile -RedirectStandardOutput $StdOutFile `
            -RedirectStandardError $StdErrFile -PassThru -NoNewWindow
    } catch {
        if ($LogPath) { Write-LogLine $LogPath "Worker 프로세스를 시작하지 못했다(ClaudeExe=$ClaudeExe): $($_.Exception.Message)" }
        $outcome.ExitCode = 127
        $outcome.Source   = "spawn-failed"
        return $outcome
    }
    if ($null -eq $proc) {
        if ($LogPath) { Write-LogLine $LogPath "Start-Process 가 프로세스 객체를 돌려주지 않았다(ClaudeExe=$ClaudeExe)." }
        $outcome.ExitCode = 127
        $outcome.Source   = "spawn-failed"
        return $outcome
    }

    # ★ 5.1 ExitCode=$null 의 **근본 원인 수정**: 시작 직후 핸들을 한 번 만져 캐시한다.
    #   이걸 안 하면 5.1 에서는 정상 종료한 프로세스의 exit code 를 영영 못 읽는다(실측).
    try { $null = $proc.Handle; $outcome.HandleCached = $true } catch { $outcome.HandleCached = $false }
    try { $outcome.Pid = $proc.Id } catch { }

    $tail = New-StreamTailState
    $pollMs = 2000
    if ($ProgressIntervalSeconds -gt 0 -and ($ProgressIntervalSeconds * 1000) -lt $pollMs) {
        $pollMs = [int][Math]::Max(200, $ProgressIntervalSeconds * 1000)
    }
    $lastActivity = [DateTime]::UtcNow
    $lastProgress = [DateTime]::UtcNow
    $exited = $false
    $killKind = ""

    while ($true) {
        # Wait-Process -PassThru 는 기다림이 실패해도 객체를 돌려주므로 timeout 판정에 쓸 수 없다
        # (2026-08-12 실제로 강제 종료 분기 전체가 죽은 코드였다). WaitForExit(ms) 는 bool 을 준다.
        $exited = $proc.WaitForExit($pollMs)
        if ($exited) { break }

        $tail = Update-StreamTailState $tail $StdOutFile
        if ($tail.Growing) {
            $lastActivity = [DateTime]::UtcNow
            if ($outcome.FirstOutputMs -lt 0) { $outcome.FirstOutputMs = [int]$sw.ElapsedMilliseconds }
        }

        $elapsed = $sw.Elapsed.TotalSeconds
        $idle = ([DateTime]::UtcNow - $lastActivity).TotalSeconds

        if ($MaxRuntimeMinutes -gt 0 -and $elapsed -ge ($MaxRuntimeMinutes * 60)) {
            $killKind = "hard"
            break
        }
        if ($IdleTimeoutMinutes -gt 0 -and $idle -ge ($IdleTimeoutMinutes * 60)) {
            $killKind = "idle"
            break
        }

        if ($ProgressIntervalSeconds -gt 0 -and
            ([DateTime]::UtcNow - $lastProgress).TotalSeconds -ge $ProgressIntervalSeconds) {
            $lastProgress = [DateTime]::UtcNow
            if ($ProgressCallback) {
                $snapshot = [pscustomobject]@{
                    ElapsedSeconds = $elapsed
                    IdleSeconds    = $idle
                    Events         = $tail.Events
                    ToolUses       = $tail.ToolUses
                    LastTool       = $tail.LastTool
                    LastEvent      = $tail.LastEvent
                    OutBytes       = $tail.Offset
                    Pid            = $outcome.Pid
                }
                try { & $ProgressCallback $snapshot } catch { }
            }
        }
    }

    if (-not $exited) {
        $limit = if ($killKind -eq "hard") { "${MaxRuntimeMinutes}분 절대 상한" } else { "${IdleTimeoutMinutes}분 동안 출력이 전혀 늘지 않음" }
        if ($LogPath) {
            Write-LogLine $LogPath ("invocation 이 멈춰 프로세스 트리를 강제 종료한다($limit) — PID=$($outcome.Pid) " +
                "elapsed=$(Format-Duration $sw.Elapsed.TotalSeconds) events=$($tail.Events) tools=$($tail.ToolUses) lastTool=$($tail.LastTool)")
        }
        Stop-ProcessTreeSafe -ProcessId $outcome.Pid -LogPath $LogPath
        try { [void]$proc.WaitForExit(10000) } catch { }
        $sw.Stop()
        $tail = Update-StreamTailState $tail $StdOutFile
        $outcome.ExitCode   = 124          # 관례적 timeout 코드
        $outcome.Source     = "timeout"
        $outcome.TimedOut   = $true
        $outcome.TimeoutKind = $killKind
        $outcome.DurationMs = [int]$sw.ElapsedMilliseconds
        $outcome.Events     = $tail.Events
        $outcome.ToolUses   = $tail.ToolUses
        $outcome.LastTool   = $tail.LastTool
        $outcome.OutBytes   = $tail.Offset
        $outcome.IdleSecondsAtEnd = [int]([DateTime]::UtcNow - $lastActivity).TotalSeconds
        return $outcome                   # timeout 에는 JSON fallback 을 절대 적용하지 않는다
    }

    # 리다이렉션 마무리를 한 번 더 기다린 뒤 상태를 갱신한다.
    try { [void]$proc.WaitForExit() } catch { }
    try { $proc.Refresh() } catch { }
    $sw.Stop()
    $tail = Update-StreamTailState $tail $StdOutFile
    $outcome.DurationMs = [int]$sw.ElapsedMilliseconds
    $outcome.Events     = $tail.Events
    $outcome.ToolUses   = $tail.ToolUses
    $outcome.LastTool   = $tail.LastTool
    $outcome.OutBytes   = $tail.Offset
    if ($outcome.FirstOutputMs -lt 0 -and $tail.Offset -gt 0) { $outcome.FirstOutputMs = [int]$sw.ElapsedMilliseconds }

    $exitCode = $null
    try { $exitCode = $proc.ExitCode } catch { $exitCode = $null }

    if ($null -ne $exitCode) {
        $outcome.ExitCode = [int]$exitCode
        $outcome.Source   = "os"
        return $outcome
    }

    $resolution = Get-ClaudeJsonExitResolution $StdOutFile
    $outcome.Subtype        = $resolution.Subtype
    $outcome.IsError        = $resolution.IsError
    $outcome.TerminalReason = $resolution.TerminalReason

    if ($resolution.Resolved) {
        $outcome.ExitCode = [int]$resolution.ExitCode
        $outcome.Source   = [string]$resolution.Source
        if ($LogPath) {
            Write-LogLine $LogPath ("OS exit code 를 읽지 못해 Claude JSON 으로 복구: exit=$($outcome.ExitCode) " +
                "subtype=$($resolution.Subtype) isError=$($resolution.IsError) terminalReason=$($resolution.TerminalReason) " +
                "handleCached=$($outcome.HandleCached)")
        }
    } else {
        # 성공을 추측하지 않는다.
        $outcome.ExitCode = 125
        $outcome.Source   = "unresolved"
        if ($LogPath) {
            Write-LogLine $LogPath ("경고: OS exit code 와 Claude JSON 모두 종료 상태를 확정하지 못함 — exit=125 로 실패 처리. " +
                "subtype=$($resolution.Subtype) isError=$($resolution.IsError) terminalReason=$($resolution.TerminalReason) " +
                "handleCached=$($outcome.HandleCached)")
        }
    }
    return $outcome
}

# ── 실패 분류 ─────────────────────────────────────────────────────────────────

function Test-IsResumeFailure {
    <#  저장된 session_id 가 더 이상 유효하지 않을 때의 시그니처. 2026-08-12 실제 CLI 호출로
        확인: exit != 0, stdout 비어 있음, stderr == "No conversation found with session ID: <id>".
        문구가 바뀔 가능성에 대비해 조금 더 넓게 잡되, 세션 관련 표현만 인정한다. #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    return ($Text -match '(?i)No conversation found with session ID' -or
            $Text -match '(?i)(session (id )?(not found|is invalid|does not exist))' -or
            $Text -match '(?i)could not (find|resume) (the )?(conversation|session)')
}

function Test-IsRateLimitFailure {
    <#  예전 판정은 stdout JSON 전체에 대해 `429|503|529` 를 찾았다 — 비용/토큰 수치, 파일 경로,
        본문 어디에 그 숫자가 있어도 rate-limit 으로 오인했다. rate-limit 은 실패 카운터를
        올리지 않으므로, 오인은 **진짜 실패를 영원히 숨기고 백오프만 반복하는** 경로였다.
        이제 상태 코드는 앞뒤 문맥이 있을 때만 인정한다.

        ★ stream-json 으로 바꾸면서 생긴 **새 오탐 경로**(2026-08-13 실측으로 발견):
          정상 실행 스트림에도 `{"type":"rate_limit_event","rate_limit_info":{"status":
          "allowed_warning",...,"rateLimitType":"seven_day"}}` 가 섞여 들어온다. 이 JSON **키
          이름들**이 "rate limit" 패턴에 그대로 걸리므로, 전혀 무관한 이유로 실패한 invocation 이
          rate-limit 으로 오분류될 수 있다. rate-limit 은 실패 카운터를 올리지 않으므로 그 오분류는
          **진짜 실패를 영원히 숨기고 백오프만 반복하는** 경로다(예전 판이 정확히 그 버그였다).
          그래서 판정 전에 키 이름을 먼저 지운다. 실제 차단 신호는 status 값(rejected/blocked)
          이나 사람이 읽는 에러 문구다. #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    # 스트림 이벤트의 **키 이름**은 판정 근거가 아니다 — 지우고 본다.
    $t = $Text -replace '(?i)"?rate_limit_(event|info)"?', '' `
               -replace '(?i)"?rateLimitType"?\s*:\s*"[^"]*"', '' `
               -replace '(?i)"?rateLimitType"?', ''
    return ($t -match '(?i)rate[ _-]?limit' -or
            $t -match '(?i)"status"\s*:\s*"(rejected|blocked|exceeded)"' -or
            $t -match '(?i)overloaded' -or
            $t -match '(?i)too many requests' -or
            $t -match '(?i)usage limit' -or
            $t -match '(?i)service[ _-]?unavailable' -or
            $t -match '(?i)(status|http|code)\D{0,12}\b(429|503|529)\b' -or
            $t -match '(?i)\b(429|503|529)\b\s*(too many|service|overload)')
}

function Test-IsOverloadFailure {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    return ($Text -match '(?i)overloaded' -or $Text -match '(?i)\b529\b' -or
            $Text -match '(?i)api[ _-]?error.*\b(500|502|503)\b')
}

function Test-IsNetworkFailure {
    <#  순간적 네트워크 장애는 "이 작업이 틀렸다"는 신호가 아니다. 짧게 기다렸다 그대로 재시도한다. #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    return ($Text -match '(?i)\b(ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|EPIPE|ENETUNREACH)\b' -or
            $Text -match '(?i)(socket hang up|network (error|timeout)|fetch failed|connect(ion)? (timed out|reset|refused))' -or
            $Text -match '(?i)getaddrinfo')
}

function Test-IsAuthFailure {
    <#  인증 문제는 기다려도 저절로 낫지 않는다 — 빠르게 수렴시키고 사람이 볼 수 있게 크게 남긴다. #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    return ($Text -match '(?i)(invalid|expired|missing).{0,20}(api key|token|credential)' -or
            $Text -match '(?i)(authentication|authorization) (failed|error|required)' -or
            $Text -match '(?i)\b401\b.{0,30}(unauthorized|invalid)' -or
            $Text -match '(?i)please run .{0,10}claude (auth|login)' -or
            $Text -match '(?i)not logged in')
}

function Get-FailureSignature {
    <#  "같은 실패가 결정적으로 반복되는가"를 판정하기 위한 지문.
        숫자·경로·UUID·타임스탬프를 지워서 같은 원인이 같은 지문을 갖게 한다. #>
    param([string]$Class, [string]$Text)
    $t = [string]$Text
    if ($t.Length -gt 4000) { $t = $t.Substring(0, 4000) }
    $t = $t -replace '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '<uuid>'
    $t = $t -replace '\d{4}-\d{2}-\d{2}T[\d:.+\-]+', '<ts>'
    $t = $t -replace '[A-Za-z]:\\[^\s"]+', '<path>'
    $t = $t -replace '\d+', '<n>'
    $t = ($t -replace '\s+', ' ').Trim()
    if ($t.Length -gt 200) { $t = $t.Substring(0, 200) }
    return "$Class|$t"
}

function Get-InvocationFailureClass {
    <#  invocation 하나의 결과를 **유형**으로 분류한다. 예전 코드는 "exit!=0 이면 실패 1회"에
        가까웠고, 그래서 밤중에 순간적 네트워크 장애 3번이면 AUTO_STOP 이었다.

        분류 규칙(위에서부터 먼저 맞는 것):
          ok             종료 코드 0
          progress       종료 코드 != 0 인데 이 invocation 이 커밋을 남겼다(=일은 됐다)
          resume-failure 저장된 session 을 못 이어받았다 — 세션 인프라 문제, 작업 실패 아님
          auth           인증/자격증명 문제 — 기다려도 안 낫는다
          rate-limit     구독/API 사용량 한도 — 실제 reset 시각까지 기다린다
          overload       모델 과부하(529 등) — 짧게 기다렸다 재시도
          network        일시적 네트워크 — 아주 짧게 기다렸다 재시도
          spawn-failed   프로세스를 못 띄웠다 — 설정 문제
          idle-timeout   출력이 완전히 멈춤 = 진짜 hang
          hard-timeout   절대 상한에 걸림
          unresolved     종료 상태를 확정하지 못함
          generic        나머지

        CountsAsFailure 는 **AUTO_STOP 카운터에 들어가는가**만 뜻한다. false 인 유형도 각자
        별도 카운터로 상한이 있어(호출부) 무한 루프가 되지 않는다. #>
    param(
        [int]$ExitCode,
        [bool]$Progressed,
        [bool]$IsNewSession,
        [string]$TimeoutKind,
        [string]$Source,
        [string]$StdErrText,
        [string]$StdOutText
    )

    $mk = {
        param($cls, $detail, $counts, $infra)
        [pscustomobject]@{ Class = $cls; Detail = $detail; CountsAsFailure = $counts; IsInfra = $infra }
    }

    if ($ExitCode -eq 0) { return (& $mk "ok" "" $false $false) }

    $combined = ([string]$StdErrText) + "`n" + ([string]$StdOutText)

    if ($Source -eq "spawn-failed") { return (& $mk "spawn-failed" "Worker 프로세스를 시작하지 못함" $true $false) }

    if ((-not $IsNewSession) -and (Test-IsResumeFailure $combined)) {
        return (& $mk "resume-failure" "저장된 session 을 이어받을 수 없음" $false $true)
    }
    if (Test-IsAuthFailure $combined) {
        return (& $mk "auth" "인증/자격증명 문제 — 사람이 봐야 한다" $true $false)
    }
    if (Test-IsRateLimitFailure $combined) {
        if (Test-IsOverloadFailure $combined) { return (& $mk "overload" "모델 과부하" $false $true) }
        return (& $mk "rate-limit" "사용량 한도" $false $true)
    }
    if (Test-IsOverloadFailure $combined) { return (& $mk "overload" "모델 과부하" $false $true) }
    if (Test-IsNetworkFailure $combined)  { return (& $mk "network" "일시적 네트워크 장애" $false $true) }

    if ($Progressed) {
        # ★ AUTO_STOP 의 의미는 "종료 코드가 0이 아니다"가 아니라 **"진척이 없다"** 여야 한다.
        return (& $mk "progress" "exit!=0 이지만 커밋을 남겼다" $false $false)
    }

    if ($TimeoutKind -eq "idle") { return (& $mk "idle-timeout" "출력이 완전히 멈춤(hang)" $true $false) }
    if ($TimeoutKind -eq "hard") { return (& $mk "hard-timeout" "절대 실행 상한 도달" $true $false) }
    if ($Source -eq "unresolved") { return (& $mk "unresolved" "종료 상태를 확정하지 못함" $true $false) }
    return (& $mk "generic" "분류되지 않은 실패" $true $false)
}

function Get-BackoffSeconds {
    param([int]$Hits, [int]$BaseSeconds, [int]$MaxSeconds)
    if ($Hits -lt 1) { $Hits = 1 }
    if ($Hits -gt 20) { $Hits = 20 }   # Pow 폭주 방지
    $v = [double]$BaseSeconds * [Math]::Pow(2, $Hits - 1)
    if ($v -gt $MaxSeconds) { $v = [double]$MaxSeconds }
    return [int][Math]::Round($v)
}

function Start-InterruptibleSleep {
    <#  긴 백오프(사용량 한도는 몇 시간이다) 중에도 사용자의 STOP 을 놓치지 않는다.
        예전엔 통짜 Start-Sleep 이라 STOP 파일을 만들어도 다음 확인까지 최대 30분을 기다렸다.
        돌려주는 값: $true = 정상 대기 완료, $false = 중단 요청 감지. #>
    param([int]$Seconds, [string]$StopFile, [string]$LogPath, [string]$Reason = "")
    if ($Seconds -le 0) { return $true }
    $deadline = (Get-Date).AddSeconds($Seconds)
    $announceEvery = 300
    $nextAnnounce = (Get-Date).AddSeconds($announceEvery)
    while ((Get-Date) -lt $deadline) {
        if ($StopFile -and (Test-Path -LiteralPath $StopFile)) {
            if ($LogPath) { Write-LogLine $LogPath "대기 중 STOP 파일을 발견해 즉시 중단한다." }
            return $false
        }
        $remain = ($deadline - (Get-Date)).TotalSeconds
        if ($remain -le 0) { break }
        Start-Sleep -Seconds ([int][Math]::Min(5, [Math]::Max(1, $remain)))
        if ((Get-Date) -ge $nextAnnounce) {
            $nextAnnounce = (Get-Date).AddSeconds($announceEvery)
            Write-ConsoleLine ("      … 대기 중 ($Reason) — 남은 시간 {0}" -f (Format-Duration ($deadline - (Get-Date)).TotalSeconds))
        }
    }
    return $true
}

# ── 단일 Writer 잠금 ──────────────────────────────────────────────────────────

function Open-ExclusiveLock {
    <#  잠금 **파일 핸들** 자체를 배타 열기로 잡고 프로세스가 사는 동안 들고 있는다.
        - 두 번째 인스턴스는 열기 자체가 실패하므로 확인/기록 사이의 경쟁 구간이 없다.
        - 크래시/강제 종료 시 OS 가 핸들을 회수하므로 stale lock 이 다음 시작을 막지 않는다.
        - FileShare::Read 로 열어 두어 두 번째 인스턴스가 보유자 PID 를 읽어 안내할 수 있다.

        예전 코드는 `catch [IOException]` 만 잡았다 — 권한 문제(UnauthorizedAccessException)는
        IOException 이 아니어서 잡히지 않고 스크립트가 그대로 죽었다. 여기서는 모든 예외를
        "잠금 실패"로 다루되 **원인 문자열을 그대로 돌려준다**(조용한 no-op 금지). #>
    param([string]$LockFile)

    $result = [pscustomobject]@{ Acquired = $false; Stream = $null; Holder = ""; Reason = "" }
    try {
        $dir = Split-Path -Parent $LockFile
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        $stream = [System.IO.File]::Open(
            $LockFile, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
        $writer = New-Object System.IO.StreamWriter($stream)
        $writer.WriteLine($PID)
        $writer.Flush()          # 스트림은 닫지 않는다 — 닫는 순간 잠금이 풀린다
        $result.Acquired = $true
        $result.Stream = $stream
    } catch {
        $result.Reason = $_.Exception.GetType().Name + ": " + $_.Exception.Message
        try { $result.Holder = (Read-TextOrEmpty $LockFile).Trim() } catch { }
        if ([string]::IsNullOrWhiteSpace($result.Holder)) { $result.Holder = "(알 수 없음)" }
    }
    return $result
}

function Close-ExclusiveLock {
    <#  잠금을 놓고 파일을 지운다. 지우기가 실패해도(다른 프로세스가 이미 다시 잡았다면 Windows 가
        막는다) 무시한다 — 남은 lock **파일**은 다음 시작을 막지 않는다. #>
    param($Lock, [string]$LockFile)
    if ($Lock -and $Lock.Stream) { try { $Lock.Stream.Close() } catch { } }
    try { Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue } catch { }
}

# ── marker 격리(삭제 대신 증거 보존) ──────────────────────────────────────────

function Move-MarkerToQuarantine {
    <#  기계 Gate 가 거부한 marker 는 **지우지 않고 옮긴다**. 왜 거부됐는지 나중에 확인할 수
        있어야 하고, 지우기만 하면 같은 실수가 반복돼도 흔적이 안 남는다. #>
    param([string]$MarkerPath, [string]$QuarantineDir, [string]$Reasons)
    try {
        if (-not (Test-Path -LiteralPath $MarkerPath)) { return "" }
        if (-not (Test-Path -LiteralPath $QuarantineDir)) {
            New-Item -ItemType Directory -Force -Path $QuarantineDir | Out-Null
        }
        $name = (Split-Path -Leaf $MarkerPath)
        $dest = Join-Path $QuarantineDir ("rejected_{0}_{1}.txt" -f $name, (Get-Date -Format "yyyyMMdd-HHmmss"))
        $body = "rejected_at=$(Get-Date -Format o)" + [Environment]::NewLine +
                "reasons:" + [Environment]::NewLine + $Reasons + [Environment]::NewLine +
                "--- original marker content ---" + [Environment]::NewLine + (Read-TextOrEmpty $MarkerPath)
        [void](Write-TextFile $dest $body)
        Remove-Item -LiteralPath $MarkerPath -Force -ErrorAction SilentlyContinue
        return $dest
    } catch { return "" }
}

# ── 호출한 셸의 환경을 더럽히지 않기 ──────────────────────────────────────────
# Supervisor 는 자식(claude.exe)에게 표시를 물려주려고 **자기 프로세스 환경**에 변수를 넣는다
# (5.1 에는 Start-Process -Environment 가 없다). 문제는 그 값이 **호출한 셸에도 그대로 남는다**는
# 것이다: 사용자가 같은 PowerShell 창에서 Ctrl+C 로 Supervisor 를 멈춘 뒤 대화형 Claude 세션을
# 시작하면, 그 세션이 supervised worker 로 오인되어 Stop hook 이 사람의 작업을 막는다.
# 2026-08-12 검수 세션이 실제로 그 상태였다(stop_guard.log 에 사람 세션 block 기록). 끝날 때
# 원래 값으로 정확히 되돌린다 — 원래 없었으면 없는 상태로.
function Save-EnvSnapshot {
    param([string[]]$Names)
    $snap = @{}
    foreach ($n in $Names) { $snap[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
    return $snap
}

function Restore-EnvSnapshot {
    param($Snapshot)
    if ($null -eq $Snapshot) { return }
    foreach ($n in @($Snapshot.Keys)) {
        try {
            $v = $Snapshot[$n]
            if ($null -eq $v) { Remove-Item -LiteralPath ("Env:" + $n) -Force -ErrorAction SilentlyContinue }
            else { Set-Item -LiteralPath ("Env:" + $n) -Value $v }
        } catch { }
    }
}

function Test-RunnerPrerequisites {
    <#  시작하자마자 확인할 수 있는 전제조건. 실패하면 3회 헛돌다 AUTO_STOP 하는 대신
        **왜 못 도는지** 를 크게 알리고 즉시 끝낸다(조용한 no-op 금지). #>
    param([string]$ProjectDir, [string]$ClaudeExe)
    $problems = New-Object System.Collections.Generic.List[string]

    if (-not (Test-Path -LiteralPath $ProjectDir -PathType Container)) {
        $problems.Add("프로젝트 디렉터리가 없다: $ProjectDir")
    } else {
        $r = Invoke-Git -RepoDir $ProjectDir "rev-parse" "--is-inside-work-tree"
        if (-not $r.Ok) { $problems.Add("git 저장소가 아니거나 git 을 실행할 수 없다: $ProjectDir ($($r.StdErr))") }
    }
    if (-not (Test-Path -LiteralPath $ClaudeExe -PathType Leaf)) {
        $problems.Add("Claude 실행 파일을 찾을 수 없다: $ClaudeExe  (-ClaudeExe 로 경로를 지정하세요)")
    }
    return @($problems.ToArray())
}

function Get-KeyValueFromText {
    <#  marker/문서 안의 `key=value` 또는 `key: value` 한 줄을 읽는다. 없으면 "".
        구분자를 둘 다 받는 이유: runtime marker 는 `key=value`(기계용)로, HANDOFF 의 PA-RC
        블록은 `key: value`(사람이 읽는 문서용)로 쓰는 것이 자연스러운데, 파서를 하나만 두면
        둘 중 하나가 조용히 안 읽힌다(controlled test T25 가 실제로 그 상태를 잡았다). #>
    param([string]$Text, [string]$Key)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    $pattern = '(?im)^\s*(?:-\s*)?' + [regex]::Escape($Key) + '\s*[:=]\s*(.+?)\s*$'
    $m = [regex]::Match($Text, $pattern)
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ""
}

# ── 다음 invocation 힌트(동적 model/effort) ───────────────────────────────────

$script:AllowedEfforts = @("low", "medium", "high", "xhigh", "max")
$script:AllowedModels  = @("haiku", "sonnet", "opus", "fable")

function Read-NextInvocationHint {
    <#  Worker 가 "다음 회차는 이 난이도로 오라"고 남긴 힌트를 읽는다.

        왜 Worker 가 정하는가: 다음에 무엇을 할지(단순 소비처 수정인지, RBAC/transaction 재설계
        인지)를 가장 정확히 아는 것은 방금 그 작업을 계획한 Worker 자신이다. Supervisor 는
        시작 조건(cold/gate 거부/연속 실패)만 안다. 둘을 합쳐서 고른다.

        신뢰하지 않고 **검증**한다: 허용 목록 밖의 값은 무시하고 사유를 로그에 남긴다.
        읽은 뒤 파일을 소비(삭제)하므로 한 번 남긴 힌트가 영원히 붙어 있지 않는다. #>
    param([string]$Path, [string]$LogPath)
    $out = [pscustomobject]@{ Found = $false; Effort = ""; Model = ""; Reason = "" }
    $raw = Read-TextOrEmpty $Path
    if ([string]::IsNullOrWhiteSpace($raw)) { return $out }
    try {
        $obj = $null
        try { $obj = $raw | ConvertFrom-Json -ErrorAction Stop } catch { $obj = $null }
        $effort = ""; $model = ""; $reason = ""
        if ($null -ne $obj) {
            $n = @($obj.PSObject.Properties.Name)
            if ($n -contains "effort") { $effort = ([string]$obj.effort).Trim().ToLowerInvariant() }
            if ($n -contains "model")  { $model  = ([string]$obj.model).Trim().ToLowerInvariant() }
            if ($n -contains "reason") { $reason = [string]$obj.reason }
        } else {
            # JSON 이 아니면 key=value 로도 받아 준다(Worker 가 쉽게 쓰게).
            $effort = (Get-KeyValueFromText $raw "effort").ToLowerInvariant()
            $model  = (Get-KeyValueFromText $raw "model").ToLowerInvariant()
            $reason = Get-KeyValueFromText $raw "reason"
        }
        if ($effort -and ($script:AllowedEfforts -notcontains $effort)) {
            if ($LogPath) { Write-LogLine $LogPath "다음 invocation 힌트의 effort='$effort' 는 허용 목록 밖이라 무시한다." }
            $effort = ""
        }
        if ($model -and ($script:AllowedModels -notcontains $model)) {
            if ($LogPath) { Write-LogLine $LogPath "다음 invocation 힌트의 model='$model' 은 허용 목록 밖이라 무시한다." }
            $model = ""
        }
        if ($effort -or $model) {
            $out.Found = $true; $out.Effort = $effort; $out.Model = $model
            if ($reason.Length -gt 200) { $reason = $reason.Substring(0, 200) }
            $out.Reason = $reason
        }
    } catch { }
    finally { try { Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue } catch { } }
    return $out
}

# ── 타이밍 계측 ───────────────────────────────────────────────────────────────

function Write-TimingRecord {
    <#  invocation 하나의 시간 분해를 한 줄 JSON 으로 남긴다. "PowerShell 이 느리다"를 추측이
        아니라 수치로 판정하기 위한 것이다(사용자 지시 §12). #>
    param([string]$Path, [System.Collections.IDictionary]$Fields)
    try {
        $obj = [pscustomobject]$Fields
        $line = ($obj | ConvertTo-Json -Depth 4 -Compress)
        $dir = Split-Path -Parent $Path
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        [System.IO.File]::AppendAllText($Path, $line + [Environment]::NewLine, $script:Utf8NoBom)
        return $true
    } catch { return $false }
}

# ── TEST SERVER 접근 상태(무인 실행 가능 여부를 시작 시 한 번 확인) ───────────

function Get-TestServerTargetFromRepo {
    <#  승인된 TEST SERVER 접속 대상(`user@host`)을 **현재 저장소 설정에서** 찾는다.

        CLAUDE.md §9 는 "특정 마지막 octet 을 과거 기억으로 하드코딩하지 마라. 실제 대상은
        현재 저장소 설정·배포 스크립트·runtime configuration 에서 확인하라"고 못박고 있다.
        그래서 Supervisor 는 값을 들고 있지 않고 매 실행마다 저장소에서 읽는다.
        승인 대역(10.100.64.X) 밖의 주소는 절대 돌려주지 않는다 — 권한 확장 방지. #>
    param([string]$ProjectDir)
    $candidates = @(
        "var\runner\test_server.txt",          # 사용자가 직접 지정한 값이 있으면 최우선
        "docs\MAINTENANCE_PLAYBOOK.md",
        "docs\DEPLOY_NOW.md",
        "runner\README.md",
        "docs\ARCHITECTURE.md"
    )
    foreach ($rel in $candidates) {
        $abs = Join-Path $ProjectDir $rel
        $text = Read-TextOrEmpty $abs
        if ([string]::IsNullOrWhiteSpace($text)) { continue }
        $m = [regex]::Match($text, '([A-Za-z0-9._-]+)@(10\.100\.64\.\d{1,3})\b')
        if ($m.Success) { return ($m.Groups[1].Value + "@" + $m.Groups[2].Value) }
    }
    return ""
}

function Test-TestServerAccess {
    <#  승인된 TEST SERVER(CLAUDE.md §9)에 **비대화형으로** 닿는지, sudo 가 비밀번호 없이
        되는지를 시작 시 한 번만 확인해 RUN CONTEXT 에 넣는다.

        왜 Supervisor 가 하는가: 매 invocation 마다 Worker 가 같은 것을 다시 알아내는 것은
        낭비이고, 못 닿을 때 Worker 가 "사람이 해야 한다"고 잘못 결론 내리는 것을 막기 위해
        **사실**을 미리 준다. 자격증명은 절대 이 함수에 들어오지 않는다 — BatchMode 로 키 인증만
        시험하고, sudo 는 `-n`(비밀번호 없이 되는가)만 본다. #>
    param([string]$Target, [int]$TimeoutSeconds = 12)
    $out = [pscustomobject]@{ Probed = $false; SshOk = $false; SudoNoPassword = $false; Detail = "" }
    if ([string]::IsNullOrWhiteSpace($Target)) { return $out }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out.Probed = $true
        $global:LASTEXITCODE = 0
        $sshArgs = @("-o", "BatchMode=yes", "-o", ("ConnectTimeout=" + [int]$TimeoutSeconds),
                     "-o", "StrictHostKeyChecking=accept-new", $Target,
                     "echo SSH_OK; sudo -n true >/dev/null 2>&1 && echo SUDO_NOPASSWD || echo SUDO_NEEDS_PASSWORD")
        $text = (& ssh @sshArgs 2>&1 | Out-String)
        $out.SshOk = ($text -match 'SSH_OK')
        $out.SudoNoPassword = ($text -match 'SUDO_NOPASSWD')
        $out.Detail = ($text -replace '\s+', ' ').Trim()
        if ($out.Detail.Length -gt 200) { $out.Detail = $out.Detail.Substring(0, 200) }
    } catch {
        $out.Detail = "probe-exception: " + $_.Exception.Message
    } finally { $ErrorActionPreference = $prevEap }
    return $out
}

# ── active state / resume context 캐시 ────────────────────────────────────────
# 사용자 지시 §3/§4: 큰 역사 문서를 **매 invocation 마다** 다시 읽는 구조를 없앤다.
# 여기서 만드는 것은 Source of Truth 가 **아니다** — 원본 문서에서 언제든 재생성 가능한 cache 다.
# 원본은 그대로 두고(역사 증거 보존), "항상 읽지는 않는다"로 해결한다.

function Get-UnresolvedBacklogIndex {
    <#  BACKLOG.md 에서 **아직 안 끝난 항목**만 뽑는다.

        이 저장소의 BACKLOG 는 표 기반이고 상태 어휘가 문서 머리에 정의돼 있다:
          발견 → 작업예정 → 작업중 → 구현완료 → 검증대기 → 배포완료 → 실환경검증완료
        "실환경검증완료"만 완료다. 취소선(~~)·✅ 로 정리된 행도 완료로 본다.

        완벽한 파서를 목표로 하지 않는다 — 목적은 "다음에 뭘 고를지 후보를 좁히는 index"이고,
        Worker 는 필요하면 원본의 해당 절만 읽는다. 그래서 애매하면 **미해결 쪽으로** 남긴다. #>
    param([string]$Path, [int]$Max = 400)
    $items = New-Object System.Collections.Generic.List[object]
    $raw = Read-TextOrEmpty $Path
    if ([string]::IsNullOrWhiteSpace($raw)) { return @($items.ToArray()) }

    $lines = $raw -split "`n"
    foreach ($line in $lines) {
        if ($line.Length -lt 8) { continue }
        if ($line[0] -ne '|') { continue }                       # 표 행만 본다
        if ($line -match '^\|\s*-{2,}') { continue }             # 구분선
        $m = [regex]::Match($line, '`([A-Z][A-Z0-9]*-\d+[A-Za-z]?)`')
        if (-not $m.Success) { continue }
        $id = $m.Groups[1].Value
        $done = ($line -match '실환경검증완료' -or $line -match '✅' -or $line -match '~~' -or
                 $line -match '철회' -or $line -match '해당없음')
        if ($done) { continue }
        $cells = @($line.Trim('|') -split '\|')
        $title = ""
        foreach ($c in $cells) {
            $t = $c.Trim()
            if ($t -eq "" -or $t -eq $id -or $t -match '^`' -and $t -match '`$' -and $t.Length -lt 16) { continue }
            if ($t.Length -gt $title.Length) { $title = $t }
        }
        $title = ($title -replace '\*\*', '' -replace '`', '').Trim()
        if ($title.Length -gt 120) { $title = $title.Substring(0, 120) }
        $sev = ""
        if ($line -match '(?i)critical') { $sev = "Critical" }
        elseif ($line -match '(?i)\bhigh\b|높음') { $sev = "High" }
        $items.Add([pscustomobject]@{ id = $id; severity = $sev; title = $title })
        if ($items.Count -ge $Max) { break }
    }
    # 같은 ID 가 여러 절에 나올 수 있다 — 첫 등장만 남긴다.
    $seen = @{}
    $uniq = New-Object System.Collections.Generic.List[object]
    foreach ($i in $items) {
        if ($seen.ContainsKey($i.id)) { continue }
        $seen[$i.id] = $true
        $uniq.Add($i)
    }
    return @($uniq.ToArray())
}

function New-RunnerContextCache {
    <#  원본 문서를 읽지 않고도 "지금 어디인가"를 알 수 있는 compact cache 를 만든다.
        결과: <OutDir>\active_state.json · unresolved_index.json · resume_context.txt
        전부 var/ 아래(gitignore)이고 원본에서 재생성 가능하다. #>
    param(
        [string]$ProjectDir,
        [string]$OutDir,
        [System.Collections.IDictionary]$Extra
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $docs = @("docs/WORK_STATE.md", "docs/BACKLOG.md", "docs/QA_COVERAGE.md",
              "docs/DECISIONS.md", "docs/PROGRESS_STATUS.md", "docs/WORK_PLAN_INDEX.md")
    $docInfo = New-Object System.Collections.Generic.List[object]
    foreach ($d in $docs) {
        $abs = Join-Path $ProjectDir ($d -replace '/', '\')
        $lines = 0; $mtime = ""
        try {
            if (Test-Path -LiteralPath $abs -PathType Leaf) {
                $fi = Get-Item -LiteralPath $abs
                $mtime = $fi.LastWriteTime.ToString("s")
                $lines = @([System.IO.File]::ReadAllLines($abs)).Count
            }
        } catch { }
        $docInfo.Add([pscustomobject]@{ path = $d; lines = $lines; modified = $mtime })
    }

    $unresolved = @(Get-UnresolvedBacklogIndex (Join-Path $ProjectDir "docs\BACKLOG.md"))
    $head   = Get-GitHeadSha -RepoDir $ProjectDir
    $branch = Get-GitBranch -RepoDir $ProjectDir
    $dirty  = @(Get-GitStatusEntries -RepoDir $ProjectDir | ForEach-Object { "$($_.Status) $($_.Path)" })

    $state = [ordered]@{
        generatedAt   = (Get-Date -Format o)
        head          = $head
        branch        = $branch
        dirtyCount    = $dirty.Count
        dirty         = @($dirty | Select-Object -First 40)
        recentCommits = @(Get-GitCommitSubjects -RepoDir $ProjectDir -Count 12)
        docs          = @($docInfo.ToArray())
        unresolvedCount = $unresolved.Count
        criticalHigh  = @($unresolved | Where-Object { $_.severity } | Select-Object -First 40)
    }
    if ($Extra) { foreach ($k in $Extra.Keys) { $state[$k] = $Extra[$k] } }

    [void](Write-TextFile (Join-Path $OutDir "active_state.json") (([pscustomobject]$state) | ConvertTo-Json -Depth 6))
    [void](Write-TextFile (Join-Path $OutDir "unresolved_index.json") ((@($unresolved) | ConvertTo-Json -Depth 4)))

    $sw.Stop()
    return [pscustomobject]@{
        Head = $head; Branch = $branch; DirtyCount = $dirty.Count
        UnresolvedCount = $unresolved.Count; Docs = @($docInfo.ToArray())
        RecentCommits = @($state.recentCommits); BuildMs = [int]$sw.ElapsedMilliseconds
    }
}
