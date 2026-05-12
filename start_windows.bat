@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0" || exit /b 1

echo == Quant 4.0 Multi-Agent Windows launcher ==
echo Project: %CD%

set "PYTHON_BIN="
where py >nul 2>nul
if %ERRORLEVEL%==0 set "PYTHON_BIN=py -3"

if not defined PYTHON_BIN (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 set "PYTHON_BIN=python"
)

if not defined PYTHON_BIN (
  echo.
  echo Error: Python 3 is not installed or not available in PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_BIN% -m venv .venv
  if errorlevel 1 (
    echo.
    echo Error: failed to create virtual environment.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn, pandas, numpy, akshare, httpx" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-input -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Error: failed to install dependencies. Please check your network and Python environment.
    pause
    exit /b 1
  )
) else (
  echo Dependencies already available.
)

if not exist ".env" (
  if exist ".env.example" (
    echo Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    if errorlevel 1 (
      echo.
      echo Error: failed to create .env.
      pause
      exit /b 1
    )
  ) else (
    echo Warning: .env.example not found; continuing without .env.
  )
)

if not defined APP_HOST set "APP_HOST=127.0.0.1"
if not defined APP_PORT set "APP_PORT=8000"

for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$hostName=$env:APP_HOST; $start=[int]$env:APP_PORT; for($p=$start; $p -lt $start+50; $p++){ $listener=$null; try { $listener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse($hostName), $p); $listener.Start(); $listener.Stop(); Write-Output $p; break } catch { if($listener){ try { $listener.Stop() } catch {} } } }"') do set "PORT=%%P"

if not defined PORT (
  echo.
  echo Error: no available local port found from %APP_PORT% to %APP_PORT%+49.
  pause
  exit /b 1
)

set "URL=http://%APP_HOST%:%PORT%"
if not "%PORT%"=="%APP_PORT%" echo Port %APP_PORT% is busy or unavailable; using %PORT% instead.

echo Starting server at %URL%
start "" "%URL%"

".venv\Scripts\uvicorn.exe" app.main:app --host "%APP_HOST%" --port "%PORT%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Server exited with code %EXIT_CODE%.
  echo Troubleshooting:
  echo 1. If Windows Firewall asks for network permission, allow local private network access.
  echo 2. Try another port: set APP_PORT=8010 then run start_windows.bat again.
  echo 3. If dependencies are broken, delete .venv and run this script again.
  pause
)

exit /b %EXIT_CODE%
