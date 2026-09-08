# restart-server.ps1 - 서버 빠른 재시작 (.env 변경 반영용)
# frontend 빌드 없이 backend 서버만 내렸다 다시 올린다.
# 코드(frontend/backend)를 수정했다면 대신 start-server.ps1 을 쓸 것.
# 사용법:  .\scripts\restart-server.ps1

$ErrorActionPreference = "Stop"
$backendDir = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
# 폰 접속 주소 (Tailscale serve/funnel) - 안내 출력 전용. 이 PC의 tailnet 이름이 바뀌면 여기만 수정
$publicUrl = "https://desktop-8k13b1r.tail6df393.ts.net"

# 1) 8000 포트를 점유한 프로세스만 정확히 종료 (다른 python 작업은 건드리지 않음)
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $conn | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Write-Output "기존 서버 종료 (PID $_)"
        try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {
            Write-Output "  직접 종료 실패($($_.Exception.Message.Trim())) - Task Scheduler 서버로 판단"
        }
    }
    Start-Sleep -Seconds 2
    # 권한 부족으로 못 죽인 경우(Task Scheduler가 띄운 서버): 작업 경유로 재시작 위임
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        Write-Output "포트가 아직 점유됨 - VolumeApp-StartServer 작업으로 재시작을 위임합니다 (빌드 포함, 1~2분)"
        schtasks /End /TN "VolumeApp-StartServer" 2>$null | Out-Null
        schtasks /Run /TN "VolumeApp-StartServer" | Out-Null
        foreach ($i in 1..120) {
            Start-Sleep -Seconds 2
            try {
                $h = Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2
                if ($h.status -eq "ok") {
                    Write-Output "작업 경유 재시작 완료: http://127.0.0.1:8000 (health ok)"
                    Write-Output "폰 접속 주소: $publicUrl"
                    exit 0
                }
            } catch {}
        }
        Write-Output "작업 경유 재시작이 4분 안에 완료되지 않았습니다. scripts\logs\start-server.log 확인 필요."
        exit 1
    }
} else {
    Write-Output "실행 중인 서버 없음 - 새로 시작합니다"
}

# 2) 서버 기동 (백그라운드, 창 없음)
#    uv run 대신 venv python 직접 실행 - uv의 기동 지연(백신 검사 등으로 수십 초 편차)을 회피
$py = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "backend\.venv 이 없습니다. backend 폴더에서 'uv sync'를 먼저 실행하세요."
}
Start-Process -FilePath $py `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $backendDir -WindowStyle Hidden

# 3) 기동 확인 (포트가 열린 뒤 health 응답까지, 최대 90초)
$ok = $false
foreach ($i in 1..90) {
    Start-Sleep -Seconds 1
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        try {
            # localhost 금지: 이 PC에서 IPv6(::1) 우선 해석 때문에 간헐적으로 타임아웃 난다
            $h = Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2
            if ($h.status -eq "ok") { $ok = $true; break }
        } catch {}
    }
}
if ($ok) {
    Write-Output "서버 재시작 완료: http://127.0.0.1:8000 (health ok)"
    Write-Output "폰 접속 주소: $publicUrl"
} else {
    Write-Output "서버가 90초 안에 응답하지 않습니다. backend 폴더에서 직접 실행해 에러를 확인하세요:"
    Write-Output "  cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
}
