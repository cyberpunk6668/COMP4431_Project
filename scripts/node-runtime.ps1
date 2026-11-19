# Optional Node bootstrap. Nothing is installed in the source checkout.
# Pinned official release: https://nodejs.org/en/blog/release/v24.12.0
function Get-FinPilotNodeSHA256 {
    param([Parameter(Mandatory=$true)][string]$LiteralPath)
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($LiteralPath)
    try { return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose(); $hash.Dispose() }
}

function Invoke-FinPilotDesktopCommand {
    param([Parameter(Mandatory=$true)][string]$Executable,[Parameter(Mandatory=$true)][string[]]$Arguments,
          [Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$Label)
    # Only file paths and fixed installer options are passed, never shell code.
    # Process redirection keeps npm warnings out of PowerShell 5.1's
    # terminating error stream while retaining the real process exit status.
    if (@($Arguments | Where-Object { $_.Contains('"') -or $_.Contains("`n") -or $_.Contains("`r") }).Count) { throw 'Unexpected quote or newline in installer argument.' }
    $tag = $Label + '-' + [Guid]::NewGuid().ToString('N')
    $stdout = Join-Path $Directory ($tag + '.stdout.log')
    $stderr = Join-Path $Directory ($tag + '.stderr.log')
    $quoted = @($Arguments | ForEach-Object { '"' + $_ + '"' })
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = $quoted -join ' '
    $info.WorkingDirectory = $Directory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        $null = $process.Start()
        @{pid=$process.Id;started_at_ticks=$process.StartTime.ToUniversalTime().Ticks;executable=$Executable;label=$Label} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Directory 'active-install-process.json') -Encoding UTF8
        $readOutput = $process.StandardOutput.ReadToEndAsync()
        $readError = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $readOutput.GetAwaiter().GetResult() | Set-Content -LiteralPath $stdout -Encoding UTF8
        $readError.GetAwaiter().GetResult() | Set-Content -LiteralPath $stderr -Encoding UTF8
        $exitCode = $process.ExitCode
    } finally { $process.Dispose() }
    foreach ($log in @($stdout,$stderr)) { if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log | ForEach-Object { Write-Host $_ } } }
    return $exitCode
}

function Test-FinPilotNode {
    param([string]$Executable)
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $null }
    try {
        $priorErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $reported = (& $Executable --version 2>$null | Out-String).Trim()
            $nodeExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $priorErrorAction }
        if ($nodeExitCode -ne 0 -or $reported -notmatch '^v(\d+\.\d+\.\d+)$') { return $null }
        if ([version]$Matches[1] -lt [version]'22.12.0') { return $null }
        $npmScript = Join-Path (Split-Path -Parent $Executable) 'node_modules\npm\bin\npm-cli.js'
        if (-not (Test-Path -LiteralPath $npmScript -PathType Leaf)) { return $null }
        try {
            $ErrorActionPreference = 'Continue'
            & $Executable $npmScript --version 2>$null | Out-Null
            $npmExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $priorErrorAction }
        if ($npmExitCode -ne 0) { return $null }
        return [PSCustomObject]@{ Node = $Executable; Npm = $npmScript; Version = $reported }
    } catch { return $null }
}

