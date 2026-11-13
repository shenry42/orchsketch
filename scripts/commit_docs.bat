@echo off
REM Commits only SPEC.md and STATUS.md (a docs-only commit, e.g. the Phase 2 plan before Milestone 7's code).
REM Nothing is pushed: release.bat pushes it together with the next version.
setlocal
cd /d "%~dp0.."
git add SPEC.md STATUS.md
git diff --cached --quiet && (echo Nothing to commit: SPEC.md and STATUS.md are already committed. & goto done)
git commit -q -m "docs: Phase 2 plan (SPEC 14: decisions, guardrails, milestones 7-12)" -- SPEC.md STATUS.md
if errorlevel 1 (echo ERROR: the commit failed. Scroll up for the message. & goto done)
echo.
echo DOCS COMMITTED:
git log --oneline -1
:done
pause
