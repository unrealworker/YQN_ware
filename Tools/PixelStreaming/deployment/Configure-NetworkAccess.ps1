#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateRange(1,65535)][int]$HttpPort=8080,
    [Parameter(Mandatory=$true)][string]$ApplicationPath,
    [ValidateSet('LAN','Public')][string]$Scope='LAN',
    [switch]$TrustProxy,
    [switch]$PlanOnly
)
$ErrorActionPreference='Stop'
$app=(Resolve-Path -LiteralPath $ApplicationPath).Path
if([IO.Path]::GetExtension($app) -ine '.exe'){throw '请选择 UE 的 .exe 程序。'}
$appFolder=Split-Path -Parent $app
foreach($name in @('TestGame-Win64-Shipping.exe','TestGame.exe')) {
    $candidate=Join-Path $appFolder ('Test/Binaries/Win64/'+$name)
    if(Test-Path -LiteralPath $candidate -PathType Leaf){$app=(Resolve-Path -LiteralPath $candidate).Path;break}
}
$node=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'runtime/node.exe')).Path
$sha=[Security.Cryptography.SHA256]::Create()
try{$id=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($PSScriptRoot.ToLowerInvariant())))).Replace('-','').Substring(0,12)}finally{$sha.Dispose()}
$group='GHS Pixel Streaming Launcher'
$webName='GHS Pixel Streaming '+$id+' Web'
$mediaName='GHS Pixel Streaming '+$id+' Media'
$remote=if($Scope -eq 'Public'){'*'}else{'LocalSubnet'}
$specs=@()
if(-not $TrustProxy){$specs+=@{Name=$webName;Program=$node;Protocol=6;Ports=[string]$HttpPort}}
$specs+=@{Name=$mediaName;Program=$app;Protocol=17;Ports='50000-50199'}
$plan=[ordered]@{scope=$Scope;remoteAddresses=$remote;trustProxy=[bool]$TrustProxy;rules=$specs;note='仅配置 Windows 入站规则；路由器/NAT、云安全组、域名、TLS 和 TURN 需另行配置。不开放 UE 信令与管理端口。'}
if($PlanOnly){$plan | ConvertTo-Json -Depth 5;return}
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(-not $admin){throw '请从启动器的配置访问按钮运行此脚本，或以管理员身份运行。'}
$policy=New-Object -ComObject HNetCfg.FwPolicy2
# Only replace this installation's owned rules; validate every rule before mutation.
foreach($name in @($webName,$mediaName)){
    foreach($rule in @($policy.Rules | Where-Object {$_.Name -eq $name})){
        if($rule.Grouping -ne $group){throw ('同名防火墙规则不属于启动器：'+$name)}
    }
}
foreach($name in @($webName,$mediaName)){
    foreach($rule in @($policy.Rules | Where-Object {$_.Name -eq $name})){$policy.Rules.Remove($name)}
}
foreach($spec in $specs){
    $rule=New-Object -ComObject HNetCfg.FWRule
    $rule.Name=$spec.Name
    $rule.Description='GHS 仓储像素流；访问范围 '+$Scope+'；目录 '+$PSScriptRoot
    $rule.Grouping=$group
    $rule.ApplicationName=$spec.Program
    $rule.Protocol=$spec.Protocol
    $rule.LocalPorts=$spec.Ports
    $rule.RemoteAddresses=$remote
    $rule.Profiles=2147483647
    $rule.Direction=1
    $rule.Action=1
    $rule.Enabled=$true
    $policy.Rules.Add($rule)
}
$plan['configuredAt']=[DateTime]::UtcNow.ToString('o')
$out=Join-Path $PSScriptRoot 'logs/network-access.json'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
$plan | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $out -Encoding UTF8
Write-Host ('Windows '+$Scope+' 入站规则已配置；请继续检查云安全组、NAT 和 TURN。')
