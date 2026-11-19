[CmdletBinding()]
param([ValidateRange(0,65535)][int]$Port=0,[string]$Python='',[switch]$Install,[switch]$Offline,[switch]$NoBrowser,[switch]$NoDesktop,[switch]$SetupOnly,[switch]$Stop)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath($PSScriptRoot)
. (Join-Path $projectRoot 'scripts\launcher.ps1')
$paths=Get-FinPilotFullPaths -ProjectRoot $projectRoot
$supervisor=Join-Path $projectRoot 'scripts\project_lifecycle.py'
$state=Join-Path $paths.Root 'project'
if($Stop){
    if($Python){$paths.Python=(Resolve-Path -LiteralPath $Python).ProviderPath}
    if(-not (Test-Path -LiteralPath $paths.Python)){Write-Host 'This project has no prepared runtime or running managed instance.';return}
    & $paths.Python -I $supervisor --project-root $projectRoot --runtime-dir $state --stop
    if($LASTEXITCODE -ne 0){throw 'The managed project did not stop correctly.'}
    return
}
$paths=Initialize-FinPilotFullRuntime -ProjectRoot $projectRoot -Python $Python -Install:$Install
if($SetupOnly){Write-Host 'Core runtime ready. No project or desktop window started.';return}
$arguments=@('-I',$supervisor,'--project-root',$projectRoot,'--python',$paths.Python,'--runtime-dir',$state,'--port',"$Port")
if($NoBrowser){$arguments+='--no-browser'}else{$arguments+='--browser-request'}
if($Offline){$arguments+='--offline'}
if($NoDesktop){$arguments+='--no-desktop'}
else {
    $desktop=Initialize-FinPilotFullDesktop -ProjectRoot $projectRoot -Paths $paths
    $arguments+=@('--electron',$desktop.Electron,'--desktop-dir',$desktop.Directory,'--electron-app',$desktop.Directory,'--profile-dir',$desktop.ProfileDirectory)
}
Write-Host 'Keep this launch window open. Ctrl+C, closing it, or -Stop ends the project and its assistant.'
. (Join-Path $projectRoot 'scripts\run-project.ps1')
$projectExitCode=Invoke-FinPilotProject -Python $paths.Python -Arguments $arguments
if($projectExitCode -ne 0){throw "Project stopped with exit code $projectExitCode"}
