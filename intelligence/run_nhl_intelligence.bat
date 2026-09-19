@echo off
setlocal
cd /d "%~dp0\.."

echo NHL Intelligence publication
echo ----------------------------
python intelligence\build_nhl_intelligence_snapshot.py
if errorlevel 1 goto :fail

python intelligence\build_nhl_research_queue.py
if errorlevel 1 goto :fail

if not exist intelligence\current\research_results.json (
  echo Research results not present. Creating an empty result package for unresolved-state rendering.
  if not exist intelligence\current mkdir intelligence\current
  > intelligence\current\research_results.json echo {"schema_version":"1.0","generated_at":null,"results":[]}
)
if not exist intelligence\current\source_ledger.json (
  > intelligence\current\source_ledger.json echo {"schema_version":"1.0","generated_at":null,"sources":[]}
)

python intelligence\compile_nhl_intelligence.py
if errorlevel 1 goto :fail

python intelligence\render_nhl_intelligence.py
if errorlevel 1 goto :fail

echo.
echo SUCCESS: intelligence.html refreshed from canonical NHL intelligence JSON.
exit /b 0

:fail
echo.
echo FAILED: NHL Intelligence publication stopped. Existing published HTML was not intentionally replaced by later steps.
exit /b 1
