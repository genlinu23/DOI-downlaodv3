# SciHubEVA one-time dev setup
# Usage: .\setup.ps1
# After this, just run: python app.py

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "[1/3] Creating virtual environment..." -ForegroundColor Cyan
python -m venv .venv

Write-Host "[2/3] Installing dependencies..." -ForegroundColor Cyan
& .\.venv\Scripts\pip install `
    pyside6 lxml pathvalidate "pdfminer.six" `
    requests urllib3 darkdetect PySocks

Write-Host "[3/3] Compiling QML resources..." -ForegroundColor Cyan
& .\.venv\Scripts\pyside6-rcc SciHubEVA.qrc -o scihub_eva\resources.py

Write-Host ""
Write-Host "Setup done. To run the app:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "  python app.py" -ForegroundColor Yellow
