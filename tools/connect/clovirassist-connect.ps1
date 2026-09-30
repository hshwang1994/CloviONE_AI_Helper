<#
  ClovirAssist ChatGPT 계정 연결 도우미 (Windows)

  ClovirAssist 의 AI 설정 화면에서 "Continue with ChatGPT" 를 누르면 이 파일을 실행하는 명령이 나온다. 이 도우미는
  브라우저가 있는 이 PC 에서 ChatGPT 의 로그인 콜백(http://127.0.0.1:<포트>/auth/callback)을 받아 ClovirAssist
  서버에 넘기기만 한다. 토큰은 이 PC 를 거치지 않는다 - 인가 코드를 토큰으로 바꾸는 일은 서버가 한다.

    powershell -NoProfile -ExecutionPolicy Bypass -File .\clovirassist-connect.ps1 -Server https://clovirassist.example -Token <토큰> [-Fingerprint sha256:<지문>]

  Windows PowerShell 5.1 과 PowerShell 7 에서 돈다. 파이썬이 필요 없다. 서버 인증서 지문(-Fingerprint)을 주면 그
  지문의 인증서만 믿는다 - 설치가 만든 자체 서명 인증서에서도 안전하게 붙는다.
#>
param(
  [Parameter(Mandatory = $true)][string]$Server,
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$Fingerprint = "",
  [int]$Port = 1455
)

$ErrorActionPreference = "Stop"
$CallbackPath = "/auth/callback"
$WaitSeconds = 600

function Fail([string]$Message) {
  Write-Host "연결하지 못했습니다. $Message"
  exit 1
}

# ── 서버 주소와 지문 ─────────────────────────────────────────────────────────
try { $ServerUri = [System.Uri]$Server } catch { Fail "서버 주소는 https:// 로 시작해야 합니다." }
$isLoopback = $ServerUri.Host -eq "127.0.0.1" -or $ServerUri.Host -eq "localhost"
if ($ServerUri.Scheme -ne "https" -and -not ($ServerUri.Scheme -eq "http" -and $isLoopback)) {
  Fail "서버 주소는 https:// 로 시작해야 합니다."
}
$Pin = ""
if ($Fingerprint) {
  $Pin = $Fingerprint.Trim().ToLowerInvariant()
  if ($Pin.StartsWith("sha256:")) { $Pin = $Pin.Substring(7) }
  $Pin = $Pin.Replace(":", "")
  if ($Pin -notmatch '^[0-9a-f]{64}$') { Fail "인증서 지문 형식이 올바르지 않습니다. 화면의 명령을 그대로 붙여 넣으세요." }
}

# ── 지문을 비교하는 HTTP 클라이언트 ──────────────────────────────────────────
# 검사를 C# 로 둔다. PowerShell 스크립트 블록을 인증서 콜백으로 넘기면 다른 스레드에서 불릴 때 멈출 수 있다.
$refs = @()
if ($PSVersionTable.PSEdition -ne "Core") {
  Add-Type -AssemblyName System.Net.Http
  $refs = @("System.Net.Http")
}
$source = @"
using System;
using System.Net.Http;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

public static class ClovirAssistConnect {
  public static HttpClient Create(string pin) {
    var handler = new HttpClientHandler();
    if (!String.IsNullOrEmpty(pin)) {
      handler.ServerCertificateCustomValidationCallback = (message, cert, chain, errors) => {
        if (cert == null) { return false; }
        using (var sha = SHA256.Create()) {
          var hash = BitConverter.ToString(sha.ComputeHash(cert.RawData)).Replace("-", "").ToLowerInvariant();
          return hash == pin;
        }
      };
    }
    var client = new HttpClient(handler);
    client.Timeout = TimeSpan.FromSeconds(30);
    return client;
  }
}
"@
if (-not ("ClovirAssistConnect" -as [type])) {
  if ($refs.Count -gt 0) { Add-Type -TypeDefinition $source -ReferencedAssemblies $refs } else { Add-Type -TypeDefinition $source }
}
if ($PSVersionTable.PSEdition -ne "Core") {
  [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
}
$Client = [ClovirAssistConnect]::Create($Pin)

function Post-Json([string]$Path, $Body) {
  $json = $Body | ConvertTo-Json -Depth 5 -Compress
  $content = New-Object System.Net.Http.StringContent($json, [System.Text.Encoding]::UTF8, "application/json")
  $url = $ServerUri.GetLeftPart([System.UriPartial]::Authority) + $Path
  try {
    $response = $Client.PostAsync($url, $content).GetAwaiter().GetResult()
  } catch {
    Fail "서버에 연결하지 못했습니다. 서버 주소와 인증서 지문을 확인하세요."
  }
  $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
  $data = $null
  if ($raw) { try { $data = $raw | ConvertFrom-Json } catch { $data = $null } }
  if (-not $response.IsSuccessStatusCode) {
    $message = $null
    if ($data -and $data.error -and $data.error.message) { $message = $data.error.message }
    if (-not $message) { $message = "서버가 요청을 거절했습니다(HTTP " + [int]$response.StatusCode + ")." }
    Fail $message
  }
  return $data
}

# ── 콜백을 받을 빈 포트 ──────────────────────────────────────────────────────
# HttpListener 대신 TcpListener 를 쓴다. HttpListener 의 127.0.0.1 주소는 관리자 권한을 요구할 수 있다.
$Listener = $null
for ($p = $Port; $p -lt $Port + 20; $p++) {
  try {
    $candidate = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
    $candidate.ExclusiveAddressUse = $true
    $candidate.Start()
    $Listener = $candidate
    $Port = $p
    break
  } catch { continue }
}
if (-not $Listener) { Fail "콜백을 받을 빈 포트를 찾지 못했습니다." }

function Read-Query([string]$Query) {
  $values = @{}
  foreach ($pair in $Query.TrimStart("?").Split("&")) {
    if (-not $pair) { continue }
    $kv = $pair.Split("=", 2)
    $key = [System.Uri]::UnescapeDataString($kv[0].Replace("+", " "))
    $value = ""
    if ($kv.Count -gt 1) { $value = [System.Uri]::UnescapeDataString($kv[1].Replace("+", " ")) }
    if (-not $values.ContainsKey($key)) { $values[$key] = $value }
  }
  return $values
}

function Wait-Callback {
  $deadline = (Get-Date).AddSeconds($WaitSeconds)
  while ((Get-Date) -lt $deadline) {
    if (-not $Listener.Pending()) { Start-Sleep -Milliseconds 200; continue }
    $tcp = $Listener.AcceptTcpClient()
    try {
      $stream = $tcp.GetStream()
      $stream.ReadTimeout = 5000
      $buffer = New-Object byte[] 16384
      $total = 0
      $text = ""
      while ($total -lt $buffer.Length) {
        $read = $stream.Read($buffer, $total, $buffer.Length - $total)
        if ($read -le 0) { break }
        $total += $read
        $text = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $total)
        if ($text.Contains("`r`n`r`n")) { break }
      }
      $line = ($text -split "`r`n")[0]
      $parts = $line.Split(" ")
      $target = ""
      if ($parts.Count -ge 2) { $target = $parts[1] }
      $path = $target.Split("?")[0]
      if ($parts[0] -ne "GET" -or $path -ne $CallbackPath) {
        $notFound = [System.Text.Encoding]::ASCII.GetBytes("HTTP/1.1 404 Not Found`r`nContent-Length: 0`r`nConnection: close`r`n`r`n")
        $stream.Write($notFound, 0, $notFound.Length)
        continue
      }
      $query = ""
      if ($target.Contains("?")) { $query = $target.Substring($target.IndexOf("?") + 1) }
      $html = "<!doctype html><html lang=`"ko`"><meta charset=`"utf-8`"><title>ClovirAssist</title><body style=`"font-family:sans-serif;padding:2rem`"><p>ChatGPT 승인을 받았습니다. ClovirAssist 화면으로 돌아가세요. 이 창은 닫아도 됩니다.</p></body></html>"
      $body = [System.Text.Encoding]::UTF8.GetBytes($html)
      $head = [System.Text.Encoding]::ASCII.GetBytes("HTTP/1.1 200 OK`r`nContent-Type: text/html; charset=utf-8`r`nContent-Length: " + $body.Length + "`r`nConnection: close`r`n`r`n")
      $stream.Write($head, 0, $head.Length)
      $stream.Write($body, 0, $body.Length)
      return (Read-Query $query)
    } finally {
      $tcp.Close()
    }
  }
  Fail "브라우저 승인을 기다리는 시간이 지났습니다. 화면에서 연결을 다시 시작하세요."
}

try {
  $begun = Post-Json "/api/connect/openai/begin" @{ pairing_token = $Token; port = $Port }
  if (-not $begun.authorize_url -or -not $begun.authorize_url.StartsWith("https://") -or -not $begun.transaction_id) {
    Fail "서버가 인가 주소를 주지 않았습니다."
  }
  Write-Host "브라우저에서 ChatGPT 승인 화면을 엽니다. 열리지 않으면 아래 주소를 브라우저에 붙여 넣으세요."
  Write-Host $begun.authorize_url
  Start-Process $begun.authorize_url
  $callback = Wait-Callback
  $done = Post-Json "/api/connect/openai/complete" @{
    pairing_token = $Token
    transaction_id = $begun.transaction_id
    callback = @{
      code = $callback["code"]; state = $callback["state"]; client_id = $callback["client_id"]
      scope = $callback["scope"]; error = $callback["error"]
    }
  }
} finally {
  $Listener.Stop()
}
$label = "ChatGPT"
if ($done -and $done.account_label) { $label = $done.account_label }
Write-Host "$label 계정을 연결했습니다. ClovirAssist 화면으로 돌아가세요."
exit 0
