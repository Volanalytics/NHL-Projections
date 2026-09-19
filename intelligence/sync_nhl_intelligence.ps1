param(
  [string]$RepoRoot = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$required = @(
  "intelligence/run_nhl_intelligence_cycle.py",
  "intelligence/resolve_nhl_gate.py",
  "intelligence/build_nhl_research_queue.py",
  "intelligence/nhl_research_executor.py",
  "intelligence/compile_nhl_intelligence.py",
  "intelligence/render_nhl_intelligence.py",
  "intelligence/stage_nhl_publication.py",
  "intelligence/publish_nhl_stage.py",
  "intelligence/research_policy_v1.0.json",
  "intelligence/nhl_intelligence_manifest_v1.0.json",
  "intelligence/nhl_intelligence_schema_v1.0.json"
)

if (-not (Test-Path ".git")) {
  throw "This folder is not the NHL-Projections Git repository. Clone/open Volanalytics/NHL-Projections first, then run this script from its root."
}

Write-Host "Syncing NHL Intelligence package from origin/main..."
git fetch origin main
if ($LASTEXITCODE -ne 0) { throw "git fetch failed." }

foreach ($path in $required) {
  git checkout origin/main -- $path
  if ($LASTEXITCODE -ne 0) { throw "Failed to sync $path" }
}

New-Item -ItemType Directory -Force "intelligence/current" | Out-Null

$missing = @()
foreach ($path in $required) {
  if (-not (Test-Path $path)) { $missing += $path }
}
if ($missing.Count -gt 0) {
  throw ("Sync incomplete. Missing: " + ($missing -join ", "))
}

Write-Host ""
Write-Host "NHL Intelligence package synced successfully."
Write-Host "Place the latest snapshot at:"
Write-Host "  intelligence/current/nhl_model_snapshot.json"
Write-Host ""
Write-Host "Then dry-run:"
Write-Host "  python intelligence/run_nhl_intelligence_cycle.py --publish-stage"
Write-Host ""
Write-Host "No GitHub publication is performed by this sync script."
