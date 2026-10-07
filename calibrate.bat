@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  微信托管 - 模板校准工具
echo  Template Calibration Tool
echo ================================================
echo.

REM Check conda environment
if not exist "env\python.exe" (
    echo [错误] Conda 环境未找到！
    echo 请确保 'env' 目录存在
    pause
    exit /b 1
)

REM Check OpenCV
echo [1/2] 检查依赖...

REM Start calibration tool
echo.
echo [2/2] 启动校准工具...
echo.
echo 提示:
echo - 请确保微信客户端已打开
echo - 工具会截取微信窗口并显示检测区域
echo - 按任意键关闭预览窗口
echo.

"env\python.exe" utils\calibrate_template.py

if errorlevel 1 (
    echo.
    echo [错误] 校准工具异常退出
    pause
)
