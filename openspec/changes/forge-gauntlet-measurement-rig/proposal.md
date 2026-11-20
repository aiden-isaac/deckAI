# Proposal

## Why

The user wants CLI LLM agents to learn to pilot decks through careful play and review. A Forge-AI gauntlet measures a different pilot. This authorized revision replaces the throughput/Donate direction with two actual CLI pilots playing Standard.

## What Changes

- Reuse the pinned Forge build, validation and recording foundations. Preserve old work and Git history; the historical change-directory name stays stable.
- **BREAKING planning change:** replace the no-in-game-LLM restriction, Forge-AI acceptance gate and Donate-specific heuristics with external strategic decision ownership.
- Run two persistent Codex conversations using the existing login, with private seat observations, isolated tools/filesystems and separate strategy memories. Kiro ACP is a later transport, not a prerequisite.
- Source current Standard Izzet aggro/prowess and aggressive landfall 60+15 lists, with dated articles/video evidence for piloting and sideboarding. Label inaccessible content and inferred adaptations.
- Journal decisions and accepted actions; pause on quota, malformed answers or unsupported callbacks without selecting any default or AI action.
- Prove one complete two-CLI game, legal pilot-selected sideboarding, interruption/recovery and one versioned lesson tested on a captured decision. A lone win is not evidence of stronger play.

## Capabilities

### New Capabilities

- `forge-engine-control`: pinned rules execution, private legal prompts, recorded actions and replay without strategic AI fallbacks.
- `deck-validation`: construction, installed-card and current paper-legality checks, plus runtime stripping refusals.
- `pilot-policy`: persistent CLI seats, decision identity/ownership and pause/recovery.
- `deck-profiles`: dated sourced lists, initial strategy and sideboarding knowledge.
- `pilot-learning`: isolated versioned lessons backed by decision-time evidence and controlled replay.

### Modified Capabilities

None: no main capabilities have been archived. This revises the first in-flight change.

## Impact

Implementation lives in `engine-adapter/`, `harness/pilots/`, their tests, `decks/standard/` and operating docs. Reuse and pin spike-eval's audited controller/observation/answer boundary where compatible. Preserve existing utilities but do not use Forge strategic AI for this MVP. Runs stay on kano. Donate, neural training, automatic deck optimization, large statistical claims and jarlaxle migration are deferred.
