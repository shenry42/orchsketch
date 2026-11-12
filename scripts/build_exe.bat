@echo off
REM Builds the packaged app: build\exe\dist\OrchSketch\OrchSketch.exe (folder build: fast start).
REM Bundles the data files (instruments, rules, presets), the FluidSynth DLLs and the GeneralUser GS SoundFont,
REM runs the built app's self-check, and zips the folder to releases\OrchSketch-vX.Y-win64.zip.
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%ROOT%\build\exe_build_log.txt"
if not exist build mkdir build
for /f "delims=" %%v in ('.venv\Scripts\python.exe scripts\print_version.py') do set "VER=%%v"
if not defined VER goto novenv
for /f "delims=" %%d in ('.venv\Scripts\python.exe scripts\print_dll_dir.py') do set "DLLDIR=%%d"
if not defined DLLDIR goto nofs
if not exist "%ROOT%\vendor\soundfonts\GeneralUser-GS.sf2" goto nofs
echo [1/3] Building OrchSketch v%VER% (2-4 minutes)...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name OrchSketch ^
  --paths "%ROOT%\src" ^
  --add-data "%ROOT%\src\orchsketch\data;orchsketch\data" ^
  --add-binary "%DLLDIR%\*.dll;fluidsynth" ^
  --add-data "%ROOT%\vendor\soundfonts\GeneralUser-GS.sf2;soundfonts" ^
  --add-data "%ROOT%\vendor\soundfonts\LICENSE.txt;soundfonts" ^
  --hidden-import fluidsynth ^
  --exclude-module music21 --exclude-module matplotlib --exclude-module numpy --exclude-module tkinter ^
  --exclude-module pytest ^
  --distpath "%ROOT%\build\exe\dist" --workpath "%ROOT%\build\exe\work" --specpath "%ROOT%\build\exe" ^
  "%ROOT%\scripts\orchsketch_main.py" > "%LOG%" 2>&1
if errorlevel 1 goto failed
set "EXE=%ROOT%\build\exe\dist\OrchSketch\OrchSketch.exe"
if not exist "%EXE%" goto failed
echo [2/3] Self-check of the built app (you should hear a short string chord)...
start "" /wait "%EXE%" --self-check
type "%USERPROFILE%\Documents\OrchSketch\logs\self_check.txt"
copy /y "%USERPROFILE%\Documents\OrchSketch\logs\self_check.txt" "%ROOT%\build\exe_self_check.txt" >nul
findstr /c:"SELF-CHECK OK" "%ROOT%\build\exe_self_check.txt" >nul || goto checkfail
echo [3/3] Zipping to releases\OrchSketch-v%VER%-win64.zip...
if not exist releases mkdir releases
powershell -NoProfile -Command "Compress-Archive -Force -Path '%ROOT%\build\exe\dist\OrchSketch' -DestinationPath '%ROOT%\releases\OrchSketch-v%VER%-win64.zip'" >> "%LOG%" 2>&1
echo.
echo BUILD OK: build\exe\dist\OrchSketch\OrchSketch.exe
explorer "%ROOT%\build\exe\dist\OrchSketch"
goto done
:novenv
echo ERROR: couldn't read the version. Run scripts\setup.bat first.
goto done
:nofs
echo ERROR: FluidSynth or the SoundFont is missing. Run scripts\setup.bat first.
goto done
:failed
echo ERROR: build failed. See build\exe_build_log.txt
goto done
:checkfail
echo ERROR: the built app's self-check failed. See build\exe_self_check.txt
:done
pause
