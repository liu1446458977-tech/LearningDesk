@echo off
chcp 65001 >nul
title Hermes Pet - 安装依赖

echo ========================================
echo Hermes Pet - 小马桌面悬浮窗
echo ========================================
echo.

echo [1/3] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)
python --version
echo ✅ Python 已安装
echo.

echo [2/3] 安装依赖包...
cd /d "%~dp0"
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)
echo ✅ 依赖安装完成
echo.

echo [3/3] 安装完成！
echo.
echo ========================================
echo 现在你可以：
echo   - 双击 "run.bat" 运行程序
echo   - 或者双击 "build.bat" 打包成 exe
echo ========================================
echo.
pause
