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
$expectedContract = 'options-demo.v2'
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
        $recordedTicks = $record.started_at_ticks
        if (-not $recordedTicks) { $recordedTicks = ([DateTime]$record.started_at).ToUniversalTime().Ticks }
        if ($serverProcess.StartTime.ToUniversalTime().Ticks -ne $recordedTicks) { return $null }
        if ([IO.Path]::GetFullPath($serverProcess.Path) -ne $record.python_path) { return $null }
        return [PSCustomObject]@{ Process = $serverProcess; Record = $record }
    } catch { return $null }
}

function Get-OwnedUvicornChildren($parentProcess) {
    # Windows venv python.exe may be a redirector. Its real Python child owns
    # the listening socket; stopping only the redirector leaves an orphan.
    $expectedArguments = '(?i)-m\s+uvicorn\s+app\.main:app\s+--host\s+127\.0\.0\.1\s+--port\s+' + $Port + '(?:\s|$)'
    return @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($parentProcess.Id)" | Where-Object {
        $_.CommandLine -match $expectedArguments -and $_.Name -match '^python(?:w)?\.exe$'
    })
}

function Get-BackendSignature {
    # Static files are read on demand, but Python code remains in memory.
    # A source update must restart an owned server even if its API is compatible.
    $backendDirectory = Join-Path $projectRoot 'app'
    $sources = @(Get-ChildItem -LiteralPath $backendDirectory -Filter '*.py' -File -Recurse | Sort-Object FullName)
    $entries = @($sources | ForEach-Object {
        $_.FullName.Substring($projectRoot.Length).Replace('\', '/') + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    })
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($entries -join "`n"))))).Replace('-', '').ToLowerInvariant()
    } finally { $hasher.Dispose() }
}

function Test-ScenarioReady {
    try {
        $metadata = Invoke-RestMethod -Uri "$baseUrl/api/options-demo/scenario?language=en" -TimeoutSec 1
        return ($metadata.api_contract -eq $expectedContract -and
                $metadata.language -eq 'en' -and
                'en' -in $metadata.supported_languages -and
                'zh' -in $metadata.supported_languages -and
                $metadata.display_catalogue.frames.Count -eq 2 -and
                $metadata.scenario.id -eq $expectedScenario -and
                $metadata.source_kind -eq 'synthetic_replay' -and
                $metadata.gateway_connected -eq $false)
    } catch { return $false }
}

function Stop-OwnedServer($owned) {
    $verified = Read-OwnedServer
    if (-not $verified -or $verified.Process.Id -ne $owned.Process.Id -or
        $verified.Process.StartTime.ToUniversalTime().Ticks -ne $owned.Process.StartTime.ToUniversalTime().Ticks) {
        throw 'The owned process changed. No process was stopped.'
    }
    foreach ($child in @(Get-OwnedUvicornChildren $owned.Process)) {
        # A venv redirector and its exact uvicorn child belong to this launch.
        $childProcess = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        if ($childProcess -and $childProcess.Path -eq $child.ExecutablePath -and
            [Math]::Abs(($childProcess.StartTime.ToUniversalTime() - $child.CreationDate.ToUniversalTime()).TotalMilliseconds) -lt 1) {
            $childTicks = $childProcess.StartTime.ToUniversalTime().Ticks
            Stop-Process -Id $childProcess.Id -ErrorAction SilentlyContinue
            $childProcess.WaitForExit(2000) | Out-Null
            $remainingChild = Get-Process -Id $childProcess.Id -ErrorAction SilentlyContinue
            if ($remainingChild -and $remainingChild.StartTime.ToUniversalTime().Ticks -eq $childTicks) {
                throw 'Could not stop the owned uvicorn child. Its process record was retained.'
            }
        }
    }
    $remainingParent = Get-Process -Id $owned.Process.Id -ErrorAction SilentlyContinue
    if ($remainingParent -and $remainingParent.StartTime.ToUniversalTime().Ticks -eq $owned.Process.StartTime.ToUniversalTime().Ticks) {
        $parentTicks = $remainingParent.StartTime.ToUniversalTime().Ticks
        Stop-Process -Id $remainingParent.Id -ErrorAction SilentlyContinue
        $remainingParent.WaitForExit(2000) | Out-Null
        $stillRunning = Get-Process -Id $remainingParent.Id -ErrorAction SilentlyContinue
        if ($stillRunning -and $stillRunning.StartTime.ToUniversalTime().Ticks -eq $parentTicks) {
            throw 'Could not stop the owned Python launcher. Its process record was retained.'
        }
    }
    Remove-Item -LiteralPath $statePath -Force
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
        Stop-OwnedServer $owned
        Write-Host "Stopped this project's options-demo process on port $Port."
        return
    }

    if ($owned) {
        if ([bool]$owned.Record.offline -ne [bool]$Offline) {
            throw "The demo is already running with different -Offline settings. Run this script with -Port $Port -Stop, then launch again."
        }
        if ($owned.Record.source_signature -ne (Get-BackendSignature) -or -not (Test-ScenarioReady)) {
            Write-Host "Updating this project's outdated options service on port $Port."
            Stop-OwnedServer $owned
            $owned = $null
        }
    }
    if ($owned) {
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
        $sourceSignature = Get-BackendSignature
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
            started_at_ticks = $serverProcess.StartTime.ToUniversalTime().Ticks
            offline = [bool]$Offline
            source_signature = $sourceSignature
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
    Write-Host "To stop from the project directory: .\start-options-demo.cmd -Port $Port -Stop"
    if (-not $NoBrowser) { Start-Process -FilePath "$baseUrl/options-demo" | Out-Null }
} finally {
    if ($launcherLock) { $launcherLock.Dispose() }
}
