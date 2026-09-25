@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Vibrato is not set up yet. Run setup.bat first.
  exit /b 1
)

if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

if "%VIBRATO_HOST%"=="" set "VIBRATO_HOST=127.0.0.1"
if "%VIBRATO_PORT%"=="" set "VIBRATO_PORT=8765"
if /i "%~1"=="--dev" goto dev
if /i "%~1"=="--help" goto help

if not exist "frontend\dist\index.html" (
  echo ==^> Building the interface for the first run
  pushd frontend
  call npm run build
  if errorlevel 1 (
    popd
    exit /b 1
  )
  popd
)

echo Vibrato is starting on http://%VIBRATO_HOST%:%VIBRATO_PORT% - press Ctrl+C to stop
if /i "%~1"=="--no-browser" (
  ".venv\Scripts\python.exe" -m vibrato
) else (
  ".venv\Scripts\python.exe" -m vibrato --open
)
exit /b %errorlevel%

:dev
start "Vibrato analysis server" ".venv\Scripts\python.exe" -m vibrato --reload
set "VIBRATO_API=http://%VIBRATO_HOST%:%VIBRATO_PORT%"
pushd frontend
call npx vite --host 127.0.0.1 --port 5173 --open
popd
exit /b 0

:help
echo Usage: run.bat [--dev ^| --no-browser]
echo   default       serve the built interface and the analysis server on http://%VIBRATO_HOST%:%VIBRATO_PORT%
echo   --dev         hot-reloading interface on http://127.0.0.1:5173 and an auto-reloading backend
echo   --no-browser  do not open a browser window
echo A .env file in the project root is loaded automatically if present (see .env.example)
exit /b 0
