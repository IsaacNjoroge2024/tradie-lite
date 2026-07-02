
@echo off
echo Starting FastAPI Data Bridge...
:: Close any existing process holding port 5052
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 5052 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" >nul 2>&1
cd /d "%~dp0..\data-bridge"
python -m uvicorn main:app --port 5052
