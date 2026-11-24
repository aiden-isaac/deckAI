# Running a measured gauntlet

The command line wraps the same Python API used by other callers:
`run_gauntlet`, `resume_run`, `report_run`, `reproduce_game`, and
`rebuild_index`. Run commands from the repository root with the local Python
environment available.

## Start or resume

Start a 200-game run with the pinned Forge installation, two validated deck
files, and frozen opponent manifest:

```sh
uv run python -m harness.cli run data/example +  --candidate decks/candidate.dck +  --incumbent decks/incumbent.dck +  --manifest gauntlets/acceptance/manifest.json +  --forge-root /home/aiden/Projects/forge +  --pin forge-patches/identity.json +  --java /home/aiden/.local/opt/jdk-17.0.21.1+2/bin/java +  --worker-ceiling-mib 4096
```

The defaults are 2,048 MiB JVM heap, 200 games, seed 20261120, `Default` AI
profiles and a 120 second game clock. Set the worker ceiling above the heap.
The run refuses to start if either deck fails validation, the offline Scryfall
cache is unavailable, or Forge's pinned commit, patch series or jar has drifted.
Worker count is bounded by currently available memory.

If execution stops after the run journal is created, continue its remaining
cells with:

```sh
uv run python -m harness.cli resume data/example
```

The JSON Lines journal is authoritative. Completed cells survive worker
retries; SQLite is a rebuildable index.

## Inspect, replay and rebuild

```sh
uv run python -m harness.cli report data/example
uv run python -m harness.cli replay data/example CELL_ID
uv run python -m harness.cli rebuild data/example
```

`report` returns games, wins, draws, whether the run is scorable, refusals,
pilot warnings, validation records and run identity. A stripped card prevents
a score. A card that the AI reports it cannot play well appears as a warning.
`replay` reruns a stored cell and checks its winner and turn count. Copy its
`cell_id` from the report's records. `rebuild` recreates the SQLite index and
prints the indexed row count.

Do not treat a partial run as a completed result. A report marks it unscorable
until every planned cell is journaled and the run has a completion event.
These results describe the declared Forge AI pilot; they do not establish that
it can execute a combo strategy.
