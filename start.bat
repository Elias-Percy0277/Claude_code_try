@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  WeChat Custody Service
echo  微信 AI 托管服务
echo ================================================
echo.

REM Check conda environment
if not exist "env\python.exe" (
    echo [ERROR] Conda environment not found!
    echo Please ensure the 'env' directory exists
    pause
    exit /b 1
)

REM Check trained YOLO model
echo [1/4] Checking YOLO model...
if exist "runs\detect\runs\detect\train3\weights\best.pt" (
    echo [OK] Trained YOLO model found
) else (
    echo [WARNING] Trained model not found, using pretrained model
)

REM Check region config (optional - has default template)
echo.
echo [2/4] Checking region configuration...
if exist "data\region_config.json" (
    echo [OK] Using custom region configuration
) else (
    echo [INFO] No custom region config found, using default template
    echo [INFO] Run calibrate.bat to create custom regions for better accuracy
)

REM Check Ollama
echo.
echo [3/4] Checking Ollama service...
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
echo [4/4] Starting WeChat Custody Service...
echo.

"env\python.exe" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Program exited with errors
    pause
)
