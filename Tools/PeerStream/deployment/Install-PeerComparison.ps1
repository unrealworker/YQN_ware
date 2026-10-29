[CmdletBinding()]
param([string]$Target = 'C:\YQN_WareHouse', [switch]$DryRun)
. (Join-Path $PSScriptRoot 'Comparison-Common.ps1')

$targetRoot = Get-RootPath $Target; $bundleRoot = Get-RootPath $PSScriptRoot
if (!(Test-Path -LiteralPath $targetRoot -PathType Container)) { throw 'Deployment target does not exist.' }
$bundle = Read-Json (Join-Path $bundleRoot 'bundle-manifest.json')
if ($bundle.version -ne 1 -or [string]$bundle.bundleId -notmatch '^peer-comparison-[0-9a-f-]{36}$' -or $bundle.expectedServiceSha256 -ne '8d587e5dcb88fbde862026c40a4cc8c3ccf2c52d8eb9c33238a208bbcd345c6d') { throw 'Unsupported comparison bundle.' }
$payload = Get-SafePath $bundleRoot 'payload'; $seen = @{}
foreach ($entry in $bundle.files) {
    $relative = [string]$entry.path
    if ($seen.ContainsKey($relative) -or ($relative -notmatch '^PeerStream/' -and $relative -notin @('server/service.js','server/peer-comparison-proxy.js','server/peer-comparison.json')) -or $relative -match '^PeerStream/(?i:settings\.json$|runtime/|logs/|\.state/)') { throw "Invalid bundle path: $relative" }
    $seen[$relative] = $true; Assert-FileSha (Get-SafePath $payload $relative) $entry.sha256
}
foreach ($entry in $bundle.scripts) { Assert-FileSha (Get-SafePath $bundleRoot $entry.path) $entry.sha256 }
foreach ($required in @('server/service.js','server/peer-comparison-proxy.js','server/peer-comparison.json','PeerStream/host.cjs','PeerStream/player.html','PeerStream/peer-stream.js','PeerStream/player-session.js','PeerStream/service.cjs','PeerStream/signal.js','PeerStream/node_modules/ws/package.json')) {
    if (!$seen.ContainsKey($required)) { throw "Incomplete bundle: $required" }
}
$peer = Get-SafePath $targetRoot 'PeerStream'
if (Test-Path -LiteralPath $peer) { throw 'Target PeerStream already exists. Refusing to overwrite existing content.' }
$configPath = Get-SafePath $targetRoot 'launcher.config.json'; $manifestPath = Get-SafePath $targetRoot 'delivery-manifest.json'
$config = Read-Json $configPath; $delivery = Read-Json $manifestPath
$configHash = Get-FileSha $configPath; $manifestHash = Get-FileSha $manifestPath
$managed = Get-ManifestMap $delivery $targetRoot
Assert-FileSha (Get-SafePath $targetRoot 'server/service.js') $bundle.expectedServiceSha256
foreach ($relative in @('server/service.js','runtime/node.exe','runtime/LICENSE.txt')) {
    if (!$managed.ContainsKey($relative)) { throw "Required managed baseline file missing: $relative" }
    Assert-FileSha (Get-SafePath $targetRoot $relative) $managed[$relative].sha256
}
$settings = Get-PeerSettings $config $targetRoot $managed
Assert-Stopped $config
if ($DryRun) {
    Write-Output ('DRY RUN OK: bundle and baseline verified; target unchanged. 1920x1080, 60 FPS; maximum peer instances: ' + $settings.instances)
    return
}

