@echo off
rem Double-click this file to start the Short Video Maker. Close this window to stop it.
cd /d "%~dp0"
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run app.py
pause
