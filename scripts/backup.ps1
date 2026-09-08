# backup.ps1 - SQLite 스냅샷 백업 (SETTING.MD 7.4)
# VACUUM INTO 로 app-YYYYMMDD.db 스냅샷을 만들어 대상 폴더(클라우드 동기화 폴더 권장)에 저장.
# 대상 폴더의 app-*.db 는 최근 -Keep 개(기본 30)만 보존하고 이전 것은 삭제한다.
#
# 사용법:
#   .\backup.ps1 -DestinationDir "C:\Users\me\OneDrive\volume-app-backup"
#   .\backup.ps1 -DestinationDir D:\backup -DbPath C:\somewhere\app.db -Keep 60

param(
    [Parameter(Mandatory = $true)]
    [string]$DestinationDir,
    [string]$DbPath = "",
    [int]$Keep = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ($DbPath -eq "") { $DbPath = Join-Path $repoRoot "backend\data\app.db" }

if (-not (Test-Path $DbPath)) { throw "DB 파일이 없습니다: $DbPath" }
if (-not (Test-Path $DestinationDir)) {
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd"
$target = Join-Path $DestinationDir ("app-" + $stamp + ".db")
# 같은 날 재실행 시 최신 스냅샷으로 교체 (VACUUM INTO 는 기존 파일이 있으면 실패)
if (Test-Path $target) { Remove-Item $target -Force }

# VACUUM INTO: WAL 포함 일관된 시점의 단일 파일 스냅샷 (서버 실행 중에도 안전)
$py = @'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
con = sqlite3.connect(src)
con.execute("VACUUM INTO ?", (dst,))
con.close()
print("snapshot ok: " + dst)
'@
$py | uv run --no-project python - "$DbPath" "$target"
if ($LASTEXITCODE -ne 0) { throw "VACUUM INTO 실패 (exit $LASTEXITCODE)" }

# 보존 정책: 파일명이 app-YYYYMMDD.db 라 이름 내림차순 = 최신순
$old = Get-ChildItem -Path $DestinationDir -Filter "app-*.db" |
    Sort-Object Name -Descending |
    Select-Object -Skip $Keep
foreach ($f in $old) {
    Remove-Item $f.FullName -Force
    Write-Output ("removed old snapshot: " + $f.Name)
}

Write-Output ("backup done: " + $target + " (keep " + $Keep + ")")
