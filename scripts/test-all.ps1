<#
.SYNOPSIS
    Run the full verification suite: backend lint, backend tests and frontend build.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$failures = @()

Push-Location $root
try {
    Write-Host '== ruff ==' -ForegroundColor Cyan
    & $python -m ruff check backend\app backend\tests --output-format=concise
    if ($LASTEXITCODE -ne 0) { $failures += 'ruff' }

    Write-Host '== pytest ==' -ForegroundColor Cyan
    Push-Location backend
    $env:PYTHONPATH = '.'
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { $failures += 'pytest' }
    Pop-Location

    Write-Host '== frontend build ==' -ForegroundColor Cyan
    Push-Location frontend
    npm run build
    if ($LASTEXITCODE -ne 0) { $failures += 'frontend build' }
    Pop-Location
}
finally {
    Pop-Location
}

if ($failures.Count -gt 0) {
    Write-Host ("FAILED: " + ($failures -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host 'All checks passed.' -ForegroundColor Green
