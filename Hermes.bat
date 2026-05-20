@echo off
REM === Edit these paths to match your system ===
set HERMES_HOME=%USERPROFILE%\.hermes
set HERMES_BIN=%APPDATA%\Python\Python314\Scripts\hermes.exe
set HERMES_AGENT_ROOT=%APPDATA%\Python\Python314\site-packages
cd /d "%~dp0src"
python main.py
pause
