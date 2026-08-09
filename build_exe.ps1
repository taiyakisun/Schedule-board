$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$iconPath = Join-Path $projectRoot "assets\sch_gantt_icon.ico"
$assetsPath = Join-Path $projectRoot "assets"
$entryPoint = Join-Path $projectRoot "sch_gantt_main.py"
$buildPath = Join-Path $projectRoot "build"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

& $pythonPath -m PyInstaller `
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

$outputPath = Join-Path $projectRoot "dist\ScheduleBoard"
$dataFiles = @(
    "schedules.json",
    "schedules.json.bak",
    "schedules.json.tmp",
    "schedules.json.recovery.tmp",
    "completed_tasks.jsonl",
    "completed_tasks.jsonl.bak",
    "completed_tasks.jsonl.tmp",
    "completed_tasks.jsonl.recovery.tmp",
    "completed_tasks.jsonl.pending"
)
foreach ($fileName in $dataFiles) {
    $sourcePath = Join-Path $projectRoot $fileName
    if (Test-Path -LiteralPath $sourcePath) {
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $outputPath $fileName) -Force
    }
}

Write-Host "Built: $(Join-Path $outputPath 'ScheduleBoard.exe')"
