[CmdletBinding(DefaultParameterSetName = 'Apply')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Apply')][string]$PatchDirectory,
    [Parameter(Mandatory = $true)][string]$InstallDirectory,
    [Parameter(ParameterSetName = 'Apply')][switch]$CheckOnly,
    [Parameter(Mandatory = $true, ParameterSetName = 'Rollback')][switch]$Rollback
)

# Compatible with Windows PowerShell 5.1. Never stops a game or service.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Assert-NoReparsePoint([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse points are not allowed: $cursor"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Resolve-Directory([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    if (-not (Test-Path -LiteralPath $full -PathType Container)) { throw "Directory missing: $full" }
    Assert-NoReparsePoint $full
    return $full
}

function Get-SafePath([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or $Relative.Contains('\') -or
        $Relative.StartsWith('/') -or $Relative -match '[:\x00-\x1f<>"|?*]') {
        throw "Unsafe relative path: $Relative"
    }
    foreach ($part in $Relative.Split('/')) {
        if (-not $part -or $part -in @('.', '..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
            $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw "Unsafe path segment: $Relative"
        }
    }
    $full = [IO.Path]::GetFullPath((Join-Path $Root $Relative.Replace('/', '\')))
    if (-not $full.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes installation: $Relative"
    }
    Assert-NoReparsePoint $full
    return $full
}

function Read-Json([string]$Path) { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
function Save-Json([string]$Path, $Value) {
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}
function Get-ReleaseVersion([string]$Value) {
    if ($Value -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') {
        throw "Invalid release version: $Value"
    }
    return [version]$Value
}

function Get-FileMap($Entries, [string]$Root) {
    $map = @{}
    foreach ($entry in @($Entries)) {
        $relative = [string]$entry.path
        $null = Get-SafePath $Root $relative
        if ($relative -match '^(?i:\.warehouse-patch)(/|$)' -or $relative -ieq 'warehouse-version.json') {
            throw "Manifest uses a reserved path: $relative"
        }
        if ($map.ContainsKey($relative)) { throw "Duplicate file path: $relative" }
        if ([string]$entry.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or [long]$entry.size -lt 0) {
            throw "Invalid file checksum or size: $relative"
        }
        $map[$relative] = $entry
    }
    return ,$map
}

function Assert-File([string]$Path, $Entry) {
    Assert-NoReparsePoint $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file missing: $Path" }
    if ((Get-Item -LiteralPath $Path).Length -ne [long]$Entry.size -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ine [string]$Entry.sha256) {
        throw "File checksum differs: $Path"
    }
}

function Assert-Manifest($Manifest, [string]$Root) {
    if ($Manifest.schemaVersion -ne 1 -or $Manifest.kind -ne 'cumulative-patch' -or $Manifest.project -ne 'Test') {
        throw 'Unsupported patch manifest'
    }
    $base = Get-ReleaseVersion ([string]$Manifest.baseVersion)
    $version = Get-ReleaseVersion ([string]$Manifest.version)
    if ($version -le $base) { throw 'Patch version must be greater than its baseline' }
    if ($version.Major -ne $base.Major) { throw 'A major version change requires a new full baseline' }
    if ([string]::IsNullOrWhiteSpace([string]$Manifest.engineVersion)) { throw 'Missing engine version' }
    $baseMap = Get-FileMap $Manifest.baseFiles $Root
    $filesMap = Get-FileMap $Manifest.files $Root
    foreach ($required in @('TestGame.exe', 'Test/Binaries/Win64/TestGame-Win64-Shipping.exe',
            'Test/Content/Paks/Test-Windows.pak', 'Test/Content/Paks/Test-Windows.utoc', 'Test/Content/Paks/Test-Windows.ucas')) {
        if (-not $baseMap.ContainsKey($required)) { throw "Baseline lacks required file: $required" }
    }
    if ($filesMap.Count -eq 0) { throw 'Patch has no payload files' }
    foreach ($relative in $filesMap.Keys) {
        # Native patch containers must be overlays. Replacing the original
        # containers would invalidate the immutable baseline used by later patches.
        if ($relative -match '^(?i:Test/Content/Paks)/' -and $baseMap.ContainsKey($relative)) {
            throw "Patch attempts to overwrite a baseline container: $relative"
        }
    }
}

function Assert-SameBaseline($Old, $New, [string]$Root) {
    if ($Old.baseVersion -ne $New.baseVersion -or $Old.engineVersion -ne $New.engineVersion) {
        throw 'Patch baseline or engine version differs from installed patch'
    }
    $oldMap = Get-FileMap $Old.baseFiles $Root
    $newMap = Get-FileMap $New.baseFiles $Root
    if ($oldMap.Count -ne $newMap.Count) { throw 'Baseline file set changed' }
    foreach ($relative in $oldMap.Keys) {
        if (-not $newMap.ContainsKey($relative) -or
            $oldMap[$relative].sha256 -ine $newMap[$relative].sha256 -or
            [long]$oldMap[$relative].size -ne [long]$newMap[$relative].size) {
            throw "Baseline identity changed: $relative"
        }
    }
}

function Assert-PackageStopped([string]$Root) {
    # Get-CimInstance checks both launcher and child runtime by actual path.
    # Failure to inspect processes is an error, never permission to patch live files.
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if (-not $process.ExecutablePath -and $process.Name -like 'TestGame*.exe') {
            throw "Cannot verify the path of $($process.Name), PID $($process.ProcessId); retry with permission to inspect that process"
        }
        if ($process.ExecutablePath -and
            $process.ExecutablePath.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Stop the package before updating: PID $($process.ProcessId)"
        }
    }
}

function Copy-Safe([string]$Source, [string]$Destination) {
    Assert-NoReparsePoint $Source
    Assert-NoReparsePoint $Destination
    $null = New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($Destination)) -Force
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

$install = Resolve-Directory $InstallDirectory
$stateDirectory = Get-SafePath $install '.warehouse-patch'
$statePath = Get-SafePath $install '.warehouse-patch/installed.json'
$backupRoot = Get-SafePath $install '.warehouse-patch/baseline-backup'
$versionPath = Get-SafePath $install 'warehouse-version.json'
$installed = $null
if (Test-Path -LiteralPath $statePath) {
    $installed = Read-Json $statePath
    Assert-Manifest $installed $install
}
if ($Rollback) {
    if ($null -eq $installed) { throw 'No installed patch to roll back' }
    $manifest = $installed
} else {
    $patch = Resolve-Directory $PatchDirectory
    if ($patch -eq $install -or $patch.StartsWith($install + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Extract the patch outside the installation directory'
    }
    $manifest = Read-Json (Get-SafePath $patch 'patch.json')
    Assert-Manifest $manifest $install
    if ($installed) {
        Assert-SameBaseline $installed $manifest $install
        if ((Get-ReleaseVersion $manifest.version) -le (Get-ReleaseVersion $installed.version)) {
            throw 'Patch version must be newer than the installed version'
        }
    }
    $payload = Resolve-Directory (Get-SafePath $patch 'payload')
    $payloadMap = Get-FileMap $manifest.files $payload
    foreach ($entry in $payloadMap.Values) { Assert-File (Get-SafePath $payload $entry.path) $entry }
    foreach ($file in @(Get-ChildItem -LiteralPath $payload -File -Recurse -Force)) {
        $relative = $file.FullName.Substring($payload.Length + 1).Replace('\', '/')
        $null = Get-SafePath $payload $relative
        if (-not $payloadMap.ContainsKey($relative)) { throw "Unlisted payload file: $relative" }
    }
}

$baseMap = Get-FileMap $manifest.baseFiles $install
$expected = @{}
foreach ($relative in $baseMap.Keys) { $expected[$relative] = $baseMap[$relative] }
$previousFiles = @{}
if ($installed) {
    $previousFiles = Get-FileMap $installed.files $install
    foreach ($relative in $previousFiles.Keys) { $expected[$relative] = $previousFiles[$relative] }
}
if (Test-Path -LiteralPath $versionPath) {
    $marker = Read-Json $versionPath
    $expectedVersion = if ($installed) { [string]$installed.version } else { [string]$manifest.baseVersion }
    if ($marker.schemaVersion -ne 1 -or $marker.project -ne 'Test' -or
        $marker.version -ne $expectedVersion -or $marker.baseVersion -ne $manifest.baseVersion -or
        $marker.engineVersion -ne $manifest.engineVersion) {
        throw 'Version marker does not match the verified installation state'
    }
}
if (-not $Rollback) {
    foreach ($entry in @($manifest.files)) {
        $relative = [string]$entry.path
        if (-not $expected.ContainsKey($relative) -and (Test-Path -LiteralPath (Get-SafePath $install $relative))) {
            throw "Patch would overwrite an unmanaged file: $relative"
        }
    }
}
foreach ($entry in $expected.Values) { Assert-File (Get-SafePath $install $entry.path) $entry }
foreach ($file in @(Get-ChildItem -LiteralPath (Get-SafePath $install 'Test/Content/Paks') -File -Force)) {
    if ($file.Name -match '(?i)_P(?:_s[0-9]+)?\.(pak|utoc|ucas)$') {
        $relative = $file.FullName.Substring($install.Length + 1).Replace('\', '/')
        if (-not $previousFiles.ContainsKey($relative)) { throw "Unknown installed patch container: $relative" }
    }
}
foreach ($relative in $previousFiles.Keys) {
    if ($baseMap.ContainsKey($relative)) {
        Assert-File (Get-SafePath $backupRoot $relative) $baseMap[$relative]
    }
}
Assert-PackageStopped $install
if ($CheckOnly) { Write-Output "Verified patch $($manifest.version) for baseline $($manifest.baseVersion); no files changed."; return }

# Snapshot the exact files this transaction can touch. A failed copy restores the
# prior installed version; explicit -Rollback instead restores the full baseline.
$affected = @{}
foreach ($relative in $previousFiles.Keys) { $affected[$relative] = $true }
if (-not $Rollback) { foreach ($entry in @($manifest.files)) { $affected[[string]$entry.path] = $true } }
$affected['warehouse-version.json'] = $true
$affected['.warehouse-patch/installed.json'] = $true
$transactionRelative = '.warehouse-patch/transactions/' + [guid]::NewGuid().ToString('N')
$transactionRoot = Get-SafePath $install $transactionRelative
$snapshot = @{}
$null = New-Item -ItemType Directory -Path $transactionRoot -Force
foreach ($relative in $affected.Keys) {
    $target = Get-SafePath $install $relative
    $exists = Test-Path -LiteralPath $target -PathType Leaf
    $snapshot[$relative] = $exists
    if ($exists) { Copy-Safe $target (Get-SafePath $transactionRoot $relative) }
}
# Create persistent baseline backups before any installation file is altered.
if (-not $Rollback) {
    foreach ($entry in @($manifest.files)) {
        $relative = [string]$entry.path
        if ($baseMap.ContainsKey($relative)) {
            $backup = Get-SafePath $backupRoot $relative
            if (-not (Test-Path -LiteralPath $backup)) { Copy-Safe (Get-SafePath $install $relative) $backup }
            Assert-File $backup $baseMap[$relative]
        }
    }
}

try {
    Assert-PackageStopped $install
    foreach ($relative in $previousFiles.Keys) {
        $target = Get-SafePath $install $relative
        if ($baseMap.ContainsKey($relative)) { Copy-Safe (Get-SafePath $backupRoot $relative) $target }
        elseif (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
    }
    if (-not $Rollback) {
        foreach ($entry in @($manifest.files)) {
            $target = Get-SafePath $install $entry.path
            Copy-Safe (Get-SafePath $payload $entry.path) $target
            Assert-File $target $entry
        }
        Save-Json $statePath $manifest
        $targetVersion = $manifest.version
    } else {
        Remove-Item -LiteralPath $statePath -Force
        $targetVersion = $manifest.baseVersion
    }
    Save-Json $versionPath ([ordered]@{ schemaVersion=1; project='Test'; version=$targetVersion;
        baseVersion=$manifest.baseVersion; engineVersion=$manifest.engineVersion; updatedAt=(Get-Date).ToString('o') })
} catch {
    $originalError = $_
    $restoreErrors = @()
    foreach ($relative in $snapshot.Keys) {
        try {
            $target = Get-SafePath $install $relative
            if ($snapshot[$relative]) { Copy-Safe (Get-SafePath $transactionRoot $relative) $target }
            elseif (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
        } catch { $restoreErrors += $_.Exception.Message }
    }
    if ($restoreErrors.Count) { throw "Update failed: $originalError. Recovery incomplete; keep $transactionRoot. $($restoreErrors -join '; ')" }
    throw "Update failed and prior files were restored: $originalError. Transaction retained at $transactionRoot"
}

# Only delete files from the transaction created above. Leave rollback backups.
foreach ($relative in $snapshot.Keys) {
    $saved = Get-SafePath $transactionRoot $relative
    if (Test-Path -LiteralPath $saved -PathType Leaf) { Remove-Item -LiteralPath $saved -Force }
}
Write-Output "Installed version $targetVersion. Restart the package or Pixel Streaming service when ready."
