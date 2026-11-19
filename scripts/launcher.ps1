# Runtime preparation for the full checkout. Application lifetime is managed by
# the isolated Python supervisor, never by the user's parent shell.
$ErrorActionPreference='Stop'
function Invoke-FinPilotNative {
    param([string]$Executable,[string[]]$Arguments)
    $before=$ErrorActionPreference
    try {$ErrorActionPreference='Continue'; & $Executable @Arguments 2>&1 | ForEach-Object {Write-Host $_};$code=$LASTEXITCODE}
    finally {$ErrorActionPreference=$before}
    if($code -ne 0){throw "Command failed (exit $code): $Executable"}
}
function Get-FinPilotFullPaths {
    param([string]$ProjectRoot)
    $project=[IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $hash=[Security.Cryptography.SHA256]::Create()
    try {$id=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($project.ToLowerInvariant())))).Replace('-','').Substring(0,12).ToLowerInvariant()}
    finally {$hash.Dispose()}
    $cache=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) "FinPilot\runtimes\full-$id"
    return [PSCustomObject]@{Root=$cache;Python=(Join-Path $project '.venv\Scripts\python.exe');Desktop=(Join-Path $cache 'desktop');Node=(Join-Path $cache 'node');ProjectRoot=$project}
}
function Initialize-FinPilotFullRuntime {
    param([string]$ProjectRoot,[string]$Python='',[switch]$Install)
    $paths=Get-FinPilotFullPaths -ProjectRoot $ProjectRoot
    if($Python){$paths.Python=(Resolve-Path -LiteralPath $Python).ProviderPath}
    if(-not (Test-Path -LiteralPath $paths.Python -PathType Leaf)){
        $base=Get-Command py.exe -ErrorAction SilentlyContinue
        if($base){Invoke-FinPilotNative $base.Source @('-3','-m','venv',(Join-Path $paths.ProjectRoot '.venv'))}
        else {
            $base=Get-Command python.exe -ErrorAction SilentlyContinue
            if(-not $base -or $base.Source -match '\\WindowsApps\\'){throw 'Install Python 3.11 or newer, or pass -Python with an existing interpreter.'}
            Invoke-FinPilotNative $base.Source @('-m','venv',(Join-Path $paths.ProjectRoot '.venv'))
        }
    }
    & $paths.Python -I -c 'import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)' | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Python 3.11 or newer is required.'}
    $healthy=$false
    try { & $paths.Python -I (Join-Path $paths.ProjectRoot 'scripts\runtime_probe.py') core 2>$null | Out-Null;$healthy=$LASTEXITCODE -eq 0 }catch{}
    if($Install -or -not $healthy){Invoke-FinPilotNative $paths.Python @('-I','-m','pip','install','--disable-pip-version-check','-r',(Join-Path $paths.ProjectRoot 'requirements.txt'))}
    if(-not (Test-Path -LiteralPath (Join-Path $paths.ProjectRoot '.env'))){Copy-Item -LiteralPath (Join-Path $paths.ProjectRoot '.env.example') -Destination (Join-Path $paths.ProjectRoot '.env')}
    New-Item -ItemType Directory -Path $paths.Root -Force | Out-Null
    return $paths
}
function Initialize-FinPilotFullDesktop {
    param([string]$ProjectRoot,$Paths)
    $source=Join-Path $ProjectRoot 'desktop'
    $electron=Join-Path $source 'node_modules\electron\dist\electron.exe'
    $version=Join-Path $source 'node_modules\electron\dist\version'
    $expected=(Get-Content -LiteralPath (Join-Path $source 'package.json') -Raw -Encoding UTF8|ConvertFrom-Json).devDependencies.electron
    if((Test-Path -LiteralPath $electron) -and (Test-Path -LiteralPath $version) -and (Get-Content -LiteralPath $version -Raw).Trim().TrimStart('v') -eq $expected){
        return [PSCustomObject]@{Electron=$electron;Directory=$source;ProfileDirectory=(Join-Path $Paths.Root 'desktop\profile')}
    }
    . (Join-Path $ProjectRoot 'scripts\node-runtime.ps1')
    return Initialize-FinPilotDesktop -ProjectRoot $ProjectRoot -Paths $Paths
}
