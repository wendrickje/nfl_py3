# Session handoff

This is the durable starting point for a new development session. Git, local files,
and generated artifact manifests remain authoritative; this document is a concise
index, not a substitute for inspecting them.

Handoff schema: `1`

Refreshed at: `2026-08-14T15:47:20.323176+00:00`

## Start here

1. Run `git status --short` and `git log -3 --oneline --decorate`.
2. Read this file, [README.md](README.md), the recommended execution order in
   [ROADMAP.md](ROADMAP.md), and the relevant file under [`docs/`](docs/).
3. Run `.\.tools\uv.exe run nfl-ats doctor` when the local environment exists.
4. Inspect `artifacts/active_ats_model.json` before quoting current model results.
5. Before changing code, state the verified current condition and intended next work.

## Commit context before this refresh

- Branch: `claude/affectionate-dijkstra-d3c1qe`
- Baseline commit: `ed5406a5143e` — Merge pull request #2 from wendrickje/claude/pull-from-source-fork-zocrc6
- Pending change set: 7 paths
  - `M  .env.example`
  - `M  pyproject.toml`
  - `M  src/nfl_ats/cli.py`
  - `A  src/nfl_ats/splashsports.py`
  - `A  tests/fixtures/splashsports_picksheet.html`
  - `A  tests/test_splashsports.py`
  - `M  uv.lock`

The baseline commit and pending paths were observed before the automatic refresh.
They normally describe the parent and contents of the handoff-bearing commit. Always
trust live Git output after checkout.

## Current model evidence

Local active-model artifacts are unavailable. This is expected in a fresh clone; use the tracked forecast below as the last published state and regenerate local artifacts before changing model claims.

The 52.05% figure is historical forced-pick ATS classification accuracy, not a
game-specific probability and not proof of a profitable or stable market edge.

## Last tracked weekly publication

[CURRENT_PREDICTIONS.md](CURRENT_PREDICTIONS.md) contains **2026 Week 1** from model `be9326573294de5a`, published `2026-08-12T22:23:56.868653+00:00`. It is an early, mutable research preview.

## Local reproducibility inventory

- canonical team features: **missing** (`data/processed/game_features.parquet`)
- play-by-play features: **missing** (`data/processed/game_features_pbp.parquet`)
- player features: **missing** (`data/processed/game_features_player.parquet`)
- player-value research features: **missing** (`data/processed/game_features_player_value.parquet`)
- participation source snapshot: **missing** (`data/players/participation/raw/LATEST_MANIFEST_MISSING.json`)
- participation-rating research features: **missing** (`data/processed/game_features_player_participation.parquet`)
- learned-availability research features: **missing** (`data/processed/game_features_player_learned_availability.parquet`)
- frozen player-model selection: **missing** (`artifacts/player_model_selection/LATEST_METADATA.JSON_MISSING`)
- participation-rating experiment: **missing** (`artifacts/participation_experiments/LATEST_METADATA.JSON_MISSING`)
- learned-availability experiment: **missing** (`artifacts/availability_experiments/LATEST_METADATA.JSON_MISSING`)
- active model manifest: **missing** (`artifacts/active_ats_model.json`)

Raw data, processed features, fitted models, and evaluation artifacts are intentionally
ignored by Git. A fresh clone therefore starts with documentation, source, tests, and
the last published Markdown forecast but must rebuild or transfer local artifacts.

## Highest-priority work

1. Maintain the prediction-safety contract and add a regression canary for every production error or newly supported output type.
2. Audit and ingest college-football PBP, rosters, participation, player identities, betting lines, and injury-report semantics; then establish a CFB-only market-residual benchmark and sensitivity profile.
3. Learn season-lagged expected role delivery from injury/practice state and current versus strictly prior snap share, then compare it once with both fixed status weights and the completed any-snap probability lead.
4. Replicate position-specific role loss and replacement effects in CFB, then compare NFL-only, pooled-control, pretrained, and hierarchical transfer on NFL-only outer weeks.
5. Predeclare the single QB-plus-continuity follow-up identified above; do not describe another score on 2018–2025 as independent confirmation.
6. Add joint score/total distributions and compare calibration methods inside the nested protocol.

The roadmap is authoritative. Negative results remain part of the evidence base and
must not be silently removed or retuned away.

## Commands that matter

```powershell
# Manual diagnostic/recovery only; the agent and Git hooks own normal refreshes
.\.tools\uv.exe run nfl-ats handoff --check

# Launch the local dashboard
.\.tools\uv.exe run nfl-ats dashboard

# Quality gates
.\.tools\uv.exe run ruff format --check .
.\.tools\uv.exe run ruff check .
.\.tools\uv.exe run mypy src
.\.tools\uv.exe run pytest
```

## Automatic end-of-session contract

1. Reconcile completed work and new evidence with `ROADMAP.md` and relevant docs.
2. If the synchronized weekly forecast changed, run `nfl-ats publish-predictions`.
3. Run all quality gates and record the result in the final response.
4. The agent refreshes the handoff automatically before a handoff, commit, or push
   to `master`; it must never delegate this command to the user.
5. Check `git status`; never commit ignored data, credentials, or fitted models.
6. Commit or push only when the user explicitly asks, and report the exact branch/hash.
