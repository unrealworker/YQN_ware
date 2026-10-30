param([string]$EngineRoot = 'D:/UE/UE_5.8')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
function Assert-Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
$project = Get-Content -Raw -LiteralPath (Join-Path $repo 'Test.uproject') | ConvertFrom-Json
Assert-Check ($project.EngineAssociation -eq '5.8') 'Project must target UE5.8.'
Assert-Check (@($project.Plugins | Where-Object { $_.Name -eq 'PixelStreaming2' -and $_.Enabled }).Count -eq 1) 'PixelStreaming2 is not enabled.'
Assert-Check (@($project.Plugins | Where-Object { $_.Name -eq 'PixelStreaming' -and $_.Enabled }).Count -eq 0) 'Legacy PixelStreaming must not be enabled.'
$build = Get-Content -Raw -LiteralPath (Join-Path $repo 'Source/Test/Test.Build.cs')
Assert-Check ($build -match '"PixelStreaming2"' -and $build -notmatch '"PixelStreaming"') 'Project module still depends on Legacy PixelStreaming.'
$ps2 = Join-Path $EngineRoot 'Engine/Plugins/Media/PixelStreaming2/Source'
$settings = Get-Content -Raw -LiteralPath (Join-Path $ps2 'PixelStreaming2Settings/Private/PixelStreaming2PluginSettings.cpp')
foreach ($cvar in @('PixelStreaming2.DecoupleFramerate','PixelStreaming2.WebRTC.Fps','PixelStreaming2.WebRTC.MinBitrate','PixelStreaming2.WebRTC.MaxBitrate','PixelStreaming2.Encoder.Codec','PixelStreaming2.WebRTC.NegotiateCodecs')) {
    Assert-Check ($settings.Contains($cvar)) "Engine setting missing: $cvar"
}
$input = Get-Content -Raw -LiteralPath (Join-Path $ps2 'PixelStreaming2Input/Public/IPixelStreaming2InputHandler.h')
Assert-Check ($input.Contains('FindMessageHandler') -and $input.Contains('RegisterMessageHandler')) 'PS2 public input handler API changed.'
$streamer = Get-Content -Raw -LiteralPath (Join-Path $ps2 'PixelStreaming2Core/Public/IPixelStreaming2Streamer.h')
Assert-Check ($streamer.Contains('SendAllPlayersMessage') -and $streamer.Contains('GetInputHandler')) 'PS2 public response API changed.'
$runtime = Get-Content -Raw -LiteralPath (Join-Path $repo 'Source/Test/GHSStreamingRuntime.cpp')
Assert-Check ($runtime.Contains('GHS_PS2_CONFIG') -and $runtime.Contains('FAPI::Get<FNVENC>().IsValid()')) 'Explicit NVIDIA policy validation is missing.'
Assert-Check (-not $runtime.Contains('TEXT("PixelStreaming.WebRTC.')) 'Runtime budget uses obsolete Legacy CVars.'
$version = Get-Content -Raw -LiteralPath (Join-Path $EngineRoot 'Engine/Build/Build.version') | ConvertFrom-Json
Write-Output "PixelStreaming2 integration structure verified against UE $($version.MajorVersion).$($version.MinorVersion).$($version.PatchVersion). Build, automation and browser connection still required."
