@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

rem Prefer the project environment; otherwise use Python from PATH.
set "BUILD_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "BUILD_PYTHON=%CD%\.venv\Scripts\python.exe"

rem No arguments builds both platforms. Forward explicit options unchanged.
if "%~1"=="" (
    "%BUILD_PYTHON%" src\build_all.py --platform all
) else (
    "%BUILD_PYTHON%" src\build_all.py %*
)
set "BUILD_RESULT=%ERRORLEVEL%"
popd
exit /b %BUILD_RESULT%
