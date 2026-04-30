# Start Synthetiq Redact Backend (v2)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir\backend

# Activate venv and run
& .\venv\Scripts\Activate.ps1
Write-Host "Starting Synthetiq Redact Backend v2 on http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
uvicorn main_v2:app --host 127.0.0.1 --port 8000 --reload
