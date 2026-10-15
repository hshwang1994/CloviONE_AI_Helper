<#
.SYNOPSIS
  클래식 Outlook(Windows, Word 엔진)으로 메일 틀을 그려 창을 찍는다 (D-571).

.DESCRIPTION
  `scripts/ui_qa/mail_render_matrix.py --no-shots` 가 낸 src 폴더(종류별 HTML · 로고 PNG · manifest.json)를 받아, 이 PC 의 클래식 Outlook 에서
  새 메일 작성 창을 하나씩 열고(CreateItem(0)), 로고를 CID 첨부(PR_ATTACH_CONTENT_ID · 숨김)로 붙인 뒤 HTMLBody 를 넣고, 창을 맨 앞으로
  최대화해 화면을 찍는다. 찍은 뒤 창은 버린다(Close(1) = olDiscard). 보내지 않고 저장하지 않는다.

  지키는 것(사람이 쓰는 Outlook 이다):
    - 이미 떠 있는 Outlook 에 붙는다. 끄거나 다시 띄우지 않는다. 떠 있지 않았을 때만 COM 이 한 번 띄우고, 그때만 끝에 Quit() 한다.
    - Office 테마(레지스트리 UI Theme)를 바꾸지 않는다. 지금 테마 하나로만 그리고 그 이름을 보고서에 적는다.
    - 이 스크립트가 만든 작성 창만 연다. Send · Save 를 부르지 않는다. 임시 보관함(Drafts) 수를 앞뒤로 세어 같음을 확인한다.
    - 찍기 전에 창을 맨 앞에 세우고(SetForegroundWindow · 최대화 · 잠시 맨 위) 1.5초 기다린 뒤, 맨 앞 창의 제목이 이 메일의 제목인지 확인한다.

.EXAMPLE
  pwsh -File scripts/ui_qa/outlook_render.ps1 -Source dist/ui-qa/mail-templates/<ts>/src
  pwsh -File scripts/ui_qa/outlook_render.ps1 -Source <src> -Kinds test,password_reset -NoImage
#>
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [string[]]$Kinds = @('test', 'ticket_assigned', 'password_reset', 'notify_email_verification', 'account_locked'),
  [string]$Out = '',
  [switch]$NoImage,
  [int]$WaitMs = 1500
)

$ErrorActionPreference = 'Stop'
# `pwsh -File` 은 `-Kinds a,b` 를 문자열 하나로 넘긴다 - 쉼표로 다시 가른다.
$Kinds = @($Kinds | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class CaWin {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static string Title(IntPtr h) { var sb = new StringBuilder(512); GetWindowTextW(h, sb, 512); return sb.ToString(); }
}
"@
[void][CaWin]::SetProcessDPIAware()

$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$Source = (Resolve-Path $Source).Path
$manifest = Get-Content -Raw -Encoding utf8 (Join-Path $Source 'manifest.json') | ConvertFrom-Json
$logo = Join-Path $Source $manifest.logo
$cid = $manifest.cid
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $Out) { $Out = Join-Path $Root "dist\ui-qa\mail-outlook\$stamp" }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

# 지금 Office 테마 - 읽기만 한다(바꾸지 않는다). 6 = Windows 설정을 따름.
$themeNames = @{ 0 = 'colorful'; 3 = 'darkgray'; 4 = 'black'; 5 = 'white'; 6 = 'system' }
$themeValue = (Get-ItemProperty 'HKCU:\Software\Microsoft\Office\16.0\Common' -ErrorAction SilentlyContinue).'UI Theme'
$theme = if ($null -ne $themeValue -and $themeNames.ContainsKey([int]$themeValue)) { $themeNames[[int]$themeValue] } else { 'unknown' }
if ($theme -eq 'system') {
  $light = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize' -ErrorAction SilentlyContinue).AppsUseLightTheme
  $theme = if ($light -eq 0) { 'system-dark' } else { 'system-light' }
}

$wasRunning = [bool](Get-Process OUTLOOK -ErrorAction SilentlyContinue)
$ol = New-Object -ComObject Outlook.Application
$ns = $ol.GetNamespace('MAPI')
$drafts = $ns.GetDefaultFolder(16)
$draftsBefore = $drafts.Items.Count
$version = $ol.Version

function Show-Front([IntPtr]$hwnd) {
  [void][CaWin]::ShowWindow($hwnd, 3)  # SW_MAXIMIZE
  $fg = [CaWin]::GetForegroundWindow()
  $me = [CaWin]::GetCurrentThreadId()
  $other = [CaWin]::GetWindowThreadProcessId($fg, [IntPtr]::Zero)
  $attached = $false
  if ($other -ne 0 -and $other -ne $me) { $attached = [CaWin]::AttachThreadInput($me, $other, $true) }
  [void][CaWin]::BringWindowToTop($hwnd)
  [void][CaWin]::SetForegroundWindow($hwnd)
  if ($attached) { [void][CaWin]::AttachThreadInput($me, $other, $false) }
  # 찍는 동안만 맨 위(HWND_TOPMOST = -1). 다른 창이 찍힌 칸을 덮지 못하게 한다. SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW.
  [void][CaWin]::SetWindowPos($hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x0043)
}

