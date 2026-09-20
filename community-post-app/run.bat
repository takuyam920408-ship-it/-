@echo off
REM Windows 用。ダブルクリックで起動
cd /d "%~dp0"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
