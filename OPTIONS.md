# deckAI — three ways to build it

Written 2026-11-20 from five parallel research investigations. The full reports are in
[`.agents/tasks/`](.agents/tasks/) and every number below traces to one of them.

**The goal, as stated:** give the tool a starting decklist and an objective, have it play
that list against a fixed gauntlet of meta decks, iterate on card choices, and hand back a
heavily tested 60-card main deck and 15-card sideboard — so you don't buy paper cards that
turn out not to work. Format: Standard. Engine: Forge. Harness: Python.

---

## What the research settled before the options begin

Five findings constrain every option, so they are stated once here rather than repeated three
times.

**1. The LLM must not play the games.** A CLI coding agent as the in-game pilot fails on quota
by roughly 100× and on latency by roughly 40×. ChatGPT Plus is documented at 15–160 GPT-6.1 Sol
messages per 5-hour window; one decision is one message; a Standard game has ~300 decisions.
That is 2.56 games/day, so **1,000 games takes 391 days**. Measured latency from your own local
Codex rollouts is 9.0 s median per turn (n=42) with a warm cache, and a cold `codex exec` sends
22,150 uncached input tokens before the model speaks. This is not an engineering problem with a
workaround; it is arithmetic.

**2. The LLM is excellent at the job that remains.** [AutoTavern (arXiv 2610.33845)](https://arxiv.org/abs/2610.33845)
measured LLM agents building a card-game simulator and training a policy: the built policy
answered 91% of play tasks against at most 63% for frontier LLMs, deciding in 0.03 s versus up
to 26 s. LLM agents build far better than they play. Here, "building" means proposing which
cards to try — and that is not a nice-to-have. There are **5,460 Standard-legal cards** (Scryfall,
verified) and over 10^100 legal 60-card lists; the measurement loop affords roughly **5,000
evaluations per year**. No search algorithm extracts signal from 5,000 samples of a 10^100 space.
The LLM is the only available prior that makes the search possible at all.

**3. Forge already ships the pilot and the batch runner.**
`java -jar forge.jar sim -d deckA deckB -n 100 -s 42 -q` runs headless AI-vs-AI games, seeds the
shuffle, loops best-of-M, and prints per-game elapsed milliseconds. No Java required to start.
`-m M` gives matches, `-t Bracket|RoundRobin|Swiss` gives tournaments, `-a profileA profileB`
sets a different AI per seat. Forge's own docs omit `-s`, `-a` and `-mc`; those came from
`argumentHelp()` in the source.

**4. Four Forge defaults will silently corrupt your results if you don't handle them.**

| Default | Consequence | Fix cost |
|---|---|---|
| Unscripted cards are **stripped from your deck**, not rejected — `Match.java` builds the library from `getValid().getLeft()` and merely *reveals* the remainder | A 60-card list with 3 unimplemented cards becomes a **57-card library and the game proceeds** | ~20 lines in the harness: parse the reveal, refuse to score the run |
| `sim` never calls `getDeckConformanceProblem()` | An illegal list (wrong size, 5 copies, banned card) plays happily | Harness validates against Forge's own `res/formats/Sanctioned/Standard.txt` |
| `AISideboardingEnabled` and `sideboardForAI` both default **false**, and `SimulateMatch` never sets them | **No sideboarding happens at all** — your 15-card sideboard goal is unreachable | ~10-line patch |
| `-mc` (Flat Monte Carlo AI refinement) defaults **off** in simulations because it's a GUI-only preference | `sim` runs a materially *weaker* AI than the desktop game | One flag, but it costs seconds per game |

A fifth is structural rather than a default: **one seed covers an entire run**, so you cannot
pair A/B samples by seed. Paired shuffles are the main variance-reduction tool available, so this
one is worth real effort.

**5. Forge's AI is the measuring instrument, and it has a known bias.** Its own documentation:
the AI "is *not* 'trained'", is "Best with Aggro and midrange decks, Poor to Ok in control decks,
Pretty bad for most combo decks", and "its limitations exist even against itself." The predictable
failure mode of this entire project is therefore specific and must be printed on every report it
produces: **it over-rewards aggressive, low-decision-density cards and under-rewards control,
combo, and anything with a subtle activated ability.** For an aggro objective this is tolerable.
For a control or combo deck it is disqualifying.

### The budget, worked out

Assumption to be measured on day one: **25 s per game** (the only published figure, from
commander-ai-lab, for 4-player Commander on Windows — a transplant, and Forge prints the real
number for free so the model self-corrects). RAM, not cores, is the constraint: each game is
single-threaded inside a JVM holding the full card database, so parallelism means processes, at
~1.0–1.5 GB each.

```
17,280 games/day   at 25 s/game × 5 workers
   ├─ screen one candidate   ~1,100 games (SPRT, bounds [0,+4pp])  →  ~14 candidates/day
   ├─ confirm a winner        8,721 games (paired, 3pp @ 80% power) →  ~2/day
   └─ validate final list     3,140 games (5pp @ 80% power)
```

Sample sizes for a two-proportion test at 80% power: **3,140** games per arm for a 5 pp effect,
**8,721** for 3 pp, **19,622** for 2 pp. So the honest capability statement is:

> **The tool can resolve 4–5 percentage-point decisions. It cannot resolve 1–2 point
> decisions — the 3rd versus 4th copy, or one burn spell versus a similar one — in any
> practical time.**

Coarse decisions are exactly what you asked for (land count, removal count, card-draw count,
which cards), so the project is viable as specified. It would not be viable as a fine-tuner.

**Per-matchup numbers are diagnostic, never decision-grade.** Under proportional allocation a
gauntlet deck with 4% metagame share receives 44 games out of a 1,100-game screen: standard error
7.5 pp, 95% CI ±15 pp. Resolving a 5 pp change *within* that matchup would need 78,500 games —
4.5 days for one candidate. Per-matchup win rates tell the LLM where to look; the weighted
aggregate makes decisions. Any report showing a per-matchup number without its confidence
interval is how this project produces a confidently wrong decklist.

**Your hardware is the throughput ceiling, and it is cheap to lift.** jarlaxle has 7 GB total
with ~4 GB already consumed by something, leaving ~2 GB — that is **2 workers, not 5**, with 10
of 12 cores idle. **+16 GB of RAM is the highest-leverage purchase in this project**, worth more
than any GPU, model or subscription tier. Finding out what's eating the 4 GB is free and comes first.

### Prior art you should read before writing code

| Project | What it gives you |
|---|---|
| [grimorio](https://github.com/hubertdungen/grimorio) (GPL-3.0) | Closest to your goal: Forge-in-Docker AI-vs-AI runner, Bo1/Bo3, per-card draw/cast/stuck-in-hand event recording, deck importers, Scryfall pipeline, SQLite. **No hypothesis test** — its README suggests "10+ games per deck", which has a ±16 pp standard error. Reuse the plumbing, build the statistics yourself. |
| [spike-eval](https://github.com/lumlaolao/spike-eval) (GPL-3.0) + [write-up](https://folds.ink/posts/mtg-benchmark) | The measurement discipline, already worked out: mirror panels so deck strength cancels by symmetry, seed-paired comparisons across both seat orders, AI-vs-AI controls, decks pinned by `sha256[:12]`, held-out seed banks, null sanity arms, and a benchmark version controlling which results may be pooled. Also a working seeded Forge path and an SPRT implementation. |
| [manabrew](https://github.com/witchesofthehill/manabrew) (AGPL-3.0) | The only project here with *verified* determinism: `CountingRandom(seed)`, `ReplayRandom`, a decision journal, a cross-process replay test, and a real legal-action API (`ActionSpace.getPossibleActions`) over JSON-RPC. Wrong shape for batching whole games; read it before building your own seeding. |
| [Deep Surrogate Assisted MAP-Elites](https://arxiv.org/html/2112.03534v4) | The methodological answer to "evaluations are too expensive": train a surrogate on your own accumulated results to pre-rank candidates. Phase-2 idea — it needs thousands of labelled decklists, which the loop generates as a by-product. |

**Statistical decklist optimisation on top of Forge does not exist.** Engines and LLM-play
harnesses are abundant as of late 2026; the measurement layer is the missing piece. The academic
Forge-based genetic-algorithm work I went looking for turned out to be [a forum thread where the
idea was raised and never built](https://slightlymagic.net/forum/viewtopic.php?f=52&t=18164) —
and that thread names the two real problems: crossover between differently-coloured decks produces
a broken mana base, and the search converges on cards that beat *the Forge AI* rather than cards
that are good.

---

## Option 1 — Thin harness over stock `sim`

Python spawns the shipped Forge release, parses stdout, and runs the statistics. No Java is
written and no engine patch is applied. The LLM proposes card swaps offline between runs through
your existing CLI subscription.

```
Python harness ── spawns ──> java -jar forge.jar sim -d cand gaunt_01 -n 200 -s 42 -q
     │                                    │
     │  legality + strip guard            └──> stdout: per-game result + elapsed ms
     │  SPRT screen vs frozen baseline         │
     │  JSONL results + SQLite                 ▼
     └──> kiro-cli / codex (offline, ~10 calls per round): propose 5-10 edits
```

**Delivers:** a 60-card main deck where every accepted change has a measured effect size and a
confidence interval, plus a written history explaining each choice.

**Up**
- Running gauntlet in **days, not weeks**. Nothing to build but the harness.
- Arm's-length from Forge's GPL-3.0: you spawn a binary, you don't link it. Your code stays yours.
- No GPU, no local model, no API key, no account risk. Marginal cost per game is zero.
- Pins to a released Forge tarball — no build toolchain on jarlaxle, which currently has no node,
  no docker and no git.
- Easy to abandon. If the acceptance test fails you've lost a week, not a quarter.

**Down**
- **No sideboard.** Sideboarding is off by default and unreachable without the patch, so you get a
  60, not a 75. For a tool whose output is a buy list, that's a significant hole.
- **No paired seeds**, so you pay full variance: every effect size costs more games than it should.
- Stdout parsing is brittle and will break on a Forge upgrade. Mitigated by pinning, which means
  you don't get new sets without re-testing the parser.
- Runs the weaker `-mc off` AI, widening the gap between measured and real-world performance.
- Resolves 4–5 pp at best, and with jarlaxle's current 2 GB free, roughly 7,000 games/day rather
  than 17,000 — so ~6 candidates/day.

**Good if:** you want to know within a week whether this whole idea measures anything real.

---

## Option 2 — Patched Forge plus a proper experiment layer

Option 1, plus a small git-tracked patch set against a pinned Forge tag, plus the measurement
discipline borrowed from spike-eval. **This is the recommended build.**

The patch set, in rising order of effort: write results as JSONL instead of text; call
`setAISideboardingEnabled(true)` behind a flag; accept a per-game seed so A/B samples pair;
expose `-mc` per run. The first two are roughly ten lines each.

```
Objective file ──> LLM proposes 5-10 edits ──> deterministic filter
(versioned, fixed)         (1 call/round)      (legality, Forge pool, RemAIDecks,
                                                Karsten mana base re-derived free)
                                    │
                                    ▼
                    SPRT screen, paired seeds, mirrored play/draw
                    proportional allocation over a frozen gauntlet
                                    │
                    ┌───────────────┴───────────────┐
                 reject                          accept
            (report back as                   confirm at 3pp,
             context next round)               8,721 paired games
                                                      │
                                              sideboard phase (Bo3)
                                                      │
                                           held-out archetype validation
```

**Delivers:** a 60-card main deck *and* a 15-card sideboard with per-matchup plans, a per-matchup
win-rate matrix with confidence intervals, the aggregate scored under three different metagame
weightings, a training-versus-holdout gap, and a Pareto front over (win rate, speed).

**Up**
- **The sideboard becomes reachable** — the one thing standing between a 60 and the 75 you actually
  wanted is a ten-line patch.
- **Paired seeds cut the variance**, which converts directly into more candidates screened per day
  at the same hardware.
- Three safeguards against the Forge-AI bias, built in from the start rather than bolted on:
  vary the AI profile with `-a` so results aren't one bot's taste; score the gauntlet spread rather
  than any single matchup; hold out archetypes so you can measure whether you overfitted.
- **The mana base is derived, never searched.** Karsten's colour-source tables give you a
  closed-form answer at zero games; only genuine infeasibility at 24–26 lands becomes a real
  decision worth testing. This alone saves thousands of games.
- Honest output. Every number carries a CI, the metagame weighting is a versioned input rather
  than a hidden assumption, and sign-flips under alternative weightings are reported as
  metagame-contingent rather than as improvements.

**Down**
- **Patching Forge makes your harness a GPL-3.0 derivative** the moment you compile against it
  (spike-eval states exactly this about itself). Fine for a personal tool; decide now if you ever
  want to close it.
- Needs a Java build toolchain and a maintained patch rebased on each Forge upgrade — real
  ongoing maintenance, and Standard rotates, so you will upgrade.
- Two to four weeks before the first trustworthy 75, versus days for Option 1.
- **Sideboard testing is intrinsically expensive**: Bo3 roughly triples game cost, and a sideboard
  card is only as good as the plan that brings it in, so you're testing plans, not cards.
- Still measures Forge-AI-piloted performance. The patch improves rigour, not the pilot.

**Good if:** you want the tool you actually described, and accept two weeks and a GPL obligation
to get it.

---

## Option 3 — Option 2 plus a pilot-quality track

Everything in Option 2, plus work on the *instrument itself*: a `PlayerControllerAi` subclass that
lets a better decider take over specific decisions, used on a small audited sample to quantify how
much Forge's AI is distorting your results — and later a learned policy trained on your own logs.

```
Layer 3  Frontier LLM (offline) ── proposes cards, reads reports. Never plays.
Layer 0  Forge built-in AI ─────── pilots 100% of bulk gauntlet games. Free.
Layer 1  Deterministic auto-resolve ── only in audited games.
Layer 2  Kev-0.8B on the laptop ───── audited 1-5% of games, as a second opinion.
            │
            └──> counterfactual replay from decision points → labelled misplays
                 → feature-based policy net (sub-millisecond, CPU-only, runs on jarlaxle)
```

Note what changed from your original plan: **there is no local Jev and there never has been.**
It is hosted, closed-weight, proprietary, with no download and no announced plan for one, verified
across five sources. Your instinct about the *category* was right — an Apache-2.0 open family doing
the same job exists (**Kev** 0.8B/4B/9B/27B, plus Decision 2.0, Clef, Nimble, CLM-8B) — but only
**Kev-0.8B** (~1.8 GB) fits your 6 GB 4050. Kev-4B needs ~9.3 GB bf16 and no validated 4-bit quant
is published.

**Up**
- **The only option that can tell you how wrong the measurement is.** Everything else takes
  Forge's AI on faith; this quantifies the bias instead of caveating it.
- The only path to trusting the tool on **control or combo** decks, where Forge's own authors say
  its AI is poor to bad. If you ever want to brew anything but aggro, this is the work.
- The learned policy net is the genuinely attractive endgame: sub-millisecond, CPU-friendly, trains
  on logs the gauntlet produces for free, and could eventually run on jarlaxle with no GPU at all.
- Optional Endstep adapter falls out of the same controller interface, if you ever want to watch it
  play a human. Endstep turned out to be technically easy — the server enumerates legal actions as
  `pendingAction.cardOptions[].playableAbilities[{index, description, cost}]`, so no rules
  reimplementation is needed.

**Down**
- **The decider cannot go in the bulk gauntlet.** Kev-0.8B measured 798 ms for a 2,417-token state
  on a GTX 1650; call it 350–550 ms on your 4050, which is 1–2 minutes of decider time *per game*
  on top of the game — **20–30 hours per thousand games**, against seconds for free. Audited
  subsets only.
- **Quality is unproven at depth.** On an independent 1,800-item benchmark, hosted Jev beats Kev-9B
  by 25.3 points overall and by **39.8 points at depth 5**. A Standard priority pass with a stack
  and a combat trick is not a depth-0 question. The small local model may simply not be good enough
  to be a useful second opinion, and you won't know until you measure.
- **Splits the system across two machines** — Forge on jarlaxle, decider on the laptop — so
  "unattended" now means "unattended while the laptop is awake".
- **A ToS line you must not cross.** OpenAI's Usage Policies, effective 2026-11-20, prohibit using
  model outputs to supply training material or signals for other models, explicitly including
  labels, scores, rankings, preferences, rewards and corrections, and explicitly "even if you do not
  train the resulting model". So **never train the decider on agent play.** Train it on game
  outcomes and counterfactual replays. This costs nothing, because the recommended design has no
  agent in the loop anyway — but it does kill the "harvest Codex's decisions as training data" idea.
- Months of work, and the payoff is better *measurement*, not a better decklist. Everything here is
  an optimisation of a loop that must first exist and must first be trustworthy.

**Good if:** this is a research platform you want to keep extending, not just a tool that outputs
a buy list.

---

## Recommendation

**Build Option 2, and ship Option 1 as its first milestone.** They are the same codebase; Option 1
is Option 2 before the patch set lands. That ordering gets a trustworthy measurement within a week
and a complete 75 within a month, with no wasted work in between.

**Treat Option 3 as a separate decision, made later, with data in hand.** Its value depends
entirely on a number you don't have yet: how much Forge's AI distorts your results. Option 2's
held-out validation and AI-profile variation will estimate that for free. If the distortion is
small, Option 3 is a hobby; if it's large, Option 3 is the project.

### Three things to do before any option starts

1. **Find out what is eating 4 of jarlaxle's 7 GB**, and add 16 GB if you can. This single number
   sets your games-per-day, and therefore how many card decisions the tool can make per week.
2. **Measure the two unknowns the whole budget rests on**: seconds per game and resident memory per
   worker, from 200 real AI-vs-AI games. Forge prints the per-game milliseconds itself, so this is
   nearly free. Every throughput figure in this document is an estimate until this replaces it.
3. **Run the known-answer acceptance test, and let it have a veto.** Take one real Standard aggro
   list, make one deliberately crippled variant by cutting lands from 24 to 20, and SPRT the
   variant against the healthy list. All five criteria must hold: the test rejects the crippled
   list with the right sign in under ~1,500 games; throughput is within 2× of the model; the parsed
   fitness fields (winning turn, mulligans, damage by turn 5) are non-degenerate and move in the
   expected direction; the draw rate at the chosen clock is a few percent at most; and a recorded
   game replays to the same result from its seed.

   If the land-count test shows **no difference**, the rig is broken or Forge's AI is insensitive
   to mana-base quality — and the second possibility would stop the project, which is exactly why
   it should be discovered on day one. A **wrong sign** means the pilot is biased in a way that
   inverts results, and nothing should be built until that is understood.

   This costs under a day, needs no LLM calls, no patch and no search algorithm, and it validates
   throughput, parsing, statistics, reproducibility and the engine's sensitivity to deck quality
   all at once. It is worth more than every model-selection decision in this document.

### Open decisions for you

- **GPL-3.0**: patching Forge makes this project GPL-3.0. Acceptable, or should it stay at
  arm's length?
- **Gauntlet source**: `MTGODecklistCache`, the standard machine-readable decklist feed, **shut
  itself down in 2025** (scrapers broke, repo archived). The fallback is scraping MTGTop8 for
  archetypes and shares. Do you want the tool to pull its own gauntlet, or will you hand it the
  decks you care about?
- **Objective metric**: "wins by turn 5" needs to become something measurable, e.g.
  `P(win ∧ turn ≤ 5)`, with a metagame weight vector as an explicit versioned input. What exactly
  should the tool be maximising?
- **How much RAM** can jarlaxle get? This is the difference between ~6 and ~15 card decisions per day.

---

## Next step in the OpenSpec workflow

OpenSpec 2.1.1 is installed and initialized (Kiro + Codex skills, project scope). This document is
the output of the explore phase. Once you pick an option, the next command is
`/openspec-propose` — it will create `openspec/changes/<name>/` with a proposal, delta specs, a
design and a task list to review before any code is written.
