@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  Incubrix Growth Engine - Build Installer
echo ============================================
echo.

REM Prefer active venv python when available
set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
set "ROOT=%cd%"

"%PY%" -c "import sys; print(sys.executable)"
if errorlevel 1 (
  echo ERROR: Python not found.
  exit /b 1
)

echo [1/3] Installing PyInstaller + pywin32 + winshell...
"%PY%" -m pip install --upgrade pip pyinstaller pywin32 winshell
if errorlevel 1 (
  echo ERROR: Failed to install build dependencies.
  exit /b 1
)

echo.
echo [2/3] Building installer wizard ^(onedir^): Setup.exe + _internal...
if exist "dist\Setup" rmdir /s /q "dist\Setup"
if exist "build\Setup" rmdir /s /q "build\Setup"

"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name "Setup" ^
  --distpath "%ROOT%\dist" ^
  --workpath "%ROOT%\build" ^
  --specpath "%ROOT%\build" ^
  --hidden-import win32com.client ^
  --hidden-import winshell ^
  --collect-submodules win32com ^
  --add-data "%ROOT%\app.py;." ^
  --add-data "%ROOT%\run.py;." ^
  --add-data "%ROOT%\requirements.txt;." ^
  --add-data "%ROOT%\.env;." ^
  --add-data "%ROOT%\src;src" ^
  --add-data "%ROOT%\installer;installer" ^
  "%ROOT%\installer\setup_ui.py"

if errorlevel 1 (
  echo ERROR: Setup wizard PyInstaller build failed.
  exit /b 1
)

echo.
echo [3/3] Verifying build outputs...
if not exist "dist\Setup\Setup.exe" (
  echo ERROR: dist\Setup\Setup.exe was not created.
  exit /b 1
)
if not exist "dist\Setup\_internal" (
  echo ERROR: dist\Setup\_internal was not created.
  exit /b 1
)

echo.
echo Build complete.
echo   Setup root:  dist\Setup\Setup.exe
echo   Payload:     dist\Setup\_internal\
echo.
endlocal
exit /b 0
