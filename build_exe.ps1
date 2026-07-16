$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$iconPath = Join-Path $projectRoot "assets\sch_gantt_icon.ico"
$assetsPath = Join-Path $projectRoot "assets"
$entryPoint = Join-Path $projectRoot "sch_gantt_main.py"
$buildPath = Join-Path $projectRoot "build"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name ScheduleBoard `
    --specpath $buildPath `
    --icon $iconPath `
    --add-data "$assetsPath;assets" `
    $entryPoint

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

Write-Host "Built: $(Join-Path $projectRoot 'dist\ScheduleBoard\ScheduleBoard.exe')"
