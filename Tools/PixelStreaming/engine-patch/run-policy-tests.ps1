param(
    [string]$VisualStudio = 'C:\Program Files\Microsoft Visual Studio\2022\Professional',
    [string]$CompilerVersion = '14.38.33130'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$outDir = Join-Path $PSScriptRoot '.test-output'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$includeDir = Join-Path $repo 'Plugins/PixelStreaming/Source/PixelStreaming/Private'
$source = Join-Path $PSScriptRoot 'policy-tests.cpp'
$obj = Join-Path $outDir 'policy-tests.obj'
$exe = Join-Path $outDir 'policy-tests.exe'
$vcvars = Join-Path $VisualStudio 'VC/Auxiliary/Build/vcvars64.bat'
if (-not (Test-Path -LiteralPath $vcvars)) { throw "Missing Visual C++ environment: $vcvars" }
# Paths are fixed tool/repository paths. This does not delete/move files or alter the engine.
$batch = Join-Path $outDir 'run-tests.cmd'
$commands = @(
    '@echo off',
    ('call "{0}" -vcvars_ver={1} >nul' -f $vcvars,$CompilerVersion),
    'if errorlevel 1 exit /b %errorlevel%',
    ('cl /nologo /std:c++17 /EHsc /W4 /WX /I"{0}" /Fo"{1}" /Fe"{2}" "{3}"' -f $includeDir,$obj,$exe,$source),
    'if errorlevel 1 exit /b %errorlevel%',
    ('"{0}"' -f $exe),
    'exit /b %errorlevel%'
)
Set-Content -LiteralPath $batch -Value $commands -Encoding ascii
& $env:ComSpec /d /c $batch
if ($LASTEXITCODE -ne 0) { throw "Pixel Streaming C++ policy test failed with exit code $LASTEXITCODE" }
