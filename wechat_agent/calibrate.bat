@echo off
cd /d "%~dp0"

echo ================================================
echo  Screen Region Calibrator
echo ================================================
echo.
echo This tool helps you mark message regions on screen.
echo.
echo Steps:
echo   1. Press 1-5 to select region type
echo   2. Drag mouse to select region
echo   3. Press S to save when done
echo.
echo Press any key to start...
pause >nul

"venv\Scripts\python.exe" utils\interactive_calibrator.py

if exist "data\region_config.json" (
    echo.
    echo Success! Configuration saved to data\region_config.json
) else (
    echo.
    echo No configuration saved.
)

echo.
pause
