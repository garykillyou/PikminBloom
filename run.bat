@echo off
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_tunneld.ps1"

if %errorlevel%==1 echo Starting tunneld, admin permission required, please wait...
if %errorlevel%==1 ping -n 4 127.0.0.1 >nul

start "" pythonw -m gps_qt.main
exit
