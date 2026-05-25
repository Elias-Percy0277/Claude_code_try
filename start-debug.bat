@echo off
REM 调试版本 - 显示所有输出
echo 开始调试...
echo.

echo 当前目录: %CD%
echo.

echo [1] 检查 Python:
python --version
echo.

echo [2] 检查 Node.js:
node --version
echo.

echo [3] 检查目录结构:
dir /b
echo.

echo [4] 检查 requirements.txt:
type requirements.txt
echo.

echo 调试完成，按任意键退出...
pause >nul
