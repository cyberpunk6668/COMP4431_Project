$ErrorActionPreference = 'Stop'
$deckPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../FinPilot_English_Grouped/FinPilot_English_Grouped.pptx'))
$renderPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../FinPilot_English_Grouped/build/rendered'))
New-Item -ItemType Directory -Force -Path $renderPath | Out-Null
$existingPowerPoint = @(Get-Process POWERPNT -ErrorAction SilentlyContinue).Count
$pptApplication = $null
$ownedPresentation = $null
try {
    $pptApplication = New-Object -ComObject PowerPoint.Application
    $ownedPresentation = $pptApplication.Presentations.Open($deckPath, -1, 0, 0)
    for ($slideIndex = 1; $slideIndex -le $ownedPresentation.Slides.Count; $slideIndex++) {
        if ([int]$ownedPresentation.Slides.Item($slideIndex).SlideShowTransition.Hidden -ne 0) { throw ('Unexpected hidden slide ' + $slideIndex) }
        $ownedPresentation.Slides.Item($slideIndex).Export((Join-Path $renderPath ('slide-' + $slideIndex + '.png')), 'PNG', 1920, 1080)
    }
    Write-Output ('Exported ' + $ownedPresentation.Slides.Count + ' visible slides through PowerPoint document API.')
} finally {
    if ($null -ne $ownedPresentation) { $ownedPresentation.Close(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($ownedPresentation) }
    if ($null -ne $pptApplication) {
        if ($existingPowerPoint -eq 0 -and $pptApplication.Presentations.Count -eq 0) { $pptApplication.Quit() }
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($pptApplication)
    }
}
