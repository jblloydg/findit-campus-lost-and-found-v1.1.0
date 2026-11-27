# Find-IT daily database backup (run by Windows Task Scheduler).
# Creates a validated, date-stamped backup and applies the retention policy.
# Output is appended to logs\backup-task.log; a non-zero exit code marks the task as failed.
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "logs") | Out-Null
$Log = Join-Path $ProjectDir "logs\backup-task.log"
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

"[$(Get-Date -Format s)] Starting daily backup" | Out-File -Append -Encoding utf8 $Log
& $Python manage.py backup_db --kind daily *>> $Log
$Code = $LASTEXITCODE
"[$(Get-Date -Format s)] Finished with exit code $Code" | Out-File -Append -Encoding utf8 $Log
exit $Code
