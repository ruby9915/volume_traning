# install-cloudflare-tunnel.ps1 - Cloudflare Tunnel 커넥터 설치 (SETTING.MD §12, 2026-09-10 결정)
# 외부 공개를 Tailscale Funnel 대신 Cloudflare Tunnel(원격 관리 터널)로 한다.
# PC에는 설정 파일 없이 커넥터 서비스(cloudflared)만 깔리고, 호스트명·라우팅은 Cloudflare 대시보드에서 관리.
#
# 준비 (사용자, 대시보드에서 1회):
#   1. 도메인을 Cloudflare DNS에 등록 (무료 플랜)
#   2. Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared > 이름 입력
#   3. "Install and run a connector" 단계의 Windows 명령에서 토큰(긴 문자열)만 복사
#   4. Public Hostname 탭: Subdomain(예: volume) + Domain 선택, Service = HTTP, URL = 127.0.0.1:8000
#
# 사용법 (관리자 PowerShell):
#   .\scripts\install-cloudflare-tunnel.ps1 -Token "<복사한 토큰>"
#   .\scripts\install-cloudflare-tunnel.ps1 -Status
#   .\scripts\install-cloudflare-tunnel.ps1 -Uninstall
#
# 서비스는 Windows 부팅 시 자동 시작되며 VolumeApp-StartServer 예약 작업과 독립이다.
# 앱은 지금처럼 127.0.0.1:8000만 듣는다 (인바운드 포트 개방·포트포워딩 없음).

#Requires -RunAsAdministrator
param(
    [string]$Token = "",
    [switch]$Status,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$serviceName = "Cloudflared"

function Get-CloudflaredPath {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

function Show-Status {
    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Output "cloudflared 서비스: $($svc.Status) (시작 유형: $((Get-CimInstance Win32_Service -Filter "Name='$serviceName'").StartMode))"
    } else {
        Write-Output "cloudflared 서비스: 미설치"
    }
    try {
        $h = Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 3
        Write-Output "앱(127.0.0.1:8000): $($h.status)"
    } catch {
        Write-Output "앱(127.0.0.1:8000): 응답 없음 - VolumeApp-StartServer 작업을 확인하세요"
    }
    $exe = Get-CloudflaredPath
    if ($exe) { Write-Output "cloudflared: $(& $exe --version 2>&1 | Select-Object -First 1)" }
    Write-Output "최근 로그: Get-WinEvent -LogName Application -MaxEvents 20 | Where-Object ProviderName -eq 'cloudflared'"
}

if ($Status) { Show-Status; exit 0 }

if ($Uninstall) {
    $exe = Get-CloudflaredPath
    if (-not $exe) { throw "cloudflared가 설치돼 있지 않습니다." }
    & $exe service uninstall
    Write-Output "cloudflared 서비스를 제거했습니다. 대시보드의 터널·호스트명은 남아 있으니 필요하면 거기서 삭제하세요."
    exit 0
}

if ($Token -eq "") {
    throw "-Token 을 지정하세요. Cloudflare 대시보드 > Zero Trust > Networks > Tunnels 에서 커넥터 설치 명령의 토큰을 복사합니다."
}
if ($Token.Length -lt 100) {
    throw "토큰이 너무 짧습니다 ($($Token.Length)자). 명령 전체가 아니라 'cloudflared service install' 뒤의 토큰 문자열만 붙여넣으세요."
}

# 1) cloudflared 설치 (winget)
$exe = Get-CloudflaredPath
if (-not $exe) {
    Write-Output "[1/3] cloudflared 설치 (winget)"
    winget install --id Cloudflare.cloudflared --exact --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "winget install 실패 (exit $LASTEXITCODE)" }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $exe = Get-CloudflaredPath
    if (-not $exe) { throw "설치 후에도 cloudflared.exe 를 찾지 못했습니다. PowerShell 을 새로 열고 다시 실행하세요." }
} else {
    Write-Output "[1/3] cloudflared 이미 설치됨: $exe"
}

# 2) 서비스 설치 (토큰 = 원격 관리 터널). 이미 있으면 교체.
Write-Output "[2/3] cloudflared 서비스 설치"
$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "  기존 서비스 발견 - 제거 후 재설치"
    if ($existing.Status -eq "Running") { Stop-Service -Name $serviceName -Force }
    & $exe service uninstall | Out-Null
    Start-Sleep -Seconds 2
}
& $exe service install $Token
if ($LASTEXITCODE -ne 0) { throw "cloudflared service install 실패 (exit $LASTEXITCODE)" }

# 3) 기동 확인
Write-Output "[3/3] 서비스 기동 확인"
$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $svc) { throw "서비스가 등록되지 않았습니다." }
if ($svc.Status -ne "Running") { Start-Service -Name $serviceName }
Set-Service -Name $serviceName -StartupType Automatic
foreach ($i in 1..15) {
    Start-Sleep -Seconds 2
    if ((Get-Service -Name $serviceName).Status -eq "Running") { break }
}
Show-Status
Write-Output ""
Write-Output "완료. 대시보드 Tunnels 목록에서 상태가 HEALTHY 로 바뀌면 Public Hostname 주소로 폰(LTE)에서 접속해 확인하세요."
Write-Output "Tailscale serve(tailnet 내부 주소)는 그대로 두었습니다 - 예비 경로."
