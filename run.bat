@echo off
cd /d "%~dp0"

rem tunneld 的偵測與提權啟動已經在 gps_qt/tunneld.py 裡（打包後的 exe 共用同一份邏輯），
rem 這裡只負責用 pythonw 啟動 App，不顯示主控台視窗。
start "" pythonw -m gps_qt.main
exit
