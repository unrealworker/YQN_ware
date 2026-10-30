[CmdletBinding()]
param(
    [string]$EngineRoot = '',
    [string]$CompilerVersion = '',
    [string]$ArchiveDirectory = '',
    [string]$BuildProjectFile = '',
    [ValidateSet('Development', 'Shipping')]
    [string]$Configuration = 'Development'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$ProjectFile = Join-Path $ProjectRoot 'Test.uproject'
if ($BuildProjectFile) { $ProjectFile = [IO.Path]::GetFullPath($BuildProjectFile) }
if (-not (Test-Path -LiteralPath $ProjectFile -PathType Leaf)) { throw "Project not found: $ProjectFile" }
if (-not $EngineRoot) {
    $Association = (Get-Content -LiteralPath $ProjectFile -Raw | ConvertFrom-Json).EngineAssociation
    if ($Association -notmatch '^5\.\d+$') { throw 'Specify -EngineRoot for a custom engine association.' }
    $EngineRoot = Join-Path 'D:\UE' "UE_$Association"
}
$Uat = Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat'
if (-not (Test-Path -LiteralPath $Uat)) { throw "UE AutomationTool not found: $Uat" }
if (-not $ArchiveDirectory) { $ArchiveDirectory = Join-Path $ProjectRoot 'Deployment/GHSPixelStreaming/App' }
$ArchiveDirectory = [IO.Path]::GetFullPath($ArchiveDirectory)
$LogDirectory = Join-Path $ProjectRoot 'Saved/PixelStreaming/Packaging'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDirectory "package-$Stamp.log"
$ResultFile = Join-Path $LogDirectory "package-$Stamp.result.json"
$Map = '/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory'
$UatArguments = @(
    'BuildCookRun', "-project=$ProjectFile", '-noP4', '-platform=Win64',
    '-target=TestGame', "-clientconfig=$Configuration", '-nocompileeditor',
    '-build', '-cook', '-stage', '-pak', '-iostore', '-archive', '-prereqs',
    '-nodebuginfo', "-archivedirectory=$ArchiveDirectory", "-map=$Map",
    '-unattended', '-utf8output'
)
if ($CompilerVersion) { $UatArguments += "-ubtargs=-CompilerVersion=$CompilerVersion" }
$StartedAt = (Get-Date).ToString('o')
$MapFile = Join-Path (Split-Path -Parent $ProjectFile) 'Content/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory.umap'
$MapHash = (Get-FileHash -LiteralPath $MapFile -Algorithm SHA256).Hash
& $Uat @UatArguments 2>&1 | Tee-Object -FilePath $LogFile
$PackageExitCode = $LASTEXITCODE
$Executable = Join-Path $ArchiveDirectory 'Windows/TestGame.exe'
$RuntimeExecutable = Join-Path $ArchiveDirectory "Windows/Test/Binaries/Win64/TestGame$(@{'Development'='';'Shipping'='-Win64-Shipping'}[$Configuration]).exe"
[ordered]@{
    startedAt = $StartedAt
    finishedAt = (Get-Date).ToString('o')
    exitCode = $PackageExitCode
    project = $ProjectFile
    engineRoot = $EngineRoot
    compilerOverride = $CompilerVersion
    configuration = $Configuration
    map = $Map
    mapSha256 = $MapHash
    mapUnchanged = $MapHash -eq (Get-FileHash -LiteralPath $MapFile -Algorithm SHA256).Hash
    executable = $Executable
    runtimeExecutable = $RuntimeExecutable
    executableExists = Test-Path -LiteralPath $Executable
    log = $LogFile
    arguments = $UatArguments
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultFile -Encoding UTF8
Write-Output "Package result: $ResultFile"
if ($PackageExitCode -ne 0) { exit $PackageExitCode }
if (-not (Test-Path -LiteralPath $Executable)) { throw "UAT returned success but executable is missing: $Executable" }
Write-Output "Packaged executable: $Executable"
