# Run the session in the foreground, opening its browser from this parent shell
# so a new browser process never joins the supervisor's kill-on-close job.
function Invoke-FinPilotProject {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Python,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )
    $previousErrorAction=$ErrorActionPreference
    $projectExitCode=$null
    try {
        # Windows PowerShell 5 represents native stderr as ErrorRecord objects.
        # Keep reading those lines until the actual native process has exited.
        $ErrorActionPreference='Continue'
        & $Python @Arguments 2>&1 | ForEach-Object {
            $line=$_.ToString()
            if($line -cmatch '\AFINPILOT_BROWSER_URL=(http://127\.0\.0\.1:([1-9][0-9]{3,4})/)\z' -and [int]$Matches[2] -ge 1024 -and [int]$Matches[2] -le 65535){
                $browserUrl=$Matches[1]
                try {Start-Process -FilePath $browserUrl -ErrorAction Stop | Out-Null}
                catch {Write-Host "Open the project in your browser: $browserUrl"}
            }else{Write-Host $line}
        }
        $projectExitCode=$LASTEXITCODE
    }finally{$ErrorActionPreference=$previousErrorAction}
    if($null -eq $projectExitCode){throw 'The project supervisor did not return an exit code.'}
    return [int]$projectExitCode
}
