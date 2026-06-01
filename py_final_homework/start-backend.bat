@echo off
title DataVis Backend

cls
echo ================================
echo  DataVis Backend - Starting
echo ================================
echo.

cd /d "%~dp0"

echo [INFO] Current Directory: %CD%
echo.

REM Use conda datavis environment
set PYTHON=C:\Users\nobody-yhy\.conda\envs\datavis\python.exe
set PIP_CMD=C:\Users\nobody-yhy\.conda\envs\datavis\Scripts\pip.exe

REM Check Python
echo [1/2] Checking Python (conda datavis)...
"%PYTHON%" --version
if errorlevel 1 (
    echo [ERROR] conda datavis environment not found
    pause
    exit /b 1
)
echo.

REM Check dependencies
echo [2/2] Checking Dependencies...
"%PYTHON%" -c "import fastapi, uvicorn, pandas, pyecharts" 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    "%PIP_CMD%" install -r requirements.txt -q
)
echo [OK] Dependencies completed
echo.

echo ================================
echo  Starting Backend Service
echo ================================
echo.
echo  Backend:  http://localhost:8000
echo  API Docs: http://localhost:8000/docs
echo.
echo  Press Ctrl+C to stop the service
echo ================================
echo.

REM Start Backend
"%PYTHON%" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --log-level info

pause
