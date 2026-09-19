@echo off
setlocal
cd /d "%~dp0\.."
python intelligence\run_nhl_intelligence_cycle.py --publish-stage
if errorlevel 1 goto :fail
python intelligence\publish_nhl_stage.py --stage intelligence\publish_stage --repo-root .
if errorlevel 1 goto :fail
echo Validated files copied into the local repo.
echo Review, then run: powershell -ExecutionPolicy Bypass -File intelligence\publish_nhl_github.ps1 -Push
exit /b 0
:fail
echo NHL Intelligence cycle failed. Last-known-good GitHub publication was not pushed.
exit /b 1
