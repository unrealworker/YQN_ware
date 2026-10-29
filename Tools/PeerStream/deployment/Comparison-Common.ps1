Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RootPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd([char[]]'\/')
    if ($full.Length -le [IO.Path]::GetPathRoot($full).TrimEnd([char[]]'\/').Length) { throw 'Filesystem roots cannot be deployment targets.' }
    $probe = $full
    while ($probe) {
        if (Test-Path -LiteralPath $probe) {
            if (((Get-Item -LiteralPath $probe -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse points are not permitted: $probe" }
        }
        $probe = [IO.Path]::GetDirectoryName($probe)
    }
    return $full
}
function Get-SafePath([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative)) { throw 'Expected a relative deployment path.' }
    $parts = $Relative.Replace('\','/').Split('/')
    foreach ($part in $parts) {
        if (!$part -or $part -in @('.','..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)' -or $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) { throw "Unsafe deployment path: $Relative" }
    }
    $full = [IO.Path]::GetFullPath((Join-Path $Root ($parts -join [IO.Path]::DirectorySeparatorChar)))
    if (!$full.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Path escapes deployment root: $Relative" }
    $current = $Root
    foreach ($part in $parts) {
        $current = Join-Path $current $part
        if ((Test-Path -LiteralPath $current) -and (((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "Reparse points are not permitted: $current" }
    }
    return $full
}
function Read-Json([string]$Path) {
    try { $value = [IO.File]::ReadAllText($Path) | ConvertFrom-Json -ErrorAction Stop } catch { throw "Invalid JSON file: $Path" }
    if ($null -eq $value -or $value -isnot [pscustomobject]) { throw "Expected JSON object: $Path" }
    return $value
}
function Write-Json([string]$Path, [object]$Value) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 100), (New-Object Text.UTF8Encoding($false)))
}
function Get-FileSha([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file missing: $Path" }
    $algorithm = [Security.Cryptography.SHA256]::Create(); $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Assert-FileSha([string]$Path, [string]$Expected) {
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$' -or (Get-FileSha $Path) -ne $Expected.ToLowerInvariant()) { throw "SHA256 mismatch: $Path" }
}
function Copy-Atomic([string]$Source, [string]$Destination, [string]$Hash) {
    $directory = [IO.Path]::GetDirectoryName($Destination); [IO.Directory]::CreateDirectory($directory) | Out-Null
    $temp = Join-Path $directory ('.peer-update-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::Copy($Source, $temp, $false); Assert-FileSha $temp $Hash
        if ([IO.File]::Exists($Destination)) { [IO.File]::Replace($temp, $Destination, [NullString]::Value) } else { [IO.File]::Move($temp, $Destination) }
        Assert-FileSha $Destination $Hash
    } finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
}
function Get-Value([object]$Object, [string]$Name, [object]$Default) {
    if ($Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }; return $Default
}
function Set-Value([object]$Object, [string]$Name, [object]$Value) { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force }
function Assert-Stopped([object]$Config) {
    $ports = @(8080, 8088, 8888)
    foreach ($name in @('httpPort','streamerPort')) {
        $number = 0
        if ([int]::TryParse([string](Get-Value $Config $name 0), [ref]$number) -and $number -gt 0 -and $number -le 65535) { $ports += $number }
    }
    $busy = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $ports -contains $_.Port } | Select-Object -ExpandProperty Port -Unique)
    if ($busy.Count) { throw ('Stop both streaming services before updating. TCP listeners active: ' + ($busy -join ', ')) }
}
function Get-ManifestMap([object]$Manifest, [string]$Root) {
    if ($Manifest.version -ne 1 -or !$Manifest.files) { throw 'Unsupported delivery manifest.' }
    $map = @{}
    foreach ($entry in $Manifest.files) {
        $relative = [string]$entry.path; $null = Get-SafePath $Root $relative
        if ($relative -match '^(?i)(_updates[/\\]|launcher\.config\.json$|delivery-manifest\.json$)' -or $map.ContainsKey($relative) -or [string]$entry.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid manifest path/hash: $relative" }
        $map[$relative] = $entry
    }
    return $map
}
function Get-PeerSettings([object]$Config, [string]$Target, [hashtable]$Managed) {
    $configured = [string](Get-Value $Config 'executablePath' '')
    if (!$configured) { throw 'launcher.config.json is missing executablePath.' }
    $exe = if ([IO.Path]::IsPathRooted($configured)) { [IO.Path]::GetFullPath($configured) } else { [IO.Path]::GetFullPath((Join-Path $Target $configured)) }
    $prefix = $Target + [IO.Path]::DirectorySeparatorChar
    if (!$exe.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Configured UE executable must be inside this deployment.' }
    $relative = $exe.Substring($prefix.Length).Replace('\','/'); $exe = Get-SafePath $Target $relative
    if ([IO.Path]::GetFileName($exe) -ieq 'TestGame.exe') {
        $shipping = [IO.Path]::Combine([IO.Path]::GetDirectoryName($exe), 'Test\Binaries\Win64\TestGame-Win64-Shipping.exe')
        if (Test-Path -LiteralPath $shipping -PathType Leaf) { $relative = $shipping.Substring($prefix.Length).Replace('\','/'); $exe = Get-SafePath $Target $relative }
    }
    if (!$Managed.ContainsKey($relative)) { throw 'Configured UE executable is not registered in delivery-manifest.json.' }
    Assert-FileSha $exe $Managed[$relative].sha256
    $quality = [string](Get-Value $Config 'qualityProfile' 'balanced')
    if ($quality -notin @('balanced','clear','ultra','custom')) { throw 'Unsupported original quality profile.' }
    $min = [double](Get-Value $Config 'minBitrateMbps' 1); $start = [double](Get-Value $Config 'startBitrateMbps' 8); $max = [double](Get-Value $Config 'maxBitrateMbps' 24)
    if ($min -le 0 -or $min -gt $start -or $start -gt $max -or $max -gt 200) { throw 'Invalid original bitrate settings.' }
    $ice = @(); $stun = [string](Get-Value $Config 'stunUrl' ''); $turn = [string](Get-Value $Config 'turnUrl' '')
    if ($stun) { $ice += @{urls=@($stun)} }
    if ($turn) { $ice += @{urls=@($turn); username=[string](Get-Value $Config 'turnUsername' ''); credential=[string](Get-Value $Config 'turnPassword' '')} }
    return [pscustomobject]@{host='127.0.0.1'; port=8088; executablePath=$exe; width=1920; height=1080; fps=60; instances=[Math]::Max(1,[Math]::Min(10,[int](Get-Value $Config 'maxViewers' 10))); qualityProfile=$quality; minBitrateMbps=$min; startBitrateMbps=$start; maxBitrateMbps=$max; mediaMinPort=50000; mediaMaxPort=50199; startupTimeoutSeconds=120; idleTimeoutSeconds=8; iceServers=@($ice)}
}
function Assert-NoReparseTree([string]$Path) {
    foreach ($item in Get-ChildItem -LiteralPath $Path -Force -Recurse) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse points are not permitted: $($item.FullName)" }
    }
}
