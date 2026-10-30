@echo off
rem Double-click this file to start the Short Video Maker. Close this window to stop it.
cd /d "%~dp0"
rem Close an old copy of the app that is still running (it would keep showing old settings and code).
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run app.py
pause
