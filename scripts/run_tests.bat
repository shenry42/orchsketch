@echo off
REM Runs the automated tests except the slowest sweeps (marked "slow"; release.bat runs everything).
REM Full output goes to test_results.txt. For the full run: run_tests.bat all
cd /d "%~dp0.."
set "QT_QPA_PLATFORM=offscreen"
echo Running tests...
set "SEL=-m "not slow""
if /i "%~1"=="all" set "SEL="
.venv\Scripts\python.exe -m pytest -v %SEL% > test_results.txt 2>&1
if errorlevel 1 (
  echo.
  echo TESTS FAILED - see test_results.txt
) else (
  echo.
  echo TESTS PASSED
)
pause
