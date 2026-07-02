@echo off
echo Starting FastAPI Data Bridge...
cd /d "%~dp0..\data-bridge"
uvicorn main:app --port 5052
