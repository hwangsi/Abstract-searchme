@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: .venv not found. Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Installing/updating PyInstaller...
python -m pip install --quiet pyinstaller

echo.
echo Building AbstractSearcher.exe ...
pyinstaller build\abstract_searcher.spec --clean --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo BUILD FAILED
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  Done: dist\AbstractSearcher.exe
for %%F in (dist\AbstractSearcher.exe) do echo  Size: %%~zF bytes
echo ============================================================
endlocal
