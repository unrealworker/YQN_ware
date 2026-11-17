[CmdletBinding()]
param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$installer = Join-Path $PSScriptRoot 'Apply-WarehousePatch.ps1'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))) ('Saved/Packaging/Versioning/InstallerTests-' + [guid]::NewGuid().ToString('N'))
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a new, empty test output directory' }
$null = New-Item -ItemType Directory -Path $OutputDirectory
$testRoot = (Resolve-Path -LiteralPath $OutputDirectory).Path
$results = New-Object 'System.Collections.Generic.List[string]'

function Write-FixtureFile([string]$Root, [string]$Relative, [string]$Content) {
    $path = Join-Path $Root $Relative
    $null = New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($path)) -Force
    [IO.File]::WriteAllText($path, $Content, (New-Object Text.UTF8Encoding($false)))
}
function File-Entry([string]$Root, [string]$Relative) {
    $path = Join-Path $Root $Relative
    return [ordered]@{ path=$Relative; size=(Get-Item -LiteralPath $path).Length; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
}
function Assert-True([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Assert-Rejected([scriptblock]$Action, [string]$Name) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-True $rejected "Expected rejection: $Name"
    $results.Add($Name)
}
function New-Fixture([string]$Name) {
    $root = Join-Path $testRoot $Name
    $install = Join-Path $root 'install'
    $patch = Join-Path $root 'patch'
    $paths = @('TestGame.exe', 'Test/Binaries/Win64/TestGame-Win64-Shipping.exe',
        'Test/Content/Paks/Test-Windows.pak', 'Test/Content/Paks/Test-Windows.utoc', 'Test/Content/Paks/Test-Windows.ucas',
        'Test/Content/GHSTwinUI/web/index.html')
    foreach ($relative in $paths) { Write-FixtureFile $install $relative ('baseline:' + $relative) }
    $baseFiles = @($paths | ForEach-Object { File-Entry $install $_ })
    $payloadPaths = @('Test/Content/GHSTwinUI/web/index.html', 'Test/Content/Paks/Test-Windows_0_P.pak',
        'Test/Content/Paks/Test-Windows_0_P.utoc', 'Test/Content/Paks/Test-Windows_0_P.ucas')
    foreach ($relative in $payloadPaths) { Write-FixtureFile (Join-Path $patch 'payload') $relative ('patch one:' + $relative) }
    $manifest = [ordered]@{ schemaVersion=1; kind='cumulative-patch'; project='Test'; baseVersion='1.0.0'; version='1.0.1';
        engineVersion='5.8.4'; sourceCommit='0000000000000000000000000000000000000001';
        baseFiles=$baseFiles; files=@($payloadPaths | ForEach-Object { File-Entry (Join-Path $patch 'payload') $_ }) }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $patch 'patch.json') -Encoding UTF8
    return @{ install=$install; patch=$patch; manifest=$manifest; paths=$paths }
}
function Assert-Baseline($Fixture) {
    foreach ($entry in $Fixture.manifest.baseFiles) {
        Assert-True ((Get-FileHash -LiteralPath (Join-Path $Fixture.install $entry.path) -Algorithm SHA256).Hash -eq $entry.sha256) ('Baseline differs: ' + $entry.path)
    }
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $Fixture.install 'Test/Content/Paks/Test-Windows_0_P.pak'))) 'Overlay remains after rollback/rejection'
}

# These fixtures are inert text files, never real executables or deployment paths.
$fixture = New-Fixture 'normal'
& $installer -PatchDirectory $fixture.patch -InstallDirectory $fixture.install -CheckOnly | Out-Null
Assert-True (-not (Test-Path -LiteralPath (Join-Path $fixture.install '.warehouse-patch'))) 'CheckOnly mutated the installation'
$results.Add('CheckOnly leaves installation unchanged')
& $installer -PatchDirectory $fixture.patch -InstallDirectory $fixture.install | Out-Null
$state = Get-Content -LiteralPath (Join-Path $fixture.install '.warehouse-patch/installed.json') -Raw | ConvertFrom-Json
Assert-True ($state.version -eq '1.0.1') 'First install version differs'
Assert-True ((Get-Content -LiteralPath (Join-Path $fixture.install 'Test/Content/GHSTwinUI/web/index.html') -Raw) -match '^patch one:') 'First patch did not replace loose UI'
$results.Add('First patch installs overlay and loose UI')
Assert-Rejected { & $installer -PatchDirectory $fixture.patch -InstallDirectory $fixture.install } 'Repeated version is rejected'

