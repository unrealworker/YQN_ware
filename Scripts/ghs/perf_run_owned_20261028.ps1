param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_-]{1,64}$')][string]$Label,
    [ValidateSet('baseline','shadow-auto','shadow-off','traffic-off','traffic-hidden')][string]$Variant='baseline',
    [switch]$Trace,
    [switch]$DiagnosticTAA
)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$resultRoot=Join-Path $repoRoot 'Saved/Performance20261028'
$project=Join-Path $resultRoot 'IsolatedProject/Test.uproject'
$engine='D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe'
if (!(Test-Path -LiteralPath $project)) { throw 'Build the isolated diagnostic project first.' }
# Preserve the user's editor. Refuse only another process launched by this helper.
Get-ChildItem -LiteralPath $resultRoot -Filter 'launch-*.json' | ForEach-Object {
    $previous=Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    $running=Get-Process -Id $previous.pid -ErrorAction SilentlyContinue
    if ($running -and $running.ProcessName -eq 'UnrealEditor' -and $running.StartTime.ToUniversalTime().ToString('o') -eq $previous.processStartUtc) {
        throw "A recorded diagnostic process is still running: $($previous.pid)."
    }
}
$argsList=@($project,'/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory',
    '-game','-RenderOffscreen','-Windowed','-ForceRes','-ResX=1920','-ResY=1080',
    '-Unattended','-NoVSync',"-TwinPerf=$Label","-TwinPerfVariant=$Variant",
    '-TwinPerfWarmup=30','-TwinPerfDuration=90',"-TwinPerfOutput=$resultRoot",
    "-abslog=$resultRoot/$Label.log")
if($Trace){$argsList+='-TwinPerfTrace'}
if($DiagnosticTAA){$argsList+='-ExecCmds="r.AntiAliasingMethod 2"'}
$before=@(Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object Id,StartTime)
$p=Start-Process -FilePath $engine -ArgumentList $argsList -WindowStyle Hidden -PassThru
$manifest=[ordered]@{
    label=$Label; variant=$Variant; pid=$p.Id; processStartUtc=$p.StartTime.ToUniversalTime().ToString('o')
    project=$project; engine=$engine; arguments=$argsList; otherEditorProcesses=$before
    trace=[bool]$Trace; diagnosticTAA=[bool]$DiagnosticTAA
    backgroundCondition='user-editor-minimized-figma-static'
    note='Owned offscreen Development process; user editor preserved. No scene or configuration saves.'
    sourceMapSha256=(Get-FileHash (Join-Path $repoRoot 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap')).Hash
    testModuleSha256=(Get-FileHash (Join-Path $resultRoot 'IsolatedProject/Binaries/Win64/UnrealEditor-Test.dll')).Hash
    sourceCommit=(& git -C $repoRoot rev-parse HEAD)
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $resultRoot "launch-$Label.json") -Encoding utf8
[pscustomobject]$manifest | Select-Object label,variant,pid,trace,diagnosticTAA | ConvertTo-Json
