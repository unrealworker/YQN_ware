$ErrorActionPreference = 'Stop'
$prototypeRoot = $PSScriptRoot
$nodePath = (Get-Command node -ErrorAction Stop).Source
$vitePath = Join-Path $prototypeRoot 'node_modules/vite/bin/vite.js'
if (-not (Test-Path -LiteralPath $vitePath)) {
    Push-Location $prototypeRoot
    try { & npm ci; if ($LASTEXITCODE -ne 0) { throw '原型依赖安装失败。' } }
    finally { Pop-Location }
}
$existing = Get-NetTCPConnection -LocalPort 8781 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($existing[0].OwningProcess)"
    if (-not $owner.CommandLine.Contains('vite')) { throw '8781 端口被其他程序使用，请检查后再启动原型。' }
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8781/' -TimeoutSec 4
    if ($response.Content -notmatch 'GHS') { throw '8781 端口上的页面不是本原型，请检查后再启动。' }
} else {
    Start-Process -FilePath $nodePath -ArgumentList @("`"$vitePath`"", '--host', '127.0.0.1', '--port', '8781', '--strictPort') -WorkingDirectory $prototypeRoot -WindowStyle Hidden
}
Start-Process 'http://127.0.0.1:8781/'