# Next cumulative patch changes the container and lets the UI return to baseline.
# It intentionally omits index.html; the installer must restore its original bytes.
$next = Join-Path $testRoot 'normal/patch-two'
$newRelative = 'Test/Content/Paks/Test-Windows_0_P.pak'
Write-FixtureFile (Join-Path $next 'payload') $newRelative 'patch two container'
$nextManifest = [ordered]@{ schemaVersion=1; kind='cumulative-patch'; project='Test'; baseVersion='1.0.0'; version='1.0.2';
    engineVersion='5.8.4'; sourceCommit='0000000000000000000000000000000000000002'; baseFiles=$fixture.manifest.baseFiles;
    files=@((File-Entry (Join-Path $next 'payload') $newRelative)) }
$nextManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $next 'patch.json') -Encoding UTF8
& $installer -PatchDirectory $next -InstallDirectory $fixture.install | Out-Null
Assert-True ((Get-Content -LiteralPath (Join-Path $fixture.install 'Test/Content/GHSTwinUI/web/index.html') -Raw) -match '^baseline:') 'Cumulative update did not restore baseline UI'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $fixture.install 'Test/Content/Paks/Test-Windows_0_P.utoc'))) 'Obsolete overlay was retained'
$results.Add('Cumulative upgrade replaces prior patch and restores omitted loose file')
& $installer -Rollback -InstallDirectory $fixture.install | Out-Null
Assert-Baseline $fixture
$marker = Get-Content -LiteralPath (Join-Path $fixture.install 'warehouse-version.json') -Raw | ConvertFrom-Json
Assert-True ($marker.version -eq '1.0.0') 'Rollback version marker differs'
$results.Add('Explicit rollback restores baseline hashes and version')

