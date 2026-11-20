# Design

## Context

The pinned local Forge build, three-source validator and recording/statistics utilities already exist. Existing AI runner code is legacy work, not the external-pilot interface. The old plan is preserved in Git history. Current primary sources identify spike-eval's PlayerControllerLLM, SeatObservation and AnswerTool as the closest reusable boundary; its inherited callbacks and deterministic fallback choices still need an independent audit. An ai=0 counter alone is insufficient. Installed Codex supports persistent app-server threads, output schemas and ChatGPT authentication. Rootless bwrap is installed.

## Goals / Non-Goals

**Goals:** actual CLI sessions own play; private state stays private; every accepted decision is attributable/replayable; initial Standard profiles have useful sourced strategy; limits pause play; a controlled lesson is used in later play.

**Non-Goals:** Donate heuristics, Forge strategic AI, first-legal defaults, cold CLI startup per decision, a new rules engine, neural training, deck optimization, throughput gates or competitive-strength claims.

## Decisions

### D1. Pin and audit a reused decision adapter

Pin adapter source and verify compatibility with the selected Forge API before building. Keep overlay, provenance, license and patches under engine-adapter. Each strategic callback publishes a decision or explicitly fails unsupported: priority, casts/activations, targets, modes, exact payments, mulligans, triggers/ordering, combat and sideboarding included. No strategic choice can pass through Forge brains, AI payment, greedy resource selection or first-legal fallback. Forced singletons/no-choice mechanics can execute with explicit provenance. Use API-drift tests, ownership inventory and callback instrumentation.

### D2. One rules game and two persistent CLI seats

Python maintains one app-server process/thread per seat/game with existing authentication and minimal configuration. Send only its own observation and playbook; require a structured response each turn. Do not restart the CLI per move. Record models/effort; development-worker model assignments do not silently choose gameplay models. Use operator-configured gameplay model by default. Isolate provider code in harness/pilots; implement Codex first and document Kiro ACP follow-up.

### D3. Frozen bridge envelope v1

Decision: protocol_version=1, game_id, seat (0 or 1), decision_id, state_revision, view with public/private sections, legal_actions and playbook_version. Each legal action has action_id, label and optional parameters_schema. Use engine-owned compound schemas rather than enumerate attack combinations. Answer echoes game_id, seat, decision_id and state_revision, plus action_id and parameters. Engine validates exact identity, schema and actual legality before applying once; repeats return the previous accepted result.

Publish immutable observations on the game thread. Apply face visibility separately from zone visibility, honor temporary reveals and invalidate remembered information after shuffling. Hidden hands/library order and unrevealed faces must not be serialized. Never serialize raw Game/GameView objects.

### D4. Enforced pilot isolation

Each pilot has a private runtime/memory directory. Disable unrelated shell/apps/plugins/MCP/memory tools with verified settings. Separate cwd/read-only mode alone is insufficient. Use rootless bwrap filesystem/PID isolation if tool absence is not provable: mount only runtime dependencies, private authentication/config and its own memory; exclude sibling files/referee logs. Verify denial using actual processes and audit the actual model-visible tools before play.

### D5. Sourced Standard profiles

Select current Izzet aggro/prowess and aggressive landfall (mono-green or Gruul according to real sources). Freeze exact 60+15 lists with author/event/publication/retrieval dates and URLs. Profiles cover objective, mulligans, sequencing, priority, combat, interaction and sideboarding. Distinguish sourced advice from inferred changes. Video descriptions are not watched gameplay; timestamps require inspected transcript/video. Label missing/paywalled sources. Revalidate against pinned Forge and dated Scryfall; never silently replace illegal cards while claiming the original list. Validate in/out counts against the actual sideboard.

### D6. Journal, pause and recover

Append decision-time view, choice schema, model/profile identity, raw response, accepted action and engine result. Mark external/forced/mechanical origins. On quota, transport, schema or unsupported callback failure, preserve the pending decision and pause; no clock loss, default action or credited win. Resume the same seat conversation after checking whether an answer was applied. After process death, replay seed plus accepted-action journal and verify prompt/state identity; refuse divergence rather than guess.

### D7. Versioned learning

Freeze profiles during the match. Postgame review proposes a tentative lesson naming a decision, information actually available then, an alternative and a testable consequence. A seat updates only its own playbook; retain old versions and explicitly load new versions next game. Test the lesson in a captured-decision replay or rules-checked scenario. This is external-memory learning, not weight training; a win alone proves no quality gain.

### D8. Small acceptance gates

First test scripted bridge responses, hidden views, stale/duplicate IDs and AI/default refusals. Then run actual authenticated CLI smoke tests in isolation. Complete one recorded game with both CLI seats, exercise their sideboard choices into game two, interruption/recovery and one lesson/replay cycle. Keep lists fixed for this proof.

## Risks / Trade-offs

- Adapter/Forge mismatch: compile and audit first, pin both and preserve patches.
- Inherited strategic choices: fail closed and require non-forced decision provenance.
- CLI tools leak state: enforce filesystem isolation and test actual read denial.
- Complex prompts omit legal choices: preserve engine-owned schemas; unsupported callbacks pause.
- Low game volume: describe functional/controlled-decision evidence, not metagame strength.
- Shared provider quota: pause with durable session/action identity; no unlimited-play promise.

## Migration Plan

Preserve interrupted foundations. Revise this active plan under user authorization and direct README to the external-pilot entrypoint. Label the legacy AI runner. New overlay/pilot commits can roll back independently of existing card/engine data.
