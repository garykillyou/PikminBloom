@echo off
cd /d "%~dp0"

echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt -r requirements-build.txt || goto :error

echo [2/2] Building...
python -m PyInstaller --noconfirm --clean PinDrift.spec || goto :error

echo.
echo Build finished: dist\PinDrift\PinDrift.exe
pause
exit /b 0

:error
echo.
echo Build FAILED.
pause
exit /b 1
