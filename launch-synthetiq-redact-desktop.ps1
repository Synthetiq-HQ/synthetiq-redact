$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$stableAppExe = "C:\Users\INTERPOL\Tools\SynthetiqRedact\synthetiq-redact-v3.1-startup-preview-fix.exe"
$legacyStableAppExe = "C:\Users\INTERPOL\Tools\SynthetiqRedact\synthetiq-redact.exe"
$appExe = if (Test-Path $stableAppExe) {
    $stableAppExe
} elseif (Test-Path $legacyStableAppExe) {
    $legacyStableAppExe
} else {
    Join-Path $root "frontend\src-tauri\target\release\synthetiq-redact.exe"
}
$logDir = Join-Path $root "logs"
$port = 8765
$healthUrl = "http://127.0.0.1:$port/health"
$mutex = New-Object System.Threading.Mutex($false, "Global\SynthetiqRedactDesktopLauncher")
$hasLock = $false

try {
    $hasLock = $mutex.WaitOne(0)
    if (-not $hasLock) {
        # Another double-click is already starting the app. Do not spawn duplicates.
        exit 0
    }

    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $launcherLog = Join-Path $logDir "desktop-launcher.log"

    function Write-LauncherLog {
        param([string]$Message)
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $launcherLog -Value "[$stamp] $Message"
    }

function Get-PortOwner {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

function Test-Health {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        return ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Start-RedactBackend {
    if (Test-Health) { return $null }

    $owner = Get-PortOwner
    if ($owner) {
        try {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
            if ($proc.CommandLine -match "main_v2:app|synthetiq-redact|uvicorn") {
                Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
        } catch {}
    }

    $python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }

    $outLog = Join-Path $logDir "desktop-backend.out.log"
    $errLog = Join-Path $logDir "desktop-backend.err.log"
    $command = @"
`$env:USE_GLM_GEOMETRY_REDACTION='1'
`$env:ALLOW_OCR_GEOMETRY_FALLBACK='0'
`$env:OLLAMA_HOST='http://127.0.0.1:11434'
`$env:GLM_OCR_MODEL='glm-ocr:latest'
Set-Location '$backendDir'
& '$python' -m uvicorn main_v2:app --host 127.0.0.1 --port $port
"@

    return Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
}

function Wait-ForHealth {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if (Test-Health) { return $true }
        Start-Sleep -Milliseconds 750
    }
    return $false
}

    if (-not (Test-Path $appExe)) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("Synthetiq Redact desktop app was not found: $appExe", "Synthetiq Redact", "OK", "Error") | Out-Null
        exit 1
    }

    Write-LauncherLog "Launch requested."
    $existingApp = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "synthetiq-redact*" } |
        Select-Object -First 1
    if ($existingApp) {
        Write-LauncherLog "App is already running."
        exit 0
    }

    $backendProcess = Start-RedactBackend
    $env:SYNTHETIQ_BACKEND_MANAGED = "1"
    Write-LauncherLog "Opening app while backend starts."
    $appProcess = Start-Process -FilePath $appExe -WorkingDirectory (Split-Path $appExe) -PassThru
    Wait-Process -Id $appProcess.Id
    Write-LauncherLog "App closed. Stopping backend."

    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    $owner = Get-PortOwner
    if ($owner) {
        try {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
            if ($proc.CommandLine -match "main_v2:app|uvicorn") {
                Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
} finally {
    if ($hasLock) {
        $mutex.ReleaseMutex() | Out-Null
    }
    $mutex.Dispose()
}
