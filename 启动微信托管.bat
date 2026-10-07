@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  微信 AI 托管服务
echo  WeChat Custody Service
echo ================================================
echo.

if not exist "env\python.exe" (
    echo [错误] Conda 环境未找到
    echo 请确保 env 目录存在
    pause
    exit /b 1
)

echo [1/4] 检查 YOLO 模型...
if exist "runs\detect\runs\detect\train3\weights\best.pt" (
    echo [OK] 已找到训练好的 YOLO 模型
) else (
    echo [提示] 未找到训练模型，将使用预训练模型
)

echo.
echo [2/4] 检查区域配置...
if exist "data\region_config.json" (
    echo [OK] 使用自定义区域配置
) else (
    echo [提示] 未找到自定义区域配置，使用默认模板
    echo [提示] 运行 calibrate.bat 可创建自定义区域
)

echo.
echo [3/4] 检查 Ollama 服务...
ollama ls >nul 2>&1
if errorlevel 1 (
    echo [警告] Ollama 服务未运行
    echo [提示] 请运行: ollama serve
    echo.
) else (
    echo [OK] Ollama 服务正在运行
)

echo.
echo [4/4] 启动微信托管服务...
echo.

"env\python.exe" main.py

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出
    pause
)
