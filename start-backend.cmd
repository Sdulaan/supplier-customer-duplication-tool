@echo off
rem Starts the API on port 8000. IFS_VERIFY_TLS=false because the IFS test host uses a self-signed certificate.
set IFS_VERIFY_TLS=false
cd /d "%~dp0"
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
