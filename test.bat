@echo off
setlocal
cd /d "%~dp0"

set "V=%CD%\.venv\Scripts"
if not exist "%V%\python.exe" (
  echo Run setup.bat first.
  exit /b 1
)

pushd backend
echo ==^> backend: ruff
"%V%\ruff.exe" check vibrato tests || goto fail
"%V%\ruff.exe" format --check vibrato tests || goto fail
echo ==^> backend: mypy
"%V%\mypy.exe" vibrato || goto fail
echo ==^> backend: pytest
"%V%\python.exe" -m pytest || goto fail
popd

pushd frontend
echo ==^> frontend: typecheck
call npm run --silent typecheck || goto fail
echo ==^> frontend: eslint
call npm run --silent lint || goto fail
echo ==^> frontend: prettier
call npm run --silent format:check || goto fail
echo ==^> frontend: vitest
call npm run --silent test || goto fail

if /i "%~1"=="--e2e" (
  echo ==^> frontend: build
  call npm run --silent build || goto fail
  echo ==^> frontend: playwright
  set "VIBRATO_PYTHON=%V%\python.exe"
  call npx playwright test || goto fail
)
popd

echo.
echo All checks passed.
exit /b 0

:fail
popd
echo.
echo Checks failed.
exit /b 1
