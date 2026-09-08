# start-server.ps1 - 운영 기동 스크립트 (SETTING.MD 7.3)
# frontend 빌드 -> FastAPI(uvicorn) 운영 기동. Task Scheduler "시스템 시작 시"에서 호출된다.
#
# [Tailscale Funnel 안내]
#   외부 공개는 Tailscale Funnel로 한다 (포트포워딩 불필요, 무료).
#   최초 1회 (관리자 아님, 브라우저 승인 1회 필요. MagicDNS/HTTPS는 첫 실행 프롬프트로 활성화):
#       tailscale funnel --bg 8000
#   접속 주소: https://<pc이름>.<tailnet>.ts.net
#   funnel --bg 는 보통 재부팅 후에도 유지된다. 재부팅 후 유지되지 않는 환경으로 확인되면
#   아래 "funnel 재기동" 주석을 해제하라.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$backendDir = Join-Path $repoRoot "backend"
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

try { Start-Transcript -Path (Join-Path $logDir "start-server.log") -Append | Out-Null } catch {}

foreach ($cmd in @("npm", "uv")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "'$cmd' 명령을 찾을 수 없습니다. Task Scheduler 실행 계정의 PATH를 확인하세요 (README 트러블슈팅 참조)."
    }
}
if (-not (Test-Path (Join-Path $backendDir ".env"))) {
    throw "backend\.env 가 없습니다. backend\.env.example 을 복사해 APP_PASSWORD, JWT_SECRET 을 채우세요."
}

Write-Output "[1/2] frontend build: $frontendDir"
Push-Location $frontendDir
try {
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm install 실패 (exit $LASTEXITCODE)" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build 실패 (exit $LASTEXITCODE)" }
}
finally { Pop-Location }

Write-Output "[2/2] backend start: $backendDir (port 8000)"
Push-Location $backendDir
try {
    uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync 실패 (exit $LASTEXITCODE)" }

    # funnel 재기동 (재부팅 후 funnel이 유지되지 않는 환경에서만 주석 해제):
    # tailscale funnel --bg 8000

    # 기동 전 포트 8000 점유 프로세스 정리 (이 스크립트는 Task Scheduler 최고 권한으로 돌므로
    # 고아가 된 이전 서버도 종료 가능 — 일반 셸의 restart-server가 권한 부족으로 못 죽인 경우 대비)
    $stale = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($stale) {
        $stale | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
            Write-Output "포트 8000 점유 프로세스 종료 (PID $_)"
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 2
    }

    # --reload 없이 운영 기동. 이 프로세스가 서버 본체이므로 여기서 블로킹된다.
    # uv run 대신 venv python 직접 실행 (uv 기동 지연 회피 — restart-server.ps1과 동일 이유)
    & (Join-Path $backendDir ".venv\Scripts\python.exe") -m uvicorn app.main:app --host 0.0.0.0 --port 8000
}
finally {
    Pop-Location
    try { Stop-Transcript | Out-Null } catch {}
}
