@echo off
REM Milestone 2: runs the rule checker on the hand-made examples. Output: checker_report.txt
cd /d "%~dp0.."
.venv\Scripts\python.exe scripts\checker_report.py
start "" notepad checker_report.txt
pause
