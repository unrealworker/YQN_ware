param(
    [string[]]$Labels = @('Optimized01', 'Baseline02', 'Optimized02', 'Baseline03', 'Optimized03'),
    [int]$Duration = 90
)
$ErrorActionPreference = 'Stop'
$perfRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$perfOutput = Join-Path $perfRoot 'Saved/PerformanceP0P1'
$perfPython = 'C:/Users/28109/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
foreach ($perfLabel in $Labels) {
    if ($perfLabel -notmatch '^(Baseline|Optimized)[A-Za-z0-9_-]+$') { throw "Invalid run label: $perfLabel" }
    $perfVariant = if ($perfLabel.StartsWith('Baseline')) { 'BaselineBuild' } else { 'OptimizedBuild' }
    $perfExe = Join-Path $perfOutput "$perfVariant/Windows/Test/Binaries/Win64/TestGame.exe"
    if (!(Test-Path -LiteralPath $perfExe)) { throw "Missing packaged executable: $perfExe" }
    if (Get-Process -Name 'TestGame','UnrealEditor','UnrealEditor-Cmd','ShaderCompileWorker' -ErrorAction SilentlyContinue) {
        throw 'Close other UE/game/build processes before a timing capture.'
    }
    $perfLog = Join-Path $perfOutput "$perfLabel.log"
    $perfArgs = @('/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory', '-RenderOffscreen',
        '-Windowed', '-ForceRes', '-ResX=1920', '-ResY=1080', '-Unattended', '-NoVSync',
        "-TwinPerf=$perfLabel", "-TwinPerfDuration=$Duration", "-TwinPerfOutput=$perfOutput", "-abslog=$perfLog")
    $perfStart = [DateTime]::UtcNow
    Write-Output "Starting $perfLabel ($Duration seconds measured, plus warmup)"
    $perfProcess = Start-Process -FilePath $perfExe -ArgumentList $perfArgs -PassThru -WindowStyle Hidden
    $perfProcess.WaitForExit()
    if ($perfProcess.ExitCode -ne 0) { throw "$perfLabel exited with code $($perfProcess.ExitCode); inspect $perfLog" }
    $perfRun = Get-ChildItem -LiteralPath $perfOutput -Directory -Filter "$($perfLabel)_*" |
        Where-Object { $_.CreationTimeUtc -ge $perfStart.AddSeconds(-2) } |
        Sort-Object Name -Descending | Select-Object -First 1
    if (!$perfRun) { throw "No new result for $perfLabel" }
    $perfReport = Join-Path $perfRun.FullName 'run.json'
    & $perfPython -B (Join-Path $PSScriptRoot 'perf_analyze.py') summarize $perfReport |
        Set-Content -LiteralPath (Join-Path $perfOutput "$($perfLabel)_summary.log") -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Invalid performance evidence for $perfLabel" }
    $perfSummary = Get-Content -LiteralPath (Join-Path $perfRun.FullName 'summary.json') -Raw | ConvertFrom-Json
    $perfFrame = $perfSummary.capture.metrics.FrameTime
    $perfGame = $perfSummary.capture.metrics.GameThreadTime
    Write-Output "$perfLabel complete: frame mean=$($perfFrame.mean_ms)ms P99=$($perfFrame.p99_ms)ms; game mean=$($perfGame.mean_ms)ms"
}
