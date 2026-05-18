@echo off
setlocal

set ICON_FLAG=
if exist "desktop\resources\icon.ico" (
    set ICON_FLAG=--icon desktop\resources\icon.ico
)

pyinstaller --onefile --windowed --name AbstractSearcher %ICON_FLAG% desktop\main.py

echo.
echo Build complete. Check dist\AbstractSearcher.exe
endlocal
