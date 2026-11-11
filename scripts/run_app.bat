@echo off
REM Starts OrchSketch from source.
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\src"
start "" ".venv\Scripts\pythonw.exe" -m orchsketch
