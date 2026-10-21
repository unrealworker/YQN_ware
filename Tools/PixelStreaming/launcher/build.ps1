param([string]$OutputRoot = '', [switch]$TestsOnly)
$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$projectRoot = [IO.Path]::GetFullPath((Join-Path $sourceRoot '../../..'))
if (-not $OutputRoot) { $OutputRoot = Join-Path $projectRoot 'Deployment/GHSPixelStreaming' }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$logRoot = Join-Path $OutputRoot 'logs'
New-Item -ItemType Directory -Path $OutputRoot,$logRoot -Force | Out-Null
$compilerPath = 'C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$references = @('/r:System.dll','/r:System.Core.dll','/r:System.Drawing.dll','/r:System.Windows.Forms.dll','/r:System.Web.Extensions.dll')
$resources = @('/resource:' + (Join-Path $sourceRoot 'Assets/warehouse-overview.png') + ',Ghs.PixelStreaming.warehouse-overview.png')
$sources = @(Get-ChildItem -LiteralPath $sourceRoot -Filter '*.cs' | ForEach-Object FullName)
$testExe = Join-Path $logRoot 'GHSLauncher.Tests.exe'
$buildLog = Join-Path $logRoot 'launcher-build.log'
& $compilerPath /nologo /utf8output /codepage:65001 /platform:x64 /optimize+ /target:exe /main:Ghs.PixelStreaming.TestProgram ('/out:' + $testExe) @references @resources @sources 2>&1 | Tee-Object -FilePath $buildLog
if ($LASTEXITCODE -ne 0) { throw "Test build failed: $LASTEXITCODE" }
Add-Content -LiteralPath $buildLog -Value ((Get-Date -Format o) + ' Test executable compiled successfully, exit 0.')
& $testExe (Join-Path $logRoot 'launcher-selftest.json') 2>&1 | Tee-Object -FilePath (Join-Path $logRoot 'launcher-selftest.log')
if ($LASTEXITCODE -ne 0) { throw "Launcher self-test failed: $LASTEXITCODE" }
if (-not $TestsOnly) {
    & $compilerPath /nologo /utf8output /codepage:65001 /platform:x64 /optimize+ /target:winexe /main:Ghs.PixelStreaming.Program ('/out:' + (Join-Path $OutputRoot '像素流服务启动器.exe')) @references @resources @sources 2>&1 | Tee-Object -FilePath $buildLog -Append
    if ($LASTEXITCODE -ne 0) { throw "Launcher build failed: $LASTEXITCODE" }
    Add-Content -LiteralPath $buildLog -Value ((Get-Date -Format o) + ' Windows launcher compiled successfully, exit 0.')
}
Write-Output "Launcher build and tests completed: $OutputRoot"
