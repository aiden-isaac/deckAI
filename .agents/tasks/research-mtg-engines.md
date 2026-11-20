# Programmatically controllable MTG rules engines — findings

Investigation date: 2026-11-20. Read-only; no code was changed and nothing was built or run beyond
read-only inspection of this machine. Target format is **Standard** (owner decision mid-investigation).
Endstep was explicitly out of scope and is not covered. Every "Evidence" line below cites a file, symbol
or API response I actually read; anything I could not verify is labelled.

---

## Summary

- **Forge is the answer, and the entry point already exists.** `forge.view.SimulateMatch.simulate()`,
  reached as `java -jar forge.jar sim -d deckA deckB -n 100 -s 42 -q`, runs AI-vs-AI games with no GUI,
  seeds the shuffle, loops a best-of-M match, and prints a per-game result line with the elapsed
  milliseconds. Nothing has to be written in Java to get a first gauntlet running.
- **Four gaps need closing before it is a deck-brewing tool**, in increasing order of effort: results are
  plain text on stdout, not structured records; AI sideboarding is implemented but *not enabled* by
  `sim` (one line); cards Forge has not scripted are **silently stripped from your deck** before the game;
  and one seed covers a whole run, so you cannot pair A/B samples by seed.
- **The binding hardware constraint is RAM, not cores.** Forge ships with `-Xmx4096m`, and the closest
  prior art runs four parallel games at `-Xmx3g` each. On jarlaxle's 8 GB (≈2 GB free) that is 2–3 worker
  JVMs, each running a long *sequential* batch so the card database loads once — not one JVM per game.
  12 cores will sit mostly idle. 16 GB more RAM is the cheapest throughput you can buy.
