# Design

## Context

See `proposal.md` for motivation. The constraints that shape this design:

- **Host is `kano`**, the dev laptop: 20 cores, 16 GB RAM, RTX 4050 (6 GB), 36 GB free disk, Java 27, Maven absent, `git`/`jq`/`sqlite3`/`python3` present. `jarlaxle` migration is deferred.
- **Network is ~1 Mbps.** A Forge clone and a first Maven build will take hours, not minutes. Nothing in the critical path may assume a fast download.
- **Engine facts verified from upstream source** during research: `forge.view.SimulateMatch` is the headless entry point; `-s` seeds a whole run (not a game); `-c` defaults to a 120 s per-game clock; `AISideboardingEnabled` and `sideboardForAI` both default `false` and `SimulateMatch` never sets them; `-mc` (Flat Monte Carlo) defaults off in simulation so `sim` runs a weaker AI than the GUI; `Match.java` builds the library from `getValid().getLeft()` and merely *reveals* unscripted cards, so a deck silently shrinks; `sim` never calls `getDeckConformanceProblem()`.
- **The target deck's cards are implemented.** Verified in `forge-gui/res/cardsfolder/`: `kobayashi_maru_scenario.txt`, `the_naked_time.txt`, `iroh_tea_master.txt`, `united_battlefront.txt`, `harmless_offering.txt`, `shiko_paragon_of_the_way.txt`, `stiltzkin_moogle_merchant.txt`, `aangs_iceberg.txt`, `solitary_cell.txt`, `seam_rip.txt`, plus `aang_swift_savior_aang_and_la_oceans_fury.txt` and `skycoach_conductor_all_aboard.txt` under their compound filenames.
- **The combo is not pilotable as shipped.** `iroh_tea_master.txt` declares `AILogic$ DonateJunk` on both its `TargetOnly` and `GainControl` sub-abilities, and that logic lives in `forge-ai/src/main/java/forge/ai/ability/ControlGainAi.java`. `harmless_offering.txt` carries `AI:RemoveDeck:Random`. The names are self-describing: the stock AI donates *junk*, which for this deck means donating a Food token instead of Kobayashi Maru Scenario. Without a change here, the deck's win condition is never reached and its measured win rate says nothing about the decklist.

## Goals / Non-Goals

**Goals:**

- A measurement pipeline whose every number is reproducible from a recorded identity.
- Failure that is loud. Every known silent-corruption path in the engine becomes an explicit refusal.
- A pilot that can execute a donate combo, and a way to tell whether it did.
- Throughput good enough to screen candidates on one laptop, with worker count derived from measured memory rather than guessed.

**Non-Goals:**

- No in-game LLM calls, at any point, for any reason. The arithmetic ruling this out is in `.agents/tasks/research-cli-agent-pilot.md`.
- No local decider model in this change. Not rejected forever, just not now: it belongs on audited subsets after the rig is trustworthy.
- No search algorithm, no LLM proposal loop, no sideboard-plan optimization. Those are later changes that consume this one's output.
- No general-purpose Forge fork. The patch series stays minimal and rebasable.

## Decisions

### D1. Patch series as git commits on a pinned branch, exported as files into this repo

Forge lives at `/home/aiden/Projects/forge` (outside this repo, since it is GPL-3.0 upstream and 100 MB+). We pin an upstream commit, branch from it, and keep each change as one focused commit. `git format-patch` output is copied into `forge-patches/` here, so this repo records exactly what was changed without vendoring Forge.

*Alternative considered:* a full fork as a submodule. Rejected — a submodule of a 100 MB+ repo on a 1 Mbps link makes every clone painful, and Standard rotation means rebasing onto new Forge releases regularly, which is easier with a short patch series than with a divergent fork.

### D2. Four patches, each independently revertable

