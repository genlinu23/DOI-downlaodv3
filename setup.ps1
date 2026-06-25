# SciHubEVA one-time dev setup
# Usage: .\setup.ps1
# After this, just run: python app.py  (browser opens at http://localhost:8080)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "[1/2] Creating virtual environment..." -ForegroundColor Cyan
python -m venv .venv

Write-Host "[2/2] Installing dependencies..." -ForegroundColor Cyan
& .\.venv\Scripts\pip install `
    "nicegui>=2.0.0" lxml pathvalidate "pdfminer.six" `
    requests urllib3 PySocks

Write-Host ""
Write-Host "Setup done. To start the app:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "  python app.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "The browser will open automatically at http://localhost:8080" -ForegroundColor Cyan
