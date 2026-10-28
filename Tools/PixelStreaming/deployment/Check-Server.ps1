#Requires -Version 5.1
[CmdletBinding()]
param([switch]$VerifyFiles)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$configFile=Join-Path $root 'launcher.config.json'
$config=Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
$required=@('runtime/node.exe','server/server.js','player/index.html','像素流服务启动器.exe','App/Windows/Test/Binaries/Win64/TestGame-Win64-Shipping.exe','App/Windows/Engine/Binaries/Win64/EpicWebHelper.exe','App/Windows/Test/Content/GHSTwinUI/web/index.html','App/Windows/Test/Content/GHSTwinUI/data/order-replay.json','App/Windows/Test/Content/GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf')
$missing=@($required | Where-Object {-not (Test-Path -LiteralPath (Join-Path $root $_) -PathType Leaf)})
$os=Get-CimInstance Win32_OperatingSystem
$cpus=@(Get-CimInstance Win32_Processor)
$gpu=@()
$smi=Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if($smi){
    $raw=& $smi.Source --query-gpu=name,driver_version,memory.total,memory.free,driver_model.current --format=csv,noheader,nounits 2>$null
    if($LASTEXITCODE -eq 0){$gpu=@($raw)}
}
$integrity='未执行；使用 -VerifyFiles 校验交付文件'
if($VerifyFiles){
    $manifest=Get-Content -LiteralPath (Join-Path $root 'delivery-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $failures=@()
    foreach($item in $manifest.files){
        $file=Join-Path $root $item.path
        if(-not (Test-Path -LiteralPath $file -PathType Leaf)){$failures+=$item.path;continue}
        if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $item.sha256){$failures+=$item.path}
    }
    $integrity=if($failures.Count){'不匹配：'+($failures -join ', ')}else{'全部交付文件校验通过（不包含可修改配置与日志）'}
}
$report=[ordered]@{
    os=$os.Caption;version=$os.Version
    logicalProcessors=($cpus | Measure-Object NumberOfLogicalProcessors -Sum).Sum
    memoryGiB=[Math]::Round($os.TotalVisibleMemorySize/1MB,1)
    availableMemoryGiB=[Math]::Round($os.FreePhysicalMemory/1MB,1)
    gpu=$gpu;missingFiles=$missing
    networkMode=$config.networkMode;maxViewers=$config.maxViewers
    integrity=$integrity
    runtimeValidation='尚需在浏览器验证真实 DX12 渲染、NVENC 编码和输入；硬件名称不代表实际并发能力。'
}
New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
$report | ConvertTo-Json -Depth 4 | Tee-Object -FilePath (Join-Path $root 'logs/server-check.json')
if($missing.Count -or ($VerifyFiles -and $failures.Count)){exit 1}
