param([string]$EngineRoot = 'D:\UE\UE_5.8')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$plugin = Join-Path $repo 'Plugins/PixelStreaming'
$upstream = Join-Path $EngineRoot 'Engine/Plugins/Media/PixelStreaming'
$versionPath = Join-Path $EngineRoot 'Engine/Build/Build.version'
$version = Get-Content -Raw -LiteralPath $versionPath | ConvertFrom-Json
if ($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8 -or $version.PatchVersion -ne 4 -or $version.Changelist -ne 58902052) {
    throw 'This patch baseline is UE 5.8.4 CL 58902052. Review/rebase before changing the manifest.'
}
$files = @()
$upstreamCopiedFileCount = 0
$upstreamCopiedBytes = 0L
foreach ($entry in @('PixelStreaming.uplugin','.gitignore','.gitattributes','Config','Content','Resources','Source')) {
    $item = Get-Item -LiteralPath (Join-Path $plugin $entry)
    $candidates = if ($item.PSIsContainer) { Get-ChildItem -LiteralPath $item.FullName -File -Recurse } else { @($item) }
    foreach ($file in $candidates) {
        $relative = [IO.Path]::GetRelativePath($plugin, $file.FullName).Replace('\','/')
        if ($relative -match '^Resources/WebServers/(Frontend|SignallingWebServer|Matchmaker|SFU|Extras|Signalling|Common|SS_Test)/') { continue }
        $original = Join-Path $upstream $relative
        $originalSha = if (Test-Path -LiteralPath $original -PathType Leaf) { (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
        if ($originalSha) {
            $upstreamCopiedFileCount++
            $upstreamCopiedBytes += (Get-Item -LiteralPath $original).Length
        }
        $patchedSha = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $files += [ordered]@{
            path = $relative
            bytes = $file.Length
            upstreamSha256 = $originalSha
            projectSha256 = $patchedSha
            changed = ($originalSha -ne $patchedSha)
        }
    }
}
$manifest = [ordered]@{
    schemaVersion = 1
    patchId = 'ghs-ue58-uncapped-playout-v1'
    upstream = [ordered]@{
        engineVersion = '5.8.4'
        changelist = 58902052
        branch = '++UE5+Release-5.8'
        buildVersionSha256 = (Get-FileHash -LiteralPath $versionPath -Algorithm SHA256).Hash.ToLowerInvariant()
        relativePluginPath = 'Engine/Plugins/Media/PixelStreaming'
    }
    upstreamCopiedFileCount = $upstreamCopiedFileCount
    upstreamCopiedBytes = $upstreamCopiedBytes
    excludes = @('Binaries','Intermediate','downloaded WebServers')
    files = @($files | Sort-Object path)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'source-manifest.json') -Encoding utf8
"Manifest saved: $($files.Count) project files, $(@($files | Where-Object changed).Count) changed/new files."
