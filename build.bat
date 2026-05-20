@echo off
chcp 65001 >nul
title Hermes Pet - 打包成 exe

echo ========================================
echo Hermes Pet - 打包 exe
echo ========================================
echo.

echo [1/3] 检查 PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
)
echo ✅ PyInstaller 已准备
echo.

echo [2/3] 开始打包...
cd /d "%~dp0"
pyinstaller --clean hermespet.spec
if errorlevel 1 (
    echo ❌ 打包失败
    pause
    exit /b 1
)
echo ✅ 打包完成
echo.

echo [3/3] 查找生成的 exe...
if exist "dist\HermesPet.exe" (
    echo.
    echo ========================================
    echo ✅ 打包成功！
    echo 位置: %~dp0dist\HermesPet.exe
    echo ========================================
    explorer dist
) else (
    echo ❌ 未找到生成的 exe
)
echo.
pause
