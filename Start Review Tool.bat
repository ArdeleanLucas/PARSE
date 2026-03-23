@echo off
setlocal

rem Source Explorer dev launcher
rem - Runs from this project folder no matter where the batch file was launched from
rem - Starts the custom range-request server
rem - Opens review_tool_dev.html through http://localhost:8766/

set "PROJECT_DIR=%~dp0"
set "SERVER_SCRIPT=python\thesis_server.py"
set "DEV_PAGE=review_tool_dev.html"
set "URL=http://localhost:8766/review_tool_dev.html"

pushd "%PROJECT_DIR%" >nul 2>&1 || (
  echo [ERROR] Could not switch to the project directory:
  echo         %PROJECT_DIR%
  pause
  exit /b 1
)

if not exist "%SERVER_SCRIPT%" (
  echo [ERROR] Missing server script: %SERVER_SCRIPT%
  pause
  popd >nul
  exit /b 1
)

if not exist "%DEV_PAGE%" (
  echo [ERROR] Missing dev page: %DEV_PAGE%
  pause
  popd >nul
  exit /b 1
)

set "PYTHON_CMD="
where py >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>&1 && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo [ERROR] Could not find Python on PATH.
  echo         Install Python or make sure ^"py^" / ^"python^" works in Command Prompt.
  pause
  popd >nul
  exit /b 1
)

echo ============================================================
echo Source Explorer - Dev Launcher
echo ============================================================
echo [1/3] Project directory:
echo       %CD%
echo.
echo [2/3] Starting local server in a separate window...
echo       Command: %PYTHON_CMD% %SERVER_SCRIPT%
echo       If port 8766 is already in use, close the old server window first.
start "Source Explorer Server" cmd /k "cd /d ""%CD%"" && %PYTHON_CMD% %SERVER_SCRIPT%"
echo.
echo [3/3] Waiting a moment, then opening:
echo       %URL%
timeout /t 2 /nobreak >nul

set "CHROME_EXE="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_EXE if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_EXE if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if defined CHROME_EXE (
  echo       Using Chrome:
  echo       %CHROME_EXE%
  start "" "%CHROME_EXE%" "%URL%"
) else (
  echo       Chrome not found in common locations. Using the default browser instead.
  start "" "%URL%"
)

echo.
echo Done. Leave the server window open while you use the review tool.

popd >nul
endlocal
exit /b 0
