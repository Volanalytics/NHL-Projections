param(
  [string]$RepoRoot = (Get-Location).Path,
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$base = "https://raw.githubusercontent.com/Volanalytics/NHL-Projections/$Branch"
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

Write-Host "NHL Intelligence local sync"
Write-Host "Target: $RepoRoot"
Write-Host "Source: Volanalytics/NHL-Projections ($Branch)"
Write-Host ""

New-Item -ItemType Directory -Force "intelligence" | Out-Null
New-Item -ItemType Directory -Force "intelligence/current" | Out-Null

foreach ($path in $required) {
  $dest = Join-Path $RepoRoot ($path -replace "/", "\")
  $parent = Split-Path $dest -Parent
  New-Item -ItemType Directory -Force $parent | Out-Null
  $uri = "$base/$path"
  Write-Host "DOWNLOAD $path"
  Invoke-WebRequest -Uri $uri -OutFile $dest -UseBasicParsing
}

$missing = @()
foreach ($path in $required) {
  $dest = Join-Path $RepoRoot ($path -replace "/", "\")
  if (-not (Test-Path $dest)) { $missing += $path }
}
if ($missing.Count -gt 0) {
  throw ("Sync incomplete. Missing: " + ($missing -join ", "))
}

Write-Host ""
Write-Host "NHL Intelligence package synced successfully."
Write-Host "No Git repository is required for C:\NHL."
Write-Host ""
Write-Host "Place the latest exported snapshot at:"
Write-Host "  intelligence\current\nhl_model_snapshot.json"
Write-Host ""
Write-Host "Then run the deterministic dry test:"
Write-Host "  python intelligence\run_nhl_intelligence_cycle.py --publish-stage"
Write-Host ""
Write-Host "This sync script does not publish anything to GitHub."
