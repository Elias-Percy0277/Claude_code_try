@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  WeChat Custody Service
echo ================================================
echo.

REM Check venv
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    echo          Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check region config (optional - has default template)
echo [1/3] Checking region configuration...
if exist "data\region_config.json" (
    echo [OK] Using custom region configuration
) else (
    echo [INFO] No custom region config found, using default template
    echo [INFO] Run calibrate.bat to create custom regions for better accuracy
)

REM Check Ollama
echo.
echo [2/3] Checking Ollama service...
ollama ls >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama service not running or not installed
    echo [INFO] AI features will not work without Ollama
    echo [INFO] Install: https://ollama.com
    echo [INFO] Run: ollama serve (after installation)
    echo.
) else (
    echo [OK] Ollama service is running
)

REM Start main program
echo.
echo [3/3] Starting WeChat Custody Service...
echo.

"venv\Scripts\python.exe" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Program exited with errors
    pause
)
