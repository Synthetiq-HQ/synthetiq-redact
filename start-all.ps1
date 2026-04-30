# Start both Backend and Frontend for Synthetiq Redact
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start Backend in a new window
Write-Host "Launching Backend v2 on http://127.0.0.1:8000 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$scriptDir\backend'; .\venv\Scripts\Activate.ps1; uvicorn main_v2:app --host 127.0.0.1 --port 8000 --reload"

# Start Frontend in a new window
Write-Host "Launching Frontend on http://127.0.0.1:5173 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$scriptDir\frontend'; npm run dev"

Write-Host "" 
Write-Host "Both services are starting in separate windows!" -ForegroundColor Yellow
Write-Host "  Backend API:   http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  API Docs:      http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "  Frontend App:  http://127.0.0.1:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to close this launcher (services will keep running)..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
