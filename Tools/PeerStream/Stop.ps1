$ErrorActionPreference = 'Stop'

try {
    $settings = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'settings.json') -Raw | ConvertFrom-Json
    $port = 0
    if (-not [int]::TryParse([string]$settings.port, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        throw 'settings.json must contain a valid port (1-65535).'
    }
    $localHost = '127.0.0.1'
    if ([string]$settings.host -eq '::1' -or [string]$settings.host -eq '::') {
        $localHost = '[::1]'
    }
    $baseUrl = 'http://{0}:{1}' -f $localHost, $port
    try {
        $health = Invoke-RestMethod -Uri ($baseUrl + '/health') -Method Get -TimeoutSec 2
    } catch {
        throw 'Service health is unreachable. No process was terminated.'
    }
    if ($health.service -ne 'ghs-peer-stream') {
        throw ('Port {0} is responding as another service. Stop cancelled.' -f $port)
    }

    $controlPath = Join-Path $PSScriptRoot '.state\control.json'
    $control = Get-Content -LiteralPath $controlPath -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$control.token) -or
        [string]$control.port -ne [string]$port -or
        [string]::IsNullOrWhiteSpace([string]$health.serviceId) -or
        [string]$control.serviceId -ne [string]$health.serviceId) {
        throw 'Control state does not match the running service. Stop cancelled.'
    }
    $headers = @{ Authorization = 'Bearer ' + [string]$control.token }
    [void](Invoke-RestMethod -Uri ($baseUrl + '/control/stop') -Method Post -Headers $headers -TimeoutSec 5)
    Write-Host 'Graceful stop requested.'

    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 15) {
        Start-Sleep -Milliseconds 250
        try {
            $remaining = Invoke-RestMethod -Uri ($baseUrl + '/health') -Method Get -TimeoutSec 1
        } catch {
            Write-Host 'Service health endpoint is no longer reachable.'
            exit 0
        }
        if ($remaining.service -ne 'ghs-peer-stream' -or [string]$remaining.serviceId -ne [string]$health.serviceId) {
            throw 'The responding service changed during shutdown. No further action was taken.'
        }
    }
    throw 'Stop was requested, but health is still reachable after 15 seconds. No process was forcibly terminated.'
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
