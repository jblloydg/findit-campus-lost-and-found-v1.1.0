@echo off
rem Creates a "Find-IT" shortcut on your Desktop that runs FindIT.cmd.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Find-IT.lnk');" ^
  "$s.TargetPath = '%~dp0FindIT.cmd';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = 'shell32.dll,13';" ^
  "$s.Description = 'Start Find-IT v1.1.0';" ^
  "$s.Save()"
if errorlevel 1 (
  echo Could not create the shortcut.
) else (
  echo A "Find-IT" shortcut was added to your Desktop. Double-click it to start Find-IT.
)
pause
