@echo off
setlocal
cd /d "%~dp0"

set "PY="
py -3.13 -c "import sys" >nul 2>nul && set "PY=py -3.13"
if not defined PY py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Vibrato needs Python 3.11 or newer. Install it from https://www.python.org and run setup.bat again.
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js 20.19+ or 22.12+ is required. Install it from https://nodejs.org and run setup.bat again.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo ==^> Creating virtual environment in .venv
  %PY% -m venv .venv
  if errorlevel 1 exit /b 1
)

set "VPY=%CD%\.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip wheel >nul

echo ==^> Installing the analysis backend
"%VPY%" -m pip install -e "backend[dev]"
if errorlevel 1 exit /b 1

echo ==^> Installing optional decoders and the WORLD vocoder
"%VPY%" -m pip install -e "backend[decoders]" || echo     PyAV could not be installed: MP3, M4A and AAC import fall back to libsndfile and audioread.
"%VPY%" -m pip install -e "backend[world]" || echo     pyworld could not be installed: the breathiness preview is disabled, everything else works.

if "%VIBRATO_NEURAL%"=="1" (
  echo ==^> Installing optional neural pitch tracking
  "%VPY%" -m pip install -e "backend[neural]" || echo     torch or torchcrepe could not be installed; CREPE stays unavailable.
)

echo ==^> Installing the interface
pushd frontend
if exist package-lock.json (
  call npm ci --no-audit --no-fund
) else (
  call npm install --no-audit --no-fund
)
if errorlevel 1 (
  popd
  exit /b 1
)

echo ==^> Building the interface
call npm run build
if errorlevel 1 (
  popd
  exit /b 1
)
popd

echo.
echo Setup complete. Start Vibrato with run.bat
exit /b 0
