# Registers a Windows Task Scheduler task that runs scripts\backup_daily.ps1 every day.
# Run once from PowerShell in the Find-IT folder:
#   powershell -ExecutionPolicy Bypass -File .\scripts\register_backup_task.ps1
# Optional: -Time "02:00"  -TaskName "Find-IT Daily Backup"
param(
    [string]$Time = "02:00",
    [string]$TaskName = "Find-IT Daily Backup"
)
$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "backup_daily.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`"" `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: if the PC was off at the scheduled time, run as soon as it is back on.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Daily Find-IT database backup with retention" -Force | Out-Null
Write-Host "Registered '$TaskName' to run daily at $Time."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Then check:        Get-ScheduledTaskInfo -TaskName '$TaskName'  (LastTaskResult 0 = success)"
