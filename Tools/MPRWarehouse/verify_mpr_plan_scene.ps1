param([switch]$ResumeAfterImport)
$ErrorActionPreference = 'Stop'
$mprRoot = 'D:\UEPro\Test'
$mprEditor = 'D:\UE\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$mprJobs = @(
    @{ Name='import'; Script='import_mpr_reference_exterior.py'; Mode='editor'; Report='Saved/MPR/reference_v4_build.json' },
    @{ Name='reload'; Script='validate_mpr_reference_exterior.py'; Mode='capture'; Report='Saved/MPR/reference_v4/validation.json' },
    @{ Name='performance'; Script='profile_mpr_runtime.py'; Mode='game'; Report='Saved/MPR/performance.json' },
    @{ Name='runtime_views'; Script='capture_mpr_reference_runtime_views.py'; Mode='game'; Report='Saved/MPR/reference_v4/runtime_views/capture_report.json' },
    @{ Name='runtime_capture'; Script='capture_mpr_reference_game.py'; Mode='overscan'; Report='Saved/MPR/reference_v4/runtime_calibrated_capture.json' },
    @{ Name='plan_views'; Script='capture_mpr_plan_views.py'; Mode='game'; Report='Saved/MPR/road_v5/runtime_views/capture_report.json' }
)
$mprResults = @()
if ($ResumeAfterImport) {
    $mprJobs = @($mprJobs | Where-Object { $_.Name -ne 'import' })
    $mprResults = @(Get-Content -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/final_pipeline.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
    if ($mprResults.Count -ne 1 -or $mprResults[0].name -ne 'import' -or -not $mprResults[0].success) { throw 'No successful import to resume.' }
}
foreach ($mprJob in $mprJobs) {
    $mprActive = @(Get-Process UnrealEditor,blender -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited })
    if ($mprActive.Count -gt 0) { throw ('Another UE/Blender process is active: ' + ($mprActive.Id -join ',')) }
    $mprStarted = [DateTime]::UtcNow
    $mprArgs = @('D:\UEPro\Test\Test.uproject','/Game/Maps/MPR_CAD_Warehouse','-unattended','-NoSplash','-NoSound','-RenderOffscreen','-NoLiveCoding')
    $mprScript = 'D:/UEPro/Test/Tools/MPRWarehouse/' + $mprJob.Script
    if ($mprJob.Mode -eq 'editor') {
        $mprArgs += '-ExecutePythonScript=' + $mprScript
    } else {
        $mprArgs += '-ExecCmds="py ' + $mprScript + '"'
        if ($mprJob.Mode -eq 'capture') { $mprArgs += '-MPRReferenceCaptureQuit' }
        else {
            $mprArgs += @('-game','-ForceRes')
            if ($mprJob.Mode -eq 'overscan') { $mprArgs += @('-ResX=2006','-ResY=1860') }
            else { $mprArgs += @('-ResX=1920','-ResY=1080') }
            if ($mprJob.Name -eq 'performance') { $mprArgs += '-MPRProfile' }
        }
    }
    $mprArgs += '-abslog=D:/UEPro/Test/Saved/MPR/reference_v4_' + $mprJob.Name + '.log'
    $mprProcess = Start-Process -FilePath $mprEditor -ArgumentList $mprArgs -WorkingDirectory $mprRoot -WindowStyle Hidden -PassThru
    Write-Output ('START ' + $mprJob.Name + ' PID=' + $mprProcess.Id)
    while (-not $mprProcess.HasExited) {
        Start-Sleep -Seconds 1
        $mprProcess.Refresh()
        if (([DateTime]::UtcNow - $mprStarted).TotalMinutes -gt 8) { throw ('UE process deadline: ' + $mprJob.Name) }
    }
    if ($mprProcess.ExitCode -ne 0) { throw ('UE exit failed: ' + $mprJob.Name + ' ' + $mprProcess.ExitCode) }
    $mprProcess.Dispose()
    Start-Sleep -Seconds 2
    $mprReportPath = Join-Path $mprRoot $mprJob.Report
    $mprInfo = Get-Item -LiteralPath $mprReportPath
    if ($mprInfo.LastWriteTimeUtc -lt $mprStarted) { throw ('Stale report: ' + $mprJob.Name) }
    $mprReport = Get-Content -LiteralPath $mprReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $mprReport.success) { throw ('Report failed: ' + $mprJob.Name) }
    $mprResults += @{ name=$mprJob.Name; success=$true; elapsed_seconds=([DateTime]::UtcNow-$mprStarted).TotalSeconds; report=$mprJob.Report }
    $mprResults | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/final_pipeline.json') -Encoding UTF8
    Write-Output ('PASS ' + $mprJob.Name)
    if ($mprJob.Name -eq 'import') {
        & 'C:\Users\28109\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' (Join-Path $mprRoot 'Tools/MPRWarehouse/archive_mpr_plan_validation.py') --begin-run
        if ($LASTEXITCODE -ne 0) { throw 'Validation run snapshot failed' }
    }
}
Copy-Item -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4_build.json') -Destination (Join-Path $mprRoot 'SourceAssets/MPR/reference_v4/validation/import_report.json')
Copy-Item -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/validation.json') -Destination (Join-Path $mprRoot 'SourceAssets/MPR/reference_v4/validation/reload_validation.json')
Write-Output 'MPR_FINAL_PIPELINE_PASSED'
