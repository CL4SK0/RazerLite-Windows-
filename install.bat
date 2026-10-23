@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Installation de RazerLite ===
where py >nul 2>&1 && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo Python est introuvable. Installe-le depuis https://www.python.org/downloads/
  echo en cochant "Add python.exe to PATH", puis relance ce fichier.
  pause
  exit /b 1
)
%PY% -m pip install --user --upgrade -r requirements.txt
if errorlevel 1 (
  echo L'installation des modules a echoue.
  pause
  exit /b 1
)
%PY% -c "from razerlite import logo; logo.save_ico('RazerLite.ico')"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\RazerLite.lnk');" ^
  "$s.TargetPath='%~dp0RazerLite.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.IconLocation='%~dp0RazerLite.ico'; $s.Save()"
echo.
echo Installe. Un raccourci RazerLite est sur le bureau.
echo Pense a fermer Synapse avant (synapse-off.bat).
pause
