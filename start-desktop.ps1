[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port = 8000,
    [string]$Python = '',
    [switch]$Development
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$baseUrl = "http://127.0.0.1:$Port"
function Test-FinPilot {
    try {
        $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 3
        if ($health.application -ne 'FinPilot') { throw 'wrong_service' }
        return $true
    } catch {
        if ($_.Exception.Message -eq 'wrong_service') { throw "Port $Port is not a FinPilot service. Choose another -Port; no process was stopped." }
        return $false
    }
}
if (-not (Test-FinPilot)) {
    $portListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($portListener) { throw "Port $Port is occupied. No process was stopped. Choose another -Port." }
    if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python environment missing. Follow README startup instructions first, or pass -Python with an existing interpreter.' }
    & $Python -c 'import fastapi,uvicorn,dotenv' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Python runtime dependencies are missing. Install requirements.txt in the selected environment first.' }
    $logDirectory = Join-Path $projectRoot 'tmp\desktop'
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory "$stamp.stdout.log") -RedirectStandardError (Join-Path $logDirectory "$stamp.stderr.log") | Out-Null
    $serverReady = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        if (Test-FinPilot) { $serverReady=$true; break }
    }
    if (-not $serverReady) { throw "The backend did not become ready. Inspect $logDirectory. No external process was stopped." }
}
$desktopRoot = Join-Path $projectRoot 'desktop'
$portable = Get-ChildItem -LiteralPath (Join-Path $desktopRoot 'artifacts') -Filter 'FinPilotPet-*-win-x64-portable.exe' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($portable -and -not $Development) {
    # This is the explicitly requested visible desktop UI. SW_HIDE can override
    # Electron's first showInactive() on Windows; only the Python helper is hidden.
    Start-Process -FilePath $portable.FullName -ArgumentList "--base-url=$baseUrl" -WorkingDirectory $projectRoot -WindowStyle Normal | Out-Null
} else {
    $electron = Join-Path $desktopRoot 'node_modules\electron\dist\electron.exe'
    if (-not (Test-Path -LiteralPath $electron)) { throw 'Desktop dependencies missing. Run npm ci in desktop/, then retry. A portable build can be generated with npm run dist.' }
    Start-Process -FilePath $electron -ArgumentList '.',"--base-url=$baseUrl" -WorkingDirectory $desktopRoot -WindowStyle Normal | Out-Null
}
Write-Host "FinPilot desktop companion: $baseUrl/pet"
Write-Host 'Quit the pet from its tray menu. The shared Python backend remains running.'