$rows = @()
foreach ($kind in $Kinds) {
  $item = $manifest.items | Where-Object { $_.kind -eq $kind }
  if (-not $item) { Write-Host "SKIP $kind (manifest 에 없음)"; continue }
  $html = Get-Content -Raw -Encoding utf8 (Join-Path $Source $item.file)
  $variant = if ($NoImage) { 'noimage' } else { 'image' }
  $subject = "[render] $kind $variant $stamp"
  $mail = $null; $insp = $null
  try {
    $mail = $ol.CreateItem(0)
    $mail.Subject = $subject
    if (-not $NoImage) {
      $att = $mail.Attachments.Add($logo, 1, 0, $manifest.logo)
      $pa = $att.PropertyAccessor
      $pa.SetProperty('http://schemas.microsoft.com/mapi/proptag/0x3712001F', $cid)
      $pa.SetProperty('http://schemas.microsoft.com/mapi/proptag/0x7FFE000B', $true)
    }
    $mail.HTMLBody = $html
    $insp = $mail.GetInspector
    $insp.Display($false)
    Start-Sleep -Milliseconds 800
    $insp.WindowState = 0  # olMaximized
    $caption = $insp.Caption
    $hwnd = [CaWin]::FindWindowW('rctrl_renwnd32', $caption)
    if ($hwnd -eq [IntPtr]::Zero) { $hwnd = [CaWin]::FindWindowW($null, $caption) }
    if ($hwnd -eq [IntPtr]::Zero) { throw "작성 창을 찾지 못했습니다: $caption" }
    $insp.Activate()
    Show-Front $hwnd
    Start-Sleep -Milliseconds $WaitMs
    $front = [CaWin]::Title([CaWin]::GetForegroundWindow())
    $rect = New-Object CaWin+RECT
    [void][CaWin]::GetWindowRect($hwnd, [ref]$rect)
    $w = $rect.Right - $rect.Left; $h = $rect.Bottom - $rect.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
    $file = Join-Path $Out "$kind-$theme-$variant.png"
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    [void][CaWin]::SetWindowPos($hwnd, [IntPtr](-2), 0, 0, 0, 0, 0x0043)  # HWND_NOTOPMOST
    $rows += [pscustomobject]@{ kind = $kind; theme = $theme; variant = $variant; file = (Split-Path $file -Leaf);
      caption = $caption; front_ok = ($front -eq $caption); front = $front; width = $w; height = $h }
    Write-Host ("SHOT {0} {1} {2} front={3}" -f $kind, $theme, $variant, ($front -eq $caption))
  } finally {
    if ($mail) { try { $mail.Close(1) } catch { Write-Host "닫기 실패: $_" } }
    foreach ($o in @($insp, $mail)) { if ($o) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($o) } }
  }
}

Start-Sleep -Milliseconds 500
$draftsAfter = $drafts.Items.Count
# 같은 폴더로 여러 번 돌리면(그림 있음 · 없음) 앞선 줄을 이어 적는다 - 같은 종류 · 테마 · 그림의 줄만 새것으로 바뀐다.
$previous = @()
$jsonPath = Join-Path $Out 'report.json'
if (Test-Path $jsonPath) { $previous = @(Get-Content -Raw -Encoding utf8 $jsonPath | ConvertFrom-Json) }
$keys = @($rows | ForEach-Object { "$($_.kind)|$($_.theme)|$($_.variant)" })
$rows = @($previous | Where-Object { $keys -notcontains "$($_.kind)|$($_.theme)|$($_.variant)" }) + $rows
$lines = @(
  '# 클래식 Outlook 렌더 (COM)', '',
  "- Outlook $version, Office 테마 $theme(읽기만 함), 화면 배율 100%가 아니면 픽셀 값이 배율만큼 커진다.",
  "- 입력 $Source",
  "- 임시 보관함 수: 앞 $draftsBefore, 뒤 $draftsAfter (같아야 한다 - 저장한 메일 없음)",
  "- Outlook 이 이미 떠 있었는가: $wasRunning", '',
  '| 종류 | 테마 | 그림 | 파일 | 맨 앞 창 제목 일치 | 창 크기 |', '|---|---|---|---|---|---|'
)
foreach ($r in $rows) { $lines += "| $($r.kind) | $($r.theme) | $($r.variant) | $($r.file) | $($r.front_ok) | $($r.width)x$($r.height) |" }
$lines | Set-Content -Encoding utf8 (Join-Path $Out 'report.md')
ConvertTo-Json -InputObject @($rows) | Set-Content -Encoding utf8 $jsonPath

foreach ($o in @($drafts, $ns)) { if ($o) { [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($o) } }
if (-not $wasRunning) { $ol.Quit() }
[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ol)
$ok = ($draftsBefore -eq $draftsAfter) -and ($rows.Count -gt 0) -and -not ($rows | Where-Object { -not $_.front_ok })
$tag = if ($ok) { 'OUTLOOK_RENDER_OK' } else { 'OUTLOOK_RENDER_CHECK' }
Write-Host "$tag ($($rows.Count)) -> $Out drafts $draftsBefore/$draftsAfter"
