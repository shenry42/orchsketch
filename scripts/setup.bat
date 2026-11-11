@echo off
REM OrchSketch one-time setup: Python 3.12, packages, FluidSynth, SoundFont, Git.
REM Safe to run again: it skips anything already done.
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%ROOT%\setup_log.txt"
echo OrchSketch setup - this can take 5-10 minutes. Details go to setup_log.txt
echo === setup %date% %time% === > "%LOG%"

REM ---- 1. Python 3.12 ----
set "PY312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY312%" goto havepy
echo [1/6] Installing Python 3.12...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
:havepy
if not exist "%PY312%" goto err_py
"%PY312%" --version >> "%LOG%" 2>&1

REM ---- 2. Virtual environment ----
if exist ".venv\Scripts\python.exe" goto havevenv
echo [2/6] Creating the project's Python environment...
"%PY312%" -m venv .venv >> "%LOG%" 2>&1
:havevenv
set "VPY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%VPY%" goto err_venv

REM ---- 3. Packages ----
echo [3/6] Installing Python packages (the biggest step)...
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
"%VPY%" -m pip install -r requirements-dev.txt >> "%LOG%" 2>&1
if errorlevel 1 goto err_pip
"%VPY%" -m pip freeze > requirements.lock.txt

REM ---- 4 + 5. FluidSynth and SoundFont ----
echo [4/6] Downloading FluidSynth and the GeneralUser GS SoundFont...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\get_vendor.ps1" -Root "%ROOT%" >> "%LOG%" 2>&1
if errorlevel 1 goto err_vendor

REM ---- 6. Git ----
echo [5/6] Setting up Git...
git config --global user.name >nul 2>&1 || call :askname
git config --global user.email >nul 2>&1 || call :askemail
if exist ".git" goto havegit
git init -b main >> "%LOG%" 2>&1
git remote add origin https://github.com/shenry42/orchsketch.git >> "%LOG%" 2>&1
git fetch origin >> "%LOG%" 2>&1
if errorlevel 1 goto err_git
git reset --hard origin/main >> "%LOG%" 2>&1
git branch --set-upstream-to=origin/main main >> "%LOG%" 2>&1
:havegit

echo [6/6] Checking everything...
"%VPY%" scripts\verify_setup.py >> "%LOG%" 2>&1
if errorlevel 1 goto err_verify
echo.
echo SETUP OK. You can close this window.
goto done

:askname
set "GN=Sam"
set /p "GN=Name to show on your Git commits [press Enter for Sam]: "
git config --global user.name "%GN%"
exit /b
:askemail
set "GE=shenry42@users.noreply.github.com"
set /p "GE=Email for Git commits [press Enter for shenry42@users.noreply.github.com]: "
git config --global user.email "%GE%"
exit /b

:err_py
echo ERROR: Python 3.12 did not install. See setup_log.txt
goto done
:err_venv
echo ERROR: could not create the Python environment. See setup_log.txt
goto done
:err_pip
echo ERROR: package install failed. See setup_log.txt
goto done
:err_vendor
echo ERROR: FluidSynth or SoundFont download failed. See setup_log.txt
goto done
:err_git
echo ERROR: could not reach the GitHub repo. See setup_log.txt
goto done
:err_verify
echo ERROR: final check failed. See setup_log.txt
goto done

:done
echo === end %date% %time% === >> "%LOG%"
pause