function Initialize-FinPilotNode {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)]$Paths, [switch]$ForcePortable)
    $nodeDirectory = [IO.Path]::GetFullPath($Paths.Node)
    if ($Paths.PSObject.Properties['ProjectRoot']) {
        $projectDirectory = [IO.Path]::GetFullPath($Paths.ProjectRoot).TrimEnd('\')
        if ($nodeDirectory -eq $projectDirectory -or $nodeDirectory.StartsWith($projectDirectory+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Node dependencies must be cached outside the lightweight source directory.' }
    }
    if (-not $ForcePortable) {
        $systemNode = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($systemNode) {
            $existing = Test-FinPilotNode $systemNode.Source
            if ($existing) { return $existing }
        }
    }
    $nodeVersion = '24.12.0'
    $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'The desktop companion requires 64-bit Windows.' }
    $archiveName = "node-v$nodeVersion-win-$architecture.zip"
    # These exact values are in the official release SHASUMS256.txt.
    $expected = @{
        x64 = '9c125f61ae947b52e779095830f9cac267846a043ef7192183c84016aaad2812'
        arm64 = 'b05e7e066f813d35ad3cd9c24eedaee074c012ac7e00071297608fdd2e948ae3'
    }[$architecture]
    New-Item -ItemType Directory -Path $nodeDirectory -Force | Out-Null
    $installLock = $null
    try {
        try { $installLock = [IO.File]::Open((Join-Path $nodeDirectory 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch { throw 'Another Node setup is running for this project. Wait for it to finish, then retry.' }
        $expanded = Join-Path $nodeDirectory "node-v$nodeVersion-win-$architecture"
        $portableNode = Join-Path $expanded 'node.exe'
        $readyPath = Join-Path $nodeDirectory "ready-v$nodeVersion-win-$architecture.json"
        $ready = $null
        try { $ready = Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
        if ($ready -and $ready.install_directory) {
            $recordedDirectory = [IO.Path]::GetFullPath($ready.install_directory)
            if (-not $recordedDirectory.StartsWith($nodeDirectory.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'The cached Node installation path escaped its runtime cache.' }
            $expanded = $recordedDirectory
            $portableNode = Join-Path $expanded 'node.exe'
        }
        $existing = Test-FinPilotNode $portableNode
        if ($existing -and $existing.Version -eq "v$nodeVersion" -and $ready -and $ready.sha256 -eq $expected) { return $existing }
        $base = "https://nodejs.org/dist/v$nodeVersion"
        Write-Host "Downloading optional Node.js $nodeVersion from nodejs.org..."
        $previousProtocol = [Net.ServicePointManager]::SecurityProtocol
        $previousProgress = $ProgressPreference
        $archive = Join-Path $nodeDirectory ([Guid]::NewGuid().ToString('N') + '.zip')
        try {
            [Net.ServicePointManager]::SecurityProtocol = $previousProtocol -bor [Net.SecurityProtocolType]::Tls12
            $ProgressPreference = 'SilentlyContinue'
            $published = (Invoke-WebRequest -Uri "$base/SHASUMS256.txt" -UseBasicParsing -TimeoutSec 60).Content
            if ($published -is [byte[]]) { $published = [Text.Encoding]::UTF8.GetString($published) }
            $line = @($published -split "`n" | Where-Object { $_.TrimEnd() -match ('^[a-f0-9]{64}\s+' + [regex]::Escape($archiveName) + '$') })
            if ($line.Count -ne 1 -or ($line[0] -split '\s+')[0] -ne $expected) { throw 'The official Node checksum did not match the pinned release.' }
            Invoke-WebRequest -Uri "$base/$archiveName" -OutFile $archive -UseBasicParsing -TimeoutSec 600
            if ((Get-FinPilotNodeSHA256 -LiteralPath $archive).ToLowerInvariant() -ne $expected) { throw 'Node download checksum mismatch. No downloaded code was executed.' }
            # A fresh extraction path prevents interrupted installation contents
            # being mistaken for a complete Node runtime. No PS Archive module
            # is needed, including under Windows PowerShell 5.1.
            $extraction = Join-Path $nodeDirectory ('install-' + [Guid]::NewGuid().ToString('N'))
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [IO.Compression.ZipFile]::ExtractToDirectory($archive,$extraction)
            $expanded = Join-Path $extraction "node-v$nodeVersion-win-$architecture"
            $portableNode = Join-Path $expanded 'node.exe'
        } finally {
            [Net.ServicePointManager]::SecurityProtocol = $previousProtocol
            $ProgressPreference = $previousProgress
            # Only the newly generated, checksum-checked download path is removed.
            if (Test-Path -LiteralPath $archive -PathType Leaf) { Remove-Item -LiteralPath $archive -Force }
        }
        $installed = Test-FinPilotNode $portableNode
        if (-not $installed -or $installed.Version -ne "v$nodeVersion") { throw 'The downloaded Node runtime did not pass its version and npm check.' }
        @{version=$nodeVersion;architecture=$architecture;sha256=$expected;install_directory=$expanded;completed_at=[DateTimeOffset]::UtcNow.ToString('o')} |
            ConvertTo-Json | Set-Content -LiteralPath $readyPath -Encoding UTF8
        return $installed
    } finally { if ($installLock) { $installLock.Dispose() } }
}

function Initialize-FinPilotDesktop {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$ProjectRoot, [Parameter(Mandatory=$true)]$Paths,
          [switch]$Install, [switch]$ForcePortableNode)
    $desktopDirectory = [IO.Path]::GetFullPath($Paths.Desktop)
    $sourceDirectory = Join-Path $ProjectRoot 'desktop'
    $projectDirectory = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $sourcePrefix = $projectDirectory + '\'
    if ($desktopDirectory -eq $projectDirectory -or $desktopDirectory.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Desktop dependencies must be cached outside the lightweight source directory.'
    }
    $node = Initialize-FinPilotNode -Paths $Paths -ForcePortable:$ForcePortableNode
    New-Item -ItemType Directory -Path $desktopDirectory -Force | Out-Null
    $setupLock = $null
    try {
        try { $setupLock = [IO.File]::Open((Join-Path $desktopDirectory 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch { throw 'Another desktop setup is running. Wait for it to finish, then retry.' }
        # A cancelled PowerShell launcher can leave its native installer alive.
        # Do not run npm ci over that install even after its file lock is gone.
        $active = $null
        try { $active = Get-Content -LiteralPath (Join-Path $desktopDirectory 'active-install-process.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
        if ($active) {
            $previousProcess = Get-Process -Id ([int]$active.pid) -ErrorAction SilentlyContinue
            if ($previousProcess -and $previousProcess.Path -eq $active.executable -and $previousProcess.StartTime.ToUniversalTime().Ticks -eq $active.started_at_ticks) {
                throw 'A previous desktop installer is still running. Wait for it to finish, then retry.'
            }
        }
        $sourceFiles = @('package.json','package-lock.json','main.cjs','preload.cjs','geometry.cjs','lifecycle.cjs','tray.png','README.md')
        $sourceHashes = @{}
        foreach ($name in $sourceFiles) {
            $source = Join-Path $sourceDirectory $name
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Desktop source missing: $name" }
            $sourceHashes[$name] = Get-FinPilotNodeSHA256 -LiteralPath $source
        }
        $packageHash = $sourceHashes['package.json']
        $lockHash = $sourceHashes['package-lock.json']
        foreach ($name in @('package.json','package-lock.json')) {
            $copied = Join-Path $desktopDirectory $name
            Copy-Item -LiteralPath (Join-Path $sourceDirectory $name) -Destination $copied -Force
            if ((Get-FinPilotNodeSHA256 -LiteralPath $copied) -ne $sourceHashes[$name]) { throw 'Desktop source changed during setup. Retry after saving your edits.' }
        }
        $fingerprint = "$packageHash`:$lockHash"
        $markerPath = Join-Path $desktopDirectory 'installed-dependencies.json'
        $marker = $null
        if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
            try { $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $marker = $null }
        }
        $electron = Join-Path $desktopDirectory 'node_modules\electron\dist\electron.exe'
        $expectedElectron = (Get-Content -LiteralPath (Join-Path $sourceDirectory 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json).devDependencies.electron
        $installedElectron = $null
        $installedPackage = Join-Path $desktopDirectory 'node_modules\electron\package.json'
        if (Test-Path -LiteralPath $installedPackage -PathType Leaf) {
            try { $installedElectron = (Get-Content -LiteralPath $installedPackage -Raw -Encoding UTF8 | ConvertFrom-Json).version } catch { $installedElectron = $null }
        }
        if ($Install -or -not $marker -or $marker.fingerprint -ne $fingerprint -or $installedElectron -ne $expectedElectron -or -not (Test-Path -LiteralPath $electron -PathType Leaf)) {
            Write-Host "Installing optional desktop dependencies into $desktopDirectory ..."
            $previousPath = $env:PATH
            $electronRunAsNode = $env:ELECTRON_RUN_AS_NODE
            $systemPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0'
            try {
                $env:PATH = (Split-Path -Parent $node.Node) + ';' + $systemPowerShell + ';' + $previousPath
                # Never let a parent's development setting change Electron installation.
                $env:ELECTRON_RUN_AS_NODE = $null
                Push-Location -LiteralPath $desktopDirectory
                try {
                    $npmExitCode = Invoke-FinPilotDesktopCommand -Executable $node.Node -Arguments @($node.Npm,'ci','--no-audit','--no-fund','--prefer-offline') -Directory $desktopDirectory -Label 'npm-ci'
                    if ($npmExitCode -ne 0) { throw 'Desktop dependency installation failed. Check network access and retry the launcher.' }
                    # Electron 45 no longer has an automatic postinstall hook.
                    # Run its pinned official installer explicitly; it verifies
                    # the downloaded binary against its bundled checksums.json.
                    $electronInstaller = Join-Path $desktopDirectory 'node_modules\electron\install.js'
                    $installedVersion = (Get-Content -LiteralPath $installedPackage -Raw -Encoding UTF8 | ConvertFrom-Json).version
                    if ($installedVersion -ne $expectedElectron -or -not (Test-Path -LiteralPath $electronInstaller -PathType Leaf)) { throw 'The installed Electron package did not match the source lockfile.' }
                    Write-Host 'Preparing the pinned Electron binary (first desktop launch only)...'
                    $installerOverrides = @{}
                    foreach ($name in @('ELECTRON_OVERRIDE_DIST_PATH','ELECTRON_INSTALL_PLATFORM','ELECTRON_INSTALL_ARCH','npm_config_platform','npm_config_arch','electron_use_remote_checksums','npm_config_electron_use_remote_checksums')) {
                        $installerOverrides[$name] = [Environment]::GetEnvironmentVariable($name,'Process')
                        [Environment]::SetEnvironmentVariable($name,$null,'Process')
                    }
                    try {
                        $electronExitCode = Invoke-FinPilotDesktopCommand -Executable $node.Node -Arguments @($electronInstaller) -Directory $desktopDirectory -Label 'electron-install'
                    } finally {
                        foreach ($name in $installerOverrides.Keys) { [Environment]::SetEnvironmentVariable($name,$installerOverrides[$name],'Process') }
                    }
                    if ($electronExitCode -ne 0) { throw 'Electron binary download or checksum verification failed. Check the network and retry.' }
                } finally { Pop-Location }
            } finally { $env:PATH = $previousPath; $env:ELECTRON_RUN_AS_NODE = $electronRunAsNode }
            if (-not (Test-Path -LiteralPath $electron -PathType Leaf)) { throw 'npm finished without the required Electron binary. Check installation scripts and retry.' }
            $binaryVersion = (Get-Content -LiteralPath (Join-Path $desktopDirectory 'node_modules\electron\dist\version') -Raw).Trim().TrimStart('v')
            $binaryPath = (Get-Content -LiteralPath (Join-Path $desktopDirectory 'node_modules\electron\path.txt') -Raw).Trim()
            if ($binaryVersion -ne $expectedElectron -or $binaryPath -ne 'electron.exe') { throw 'The Electron binary did not pass its installed version and entry-point check.' }
            [ordered]@{ fingerprint=$fingerprint; installed_at=[DateTimeOffset]::UtcNow.ToString('o'); node_version=$node.Version } |
                ConvertTo-Json | Set-Content -LiteralPath $markerPath -Encoding UTF8
        }
        # A running host must not see half of a later source update. Each launch
        # uses a verified immutable host snapshot; dependencies and preferences
        # remain shared in the external per-project cache.
        $hostDigest = [Security.Cryptography.SHA256]::Create()
        try { $hostId = ([BitConverter]::ToString($hostDigest.ComputeHash([Text.Encoding]::UTF8.GetBytes((($sourceFiles | ForEach-Object { $_ + ':' + $sourceHashes[$_] }) -join "`n"))))).Replace('-','').ToLowerInvariant() }
        finally { $hostDigest.Dispose() }
        $hosts = Join-Path $desktopDirectory 'hosts'
        New-Item -ItemType Directory -Path $hosts -Force | Out-Null
        $hostDirectory = Join-Path $hosts $hostId
        $snapshotValid = Test-Path -LiteralPath $hostDirectory -PathType Container
        if ($snapshotValid) {
            foreach ($name in $sourceFiles) {
                $existingFile = Join-Path $hostDirectory $name
                if (-not (Test-Path -LiteralPath $existingFile -PathType Leaf) -or (Get-FinPilotNodeSHA256 -LiteralPath $existingFile) -ne $sourceHashes[$name]) { $snapshotValid=$false;break }
            }
        }
        if (-not $snapshotValid) {
            if (Test-Path -LiteralPath $hostDirectory) { $hostDirectory = Join-Path $hosts ($hostId + '-' + [Guid]::NewGuid().ToString('N')) }
            $stage = Join-Path $hosts ('staging-' + [Guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $stage | Out-Null
            foreach ($name in $sourceFiles) {
                $copied = Join-Path $stage $name
                Copy-Item -LiteralPath (Join-Path $sourceDirectory $name) -Destination $copied
                if ((Get-FinPilotNodeSHA256 -LiteralPath $copied) -ne $sourceHashes[$name]) { throw 'Desktop source changed during setup. Retry after saving your edits.' }
            }
            $cachePrefix = $desktopDirectory.TrimEnd('\') + '\'
            if (-not [IO.Path]::GetFullPath($stage).StartsWith($cachePrefix,[StringComparison]::OrdinalIgnoreCase) -or -not [IO.Path]::GetFullPath($hostDirectory).StartsWith($cachePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Host snapshot escaped its runtime cache.' }
            Move-Item -LiteralPath $stage -Destination $hostDirectory
        }
        return [PSCustomObject]@{ Electron=$electron; Directory=$hostDirectory; DependencyDirectory=$desktopDirectory; ProfileDirectory=(Join-Path $desktopDirectory 'profile'); Node=$node.Node; Npm=$node.Npm; NodeVersion=$node.Version; SourceFingerprint=$hostId }
    } finally { if ($setupLock) { $setupLock.Dispose() } }
}
