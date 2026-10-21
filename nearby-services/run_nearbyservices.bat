@echo off
title Nearby Services WebGIS Launcher
echo ===================================================
echo   Starting Nearby Services WebGIS Project...
echo ===================================================

cd backend
echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Launching FastAPI Server & Initializing PostGIS...
start ..\frontend\index.html
python -m uvicorn main:app --reload --port 8000
pause