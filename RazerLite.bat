@echo off
rem Ouvre RazerLite sans fenetre console
cd /d "%~dp0"
where pyw >nul 2>&1 && (start "" pyw -3 RazerLite.pyw %*) || (start "" pythonw RazerLite.pyw %*)
