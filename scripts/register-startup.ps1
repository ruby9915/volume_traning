# register-startup.ps1 - Task Scheduler 등록 스크립트 (SETTING.MD 7.1 운영 설정)
# "시스템 시작 시" start-server.ps1 을 실행하는 작업을 등록한다.
# -BackupDir 을 주면 매일 04:00 backup.ps1 스냅샷 작업도 함께 등록한다 (SETTING.MD 7.4).
#
# 사용법 (관리자 PowerShell 필수):
#   .\register-startup.ps1
#   .\register-startup.ps1 -BackupDir "C:\Users\me\OneDrive\volume-app-backup"
#
# 등록 확인:  Get-ScheduledTask -TaskName "VolumeApp-*"
# 즉시 테스트: Start-ScheduledTask -TaskName "VolumeApp-StartServer"
# 해제:       Unregister-ScheduledTask -TaskName "VolumeApp-StartServer" -Confirm:$false

#Requires -RunAsAdministrator
param(
    [string]$BackupDir = "",
    [string]$BackupTime = "04:00"
)

$ErrorActionPreference = "Stop"

$startScript = Join-Path $PSScriptRoot "start-server.ps1"
$backupScript = Join-Path $PSScriptRoot "backup.ps1"
if (-not (Test-Path $startScript)) { throw "start-server.ps1 을 찾을 수 없습니다: $startScript" }

$taskUser = "$env:USERDOMAIN\$env:USERNAME"
# S4U: 로그온하지 않아도 실행, 비밀번호 저장 없음
$principal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType S4U -RunLevel Limited
# ExecutionTimeLimit 0 = 무제한 (서버 프로세스는 계속 떠 있어야 함)
$serverSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$serverAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
$serverTrigger = New-ScheduledTaskTrigger -AtStartup

Register-ScheduledTask -TaskName "VolumeApp-StartServer" `
    -Action $serverAction -Trigger $serverTrigger `
    -Settings $serverSettings -Principal $principal -Force | Out-Null
Write-Output "등록 완료: VolumeApp-StartServer (시스템 시작 시 $startScript)"

if ($BackupDir -ne "") {
    if (-not (Test-Path $backupScript)) { throw "backup.ps1 을 찾을 수 없습니다: $backupScript" }
    $backupSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $backupAction = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`" -DestinationDir `"$BackupDir`""
    $backupTrigger = New-ScheduledTaskTrigger -Daily -At $BackupTime

    Register-ScheduledTask -TaskName "VolumeApp-DailyBackup" `
        -Action $backupAction -Trigger $backupTrigger `
        -Settings $backupSettings -Principal $principal -Force | Out-Null
    Write-Output "등록 완료: VolumeApp-DailyBackup (매일 $BackupTime -> $BackupDir)"
}
else {
    Write-Output "참고: -BackupDir 미지정 - 일일 백업 작업은 등록하지 않았습니다."
}