$wrongBase = New-Fixture 'wrong-baseline'
Write-FixtureFile $wrongBase.install 'TestGame.exe' 'unrelated executable'
Assert-Rejected { & $installer -PatchDirectory $wrongBase.patch -InstallDirectory $wrongBase.install } 'Wrong baseline fails before writes'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $wrongBase.install '.warehouse-patch'))) 'Wrong baseline created state'
$corrupt = New-Fixture 'corrupt-payload'
Write-FixtureFile (Join-Path $corrupt.patch 'payload') 'Test/Content/Paks/Test-Windows_0_P.ucas' 'truncated'
Assert-Rejected { & $installer -PatchDirectory $corrupt.patch -InstallDirectory $corrupt.install } 'Corrupt payload fails before writes'
Assert-Baseline $corrupt
$unsafe = New-Fixture 'unsafe-path'
$unsafe.manifest.files[0].path = '../outside.txt'
$unsafe.manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $unsafe.patch 'patch.json') -Encoding UTF8
Assert-Rejected { & $installer -PatchDirectory $unsafe.patch -InstallDirectory $unsafe.install } 'Path traversal fails before writes'
Assert-Baseline $unsafe
$unknown = New-Fixture 'unknown-overlay'
Write-FixtureFile $unknown.install 'Test/Content/Paks/Foreign_7_P.utoc' 'foreign patch'
Assert-Rejected { & $installer -PatchDirectory $unknown.patch -InstallDirectory $unknown.install } 'Unknown installed overlay is rejected'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $unknown.install '.warehouse-patch'))) 'Unknown overlay changed state'
$unmanaged = New-Fixture 'unmanaged-file'
$unmanagedPath = 'Test/new-file.txt'
Write-FixtureFile $unmanaged.install $unmanagedPath 'keep this unrelated file'
Write-FixtureFile (Join-Path $unmanaged.patch 'payload') $unmanagedPath 'new patch content'
$unmanaged.manifest.files += (File-Entry (Join-Path $unmanaged.patch 'payload') $unmanagedPath)
$unmanaged.manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $unmanaged.patch 'patch.json') -Encoding UTF8
Assert-Rejected { & $installer -PatchDirectory $unmanaged.patch -InstallDirectory $unmanaged.install } 'Unmanaged file collision is rejected'
Assert-True ((Get-Content -LiteralPath (Join-Path $unmanaged.install $unmanagedPath) -Raw) -eq 'keep this unrelated file') 'Unmanaged file was overwritten'
$wrongMarker = New-Fixture 'wrong-version-marker'
[ordered]@{ schemaVersion=1; project='Test'; version='2.0.0'; baseVersion='2.0.0'; engineVersion='5.8.4' } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $wrongMarker.install 'warehouse-version.json') -Encoding UTF8
Assert-Rejected { & $installer -PatchDirectory $wrongMarker.patch -InstallDirectory $wrongMarker.install } 'Mismatched version marker is rejected'
Assert-Baseline $wrongMarker
$major = New-Fixture 'major-version-change'
$major.manifest.version = '2.0.0'
$major.manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $major.patch 'patch.json') -Encoding UTF8
Assert-Rejected { & $installer -PatchDirectory $major.patch -InstallDirectory $major.install } 'Major version change requires a new full baseline'
Assert-Baseline $major
$unreadableProcess = New-Fixture 'unreadable-game-process'
function global:Get-CimInstance {
    param([string]$ClassName, [string]$ErrorAction)
    return [pscustomobject]@{ Name='TestGame-Win64-Shipping.exe'; ProcessId=99999; ExecutablePath=$null }
}
try {
    Assert-Rejected { & $installer -PatchDirectory $unreadableProcess.patch -InstallDirectory $unreadableProcess.install } 'Unreadable game process path prevents installation'
} finally { Remove-Item -LiteralPath Function:\Get-CimInstance }
Assert-Baseline $unreadableProcess

# Inject one copy failure after the UI was replaced. The wrapper delegates every
# other copy to PowerShell's native cmdlet, including rollback restoration.
$failure = New-Fixture 'interrupted-copy'
$global:WarehousePatchTestFailPath = Join-Path $failure.patch 'payload/Test/Content/Paks/Test-Windows_0_P.utoc'
$global:WarehousePatchTestFailureSeen = $false
function global:Copy-Item {
    param([string]$LiteralPath, [string]$Destination, [switch]$Force)
    if ($LiteralPath -eq $global:WarehousePatchTestFailPath -and -not $global:WarehousePatchTestFailureSeen) {
        $global:WarehousePatchTestFailureSeen = $true
        throw 'Injected fixture copy failure'
    }
    Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
try {
    Assert-Rejected { & $installer -PatchDirectory $failure.patch -InstallDirectory $failure.install } 'Mid-copy failure is reported'
    Assert-True $global:WarehousePatchTestFailureSeen 'Copy fault was not reached'
} finally {
    Remove-Item -LiteralPath Function:\Copy-Item
    Remove-Variable WarehousePatchTestFailPath,WarehousePatchTestFailureSeen -Scope Global
}
Assert-Baseline $failure
Assert-True (-not (Test-Path -LiteralPath (Join-Path $failure.install '.warehouse-patch/installed.json'))) 'Failed transaction left installed state'
$results.Add('Mid-copy failure restores baseline and does not publish state')

[ordered]@{ success=$true; checks=@($results); count=$results.Count; outputDirectory=$testRoot;
    powershellVersion=$PSVersionTable.PSVersion.ToString(); completedAt=(Get-Date).ToString('o') } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $testRoot 'results.json') -Encoding UTF8
Write-Output "Passed $($results.Count) patch installer checks. Report: $testRoot\results.json"
