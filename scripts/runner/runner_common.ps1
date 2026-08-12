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

  --- 이 파일이 의존하는, 실측으로 확인한 플랫폼 사실 (2026-08-12) ---
  1) **Windows PowerShell 5.1에서 `Start-Process -PassThru` 자식의 `ExitCode` 가 `$null` 이
     되는 근본 원인은 프로세스 핸들 미캐시다.** 시작 직후 `$proc.Handle` 을 한 번 읽어
     핸들을 캐시하면 5.1에서도 정확한 exit code 가 나온다. 실측(probe1):
       PS 7.6.3 : 핸들 미접근 ExitCode=7 / 접근 ExitCode=7
       PS 5.1   : 핸들 미접근 ExitCode=<null> / **접근 ExitCode=7**
     운영 로그(var/runner/runner.log)에서 모든 invocation 이 exit code 를 못 읽던 것과
     state.json/session_id.txt 에 UTF-8 BOM 이 있던 것(=5.1 이 쓴 파일)이 이 진단과 일치한다.
     Claude JSON fallback 은 그대로 유지하되 **더 이상 유일한 성공 경로가 아니다**.
  2) **PS 5.1에서 `$ErrorActionPreference='Stop'` + native 명령 + stderr 리다이렉트는
     terminating error 다.** 실측(probe2, PS 5.1):
       `git -C <없는경로> rev-parse HEAD 2>$null`            → throw
       `git diff --name-only "deadbeef..HEAD" 2>$null`       → throw
       `git rev-parse --verify nosuchref 2>$null`            → throw
       `... 2>&1 | Out-String`                               → throw
       `$ErrorActionPreference='Continue'` 로 감싸면          → throw 안 함, $LASTEXITCODE 읽힘
     PS 7.6.3 에서는 어느 쪽도 throw 하지 않는다. 즉 이 결함은 **5.1 전용이며 실제 운영
     환경이 5.1이다**. git 이 stderr 에 한 줄만 뱉어도(dubious ownership 경고, 없는 리비전 등)
     Supervisor 가 통째로 죽던 경로였다. 모든 git 호출은 `Invoke-Git` 을 경유한다.
  3) `[pscustomobject]` 에 **없는 속성을 대입하면 throw 한다**(5.1/7 공통, 실측). state.json
     스키마가 바뀌면 조용히 죽으므로 읽을 때 반드시 정규화한다.
  4) `exit` 는 `try{}finally{}` 의 finally 를 실행하고 종료 코드도 보존한다(5.1/7 공통, 실측).
     잠금 해제를 finally 에 두어도 안전하다.
  5) PS 5.1 `Set-Content -Encoding utf8` 은 **BOM 을 쓴다**(7은 안 쓴다). marker/state/prompt
     를 두 버전이 번갈아 써도 같게 보이도록 BOM 없는 UTF-8 로 통일하고, 읽을 때는 BOM 을 벗긴다.
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
        $raw = Read-TextOrEmpty $JsonLogPath
        if ([string]::IsNullOrWhiteSpace($raw)) { return $unresolved }

        $result = $raw | ConvertFrom-Json -ErrorAction Stop

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
    <#  응답 JSON 에서 **실제로 쓰인** 모델을 읽는다. 요청값과 별개로 남겨 두면 나중에
        "정말 그 모델로 돌았나"를 로그만으로 확인할 수 있다. 추측하지 않는다. #>
    param([string]$JsonLogPath)
    try {
        $raw = Read-TextOrEmpty $JsonLogPath
        if ([string]::IsNullOrWhiteSpace($raw)) { return "unknown" }
        $usage = ($raw | ConvertFrom-Json).modelUsage
        if (-not $usage) { return "unknown" }
        $names = @($usage.PSObject.Properties | ForEach-Object { $_.Value.canonicalModel } |
                   Where-Object { $_ } | Sort-Object -Unique)
        if ($names.Count -eq 0) { $names = @($usage.PSObject.Properties.Name) }
        if ($names.Count -eq 0) { return "unknown" }
        return ($names -join ',')
    } catch { return "unknown" }
}

