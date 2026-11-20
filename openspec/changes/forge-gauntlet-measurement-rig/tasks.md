# Tasks

Host is `kano`. Groups 3, 5 and 7 need no Forge build and can run in parallel with groups 1-2.
Group 6 is a hard gate: nothing in groups 8-10 starts until it passes.

## 1. Pinned engine and build environment

- [ ] 1.1 Install Maven from the binary tarball into `~/.local` (no root) and verify `mvn -version` reports a version and resolves a JDK
- [ ] 1.2 Determine the JDK version Forge's `pom.xml` targets; if the system Java 27 is unsupported, install a supported JDK under `~/.local` and verify `JAVA_HOME=<path> java -version` matches the target
- [ ] 1.3 Pin the engine: record the cloned Forge commit SHA, upstream tag and card-data version into `forge-patches/PIN.md`, create branch `deckai-patches` from it, and verify `git -C /home/aiden/Projects/forge log -1` matches the recorded SHA
- [ ] 1.4 Build unpatched Forge headlessly and verify `java -jar <built jar> sim -d <deck1> <deck2> -n 1 -q` completes one game and prints a result line (expect a long first build on a 1 Mbps link; capture the build log)
- [ ] 1.5 Write `docs/engine-setup.md` recording the exact build command, JDK, Maven version, jar path and first-build wall time, and verify a fresh shell can reproduce the run command from the doc alone

## 2. Engine patches for measurable output

- [ ] 2.1 Patch `SimulateMatch` to accept `-o <file>` writing one JSON object per game (winner, loss reason, turn count, elapsed ms, seed, seat, mulligans for both players, draw flag, match-game index) appended as each game completes; verify a 5-game run produces 5 parseable JSON lines
- [ ] 2.2 Patch `SimulateMatch` to accept `-S <seedfile>` applying one seed per game in order; verify two separate 10-game runs with the same seed file produce identical winners and turn counts game-for-game
- [ ] 2.3 Verify the seed patch produces *different* results for different seeds (guard against a seed being silently ignored): run 10 games with two different seed files and confirm the outcome sequences differ
- [ ] 2.4 Export both patches with `git format-patch` into `forge-patches/`, record the patch-series hash, and verify applying the series to a clean checkout of the pinned SHA reproduces the built jar's behaviour on a 5-game run

## 3. Deck files and validation gate

- [ ] 3.1 Implement `.dck` reading and writing (main deck, sideboard, card names, counts) and verify a round-trip of a hand-written 60+15 list is byte-identical after normalisation
- [ ] 3.2 Build the installed-card-pool index by scanning the pinned `forge-gui/res/cardsfolder/` (including compound filenames such as `aang_swift_savior_aang_and_la_oceans_fury.txt`), and verify the index resolves all of Kobayashi Maru Scenario, The Naked Time, Iroh Tea Master, United Battlefront, Harmless Offering, Shiko Paragon of the Way, Skycoach Conductor and Aang Swift Savior
- [ ] 3.3 Parse Forge's `res/formats/Sanctioned/Standard.txt` into legal sets plus ban list and verify the parsed ban list matches the file's `Banned:` entries exactly
- [ ] 3.4 Download Scryfall bulk `oracle_cards`, filter to `legalities.standard == "legal"` and paper-available, and verify the filtered count is reported and cached to disk for offline reuse
- [ ] 3.5 Implement the validation gate intersecting the three sources plus construction rules (60 minimum main, 15 maximum sideboard, 4-copy limit with basic-land exception) and verify unit tests cover: legal list passes, banned card rejected, 5-copy rejected, 59-card rejected, card-absent-from-pool rejected, and Forge/Scryfall disagreement reported rather than resolved
- [ ] 3.6 Implement pilot-competence disclosure by collecting `AI:RemoveDeck` and `SVar:AI` flags from card scripts, and verify Harmless Offering is reported as flagged (`AI:RemoveDeck:Random`) while Kobayashi Maru Scenario is not
- [ ] 3.7 Implement runtime reveal parsing for stripped and cannot-play-well cards, mark such runs unscorable, and verify a deliberately constructed deck containing a non-existent card name yields an unscorable run with the card named

