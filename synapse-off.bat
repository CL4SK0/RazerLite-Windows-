@echo off
rem Arrete Synapse et passe ses services en demarrage manuel (reversible avec synapse-on.bat)
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-Process | Where-Object { $_.ProcessName -like 'Razer*' -or $_.ProcessName -like 'Rz*' } | Stop-Process -Force -ErrorAction SilentlyContinue;" ^
  "Get-Service | Where-Object { $_.DisplayName -like 'Razer*' -or $_.Name -like 'Rz*' } | ForEach-Object { Write-Host 'Arret :' $_.DisplayName; Stop-Service $_ -Force -ErrorAction SilentlyContinue; Set-Service $_.Name -StartupType Manual -ErrorAction SilentlyContinue }"
echo.
echo Synapse est arrete et ne se relancera plus tout seul au demarrage des services.
echo Pense aussi a decocher Synapse dans Gestionnaire des taches ^> Demarrage.
pause
