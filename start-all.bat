@echo off
cd /d "%~dp0"

echo Launching Backend v2 on http://127.0.0.1:8000 ...
start "Synthetiq Backend" cmd /k "cd backend && .\venv\Scripts\activate.bat && uvicorn main_v2:app --host 127.0.0.1 --port 8000 --reload"

echo Launching Frontend on http://127.0.0.1:5173 ...
start "Synthetiq Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both services are starting in separate windows!
echo   Backend API:   http://127.0.0.1:8000
echo   API Docs:      http://127.0.0.1:8000/docs
echo   Frontend App:  http://127.0.0.1:5173
echo.
pause
