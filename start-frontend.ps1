# Start Synthetiq Redact Frontend
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir\frontend

Write-Host "Starting Synthetiq Redact Frontend on http://127.0.0.1:5173" -ForegroundColor Green
npm run dev