function Invoke-ClaudeWorker {
    <#  Claude Code 를 한 번 띄우고 **정확한 종료 상태**를 돌려준다.

        프롬프트는 반드시 파일 → stdin 리다이렉트로 넘긴다. -ArgumentList 배열 원소로 넘기면
        Windows 커맨드라인 재조립 과정에서 멀티라인/특수문자가 깨져 프롬프트 안의 예시 텍스트가
        claude.exe 자신의 옵션으로 오인된다(2026-08-11 실제 장애: "unknown option '--oneline'").
        같은 이유로 $ArgList 에 **빈 문자열 원소를 넣지 마라** — 재조립 때 누락되어 뒤 인자가
        한 칸씩 밀리고, --session-id/--resume 가 엉뚱한 값에 붙는 것까지 확인된 함정이다. #>
    param(
        [string]$ClaudeExe,
        [string[]]$ArgList,
        [string]$WorkingDirectory,
        [string]$PromptFile,
        [string]$StdOutFile,
        [string]$StdErrFile,
        # double 인 이유: controlled test 가 3초(0.05분) 같은 값으로 timeout 경로를 실제로
        # 밟아 볼 수 있게 하기 위함이다. production 기본값은 그대로 분 단위 정수다.
        [double]$TimeoutMinutes,
        [string]$LogPath
    )

    $outcome = [pscustomobject]@{
        ExitCode = 125; Source = "unresolved"; TimedOut = $false
        HandleCached = $false; StartedAt = (Get-Date); Subtype = $null
        IsError = $null; TerminalReason = $null; Pid = 0
    }

    # 프로세스를 못 띄우는 것(실행 파일 없음/권한/경로)은 Supervisor 를 죽일 이유가 아니다 —
    # 실패로 세고 다음 반복으로 넘겨서, 연속 실패 상한이 정상적으로 AUTO_STOP 을 만들게 한다.
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

    # Wait-Process -PassThru 는 기다림이 실패해도 객체를 돌려주므로 timeout 판정에 쓸 수 없다
    # (2026-08-12 실제로 강제 종료 분기 전체가 죽은 코드였다). WaitForExit(ms) 는 bool 을 준다.
    $waitMs = [int][Math]::Max(1000, [Math]::Min([int]::MaxValue, $TimeoutMinutes * 60 * 1000))
    $exited = $proc.WaitForExit($waitMs)

    if (-not $exited) {
        if ($LogPath) { Write-LogLine $LogPath "invocation 이 ${TimeoutMinutes}분 안에 끝나지 않아 프로세스 트리를 강제 종료한다(PID=$($outcome.Pid))." }
        Stop-ProcessTreeSafe -ProcessId $outcome.Pid -LogPath $LogPath
        try { [void]$proc.WaitForExit(10000) } catch { }
        $outcome.ExitCode = 124          # 관례적 timeout 코드
        $outcome.Source   = "timeout"
        $outcome.TimedOut = $true
        return $outcome                   # timeout 에는 JSON fallback 을 절대 적용하지 않는다
    }

    # 리다이렉션 마무리를 한 번 더 기다린 뒤 상태를 갱신한다.
    try { [void]$proc.WaitForExit() } catch { }
    try { $proc.Refresh() } catch { }

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
        이제 상태 코드는 앞뒤 문맥이 있을 때만 인정한다. #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    return ($Text -match '(?i)rate[ _-]?limit' -or
            $Text -match '(?i)overloaded' -or
            $Text -match '(?i)too many requests' -or
            $Text -match '(?i)usage limit' -or
            $Text -match '(?i)service[ _-]?unavailable' -or
            $Text -match '(?i)(status|http|code)\D{0,12}\b(429|503|529)\b' -or
            $Text -match '(?i)\b(429|503|529)\b\s*(too many|service|overload)')
}

function Get-BackoffSeconds {
    param([int]$Hits, [int]$BaseSeconds, [int]$MaxSeconds)
    if ($Hits -lt 1) { $Hits = 1 }
    if ($Hits -gt 20) { $Hits = 20 }   # Pow 폭주 방지
    $v = [double]$BaseSeconds * [Math]::Pow(2, $Hits - 1)
    if ($v -gt $MaxSeconds) { $v = [double]$MaxSeconds }
    return [int][Math]::Round($v)
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
