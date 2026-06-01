@echo off
title DataVis - Start

cls
echo ================================
echo  DataVis - Starting All Services
echo ================================
echo.

cd /d "%~dp0"

echo [INFO] Current Directory: %CD%
echo.

REM Use conda datavis environment
set PYTHON=C:\Users\nobody-yhy\.conda\envs\datavis\python.exe
set PIP_CMD=C:\Users\nobody-yhy\.conda\envs\datavis\Scripts\pip.exe

REM Check Python
echo [1/3] Checking Environment (conda datavis)...
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda datavis environment not found
    pause
    exit /b 1
)

REM Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed
    pause
    exit /b 1
)
echo [OK] Environment check completed
echo.

REM Check backend dependencies
echo [2/3] Checking Backend Dependencies...
"%PYTHON%" -c "import fastapi, pyecharts" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing backend dependencies...
    "%PIP_CMD%" install -r requirements.txt -q
)
echo [OK] Backend dependencies completed
echo.

REM Check frontend dependencies
echo [3/3] Checking Frontend Dependencies...
if not exist "frontend\node_modules\" (
    echo [INFO] Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)
echo [OK] Frontend dependencies completed
echo.

echo ================================
echo  Starting Services
echo ================================
echo.
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo  API Docs: http://localhost:8000/docs
echo.
echo  Press Ctrl+C to stop all services
echo ================================
echo.

REM Start Backend
start "DataVis-Backend" cmd /k "cd /d "%~dp0" && title DataVis Backend && echo [BACKEND] Starting... && "%PYTHON%" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --log-level info"

REM Wait for backend to start
timeout /t 3 /nobreak >nul

REM Start Frontend
start "DataVis-Frontend" cmd /k "cd /d "%~dp0frontend" && title DataVis Frontend && echo [FRONTEND] Starting... && npm run dev"

echo.
echo ================================
echo  All Services Started!
echo ================================
echo.
echo Press any key to close all services...
pause >nul

echo.
echo Stopping services...
taskkill /FI "WINDOWTITLE eq DataVis-Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq DataVis-Frontend*" /F >nul 2>&1
echo Done.
timeout /t 1 /nobreak >nul
