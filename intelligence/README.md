# NHL Intelligence Production Workflow

The NHL Intelligence layer is read-only relative to the Google Sheets projection model.

## Daily flow

1. Run the existing Apps Script projection pipeline.
2. Run `exportNhlIntelligenceSnapshot()` after projections are complete.
3. Place the exported JSON at `intelligence/current/nhl_model_snapshot.json`.
4. Build the bounded research queue.
5. Research only queue items allowed by the current gate and `research_policy_v1.0.json`.
6. Feed sourced findings through `nhl_research_executor.py`.
7. Compile `nhl_intelligence.json`.
8. Render `intelligence.html`.
9. Run `stage_nhl_publication.py`.
10. Publish only the validated stage through the repository's GitHub publisher.

## Gate behavior

EARLY is low-spend context research. GAME_DAY establishes goalie/injury/media/market state. T-90 is the primary NHL confirmation pass. T-30 is a narrow final-material-change pass. PUCK_DROP freezes the game.

Daily Faceoff is not independently queried by the intelligence layer. The three model pulls remain the shared authoritative lineup feed.

## Fail-closed rules

A changed starting goalie or projected-player scratch requires re-projection. Material line/PP/PK changes produce explicit conflicts. Identity collisions require re-projection. Missing evidence remains UNRESOLVED; it is never converted to confirmed by inference.

Publication is staged and hashed before the GitHub publisher runs. Failed builds leave the prior public page intact.
