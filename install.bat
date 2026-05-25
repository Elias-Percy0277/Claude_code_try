@echo off
title DataVis - Install

echo ================================
echo  Creating Conda Environment
echo ================================
echo.

cd /d "%~dp0"

echo [1/3] Creating env: datavis...
conda create -n datavis python=3.9 -y

echo.
echo [2/3] Installing Python deps...
call conda activate datavis
pip install -r requirements.txt

echo.
echo [3/3] Installing frontend...
cd frontend
call npm install
cd ..

echo.
echo Done! Environment: datavis
pause
