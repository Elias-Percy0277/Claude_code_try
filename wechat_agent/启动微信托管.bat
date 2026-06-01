@echo off
cd /d "%~dp0"

echo ================================================
echo  微信托管 AI 服务
echo ================================================
echo.

REM 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    echo          Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM 检查区域配置
echo [1/3] Checking region configuration...
if not exist "data\region_config.json" (
    echo [WARNING] Region configuration not found!
    echo.
    echo Please run the calibrator first.
    echo.
    echo Run: calibrate.bat
    echo   Or: venv\Scripts\python.exe utils\interactive_calibrator.py
    echo.
    choice /C YN /M "Run calibrator now"
    if errorlevel 2 (
        echo Cancelled.
        pause
        exit /b 1
    )
    echo.
    echo Starting calibrator...
    "venv\Scripts\python.exe" utils\interactive_calibrator.py
    if errorlevel 1 (
        echo Calibrator failed or was cancelled.
        pause
        exit /b 1
    )
    echo.
)

REM 检查 Ollama
echo [2/3] Checking Ollama service...
ollama list >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama service not running
    echo Please run: ollama serve
    echo.
)

REM 启动程序
echo [3/3] Starting WeChat Custody Service...
echo.

"venv\Scripts\python.exe" main.py

pause
