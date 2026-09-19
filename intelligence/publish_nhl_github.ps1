param(
  [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path,
  [switch]$Push
)
$ErrorActionPreference = "Stop"
Set-Location $RepoRoot
python intelligence\publish_nhl_stage.py --stage intelligence\publish_stage --repo-root .
if ($LASTEXITCODE -ne 0) { throw "NHL publication copy failed." }

$paths = @(
  "intelligence.html",
  "intelligence/current/nhl_model_snapshot.json",
  "intelligence/current/research_queue.json",
  "intelligence/current/nhl_intelligence.json",
  "intelligence/current/source_ledger.json",
  "intelligence/archive"
)
git add -- $paths
$changes = git diff --cached --name-only
if (-not $changes) { Write-Host "No NHL Intelligence publication changes."; exit 0 }
$slate = (Get-Content intelligence\publish_stage\publication_manifest.json | ConvertFrom-Json).slate_date
git commit -m "Publish NHL Intelligence $slate"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed." }
if ($Push) {
  git push
  if ($LASTEXITCODE -ne 0) { throw "Git push failed; local commit retained for retry." }
  Write-Host "NHL Intelligence published to GitHub."
} else {
  Write-Host "Local publication commit created. Re-run with -Push after review."
}
