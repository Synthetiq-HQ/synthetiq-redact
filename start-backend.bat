@echo off
cd /d "%~dp0\backend"
call .\venv\Scripts\activate.bat
echo Starting Synthetiq Redact Backend v2 on http://127.0.0.1:8000
echo API Docs: http://127.0.0.1:8000/docs
uvicorn main_v2:app --host 127.0.0.1 --port 8000 --reload
