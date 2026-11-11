@echo off
REM Runs all automated tests. Full output goes to test_results.txt.
cd /d "%~dp0.."
set "QT_QPA_PLATFORM=offscreen"
echo Running tests...
.venv\Scripts\python.exe -m pytest -v > test_results.txt 2>&1
if errorlevel 1 (
  echo.
  echo TESTS FAILED - see test_results.txt
) else (
  echo.
  echo TESTS PASSED
)
pause
