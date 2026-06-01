@echo off
title DataVis Frontend

cls
echo ================================
echo  DataVis Frontend - Starting
echo ================================
echo.

cd /d "%~dp0frontend"

echo [INFO] Current Directory: %CD%
echo.

REM Check Node.js
echo [1/2] Checking Node.js...
node --version
if errorlevel 1 (
    echo [ERROR] Node.js is not installed
    pause
    exit /b 1
)
echo.

REM Check dependencies
echo [2/2] Checking Dependencies...
if not exist "node_modules\" (
    echo [INFO] Installing dependencies...
    call npm install
)
echo [OK] Dependencies completed
echo.

echo ================================
echo  Starting Frontend Service
echo ================================
echo.
echo  Frontend: http://localhost:5173
echo.
echo  Press Ctrl+C to stop the service
echo ================================
echo.

REM Start Frontend
npm run dev

pause