$lockPath = Get-SafePath $targetRoot '.peer-comparison-update.lock'
$lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$backup = $null
try {
    Assert-Stopped $config
    Assert-FileSha $configPath $configHash; Assert-FileSha $manifestPath $manifestHash
    Assert-FileSha (Get-SafePath $targetRoot 'server/service.js') $bundle.expectedServiceSha256
    if (Test-Path -LiteralPath $peer) { throw 'PeerStream appeared during preflight. Update cancelled.' }
    $backup = Get-SafePath $targetRoot ('_updates/PeerComparison-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($backup) | Out-Null
    foreach ($script in @('Comparison-Common.ps1','Rollback-PeerComparison.ps1')) { [IO.File]::Copy((Join-Path $bundleRoot $script), (Get-SafePath $backup $script), $false) }
    foreach ($pair in @(@('width',1920),@('height',1080),@('fps',60),@('adaptiveResourceBudget',$false))) { Set-Value $config $pair[0] $pair[1] }
    $staging = Get-SafePath $backup 'staged'; [IO.Directory]::CreateDirectory($staging) | Out-Null
    Write-Json (Get-SafePath $staging 'launcher.config.json') $config
    Write-Json (Get-SafePath $staging 'PeerStream/settings.json') $settings

    # Keep the original application sourceCommit/mapSha256. Register only file hashes
    # and a separate comparison record; no credentials are included in the manifest.
    $newEntries = @{}
    foreach ($entry in $bundle.files) { $newEntries[[string]$entry.path] = $entry }
    foreach ($name in @('node.exe','LICENSE.txt')) {
        $original = Get-SafePath $targetRoot ('runtime/' + $name)
        $newEntries['PeerStream/runtime/' + $name] = [pscustomobject]@{path=('PeerStream/runtime/' + $name); bytes=(Get-Item -LiteralPath $original).Length; sha256=(Get-FileSha $original)}
    }
    $entries = @($delivery.files | Where-Object { !$newEntries.ContainsKey([string]$_.path) }) + @($newEntries.Values)
    Set-Value $delivery 'files' @($entries | Sort-Object path)
    Set-Value $delivery 'peerComparison' ([pscustomobject]@{bundleId=$bundle.bundleId; sourceCommit=$bundle.sourceCommit; sourceDirty=$bundle.sourceDirty; installedAt=[DateTime]::UtcNow.ToString('o'); path='/peer-stream/'; settings='1920x1080; 60 FPS; H264'; applicationUnchanged=$true})
    Write-Json (Get-SafePath $staging 'delivery-manifest.json') $delivery

    $operations = @()
    foreach ($relative in @('server/service.js','server/peer-comparison-proxy.js','server/peer-comparison.json','launcher.config.json','delivery-manifest.json')) {
        $destination = Get-SafePath $targetRoot $relative
        $source = if ($relative.StartsWith('server/')) { Get-SafePath $payload $relative } else { Get-SafePath $staging $relative }
        $oldHash = $null
        if (Test-Path -LiteralPath $destination) {
            $oldHash = Get-FileSha $destination; $oldCopy = Get-SafePath $backup ('original/' + $relative)
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($oldCopy)) | Out-Null
            [IO.File]::Copy($destination, $oldCopy, $false); Assert-FileSha $oldCopy $oldHash
        }
        $operations += [pscustomobject]@{path=$relative; oldSha256=$oldHash; newSha256=(Get-FileSha $source)}
    }
    $state = [pscustomobject]@{version=1; bundleId=$bundle.bundleId; target=$targetRoot; state='prepared'; operations=$operations}
    Write-Json (Get-SafePath $backup 'rollback-state.json') $state

    # All destinations have been resolved below the explicit deployment target.
    [IO.Directory]::CreateDirectory($peer) | Out-Null
    foreach ($entry in $bundle.files | Where-Object { $_.path.StartsWith('PeerStream/') }) {
        Copy-Atomic (Get-SafePath $payload $entry.path) (Get-SafePath $targetRoot $entry.path) $entry.sha256
    }
    foreach ($name in @('node.exe','LICENSE.txt')) {
        Copy-Atomic (Get-SafePath $targetRoot ('runtime/' + $name)) (Get-SafePath $targetRoot ('PeerStream/runtime/' + $name)) $managed['runtime/' + $name].sha256
    }
    $stagedSettings = Get-SafePath $staging 'PeerStream/settings.json'
    Copy-Atomic $stagedSettings (Get-SafePath $targetRoot 'PeerStream/settings.json') (Get-FileSha $stagedSettings)
    foreach ($op in $operations) {
        $source = if ($op.path.StartsWith('server/')) { Get-SafePath $payload $op.path } else { Get-SafePath $staging $op.path }
        Copy-Atomic $source (Get-SafePath $targetRoot $op.path) $op.newSha256
    }
    $state.state = 'installed'; Write-Json (Get-SafePath $backup 'rollback-state.json') $state
    Write-Output ('INSTALL OK: both entries configured for 1920x1080 / 60 FPS. Services have not been started.')
    Write-Output ('BACKUP=' + $backup)
    Write-Output ('ROLLBACK: powershell -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $backup 'Rollback-PeerComparison.ps1') + '" -Target "' + $targetRoot + '" -Backup "' + $backup + '"')
} catch {
    if ($backup) { Write-Warning ('Install did not complete. Backup retained for rollback: ' + $backup) }
    throw
} finally {
    $lock.Dispose(); if ([IO.File]::Exists($lockPath)) { [IO.File]::Delete($lockPath) }
}
