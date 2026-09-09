@echo off
cd /d "%~dp0"
echo Starting Bili Analyzer at http://127.0.0.1:8000
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
pause