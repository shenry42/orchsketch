@echo off
REM OrchSketch - prerequisite check. Writes results to prereqs.txt in the OrchSketch folder.
cd /d "%~dp0.."
set "OUT=%CD%\prereqs.txt"
echo Checking prerequisites, please wait...
(
echo === OrchSketch prerequisite check ===
echo %date% %time%
ver
echo.
echo --- Python launcher: installed versions ---
py -0p
echo.
echo --- python on PATH ---
where python
python --version
echo.
echo --- Python 3.12 ---
py -3.12 -c "import sys,struct;print(sys.version, struct.calcsize('P')*8, 'bit')"
py -3.12 -m pip --version
echo.
echo --- Git ---
where git
git --version
git config --global user.name
git config --global user.email >nul && echo user.email is set|| echo user.email NOT set
git config --global credential.helper
echo.
echo --- GitHub CLI ---
where gh
echo.
echo --- FluidSynth ---
where fluidsynth
fluidsynth --version
where libfluidsynth-3.dll
echo.
echo --- Internet: PyPI and GitHub reachable? ---
py -3.12 -c "import urllib.request as u;print('pypi', u.urlopen('https://pypi.org/simple/mido/',timeout=10).status)"
py -3.12 -c "import urllib.request as u;print('github', u.urlopen('https://github.com',timeout=10).status)"
git ls-remote https://github.com/shenry42/orchsketch
echo git ls-remote exit code: %errorlevel%
echo.
echo --- Sound devices ---
powershell -NoProfile -Command "Get-CimInstance Win32_SoundDevice | ForEach-Object Name"
echo === end ===
) > "%OUT%" 2>&1
echo.
echo Done. Results saved to prereqs.txt - you can close this window.
pause
