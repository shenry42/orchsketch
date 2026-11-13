@echo off
REM SPEC 8 second benchmark: builds the ear-test projects for your own progressions (tests\data\benchmark\)
REM in Documents\OrchSketch\Projects\Benchmark\, plus the Phase 2 ear-test sets (SPEC 14) in Benchmark\Phase2\
REM and (v1.3, Milestone 8) Benchmark\Phase2b\,
REM and checks the automatic pass/fail rules. Report: benchmark_report.txt (with generation times)
cd /d "%~dp0.."
set "QT_QPA_PLATFORM=offscreen"
echo Building the benchmark projects and the Phase 2 ear-test sets (a few minutes).
.venv\Scripts\python.exe scripts\testset.py --benchmark
if errorlevel 1 (echo. & echo SOME CHECKS FAILED - see benchmark_report.txt) else (echo. & echo ALL AUTOMATIC CHECKS PASSED)
start "" notepad benchmark_report.txt
explorer "%USERPROFILE%\Documents\OrchSketch\Projects\Benchmark"
pause
