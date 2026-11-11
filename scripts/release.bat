@echo off
REM Tests, commits, tags vX.Y, pushes to GitHub and writes releases\orchsketch-vX.Y-src.zip.
setlocal
cd /d "%~dp0.."
for /f "delims=" %%v in ('.venv\Scripts\python.exe scripts\print_version.py') do set "VER=%%v"
if not defined VER goto noversion
echo Releasing OrchSketch v%VER%
set "QT_QPA_PLATFORM=offscreen"
echo [1/4] Running tests...
.venv\Scripts\python.exe -m pytest -q > test_results.txt 2>&1
if errorlevel 1 goto testfail
git rev-parse -q --verify "refs/tags/v%VER%" >nul && goto tagexists
echo [2/4] Committing and tagging...
git add -A
if exist build\commit_msg.txt (git commit -q -F build\commit_msg.txt) else (git commit -q -m "OrchSketch v%VER%")
git tag -a "v%VER%" -m "OrchSketch v%VER%"
if errorlevel 1 goto gitfail
echo [3/4] Pushing to GitHub (a sign-in window may open the first time)...
git push origin main
if errorlevel 1 goto pushfail
git push origin "v%VER%"
if errorlevel 1 goto pushfail
echo [4/4] Writing the source zip...
if not exist releases mkdir releases
git archive --format=zip --prefix=orchsketch-v%VER%/ -o "releases\orchsketch-v%VER%-src.zip" "v%VER%"
if errorlevel 1 goto gitfail
echo.
echo RELEASE OK: v%VER% pushed, zip in releases\
goto done
:noversion
echo ERROR: couldn't read the version. Has setup.bat run?
goto done
:testfail
echo ERROR: tests failed, nothing was released. See test_results.txt
goto done
:tagexists
echo Tag v%VER% already exists - nothing to do.
goto done
:gitfail
echo ERROR: a git step failed. Scroll up for the message.
goto done
:pushfail
echo ERROR: push failed. Your commit and tag are saved locally; run release.bat again after fixing.
echo (If it says the tag exists, push manually: git push origin main --tags)
:done
pause
