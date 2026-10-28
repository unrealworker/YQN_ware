param([string]$EngineRoot = 'D:\UE\UE_5.4')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$plugin = Join-Path $repo 'Plugins/PixelStreaming'
$upstream = Join-Path $EngineRoot 'Engine/Plugins/Media/PixelStreaming'
$versionPath = Join-Path $EngineRoot 'Engine/Build/Build.version'
$version = Get-Content -Raw -LiteralPath $versionPath | ConvertFrom-Json
if ($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 4 -or $version.PatchVersion -ne 4 -or $version.Changelist -ne 35576357) {
    throw 'This patch baseline is UE 5.4.4 CL 35576357. Review/rebase before changing the manifest.'
}
$files = @()
foreach ($entry in @('PixelStreaming.uplugin','.gitignore','.gitattributes','Config','Content','Resources','Source')) {
    $item = Get-Item -LiteralPath (Join-Path $plugin $entry)
    $candidates = if ($item.PSIsContainer) { Get-ChildItem -LiteralPath $item.FullName -File -Recurse } else { @($item) }
    foreach ($file in $candidates) {
        $relative = [IO.Path]::GetRelativePath($plugin, $file.FullName).Replace('\','/')
        if ($relative -match '^Resources/WebServers/(Frontend|SignallingWebServer|Matchmaker|SFU)/') { continue }
        $original = Join-Path $upstream $relative
        $originalSha = if (Test-Path -LiteralPath $original -PathType Leaf) { (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
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
    patchId = 'ghs-ue54-uncapped-playout-v1'
    upstream = [ordered]@{
        engineVersion = '5.4.4'
        changelist = 35576357
        branch = '++UE5+Release-5.4'
        buildVersionSha256 = (Get-FileHash -LiteralPath $versionPath -Algorithm SHA256).Hash.ToLowerInvariant()
        relativePluginPath = 'Engine/Plugins/Media/PixelStreaming'
    }
    upstreamCopiedFileCount = 248
    upstreamCopiedBytes = 1119772
    excludes = @('Binaries','Intermediate','downloaded WebServers')
    files = @($files | Sort-Object path)
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'source-manifest.json') -Encoding utf8
"Manifest saved: $($files.Count) project files, $(@($files | Where-Object changed).Count) changed/new files."
