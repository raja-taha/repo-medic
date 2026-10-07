$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = "$(Resolve-Path .\packages)"
Set-Location services\worker
arq worker.WorkerSettings