- **Two mature prior-art projects do most of what you want and are worth reading before writing code.**
  [`lumlaolao/spike-eval`](https://github.com/lumlaolao/spike-eval) is a Python harness driving headless
  Forge with seeds, a gauntlet runner, parallel JVMs and an SPRT A/B tester;
  [`witchesofthehill/manabrew`](https://github.com/witchesofthehill/manabrew) exposes Forge as a long-lived
  JSON-RPC process with a legal-action API and verified deterministic replay. Manabrew exists; its parity
  harness is deprecated exactly as claimed.
- **The biggest threat to the whole plan is not technical.** Forge's own documentation says its AI is
  "Best with Aggro and midrange decks, Poor to Ok in control decks, Pretty bad for most combo decks", and
  the engine carries a per-card "AI can't play this well" complaint list. A gauntlet scored by Forge's AI
  piloting both seats measures *how a deck performs when a heuristic bot plays it*, which is a biased
  proxy for paper Standard, biased toward aggro. Plan the experiment around that, or the tool will
  confidently recommend the wrong 60 cards.

---

## Comparison table

| Engine | Language | Licence | Headless? | Legal-action API? | Determinism | Card coverage | Activity (last commit) | Fit for a Standard brewing gauntlet |
|---|---|---|---|---|---|---|---|---|
| **Forge** (`Card-Forge/forge`) | Java 17+ | GPL-3.0 | **Yes, shipped** — `sim` CLI, `setNoGUIUser()` | Internally yes (`Card.getAllPossibleAbilities`, `PlayerController`); not exposed to a non-Java caller | Seeded shuffle via `-s` → `MyRandom.setRandom`; thread-local RNG built for parallel sim workers; unseeded default is `SecureRandom` | Full Standard; sets added during preview season; release per set | 2026-11-20 (today) | **Best.** Only engine with a supported non-GUI batch mode and current Standard |
| **XMage** (`magefree/mage`) | Java | MIT | Only via its own test framework (`CardTestPlayerBase`) or a client you write | Via server protocol; no shipped headless client | No documented seeding/replay (unverified) | 31,000+ unique cards claimed in readme | 2026-11-18 | Workable but you must build the client layer first; memory-hungry |
| **manabrew** (`witchesofthehill/manabrew`) | Rust + Java + TS | AGPL-3.0+ (own), GPL-3.0+ (vendored Forge) | **Yes** — `forge.harness.Main --interactive-server`, `self-hosted-node` | **Yes, explicitly** — `ActionSpace.getPossibleActions`, `EngineHandler` | **Strongest** — `CountingRandom(seed)`, `ReplayRandom`, `DecisionJournal` v2, cross-process replay test | Java Forge path = full Forge; Rust engine incomplete | 2026-11-19 | Best per-decision API, wrong shape for whole-game batching; heavy toolchain (Node 24, Yarn, Rust, JDK 18–21) |
| **Magarena** | Java | GPL-3.0 | AI-vs-AI via `-DselfMode` | No | Unknown | Small, frozen pre-2023 pool | **2023-04-24 (dormant)** | **No** — no Standard coverage |
| **Cockatrice** | C++ | GPL-2.0 | n/a | n/a | n/a | **No rules engine at all** — virtual tabletop; players move cards by hand | 2026-11-20 | **No** |
| **MageZero** (XMage fork + RL) | Python + Java | MIT | Yes, as a gym env | Via its fork's RL modules | Unknown | XMage's | 2026-11-20 | Reference only — needs 16–64 GB RAM and a GPU |
| **python-mtg** (PyPI 0.1.1) | Python | not declared | Yes | **Yes, cleanest** — `legal_moves` / `push` / `pop` / `copy` / `key` | `seed 0` demo game | Demo matchup only | 2026 | **No** — API to admire, pool unusable |

---

## Q1 — Forge: headless, scriptable, simulation play

**Verdict: yes, fully, with a documented CLI and no Java required.** This is the single most important
finding and it is verified from source, not from the wiki.

**Evidence.**

- Entry point: `forge-gui-desktop/src/main/java/forge/view/SimulateMatch.java`, `public static void
  simulate(String[] args)`, dispatched from `forge/view/Main.java` when `argv[0] == "sim"`. It calls
  `FModel.initialize(null, null)` itself, so no GUI is constructed.
- Per game, `simulateSingleMatch(Match, int, boolean)` does `final Game g1 = mc.createGame();
  g1.setNoGUIUser();` and then runs `mc.startGame(g1)` inside
  `TimeLimitedCodeBlock.runWithTimeout(..., mc.getRules().getSimTimeout(), TimeUnit.SECONDS)`. The comment
  in the file says "will run match in the same thread".
- **Full flag list, read from `argumentHelp()` in the source** (note: `docs/AI.md` documents only a
  subset — it omits `-s`, `-a` and `-mc`, which matter most to you):

  | Flag | Meaning |
  |---|---|
  | `-d <deck…>` | space-separated deck names or `name.dck` filenames |
  | `-D <dir>` | absolute directory to load decks from (overrides the default) |
  | `-n N` | number of games (default 1) |
  | `-m M` | play a full match of M games, best-of-M (overrides `-n`) |
  | `-t Bracket\|RoundRobin\|Swiss` | tournament over all provided decks |
  | `-p P` | players per match, tournaments only (default 2) |
  | `-f F` | format/variant (default `constructed`) |
  | **`-s S`** | **RNG seed** |
  | **`-a A…`** | **AI profile per player, in deck order** (`-a Default Experimental`) |
  | `-c S` | per-game clock in seconds; exceeding it calls a draw (**default 120**) |
  | **`-mc on\|max\|off`** | **Flat Monte Carlo AI refinement; default off in simulations** |
  | `-q` | quiet: result only, not the whole game log |

- `-mc` is load-bearing and under-documented. The source comment: "Flat Monte Carlo is a match preference
  that only the GUI applies (`HostedMatch`); without this switch a simulation always runs the plain
  heuristic AI, whatever the preference says." `max` is described as "the strength a desktop match gets
  automatically". So **by default `sim` runs a materially weaker AI than the GUI does.**
- Net server mode: separate from `sim` and aimed at testing the network pipeline, not at batching games.
  The [Network Testing wiki page](https://github.com/Card-Forge/forge/wiki/Network-Testing) describes
  `NetworkPlayIntegrationTest` with `testConfigurableSequential` / `testConfigurableParallel`,
  `MultiProcessGameExecutor` and `ComprehensiveGameRunner`, driven by `-Dtest.2pGames=N`,
  `-Dtest.batchSize=N`, `-Dtest.timeoutMs=N` (default 300000). Its own note says: "If you just want to run
  AI-vs-AI games without network overhead, see the command-line controls on the AI wiki page." Use it as
  proof that **one-JVM-per-game process parallelism is the project's own approach**, not as your runner.
- A non-GUI match between two *programmatic* controllers is possible, and has been done. `spike-eval`
  does it by subclassing `PlayerControllerAi` — see Q8.
- Card behaviour is scripted in a per-card DSL, one text file per card, under
  `forge-gui/res/cardsfolder/<letter>/<snake_case_name>.txt`. Verified by reading three:

  ```
  Name:Lightning Bolt
  ManaCost:R
  Types:Instant
  A:SP$ DealDamage | ValidTgts$ Any | NumDmg$ 3 | SpellDescription$ CARDNAME deals 3 damage to any target.
  ```

  Cards also carry AI hints: `Kuldotha Rebirth` has `SVar:AIPreference:SacCost$Artifact.token,...`,
  `AI:RemoveDeck:Random`, `DeckNeeds:Type$Artifact`. New-mechanic support reaches the Java core too —
  `waterbend` (a 2025 set mechanic) is implemented in `forge-game/.../cost/CostAdjustment.java`
  (`adjustCostByWaterbend`, `setMaxWaterbend`).

**Confidence: high** for everything above (read from source at `master`). **Medium** on `-mc max` being
exactly GUI-equivalent strength — I read the comment, not the code path.

---

## Q2 — XMage

**Verdict: a complete, MIT-licensed engine with the largest card pool, and no headless client. You would
build the automation layer yourself. Someone already has, twice.**

**Evidence.**

- `magefree/mage`, Java, **MIT**, 2409 stars, last commit 2026-11-18 ("[SLD] Implement Reverend Mother
  Jessica"). Repo root modules: `Mage`, `Mage.Common`, `Mage.Server`, `Mage.Client`, `Mage.Sets`,
  `Mage.Tests`, `Mage.Verify`, `Mage.Server.Plugins`.
- Architecture is server + Swing client. There is **no headless client in the repository**. Two real paths:
  1. **In-JVM test framework** — `Mage.Tests/src/test/java/org/mage/test/serverside/base/` contains
     `CardTestPlayerBase`, `CardTestPlayerBaseAI`, `CardTestPlayerBaseWithMonteCarloAIHelps`,
     `CardTestMultiPlayerBase`, `CardTestCommanderDuelBase`, `MageTestPlayerBase`. These run complete games
     in-process with scripted decisions. This is the lowest-friction programmatic entry.
  2. **Write a client.** [`GregorStocks/mage-bench`](https://github.com/GregorStocks/mage-bench) (Java, 71
     stars, 2026-11-18) did this: its readme describes three layers, with the "XMage server — upstream game
     engine… **Unmodified from upstream**" and two new modules it added, `Mage.Client.Bridge` (exposes the
     game to an LLM as MCP tools) and `Mage.Client.Observer` (JavaFX render + FFmpeg recording). Its player
     types are Pilot (LLM), Sleepwalker (auto-player) and CPU (`COMPUTER_MAD`, XMage's built-in AI).
- [`WillWroble/MageZero`](https://github.com/WillWroble/MageZero) (MIT, 67 stars, 2026-11-20) uses XMage
  "as a gym environment" via a fork adding `Player.AI.RL`, `Player.AI.MCTS`, `Mage.MageZero`, with a `mz`
  CLI and a bundled 16-deck pool "being used to simulate the 2022-2025 standard metagame". Its hardware
  table asks for **4 cores / 16 GB minimum, 8–16 cores / 32–64 GB recommended, NVIDIA 8 GB+ VRAM**, and its
  troubleshooting section says "Default heap is `-Xmx24g`".
- Determinism: I found **no** documented seed/replay facility in XMage. **Unverified — treat as absent.**

**Confidence: high** on structure, licence and the absence of a shipped headless client. **Low** on
determinism (absence of evidence, not evidence of absence).

---

## Q3 — Does manabrew exist?

**Verdict: yes, it exists, it is substantial, it is the most sophisticated Forge automation layer in the
open, and its parity harness is deprecated exactly as you were told.**

**Evidence.**

- GitHub API: `witchesofthehill/manabrew`, primary language **Rust**, 96 stars, last push
  **2026-11-19**, licence `NOASSERTION` resolving to **AGPL-3.0-or-later for its own code** with the
  vendored `forge/` submodule remaining GPL-3.0-or-later (README "License" and "Relationship With Forge").
  Description: "Open-source MTG client for the web and desktop, with MTG Forge running in-browser via
  WebAssembly."
- **Parity is deprecated.** The first line of `README.md`, of `AGENTS.md`, of
  `manabrew-rs/crates/self-hosted-node/README.md` and of
  `forge-harness/src/main/java/forge/harness/AGENTS.md` is, verbatim: "**Parity is DEPRECATED and NOT
  FUNCTIONING.** Do not run `yarn parity`, the parity harness (`manabrew-rs/crates/parity`), the parity
  debugger, or `DeterministicController`." The claim in the brief is accurate. Note the README's own
  "Parity Harness" section still documents `yarn parity:test -- --deck1 red_burn --deck2 green_stompy
  --seed 42 --max-turns 20`; the banner overrides it.
- **Headless engine: yes, two layers.**
  - Java: `forge-harness/src/main/java/forge/harness/Main.java` — a CLI with three modes.
    `--deck1/--deck2/--seed/--max-turns/--prefer-actions/--forge-home/--variant/--commanders` one-shot;
    `--server` ("reads JSONL requests from stdin and writes snapshot responses to stdout. Avoids repeated
    JVM startup cost… one StateSnapshot per line"); `--interactive-server` — a per-session JSON-RPC
    dispatcher over stdin/stdout whose command set I read directly from the dispatch switch:
    `startGame`, `submitAction`, `getPrompt`, `getSnapshot`, `getGameOver`, `getStateRevision`,
    `exportReplaySnapshot`, `restoreReplaySnapshot`, `readDecisionJournal`,
    `acknowledgeDecisionJournal`, `drainDecisionJournal`, `drainDirectives`, `drainCheckpointMetrics`,
    `getRewindRequest`, `resumeAfterFailedRewind`, `replayReady`, `reset`, `endGame`, `abortGame`, `quit`.
    Its javadoc: "Sessions are routed by sessionId and each runs on its own game thread, so one process can
    host several concurrent games."
  - Rust: `manabrew-rs/crates/self-hosted-node` — "Headless room host… with the `forge` backend it spawns
    one Forge JVM per concurrent game."
- **Legal-action API: yes, and it is the real thing.** `forge.harness.common.ActionSpace.getPossibleActions`,
  plus `ChoiceSpace`, `CombatChoiceSpace`, and `EngineHandler`, which the package's AGENTS.md calls "the one
  entrypoint for Forge GUI/controller legality: per prompt it returns the legal choice set (so a caller only
  offers valid picks) and post-validates the submitted answer for whole-answer constraints a per-option set
  can't express (e.g. `CombatUtil.validateBlocks`)". That document is ~200 lines of hard-won detail about
  Forge's mana-payability prediction, and is worth reading in full before you write any action enumerator.
- **Deterministic traces: yes, verified by a test.** `CountingRandom(seed, "game")` and
  `CountingRandom(seed, "agent")` in `Main.java`; `ReplayRandom`; `DecisionJournal` v2 batches holding
  "the exact `startRequest`, then ordered entries with `sequence`, `playerIndex`, `prompt`, `action` and
  `verification`" (`docs/DECISION_REPLAY.md`). Verification "covers canonical prompts, every seat's view,
  spectator state, ordered card identities in all zones (including libraries), and the primitive RNG
  stream." `JournalRewindTest` plays a seeded two-seat game to turn 12 in one process, rewinds to turn 10
  and reconstructs it in a second process, requiring every later prompt and view to match.
- **One caveat that matters to you:** the same document states "**Internal Forge AI is not deterministic
  under replay and is rejected by journal mode**." Journal replay works for scripted/bot seats, not for
  Forge-AI-vs-Forge-AI. Also "Cross-runtime, cross-artifact and cross-version replay are unsupported."
- **Completeness:** the README is candid — "pre-release software"; "The client and Java Forge backend path
  are the most practical way to play today"; "The Rust engine works for selected matchups, but broad card
  coverage is still in progress."
- **Agent interface already exists**, and it is literally the shape your brief asks about
  (`manabrew-rs/crates/manabot/src/agent/mod.rs`):

  ```rust
  pub trait BotAgent: Send {
      fn observe(&mut self, _view: GameViewDto) {}
      fn decide(&mut self, prompt: AgentPrompt) -> Option<PromptOutput>;
  }
  ```

  with `manabrew-agent-interface` holding `prompt.rs`, `protocol.rs`, `game_view_dto.rs` and per-prompt
  DTOs (`chooseAction`, `chooseAttackers`, `chooseBlockers`, `payManaCost`, `mulligan`, `scry`,
  `chooseCombatDamageAssignment`, …), and `AgentKind::Simple` as the one built-in agent.
- **Adoption cost is the problem.** Prerequisites: Node.js 24.x, Yarn v1, Rust stable, **JDK 18–21 and
  Maven** — and the README warns "Newer JDKs (e.g. 26) currently fail to compile Forge". jarlaxle has no
  node and no npm.

**Confidence: high** throughout (read from the repository's own sources and tests).

---

## Q4 — Other candidates

**Verdict: Magarena and Cockatrice are out. The interesting finds are not engines, they are harnesses —
and three of them are LLM-plays-MTG projects that already exist publicly.**

**Evidence.**

- **Magarena** (`magarena/magarena`, GPL-3.0, Java, 444 stars): **last push 2023-04-24**. AI-vs-AI exists
  via a system property — issue #138: "Currently you can play an AI vs AI game using `-DselfMode` but you
  are limited in being able to specify the AI type and decks that are played." Dormant for ~3.5 years, so
  no recent Standard sets. Out.
- **Cockatrice** (`Cockatrice/Cockatrice`, GPL-2.0, C++, 1848 stars, active 2026-11-20): **the brief's
  claim is correct.** Its own README describes "an open-source, multiplatform application for playing
  tabletop card games over a network. The program's server design prevents users from manipulating the game
  for unfair advantage." That is anti-cheat on card movement, not rules enforcement. There is no engine to
  drive. Out.
- **An LLM-plays-MTG project already exists. Three do, and one is on Forge.**
  - **[`lumlaolao/spike-eval`](https://github.com/lumlaolao/spike-eval)** (GPL-3.0, Python + a Java
    overlay, last push 2026-11-19). "Models take a player's seat in Forge… and play against a person,
    Forge's built-in AI or another model." Forge pinned at commit `34a8662b7966a6ee757411feae2ae8ff38cce436`.
    This is your reference implementation — details in Q6, Q7 and Q8.
  - **[`GregorStocks/mage-bench`](https://github.com/GregorStocks/mage-bench)** (71 stars, active) — XMage +
    MCP bridge, 1v1 and Commander, video recording, a public site at mage-bench.com.
  - **[`WillWroble/MageZero`](https://github.com/WillWroble/MageZero)** (MIT, 67 stars, active) — the
    closest thing to a Gym/PettingZoo MTG environment with real card coverage: XMage as the env, AlphaZero-
    style per-deck agents, `mz train` driving a full curriculum, 16 opponent decks standing in for the
    2022–2025 Standard metagame, decks dropped in as `xmage/decks/*.dck`.
  - **[`pianodeath42/MTG-simulation`](https://github.com/pianodeath42/MTG-simulation)** (Python, no licence,
    0 stars, 2026-04) — "XMage-based MTG deck simulation, shared 60-card decklists, and Elo-style ratings…
    XMage batch runs". Same ambition as yours, tiny; worth a skim, not a dependency.
  - `taoroalin/mtg-llm` — Python LLM scaffolding with its own `game_state.py`; it is not a rules engine.
- **PyPI.** No general-purpose MTG rules-engine package of substance. The only one with the right API shape
  is **`python-mtg` 0.1.1** (`github.com/yevbar/witchcraft`): "One stateful object holds the whole game; you
  read the legal moves, push one, pop to take it back — the python-chess shape". It offers `g.legal_moves`,
  `g.push/pop/copy`, `Game.move_key`, `g.key()` transposition keys and `with g.branch(move)`. Its quickstart
  loads "the demo Gruul-vs-Dimir matchup (real cards), seed 0". **No licence is declared on PyPI** and the
  card pool is a demo. Steal the API shape, not the engine. (Other PyPI hits — `mtg-mcp-server`, `mtgtools`,
  `scry-terminal`, `doubletap` — are card-data and deck-advice tools with no game simulation.)
- No OpenAI-Gym/PettingZoo MTG environment with current card coverage exists outside MageZero's XMage fork.

**Confidence: high** on Magarena/Cockatrice/prior-art existence. **Medium** on PyPI exhaustiveness (search,
not an index crawl).

---

## Q5 — Card coverage vs format legality (answered for **Standard**)

**Verdict: Forge tracks Standard legality within weeks of each set and scripts cards during preview season.
XMage claims a larger total pool. The real coverage risk is not "is the set in", it is "is *this card*
scripted" — because Forge silently drops unscripted cards from your deck.**

**Evidence — Forge's currency.**

- `forge-gui/res/formats/Sanctioned/Standard.txt` (read in full):
  `Sets:WOE, LCI, MKM, OTJ, BIG, BLB, DSK, FDN, DFT, TDM, FIN, EOE, SPM, TLA, ECL, TMT, SOS, MSH, HOB, FRA, TRK`
  plus a 13-entry `Banned:` list (Cori-Steel Cutter, Heartfire Hero, Monstrous Rage, Screaming Nemesis,
  Stormchaser's Talent, Vivi Ornitier, …). So the format definition is a data file you can also read from
  your harness to validate a candidate decklist.
- Commit history of that one file shows the cadence: `Add TRK, TRC, SDS to formats` (2026-11-03),
  `Add FRA, FRC, YFRA to formats` (2026-09-20), `Banned and Restricted Announcement for August 10, 2026`
  (2026-08-10), `Add HOB, HOC to formats` (2026-08-01), `Add MSH, MSC to formats` (2026-06-17).
  **Standard legality is updated per set and per B&R announcement, within days.**
- Releases are named after sets: `forge-2.0.16` "Star Trek Release" (2026-11-11), `2.0.15` "Reality
  Fracture" (2026-09-28), `2.0.14` "The Hobbit" (2026-08-08), `2.0.13` "Marvel Super Heroes" (2026-06-22).
  Plus a rolling `daily-snapshots` tag. Expect a release within ~1–2 weeks of a set's street date.
- **Pre-release scripting is real.** `forge-gui/res/cardsfolder/upcoming/` currently holds 16 scripted cards
  from an unreleased Dune set (`shai_hulud.txt`, `muaddib_prophet_foretold.txt`,
  `baron_vladimir_harkonnen.txt`, `reverend_mother_jessica.txt`, …) — and the repo's most recent commit
  touching `res/editions` is from 2026-11-19. Cards land during preview season, before the set is legal.
- **Recent mechanics reach the Java core, not just the DSL.** `waterbend` has first-class support in
  `forge-game/.../cost/CostAdjustment.java` (`adjustCostByWaterbend`, `setMaxWaterbend`), and manabrew's
  harness notes document Forge's own `InputSelectCardsForConvokeOrImprovise` taking the artifact branch for
  it. Correctness of recent mechanics is not uniform, though: the same document records an upstream Forge
  bug for `Crashing Wave` ("upstream native Forge is broken for this card: X resolves to 0 and targeting
  locks at 'up to 0'"), and Forge has 746 open issues. Expect per-card defects at the frontier of new sets.

**Evidence — the silent-strip hazard (read this twice).**

In `forge-game/src/main/java/forge/game/Match.java`, inside the per-player deck preparation:

```java
Pair<Deck, List<PaperCard>> myDeck = toCheck.getValid();
...
preparePlayerZone(player, ZoneType.Library, myDeck.getLeft().getMain(), psc.useRandomFoil());
...
unsupported.put(player, myDeck.getRight());
...
if (!unsupported.isEmpty()) { game.getAction().revealUnsupported(unsupported); }
```

`getValid()` returns the playable deck on the left and **unscripted cards on the right**. The library is
built from the left. The right is merely *revealed*. A 60-card list with three unimplemented cards becomes
a 57-card library and the game proceeds. Separately, `player.getController().complainCardsCantPlayWell(deck)`
feeds `rAICards`, revealed as `lblAICantPlayCards` — cards the AI admits it pilots badly. These are
*complaints*, not removals, so those cards stay in the deck but will be misplayed.

**Action: your harness must parse both reveals and refuse to score any gauntlet where either is non-empty
for the candidate deck.** This is the highest-value 20 lines of code in the project.

**On the original Pauper question**, since the brief asked: Forge's `res/formats/Sanctioned/Pauper.txt`
bans both **Monastery Swiftspear** and **Kuldotha Rebirth**. The cards are implemented and playable in a
Constructed sim, but a Kuldotha-Swiftspear list is not Pauper-legal under Forge's own ban list. Moot now.

**Confidence: high** on legality currency and the strip behaviour (both read from source/data).
**Medium** on "how correct is recent-mechanic scripting" — I verified one mechanic deeply and found one
upstream bug; I did not audit a set.

---

## Q6 — Determinism and experiment control

**Verdict: Forge can seed a run, and that is genuinely useful. It cannot give you paired A/B samples, and
believing otherwise would quietly invalidate your card-swap comparisons. Forced opening hands need the
puzzle path, not the sim path. manabrew is the only project here with verified replay.**

**Evidence — seeding works.**

- `SimulateMatch.simulate`: `if (params.containsKey("s")) { seed = Long.parseLong(params.get("s").get(0));
  MyRandom.setRandom(new Random(seed)); }`
- `forge-core/src/main/java/forge/util/MyRandom.java` is better engineered for your use case than I
  expected, and its own comments say so:
  - The default is **`new SecureRandom()`** per thread. **An unseeded run is not reproducible.** Always
    pass `-s`.
  - The stream is `InheritableThreadLocal`, documented as: "Thread-local so concurrent games in one JVM
    (headless simulation workers, parallel AI harnesses) that seed their stream via `setRandom(Random)`
    cannot contaminate each other's sequences. Inheritable so threads spawned from a seeded thread (AI
    evaluation helpers) continue the parent's stream."
  - Every draw funnels through a `CountingRandom.next(bits)` wrapper with a call counter
    (`MyRandom.callCount()`), used by undo detection. A debug flag `-Dforge.undo.debug=true` tallies draws
    by call site (`MyRandom.drainTrace`) — that is a ready-made tool for auditing where randomness is
    consumed if a replay ever diverges.
- Shuffles go through it: `Match.java` calls `player.shuffle(null)` during deck preparation.

**Evidence — three limits you must design around.**

1. **One stream per run, not per game.** `-s` seeds once; `simulate` then loops
   `simulateSingleMatch(mc, iGame, …)` for `-n` games on the same stream. Game 7 depends on games 1–6.
   Reproducing *game 7 alone* means replaying 1–6.
2. **Seeds do not pair across deck variants.** Changing one card changes how much randomness the game
   consumes, so deck A at seed 42 and deck A′ at seed 42 diverge after the first differing draw. You get
   *reproducibility* (rerun the same experiment and get the same answer) but **not** *variance reduction*
   (comparing A and A′ on "the same shuffles"). Plan for larger N and a sequential test instead —
   spike-eval ships `eval/sprt.py` for exactly this.
3. **No forced opening hand in `sim`.** There is no flag. The mechanism that exists is Forge's puzzle
   format: spike-eval drives boards with `PUZZLE=<file>.pzl` and has a whole puzzle runner
   (`eval/puzzles/puzzle_solve.py`). That is the path for "start from this board", and it is a different
   runner from `sim`. Also check `GameRules.setAllowCheatShuffle` (driven in the GUI by
   `FPref.UI_ENABLE_AI_CHEATS`): `SimulateMatch` never sets it, so you inherit the `GameRules` default —
   **verify it is off before trusting any result**, which I did not do.

**Evidence — manabrew is the determinism reference.** See Q3: seeded `CountingRandom`, `ReplayRandom`,
`DecisionJournal` v2 with per-entry `verification`, and `JournalRewindTest` reconstructing a seeded game
in a *second process* and comparing every subsequent prompt and view. Its own limitation is the one that
blocks you: "Internal Forge AI is not deterministic under replay and is rejected by journal mode."

**Evidence — spike-eval's seed discipline is worth copying wholesale.** `eval/seed_policy.py`,
`eval/seed_registry.py` + `seed_registry.json` (reserved seed bands so evaluation seeds never leak into
development runs), `eval/holdouts.json`, `eval/check_holdouts.py`, and a `GAME_SEED` env var per game. Its
acceptance suite pins canary games by seed: "The seed-42 floor and random mirrors are pinned canaries, at
A/108/1828 and A/55/365 (Linux pins)" — i.e. a fixed seed reproduces an exact game on a fixed platform.

**Confidence: high** on the seed mechanism and its limits (source). **Medium** on cheat-shuffle default
(not checked). **High** on manabrew's replay (test-backed).

---

## Q7 — Throughput

**Verdict: no published seconds-per-game figure exists for Forge AI-vs-AI; I looked and did not find one.
Process-level parallelism is supported and is the project's own approach. Here is a bounded estimate with
the assumptions stated, and the exact command to replace it with a measurement in ten minutes.**

**Verified facts.**

- Forge prints the number itself: `System.out.printf("\nGame Result: Game %d ended in %d ms. %s has
  won!\n%n", 1 + iGame, sw.getTime(), …)`. Measuring is `-n 20` and a regex.
- The default draw clock is **120 s per game** (`-c`, `GameRules.simTimeout = 120`). Games that exceed it
  are called draws.
- Forge's network test harness defaults to a **300 s** per-game timeout and `-Dtest.batchSize=10` parallel
  JVMs; its minimal 10-card deck-out game is documented as "Under 60 seconds" *including* JVM start, server
  and client.
- spike-eval's gauntlet sets `GAME_CAP_MS=300000` for full games where one seat answers instantly.
- Parallelism is real and process-shaped: Forge's own `MultiProcessGameExecutor` /
  `ComprehensiveGameRunner` spawn one JVM per game; spike-eval's `keyword_gauntlet.sh` ends with
  `xargs -P "$PAR" -n 2 bash -c 'game "$0" "$1"'` with `PAR` defaulting to 4.
- Thread-level parallelism inside one JVM is *not* available: `SimulateMatch` is explicitly single-threaded,
  and a standing community request asks for it — "It would be great to enhance the simulation capability of
  Forge to embrace multithreading. The headless, AI vs AI command line utility has great potential but could
  be much faster" ([slightlymagic.net forum](https://slightlymagic.net/forum/viewtopic.php?f=26&t=29255)).
  `MyRandom`'s thread-local design shows the groundwork is there; the runner is not.

**Inference, with assumptions.** Assume: `-mc off` (the sim default, plain heuristic AI); two Standard
decks of normal interaction density; one game per core; card database already loaded. The 120 s default
draw clock is the strongest available signal — if typical games exceeded it, the shipped default would
produce mass draws and nobody would use the feature. For aggro-vs-aggro I would expect single-digit
seconds; **for Standard, which the owner correctly notes runs longer, I assume 15–45 s of engine time per
game, i.e. roughly 80–240 games per hour per worker.** Add a **one-time 20–60 s** `FModel.initialize` per
JVM (card database load) — which is the whole argument for long sequential batches per JVM rather than one
JVM per game. `-mc on` will cost multiples of this, because it is a search.

**Flagged as unverified: the 15–45 s figure is my estimate, not a measurement.** Replace it first thing:

```bash
java -Xmx2g -jar forge.jar sim -d candidate gauntlet01 -n 20 -s 1 -q
```

**Confidence: high** on the parallelism facts and the self-reported timing. **Low** on the
seconds-per-game estimate.

---

## Q8 — Interface shape for the leading candidate

**Verdict: not JPype, and for your actual objective, not a per-decision API at all. The adapter you need
first is a subprocess that runs Forge's stock `sim` CLI and parses stdout. If you later want in-game
control, the proven shape is an in-process Java subclass of `PlayerControllerAi`, reached from Python over
loopback HTTP or stdin.**

**Three concrete options, in the order I recommend them.**

**1. Subprocess + text I/O over the stock CLI — zero Java.**
Python spawns `java -Xmx2g -jar forge.jar sim -d <candidate> <gauntlet_n> -n N -s <seed> -f constructed`,
reads stdout, and parses: the `Game Result: Game N ended in M ms. <name> has won!` line, and typed log
lines of the form `"<Type caption>: <message>"` (`GameLogEntry.toString()` is
`type.getCaption() + ": " + message`). `-q` restricts output to `MATCH_RESULTS`. **This is the right first
adapter**, because the brewing agent's decision loop is over *decklists*, not over in-game plays — Forge's
AI pilots both seats, and the LLM only edits the 75.

**2. In-process Java controller — the spike-eval shape, proven.**
From `docs/harness/ARCHITECTURE.md` §1 and §3:

```
 Forge rules engine (pinned commit; four marked patches as diffs)
   │  asks the seat's PlayerController for every decision
   ▼
 PlayerControllerLLM  (forge-overlay/.../spike/LlmSpikeGui.java)
   │  1. builds what the seat may see   2. builds the ask
   │  3. sends it, with the tools       4. reads the answer   5. carries it out
   ▼
 Engine applies it; illegal moves cannot happen: every option shown was produced by the engine
```

- "**A subclass of Forge's `PlayerControllerAi` that overrides each decision method.** *Why subclass the AI
  controller:* the engine has paths that only work for a non-human controller (headless play, payment,
  triggers). Subclassing keeps those paths and replaces the decisions."
- The trap, in their own words: "*Why that is dangerous, and how it is policed:* every method not
  overridden is decided by Forge's AI." They maintain `docs/harness/controller-ownership.tsv` listing every
  controller method and who decides it, and assert `[TALLY] … ai=0` in every game log.
- Launch is a plain classpath invocation, not JPype, not a socket:
  `java $JVM_FLAGS -cp "$CLASSES:$(cat classpath.txt)" forge.spike.LlmSpikeHeadless`
  with configuration by environment: `GAME_SEED=7 GAME_CAP_MS=300000 DECK_A=<path> DECK_B=<path>
  CONTROLLER_A=llm CONTROLLER_B=ai EVAL_OUT=<dir> OPENROUTER_BASE_URL=http://127.0.0.1:$port/v1`.
- Four engine files needed patching because no `PlayerController` hook existed: `ComputerUtilMana`,
  `Player.assignCompanion`, `MagicStack`, `GameCopier`. Patches are kept as unified diffs against the
  pinned commit, with the original's sha256 recorded, so a re-pin forces a re-diff.
- Decks are plain text, not `.dck`: "one card per line, the count and then the card's exact name, with an
  optional `Sideboard` line before the sideboard."
- Controllers available: `llm`, `ai`, `random`, `floor`, `human`, `replay:<attempt>`, `jev:<model>`.

**3. Long-lived JSON-RPC Java process — the manabrew shape, most capable.**
`java -jar forge-harness-jar-with-dependencies.jar --interactive-server`, then newline-delimited JSON over
stdin/stdout: `{"command":"startGame","sessionId":…,"payload":"<json>"}` →
`{"ok":true,"result":"<json>"}`. The mapping to your requested triple is direct:
`observe()` → `getSnapshot` / `getPrompt`; `get_actions()` → `ActionSpace.getPossibleActions` surfaced in
the prompt's action list; `execute(action_id)` → `submitAction` echoing an offered id. Sessions are routed
by `sessionId`, several concurrent games per process. The cost is adopting an AGPL Rust/Node project, or
vendoring its Java `forge-harness` module alone (AGPL-3.0+, derived from GPL-3.0+ Forge).

**On the local decider model ("jev").** spike-eval already has this seat, and it tells you what the
pattern looks like. `DecisionsBridge` handles `jev:<model>` specs — "TypeSafe's Jev 1.14… is not a chat
model: it is served only on OpenRouter's Decisions API", its "typed answer is turned into" the engine's
answer directly, and by construction it has "No lookups… No text answer… No reasoning text". Crucially for
a homelab: the bridge permits a **loopback** endpoint without egress consent
("`OpenRouterBridge.authorizationHeader` never sends the key to loopback"), so a locally served decider
drops into the same seat. **But** on jarlaxle — no GPU, 8 GB RAM, no ollama — a local model cannot share
the box with Forge workers, and for *deck brewing* the in-game decisions are Forge's AI's anyway. Defer
this until the gauntlet works.

**Confidence: high** (all read from the projects' own sources and scripts).

---

## The owner's deck-brewing requirements, (a)–(f)

### (a) How to run AI-vs-AI simulated matches non-interactively, and what output you get

**Entry point:** `forge.view.SimulateMatch.simulate(String[])` in
`forge-gui-desktop/src/main/java/forge/view/SimulateMatch.java`, dispatched by `forge/view/Main.java` on
`argv[0] == "sim"`. No build required — download the release tarball and run the jar.

```bash
java -Xmx2g -jar forge.jar sim -D /srv/decks/gauntlet -d candidate.dck meta01.dck -n 200 -s 42 -q
```

**Output** is plain text on stdout (stderr carries Forge's startup warnings), per game:

- without `-q`: the whole game log, chronological, each line `"<Type>: <message>"`, with types from
  `GameLogEntryType`: `Turn`, `Mulligan`, `Damage`, `Life`, `Land`, `Discard`, `Combat`, `Add To Stack`,
  `Resolve Stack`, `Mana`, `Replacement Effect`, `Zone Change`, `Phase`, `Sideboard`, `Game Outcome`,
  `Match Result`.
- with `-q`: only `MATCH_RESULTS` entries.
- always, the result line: `Game Result: Game <n> ended in <ms> ms. <AiName> has won!`, or
  `Game Result: Game <n> ended in a Draw! Took <ms> ms.`
- a timeout prints `Stopping slow match as draw`.
- player names are generated as `Ai(<i>)-<DeckName>` (with `[profile]` appended if `-a` was used), so the
  winner line is attributable to a deck without extra bookkeeping.
- with `-mc on`, `FlatMonteCarloStats.summary()` is printed at the end.

### (b) Gauntlet / tournament mode, and whether it is scriptable

- **Tournament: yes, scriptable.** `-t Bracket|RoundRobin|Swiss` with `-p P` players per match, decks from
  `-d` or every `*.dck` in `-D <dir>`. `simulateTournament` builds a `DeckGroup`, pairs via
  `forge.gamemodes.tournament.system.{TournamentBracket,TournamentRoundRobin,TournamentSwiss}`, prints
  round pairings and `Match Winner - <name>!` per match, then `tourney.outputTournamentResults()`. It is
  also fault-tolerant: it abandons a game after an exception and bails out of the match after 5.
- **Gauntlet: exists, but not from the CLI.** `forge-gui/src/main/java/forge/gamemodes/gauntlet/` holds
  `GauntletData`, `GauntletIO`, `GauntletUtil`, `GauntletWinLoseController`. `GauntletData` is exactly your
  data model — a `Deck userDeck`, a `List<Deck> decks`, `eventNames`, `eventRecords`, `completed` — but it
  holds a `transient HostedMatch`, and `HostedMatch` is the GUI match host that reads `FModel`
  preferences. `SimulateMatch` deliberately bypasses `HostedMatch` (that is why `-mc` exists). **Do not try
  to drive gauntlet mode headlessly.**
- **What to do instead:** your harness owns the gauntlet. A fixed gauntlet is a directory of `.dck` files
  plus a Python loop issuing one `sim` invocation per (candidate, opponent) pair. That is better than
  `-t RoundRobin` anyway, because you want *fixed* pairings against an unchanging meta, not a bracket that
  eliminates decks, and because it parallelises trivially.

### (c) Best-of-three with sideboarding

**Best-of-three: yes. Sideboarding: implemented, and silently disabled in `sim`.** This is the finding most
likely to waste your time if you don't know it.

- `-m 3` sets `rules.setGamesPerMatch(3)` (which sets `gamesToWinMatch = M/2 + 1`) and loops
  `while (!mc.isMatchOver())`.
- `Match.java` then gates sideboarding three ways:
  ```java
  boolean canSideBoard = !isFirstGame && rules.getGameType().isSideboardingAllowed();
  boolean sideboardForAIs = rules.getSideboardForAI() &&
      rules.getGameType().getDeckFormat().equals(DeckFormat.Constructed);
  ```
  and in `GameRules.java` the defaults are `AISideboardingEnabled = false` and `sideboardForAI = false`.
- `PlayerControllerAi.sideboard(...)` returns early: `if (!brains.getGame().getRules().getAISideboardingEnabled()
  || !deck.has(DeckSection.Sideboard)) { return null; }`
- The GUI sets these from a preference (`HostedMatch.getGameRules()` switches on
  `AiProfileUtil.getAISideboardingMode()` → `Off` / `AI` / `HumanForAI`). **`SimulateMatch` never calls
  `setAISideboardingEnabled` or `setSideboardForAI` at all** (verified by grep over the file).
- When enabled, the machinery is good: `SideboardAdvisor.advise(player, main, sideboard, opponentMains,
  opponentNames, SideboardAdvisor.maxSwapsFor(main.size()))` reads the opponents' last-game main decks
  (`Match.playedMains`, "taken before anyone sideboards for the next"), swaps cards that do nothing against
  them, enforces that "the overall content of the deck (Main+Sideboard) must not change, or the AI may
  cheat", and logs what it did as `GameLogEntryType.SIDEBOARD` lines via `getSideboardingReport()`. A deck
  can also carry an explicit plan as deck metadata: `deck.getAiHint("SideboardingPlan")`, `;`-separated.
- **The catch.** The self-advising path requires Flat Monte Carlo:
  ```java
  private boolean sideboardsAgainstOpponentDeck() {
      return brains.getGame().getRules().getAISideboardingEnabled() && brains.getGame().getAIFlatMonteCarlo()
          && brains.getBoolProperty(AiProps.FLAT_MC_ENABLED) && !brains.getGame().getRules().getSideboardForAI();
  }
  ```
  So a sideboarding gauntlet needs `-mc on` **and** a one-line patch adding
  `rules.setAISideboardingEnabled(true)` to `SimulateMatch.simulate`. Both cost throughput. Measure the
  `-mc on` penalty before committing to bo3.
- **Recommendation:** run your gauntlet as game-1-only (`-n`, not `-m`) for the main 60-card search, where
  you want thousands of cheap games. Validate the 15-card sideboard separately with a smaller patched,
  `-mc on`, `-m 3` run against the specific decks the board is aimed at. Different experiments, different
  budgets.

### (d) Deck file format and location

- Format is INI-style `.dck`, loaded by `forge.deck.io.DeckSerializer.fromFile(File)`. Verified against
  `forge-gui/res/quest/precons/Air Forces.dck`:
  ```
  [metadata]
  Name=Air Forces
  Deck Type=constructed
  [main]
  4 Island|MIR|3
  3 Benalish Knight|WTH
  1 Man-o'-War|VIS
  ```
  Lines are `<count> <Card Name>[|<SET>[|<collectorNumber>]]`. Set and collector number are optional; a
  bare name resolves against Forge's card database. `[sideboard]` is the sibling section (the sample precon
  I read has no sideboard, so **the exact header spelling is inferred from `DeckSection.Sideboard` and
  Forge's own deck exports — verify with one round-trip through Forge's deck editor before generating
  thousands of files**).
- Location: `ForgeConstants.DECK_CONSTRUCTED_DIR` (= `ForgeProfileProperties.getDecksConstructedDir()`,
  i.e. `<userdata>/decks/constructed/`) for Constructed, `DECK_COMMANDER_DIR` for Commander. `-d name.dck`
  resolves there; **`-D /abs/path` overrides it**, which is what your harness should use — keep the fixed
  gauntlet and each generated candidate in a run-scoped directory, never in the user profile.
- `deckFromCommandLineParameter` decides file-vs-name by extension: "deck is treated as file if it ends
  with a dot followed by three numbers or letters". A name without that suffix is looked up in
  `FModel.getDecks().getConstructed()`. **Always pass `.dck` filenames with `-D`** to avoid the lookup path.
- Note spike-eval chose plain `N Cardname` text lists instead and loads them itself — if you build the
  in-process controller later, you can skip `.dck` entirely.

### (e) Capturing per-game results machine-readably, and what must be patched

**Nothing structured is written today. Two levels of fix; start with the first.**

**Level 1 — parse stdout, no patch (good enough to start).** You can recover: winner (from the result
line, with deck name embedded in `Ai(i)-<DeckName>`), draw flag, wall-clock ms per game, turns (count
`Turn:` lines or read the last one), mulligans (`Mulligan:` lines), and damage events (`Damage:` lines) —
run without `-q` to get them. Fragile against localisation (`GameLogFormatter` uses `Localizer`) and log
verbosity, so pin the locale.

**Level 2 — a small patch for real records (recommended once the loop works).** Everything you want is
already in memory; it just isn't serialised. In `forge-game`:

- `GameOutcome`: `getWinningPlayer()` / `getWinningLobbyPlayer()`, `isDraw()`, `getWinCondition()`
  (`GameEndReason`), **`getLastTurnNumber()`**, `getLifeDelta()`, `getWinSpellEffect()`, and it is
  `Iterable<Entry<RegisteredPlayer, PlayerStatistics>>`.
- `PlayerStatistics`: `getOpeningHandSize()`, **`getMulliganCount()`**, `getTurnsPlayed()`,
  `getExtraTurnsPlayed()`, `getOutcome()`.
- For damage attribution, subscribe to the game's Guava EventBus rather than parsing text. The event
  classes exist in `forge-game/src/main/java/forge/game/event/`: `GameEventPlayerDamaged`,
  `GameEventCardDamaged`, `GameEventMulligan`, `GameEventTurnBegan`, `GameEventTurnEnded`,
  `GameEventGameOutcome`, `GameEventGameFinished`. manabrew's harness does exactly this — its `Main.java`
  imports `com.google.common.eventbus.Subscribe`, `GameEventPlayerPriority` and `GameEventTurnPhase`.

So the patch is: add an `-o <results.jsonl>` flag to `SimulateMatch`, register a `@Subscribe` listener on
the game's event bus, and after each `simulateSingleMatch` append one JSON object built from `GameOutcome`
+ `PlayerStatistics` + the listener's tallies. Perhaps 150 lines of Java, no engine semantics touched.

**Also capture, or you will be fooled:** the `revealUnsupported` and `lblAICantPlayCards` reveals from Q5,
and the `SIDEBOARD` log lines if you enable sideboarding.

### (f) Wall-clock per game, and whether N parallel JVMs is right on 12 cores

**Per game:** see Q7 — estimated **15–45 s** for Standard with `-mc off` (my inference, flagged), plus
**20–60 s** of one-time card-DB load per JVM. Measure it before planning a run.

**Scaling shape: parallel JVM *workers*, each running a long sequential batch — not one JVM per game.**

- Process parallelism is the supported mechanism (Forge's own `MultiProcessGameExecutor`; spike-eval's
  `xargs -P 4`). Thread parallelism inside one JVM would need new code.
- But `sim -n 500` already loops 500 games in one JVM after one `FModel.initialize`. Launching a JVM per
  game would pay the card-DB load 500 times and, worse, hold 500 × ~1–2 GB peaks on an 8 GB box.
- So: `W` long-lived workers, each `java -Xmx<cap> -jar forge.jar sim -d candidate meta_k -n <big> -s <seed_k>`,
  with the Python harness owning the (candidate × opponent × seed) work queue.

**`W` on jarlaxle is set by RAM, not by the 12 cores.**

| Evidence | Value |
|---|---|
| Forge's shipped JVM args (`forge-gui-desktop/pom.xml`, `mandatory.java.args`) | `-Xmx4096m` |
| spike-eval's 4-parallel gauntlet (`keyword_gauntlet.sh`), with the comment "`-Xmx` is lower here, where four games run side by side" | `-Xmx3g` each |
| Forge README's Android guidance | "at least **6GB RAM** to run smoothly" |
| MageZero (XMage, for contrast) | `-Xmx24g`, 16 GB min / 32–64 GB recommended |

**Judgement.** These are caps and recommendations, not measured resident sets — **I did not measure Forge's
actual RSS, and you should, with `/usr/bin/time -v java -jar forge.jar sim … -n 5`.** My estimate is
**1–2 GB resident per sim JVM**, dominated by the card database, which is loaded per process and not
shared. Against an 8 GB ceiling with ~2 GB free right now:

- **As the box stands: 1–2 workers.** ~2 GB free is one worker's working set.
- **After freeing memory (stop other services; page cache will yield): realistically 2–3 workers** at
  `-Xmx1500m`–`2g`. At my throughput estimate that is roughly **200–700 games/hour**, so a 10-deck gauntlet
  × 100 games × 2 candidate configurations (2000 games) is **3–10 hours unattended** — acceptable for an
  overnight homelab job, which is what you described.
- **9–10 of the 12 cores will be idle.** This is the clearest possible signal: **jarlaxle needs RAM, not
  cores.** +16 GB (24 GB total) would support 8–10 workers and turn a 10-hour gauntlet into ~2–3 hours.
  That is the single highest-leverage purchase in the project.
- Set `-Xmx` explicitly per worker and watch for OOM kills; do not rely on the shipped `-Xmx4096m`.
- Disk is a non-issue (297 GB free; the installer is ~300 MB; JSONL logs are small — but turn off the full
  game log once you have the structured records, or thousands of games will produce gigabytes of text).
- **Toolchain check:** jarlaxle needs **only a JDK 17+** if you use the release jar — no Maven, no Node, no
  Docker, no uv. Confirm the installed Java version; Forge requires 17+ and manabrew reports that JDK 26+
  fails to *compile* Forge, so if you ever build from source, pin JDK 21. (This investigation machine is not
  jarlaxle: 20 cores, 15 GiB RAM, OpenJDK 27, **no `mvn`**.)

---

## Recommended engine, and what to prototype first

### Engine: Forge, driven by the stock `sim` CLI from a Python harness

It is the only engine with a shipped non-GUI batch mode, current Standard legality maintained as data
files, seeded shuffles, a best-of-M match loop, per-game timing already printed, and a release you can run
without a build. XMage has more cards and a friendlier licence but no headless client — you would spend
your first month writing what Forge gives you on line one. manabrew has the better *per-decision* API, which
you do not need for deck brewing, at the cost of a toolchain jarlaxle cannot host today.

**Licence note:** Forge is GPL-3.0. A Python harness that merely spawns `java -jar forge.jar` is at arm's
length. The moment you compile a controller *into* Forge (option 2 or 3 in Q8), your harness is a GPL-3.0
derivative — spike-eval says exactly this: "GPL-3.0-or-later, like Forge, into which the harness is
compiled." Decide now whether that matters to you.

### Prototype order

1. **Measure, before designing anything.** Install the `forge-2.0.16` release tarball on jarlaxle. Run
   `java -Xmx2g -jar forge.jar sim -d a.dck b.dck -D <dir> -n 20 -s 1 -q` under `/usr/bin/time -v`.
   Record: median ms/game, peak RSS, and whether any game hits the 120 s draw clock. **Every number in Q7
   and (f) of this report is an estimate until this step replaces it.** Pick `W` from the measured RSS.
2. **Build the deck-legality and integrity guard.** A Python module that reads
   `forge-gui/res/formats/Sanctioned/Standard.txt` (sets + ban list) to validate a candidate list, writes
   `.dck` files, and **fails the run if Forge reveals unsupported or "can't play well" cards.** Without
   this, step 3's results are not about the deck you think you tested.
3. **The gauntlet runner.** Python owns a work queue of (candidate, opponent, seed) triples, spawns `W`
   worker JVMs each with a long `-n` batch, parses stdout into one JSONL row per game (winner, deck,
   turns, ms, mulligans, draw flag, seed), and writes results under a run id that also records the Forge
   version and the exact command. Fixed gauntlet = a directory of `.dck` files that never changes.
4. **The statistics layer, before the agent layer.** Given the Q6 finding that seeds do not pair across
   deck variants, "deck A′ beat deck A" needs a real test, not a win-rate eyeball. Port the shape of
   `eval/sprt.py` and `eval/rating.py` from spike-eval. Decide your minimum detectable effect up front; a
   3% win-rate difference needs thousands of games, and it is better to know that before an agent proposes
   fifty one-card swaps.
5. **Then the agent loop.** The LLM takes a decklist plus the objective, reads the aggregated gauntlet
   report, proposes a bounded change set, and the harness re-runs the identical gauntlet. Note that this
   loop needs **no in-game LLM play at all** — which is why steps 1–4 are the whole project and the
   "LLM plays Magic" problem can be skipped entirely.
6. **Deferred, in this order, only if needed:** the `-o results.jsonl` patch (when stdout parsing starts
   hurting); `setAISideboardingEnabled(true)` + `-mc on` + `-m 3` for sideboard validation as a separate
   smaller experiment; a `PlayerControllerAi` subclass if you ever want the agent to pilot; a local decider
   model last, and probably on different hardware.

### The caveat to design around, not to discover later

Forge's `docs/AI.md`, verbatim: "The AI is *not* 'trained'. It uses basic rules and can be easy to overcome
knowing its weaknesses. The AI is: Best with Aggro and midrange decks, Poor to Ok in control decks, Pretty
bad for most combo decks." The same file adds "the AI is still the AI, and its limitations exist even
against itself." Combined with `complainCardsCantPlayWell` and per-card `AI:RemoveDeck` hints, this means
your gauntlet measures *Forge-AI-piloted* performance. For a tool whose purpose is to stop you buying paper
cards that don't work, the failure mode is specific and predictable: **it will over-reward aggressive,
low-decision-density cards and under-reward control, combo and anything with a subtle activated ability.**

Three mitigations worth building in from the start: use `-a <profile1> <profile2>` so the gauntlet is not
one AI's taste; score the *gauntlet* (a fixed spread of meta decks) rather than any single matchup; and keep
a human-judgement gate on the final 75 rather than shipping the agent's output straight to a buy list.

---

## What I could not verify

- **Seconds per AI-vs-AI game for Standard decks.** No published figure exists; mine is an estimate from
  the 120 s default draw clock and the 300 s caps other harnesses use. Flagged at every use.
- **Forge's actual resident memory per sim JVM.** All four data points are caps or recommendations.
- **`GameRules` default for `allowCheatShuffle`** (`sim` does not set it; the GUI drives it from
  `FPref.UI_ENABLE_AI_CHEATS`). Check before trusting results.
- **The exact `[sideboard]` section header** in `.dck` files — inferred from `DeckSection.Sideboard`; the
  precon I read had no sideboard.
- **XMage determinism / seeding.** Found nothing; absence of evidence.
- **Correctness breadth of Forge's newest-set scripting.** I verified one recent mechanic in the Java core
  and found one documented upstream per-card bug. I did not audit a set, and 746 issues are open.
- **`python-mtg`'s licence and card count** — no licence declared on PyPI; I did not open its repository.
