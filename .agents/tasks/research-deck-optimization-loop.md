# The Search and Measurement Loop for Automated MTG Deck Refinement

Read-only research investigation. Repo `/home/aiden/Projects/deckAI` contains only OpenSpec scaffolding; no project code was read because none exists. Target format: **Standard** (per owner decision mid-investigation, superseding the brief's Pauper examples).

Date of all live data in this report: **2026-11-20**. Every number below is tagged as VERIFIED (I ran the command or read the source), CITED (from a named source), ESTIMATE (my arithmetic from stated assumptions), or PROPOSAL (my design recommendation, not a finding).

---

## Summary

- **Statistically tractable on a 12-core / 8 GB box — but only for coarse decisions.** At a measured ~25 s per Forge AI-vs-AI game and a RAM-limited ~5 parallel JVMs, jarlaxle produces roughly **17,000 games/day**. With sequential testing that buys **~12–16 candidate card changes screened per day** and resolves effects of **4–5 percentage points**. It cannot resolve 1–2 pp differences (the 3rd vs 4th copy, one burn spell versus a similar one) in any practical time. Coarse decisions are exactly what the owner asked for — land count, removal count, card-draw count, which cards — so the project is viable as specified and would not be viable if the goal were fine-tuning.
- **The binding constraint is RAM, not cores.** Each game is single-threaded inside one JVM that loads the full card database; 8 GB total caps you at ~4–6 concurrent workers, so 6 of the 12 cores will sit idle. This is the single most important engineering finding and the cheapest thing to measure first.
- **Prior art on *playing* MTG with Forge is now rich; prior art on *statistically optimising decklists* is essentially nonexistent.** Three 2026 projects (grimorio, spike-eval, commander-ai-lab) wrap Forge for AI-vs-AI play, and spike-eval contains a genuinely rigorous win-rate scoring design. None of them run a hypothesis test between two decklists. The owner's loop is the missing piece, not the engine.
- **The frontier model must not play the games, and must not pick the winner.** spike-eval measures ~8 minutes and ~$0.09 per LLM-piloted game; the heuristic Forge AI plays in ~25 s for free. The LLM's job is to *prune the search space* — propose 5–10 plausible edits per round from the objective and the measured failure mode — and the statistics decide. With ~5,000 evaluations per year against a space of >10^100 legal 60-card lists, the LLM prior is not an optimisation; it is the only thing that makes the search possible at all.
- **Two measurement ceilings are real and must be stated in every report the tool produces.** Forge's AI is documented by its own authors as good at aggro, poor at control, bad at combo, and Forge's simulation mode silently runs a *weaker* AI than the desktop GUI (Flat Monte Carlo is off by default) and performs **no sideboarding at all** by default. Results are therefore "win rate as piloted by a weak heuristic AI" — tolerable for an aggro objective, disqualifying for control or combo.
- **A single aggregate win rate is a property of the gauntlet, not of the deck.** Standard's rock-paper-scissors structure means the metagame weight vector largely determines which of two lists "wins". This is a definitional problem that more games do not fix. The fix is to make the weight vector an explicit versioned input, report per-matchup, and prefer changes that survive several plausible weightings.

---

## Verified environment

| Item | Value | How verified |
|---|---|---|
| jarlaxle cores | 12 | VERIFIED `ssh jarlaxle nproc` |
| jarlaxle RAM | 7 GB total, ~2 GB available at time of check (4 GB already in use) | VERIFIED `free -g` |
| OS | Ubuntu 24.04.5 LTS | VERIFIED `/etc/os-release` |
| Java | OpenJDK 21.0.13.1 | VERIFIED `java -version` |
| Python | 3.12.3 | VERIFIED `python3 --version` |

The 8 GB figure in the brief is really **7 GB, with ~4 GB already consumed by whatever else the box runs**. Unless that is freed, concurrency is ~2 workers, not 5. Resolve this before planning any throughput.

---

## Prior-art table

| Project / paper | What it did | What it measured | How well it worked | Reusable? |
|---|---|---|---|---|
| **[hubertdungen/grimorio](https://github.com/hubertdungen/grimorio)** (GPL-3.0, Python+JS, pushed 2026-11-18, 36 MB) | Self-hosted deck builder + "Coliseum" that runs Forge 2.0.15 in Docker for AI-vs-AI Bo1/Bo3, records which cards were drawn/cast/stuck in hand, suggests swaps with reasons, maintains an Elo per deck. Imports from MTGTop8/Moxfield/Archidekt/Goldfish. SQLite (`grimorio.db`). | Per-card "win contribution", usage, deck Elo. **No hypothesis test.** Its own README advises "10+ games per deck is a good start". | Closest thing to the owner's stated goal, and the per-card event recording is genuinely the right data model. But 10 games has a standard error of ~16 pp — three orders of magnitude short of a decision. Its swap suggestions are heuristic attribution, not measurement. | **Partly.** The Forge-in-Docker runner, the Scryfall data pipeline, the deck importers and the per-game card-event schema are directly reusable and save weeks. The statistics layer does not exist. **GPL-3.0: reusing code makes the owner's project GPL-3.0.** Verdict: study the architecture, consider vendoring the Forge runner, build the search/measurement loop yourself. |
| **[lumlaolao/spike-eval](https://github.com/lumlaolao/spike-eval)** (GPL-3.0, Python, pushed 2026-11-19) + [write-up](https://folds.ink/posts/mtg-benchmark) | Harness that seats an LLM in Forge via tool calls with full game state and an enumerated legal-action list; plus a 500-puzzle eval. Its `docs/eval/SCORING.md` defines a full-game scoring system: **mirror panels** (pilot on deck *d* vs Forge AI on deck *d*, so deck strength cancels by symmetry), **cross panels** with AI-vs-AI controls on the same deck pair, **seed-paired** comparisons across both seat orders, 100 games/cell, Bradley-Terry ratings with the Forge AI pinned at 1500, decks pinned by `sha256[:12]`, a held-out eval-only seed bank, null "sanity arms" (floor / random / empty / garbage policies), and a benchmark version that controls which reports may be pooled. | LLM *pilot* skill. Headline metric is puzzle solve rate; full-game win rates are a secondary scored artefact. | The harness works well enough that human friends could not tell they were playing a model. The author's measured cost: ~8 min and ~$0.09 per LLM game. | **Yes, conceptually, and this is the most valuable find in the investigation.** Its variance-control design is exactly what the owner needs with the roles of deck and pilot swapped. Mirror panels, seed pairing, both seat orders, AI-vs-AI controls, deck hashing, held-out seed banks and a poolability version are the answer to questions 4 and 8, already worked out. GPL-3.0 again. |
| **[KoalaTrapLord/commander-ai-lab](https://github.com/KoalaTrapLord/commander-ai-lab)** (no licence = all rights reserved, Python, pushed 2026-04-06) | Forge batch simulation + a hand-written Python Monte Carlo engine + a 7-step Ollama deck builder with "simulation insights injected into prompts" + RAG coach + Unity client. Overnight run script that nudges `learned_weights.json` from decision logs. | Card weights learned from decision logs; neural net on outcomes. No hypothesis test. | **Reports the one hard throughput number in the literature: ~0.04 Forge sims/sec single-threaded, i.e. ~25 s per game, each game spawning a JVM subprocess.** Commander (4-player), Windows. The README itself says the feedback loop "is a no-op until real sim data exists". | **No.** No licence, stale since April 2026, hardcoded Windows paths, Commander-only. Take two things: the 25 s/game figure and the overnight-run + weight-update architecture. |
| **[GregorStocks/mage-bench](https://github.com/GregorStocks/mage-bench)** (Java, 71 stars, pushed 2026-11-18) | LLM harness on XMage rather than Forge. | LLM play quality. | Not examined in depth. | Not for this project — the engine choice is settled elsewhere as Forge. Worth a look only if Forge's AI proves unusable. |
| **[wingedsheep/argentum-engine](https://github.com/wingedsheep/argentum-engine)** (Kotlin, 87 stars, pushed 2026-11-20, 1.8 GB) | Independent MTG rules engine with gym-server / gym-trainer components for RL. | RL agent training. | Not examined in depth. | Not now. A from-scratch engine will have a far smaller card pool than Forge's ~30k, which is fatal for Standard legality coverage. The gym-server idea matters only if the project later wants a learned pilot. |
| **[taoroalin/mtg-llm](https://github.com/taoroalin/mtg-llm)** (Python, 2 MB) | LLM scaffolding to play MTG. | — | Tiny, 1 star. | No. |
| **Churchill, Biderman & Herrick, [Magic: The Gathering is Turing Complete](https://arxiv.org/abs/1904.09828)** (FUN 2021) | Embeds a universal Turing machine in a legal game of Magic. | Computability of optimal play. | Settled: optimal play is at least as hard as the Halting Problem, and even deciding the winner of a game with no non-trivial decisions remaining is undecidable. | **Relevant as a bound, not a tool.** It is the formal reason nobody will ever "solve" a matchup analytically, and the reason simulation is the only available evaluator. Quote it when the project is accused of being unprincipled. |
| **Biderman, [Magic: the Gathering is as Hard as Arithmetic](https://arxiv.org/abs/2003.05119)** | Strengthens the above: "mate-in-n" is Δ⁰-hard, optimal two-player play is non-arithmetic. | Same. | Same. | Same. |
| **[Mapping Hearthstone Deck Spaces through MAP-Elites with Sliding Boundaries](https://arxiv.org/abs/1904.10656)** | Quality-diversity search over Hearthstone decks: produces an archive of high-performing decks spread across behavioural dimensions rather than one optimum. | Win rate + behavioural descriptors. | Worked; produced interpretable deck-space maps. | **Conceptually, strongly.** The "archive of diverse good decks indexed by behaviour" idea maps directly onto "give me a fast deck and a grindy deck and show me the trade-off" — i.e. the Pareto front of question 5. Not reusable as code (Hearthstone, different engine). |
| **[Deep Surrogate Assisted MAP-Elites for Automated Hearthstone Deckbuilding](https://arxiv.org/html/2112.03534v4)** | Trains a surrogate model to predict deck performance so MAP-Elites needs far fewer expensive simulated evaluations. | Win rate, predicted vs simulated. | The paper's whole premise is that MAP-Elites "requires a large number of expensive evaluations" — exactly the owner's problem. | **The single most relevant methodological paper.** A surrogate trained on the owner's own accumulated game records could pre-rank candidate edits before spending games on them. This is a phase-2 idea: it needs thousands of labelled decklists first, which the loop generates as a by-product. |
| **[Evolutionary Approach to Collectible Card Game Arena Deckbuilding using Active Genes](https://arxiv.org/abs/2001.01326)** | Evolutionary algorithm for Legends of Code and Magic arena drafting, with an "active gene" operator restricting mutation to the subsequence relevant to the current draft. | Non-deterministic simulation-estimated fitness. | Statistically better draft policies than baselines, with explicit accounting of computational cost per variant. | **Conceptually useful.** The active-gene restriction is the right instinct for decklists too: mutate only the slots currently under question, not the whole 60. |
| **[Introducing the Hearthstone-AI Competition](https://arxiv.org/abs/1906.04238)** and the [Optimizing Hearthstone Agents using an EA](https://arxiv.org/pdf/2410.19681v1) line | Competition framework and EA-tuned agents for a CCG. | Agent strength. | Established benchmark. | Low. These optimise the *pilot*, which another investigation covers. |
| **[luinlulu/magique](https://github.com/luinlulu/magique)** | C++ genetic algorithm over MTG decklists built from a personal collection CSV, with "mechanics and interactions models" from MTGJSON card text. | A *static* fitness from modelled card interactions — **no simulated play at all**. | Unknown; no published results. | No. It is the cautionary example: a GA over decklists whose fitness is a hand-built synergy heuristic measures the heuristic, not the deck. |
| **[slightlymagic.net thread: "Using the Forge AI and Machine Learning to build better decks"](https://slightlymagic.net/forum/viewtopic.php?f=52&t=18164)** | Community discussion of exactly this project, circa the Forge forum. | — | **Nothing was built.** The thread identifies two problems that remain the real ones: crossover between differently-coloured decks produces a broken mana base, and the search will converge on cards that beat the *Forge AI* rather than cards that are good. | As evidence of the gap. **This is the honest headline for the prior-art question: the "older academic work using Forge" that the brief hoped existed does not appear to exist.** I searched for it specifically and found a forum thread, not a paper. |
| **Forge's own deck generation** | VERIFIED: `forge-core/.../deck/generation/` contains `DeckGeneratorBase`, `DeckGeneratorMonoColor`, `DeckGenerator2Color` … `5Color`, driven by `getLandPercentage()` / `getCreaturePercentage()` / `getSpellPercentage()` and an `adjustDeckSize()` pass. | Nothing — it is a *constructor*, not an evaluator. | Produces playable random decks for its quest/gauntlet modes. | **Yes, narrowly.** The land/creature/spell ratio logic and `countLands()` are a sane starting prior for "what does a legal, playable 60 look like", and the `RemAIDecks` card flag (cards the AI does not know how to play) is a hint set the owner's candidate filter should respect. |
| **[Frank Karsten's colour-source tables](https://strategy.channelfireball.com/home/how-many-sources-do-you-need-to-consistently-cast-your-spells-a-2022-update/)** (summarised [here](https://sites.google.com/view/peasant-magic/articles/magic-deckbuilding/how-many-sources-do-you-need-to-consistently-cast-your-spells)); [MTGGoldfish hypergeometric primer](https://www.mtggoldfish.com/articles/brewer-s-minute-hypergeometric-distribution-in-deck-building) | Closed-form / Monte-Carlo tables for how many sources of a colour you need to cast a spell on curve at ~90% reliability, under the London mulligan, for 60- and 80-card decks. | Probability of casting on curve. | The accepted standard in competitive deck building. | **Yes, and it is load-bearing.** This is the free, deterministic, zero-game answer to "keep the mana base consistent with the spells after each change". Never spend games discovering a mana base. |
| **Metagame tooling: [Badaro/MTGODecklistCache](https://github.com/Badaro/MTGODecklistCache)** | JSON cache of MTGO / Melee / Manatraders / Topdeck tournaments; the standard machine-readable source for years. | Tournament results and decklists. | **DEAD.** VERIFIED from its README: melee.gg scraper broke 2025-03-19, Manatraders disabled 2025-03-20, mtgo.com broke 2025-06-10 and "this project will be officially shut down". Tools repo archived 2025-09-24. | **No — and anything that recommends it is out of date.** See the gauntlet section for live alternatives I tested. |
| **[Badaro/MTGOArchetypeParser](https://github.com/Badaro/MTGOArchetypeParser)** | Rules-based archetype detection from decklists. | Archetype labels. | Was the standard; depends on the dead cache for input but the rule engine itself is independent. | Maybe later. The owner does not need to *classify* decks — he is choosing a handful of named gauntlet decks by hand. Archetype clustering is a problem he does not have. |

**Honest assessment of thinness.** Automated deckbuilding evaluated by simulated play is a real research area *in Hearthstone* (MAP-Elites line, well-measured, reproducible). In Magic it is thin to the point of absence: lots of engines, lots of LLM-play harnesses as of 2026, one dead GA repo with no simulated fitness, one forum thread, and no paper I could find that evolves MTG decklists against simulated play. Deck-archetype clustering and metagame analysis tooling exists and is mature but solves a problem the owner does not have. Goldfish simulators (solitaire draw simulators) exist in abundance but measure draw consistency, not matchup win rate; the hypergeometric tooling above is the useful part of that family.

---

## Search-algorithm comparison

The decisive number first. Scryfall reports **5,460 Standard-legal cards** (VERIFIED: `legal:standard -is:digital`, 2026-11-20). The number of 60-card main decks with at most 4 copies each is well over 10^100. The measurement loop affords roughly **5,000 evaluations per year**. No search algorithm extracts signal from 5,000 samples of a 10^100 space. Every row below should be read as "what do we do with a space the LLM has already cut down to ~20 cards and ~15 live decisions".

| Approach | How it would work here | Pros for a solo builder | Cons | Verdict |
|---|---|---|---|---|
| **Hill climbing on card counts** | State = the count vector over a fixed ~20-card candidate set plus land count. Move = ±1 copy of one card, compensated by ∓1 elsewhere. Accept if the test says better. | Simplest thing that works. Every state is a legal, playable 60. Each step is independently verifiable and *explainable* — "we went from 3 to 4 Cards because it tested +4 pp". Naturally resumable after a crash. Pairs perfectly with sequential testing. | Local optima; cannot discover a card outside the candidate set; cannot make the coordinated multi-card change that an archetype shift needs. | **Recommended as the core loop.** The local-optimum objection is answered by the LLM refreshing the candidate set each round, which is a non-local move generator. |
| **Genetic algorithm with crossover over decklists** | Population of lists, crossover mixes card pools, mutation swaps cards, fitness = gauntlet win rate. | Can in principle discover coordinated multi-card changes. The intuitive choice, and the one the forum thread reached for. | Fatal at this budget. A population of 30 with 20 generations is 600 evaluations *per run*, each needing ~1,100 games = 660,000 games = **38 days**, to do one GA run with no guarantee. Crossover between differently-coloured parents produces broken mana bases (named in the [Forge forum thread](https://slightlymagic.net/forum/viewtopic.php?f=52&t=18164)); repairing them means a hand-written repair operator that encodes exactly the Magic knowledge the LLM supplies more cheaply. Fitness is noisy, so selection amplifies noise into drift. | **Reject.** The one salvageable idea is the "active gene" restriction from [arXiv:2001.01326](https://arxiv.org/abs/2001.01326): mutate only the slots currently in question. That is hill climbing. |
| **Multi-armed bandits / successive halving / Hyperband** ([Li et al.](https://arxiv.org/pdf/1603.06560)) | Arms = candidate lists. Allocate games adaptively, halve the field repeatedly, promote survivors to longer runs. | Exactly the right shape: cheap evaluations that can be stopped early, arms whose value is a noisy mean. Kills obviously bad candidates in ~200 games. Trivial to parallelise across workers. | Designed for 50+ arms; with 5–10 LLM-proposed candidates per round the bookkeeping outweighs the gain. Gives a ranking, not a calibrated "is this better than the incumbent" decision, which is what the owner wants recorded. | **Adopt the mechanism, not the framework.** Use SPRT per candidate against a fixed incumbent baseline — which *is* a per-arm early-stopping rule, and additionally gives a calibrated accept/reject. Revisit Hyperband only if a round ever has >20 candidates. |
| **Bayesian optimisation over counts** | GP or TPE over the ~20-dimensional integer count vector, acquisition function picks the next list. | Sample-efficient in theory, and the reduced count space is exactly the kind of low-dimensional box BO is built for. | Observation noise is enormous relative to the effect size (one 1,100-game evaluation has SE ≈ 1.5 pp and the effects are 3–5 pp), so the GP spends its budget modelling noise. BO needs tens of evaluations before its model beats random, and the owner has ~15/day of which most should be spent on decisions he can explain. Integer-constrained, sum-constrained (must total 60) domains need custom handling. The result is unexplainable, which defeats the purpose of a tool that is supposed to teach the owner what to buy. | **Reject for now.** The honest version: BO's advantage over hill climbing appears when evaluations are cheap enough to afford 100+ of them and the surface is smooth. Neither holds. |
| **One-card-at-a-time A/B swaps from an LLM-proposed pool** | LLM reads the objective, the current list, and the measured per-matchup statistics; proposes 5–10 specific edits with reasons; each is screened by SPRT against the incumbent; winners are accepted one at a time. | Matches how the decisions are actually made and reported. Every accepted change has a reason and a measured effect size, which is the artefact the owner wants. Uses the LLM where it is irreplaceable (Magic knowledge) and never where it is unreliable (judging a 3 pp difference). Fits the budget exactly. | Depends on the quality of the LLM's proposals; will miss a change no proposal contained. Serial acceptance means the loop cannot exploit interactions between two simultaneously-good changes. | **Recommended.** This plus hill climbing on counts is the whole search algorithm. |

### The structural question: should the LLM prune, and leave the statistics to decide?

**Yes, unambiguously, and this is the project's core design decision.** The argument is arithmetic, not taste. The search has ~5,000 evaluations per year against >10^100 candidates. Any uninformed search is a random sample of measure zero. The LLM is not an optimiser in this loop; it is the **prior over a space the optimiser could never cover**, and it is the only available source of that prior short of the owner doing the proposing himself.

The division of labour should be strict, because each side fails in the other's domain:

- The LLM proposes and explains. It is allowed to be wrong; it is not allowed to decide.
- The statistics decide. They are allowed to reject every proposal in a round; they are not allowed to propose.
- Nothing the LLM says about *how much better* a card is ever enters the record. Only measured effect sizes with confidence intervals do.

A useful corollary: because proposals are cheap and evaluations are not, the LLM should over-propose and the *filter* should be a cheap deterministic one (legality, mana-base feasibility, card availability in the installed Forge build) before any game is played. See question 7.

### Legality and construction constraints

| Constraint | Who enforces it | Status |
|---|---|---|
| 4-copy limit, 60-card minimum main, 0–15 sideboard | VERIFIED: `DeckFormat.Constructed = Range.of(60, MAX), Range.of(0, 15), 4` in `forge-core/src/main/java/forge/deck/DeckFormat.java:47`, checked by `getDeckConformanceProblem(Deck)` | **Forge has the rule but simulation mode never calls it.** `SimulateMatch.simulate()` loads decks via `DeckSerializer.fromFile()` and starts the match with no conformance check (VERIFIED by reading `forge-gui-desktop/src/main/java/forge/view/SimulateMatch.java`). An illegal list will happily play. **The harness must validate.** |
| Standard set legality + ban list | VERIFIED: Forge ships `forge-gui/res/formats/Sanctioned/Standard.txt` with `Sets:` (21 sets, WOE through TRK) and `Banned:` (13 cards, e.g. Cori-Steel Cutter, Heartfire Hero, Monstrous Rage, Up the Beanstalk, Vivi Ornitier) | There is **no `DeckFormat.Standard`** and no `-f standard` in sim mode; `-f` accepts only Constructed / Commander / Oathbreaker / TinyLeaders / Brawl / MomirBasic / Vanguard / MoJhoSto. Rotation legality is not a simulation-mode concept. The harness must validate against Scryfall *and* against this file. |
| Card actually implemented in the installed Forge build | Forge's card scripts | **This is the constraint nobody plans for.** A card can be Standard-legal on Scryfall and absent or buggy in the pinned Forge version. The candidate filter must intersect Scryfall's Standard-legal set with the installed Forge card pool, and should also exclude cards flagged `RemAIDecks` (VERIFIED: Forge's card-scripting API documents this flag for cards "too narrow for random decks"; `PlayerControllerAi.sideboard()` already skips them with the comment "don't sideboard in anything that we don't know how to play"). A card the AI cannot pilot will test badly for reasons that have nothing to do with the card. |
| Mana base consistent with the spells | Nobody — must be built in | **PROPOSAL:** after every accepted spell change, re-derive the mana base deterministically from Karsten's colour-source requirements rather than searching for it. Compute each spell's required sources from its mana cost and the turn you intend to cast it, take the per-colour maximum, and solve for a land configuration that meets every requirement at the ~90% threshold. This is a closed-form step costing zero games. Only when the requirements are *infeasible* at 24–26 lands does the loop have a real decision to test (cut a colour, or cut the demanding spell), and that is a decision worth games. Treat total land count as one explicit hill-climbing dimension and colour distribution as derived, not searched. |

---

## The arithmetic, worked explicitly

### Part 1 — sample size for a fixed-*n* comparison

Two-proportion, two-sided, α = 0.05. Per-arm sample size:

```
n_per_arm = (z_{1-α/2} + z_{1-β})² · [p_A(1-p_A) + p_B(1-p_B)] / δ²
```

With p ≈ 0.5 in both arms (the worst case for variance), `p_A(1-p_A) + p_B(1-p_B) = 0.5`:

```
z_{0.975} = 1.959964
z_{0.80}  = 0.841621   →  (1.959964 + 0.841621)² = 2.801585² = 7.84888
z_{0.95}  = 1.644854   →  (1.959964 + 1.644854)² = 3.604818² = 12.99471
```

So `n_per_arm = K · 0.5 / δ²` and `n_total = K / δ²`:

| Effect δ | 80% power, per arm | 80% power, **total games** | 95% power, per arm | 95% power, **total games** |
|---|---|---|---|---|
| 2 pp (0.02) | 7.84888 × 0.5 / 0.0004 = **9,811** | **19,622** | 12.99471 × 0.5 / 0.0004 = **16,243** | **32,487** |
| 3 pp (0.03) | 7.84888 × 0.5 / 0.0009 = **4,361** | **8,721** | 12.99471 × 0.5 / 0.0009 = **7,219** | **14,439** |
| 5 pp (0.05) | 7.84888 × 0.5 / 0.0025 = **1,570** | **3,140** | 12.99471 × 0.5 / 0.0025 = **2,599** | **5,198** |

For a secondary metric with a lower base rate — "wins by turn 5" at p ≈ 0.30, where `p(1-p) = 0.21` per arm — the same 3 pp absolute difference at 80% power needs `7.84888 × 0.42 / 0.0009 = 3,663` per arm, **7,325 total**: slightly *cheaper* than a win-rate difference, because variance is lower away from p = 0.5.

### Part 2 — sequential testing collapses these numbers

The fixed-*n* table is the worst case: it pays full price even for a change that is obviously terrible. SPRT stops as soon as the evidence is decisive and [minimises expected sample size among tests with the same error rates](https://arxiv.org/html/2410.16076v1). For Bernoulli win/loss, each game adds `log(p₁/p₀)` on a win and `log((1-p₁)/(1-p₀))` on a loss; stop when the log-likelihood ratio crosses `log(β/(1-α))` or `log((1-β)/α)`.

I simulated this (4,000 trials per cell, α = β = 0.05). **VERIFIED by simulation**, bounds H₀: p = 0.50 versus H₁: p = 0.54 — i.e. "screen for a +4 pp improvement":

| True win rate | Mean games to a decision | Median | 90th pct | Accept rate |
|---|---|---|---|---|
| 0.45 (clearly worse) | **266** | 243 | 418 | 0.03% |
| 0.48 | 455 | 390 | 792 | 0.4% |
| 0.50 (no effect) | **845** | 672 | 1,605 | 4.3% |
| 0.52 (indifference zone) | **1,398** | 1,074 | 2,926 | 49.3% |
| 0.54 (the target effect) | **824** | 668 | 1,583 | 94.9% |
| 0.56 | 464 | 401 | 803 | 99.8% |
| 0.60 | 232 | 216 | 353 | 100% |

With wider screening bounds (H₀: 0.50 vs H₁: 0.57) the cost drops roughly three-fold: 125 games to kill a 0.45 candidate, 276 under the null, 453 in the worst case.

The practical reading: **a worthless change dies in ~250–850 games instead of 8,721, and a genuinely good one is confirmed in ~820.** The expensive case is the indifference zone — a change that is real but only +2 pp — and that is precisely the case where the owner should not care. Cap each test at 4,000 games (the p90 under the worst cell is ~2,900) and treat a cap-out as "no evidence, reject".

Fishtest, the reference implementation of this discipline for chess engines, additionally uses the **[pentanomial model over game pairs rather than per-game trinomial outcomes, and expresses bounds in normalised Elo so test duration is independent of the draw rate](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-Mathematics.html)**, and GSPRT (maximum-likelihood substitution for nuisance parameters) rather than plain SPRT. The game-pair idea transfers directly and is the basis of the variance reduction below.

### Part 3 — variance reduction, and how much actually survives

| Technique | Mechanism | Realistic gain | Note |
|---|---|---|---|
| **Fixed gauntlet, identical across arms** | Makes matchup a blocking factor instead of a source of variance. | **Large and already assumed.** Without it, between-matchup variance (win rates genuinely ranging 0.30–0.70) would dominate everything. | This is the owner's design and it is correct. |
| **Mirrored play/draw** | Each configuration plays each opponent equally often on the play and on the draw, as matched pairs. | Removes the play/draw nuisance effect entirely. Worth a few pp of bias, near-zero variance cost. | spike-eval does exactly this ("the pilot plays `7800..7849` **in both seat orders**"). **Mandatory.** |
| **Shared seeds / common random numbers** | `-s [S]` sets `MyRandom.setRandom(new Random(seed))` (VERIFIED in `SimulateMatch.java`; **undocumented in `docs/AI.md`** — it is in the in-code `argumentHelp()` only). | **Much less than the chess analogy suggests.** The seed is a single global stream set once per process. Two different decklists diverge from the first differing random draw, so you get the same *opponent* and the same *play/draw assignment*, not the same opening hands. And within one process the stream for game *k* depends on how many draws games 1…*k−1* consumed, so exact pairing requires one game per JVM invocation — which costs a full card-DB load per game. | Honest estimate: **ρ ≈ 0.1–0.3**, giving a `(1 − ρ)` = 10–30% reduction in total games for a paired design. Worth taking (the same seed costs nothing when you are launching the process anyway) but do not build the budget on it. |
| **Playing both sides / mirror panels** | spike-eval's trick: run the pilot on deck *d* against the same pilot on deck *d* so deck strength cancels by symmetry. | Not applicable in the owner's direction — he *wants* the deck effect. The useful inversion is the **AI-vs-AI control**: for each gauntlet matchup, periodically run the frozen baseline list against that opponent to confirm the measurement rig has not drifted. | spike-eval's cross panel does precisely this ("Each cell has an **AI-vs-AI control** on the same deck pair"). Cheap insurance; adopt. |
| **Stratified estimator with fixed metagame weights** | Compute per-matchup win rates, then combine as `Σ wᵢ p̂ᵢ`. Variance under proportional allocation `nᵢ = wᵢN` is `(1/N) Σ wᵢ pᵢ(1−pᵢ)`. | Because rock-paper-scissors spreads `pᵢ` away from 0.5, `pᵢ(1−pᵢ)` falls below 0.25 — e.g. a gauntlet with rates {0.65, 0.45, 0.60, 0.35, 0.55, 0.70, 0.40, 0.50} averages ≈ 0.2375. **~5% fewer games than the p = 0.5 worst case.** | So the matchup spread makes the *aggregate* marginally cheaper, not dearer. The sample sizes in Part 1 are conservative. The cost of RPS structure lands somewhere else entirely — see Part 5. |

**Allocation across the gauntlet, a point worth getting right.** For minimum variance of the weighted aggregate, allocate games proportional to metagame share (`nᵢ ∝ wᵢσᵢ`, and the `σᵢ` are similar, so `nᵢ ∝ wᵢ`). For equal *diagnostic* precision per matchup, allocate equally. These conflict. **PROPOSAL:** allocate proportional-to-share during screening, because the screening test is a decision about the aggregate; run a separate periodic equal-allocation "diagnostic sweep" at lower frequency whose only purpose is to produce per-matchup numbers for the LLM to reason about.

### Part 4 — throughput and the realistic length of an optimisation run

**Seconds per game.** The only published figure I found is **~0.04 Forge sims/sec single-threaded ≈ 25 s/game** from commander-ai-lab, for 4-player Commander with a JVM spawned per game on Windows. Two-player Standard should be faster per decision but Standard games are longer and more complex than the fast Pauper aggro the brief originally assumed. Forge's own `-c` draw clock defaults to **120 s per game** (VERIFIED, `GameRules.simTimeout = 120`), which is a hard ceiling by construction, and Forge's docs warn games "can lag and become almost unbearably long when the AI has a lot to think about".

> **ASSUMPTION, to be measured on day one: 25 s per game for 2-player Standard, Forge AI both seats, `-mc off`.** This is the figure everything below rests on. Forge prints `Game Result: Game N ended in M ms` for every game (VERIFIED in `SimulateMatch.simulateSingleMatch`), so the harness measures it for free and the budget model self-corrects. Sensitivity table included.

**Workers.** Each game runs in one thread ("will run match in the same thread", VERIFIED) inside a JVM holding the full card database. Parallelism must come from multiple processes. **RAM is the constraint:** grimorio's own install guide asks for "~4 GB of free RAM for games" for a Forge-in-Docker setup. At an estimated 1.0–1.5 GB of heap per worker and ~6.5 GB usable, that is **4–6 workers** — not 12. ESTIMATE; measure with `/usr/bin/time -v` on a single worker before committing.

Games per day = `86,400 / s × W`:

| s/game ↓ \ workers → | 4 | 5 | 6 | 10 (if RAM allowed) |
|---|---|---|---|---|
| 10 s | 34,560 | 43,200 | 51,840 | 86,400 |
| **25 s (planning case)** | 13,824 | **17,280** | 20,736 | 34,560 |
| 40 s | 8,640 | 10,800 | 12,960 | 21,600 |
| 60 s | 5,760 | 7,200 | 8,640 | 14,400 |

**Planning case: 17,280 games/day.**

Candidate changes per day:

```
Fixed-n, 5 pp @ 80%:   17,280 / 3,140  =  5.5 candidates/day
Fixed-n, 3 pp @ 80%:   17,280 / 8,721  =  2.0 candidates/day
Fixed-n, 2 pp @ 80%:   17,280 / 19,622 =  0.9 candidates/day

SPRT [0, +4pp], mean ~1,100 games over the realistic mix of
true effects (most proposals are worthless → ~250-850 games;
a few are real → ~820; the occasional +2pp → ~1,400):
                       17,280 / 1,100  = 15.7 candidates/day
   less ~10% for periodic baseline re-measurement and controls
                                        ≈ 14 candidates/day
```

So the honest regime is:

| Stage | Method | Games per candidate | Throughput |
|---|---|---|---|
| **Screen** | One-sample SPRT against a frozen incumbent baseline, bounds [0, +4 pp], cap 4,000 | ~1,100 mean | **~14/day** |
| **Confirm** an accepted change | Paired fixed-*n*, 3 pp @ 80% | 8,721 | ~2/day |
| **Validate** the final list | Held-out archetypes, fixed-*n*, 5 pp @ 80% | 3,140 | — |

**Why a frozen baseline rather than a paired run.** Measuring the incumbent once per generation (say 8,000 games, SE = √(0.25/8,000) = **0.56 pp**) and then running each candidate as a one-sample test against that constant halves the cost per candidate versus playing both arms. The baseline cost amortises over the ~10–20 candidates of that generation. It must be re-measured whenever anything in the identity tuple changes — engine version, gauntlet, AI profile, sim timeout — or whenever a change is accepted (because the incumbent moved). Use the paired design only for the confirmation stage, where correctness matters more than throughput.

**Length of a run.** At ~14 screened candidates/day with a plausible 15% accept rate, that is ~2 accepted changes/day. Going from a rough first draft to a converged list plausibly takes 15–25 accepted changes, so **~10 days of continuous overnight running**, plus confirmation runs (~0.5 day each for the handful that matter) and a final held-out validation. Call it **two weeks per deck-and-objective**, assuming the box is otherwise idle and nothing breaks. ESTIMATE, with wide error bars: the accept rate is the parameter I am least able to predict, and it depends entirely on how good the LLM's proposals are.

### Part 5 — what rock-paper-scissors actually costs

This is where the matchup structure bites, and it is not in the aggregate's variance (Part 3 showed that is *slightly* helped). It is in per-matchup resolution. Under proportional allocation, a gauntlet member with 4% metagame share receives 4% of the games. To resolve a 5 pp change *within that matchup* at 80% power needs 3,140 games in that matchup alone, hence:

```
3,140 / 0.04 = 78,500 total games = 4.5 days at 17,280/day — for ONE candidate change.
```

And at a realistic screening budget of 1,100 games spread proportionally, that 4% matchup receives **44 games**: standard error 7.5 pp, 95% CI ±15 pp. Even the biggest matchup (12% share) gets 132 games, SE 4.3 pp.

**Therefore: per-matchup win rates are diagnostic, never decision-grade.** They exist to tell the LLM where to look. Decisions are made on the weighted aggregate. Any report that presents a per-matchup number must carry its confidence interval, or the owner will act on noise — which is the single most likely way this project produces a confidently wrong decklist.

---

## Q1 — Prior art

**Verdict.** Engines and LLM-play harnesses for Forge are abundant as of late 2026; statistical decklist optimisation on top of them does not exist. The owner is building the missing layer, not duplicating work. Two projects (grimorio, spike-eval) are close enough that he should read them before writing a line of code — grimorio for the Forge-running plumbing and the per-card event schema, spike-eval for the measurement discipline. The academic Forge-based GA work the brief hoped to find appears not to exist; the nearest rigorous work is the Hearthstone MAP-Elites line, which is well-measured and transfers conceptually.

**Evidence.** See the prior-art table. Load-bearing items: grimorio's README advising "10+ games per deck is a good start" (its suggestions are heuristic, not tested); spike-eval's `docs/eval/SCORING.md` mirror/cross panels with seed pairing, both seat orders, AI-vs-AI controls, deck `sha256[:12]` pins and a held-out seed bank; commander-ai-lab's measured 0.04 Forge sims/sec; MTGODecklistCache's README announcing its own shutdown; the Forge forum thread where this idea was raised and never built.

**Confidence.** High on what exists and what each does, because I read the sources. Medium on completeness of the search — a paper could exist under terminology I did not try, and I did not search non-English literature or pre-2015 conference proceedings exhaustively.

---

## Q2 — Search algorithm

**Verdict.** LLM-pruned candidate pool + one-card-at-a-time A/B swaps + hill climbing on counts. Reject genetic algorithms and Bayesian optimisation at this budget; adopt sequential-testing early stopping (the useful half of the bandit family) as the per-candidate mechanism rather than Hyperband as a framework. The LLM must prune; the statistics must decide; neither may do the other's job. Derive the mana base deterministically from Karsten's tables after every accepted spell change rather than searching for it.

**Evidence.** The comparison table above, plus: 5,460 Standard-legal cards (VERIFIED via Scryfall); ~5,000 evaluations/year (from the throughput arithmetic); a 30×20 GA run costing 38 days of continuous compute (arithmetic above); `DeckFormat.Constructed` enforcing 60/0–15/4 but simulation mode never invoking the check (VERIFIED from `SimulateMatch.java`); Forge shipping its own `Standard.txt` set and ban list; the `RemAIDecks` flag for cards the AI cannot pilot.

**Confidence.** High on rejecting GA and BO — that follows from the evaluation budget, which is arithmetic. High on the legality findings, which are read from source. Medium on hill climbing being the *best* available choice rather than merely the best-justified one; a surrogate-assisted approach ([arXiv:2112.03534](https://arxiv.org/html/2112.03534v4)) could beat it once the loop has generated a few thousand labelled lists, which is a phase-2 question.

---

## Q3 — The gauntlet

**Verdict.** Eight archetypes weighted by MTGTop8 share, covering ~66% of the observed field, plus two held out for validation. Source lists from MTGTop8 (HTML scrape, verified working) and TopDeck.gg (free authenticated REST API with a `format: "Standard"` filter). Pilot both sides with the *same* AI profile. Date and hash the gauntlet; a Standard gauntlet decays continuously as sets release and discontinuously at rotation, and results across a rotation boundary are not comparable.

**Evidence — sources I tested today.**

| Source | Reachable from this box | Machine-readable? | Verdict |
|---|---|---|---|
| **[MTGTop8](https://www.mtgtop8.com/format?f=ST)** | VERIFIED HTTP 200, 72 KB | Yes, by scraping. `format?f=ST` gives archetype names, internal ids and metagame percentages; `archetype?a=<id>&meta=50&f=ST` gives event/deck id pairs; **`https://www.mtgtop8.com/mtgo?d=<deckid>` returns a plain-text decklist** (VERIFIED: fetched 396 bytes of `4 Razorkin Needlehead` / `19 Mountain` style lines). No API, no documented terms for automated access. | **Primary source.** Scrape politely (rate-limit, cache, identify yourself); the decklist endpoint is already in the MTGO/Apprentice format most tools read. |
| **[TopDeck.gg API](https://topdeck.gg/docs/tournaments-v2)** | VERIFIED HTTP 200 | Yes — documented REST API, free key, `POST /v2/tournaments` with `{"game": "Magic: The Gathering", "format": "Standard", "start": <epoch>}`. Rate limits documented (5/min for bulk tournament queries, 100/min for most endpoints). **Attribution to TopDeck.gg is required.** Note their decklist/metagame *product* feature is a paid subscription after 14 days; the API itself is described as free. | **Secondary source, worth the key.** Proper API beats scraping for reliability. Verify what decklist detail the free tier actually returns before depending on it. |
| **[MTGGoldfish](https://www.mtggoldfish.com/metagame/standard)** | **NOT reachable from this box** — `curl` returns HTTP 000, and the fetch tool timed out. | Unknown. Has metagame share pages and per-deck exports in the browser; no public API. | **Unverified.** Could be a network block on this machine, a Cloudflare challenge, or a TLS-fingerprint block. Test from jarlaxle before relying on it. Do not build a scraper against it on the assumption it works. |
| **[Moxfield API](https://api.moxfield.com/)** | VERIFIED **HTTP 403** on an unauthenticated request | Has an API but gates it. | **No.** Moxfield restricts programmatic access to approved clients. Do not build against it. |
| **[Badaro/MTGODecklistCache](https://github.com/Badaro/MTGODecklistCache)** | Repo reachable | Was the best option | **DEAD** — officially shut down 2025-06-10 per its own README. |
| **melee.gg** | Not tested in depth | Organiser-facing API | Its public scraping path broke in 2025 (per MTGODecklistCache's notes). Low priority. |

**Evidence — the actual current Standard metagame.** VERIFIED by parsing MTGTop8's `format?f=ST` page on 2026-11-20 (405 decks in the window):

| Archetype | Share | Bucket |
|---|---|---|
| Boros Aggro | 12% | Aggro (73% total) |
| Mardu / "Other – Aggro" | 11% | Aggro |
| Dimir Aggro | 10% | Aggro |
| Selesnya Aggro | 9% | Aggro |
| Dimir Control | 9% | Control (24% total) |
| Jund Aggro | 8% | Aggro |
| Mono Green Aggro | 6% | Aggro |
| Izzet Control | 6% | Control |
| UW Control | 6% | Control |
| Azorius Aggro | 5% | Aggro |
| Orzhov Aggro | 4% | Aggro |
| UR Aggro | 4% | Aggro |
| 4/5C Control | 2% | Control |
| Rakdos Aggro, Esper Aggro | 1% each | Aggro |
| Reanimator | 1% | Combo (2% total) |

**PROPOSAL — gauntlet composition.** Eight training archetypes: Boros Aggro (12), Dimir Aggro (10), Selesnya Aggro (9), Dimir Control (9), Jund Aggro (8), Mono Green Aggro (6), Izzet Control (6), UW Control (6) — 66% of the field, with the aggro/control split (8:3 by count, 54:21 by share) roughly matching the real 73:24. Two held out and never optimised against: Azorius Aggro (5) and Orzhov Aggro (4). Renormalise the eight shares to sum to 1 and use those as the `wᵢ` in the stratified estimator.

Why eight: fewer than six and the aggregate stops resembling the real field; more than ten and the per-matchup samples become useless at any affordable budget (Part 5 of the arithmetic). Eight is the point where each matchup still gets ≥8% of the games.

**PROPOSAL — overfitting defences.** Three distinct risks, three distinct defences:
1. *Overfitting to the archetype set.* Hold out two archetypes. Validate the final list against them with a fixed-*n* run and report the result alongside the training number. A large training/holdout gap is the signal that the loop has been fitting the gauntlet.
2. *Overfitting to the specific 75s.* Equally real and more often missed. Two different Boros Aggro lists from different events differ in ways that matter. **Pin two lists per training archetype, alternate between them, and hold a third back.** A change that only helps against one particular Boros build is noise dressed as signal.
3. *Overfitting to the weight vector.* Re-score the final candidate under 2–3 plausible weightings (as-measured, aggro-heavy, control-heavy). Prefer changes that are positive under all of them. This is cheap: it is a re-weighting of per-matchup results you already have, costing zero extra games.

**PROPOSAL — rotation and versioning (addressing the Standard decision).** A Standard gauntlet has a shelf life.
- Store each gauntlet as an immutable, dated directory: `gauntlets/2026-11-20/` containing one `.dck` per member plus a `manifest.json` recording, per deck: source URL, MTGTop8 deck id, event name and date, archetype label, metagame share at capture, and the file's sha256. Record the gauntlet's own hash as the sha256 of the sorted member hashes plus the weight vector.
- **Never mutate a gauntlet in place.** A new set release or a ban creates a *new* dated gauntlet, and the old results stay attached to the old hash.
- Refresh cadence: on each new set release (seven Magic sets in 2026, returning to six in 2027 per [Wizards' 2026 announcement](https://magic.wizards.com/en/news/announcements/everything-announced-for-magic-the-gathering-in-2026)), and immediately on any ban-list change. Standard uses a **three-year rotation window** since [Revitalizing Standard](https://magic.wizards.com/en/news/announcements/revitalizing-standard); multiple outlets report **no rotation in 2026, with the next one at the first set release of 2027** (CITED — secondary sources; verify against Wizards directly before relying on the date).
- **Results from before a gauntlet change are not comparable to results after it.** Enforce this mechanically: the harness refuses to compare two runs whose `gauntlet_hash` differs, and the record stores the hash on every row. After a refresh, the incumbent baseline must be re-measured from scratch before any candidate is screened.
- Forge's own `Standard.txt` is a second rotation signal: it lists the legal sets and bans for the installed build (currently 21 sets, 13 bans). Diffing it against Scryfall's `legalities.standard` after each Forge upgrade tells you whether the engine's idea of Standard matches reality.

**Verdict on pilot symmetry.** **Both sides must use the same AI profile.** Forge's sim mode supports `-a [profile] [profile]` per player, in deck order (VERIFIED in `SimulateMatch.java`, which validates each name against `AiProfileUtil.getProfilesDisplayList()`). Using different profiles introduces a pilot-skill difference that is mathematically indistinguishable from a deck-quality difference: the candidate's measured gain would be partly "my opponent is piloted worse", and the loop would happily optimise for that. Pass `-a Default Default` explicitly rather than relying on the default, so the profile is recorded in the command line and therefore in the experiment record.

**The bias that remains even with symmetric pilots, and it is serious.** Forge's `docs/AI.md` states plainly that the AI is "Best with Aggro and midrange decks / Poor to Ok in control decks / Pretty bad for most combo decks", and that it is "not trained" but heuristic. Consequences:
- The three control archetypes in the gauntlet (21% of the real field) will underperform their true strength. Your deck's measured win rate is therefore **inflated**, and any card whose value is specifically "beats control" is **under-rewarded**.
- Combo (Reanimator, 1%) is unmeasurable. Leave it out of the gauntlet rather than include a deck the engine cannot pilot.
- Worse, simulation mode runs a *weaker* AI than the desktop GUI: `-mc` (Flat Monte Carlo refinement) defaults to **off in simulations**, and the source comments that `max` is "the strength a desktop match gets automatically" (VERIFIED in `SimulateMatch.java`). So AI-vs-AI sim results are not even representative of playing Forge yourself.
- **PROPOSAL:** measure the `-mc off` versus `-mc max` cost in seconds per game early. If `-mc max` is less than ~3× slower, use it — a better pilot narrows the aggro bias at the cost of throughput, and that trade is probably worth making for the control matchups specifically. Record the flag in the experiment identity either way, because it changes the answer.
- State this bias in every report. The tool's output is "a 60-card list that performs well against this gauntlet as piloted by Forge's heuristic AI", and the honest translation to paper Magic is weaker for control-heavy fields than for aggro ones. For the owner's stated aggressive-deck objective, the bias is partly aligned and tolerable.

**Confidence.** High on the source reachability (tested), the metagame shares (parsed today), and the Forge pilot facts (read from source). Medium on the gauntlet size of eight, which is a judgement balancing realism against per-matchup resolution. Medium on the rotation dates, which come from secondary sources.

---

## Q4 — Statistics

**Verdict.** The arithmetic section above is the answer: ~19,600 games for 2 pp, ~8,700 for 3 pp, ~3,140 for 5 pp at 80% power; SPRT with [0, +4 pp] bounds cuts the typical cost to ~250–1,400 games per candidate; variance reduction from mirrored play/draw and a fixed gauntlet is substantial, from shared seeds modest (ρ ≈ 0.1–0.3), and the matchup spread makes the aggregate *slightly* cheaper rather than dearer. Practical budget: ~17,280 games/day → ~14 screened candidates/day → ~two weeks per deck.

### Engaging directly with the spike-eval author's objection

The author of spike-eval rejected win-counting as his evaluation method, on the grounds that Magic contains a great deal of luck and that decks beat each other in rock-paper-scissors fashion, so a win rate reflects the draw and the deck choice more than the player's skill; he cites Kaggle's Game Arena finding a model that topped the chess ranking losing money at poker, and he chose fixed puzzles instead, judged against three criteria: repeatability, model differentiation, and trustability. *(Content was rephrased for compliance with licensing restrictions.)*

**I agree with the distinction the notification draws, and here is the precise reason.** His estimand is *pilot skill*; deck identity is a nuisance factor whose effect size is large relative to the pilot effect, and — critically — in his original 8-model tournament it was **confounded** with the thing being measured, because different models sat behind different decks. A confounded nuisance factor with a bigger effect than your signal is fatal, and no sample size fixes it. The owner's estimand is *deck quality* with the pilot held fixed: Forge's AI, same profile, both seats. The nuisance factor the author complains about becomes a **blocking factor** — specified by the gauntlet, identical across both arms, and therefore removed from the comparison by design. Converting a confound into a block is the textbook fix, and it is what the owner's design already does.

Note that the author himself did not actually abandon win rates; he built a careful version of them. His `SCORING.md` mirror panel holds the deck constant on both sides of the table precisely so that "deck strength cancels and the Forge-AI mirror is 50% by symmetry", with seed-paired games in both seat orders and AI-vs-AI controls. That is the same move as the owner's fixed gauntlet, applied to the other nuisance factor. His *headline* metric is puzzles because a scalar benchmark score needs to be defensible to strangers; a private optimisation loop has a lower bar — it needs to be right on average, not unimpeachable.

**Where his objection still bites the owner, honestly.**

1. **Luck is not answered by changing the estimand; it is answered by sample size, and the owner can afford the sample size while the author could not.** At ~$0.09 and ~8 minutes per LLM-piloted game, 100 games per cell is already a large spend; at ~25 s and $0 per heuristic-AI game, 20,000 games is one day. That asymmetry — roughly 20× in time and unbounded in cost — is the entire reason the owner's premise survives an objection that correctly killed the author's. It is also a warning: **the moment the owner puts an LLM in the pilot's seat, his statistical power collapses by that factor and the project stops working.** The LLM must stay out of the loop that generates games.

2. **The rock-paper-scissors objection survives intact, and it is a definitional problem rather than a statistical one.** A single aggregate win rate is a *functional of the gauntlet weights*, not a property of the deck. Two candidate lists can swap ranking under a different-but-equally-plausible weight vector, and no number of games resolves that, because both answers are correct for their respective fields. Consequences the owner must accept:
   - "The best 60" is only defined relative to a stated, dated metagame. The weight vector is an input to the answer and must be versioned alongside the gauntlet.
   - The cancellation case the notification names is real: a card at +15 pp in two 10%-share matchups and −15 pp in two others nets ~0 in the aggregate. The aggregate is not *wrong* — against that field the card genuinely is neutral — but reporting only the aggregate throws away the information that matters. **PROPOSAL: treat high matchup-variance with near-zero aggregate as the signature of a sideboard card, not of a bad card.** That is a concrete, actionable rule that falls straight out of taking the objection seriously, and it connects directly to question 6.
   - Quantitatively (Part 5 above): resolving a 5 pp effect *within* a 4%-share matchup needs ~78,500 games, 4.5 days, for one candidate. At screening budget that matchup sees ~44 games, CI ±15 pp. So per-matchup reporting is mandatory for diagnosis and forbidden for decisions.
   - Therefore **report a matrix, not a number**: per-matchup win rate with its CI, plus the weighted aggregate with its CI, plus the aggregate recomputed under 2–3 alternative weight vectors. Three lines of output instead of one, and the third line is what stops the owner buying cards on the strength of a 44-game sample.

3. **Repeatability in the author's strict sense is achievable here but costs something.** With a pinned Forge jar, a pinned gauntlet, a fixed AI profile, a recorded `-c` timeout and a recorded seed, a run is reproducible to the extent Forge's global RNG allows — which is exactly, if and only if one game runs per JVM invocation. Batching games into one process is faster but makes game *k* depend on games 1…*k−1*. **PROPOSAL: batch for screening (throughput matters, exact reproduction does not), one-game-per-process for confirmation runs and for anything that gets written into the record as a result.**

### Sequential testing and multiplicity

- **SPRT per candidate**, bounds [0, +4 pp], α = β = 0.05, hard cap 4,000 games, cap-out = reject. Simulated operating characteristics in Part 2. This is the chess-engine discipline from Fishtest, simplified: the owner does not need GSPRT's nuisance-parameter machinery or the pentanomial model, because his baseline is measured rather than assumed and his outcomes are win/loss/draw rather than a five-way game-pair result. Adopt the pentanomial idea only in the form of **game pairs** (same opponent, same seed, mirrored play/draw) as the unit of sampling.
- **Draws are a real outcome and must be recorded, not discarded.** Forge marks a game that exceeds `-c` seconds as a draw ("Stopping slow match as draw", VERIFIED). This systematically penalises grindy configurations — a deck that wins long games may be scored as drawing them. **PROPOSAL: raise `-c` well above the 120 s default for Standard (try 300 s), record every configuration's draw rate as a first-class metric, and treat a rising draw rate as a measurement failure rather than a deck property.** If draws exceed a few percent, the clock is confounding the experiment.
- **Multiple comparisons.** Testing 8–10 candidates per round at α = 0.05 gives a ~35–40% chance of at least one false acceptance. Two defences, in order of importance:
  1. **The two-stage design is the real control.** Screen at [0, +4 pp], then require an accepted candidate to survive a confirmation run at 3 pp before it enters the list. A false positive in screening costs one confirmation run, not a wrong decklist. This is what Fishtest does and it is sufficient.
  2. If you want a formal rate, use **Benjamini–Hochberg FDR** across the round's candidates rather than Bonferroni. Bonferroni at k = 10 would triple the games needed per candidate for no benefit the second stage does not already provide; FDR is the right error concept for a screening stage whose false positives are cheap.
- **Do not peek outside the SPRT.** The whole point of a sequential test is that stopping is part of the design. Looking at a candidate's running win rate and stopping when it looks good is the peeking fallacy and will manufacture improvements out of noise. The harness should not expose a running win rate to the LLM mid-test.

**Confidence.** High on the sample-size formulas and the SPRT simulation (I computed both). Medium-high on the throughput, which rests on one cited 25 s/game figure for a different format on a different OS, and on an estimated per-worker memory footprint I could not measure. High on the structural argument about estimands. Medium on the ρ ≈ 0.1–0.3 seed-pairing figure, which is my reasoning from how Forge's global RNG works, not a measurement.

---

## Q5 — Fitness beyond win rate

**Verdict.** Record everything parseable from the game log, but promote exactly one metric to decision authority per run and keep the rest as diagnostics for the LLM. Encode "wins by turn 5" as the joint probability P(win ∧ winning turn ≤ 5), which is a single Bernoulli and therefore testable with the same machinery. Keep objectives separate rather than summing them: use a **lexicographic constraint** rather than a weighted scalar, and reserve the Pareto front for the one place it earns its keep — presenting the final trade-off to the owner.

**Evidence — what the log actually gives you.** VERIFIED: Forge's `GameLogEntryType` enum contains `GAME_OUTCOME, MATCH_RESULTS, SIDEBOARD, TURN, MULLIGAN, DAMAGE, LIFE, LAND, DISCARD, COMBAT, MANA, ZONE_CHANGE, STACK_RESOLVE, STACK_ADD, EFFECT_REPLACED, PHASE, INFORMATION, PLAYER_CONTROL, ANTE, DRAFT`, and `GameLogEntry.toString()` returns `type.getCaption() + ": " + message`. So every log line is prefixed with a human-readable type caption (`Turn: …`, `Mulligan: …`, `Damage: …`, `Sideboard: …`) and a regex parser keyed on the prefix is straightforward.

**Critical operational constraint.** `-q` (quiet) restricts output to `MATCH_RESULTS` only (VERIFIED in `simulateSingleMatch`). **You cannot have both quiet logs and fitness metrics.** The full log must be produced and parsed. At tens of KB per game and ~17,000 games/day that is hundreds of MB/day of log text. **PROPOSAL: stream-parse and discard.** The worker reads Forge's stdout line by line, extracts features into a row, and writes only the row. Keep full logs for a small random sample (say 0.5%) plus every game flagged anomalous (draw, exception, duration outlier) for debugging. Never store raw logs for the whole corpus.

**PROPOSAL — the metric set.**

| Metric | Source | Role | Why |
|---|---|---|---|
| Win / loss / draw | `Game Result:` line + `GAME_OUTCOME` | **Decision metric** (default) | The one thing the SPRT tests. |
| Winning turn | last `Turn:` entry before the outcome | **Decision metric** when the objective is speed | Combines with win into P(win by turn N). |
| Per-matchup win rate | opponent deck id + outcome | Diagnostic, feeds LLM | High variance at screening budget; always report with CI. |
| On the play vs on the draw | seat order, which the harness assigns | Control variable | Must be balanced by design, then reported as a split to confirm balance. |
| Mulligan count, per player | `Mulligan:` entries | Diagnostic | A rising mulligan rate is the signature of a bad mana base or too many situational cards. Cheap and highly interpretable. |
| Lands played by turn 3 / 4 | `Land:` entries | Diagnostic | Screw/flood proxy. |
| Mana screw / flood | derived: lands in play vs turn number, and lands drawn vs deck ratio | Diagnostic | Define explicitly and keep the definition fixed, e.g. screw = fewer than 3 lands in play on turn 4; flood = more than 6 lands in play with fewer than 2 cards in hand. Arbitrary but consistent beats clever and drifting. |
| Cards left in hand at game end | `ZONE_CHANGE` accounting, or final-state entries | Diagnostic | Distinguishes "flooded out" from "ran out of gas". |
| Cumulative damage dealt by turn N | `Damage:` / `Life:` entries | **Diagnostic, and the best early signal available** | A damage-by-turn curve differentiates candidate lists with far fewer games than win rate does, because it is a near-continuous measure rather than a Bernoulli. Use it to *rank* proposals cheaply before spending SPRT budget on them. |
| Game duration (ms) | `ended in %d ms` | Operational | Feeds the throughput model; outliers flag engine trouble. |
| Draw rate | outcome | **Health check** | See the clock warning in Q4. |
| Sideboard-game win rate (games 2 and 3) | `SIDEBOARD:` entries + per-game outcome within a match | Decision metric for sideboard work | Only meaningful once sideboarding is actually enabled — see Q6. |

**Turning "wins by turn 5" into a fitness function.** Three candidate encodings, and the choice matters:
1. `P(win ∧ turn ≤ 5)` — a single Bernoulli. **Recommended.** Testable with the existing machinery; at a base rate around 0.30 it needs slightly *fewer* games than a win-rate test for the same absolute effect (7,325 vs 8,721 at 3 pp / 80%, computed above). Unambiguous, and it punishes both losing and winning slowly, which is what the objective means.
2. `E[win] − λ·E[winning turn]` — a weighted scalar. **Reject.** The λ is unjustifiable, and the resulting number cannot be explained to the owner or compared across runs.
3. Win rate subject to a speed constraint: maximise `P(win)` subject to `P(win by turn 5 | win) ≥ θ`. **Recommended as the secondary form**, with θ set from the baseline list's measured value rather than chosen. This is the lexicographic version and it has a property the scalar lacks: a change that improves win rate while making the deck slower gets *flagged* rather than silently traded away.

**Multiple objectives: separate, with a Pareto front only at the end.** During the loop, one decision metric, declared before the run starts, with the others as constraints that raise a flag when violated. Combining objectives into one score during search means the loop can drift away from the owner's stated goal without anyone noticing. At the *end* of a run, present the Pareto front over (win rate, P(win by turn 5)) across the accepted-change history — typically a handful of non-dominated lists — and let the owner choose. This is the one place the MAP-Elites insight ([arXiv:1904.10656](https://arxiv.org/abs/1904.10656)) pays off without its evaluation cost: you get the archive for free as a by-product of the hill climb's history, rather than paying for quality-diversity search.

**Confidence.** High on the log contents and the `-q` constraint (read from source). High on the sample-size arithmetic for the speed metric. Medium on the specific screw/flood thresholds, which are conventions I am proposing, not findings. Medium-high on the claim that damage-by-turn curves are a cheaper discriminator than win rate — that follows from a continuous measure having lower relative variance than a Bernoulli, but the size of the gain depends on how tightly damage correlates with winning in this gauntlet, which is measurable in the first week.

---

## Q6 — Sideboard construction

**Verdict.** Harder than the main deck, and **currently blocked by a Forge default that must be changed first**. Simulation mode runs best-of-three with no sideboarding at all. Once enabled, Forge offers a usable but limited plan representation; the pragmatic trick is that because the gauntlet is fixed, the *harness* knows the matchup before the match starts and can therefore supply a per-matchup plan by generating one deck-file variant per matchup — no in-engine conditioning needed. Minimum viable version: optimise the sideboard against the three worst measured matchups only, three to five slots each, with a fixed plan per matchup, and test on sideboard-game win rate.

**Evidence — the blocking finding.** VERIFIED by reading `forge-game/src/main/java/forge/game/GameRules.java`:

```java
private int gamesPerMatch = 3;
private boolean AISideboardingEnabled = false;   // default
private boolean sideboardForAI = false;          // default
private int simTimeout = 120;
```

and `Match.java:253–255`:

```java
boolean canSideBoard = !isFirstGame && rules.getGameType().isSideboardingAllowed();
boolean sideboardForAIs = rules.getSideboardForAI() && ...
```

`SimulateMatch.simulate()` constructs `new GameRules(type)` and sets only `gamesPerMatch` (from `-m`) and `simTimeout` (from `-c`). It **never** calls `setAISideboardingEnabled(true)` or `setSideboardForAI(true)`. `PlayerControllerAi.sideboard()` returns `null` immediately if `!getAISideboardingEnabled()`. Therefore **`java -jar forge.jar sim -m 3 …` plays three games with the same 60 cards every time.** `GameType.Constructed` does have `canSideboard = true`, so the capability is present and merely unreached.

Fixing this needs a patch to `SimulateMatch` (a new flag, e.g. `-sb`, calling `rules.setAISideboardingEnabled(true)`) or an upstream contribution. That is a ~10-line change and it is a prerequisite for any sideboard work. Flag it as an early task, not a late one.

**Evidence — the plan representation Forge already has.** VERIFIED in `PlayerControllerAi.sideboard()`: the AI first looks for a predefined plan in deck metadata via `deck.getAiHint("SideboardingPlan")`, parsed as `;`-separated `Main Card -> Sideboard Card` pairs:

```java
String sideboardAiHint = deck.getAiHint("SideboardingPlan");
for (String element : sideboardAiHint.split(";")) {
    String[] cardPair = element.split("->");
    // match cardPair[0] in main, cardPair[1] in sideboard, by exact card name
```

and `Deck.java` stores hints as `HintType$value` joined by ` | `. So a deck file can carry `SideboardingPlan$Card A->Card X;Card B->Card Y`. The swap is strictly 1-for-1 by card name, repeated for as many copies as both sides have. When a defined plan exists it is applied deterministically (the per-card random skip is bypassed: `if (!definedSideboardPlan && MyRandom...nextInt(100) < sbChancePerCard) continue;`).

Three important limitations:
1. **The plan is global, not per-matchup.** Forge has no mechanism for "if the opponent is Dimir Control, do X". One plan per deck file.
2. **Strictly 1-for-1 by name.** You cannot express "bring in 2 of these and cut 1 of each of two others" except as separate pairs, and you cannot condition on game 1's result.
3. **The fallback is unusable for optimisation.** Without a defined plan, the heuristic path swaps cards matching on shared card type, same CMC and colour-subset, skipping lands and mana producers, with probabilistic per-card application governed by `SIDEBOARDING_CHANCE_ON_WIN` and `SIDEBOARDING_CHANCE_PER_CARD` AI properties. It is random enough to add variance without adding skill. **Always supply an explicit plan.**

There is also a third path: `sideboardsAgainstOpponentDeck()` uses a `SideboardAdvisor` that **reads the opponent's main deck from the previous game** — but it requires `getAIFlatMonteCarlo()` (i.e. `-mc on|max`) *and* `AISideboardingEnabled` *and* `!getSideboardForAI()`. It is a reasonable opponent-side behaviour for the gauntlet decks, since a real opponent does know what they played against. Do not use it for the deck under test, because it would conflate sideboard-plan quality with the advisor's quality.

**PROPOSAL — representation and testing.** The key realisation: **the gauntlet is fixed, so the matchup is known to the harness at launch time.** This dissolves limitation 1 without touching the engine.

- Represent a sideboard plan as harness-level data: `plans[archetype] = [(out_card, in_card, count), …]`, stored in the experiment record as JSON, with a global 15-card sideboard shared across plans.
- At launch, the harness writes a *derived* deck file for that matchup: same 60-card main, same 15-card sideboard, with `SideboardingPlan$…` set to the plan for that specific opponent. Eight gauntlet archetypes means eight derived files from one logical deck. Hash the logical deck (main + sideboard + all plans) as the deck identity, not the derived file.
- Test on **sideboard-game win rate** — games 2 and 3 only, isolated from game 1. Game 1 is unaffected by the sideboard and including it dilutes the signal by roughly a third.
- This makes the sideboard search two nested problems: *which 15 cards* (the slots) and *which plan per matchup* (how they come in). Search them in that order, because a card's value is conditional on the plan that brings it in — but note the budget consequence: each sideboard slot is only exercised in the matchups whose plan uses it, so its effective sample is a fraction of the run. A card used in two of eight matchups sees ~25% of sideboard games. **This is why the sideboard needs a narrower, deeper design than the main deck**, and why optimising all 15 slots simultaneously is not affordable.

**PROPOSAL — minimum viable version, in order.**
1. Patch `SimulateMatch` to enable AI sideboarding. Verify by grepping the match output for `Sideboard:` log entries (`Match.java` fires `GameEventAddLog(GameLogEntryType.SIDEBOARD, …)` when the AI sideboards by itself).
2. Run the main deck to convergence with an empty sideboard and Bo1 (`-n`, not `-m`). Sideboard work on an unconverged main deck is wasted.
3. Identify the three worst matchups from the diagnostic sweep.
4. For each, ask the LLM for 3–5 candidate cards and an explicit swap plan, validate legality, and test each *plan* (not each card) as a single candidate against that matchup's Bo3 win rate. One plan = one SPRT.
5. Take the union of winning cards; if it exceeds 15, test the overlaps by dropping the lowest-measured card and re-running the affected matchups.
6. Stop. A main deck with a tested sideboard against the three worst matchups is already far beyond what the owner would achieve by hand, and the remaining five matchups have the smallest shares and the weakest signal.

**Confidence.** High on the Forge findings — they are read directly from current master source, and the "no sideboarding in sim" result is the kind of thing that silently invalidates a month of work, so it is worth re-verifying empirically on the installed build before trusting my reading. Medium-high on the per-matchup derived-deck-file trick, which follows logically from the fixed gauntlet but I have not run it. Medium on the MVP ordering, which is a judgement call about where the budget is best spent.

---

## Q7 — How the LLM earns its keep

**Verdict.** The LLM is worth its scarce calls in exactly two places — proposing candidate cards from the objective and the card pool, and writing the per-matchup sideboard plan — and is worth a few calls in a third, naming the deck's failure mode from the diagnostic sweep. It is not worth calls for explaining results to the owner (cheap, but also the easiest place for it to invent a causal story), and it must never pilot a game or judge a comparison.

| Job | Is the LLM genuinely better? | Cheaper non-LLM alternative | Verdict |
|---|---|---|---|
| **Propose candidate cards from the objective and card pool** | **Yes, decisively, and nothing else comes close.** This is the Magic-knowledge-bound task: given "aggressive Boros deck that wins by turn 5" and 5,460 legal cards, name 10 that plausibly belong. No script has the semantic model of card text, format context and archetype convention needed. | Scryfall query templates (`t:creature mv<=2 c>=r pow>=2 legal:standard`) plus EDHREC/MTGTop8 co-occurrence frequency: "cards that appear alongside the cards already in my list". This is a *real* alternative and surprisingly good — it is how grimorio's suggestions work — but it can only propose cards other people already play together, so it cannot serve a novel objective. | **Spend calls here.** Use the cheap co-occurrence prior to generate a long list, then the LLM to select and justify 5–10. That order minimises tokens. |
| **Read match statistics and form hypotheses** | **Yes, with a caveat.** Turning "we lose 70% of games against Dimir Control, our mulligan rate is 18%, and we have 4.2 cards in hand when we lose" into "the deck is too slow against interaction and the 4-drops are the problem" is genuine synthesis over heterogeneous evidence. | Fixed rule templates: "if loss rate > 60% in matchup X and average game length > 10 turns, flag 'outgrinded'". These catch the common cases for free and should exist anyway as a pre-filter. | **Spend calls here, but on the diagnostic sweep only** (the equal-allocation run with decent per-matchup samples), never on screening noise. One call per diagnostic sweep, not one per candidate. |
| **Write the per-matchup sideboard plan** | **Yes.** "Against UW Control, cut 3 burn spells for 3 cards that beat a resolved wrath" is pure Magic reasoning, and the plan must be coherent as a *plan*, not a bag of cards. | Nothing credible. Forge's own heuristic (type/CMC/colour matching with probabilistic application) is explicitly a placeholder. | **Spend calls here.** Highest value per token in the whole loop, because one plan is tested as one unit. |
| **Name the deck's failure mode** | **Partly.** Valuable as a human-readable summary and genuinely useful for directing the next round's proposals. | The diagnostic metric set already names most failure modes numerically: high mulligan rate → mana base; high flood rate → too many lands or too few card-draw effects; losing with cards in hand → too expensive; losing with an empty hand → not enough card advantage. | **Fold into the hypothesis call.** Not a separate call. |
| **Explain results to the owner** | **No.** Cheap, tempting, and the place where an LLM will most readily attach a confident mechanism to a 44-game sample. | A templated report: the measured effect size, its CI, the per-matchup table, the games played, the stopping reason. | **Do not spend calls.** Write a template. If the owner wants prose, let him ask the LLM himself, with the numbers in front of him. |
| **Pilot the games** | **No, and this would kill the project.** | Forge's heuristic AI. | **Never.** ~8 min and ~$0.09 per game (spike-eval's measured figures) versus ~25 s and $0 destroys the sample size the whole method depends on — the exact trap that made win-rate evaluation unworkable for spike-eval. |
| **Judge whether a change helped** | **No.** | SPRT. | **Never.** Not even as a tie-breaker. |

**The hallucination problem, and how to shut it down.** An LLM will confidently propose cards that do not exist, are not Standard-legal, have rotated out, are banned, or whose text it misremembers. This is not a risk to be managed with better prompting; it is a certainty to be caught by a validator that runs before any game is played. Validation is cheap, deterministic and must be mandatory.

**PROPOSAL — the validation pipeline, with exact fields.**

1. **Existence and exact name.** [Scryfall API](https://scryfall.com/docs/api). Prefer the local bulk file over per-card calls: `GET https://api.scryfall.com/bulk-data` returns the catalogue of available dumps (VERIFIED today: types `oracle_cards`, `default_cards`, `all_cards`, `unique_artwork`, `rulings`, `art_tags`, `oracle_tags`, each with a `download_uri` and an `updated_at`; refreshed roughly daily — the entries I fetched were stamped `2026-11-19T22:0x`). Use **`oracle_cards`** — one object per Oracle id, which is what you want for a decklist, rather than one per printing. Note Scryfall is [migrating bulk files to JSONL, with the legacy JSON format retired after 2026-07-20](https://scryfall.com/blog/two-new-ways-to-sync-scryfall-data-236) in favour of `jsonl_download_uri` (CITED; the `download_uri` field was still present today, so handle both). Scryfall's terms prohibit paywalling its data and require you not to imply endorsement.
2. **Standard legality.** The field is **`legalities.standard`** on the card object, with values **`legal`, `not_legal`, `restricted`, `banned`** (VERIFIED against the live API: the `legalities` object carries 23 format keys including `standard`, `pauper`, `modern`, `pioneer`, `commander`, `standardbrawl`, `alchemy`, `timeless`, …). Accept only `legal`. This one field covers rotation *and* the ban list in one check, because Scryfall folds both into it. VERIFIED count today: **5,460 cards** match `legal:standard -is:digital`.
3. **Exclude digital-only cards.** `legalities.standard` can be `legal` for Alchemy-rebalanced or Arena-only cards that do not exist on paper — and the owner's entire motivation is not wasting money on paper cards. Filter with Scryfall's `is:digital` / the `digital` boolean and the `games` array (must contain `paper`).
4. **Cross-check against the engine.** Intersect with Forge's own `forge-gui/res/formats/Sanctioned/Standard.txt` (`Sets:` and `Banned:` lines) **and** with the installed build's card pool. A card that passes Scryfall but is absent from the installed Forge cannot be tested. Also exclude cards flagged `RemAIDecks`. Any proposal rejected here should be reported back to the LLM in the next prompt as "unavailable in the engine", so it stops proposing it.
5. **Oracle text is taken from the database, never from the model.** Build every prompt's card descriptions from the `oracle_text` and `mana_cost` fields of the bulk file. If the LLM's reasoning cites text that differs from the database, the proposal is rejected and the discrepancy logged — that log is a useful measure of how much the model is confabulating.
6. **Construction legality.** 4 copies max (basic lands exempt — Scryfall's `type_line` contains `Basic Land`, and Forge's own `DeckFormat.getMaxCardCopies` has the same carve-out); 60-card minimum main; sideboard exactly 15 (0–15 is legal, but a 15-card sideboard is the deliverable the owner asked for). Enforce in the harness, because simulation mode does not.

**MTGJSON as the alternative or cross-check.** [MTGJSON](https://mtgjson.com/) offers bulk downloads (`AllPrintings.json` and per-set files, documented at [All Files](https://mtgjson.com/downloads/all-files/)) with a [Legalities data model](https://mtgjson.com/data-models/legalities/) carrying the same per-format fields, plus `MTGSQLive` for a ready-made SQLite build. VERIFIED reachable (`https://mtgjson.com/api/v5/Meta.json` returns 200). Its legality is [computed per-printing, not per-card-name](https://github.com/mtgjson/mtgjson/issues/773), which is a subtle difference from Scryfall's Oracle-level view and a trap if you mix the two. **Recommendation: Scryfall `oracle_cards` as the single source of truth for legality and text; MTGJSON only if you want a SQLite card database without building one.** Using both invites exactly the inconsistency the validator exists to prevent.

Also noted: [Scrollrack.gg](https://scrollrack.topdeck.gg/docs/api) offers a REST decklist-validation API for MTG. Worth a look as a cross-check on the harness's own validator, but do not make a network call a dependency of the inner loop.

**Confidence.** High on the data sources and field names (tested live today). High on the division of labour, which follows from the throughput arithmetic rather than from taste. Medium on the claim that co-occurrence priors are a near-substitute for LLM proposals — plausible and cheap to test, but I have not measured it.

---

## Q8 — Versioning and reproducibility

**Verdict.** Git + SQLite + Markdown is the right answer; do not reach for an experiment-tracking platform. The thing that actually needs designing is not the storage but the **result identity**: the tuple of inputs that must all match before two results may be compared. Get that right and the storage is trivial; get it wrong and a tidy database full of incomparable numbers is worse than no database.

**PROPOSAL — the result identity.** A win rate is only comparable to another win rate when every one of these matches:

```
deck_hash          sha256 of (main cards sorted | sideboard sorted | sideboard plans)
gauntlet_hash      sha256 of (sorted member file hashes | weight vector)
forge_jar_sha256   the exact engine binary
forge_card_db      Forge's card-data version / release tag
ai_profile         per seat, e.g. "Default"
mc_flag            off | on | max
sim_timeout        the -c value
games_per_match    1 (Bo1) or 3 (Bo3)
sideboarding       enabled | disabled
harness_git_sha    the parsing and launching code
```

Store this tuple on every row. The harness must **refuse** to compute a comparison across differing tuples rather than producing a misleading number. This single rule is what makes a regression traceable: when a win rate moves unexpectedly, you diff the tuples first and the decklists second.

**PROPOSAL — layout.**

```
git repo (the narrative and the inputs — small, diffable, reviewable)
  decks/<deck-name>/v0001.dck … v0042.dck     one file per accepted version
  decks/<deck-name>/history.md                why each change was made, the measured
                                              effect size and CI, the stopping reason
  gauntlets/2026-11-20/*.dck + manifest.json  immutable, dated, never edited
  objectives/<deck-name>.yaml                 the stated objective, the decision metric,
                                              the constraint thresholds, the weight vector
  harness/                                    code

SQLite (the measurements — large, append-only)
  run      (run_id, started_at, <the full identity tuple>, cmdline, stop_reason)
  game     (run_id, game_idx, opponent_deck, seed, on_play, outcome, winning_turn,
            duration_ms, mulls_self, mulls_opp, lands_t4, cards_in_hand_end,
            dmg_by_t3, dmg_by_t5, is_draw, sideboard_game_idx)
  test     (test_id, candidate_deck_hash, baseline_deck_hash, bounds, alpha, beta,
            n_games, llr, decision, effect_estimate, ci_low, ci_high)
  proposal (proposal_id, round, llm_model, card_in, card_out, rationale,
            validation_result, test_id)

filesystem (sampled raw logs, gzipped, outside git)
  logs/<run_id>/<game_idx>.log.gz             0.5% sample + all anomalies
```

Rationale for each choice:
- **Decklists in git, not the database.** They are small, they are the artefact the owner actually wants, and `git diff v0041 v0042` is the single most useful command in the project. Use Forge's `.dck` format directly so there is no conversion step between what was tested and what is stored.
- **`history.md` per deck** is where the project earns its keep as a *tool*. Each entry: what changed, why the LLM proposed it, how many games, the measured effect with CI, and the decision. This is the document that tells the owner what to buy and why — which was the whole point.
- **SQLite for games.** At ~17,000 games/day a year is ~6M rows: trivial for SQLite. Use WAL mode, batch inserts in transactions of a few thousand, and index `(run_id)` and `(candidate_deck_hash)`. One file, backed up by copying it.
- **The `proposal` table matters more than it looks.** It lets you measure the LLM: what fraction of its proposals pass validation, what fraction pass screening, what fraction survive confirmation. That is the only way to know whether frontier calls are earning their keep, and it is the number that should decide whether to keep spending them.
- **Seeds recorded per game**, with the one-game-per-JVM caveat from Q4: a seed only reproduces a game exactly when that game had the process to itself. Record which mode was used.
- **No MLflow, no W&B.** They add a service to operate and solve a problem (comparing hundreds of hyperparameter runs with artefact lineage) the owner does not have. The one thing they would give him — a UI — is better served by a 50-line script that renders the per-matchup table from SQLite.

**What spike-eval already does here, worth copying.** Its scoring design pins decks by `sha256[:12]` and stamps the hash on every game line as `deck_sha`; maintains a `seed_registry.json` with reserved blocks so that evaluation seeds never leak into development; and defines a `benchmark_version` that determines "which reports may be pooled" — which is exactly the result-identity rule above, implemented. If the owner reads one file from the prior art before designing his record, it should be that one.

**Confidence.** High. This is a design recommendation rather than a finding, but the identity-tuple rule is forced by the Forge facts established earlier (engine version, AI profile, `-mc` flag and `-c` timeout all change the answer), so the reasoning is grounded even where the specific schema is taste.

---

## Recommended optimization loop

End to end. Steps 1–6 are one-time setup; 7–14 are the repeating loop; 15–17 close out a run.

1. **Pin the engine.** Install one Forge release, record its jar sha256 and card-data version, and never upgrade mid-run. Patch `SimulateMatch` to add a flag that calls `rules.setAISideboardingEnabled(true)` (needed from step 12 onward; harmless before). Keep the patch as a git-tracked diff against the pinned tag.
2. **Measure the two unknowns the budget rests on.** Run 200 AI-vs-AI games of two real Standard lists and record (a) median seconds per game at `-mc off` and at `-mc max`, (b) resident memory of one worker, (c) the draw rate at `-c 120` and at `-c 300`. Set the worker count from (b) and the clock from (c). Re-derive the throughput table from (a). Everything downstream is calibrated here, and if the numbers differ wildly from 25 s and ~1.2 GB, the plan changes rather than the plan being wrong.
3. **Build the card database.** Download Scryfall `oracle_cards`, filter to `legalities.standard == "legal"` and `games` containing `paper`, intersect with the installed Forge card pool and with Forge's `Standard.txt`, subtract `RemAIDecks` cards. This set — call it the *testable pool* — is the only thing the LLM may propose from.
4. **Build the gauntlet.** Scrape MTGTop8 `format?f=ST` for archetypes and shares, then `archetype?a=<id>` → `mtgo?d=<deckid>` for two lists per archetype. Take eight training archetypes, hold two out, hold a third list per archetype back. Convert to `.dck`, validate every list against the testable pool, and freeze the directory as `gauntlets/<date>/` with a manifest and a hash. Add TopDeck.gg as a second source if its free tier returns usable decklists.
5. **Write the objective file.** The stated goal in words, the decision metric (e.g. `P(win)` or `P(win ∧ turn ≤ 5)`), the constraint thresholds, the metagame weight vector, and the two alternative weight vectors for robustness checking. This file is an input, it is versioned, and it does not change during a run.
6. **Establish the harness invariants.** Same AI profile both seats, passed explicitly. Mirrored play/draw: every (candidate, opponent) cell plays equal numbers on the play and on the draw. Proportional allocation across the gauntlet during screening. One game per JVM for recorded results, batched for screening.
7. **Measure the incumbent baseline.** 8,000 games of the current list against the frozen gauntlet (SE ≈ 0.56 pp). Record under the full identity tuple. ~0.5 days.
8. **Diagnostic sweep.** An equal-allocation run — say 400 games per matchup, 3,200 total — producing per-matchup win rates with CIs plus the full diagnostic metric set (mulligans, lands by turn 4, damage curves, cards in hand at end, draw rate). ~0.2 days.
9. **Rule-template pre-analysis.** Run the fixed rules over the sweep output and emit the numeric failure-mode flags. Free.
10. **One LLM call: propose.** Give it the objective file, the current list, the diagnostic sweep with CIs, the flags, the testable pool filtered by a cheap co-occurrence prior, and the history of what has already been accepted and rejected. Ask for 5–10 specific edits, each as `(out_card, count) → (in_card, count)` with one sentence of reasoning. Nothing else from this call enters the record.
11. **Validate, then derive.** Reject proposals failing legality, availability or copy limits, and report the rejections back for the next round. For each surviving proposal, re-derive the mana base from Karsten's requirements; if infeasible at 24–26 lands, convert the proposal into an explicit "cut a colour or cut the spell" decision instead of silently fixing it.
12. **Screen.** One SPRT per candidate against the step-7 baseline: bounds [0, +4 pp], α = β = 0.05, cap 4,000 games, proportional allocation, mirrored play/draw. ~1,100 games each; ~14 fit in a day. Record every test's stopping reason, not just its decision.
13. **Confirm the winner.** Take the single best-measured accepted candidate (not all of them — serial acceptance keeps the record interpretable) and run a paired fixed-*n* confirmation at 3 pp / 80% power: 8,721 games. Re-score the result under the two alternative weight vectors; if the sign flips under a plausible weighting, record that and treat the change as metagame-contingent rather than an improvement.
14. **Accept and loop.** Commit the new `.dck` as the next version, append the entry to `history.md` with the effect size and CI, and return to step 7 — the baseline must be re-measured because the incumbent moved. Expect ~2 accepted changes per day; expect most rounds to accept nothing, which is the system working.
15. **Sideboard phase**, once the main deck has stopped improving. Enable sideboarding, switch to `-m 3`, identify the three worst matchups, and test whole *plans* per matchup via the derived-deck-file trick, scoring on games 2–3 only. Per the Q6 MVP.
16. **Validate on the holdout.** Run the final list against the two held-out archetypes and the held-back third lists, fixed-*n* at 5 pp. Report the training and holdout numbers side by side. A large gap means the loop fitted the gauntlet, and the honest response is to say so in the output rather than to re-tune.
17. **Deliver.** The 60-card main deck, the 15-card sideboard with per-matchup plans, the per-matchup win-rate matrix with CIs, the aggregate under three weight vectors, the training/holdout gap, the Pareto front over (win rate, speed) from the accepted-change history, and `history.md` as the explanation of every choice. Attach the standing caveat: measured against this dated gauntlet, piloted by Forge's heuristic AI, which plays aggro well and control poorly.

### The smallest experiment that would prove the loop works at all

Do not start with the search. Start with a **falsifiable measurement test** that can be done in under a day and that fails loudly if any part of the rig is broken.

**Setup.** Take one real Standard aggro list from MTGTop8. Make one deliberately crippled variant — the cleanest is **cutting the land count from 24 to 20** and adding four more spells, because the expected effect is large, the direction is certain, and no Magic judgement is involved in predicting it. Build a three-deck gauntlet (Boros Aggro, Dimir Control, Mono Green Aggro). Enable nothing fancy: Bo1, `-mc off`, same AI profile both seats, mirrored play/draw.

**Run.** SPRT the crippled variant against the healthy list, bounds [0, +4 pp], cap 4,000 games.

**Success criteria — all five must hold.**
1. **The test rejects the crippled variant**, with the correct sign, in fewer than ~1,500 games. If it does not, either the measurement is broken or the Forge AI is insensitive to mana-base quality — and the second possibility would be a project-stopping finding worth discovering on day one rather than in week three.
2. **Measured throughput is within 2× of the budget model.** Seconds per game and sustainable worker count match step 2's calibration under real parallel load.
3. **The parsed fitness fields are non-degenerate.** Winning turn, mulligan count and damage-by-turn-5 have plausible distributions and differ between the two lists in the expected direction (the 20-land version should show more mulligans and more games lost with spells stuck in hand). This proves the log parser, which is the component most likely to be silently wrong.
4. **The draw rate is under a few percent** at the chosen clock. If grindy games are being scored as draws, every subsequent result is confounded.
5. **A result is reproducible.** Re-run one recorded game, one-per-JVM with its recorded seed, and get the same outcome. This proves the identity tuple and the seed handling.

This costs well under a day, requires no LLM calls, no sideboard patch and no search algorithm, and it validates throughput, parsing, statistics, reproducibility and the engine's sensitivity to deck quality simultaneously. **If criterion 1 or 3 fails, nothing further in this report matters, and that is precisely why it should be the first thing built.**

---

## What I could not verify

- **Seconds per game for 2-player Standard on jarlaxle.** The 25 s figure is cited from commander-ai-lab for 4-player Commander on Windows. I did not install Forge (read-only investigation), so the central number in the throughput model is a transplant. Step 2 of the loop measures it.
- **Per-worker memory footprint.** The 1.0–1.5 GB/JVM estimate is inferred from grimorio's "~4 GB free RAM for games" guidance. The worker count, and therefore the daily budget, depends on it entirely.
- **MTGGoldfish reachability.** `curl` returned HTTP 000 from this box and the fetch tool timed out. I do not know whether this is a local network restriction, a bot block, or something else. Test from jarlaxle.
- **TopDeck.gg's free-tier decklist detail.** The API docs advertise a free key and a Standard format filter, and their decklist/metagame *product* is a paid subscription after 14 days. I did not create a key, so I do not know whether full decklists come through the free API tier.
- **The 2027 Standard rotation date.** Multiple secondary sources agree there is no 2026 rotation and the next falls at the first 2027 set release; I did not find the primary Wizards announcement stating it in those terms. Verify before building a refresh schedule around it.
- **Whether Forge's AI is actually sensitive to mana-base quality** at the magnitude the search needs. This is the deepest unverified assumption in the whole design — if a heuristic AI plays a 20-land deck nearly as well as a 24-land deck, the measurement has no signal regardless of how good the statistics are. It is criterion 1 of the smallest experiment for exactly that reason.
- **Correlation ρ achievable from shared seeds.** My 0.1–0.3 range is reasoning from Forge's single global `MyRandom` stream, not a measurement. Measurable by running the same candidate twice with matched and unmatched seeds.
- **Grimorio's internals beyond its README.** I read its documentation and repository metadata, not its source. The claim that its Forge runner is reusable is an inference from its documented architecture (Python server, Forge 2.0.15 in Docker, SQLite) and should be checked before depending on it. Its GPL-3.0 licence is verified.
- **Completeness of the prior-art search.** I searched in English, for the terms the brief named plus several variants. An academic Forge-based deck-optimisation paper could exist under terminology I did not try.

---

## Separating fact from proposal from speculation

**Verified fact** (I ran the command or read the source): jarlaxle's specs; Forge's `sim` flags including the undocumented `-s` seed, `-a` AI profile and `-mc` Monte Carlo switch; `AISideboardingEnabled` and `sideboardForAI` both defaulting to false and never being set by `SimulateMatch`; the `SideboardingPlan$` AI-hint format and its 1-for-1-by-name semantics; `GameLogEntryType`'s members and the `"Caption: message"` log format; `-q` suppressing everything but match results; `DeckFormat.Constructed`'s 60/0–15/4 limits and the absence of any conformance check in sim mode; Forge's `Standard.txt` set and ban lists; the games running single-threaded in-process; Scryfall's `legalities.standard` field, its four values and the 5,460-card count; Scryfall's bulk-data types; MTGJSON's reachability; Moxfield's 403; MTGTop8's reachability, archetype shares and plain-text decklist endpoint; MTGGoldfish's unreachability from this box; MTGODecklistCache's shutdown; grimorio's licence, activity and "10+ games" guidance; spike-eval's scoring design; the SPRT operating characteristics (simulated); all the sample-size arithmetic.

**Cited** (from a named source, not independently checked): the ~0.04 Forge sims/sec figure; spike-eval's ~8 min and ~$0.09 per LLM game; the Turing-completeness and arithmetic-hardness results; the Hearthstone MAP-Elites and active-genes results; Fishtest's pentanomial/GSPRT/normalised-Elo design; Karsten's colour-source thresholds; Standard's three-year rotation window and the 2026/2027 schedule; the spike-eval author's objection to win-counting.

**Design proposal** (mine, labelled as such throughout): the eight-archetype gauntlet with two holdouts and three overfitting defences; proportional allocation for screening and equal allocation for diagnostics; the frozen-baseline one-sample SPRT with a 4,000-game cap; the two-stage screen-then-confirm multiplicity control; the metric set and the screw/flood definitions; `P(win ∧ turn ≤ 5)` as the speed objective and the lexicographic constraint form; the per-matchup derived-deck-file sideboard trick and the three-worst-matchups MVP; the LLM job allocation and the six-step validation pipeline; the result-identity tuple and the git+SQLite+Markdown layout; the 17-step loop; the smallest experiment.

**Speculation** (flagged, and I would not act on it without measuring): that damage-by-turn curves discriminate candidates more cheaply than win rate; that a surrogate model trained on the accumulated corpus could later pre-rank proposals; that cheap co-occurrence priors approach LLM proposal quality; that `-mc max` is worth its throughput cost for the control matchups; the ~15% proposal accept rate underlying the two-week run-length estimate.
