@echo off
cd /d "%~dp0"

rem tunneld detection/elevation lives in gps_qt/tunneld.py (shared by the packaged exe).
rem This script only launches the App via pythonw, with no console window.
start "" pythonw -m gps_qt.main
exit
