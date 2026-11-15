[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port = 8018,
    [string]$Python = '',
    [switch]$Offline,
    [switch]$NoBrowser,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$baseUrl = "http://127.0.0.1:$Port"
$expectedScenario = 'options-gateway-replay-v1'
$runtimeDirectory = Join-Path $projectRoot 'tmp\options-demo'
$logDirectory = Join-Path $projectRoot 'output\options-demo'
$statePath = Join-Path $runtimeDirectory "server-$Port.json"
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null

function Read-OwnedServer {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return $null }
    try {
        $record = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($record.project_root -ne $projectRoot -or $record.port -ne $Port) { return $null }
        $serverProcess = Get-Process -Id ([int]$record.pid) -ErrorAction Stop
        if ($serverProcess.StartTime.ToUniversalTime().ToString('o') -ne $record.started_at) { return $null }
        if ([IO.Path]::GetFullPath($serverProcess.Path) -ne $record.python_path) { return $null }
        return [PSCustomObject]@{ Process = $serverProcess; Record = $record }
    } catch { return $null }
}

function Test-ScenarioReady {
    try {
        $metadata = Invoke-RestMethod -Uri "$baseUrl/api/options-demo/scenario" -TimeoutSec 1
        return ($metadata.scenario.id -eq $expectedScenario -and
                $metadata.source_kind -eq 'synthetic_replay' -and
                $metadata.gateway_connected -eq $false)
    } catch { return $false }
}

# Serialize repeated double-clicks; this file is a local lock, not a process ID.
$launcherLock = $null
try {
    try {
        $launcherLock = [IO.File]::Open((Join-Path $runtimeDirectory "launcher-$Port.lock"), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw "Another options-demo launcher is running for port $Port. Wait a moment, then retry." }

    $owned = Read-OwnedServer
    if ($Stop) {
        if (-not $owned) { throw "No owned demo process was found for port $Port. No process was stopped." }
        Stop-Process -Id $owned.Process.Id -ErrorAction Stop
        Remove-Item -LiteralPath $statePath -Force
        Write-Host "Stopped this project's options-demo process on port $Port."
        return
    }

    if ($owned) {
        if ([bool]$owned.Record.offline -ne [bool]$Offline) {
            throw "The demo is already running with different -Offline settings. Run this script with -Port $Port -Stop, then launch again."
        }
        if (-not (Test-ScenarioReady)) {
            throw "The owned demo is not ready or uses an older build. Run this script with -Port $Port -Stop, then retry. Logs: $logDirectory"
        }
        Write-Host "Reusing this project's existing options demo: $baseUrl/options-demo"
    } else {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        if ($listener) {
            throw "Port $Port is occupied by a service that this launcher does not own. No process was stopped. Choose another -Port (for example 8019)."
        }
        if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
        $Python = [IO.Path]::GetFullPath($Python)
        if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
            throw "Python environment missing. Follow README setup first, or use -Python with an existing interpreter. Expected: $Python"
        }
        & $Python -c 'import fastapi,uvicorn,dotenv,httpx' 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Runtime dependencies are missing. Install requirements.txt in the selected Python environment, then retry.' }

        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
        $stdoutPath = Join-Path $logDirectory "$stamp-$Port.stdout.log"
        $stderrPath = Join-Path $logDirectory "$stamp-$Port.stderr.log"
        # Child-only overrides: preserve the caller's environment and .env file.
        $environmentBefore = @{}
        foreach ($name in @('FINPILOT_DB', 'IBKR_ENABLED', 'FINPILOT_OFFLINE')) {
            $environmentBefore[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        }
        try {
            [Environment]::SetEnvironmentVariable('FINPILOT_DB', (Join-Path $runtimeDirectory 'demo.sqlite3'), 'Process')
            [Environment]::SetEnvironmentVariable('IBKR_ENABLED', 'false', 'Process')
            if ($Offline) { [Environment]::SetEnvironmentVariable('FINPILOT_OFFLINE', 'true', 'Process') }
            $serverProcess = Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
        } finally {
            foreach ($name in $environmentBefore.Keys) {
                [Environment]::SetEnvironmentVariable($name, $environmentBefore[$name], 'Process')
            }
        }
        $record = [ordered]@{
            project_root = $projectRoot
            port = $Port
            pid = $serverProcess.Id
            python_path = $Python
            started_at = $serverProcess.StartTime.ToUniversalTime().ToString('o')
            offline = [bool]$Offline
            stdout = $stdoutPath
            stderr = $stderrPath
        }
        $record | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $ready = $false
        while ($timer.Elapsed.TotalSeconds -lt 12) {
            if ($serverProcess.HasExited) { break }
            if (Test-ScenarioReady) { $ready = $true; break }
            Start-Sleep -Milliseconds 200
            $serverProcess.Refresh()
        }
        if (-not $ready) {
            throw "The options demo did not become ready. Inspect $stderrPath. If the process remains running, use -Port $Port -Stop before retrying. No unrelated process was stopped."
        }
        Write-Host "Started isolated options demo: $baseUrl/options-demo"
    }
    Write-Host 'Source: synthetic gateway replay, never real-time market data. Actual IBKR access is disabled in this demo process.'
    if ($Offline) { Write-Host 'Offline rehearsal: local rule explanations; no model API requests.' }
    else { Write-Host 'Model mode follows .env. Explicit demo actions may call DeepSeek when configured; opening the page does not call a model.' }
    Write-Host "Logs: $logDirectory"
    Write-Host "To stop: powershell -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $projectRoot 'start-options-demo.ps1')`" -Port $Port -Stop"
    if (-not $NoBrowser) { Start-Process -FilePath "$baseUrl/options-demo" | Out-Null }
} finally {
    if ($launcherLock) { $launcherLock.Dispose() }
}
