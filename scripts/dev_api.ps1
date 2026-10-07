$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$env:PYTHONPATH = "$(Resolve-Path .\packages);$(Resolve-Path .\apps\api)"
Set-Location apps\api
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000