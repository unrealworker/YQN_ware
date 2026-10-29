[CmdletBinding()]
param([string]$Target = 'C:\YQN_WareHouse', [Parameter(Mandatory=$true)][string]$Backup, [switch]$DryRun)
. (Join-Path $PSScriptRoot 'Comparison-Common.ps1')

$targetRoot = Get-RootPath $Target; $backupRoot = Get-RootPath $Backup
if (!$backupRoot.StartsWith($targetRoot + '\_updates\PeerComparison-', [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup must be a comparison update directory within this deployment.' }
$null = Get-SafePath $targetRoot $backupRoot.Substring($targetRoot.Length + 1)
$state = Read-Json (Get-SafePath $backupRoot 'rollback-state.json')
if ($state.version -ne 1 -or $state.target -ine $targetRoot -or $state.state -notin @('prepared','installed')) { throw 'Rollback state does not match this target or is already restored.' }
$config = Read-Json (Get-SafePath $targetRoot 'launcher.config.json'); Assert-Stopped $config
foreach ($op in $state.operations) {
    if ($op.path -notin @('server/service.js','server/peer-comparison-proxy.js','server/peer-comparison.json','launcher.config.json','delivery-manifest.json')) { throw 'Unsupported rollback path.' }
    $destination = Get-SafePath $targetRoot $op.path
    if ($null -ne $op.oldSha256) { Assert-FileSha (Get-SafePath $backupRoot ('original/' + $op.path)) $op.oldSha256 }
    if (Test-Path -LiteralPath $destination) {
        $actual = Get-FileSha $destination
        if ($actual -ne $op.newSha256 -and $actual -ne $op.oldSha256) { throw ('File changed after deployment; refusing to overwrite: ' + $op.path) }
    } elseif ($null -ne $op.oldSha256) { throw ('Previously existing file is missing: ' + $op.path) }
}
$peer = Get-SafePath $targetRoot 'PeerStream'
if (Test-Path -LiteralPath $peer) { Assert-NoReparseTree $peer }
$archive = Get-SafePath $backupRoot 'archive'
if (Test-Path -LiteralPath $archive) { throw 'Rollback archive already exists; inspect the prior rollback before retrying.' }
if ($DryRun) { Write-Output 'DRY RUN OK: rollback verified; target unchanged.'; return }

$lockPath = Get-SafePath $targetRoot '.peer-comparison-update.lock'
$lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    Assert-Stopped $config
    [IO.Directory]::CreateDirectory($archive) | Out-Null
    # Archive the whole new PeerStream tree, including any logs/state, never delete it.
    if (Test-Path -LiteralPath $peer) {
        $archivePeer = Get-SafePath $targetRoot ($backupRoot.Substring($targetRoot.Length + 1) + '/archive/PeerStream')
        Assert-NoReparseTree $peer
        Move-Item -LiteralPath $peer -Destination $archivePeer
    }
    foreach ($op in $state.operations) {
        $destination = Get-SafePath $targetRoot $op.path
        if ($null -ne $op.oldSha256) { Copy-Atomic (Get-SafePath $backupRoot ('original/' + $op.path)) $destination $op.oldSha256 }
        elseif (Test-Path -LiteralPath $destination) {
            $archivedFile = Get-SafePath $archive $op.path
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($archivedFile)) | Out-Null
            Move-Item -LiteralPath $destination -Destination $archivedFile
        }
    }
    $state.state = 'restored'; Write-Json (Get-SafePath $backupRoot 'rollback-state.json') $state
    Write-Output 'ROLLBACK OK: original files/config restored; PeerStream archived. Services have not been started.'
} finally { $lock.Dispose(); if ([IO.File]::Exists($lockPath)) { [IO.File]::Delete($lockPath) } }
