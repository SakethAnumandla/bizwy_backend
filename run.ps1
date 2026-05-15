# Start API + Redis + Postgres (uses DATABASE_URL from .env)
$ErrorActionPreference = "Stop"
$env:PATH = "C:\Program Files\Docker\Docker\resources\bin;$env:PATH"
Set-Location $PSScriptRoot

if (-not (Test-Path .env)) {
    Write-Host "Missing .env — copy .env.example and set DATABASE_URL" -ForegroundColor Red
    exit 1
}

Write-Host "Creating tables on cloud database (if needed)..." -ForegroundColor Cyan
python scripts/init_db.py

Write-Host "Starting Docker (backend + redis)..." -ForegroundColor Cyan
docker compose up -d --build

Start-Sleep -Seconds 4
try {
    $h = Invoke-RestMethod -Uri http://localhost:8000/health
    Write-Host "Health:" ($h | ConvertTo-Json -Compress) -ForegroundColor Green
} catch {
    Write-Host "API not ready yet. Check: docker compose logs backend" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "API:  http://localhost:8000" -ForegroundColor Green
Write-Host "Docs: http://localhost:8000/docs" -ForegroundColor Green
docker compose ps
