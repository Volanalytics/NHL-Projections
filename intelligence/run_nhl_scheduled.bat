@echo off
setlocal
cd /d "%~dp0\.."
if not exist intelligence\current\nhl_model_snapshot.json (
  echo No NHL model snapshot; leaving last-known-good publication untouched.
  exit /b 2
)
python intelligence\run_nhl_intelligence_cycle.py --publish-stage
if errorlevel 1 (
  echo NHL Intelligence cycle failed. Do not publish.
  exit /b 1
)
echo Validated publication stage is ready. Run the repository GitHub publisher against intelligence\publish_stage.
exit /b 0
