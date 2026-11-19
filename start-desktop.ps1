[CmdletBinding()]
param([ValidateRange(0,65535)][int]$Port=0,[string]$Python='',[switch]$Development,[switch]$Offline,[switch]$SetupOnly)
$ErrorActionPreference='Stop'
if($SetupOnly){
    . (Join-Path $PSScriptRoot 'scripts\launcher.ps1')
    $paths=Initialize-FinPilotFullRuntime -ProjectRoot $PSScriptRoot -Python $Python
    $desktop=Initialize-FinPilotFullDesktop -ProjectRoot $PSScriptRoot -Paths $paths
    Write-Host "Desktop runtime ready: $($desktop.Electron)"
    return
}
& (Join-Path $PSScriptRoot 'start-finpilot.ps1') -Port $Port -Python $Python -NoBrowser -Offline:$Offline
