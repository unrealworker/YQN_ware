#Requires -Version 5.1
param(
    [ValidateRange(1024,65535)][int]$HttpPort=8080,
    [Parameter(Mandatory=$true)][string]$ApplicationPath
)
$ErrorActionPreference='Stop'
$isAdministrator=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $isAdministrator){throw '请通过启动器的“配置内网访问”按钮运行，或以管理员身份运行此脚本。'}
$app=(Resolve-Path -LiteralPath $ApplicationPath).Path
if([IO.Path]::GetExtension($app) -ine '.exe'){throw '请选择 UE 的 .exe 程序。'}
# UE's bootstrap executable starts the real game from <Project>/Binaries/Win64.
$appFolder=Split-Path -Parent $app
$relativeCandidate=Join-Path $appFolder 'Test/Binaries/Win64/TestGame.exe'
if(Test-Path -LiteralPath $relativeCandidate){$app=(Resolve-Path -LiteralPath $relativeCandidate).Path}
$node=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'runtime/node.exe')).Path
$policy=New-Object -ComObject HNetCfg.FwPolicy2
$specs=@(
    @{Name='GHS Pixel Streaming - LAN Web';Program=$node;Protocol=6;Ports=[string]$HttpPort},
    @{Name='GHS Pixel Streaming - LAN Media';Program=$app;Protocol=17;Ports='50000-50199'}
)
foreach($spec in $specs){
    $existing=@($policy.Rules | Where-Object {$_.Name -eq $spec.Name})
    foreach($rule in $existing){
        if($rule.Grouping -ne 'GHS Pixel Streaming Launcher'){throw ('同名防火墙规则不属于启动器：'+$spec.Name)}
        $policy.Rules.Remove($spec.Name)
    }
    $rule=New-Object -ComObject HNetCfg.FWRule
    $rule.Name=$spec.Name
    $rule.Description='GHS 仓储数字孪生：仅允许本地子网访问此程序。'
    $rule.Grouping='GHS Pixel Streaming Launcher'
    $rule.ApplicationName=$spec.Program
    $rule.Protocol=$spec.Protocol
    $rule.LocalPorts=$spec.Ports
    $rule.RemoteAddresses='LocalSubnet'
    $rule.Profiles=2147483647
    $rule.Direction=1
    $rule.Action=1
    $rule.Enabled=$true
    $policy.Rules.Add($rule)
}
$out=Join-Path $PSScriptRoot 'logs/lan-access.json'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
[ordered]@{success=$true;httpPort=$HttpPort;applicationPath=$app;nodePath=$node;remoteAddresses='LocalSubnet';udpPorts='50000-50199';configuredAt=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $out -Encoding UTF8
Write-Host ('内网访问已配置：网页 TCP '+$HttpPort+'，视频 UDP 50000–50199，仅本地子网。')
