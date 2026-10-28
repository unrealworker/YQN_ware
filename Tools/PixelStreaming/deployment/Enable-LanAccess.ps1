#Requires -Version 5.1
param([ValidateRange(1,65535)][int]$HttpPort=8080,[Parameter(Mandatory=$true)][string]$ApplicationPath,[switch]$PlanOnly)
& (Join-Path $PSScriptRoot 'Configure-NetworkAccess.ps1') -HttpPort $HttpPort -ApplicationPath $ApplicationPath -Scope LAN -PlanOnly:$PlanOnly