## 4. Gauntlet runner

- [ ] 4.1 Implement the work-queue model over (candidate, opponent, seed, seat) cells with mirrored play/draw and both seat orders, and verify a generated plan for 2 opponents × 20 games has equal play/draw counts and equal seat counts per pairing
- [ ] 4.2 Implement worker pool sizing from measured free memory and a configured per-worker ceiling, and verify the chosen worker count changes when the configured ceiling changes
- [ ] 4.3 Implement batch execution with per-worker sequential games, JSONL append per game, and a run-identity header (engine SHA, patch hash, deck hashes, gauntlet version, AI profile, sideboard state, clock); verify a completed run's identity contains every field with no placeholders
- [ ] 4.4 Implement worker crash and timeout handling with re-queue, and verify that killing a worker mid-batch results in the batch completing with the full game count and no partial records
- [ ] 4.5 Implement the SQLite index built from JSONL plus a rebuild command, and verify deleting the database and rebuilding reproduces identical row counts and aggregates
- [ ] 4.6 Implement single-game reproduction from a stored record and verify a replayed game matches the recorded winner and turn count

## 5. Statistics

- [ ] 5.1 Implement SPRT with declared bounds, error rates and a game cap, returning accept, reject or inconclusive plus the stopping reason; verify unit tests against hand-computed log-likelihood ratios and that a simulated 50/50 stream terminates inconclusive at the cap
- [ ] 5.2 Implement paired fixed-sample comparison over shared seeds with effect size and confidence interval, excluding unpaired games; verify unit tests cover a known-effect synthetic dataset and that unpaired seeds are reported as excluded
- [ ] 5.3 Implement weighted aggregation across the gauntlet plus per-matchup breakdown with intervals and a diagnostic-only marker below the resolvable sample size; verify a synthetic run where a 4%-weight matchup is marked diagnostic and the aggregate is not
- [ ] 5.4 Implement the result-identity equality check that refuses to pool mismatched results, and verify pooling two results differing only in AI profile raises and names that field
- [ ] 5.5 Implement re-scoring an accepted decision under alternative weightings with sign-flip detection, and verify a synthetic result that reverses under a second weighting is reported as metagame-contingent
- [ ] 5.6 Write `docs/statistics.md` stating the minimum detectable effect, the sample sizes it implies and the stopping rules in use, and verify the documented numbers match the implementation's defaults

## 6. Acceptance gate — known-answer measurement test

- [ ] 6.1 Author a healthy real Standard aggro list and a crippled variant differing only by lands cut from 24 to 20 (with 4 spells added), validate both through the group 3 gate, and verify both pass validation with no stripped cards
- [ ] 6.2 Author a fixed 3-deck opponent gauntlet, validate all three, and freeze the directory with a manifest hash; verify re-running the manifest check reports no drift
- [ ] 6.3 Calibrate the budget: run 200 games of healthy-vs-gauntlet under `/usr/bin/time -v`, and verify measured median seconds per game, peak resident memory per worker, draw rate at the 120 s clock and sustainable worker count are all recorded to `docs/calibration.md`
- [ ] 6.4 Run the SPRT of crippled against healthy and verify it **rejects the crippled list with the correct sign in under ~1,500 games**
- [ ] 6.5 Verify the fitness fields are non-degenerate: winning turn, mulligan count and damage-by-turn-5 have plausible distributions and the 20-land variant shows a higher mulligan rate than the 24-land list
- [ ] 6.6 Verify reproducibility end to end: replay one recorded game from its seed and identity and obtain the same winner and turn count
- [ ] 6.7 Record the gate outcome in `docs/acceptance-gate.md` with the five criteria and their measured values; **if any criterion fails, stop and escalate rather than proceeding to group 7 or later**

