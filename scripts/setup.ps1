<#
.SYNOPSIS
    Prepare a local CloudOps Sentinel development environment (Windows).
.DESCRIPTION
    Creates the virtual environment, installs backend and frontend dependencies,
    and creates backend/.env from the example if it does not exist yet.
    It never overwrites an existing .env.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not (Test-Path '.venv')) {
        Write-Host 'Creating Python virtual environment…'
        python -m venv .venv
    }

    Write-Host 'Installing backend dependencies…'
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    & .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt --quiet

    if (-not (Test-Path 'backend\.env')) {
        Copy-Item '.env.example' 'backend\.env'
        Write-Host 'Created backend\.env from .env.example — set SECRET_KEY and passwords before shared use.'
    }

    if (-not $SkipFrontend) {
        Write-Host 'Installing frontend dependencies…'
        Push-Location frontend
        npm install --no-audit --no-fund
        Pop-Location
    }

    Write-Host ''
    Write-Host 'Setup complete. Start the API with:' -ForegroundColor Green
    Write-Host '  cd backend; $env:PYTHONPATH="."; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload'
    Write-Host 'Start the UI with:'
    Write-Host '  cd frontend; npm run dev'
}
finally {
    Pop-Location
}
