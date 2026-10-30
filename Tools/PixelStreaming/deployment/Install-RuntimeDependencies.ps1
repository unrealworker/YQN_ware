#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$redistRoot = Join-Path $PSScriptRoot 'App/Windows/Engine/Extras/Redist/en-us'
$vc = Join-Path $redistRoot 'vc_redist.x64.exe'
$gameInput = Join-Path $redistRoot 'GameInputRedist.msi'
foreach ($file in @($vc, $gameInput)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "运行组件安装包缺失：$file。请重新复制完整 UE5.8 交付目录。" }
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw "官方安装包签名验证失败：$file。未执行安装。" }
}
$logRoot = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$restartNeeded = $false
Write-Host '正在安装 Microsoft Visual C++ x64 运行组件…'
$vcLog = Join-Path $logRoot 'vc-runtime-install.log'
$vcProcess = Start-Process -FilePath $vc -ArgumentList ('/install /passive /norestart /log "' + $vcLog + '"') -PassThru -Wait
if ($vcProcess.ExitCode -notin @(0, 3010, 1638)) { throw "VC++ x64 安装失败，退出码：$($vcProcess.ExitCode)" }
if ($vcProcess.ExitCode -eq 3010) { $restartNeeded = $true }
Write-Host '正在安装 Microsoft GameInput 运行组件…'
$msiLog = Join-Path $logRoot 'gameinput-install.log'
$msiArgs = '/i "' + $gameInput + '" /passive /norestart /L*v "' + $msiLog + '"'
$msiProcess = Start-Process -FilePath (Join-Path $env:WINDIR 'System32/msiexec.exe') -ArgumentList $msiArgs -PassThru -Wait
if ($msiProcess.ExitCode -notin @(0, 3010)) { throw "GameInput 安装失败，退出码：$($msiProcess.ExitCode)，请查看 $msiLog" }
if ($msiProcess.ExitCode -eq 3010) { $restartNeeded = $true }
if ($restartNeeded) { Write-Host '运行组件安装完成，请在方便时重启服务器后再验证流送。不会自动重启。'; exit 3010 }
Write-Host '运行组件安装完成，可启动服务并在浏览器验证画面。'