## 7. Jeskai Donate deck and its candidate pool

- [ ] 7.1 Explore the Standard-legal card pool for donate-combo construction beyond the initial suggestions — donation enablers, repeatable donation, lethal or crippling donation payloads, protection, loops and alternative shells — and verify every proposed card is confirmed present in the installed pool and Standard-legal by the group 3 gate, producing `decks/jeskai-donate/candidates.md` with a reason per card
- [ ] 7.2 Write `decks/jeskai-donate/objective.md` declaring the deck's intended win condition, the decision metric, constraint thresholds and the gauntlet weighting as versioned inputs, and verify the harness can load it and reject it when a required field is missing
- [ ] 7.3 Author decklist `v0` as a valid 60+15, verify it passes the group 3 gate with zero stripped cards, and record which cards carry pilot-competence flags
- [ ] 7.4 Derive the mana base deterministically from colour-source requirements for the v0 spells and verify the documented requirement per colour is met at the stated reliability threshold
- [ ] 7.5 Document two or three alternative build directions with the trade-off of each in `decks/jeskai-donate/directions.md`, and verify each direction's key cards resolve in the installed pool

## 8. Pilot policy for the donate combo

- [ ] 8.1 Read and document `ControlGainAi`'s existing `DonateJunk` behaviour in `docs/pilot-donate.md`, naming the methods and the evaluation it performs, and verify the description matches the pinned source
- [ ] 8.2 Implement a new `DonateLethal` AI logic branch preferring donation of a permanent whose own resolution makes its controller lose, with fallback to `DonateJunk` behaviour, and verify a unit or scripted game shows Kobayashi Maru Scenario donated in preference to a Food token
- [ ] 8.3 Add a card-script overlay pointing Iroh's abilities at `DonateLethal` without modifying shared `DonateJunk` behaviour, and verify Coveted Falcon and Jon Irenicus card scripts are untouched
- [ ] 8.4 Implement the opt-in declaration and recording of deck-specific pilot logic in the run identity, and verify pooling a `DonateLethal` run with a stock-AI run is refused and names the logic
- [ ] 8.5 Implement win-condition-execution-rate instrumentation driven by the deck's declared win condition, and verify a donate-deck run reports the rate at which the opponent lost to the donated permanent alongside the win rate
- [ ] 8.6 Export the AI patches into `forge-patches/`, re-run the group 6 acceptance gate against the patched engine, and verify the gate still passes (the AI change must not alter the aggro control result)

## 9. Sideboarding and AI strength parameters

- [ ] 9.1 Patch `SimulateMatch` to enable AI sideboarding behind a flag and verify a best-of-three run shows a changed deck composition in games 2 and 3
- [ ] 9.2 Patch `SimulateMatch` to expose `-mc` and verify runs at `off` and at `max` both complete and are recorded with the setting in their identity
- [ ] 9.3 Measure the cost of `-mc max` by comparing median seconds per game against `-mc off` over 100 games each, and record the trade-off in `docs/calibration.md`
- [ ] 9.4 Export both patches into `forge-patches/` and verify the full series applies cleanly to a clean checkout of the pinned SHA

## 10. Integration verification

- [ ] 10.1 Run the Jeskai Donate `v0` list against the frozen gauntlet with `DonateLethal` enabled and verify the run produces a scored result, a win-condition execution rate, per-matchup intervals and a complete identity
- [ ] 10.2 Verify the pilot-execution-failure path: confirm that if the execution rate is zero the result is reported as a pilot-execution failure rather than as a decklist win rate
- [ ] 10.3 Verify the end-to-end refusal paths in one pass — drifted engine pin, invalid deck, mismatched identity pooling, stale baseline — and confirm each produces an explicit refusal naming the cause
- [ ] 10.4 Write `README.md` describing how to run a gauntlet, where results live and how to reproduce a game, and verify the documented commands run as written from a fresh shell

## Workflow follow-up

- Archive the change once the acceptance gate and integration verification are recorded and reviewed.
