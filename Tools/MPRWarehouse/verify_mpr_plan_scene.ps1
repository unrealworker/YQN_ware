param([switch]$ResumeAfterImport, [ValidateSet('performance')][string]$ResumeFrom, [int[]]$IdleBlenderProcessIds = @())
$ErrorActionPreference = 'Stop'
$mprRoot = 'D:\UEPro\Test'
$mprEditor = 'D:\UE\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$mprJobs = @(
    @{ Name='import'; Script='import_mpr_reference_exterior.py'; Mode='editor'; Report='Saved/MPR/reference_v4_build.json' },
    @{ Name='reload'; Script='validate_mpr_reference_exterior.py'; Mode='capture'; Report='Saved/MPR/reference_v4/validation.json' },
    @{ Name='performance'; Script='profile_mpr_runtime.py'; Mode='game'; Report='Saved/MPR/performance.json' },
    @{ Name='runtime_views'; Script='capture_mpr_reference_runtime_views.py'; Mode='game'; Report='Saved/MPR/reference_v4/runtime_views/capture_report.json' },
    @{ Name='runtime_capture'; Script='capture_mpr_reference_game.py'; Mode='overscan'; Report='Saved/MPR/reference_v4/runtime_calibrated_capture.json' },
    @{ Name='plan_views'; Script='capture_mpr_plan_views.py'; Mode='game'; Report='Saved/MPR/road_v5/runtime_views/capture_report.json' },
    @{ Name='outside_views'; Script='capture_mpr_outside_views.py'; Mode='game'; Report='Saved/MPR/road_v5/outside_views/capture_report.json' },
    @{ Name='detail_views'; Script='capture_mpr_detail_views.py'; Mode='game'; Report='Saved/MPR/feedback_v7/detail_views/capture_report.json' },
    @{ Name='motion_final'; Script='capture_mpr_solar_motion.py'; Mode='game'; Report='Saved/MPR/solar_motion/final/capture_report.json' },
    @{ Name='motion_far'; Script='capture_mpr_solar_far.py'; Mode='game'; Report='Saved/MPR/solar_motion/far/capture_report.json' }
)
$mprResults = @()
if ($ResumeAfterImport -and $ResumeFrom) { throw 'Choose one resume mode.' }
if ($ResumeFrom) {
    $mprPrior = @(Get-Content -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/final_pipeline.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
    if ($mprPrior.Count -lt 2 -or $mprPrior[0].name -ne 'import' -or $mprPrior[1].name -ne 'reload' -or -not $mprPrior[0].success -or -not $mprPrior[1].success) { throw 'Successful import and reload are required.' }
    $mprContext = Get-Content -LiteralPath (Join-Path $mprRoot 'Saved/MPR/road_v5/validation_run_context.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ((Get-FileHash -LiteralPath (Join-Path $mprRoot 'Content/Maps/MPR_CAD_Warehouse.umap') -Algorithm SHA256).Hash.ToLower() -ne $mprContext.map_sha256) { throw 'Map changed after import.' }
    foreach ($mprSource in $mprContext.sources.PSObject.Properties) {
        if ((Get-FileHash -LiteralPath (Join-Path $mprRoot $mprSource.Name) -Algorithm SHA256).Hash.ToLower() -ne $mprSource.Value.sha256) { throw ('Source changed after import: ' + $mprSource.Name) }
    }
    Copy-Item -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/final_pipeline.json') -Destination (Join-Path $mprRoot ('Saved/MPR/reference_v4/pipeline_before_resume_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '.json'))
    $mprResults = @($mprPrior[0], $mprPrior[1])
    $mprJobs = @($mprJobs | Where-Object { $_.Name -notin @('import','reload') })
}
if ($ResumeAfterImport) {
    $mprJobs = @($mprJobs | Where-Object { $_.Name -ne 'import' })
    $mprResults = @(Get-Content -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/final_pipeline.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
    if ($mprResults.Count -ne 1 -or $mprResults[0].name -ne 'import' -or -not $mprResults[0].success) { throw 'No successful import to resume.' }
}
foreach ($mprJob in $mprJobs) {
    # Explicitly allow only a live Blender PID already inspected as idle with
    # no render job. Never close the user's unsaved interactive window.
    $mprActive = @(Get-Process UnrealEditor,blender -ErrorAction SilentlyContinue | Where-Object {
        -not $_.HasExited -and -not ($_.ProcessName -eq 'blender' -and $IdleBlenderProcessIds -contains $_.Id)
    })
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
            if ($mprJob.Name -eq 'motion_final') { $mprArgs += '-MPRMotionLabel=final' }
            if ($mprJob.Name -eq 'motion_far') { $mprArgs += '-MPRMotionLabel=far' }
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
    $mprResults += @{ name=$mprJob.Name; success=$true; elapsed_seconds=([DateTime]::UtcNow-$mprStarted).TotalSeconds; report=$mprJob.Report; inspected_idle_blender_pids=$IdleBlenderProcessIds }
    $mprResults | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/final_pipeline.json') -Encoding UTF8
    Write-Output ('PASS ' + $mprJob.Name)
    if ($mprJob.Name -eq 'import') {
        & 'C:\Users\28109\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' (Join-Path $mprRoot 'Tools/MPRWarehouse/archive_mpr_plan_validation.py') --begin-run
        if ($LASTEXITCODE -ne 0) { throw 'Validation run snapshot failed' }
    }
}
Copy-Item -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4_build.json') -Destination (Join-Path $mprRoot 'SourceAssets/MPR/reference_v4/validation/import_report.json')
Copy-Item -LiteralPath (Join-Path $mprRoot 'Saved/MPR/reference_v4/validation.json') -Destination (Join-Path $mprRoot 'SourceAssets/MPR/reference_v4/validation/reload_validation.json')
& 'C:\Users\28109\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' (Join-Path $mprRoot 'Tools/MPRWarehouse/review_mpr_solar_motion.py') --final-map (Join-Path $mprRoot 'Content/Maps/MPR_CAD_Warehouse.umap')
if ($LASTEXITCODE -ne 0) { throw 'Solar motion comparison failed' }
Write-Output 'MPR_FINAL_PIPELINE_PASSED'
