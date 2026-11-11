@echo off
REM Milestone 3: plays every audition sound (about 2 minutes). Results: sound_check_results.txt
cd /d "%~dp0.."
.venv\Scripts\python.exe scripts\sound_check.py
start "" notepad sound_check_results.txt
