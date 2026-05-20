@echo off
chcp 65001 >nul
title Hermes Pet - Super Learning Assistant

REM === Edit these paths to match your system ===
set HERMES_HOME=%USERPROFILE%\.hermes
set HERMES_BIN=%APPDATA%\Python\Python314\Scripts\hermes.exe
set HERMES_AGENT_ROOT=%APPDATA%\Python\Python314\site-packages

echo ========================================
echo Hermes Pet - Starting...
echo ========================================
echo.

cd /d "%~dp0src"
python main.py
if errorlevel 1 (
    echo.
    echo Error! Check dependencies first.
    pause
)
