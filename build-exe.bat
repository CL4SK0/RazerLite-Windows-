@echo off
rem Facultatif : fabrique dist\RazerLite.exe (plus besoin de Python ensuite)
cd /d "%~dp0"
where py >nul 2>&1 && (set PY=py -3) || (set PY=python)
%PY% -m pip install --user --upgrade pyinstaller -r requirements.txt
%PY% -c "from razerlite import logo; logo.save_ico('RazerLite.ico')"
%PY% -m PyInstaller --noconfirm --onefile --windowed --collect-data customtkinter --add-data "razerlite\assets;razerlite\assets" --icon RazerLite.ico --name RazerLite RazerLite.pyw
echo.
echo Fichier cree : %~dp0dist\RazerLite.exe
pause
