param([string]$EngineRoot = '')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$plugin = Join-Path $repo 'Plugins/PixelStreaming'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'source-manifest.json') | ConvertFrom-Json
function Assert-Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
foreach ($entry in $manifest.files) {
    Assert-Check ($entry.path -notmatch '^(Binaries|Intermediate)/|/node_modules/') "Generated file in source manifest: $($entry.path)"
    $file = Join-Path $plugin $entry.path
    Assert-Check (Test-Path -LiteralPath $file -PathType Leaf) "Missing project file: $($entry.path)"
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
    Assert-Check ($actual -eq $entry.projectSha256) "Project source hash mismatch: $($entry.path)"
    if ($EngineRoot -and $entry.upstreamSha256) {
        $engineFile = Join-Path (Join-Path $EngineRoot $manifest.upstream.relativePluginPath) $entry.path
        Assert-Check ((Get-FileHash -LiteralPath $engineFile -Algorithm SHA256).Hash -eq $entry.upstreamSha256) "Engine baseline differs: $($entry.path)"
    }
}
if ($EngineRoot) {
    Assert-Check ((Get-FileHash -LiteralPath (Join-Path $EngineRoot 'Engine/Build/Build.version') -Algorithm SHA256).Hash -eq $manifest.upstream.buildVersionSha256) 'Engine Build.version differs from tested baseline.'
}
$privateDir = Join-Path $plugin 'Source/PixelStreaming/Private'
$peer = Get-Content -Raw -LiteralPath (Join-Path $privateDir 'PixelStreamingPeerConnection.cpp')
$group = Get-Content -Raw -LiteralPath (Join-Path $privateDir 'VideoSourceGroup.cpp')
$layered = Get-Content -Raw -LiteralPath (Join-Path $privateDir 'VideoEncoderLayered.cpp')
$hardware = Get-Content -Raw -LiteralPath (Join-Path $privateDir 'VideoEncoderSingleLayerHardware.cpp')
$settings = Get-Content -Raw -LiteralPath (Join-Path $privateDir 'Settings.cpp')
$build = Get-Content -Raw -LiteralPath (Join-Path $plugin 'Source/PixelStreaming/PixelStreaming.Build.cs')
Assert-Check ($peer -notmatch 'max_framerate\s*=\s*Settings::CVarPixelStreamingWebRTCFps') 'Raw FPS=0 would become an RTP zero-frame ceiling.'
Assert-Check (([regex]::Matches($peer, 'SetEncodingFrameLimit\(')).Count -eq 3) 'Base, simulcast and runtime sender paths must use the optional-limit policy.'
Assert-Check ($group -notmatch '/\s*VideoSourceGroup->FramesPerSecond') 'Unsafe atomic/direct zero FPS division remains.'
Assert-Check (([regex]::Matches($group, 'GHS::IsUncapped\(TargetFPS\)')).Count -eq 2) 'Both worker implementations require zero-FPS guards.'
Assert-Check ($group -match 'bCoupleFramerate = GHS::ShouldCouple') 'Runtime uncapped capture coupling is missing.'
Assert-Check ($layered -match '(?s)!GHS::IsUncapped\(UE::PixelStreaming::Settings::CVarPixelStreamingWebRTCFps.GetValueOnAnyThread\(\)\)\s*&& StreamInfos\[StreamIdx\].FramerateController->ShouldDropFrame') 'Layered encoder still enforces an implicit codec-hint cap.'
Assert-Check ($group -match '(?s)OnFrameCaptured\(\).*?FScopeLock FrameLock\(&FrameThreadGuard\);.*?FrameRunnable->FrameEvent.Get\(\)->Trigger') 'Capture must protect the runnable pointer until Trigger completes.'
Assert-Check ($group -match 'RunnableToStop = MoveTemp\(FrameRunnable\)') 'Stopped runnable ownership must survive the worker join.'
Assert-Check ($group -match 'FScopeLock LifecycleLock\(&FrameThreadLifecycleGuard\)') 'Worker replacement and stop must serialize.'
Assert-Check ($hardware -match 'TargetFramerate = MeasuredRateHint.Get\(\)') 'Uncapped hardware rate-control hint is not sampled.'
Assert-Check ($hardware -match '(?s)CVarPixelStreamingGHSLowLatencyPlayout.GetValueOnAnyThread\(\).*?Image.playout_delay_ = webrtc::VideoPlayoutDelay\(0, 0\)') 'Low-latency opt-in is not applied to encoded packets.'
Assert-Check ($settings -match '(?s)CVarPixelStreamingGHSLowLatencyPlayout\(\s*TEXT\("PixelStreaming.GHSLowLatencyPlayout"\),\s*false,') 'Low-latency experiment must remain opt-in by default.'
Assert-Check ($build -match 'Path.Combine\(PluginDirectory, "Resources", "WebServers"\)') 'Runtime resources must resolve to this project plugin.'
Assert-Check ($build -notmatch '../../Engine/Plugins/Media/PixelStreaming') 'Build rules still reference engine PixelStreaming resources.'
Assert-Check ($build -match '"LibVpx", "OpenSSL", "libOpus"' -and $build -match 'PrivateDependencyModuleNames.Add\("zlib"\)') 'Installed-engine modular builds require direct official WebRTC static-library dependencies.'
"PASS: $($manifest.files.Count) source SHA256 entries, engine baseline $(if ($EngineRoot) {'verified'} else {'not requested'}), RTP/capture/encoder/playout integration guards."
