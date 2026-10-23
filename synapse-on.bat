@echo off
rem Remet les services Razer en demarrage automatique
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-Service | Where-Object { $_.DisplayName -like 'Razer*' -or $_.Name -like 'Rz*' } | ForEach-Object { Write-Host 'Relance :' $_.DisplayName; Set-Service $_.Name -StartupType Automatic -ErrorAction SilentlyContinue; Start-Service $_ -ErrorAction SilentlyContinue }"
echo.
echo Services Razer reactives. Tu peux relancer Synapse.
pause