1. **`sim-jsonl-output`** — add `-o <file>`: one JSON object per game appended as it completes, with winner, loss reason, turns, elapsed ms, seed, seat, mulligans, draw flag, match-game index. Replaces stdout scraping, which the research flagged as the component most likely to be silently wrong.
2. **`sim-per-game-seed`** — accept `-S <seedfile>` (one seed per line) so game *i* uses seed *i*. This is what makes paired A/B testing possible; `-s` alone seeds the run.
3. **`sim-enable-ai-sideboard`** — add a flag that calls `setAISideboardingEnabled(true)` and `setSideboardForAI(true)`. Roughly ten lines; without it the 15-card sideboard goal is unreachable.
4. **`sim-expose-mc`** — surface `-mc` so AI strength is a declared experiment parameter rather than an undocumented default.

Patches 1 and 2 are prerequisites for the acceptance test. Patches 3 and 4 can land later without reworking anything.

### D3. Python harness drives the JVM as a subprocess; no in-process bridge

The harness spawns `java -jar forge.jar sim ...` and reads the JSONL file. No JPype, no JNI, no long-lived RPC.

*Why:* process isolation means a hung or crashed game cannot corrupt the harness or other games, and the kill-and-requeue path is trivial. A long-lived in-process bridge (manabrew's approach) is the right design for *per-decision* control, which this change explicitly does not need.

*Consequence:* a batch must amortize the card-database load, so the unit of work is "one worker runs N sequential games", not "one process per game". One-process-per-game is reserved for reproducing a single recorded game.

### D4. Worker count from measured memory, not from `nproc`

Each worker is one JVM holding the full card database. The harness reads free memory at startup, divides by a measured per-worker ceiling (`-Xmx` plus overhead), and caps concurrency there. The per-worker figure comes from task 2's measurement, not from a guess.

*Why:* 20 cores are irrelevant if 16 GB only fits 6 JVMs. Over-subscribing swaps and silently inflates seconds-per-game, which would corrupt the throughput model the whole budget rests on.

### D5. Three independent validation sources, intersected

A card is testable only if it is (a) legal per Forge's own `res/formats/Sanctioned/Standard.txt`, (b) present in the installed `cardsfolder/`, and (c) legal per Scryfall's `legalities.standard`. Disagreement between (a) and (c) is reported, never silently resolved.

*Why all three:* Forge's file is authoritative for what the engine will *do* and is updated within days of each set and ban announcement; Scryfall is authoritative for what is legal in paper, which is what the user's money is spent on. A card legal in paper but absent from the engine is untestable; a card in the engine but rotated out of paper is a wasted test.

Pilot-competence flags (`AI:RemoveDeck`, `SVar:AI`, and the runtime `complainCardsCantPlayWell` reveal) are collected as **disclosures, not exclusions** — the user has deliberately chosen cards the AI dislikes, so the right response is to label the result, not to refuse it.

### D6. Donate logic as a new named `AILogic`, not a change to `DonateJunk`

Add a new AI logic branch (working name `DonateLethal`) in `ControlGainAi`, and point Iroh's card script at it via a **card-script overlay** — a patched copy of the one card file — rather than editing `DonateJunk`, which three other cards use.

The logic: when evaluating a donation, prefer a permanent the opponent would be forced to keep whose own resolution makes its controller lose, provided the opponent's next upkeep arrives before the donating player's own loss condition. Fall back to `DonateJunk` behaviour when no such permanent exists.

*Alternatives considered:* (i) change `DonateJunk` itself — rejected, it silently alters Coveted Falcon and Jon Irenicus and makes our results incomparable with anyone else's; (ii) hardcode "if you control Kobayashi Maru Scenario, donate it" — rejected, it measures a special case rather than the strategy, and would not transfer to any other donate payload the deck explores.

*Accepted limitation:* this is a heuristic, not a solver. It will not find the whole line (set up, protect, donate, deny the escape modes). The `pilot-policy` spec's win-condition-execution-rate requirement exists precisely so we can see how often it succeeds instead of assuming it.

### D7. JSONL as the source of truth, SQLite as the index

Every game appends to a run-scoped JSONL file. SQLite is built from those files and may be deleted and rebuilt at any time.

*Why:* an append-only text file survives crashes mid-batch, is diffable, and cannot be corrupted by a concurrent writer holding a lock. The research's crash-recovery requirement is "checkpoint after every game", which this satisfies for free.

### D8. Statistics hand-rolled, explicit, and tested against known inputs

SPRT, the paired confirmation and the interval estimates are written out in the harness with no statistics framework, and unit-tested against hand-computed values.

*Why:* the whole project's credibility is these few hundred lines. A dependency that hides the stopping rule behind a method call is a liability, and the formulae are short. Only `scipy` would be imported, and only for distribution functions that can be checked against published tables.

### D9. The acceptance test is a gate in the task list, not a checkbox at the end

Tasks are ordered so the known-answer test (24 lands cut to 20, SPRT against the healthy list) runs as soon as patches 1-2 and the runner exist, before the donate deck, before the AI logic, before any statistics beyond SPRT. Downstream tasks are explicitly blocked on it.

*Why:* if Forge's AI cannot feel a broken mana base, the project has no instrument, and that should cost a day rather than a month.

## Risks / Trade-offs

- **Forge's AI may be unable to pilot a combo deck even with `DonateLethal`.** Its own authors call it "pretty bad for most combo decks". → The win-condition-execution-rate requirement surfaces this as a number within the first run of the donate deck. If execution rate is near zero, we report that the deck is not measurable by this instrument rather than reporting a misleading win rate, and the user decides whether to spend on a better pilot.
- **Java 27 is newer than Forge targets; the build may fail or misbehave.** → Verify the build early. If it fails, install a JDK that Forge's `pom.xml` declares and pin `JAVA_HOME` for the build only. This is a day-one task precisely because the download is slow.
- **Maven is absent and a first build pulls hundreds of MB at ~1 Mbps.** → Start the build as early as possible and let it run; meanwhile, do the no-build work (validation module, Scryfall data, deck authoring, statistics unit tests) against a downloaded release jar. Maven installs from a ~10 MB tarball into `~/.local` with no root required.
- **36 GB free disk, and Forge plus a Maven cache plus card images is several GB.** → Skip optional image downloads, monitor free space in the measurement task, and keep JSONL compressed once a run is closed.
- **Patch series rots on each Forge upgrade, and Standard rotates, so upgrades are mandatory.** → Keep patches minimal and append-only in scope; re-run the acceptance test after every rebase, treating it as the regression test for the engine integration.
- **A single aggregate win rate is a property of the gauntlet, not of the deck.** → The weighting is a declared, versioned input and every accepted decision is re-scored under alternative weightings, per the `experiment-statistics` spec.
- **GPL-3.0 obligations attach once we compile against patched Forge.** → Accepted and recorded in the proposal; the harness is treated as GPL-3.0.
- **The donate deck's candidate pool is currently one person's suggestion list.** → A dedicated exploration task widens it from the whole Standard-legal pool before any optimization begins, so the search does not start pre-narrowed to untested assumptions.

## Migration Plan

Not applicable: this is the project's first change and there is no deployed state. Rollback for any engine patch is `git revert` on the Forge branch followed by a rebuild; rollback for the harness is ordinary version control. A failed acceptance test halts the change rather than rolling anything back.

## Open Questions

- **Per-worker memory ceiling and seconds per game** are unmeasured; task 2 produces them and the throughput model self-corrects. Deferrable because no spec or task ordering depends on the values, only the worker count does.
- **Whether `-mc max` is worth its time cost** — stronger AI per game versus more games per hour. Deferrable: patch 4 makes it a parameter, and the first calibration run can measure both settings.
- **Gauntlet sourcing** — hand-authored opponent decks versus scraping current Standard lists. This change needs only three to five fixed opponents for the acceptance test and the first donate-deck run; the sourcing policy can be settled when the optimization loop needs a representative metagame.
