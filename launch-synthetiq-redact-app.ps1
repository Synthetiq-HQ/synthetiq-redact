$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$logDir = Join-Path $root "logs"
$frontendUrl = "http://127.0.0.1:5173"
$backendHealthUrl = "http://127.0.0.1:8000/health"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-LocalPort {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$connection
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

function Start-Frontend {
    if (Test-LocalPort 5173) { return }
    $outLog = Join-Path $logDir "frontend-app.out.log"
    $errLog = Join-Path $logDir "frontend-app.err.log"
    Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
        -WorkingDirectory $frontendDir `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden
}

function Start-Backend {
    if (Test-LocalPort 8000) { return }
    $outLog = Join-Path $logDir "backend-app.out.log"
    $errLog = Join-Path $logDir "backend-app.err.log"
    $python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }
    $command = @"
`$env:USE_GLM_GEOMETRY_REDACTION='1'
`$env:OLLAMA_HOST='http://127.0.0.1:11434'
`$env:GLM_OCR_MODEL='glm-ocr:latest'
Set-Location '$backendDir'
& '$python' -m uvicorn main_v2:app --host 127.0.0.1 --port 8000
"@
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden
}

function Open-AppWindow {
    $edgeCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")
    )
    $chromeCandidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
    )
    $browserExe = @($edgeCandidates + $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)

    if ($browserExe) {
        $profileDir = Join-Path $env:LOCALAPPDATA "SynthetiqRedact\AppWindowProfile"
        New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
        Start-Process -FilePath $browserExe[0] -ArgumentList @(
            "--app=$frontendUrl",
            "--window-size=1500,950",
            "--user-data-dir=$profileDir"
        )
    } else {
        Start-Process $frontendUrl
    }
}

# The frontend is intentionally launched first to match the desktop-app feel.
Start-Frontend
Start-Sleep -Seconds 1
Start-Backend

$frontendReady = Wait-HttpOk $frontendUrl 45
$backendReady = Wait-HttpOk $backendHealthUrl 60

if (-not $frontendReady -or -not $backendReady) {
    $message = "Synthetiq Redact is still starting. Frontend ready: $frontendReady. Backend ready: $backendReady. Logs are in $logDir."
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($message, "Synthetiq Redact", "OK", "Warning") | Out-Null
}

Open-AppWindow
