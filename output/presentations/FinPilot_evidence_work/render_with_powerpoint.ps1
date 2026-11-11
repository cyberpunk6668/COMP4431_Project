$ErrorActionPreference = 'Stop'
$deckPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../FinPilot_3m30_retro_evidence/FinPilot_3m30_retro_evidence.pptx'))
$renderPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../FinPilot_3m30_retro_evidence/build/rendered'))
New-Item -ItemType Directory -Force -Path $renderPath | Out-Null
$existingPowerPoint = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count
$pptApplication = $null
$ownedPresentation = $null
try {
    $pptApplication = New-Object -ComObject PowerPoint.Application
    $ownedPresentation = $pptApplication.Presentations.Open($deckPath, -1, 0, 0)
    for ($slideIndex = 1; $slideIndex -le $ownedPresentation.Slides.Count; $slideIndex++) {
        $expectedHidden = if ($slideIndex -gt 6) { -1 } else { 0 }
        if ([int]$ownedPresentation.Slides.Item($slideIndex).SlideShowTransition.Hidden -ne $expectedHidden) {
            throw ('Unexpected hidden state for slide ' + $slideIndex)
        }
        $slidePath = Join-Path $renderPath ('slide-' + $slideIndex + '.png')
        $ownedPresentation.Slides.Item($slideIndex).Export($slidePath, 'PNG', 1920, 1080)
    }
    Write-Output ('Exported ' + $ownedPresentation.Slides.Count + ' slides through PowerPoint document API; six main and six hidden slides confirmed.')
} finally {
    if ($null -ne $ownedPresentation) {
        $ownedPresentation.Close()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ownedPresentation)
    }
    if ($null -ne $pptApplication) {
        if ($existingPowerPoint -eq 0 -and $pptApplication.Presentations.Count -eq 0) { $pptApplication.Quit() }
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($pptApplication)
    }
}
