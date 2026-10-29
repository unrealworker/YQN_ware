# Run this script from the deployed GHSPeerStream directory.
$ErrorActionPreference = 'Stop'

try {
    $settingsPath = Join-Path $PSScriptRoot 'settings.json'
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    $port = 0
    if (-not [int]::TryParse([string]$settings.port, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        throw 'settings.json must contain a valid port (1-65535).'
    }
    $localHost = '127.0.0.1'
    if ([string]$settings.host -eq '::1' -or [string]$settings.host -eq '::') {
        $localHost = '[::1]'
    }
    $baseUrl = 'http://{0}:{1}' -f $localHost, $port

    function Get-ServiceHealth {
        try {
            Invoke-RestMethod -Uri ($baseUrl + '/health') -Method Get -TimeoutSec 1
        } catch {
            return $null
        }
    }

    $health = Get-ServiceHealth
    if ($null -ne $health) {
        if ($health.service -ne 'ghs-peer-stream') {
            throw ('Port {0} is responding as another service. Start cancelled.' -f $port)
        }
        if ($health.state -eq 'running') {
            Write-Host ('Already running. Player: {0}/' -f $baseUrl)
            exit 0
        }
        throw ('The service is in state "{0}". Start cancelled.' -f $health.state)
    }

    $nodePath = Join-Path $PSScriptRoot 'runtime\node.exe'
    $servicePath = Join-Path $PSScriptRoot 'service.cjs'
    $executablePath = [string]$settings.executablePath
    if (-not [IO.Path]::IsPathRooted($executablePath)) {
        $executablePath = Join-Path $PSScriptRoot $executablePath
    }
    $executablePath = [IO.Path]::GetFullPath($executablePath)
    foreach ($requiredPath in @($nodePath, $servicePath, $executablePath)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw ('Required file is missing: {0}' -f $requiredPath)
        }
    }

    $logsPath = Join-Path $PSScriptRoot 'logs'
    [void][IO.Directory]::CreateDirectory($logsPath)
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdoutPath = Join-Path $logsPath ('service-{0}.out.log' -f $stamp)
    $stderrPath = Join-Path $logsPath ('service-{0}.err.log' -f $stamp)
    $startOptions = @{
        FilePath = $nodePath
        ArgumentList = ('"{0}"' -f $servicePath)
        WorkingDirectory = $PSScriptRoot
        WindowStyle = 'Hidden'
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        PassThru = $true
    }
    $serviceProcess = Start-Process @startOptions
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 15) {
        $health = Get-ServiceHealth
        if ($null -ne $health) {
            if ($health.service -ne 'ghs-peer-stream') {
                throw ('Another service responded on port {0}. See logs: {1}' -f $port, $logsPath)
            }
            if ($health.state -eq 'running') {
                Write-Host ('Started. Player: {0}/' -f $baseUrl)
                Write-Host ('Logs: {0}' -f $logsPath)
                exit 0
            }
        }
        $serviceProcess.Refresh()
        if ($serviceProcess.HasExited) {
            throw ('Service exited with code {0}. See {1} and {2}' -f $serviceProcess.ExitCode, $stdoutPath, $stderrPath)
        }
        Start-Sleep -Milliseconds 250
    }
    throw ('No running health response within 15 seconds. The process was not terminated. See {0} and {1}' -f $stdoutPath, $stderrPath)
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
