@echo off
REM Milestone 1 spike: builds build\spike\dist\OrchSketchAudioSpike.exe (FluidSynth + SoundFont inside).
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
if not exist build mkdir build
for /f "delims=" %%d in ('.venv\Scripts\python.exe scripts\print_dll_dir.py') do set "DLLDIR=%%d"
if not defined DLLDIR goto nofs
echo Building the audio test .exe (about a minute)...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --console --name OrchSketchAudioSpike ^
  --paths "%ROOT%\src" ^
  --add-binary "%DLLDIR%\*.dll;fluidsynth" ^
  --add-data "%ROOT%\vendor\soundfonts\GeneralUser-GS.sf2;soundfonts" ^
  --distpath "%ROOT%\build\spike\dist" --workpath "%ROOT%\build\spike\work" --specpath "%ROOT%\build\spike" ^
  "%ROOT%\scripts\spike_audio.py" > "%ROOT%\build\spike_build_log.txt" 2>&1
if errorlevel 1 goto failed
echo.
echo BUILD OK: build\spike\dist\OrchSketchAudioSpike.exe
explorer "%ROOT%\build\spike\dist"
goto done
:nofs
echo ERROR: FluidSynth not found. Run scripts\setup.bat first.
goto done
:failed
echo ERROR: build failed. See build\spike_build_log.txt
:done
pause
