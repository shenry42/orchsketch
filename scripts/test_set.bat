@echo off
REM SPEC 7-8 full test-set pass: builds the 15 ear-test projects in Documents\OrchSketch\Projects\TestSet\
REM and checks the automatic pass/fail rules. Report: testset_report.txt
cd /d "%~dp0.."
set "QT_QPA_PLATFORM=offscreen"
echo Building the 15 test projects (about a minute)...
.venv\Scripts\python.exe scripts\testset.py
if errorlevel 1 (echo. & echo SOME CHECKS FAILED - see testset_report.txt) else (echo. & echo ALL AUTOMATIC CHECKS PASSED)
start "" notepad testset_report.txt
explorer "%USERPROFILE%\Documents\OrchSketch\Projects\TestSet"
pause
