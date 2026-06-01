@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================
echo  微信区域可视化校准工具
echo ================================================
echo.
echo 此工具将帮助你自定义消息截取区域
echo.
echo 使用步骤:
echo   1. 确保微信窗口已打开
echo   2. 运行此工具
echo   3. 按数字键选择区域类型
echo   4. 用鼠标框选对应区域
echo   5. 按 S 保存配置
echo.
echo 按任意键继续...
pause >nul

"venv\Scripts\python.exe" utils\interactive_calibrator.py

echo.
echo ================================================
echo  校准完成！
echo ================================================
echo.
pause
