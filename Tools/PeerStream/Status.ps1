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
    $health = Invoke-RestMethod -Uri ($baseUrl + '/health') -Method Get -TimeoutSec 2
    if ($health.service -ne 'ghs-peer-stream') {
        throw ('Port {0} is responding as another service.' -f $port)
    }
    Write-Host ('Player: {0}/' -f $baseUrl)
    Write-Host 'Public health:'
    Write-Output ($health | ConvertTo-Json -Depth 8)

    try {
        $control = Get-Content -LiteralPath (Join-Path $PSScriptRoot '.state\control.json') -Raw | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace([string]$control.token) -or
            [string]$control.port -ne [string]$port -or
            [string]::IsNullOrWhiteSpace([string]$health.serviceId) -or
            [string]$control.serviceId -ne [string]$health.serviceId) {
            throw 'Control state does not match the running service.'
        }
        $headers = @{ Authorization = 'Bearer ' + [string]$control.token }
        $details = Invoke-RestMethod -Uri ($baseUrl + '/control/status') -Method Get -Headers $headers -TimeoutSec 3
        Write-Host 'Detailed status:'
        Write-Output ($details | ConvertTo-Json -Depth 10)
    } catch {
        Write-Warning ('Detailed status unavailable: {0}' -f $_.Exception.Message)
    }
    exit 0
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
