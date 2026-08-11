$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$uvCacheRoot = Join-Path $projectRoot ".cache\uv"

New-Item -ItemType Directory -Path $uvCacheRoot -Force | Out-Null
$env:UV_CACHE_DIR = $uvCacheRoot

Push-Location $backendRoot
try {
    Write-Host "Checking and upgrading the database schema..."
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed. The backend was not started."
    }

    Write-Host "Database is ready. Starting the ShuttleCube backend..."
    uv run uvicorn shuttlecube.app:create_app --factory --reload --port 8001
    if ($LASTEXITCODE -ne 0) {
        throw "The backend process exited with an error."
    }
}
finally {
    Pop-Location
}
