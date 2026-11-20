# Local decider for an MTG deck-brewing agent — findings

Read-only research. No code was written, no models downloaded, nothing installed.
Repo `/home/aiden/Projects/deckAI` is empty apart from OpenSpec scaffolding
(`openspec/config.yaml`, empty `specs/` and `changes/archive/`), so there are no
in-repo symbols to cite. Every citation below is external.

Scope as corrected by the owner mid-investigation:

- Objective is a **deck-brewing tool**, not a strong MTG player. An agent takes a
  decklist plus an objective, plays it against a fixed gauntlet, iterates card
  choices, and emits a tested 60 + 15 before money is spent on paper.
- Format is **Standard**, not Pauper.
- Environment is **local Forge-vs-Forge**.
- The decider must run **locally on the dev laptop** (16 GB RAM, RTX 4050 6 GB VRAM).
  Not on the homelab box, not as a hosted API.
- Homelab `jarlaxle`: Ubuntu 24.04, 12 cores, 8 GB RAM (~2 GB free), **no GPU**,
  297 GB free disk. Java present; node, npm, uv, docker, ollama absent.

## Summary

1. **There is no local Jev and there never has been.** Jev is TypeSafe AI's hosted,
   closed-weight System One model — proprietary licence, served from TypeSafe's
   machines, no download, no on-premises build, no announced plan for either
   ([Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)),
   [modemguides reality check](https://www.modemguides.com/blogs/ai-news/jev-typesafe-reality-check-run-locally)).
   The owner's belief that "local System One models are very small" is right about
   the *category* and wrong about *Jev*: an Apache-2.0 open family doing the same job
   exists — **Kev** (0.8B/4B/9B/27B), **Decision 2.0** (0.6B–27B), **Clef**,
   **Nimble**, **CLM-8B** — and `Kev-0.8B` is the only member validated to fit a 4 GB
   GPU at ~1.8 GB of weights, so it comfortably fits the 4050.

2. **The measured evidence says a small local decision model is the wrong tool for
   consequential Standard decisions, and an adequate tool for shallow ones.** On an
   independent 1,800-item benchmark scored by inference depth, hosted Jev beats
   Kev-9B by **+25.3 points overall** (95% CI +23.0 to +27.8); the gap is +8.3 at
   depth 0 and **+39.8 at depth 5**
   ([paoValle eval](https://github.com/paoValle/system-one-decision-models), citing
   hard-decisions.anth.us). A Standard priority pass with a stack, a combat trick and
   a land-untapped decision is not a depth-0 question. Use the small local model where
   the decision is shallow and high-volume; do not expect it to find lines.

3. **The real cost wall is not dollars, it is seconds per game, and it rules out a
   neural decider in the bulk gauntlet.** Measured: Kev-0.8B takes **798 ms** for a
   2,417-token state on a GTX 1650 4 GB (same repo, §4.5). A 4050 is maybe 1.5–2.5×
   that card, so call it ~350–550 ms per decision at realistic Standard board size. At
   ~150–250 decisions per game that is **1–2 minutes of decider time per game, on top
   of the game**. A 1,000-game gauntlet becomes a day or more of laptop GPU time; a
   10,000-game one becomes a week. Forge's own AI plays the same game for free in
   seconds. For a measuring instrument that must run thousands of games, that
   comparison is decisive.

4. **The pilot for bulk gauntlet games should be Forge's own built-in AI, and Forge's
   maintainers say so for exactly our archetype.** Forge's AI doc states plainly that
   the AI is not trained, is heuristic, and is **best with aggro and midrange decks**,
   poor-to-ok in control, bad in most combo
   ([forge/docs/AI.md](https://github.com/Card-Forge/forge/blob/master/docs/AI.md)).
   It also ships a headless `sim` mode (`java -jar forge.jar sim -d deck1 deck2 -n 3
   -q`) built for exactly this: bashing out hundreds of games on a machine with no
   display. That is zero marginal cost, consistent across thousands of games, and
   therefore low-bias and low-variance in the way a measuring instrument needs — which
   matters more here than raw strength.

5. **Spend the frontier model on building, not on playing — this is now a measured
   result, not a hunch.** AutoTavern (arXiv
   [2610.33845](https://arxiv.org/abs/2610.33845), Oct 2026) had LLM research agents
   build a Hearthstone Battlegrounds simulator and train a policy; the built policy
   answers **91%** of play tasks against at most **63%** for frontier LLMs, and decides
   in **0.03 s** where the LLMs need up to 26 s. Their one-line conclusion is that LLM
   agents build far better than they play. Mapped onto this project: the frontier model
   picks cards, reads match reports and forms hypotheses; a cheap fixed policy plays
   the games.

### The one thing to do first

Before any decider work, prove the measuring instrument. Build the seeded
Forge-vs-Forge gauntlet and run a **known-answer A/B**: two lists differing only by a
swap whose direction nobody disputes (4 Lightning Bolt vs 4 Shock, or 24 lands vs 20
lands). If the harness plus Forge AI recovers the known-better list, with the right
sign and roughly the expected effect size, the instrument works and everything
downstream is worth building. If it does not, no decider can save it. Cost: a day of
work, zero dollars, no GPU. Details in
[Recommended decision pipeline](#recommended-decision-pipeline).

---

## Hardware reality (replaces the VRAM tier table)

The owner asked for this to replace the 8/12/16/24/48 GB tier table, which no longer
applies since no GPU purchase is assumed.

| Box | Spec | What it can host | Verdict |
|---|---|---|---|
| `jarlaxle` | Ubuntu 24.04, 12 cores, 8 GB RAM (~2 GB free), **no GPU**, 297 GB disk, Java present | Forge JVMs running the gauntlet. Nothing neural worth having. | **Game runner.** This is its job and it is well suited to it. |
| Dev laptop | RTX 4050 6 GB, 16 GB RAM, 20 cores, ollama present | `Kev-0.8B` (~1.8 GB bf16) or `Decision-2.0-Kai-0.6B`/`Eos-0.8B`; a 4B-class generative model at Q4; QLoRA fine-tuning of a 0.8B decision head | **Decider and training box**, for audited subsets only. |

**Blunt answer on CPU-only inference on jarlaxle: nothing useful.** Three
independent reasons, in order of how fatal they are.

1. **RAM.** ~2 GB free is below the working set of any serving stack worth running.
   The measured llama.cpp comparison on an arm64 CPU shows Qwen3-1.7B at Q8_0 using
   **7.0 GiB** resident while serving (vLLM in BF16 used 11.4 GiB)
   ([jacar.es benchmark](https://jacar.es/en/vllm-cpu-arm64-vs-llama-cpp-benchmark/)).
   You can cut that a long way with a smaller model, Q4 and a tiny context, but you
   are then fighting Forge for the same scarce pages, and Forge is the thing that
   actually earns its keep on this box.
2. **Prefill, not generation.** A decider's cost is dominated by encoding the board
   state once per decision, not by emitting tokens. Published CPU throughput figures
   (72.7 tok/s for Qwen3-1.7B Q8_0 single-stream on arm64; ~26 tok/s for an 8B-class
   model on a 16-core Ryzen 9 7950X,
   [markaicode](https://markaicode.com/benchmarks/llamacpp-tokens-per-second-benchmark/);
   ~2 tok/s for 4B on very constrained hardware,
   [llama.cpp discussion #21136](https://github.com/ggml-org/llama.cpp/discussions/21136))
   are generation numbers. A multi-thousand-token Standard board state has to go
   through the model every single decision. On CPU that is seconds per decision,
   hundreds of seconds per game.
3. **Opportunity cost.** Those 12 cores are the single most valuable resource in the
   whole project, because they run parallel Forge games — the thing that produces the
   data. Spending them on a weak local model trades the asset for the liability.

**What jarlaxle should run:** parallel headless Forge `sim` processes, and nothing
else. *Unverified and worth measuring on day one:* Forge's resident memory per JVM and
its games-per-hour for a Standard matchup. I found no published figure for either.
With ~2 GB free you may only fit one or two JVMs today; find out where the other 6 GB
is going before planning a parallel gauntlet. 297 GB of disk is ample for game logs.

**What the laptop should run:** the decision model, the fine-tuning, and the audited
game subsets. Note the cross-request caching caveat below — it changes the design.

---

## Decider options compared

Strength ratings are for *Standard in-game decisions* specifically. Build cost assumes
one person. "Compute cost" is per decision in the bulk gauntlet.

| Option | Strength | Build cost | Compute cost | Verdict |
|---|---|---|---|---|
| **Forge built-in AI** (heuristic, in-engine) | Moderate; vendor states it is best at aggro/midrange | **None** — already there, `sim` mode is documented | **~0** (it is the engine) | **The pilot.** Consistent, free, aggro-friendly. Non-negotiable default for bulk games. |
| **Hand-written heuristics layered over Forge AI** | Moderate+, on the specific spots you encode | Low per rule, but unbounded in total | ~0 | **Yes, narrowly.** Only for spots you can measure as broken, and only behind a flag. |
| **Deterministic auto-resolve layer** (forced/only-legal-action) | n/a — removes decisions rather than making them | Low; the rule set is published (see Q1) | ~0 | **Yes, mandatory** — but it buys less in Standard than in Pauper burn. |
| **Local Kev-0.8B / Decision-2.0-Eos-0.8B** (typed-decision, Apache-2.0) | Weak on depth ≥ 1; adequate on depth-0 | Low — `kev.serve` one command, TypeSafe-compatible wire format | ~350–550 ms/decision on a 4050 (inferred from 798 ms on a GTX 1650) | **Audit subsets only.** Too slow for the bulk gauntlet. |
| **Local Kev-4B** | Noticeably better (within 1–2 pts of Jev on easy classification) | Low to run, but **does not fit 6 GB**: ~9.3 GB bf16 weights, 15.9 GB peak on the adapter load path | n/a locally | **No**, unless someone ships a validated 4-bit quant. Not documented today. |
| **Hosted Jev** | Strongest typed decider measured; +25 pts over Kev-9B on depth | Trivial (OpenRouter key) | ~$0.00014/decision; ~70–500 ms + network | **Ruled out by the owner** (must be local). Keep as the ceiling reference for offline audits. |
| **CLM-8B** (contrastive dual-encoder, cached action embeddings) | 95.2% BFCL vs Jev 99.2%; not calibrated | Medium | ~5 GB at Q4 — above 4 GB, borderline on 6 GB | **The interesting one, but risky.** See the action-cache analysis in Q3. |
| **ISMCTS / PIMCTS over the Forge engine** | Potentially the strongest non-LLM option | **High** — needs a cloneable, fast-forwardable game state Forge does not expose | High (hundreds of rollouts per decision) | **No** for a solo builder on this timeline. |
| **Small learned policy/value net on hand-engineered features** | Unknown, plausibly good; trains on your own gauntlet logs | Medium — feature engineering is the work | **Sub-millisecond**, CPU-friendly | **The sleeper pick.** Best long-term fit; only viable *after* the gauntlet produces logs. |
| **Frontier LLM per priority pass** | Strongest play, by a distance | Low (spike-eval already exists) | **~$0.09 and ~18 min per game** (measured) | **No** for the gauntlet. Yes for deck design and match-report reading. |

Two entries carry most of the recommendation: **Forge AI** as the pilot, and the
**learned policy net** as the thing the project can grow into because the gauntlet
generates its own training data for free.

---
## Jev, answered head-on

The owner asked for a dedicated section. Every question below is answered with a
source, and the one answer that matters most is the first.

### Is it hosted-only, or can it run locally?

**Hosted only. The weights are not available, at any size, under any licence.**

- Wikipedia records the licence as **Proprietary** and the developer as TypeSafe AI,
  released 15 September 2026, stable `jev-1.13.0`
  ([Jev (AI model)](https://en.wikipedia.org/wiki/Jev_(AI_model))).
- The same article states TypeSafe has published no architecture, no weights and no
  technical paper, describing the model only as transformer-based, and that outside
  observers have guessed at an open-weight LLM or a BERT-like backbone underneath.
- A vendor-adjacent FAQ site puts it bluntly: Jev is called over an API and the model
  runs on TypeSafe's servers; the open part is the surrounding tooling
  ([jevtypesafeai.com](https://jevtypesafeai.com/)).
- An independent review in November 2026 found no download, no on-premises build and
  no published plan for either
  ([modemguides](https://www.modemguides.com/blogs/ai-news/jev-typesafe-reality-check-run-locally)).
- A third-party project repeats the same finding from the integrator's side: cloud API
  only, no public weights or implementation details
  ([APUS-AI-Lab/fast-browser-use](https://github.com/APUS-AI-Lab/fast-browser-use)).
- The controlled academic study of the category says the same in its related-work
  section: Jev's architecture, weights and training data are unpublished and it is
  available only through an API (arXiv
  [2611.15592](https://arxiv.org/html/2611.15592), §2.1).

**No "mini", distilled, on-device or self-hostable variant exists.** I searched for one
specifically. What exists instead is a thicket of third-party reimplementations with
names like `openjev`, `local-jev`, `jev_local` and `mini-jev`, which take the *pattern*
(mask the answer-token logits, one forward pass, softmax over the options) and apply it
to an open model you supply. Those are not Jev. One of them is explicit that it ships
random weights and reproduces none of TypeSafe's training
([kyegomez/open-jev](https://github.com/kyegomez/open-jev)).

**Conclusion: the hosted Jev API is out as the production decider, as the owner
decided. That is the correct call on the facts.** It survives in this project only as
an offline reference oracle — see Q6.

### Actual pricing per call

Published list price is **$0.042 per million input tokens with output free**
(vendor figure, repeated by
[firecrawl](https://www.firecrawl.dev/blog/what-is-jev),
[datacamp](https://www.datacamp.com/blog/system-one-models-jev?), OpenRouter).
Every response carries a `usage.cost` field in USD
([OpenRouter Jev guide](https://openrouter.ai/docs/guides/community/jev)).

Two measured anchors, both more useful than the list price:

- The independent benchmark paper ran **346,009 requests for under US$10** — about
  **$0.000029 per request** on short classification states (arXiv
  [2609.37647](https://arxiv.org/abs/2609.37647)).
- Jev adds a **fixed ~257 input tokens to every request**, most likely its internal
  prompt. The same one-line request billed 280 tokens on Jev against 23 on Kev — up to
  a 12× gap on short requests, shrinking to ~1.3× on long multi-question ones
  (Opper A/B, via [paoValle](https://github.com/paoValle/system-one-decision-models) §4.2).

**Inferred cost for this project, flagged as my arithmetic, not a measurement:** a
Standard board state with full card text is realistically 2,000–6,000 tokens. At 3,000
tokens plus Jev's 257, one decision costs ~$0.00014. At ~200 decisions per Standard
game that is **~$0.028 per game**, so ~$28 per thousand games and ~$280 per ten
thousand. Cheap in absolute terms, and ~3× cheaper than the measured $0.09 per game for
a frontier model in spike-eval — **not 400× cheaper**, because the board state dominates
the bill and you pay for it either way. The headline multipliers do not survive contact
with a large state.

### Latency

Vendor claims **70–500 ms** end-to-end and 40–200× faster than frontier LLMs. The
community column of the reality-check table tells a different story: across 333
reported figures the **median latency was 76 ms**, and across 215 speed-up figures the
**median was 7×** (quartiles 2–20×), against a 193.6× homepage claim
([jev-usecases reality check](https://github.com/vamsikrishna2421/jev-usecases) §6).
Independent evaluators agree closely on p50 latency (236–276 ms in one wave). So:
latency is genuinely good; the speed-up multiplier is inflated by choosing a long
reasoning call as the baseline. The honest comparison is against the shortest reliable
call your own system could already make.

### Does it need few-shot examples or fine-tuning?

**No, and it cannot be fine-tuned by you.** Jev does zero-shot classification over
categories supplied at inference time — Wikipedia notes it does not require
data-specific training, unlike classical discriminative models. It is trained
exclusively on synthetic data by an unpublished method the company calls Reinforcement
Learning for Calibrated Decisions (RLCD). There is no customer fine-tuning path,
because there are no weights. You tune **the question wording and the confidence
thresholds**, nothing else.

This is a real limitation for our use case and it cuts the other way for Kev: Kev *can*
be fine-tuned on logged decisions, which is exactly what a deck-brewing harness
accumulates. See Q4.

### What the independent benchmark says versus the vendor

The owner's cited paper is *Evaluating and Benchmarking the System One Model Jev*
(arXiv [2609.37647](https://arxiv.org/abs/2609.37647), v2 Oct 2026, Deußer et al.).
It evaluated `jev-1.13.0` zero-shot on **37 datasets** with one frozen template each
and full evaluation splits, and scored Qwen3.8-27B and Gemma-4-E4B on identical
requests via their exact option probabilities.

What it found in Jev's favour:

- 95–99% accuracy on IMDB, SST-2, HellaSwag and ARC.
- Beats Qwen on **27 of 37** datasets, with none of Qwen's leads outside the bootstrap
  intervals; beats Gemma on all 37.
- Choice probabilities are well calibrated and support selective prediction.

What it found against Jev, and this is the part that matters for MTG:

- All three models degrade on low-resource languages, fine-grained or noisy labels, and
  rubric judgments.
- Binary probabilities need **tuned thresholds** — micro-F1 on UNFAIR-ToS went from
  0.50 to 0.75 once thresholds were tuned. Out-of-the-box probabilities are not
  decision-ready.
- **On sequential decisions, where the model picks the next action at every step** —
  the exact shape of an MTG priority pass — Jev completes **35%** of ALFWorld unseen
  tasks, **42%** of 90 TextWorld games, **21%** of BabyAI-Text missions. It picks the
  optimal Blackjack action **90%** of the time and on FrozenLake rarely walks away from
  the goal.
- **"It often repeats actions that had no effect."**
- **Qwen3.8-27B completes more ALFWorld (54.5%) and TextWorld (51.1%) than Jev**, while
  sharing its failures on BabyAI-Text and FrozenLake.

Read that paragraph twice. The independent evidence is that a typed-decision model is
excellent at *classifying a state* and mediocre at *driving a sequential policy*, and
an ordinary open 27B generative model outperforms it on the two richest sequential
benchmarks. The repeated-no-effect-action failure is precisely the pathology that
destroys an MTG agent: a priority window that gets the same answer forever.

The community reality check adds three more cautions, all with numbers:

- **"Cannot hallucinate" is a schema guarantee, not a correctness guarantee.** Jev
  cannot emit an invalid value; it can absolutely return a schema-valid wrong answer.
  The vendor's 0% structured-output-error figure is asserted by construction, not
  measured.
- **The vendor's 67.8% accuracy figure is agreement with two frontier LLMs at high
  thinking effort, not accuracy against ground truth** — and the workflows were written
  by TypeSafe's own model-capabilities team, which the company's own technical notes
  concede may bias the result.
- **Calibration is contested.** Four independent Banking77 evaluations of the same model
  disagree by **10.7 points** (87.0 / 83.2 / 77.8 / 76.3), and the two most rigorous
  entries are the two lowest. In one frozen-protocol field Jev's expected calibration
  error was the **worst in the field at 0.246**, against 0.039–0.122 for the LLMs, and
  it declined forced-uncertainty items only **49.7%** of the time against 97.3–100% for
  the LLMs. In the same wave, a supervised 2023-era encoder (bge-small plus logistic
  regression on 10,003 training examples) scored **93.3%**, beating both Jev (83.2%) and
  GPT-5.6 Terra (87.5%).

That last number is the single most actionable finding in the whole investigation:
**if you have labelled data, fit a classifier first.** Decision models earn their place
on zero-shot tasks and on latency. A deck-brewing gauntlet manufactures labelled data
by the tens of thousands of rows. See Q3(d) and Q4.

### Does "pick one of N enumerated legal MTG actions from a serialized board state" fit?

**The request shape fits perfectly. The task difficulty does not.**

The shape is an exact match. Jev's `choice` primitive takes an unordered option set and
returns a probability per option plus a confidence, and the state can be a JSON object
with questions referring to its attributes. Options are developer-supplied at inference
time, so "here are the 14 legal actions, pick one" is a native request. You get type
safety for free: the model cannot name an action that is not on the list, which removes
the whole illegal-move failure class.

Four things break it in practice:

1. **Depth.** The independent sequential-decision results above (35% ALFWorld, 21%
   BabyAI-Text, repeated null actions) and the proof-depth table in Q2 both say the
   same thing: typed deciders collapse once a decision needs chained inference. Standard
   decisions chain constantly — hold the removal for the better target, represent the
   trick, sequence the land drop around a counterspell.
2. **No dependency between questions.** Jev answers every question in a request in
   parallel and in isolation against the same state; the type system forbids one
   question depending on another's answer, so a dependent chain needs sequential
   requests ([Wikipedia](https://en.wikipedia.org/wiki/Jev_(AI_model)),
   [LangChain](https://www.langchain.com/blog/building-a-harness-with-jev)). You cannot
   express "if I'm casting the burn spell, then which target" in one call.
3. **No rationale.** Jev returns probabilities and nothing else — no reasoning, no
   explanation. For a *brewing* tool whose output is advice to a human about card
   choices, the absence of a rationale is a product problem, not just an engineering
   one. You would need a second generative call to explain any decision you want to
   show the owner.
4. **State size kills the economics.** The pricing analysis above: the 400× multiplier
   evaporates when the state is a full Standard board.

**Verdict on Jev: a first-class option on request shape, a second-class option on task
difficulty, and ruled out entirely on the local-only constraint.** Its correct role in
this project is as an **offline reference oracle** for the misplay audit in Q6, where
accuracy matters, volume is small, and a hosted call is acceptable because it never
touches the production loop.

### Confidence

**High** on the hosted-only finding, the licence, the pricing mechanics and the
independent sequential-decision results — multiple independent sources, one
peer-reviewed-venue paper, one Wikipedia article with primary citations, and the
vendor's own documentation all agree. **Medium** on my per-game cost arithmetic, which
depends on a board-state token count nobody has published for Standard. **Medium** on
the calibration criticism, which rests on a survey of public reports plus a handful of
small independent fields rather than one large controlled study.

---
## Q1 — The triage pattern: trivial versus consequential

### Verdict

Do not invent the rule set. A working MTG harness has already published a precise,
battle-tested list of what may be auto-resolved, derived from real failures, and you
should adopt it nearly verbatim. But in **Standard** the auto-resolvable fraction is
materially lower than in Mono-Red Pauper, and I can give you the mechanism for why
rather than a guess at the number.

### Evidence

`spike-eval` is a harness that seats a language model in Forge and scores it, GPL-3.0,
with a 169 KB architecture document that records each rule and the bug that motivated it
([repo](https://github.com/lumlaolao/spike-eval),
[ARCHITECTURE.md](https://raw.githubusercontent.com/lumlaolao/spike-eval/main/docs/harness/ARCHITECTURE.md)).
Its section headed *What the harness may decide without asking (owner rule)* lists
exactly four auto-resolve classes:

1. **A choice with exactly one legal option (forced).** Plus the degenerate cost case:
   when a cost takes exactly as many cards as there are candidates, the harness pays it
   rather than asking. Their note on why is instructive — left to Forge's AI, the pick
   could be *refused*, and the payment then fails.
2. **The priority menu is PASS only** — nothing castable, activatable or playable — **or
   this exact spot was already passed**, where "spot" is the tuple (turn, phase, stack,
   board, menu). That second clause is the valuable one and it is not obvious.
3. **A play that already failed in this window is not offered again.** Failed to pay,
   forbidden by a static effect, or refused by the stack for want of a target, keyed on
   (turn, phase, top of stack). Their recorded failure: the seat was offered the same
   unpayable play **999 times**.
4. **A declined optional search followed by the engine's "Cancel Search?" prompt**, where
   a NO re-asks the same pick in a loop. Their recorded failure: a Green Sun's Zenith
   loop of **61 asks with no outcome**.

Plus one explicit exception, which shows the care required: a window whose only option
is floating mana that changes nothing passes unasked — a land's `{T}` ability into a
pool that empties without burn, with no trigger on tap or on mana added. Floating that
*does* change the game (a creature tapped and unable to block, Manabarbs, Upwelling's
pool, mana burn) is a real play and is still asked.

Everything else asks: an opponent's spell or ability, every attack and block, every
trigger, every new option. Their stated reason is the one that matters for *us*:
skipping a window the model could act in, or picking its play for it, is a heuristic
standing in for the model — and therefore a source of measurement bias.

**The negative result nobody advertises.** That same project **retired its cheap fast
tier**. The mulligan heuristic, the skip heuristics and the cheap fast model tier all
survive only as opt-in measurement switches (`MULLIGAN_HEURISTIC=1`,
`SKIP_HEURISTICS=1`, `ONE_TIER=0`), with one tier as the default. A team that built the
two-model triage the owner is proposing, in this exact game, on this exact engine, moved
away from it. That is the strongest single piece of evidence in this report against a
naive small-model/large-model split, and it should be taken seriously rather than
explained away. The reason given is measurement integrity: a cheap tier answering a
window silently substitutes its judgement for the thing you are trying to measure.

### Concrete deterministic rules for an aggressive deck

Adapting the above, plus Forge-specific mechanics. These are safe because each is either
forced by the rules or provably outcome-neutral:

- **Forced**: exactly one legal option; a cost whose candidate count equals its required
  count; a mandatory trigger with one legal target.
- **Empty priority**: PASS-only menus; a repeat of an already-passed (turn, phase, stack,
  board, menu) tuple.
- **Known-failed plays**: suppress for the window, keyed on the stack top.
- **Outcome-neutral mana**: tap a land for mana when the pool empties without burn and
  nothing triggers on tapping or on mana added. Note that for an aggro deck this is the
  single highest-frequency auto-resolve, and it is *almost* always safe — the exception
  list above is the cost of getting it right.
- **Untapped-land bookkeeping**: for a deck with no instants and no activated abilities
  in hand, holding mana open is never correct, so land taps can be auto-sequenced. In
  Standard this condition fires far less often than in Pauper burn, because Standard
  red decks run instant-speed interaction.
- **Attack-with-everything**: *do not* auto-resolve this, even for aggro. It is the
  decision most likely to be the thing a card change actually affects, and auto-resolving
  it bakes a heuristic into your measuring instrument. spike-eval's `greedy:` baseline
  attacks with everything, and they classify it as a *floor*, not a policy.

### What fraction is trivial?

**I will not give you a single number, because nobody has published one and a made-up
figure would be worse than none.** What I can give is the mechanism and a defensible
range.

The honest reasoning: auto-resolve rules 2 and 3 above (PASS-only menus and
already-passed spots) fire on the overwhelming majority of *windows*, because MTG grants
priority constantly — after every spell, every trigger, in every step of every turn, to
both players. The large majority of those windows are ones where you hold nothing
castable. So **as a fraction of priority windows, the trivial share is very high, plausibly
80–95%.** As a fraction of *decisions that could change the game*, it is much
lower — these rules by construction only remove windows where no choice existed.

The one measured anchor I have: a spike-eval game logged **153 model calls**
(ARCHITECTURE.md, routing-latency note, seed 86 of 2026-10-15) *after* all auto-resolve
rules had run. So ~150 genuine decisions per game survive triage in their setup, on
archetype decks. That is the number to budget against, not the window count.

**Standard raises this, and here is why.** Three mechanisms, each independent:

1. **Instant-speed density.** Standard red decks run instant-speed removal and tricks;
   Pauper burn is closer to a sequence of sorceries at your own main phase. Every instant
   in hand converts a PASS-only window into a real decision, and converts the opponent's
   whole turn from auto-pass into a sequence of hold-or-use judgements.
2. **Longer games.** Stronger decks on both sides mean more turns, and decisions scale
   with turns roughly linearly.
3. **Card complexity.** A larger, newer card pool means more modal spells, more
   activated abilities, more triggered-ability ordering, each of which is a decision
   the engine must ask about.

So: **the deterministic layer is still mandatory — it is what makes the loop
terminate** — but the owner should expect it to remove a smaller share of
*consequential* decisions in Standard than the Pauper framing suggested, and should
plan the budget around ~150–300 surviving decisions per game.

### Confidence

**High** that the published rule set is correct and adoptable, and that the fast-tier
retirement is a real recorded decision — it is in a maintained architecture document
that the project's standards require to be updated in the same PR as any behaviour
change. **High** on the direction of the Standard effect. **Low** on any specific
percentage; this is the clearest gap in the evidence and the cheapest thing to measure
yourself (instrument the harness, count auto rows against model rows, for one game).

---
## Q2 — Local small-model deciders that fit 6 GB

### Verdict

The right model class is not a chatty instruct LLM with constrained decoding. It is a
**typed-decision model**: an open-weight Jev-equivalent that reads a state plus an
enumerated option list and returns a probability per option in one forward pass, with no
text generation at all. Several exist under Apache-2.0, and `Kev-0.8B` is the member
validated to run on a 4 GB GPU. Pick that, with `Decision-2.0-Eos-0.8B` as the
alternate.

### Evidence: the open typed-decision family

A controlled academic study of this exact category — *Small Heads, Strong Decisions*
(arXiv [2611.15592](https://arxiv.org/html/2611.15592)) — re-implemented five readout
architectures under one backbone, one 15-source training mix, one recipe and one seed.
Its findings reshape the model-selection question:

- **Head complexity does not matter.** On Qwen3-0.6B every readout landed in
  **81.3–82.0%** in-domain accuracy. A **0.5M-parameter cosine head** (cosine similarity
  between the pooled question and each pooled option, with a learned temperature) matched
  Cloudflare Clef's **27M-parameter** joint schema head in-domain at half the inference
  time, and cost 6.9 GPU-hours to train against 8.7–17.8 for the alternatives.
- **One joint prompt per state beats one prompt per question**: same accuracy, 1.6×
  faster inference, 2.1–2.5× faster training. Directly relevant — ask all your questions
  about one board state in a single request.
- **The backbone dominates everything.** Qwen3-0.6B → Qwen3-4B adds **4 points
  in-domain and 11 points held-out**. Qwen3-8B reaches 85.8% / 89.8% and Qwen3-14B
  86.6% / 90.8% (one epoch).
- **Base, instruct and thinking checkpoints tie** (within 0.25 points in-domain at every
  size 0.6B–14B). Do not pay for a reasoning variant.
- **Embedding and reranker checkpoints bring no gain** in-domain and trail by up to 2.1
  points held-out. This is a direct, measured negative for one of the owner's
  hypotheses: Qwen3-Embedding and Qwen3-Reranker as backbones are *not* better for this.
- Inference cost of the cosine head: **6.4 ms per state** (H100, their harness).

The paper's recommendation is one line: spend effort on the backbone and keep the head
minimal. It also notes one public leaderboard already lists about **150** open Jev-like
models.

Named open models, with licences verified from the paper's reference notes and HF:

| Model | Sizes | Licence | Notes |
|---|---|---|---|
| **Kev** ([jaredpalmer/kev](https://github.com/jaredpalmer/kev)) | 0.8B / 4B / 9B / 27B | **Apache-2.0** (Qwen bases also Apache-2.0) | Qwen3.5/3.8 base + rank-16 LoRA + pointer head; 27B is a full fine-tune. **TypeSafe SDK drop-in** — same wire format. Fine-tunable. |
| **Decision 2.0** ([vllm-sr collection](https://huggingface.co/collections/vllm-sr/decision-20)) | Kai-0.6B, Eos-0.8B, Sol-2B, Nox-4B, Lux-9B, Vega-27B | Apache-2.0 | From the vLLM Semantic Router project. Tagged zero-shot-classification on HF. |
| **Decision 3.0** ([vllm-sr/d3](https://huggingface.co/vllm-sr/d3)) | incl. a `d3-edge` variant | Apache-2.0 | Learned letter readout. |
| **Clef** ([Cloudflare/clef](https://huggingface.co/Cloudflare/clef)) | — | Apache-2.0 (head) | Joint schema head, 27.3M params; training recipe vendored in Unsloth. Training data private. |
| **Nimble** ([bespokelabs/Bespoke-Nimble-9B](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B)) | 9B | Apache-2.0 | LoRA adapter on Qwen3.5-9B; frozen LM-head rows as the readout (zero new params). |
| **CLM-8B** (Stanford Scaling Intelligence / Hazy Research + NVIDIA) | 8B (35B-A3B announced) | Apache-2.0 | Contrastive dual-encoder, frozen Qwen3-8B + trained projection heads, **per-action embedding cache**. |

### Evidence: what actually fits and how fast it is

These are measured numbers from someone running the models on consumer hardware, not
vendor figures ([paoValle/system-one-decision-models](https://github.com/paoValle/system-one-decision-models),
CC-BY-4.0, §4.5 and §5; rig was a GTX 1650 4 GB / i7-9750H / 16 GB RAM):

| Scenario | Kev-0.8B median |
|---|---|
| Short state ~100 tok, 3 questions | **187 ms** (186–188) |
| Document 2,417 tok, 3 questions | **798 ms** (765–859) |
| Document 7,310 tok, 1 question | **1,036 ms** |
| Same state, new question (KV reuse) | 407 → 296 ms, only **1.4×** on CUDA |
| 8 concurrent clients × 8 requests | **4.9 req/s**, median 1,620 ms |

Footprint findings from the same source, and this is the decisive table:

- **Kev-0.8B fits**: ~1.8 GB of bf16 weights; the only family member validated on a
  4 GB GPU.
- **Kev-4B does not**: ~9.3 GB bf16. Worse, the adapter load path briefly holds a second
  copy — measured **15.9 GB peak** against 8.4 GB for pre-merged full weights (Kev repo,
  Serving Performance). Even on a 6 GB 4050 this is out of reach without a 4-bit quant
  that **nobody has published or validated**.
- **Kev-9B** needs ~17 GB; **Kev-27B** 51 GB of weights, ~66 GB resident.
- **CLM-8B does not fit**: ~5 GB at Q4, above 4 GB and uncomfortably tight on 6 GB.

Maker-reported server-side figures for context: Kev-4B answers six questions about a
short text in **18.1 ms** of model time on an H100 and 41.5 ms on an L40S, ~101 req/s
in-process; Kev-0.8B on an L4 hits 63 req/s at 23 ms model time. So the architecture is
fast; the laptop is the constraint.

**One serving feature changes the design.** Kev's server caches the state, so asking
more questions about a document already sent pays only for the questions. On Apple MLX
the effect is dramatic: a 65,000-token state costs Kev-0.8B 21.2 s the first time and
**202 ms** after, at a 3.8 GB peak. On the CUDA backend the measured reuse was only
**1.4×**, not 5×. For MTG this matters enormously — the ideal pattern is *encode the
board once, then ask one question per candidate action* — and the measurement says you
get much less of that benefit on the 4050 than on a Mac. Flag this as a thing to verify
on your own hardware before committing to the design.

### Inferred budget for this project

My arithmetic, clearly labelled as inference. A Standard board state with full card text
is plausibly 2,000–4,000 tokens, so the 798 ms / 2,417-token measurement is the right
anchor. A laptop RTX 4050 is roughly 1.5–2.5× a GTX 1650 in FP16 throughput, giving
**~350–550 ms per decision**. At the measured ~150 surviving decisions per game (Q1),
and more for Standard, call it 200:

- **~70–110 seconds of decider time per game**, on top of the game itself.
- **1,000 games: ~20–30 hours** of laptop GPU time.
- **10,000 games: 8–13 days.**

That is the number that kills the local neural decider as the bulk gauntlet pilot, and
it is a hardware fact, not a modelling opinion.

### Serving options and constrained decoding

| Server | Constrained decoding | Runs on jarlaxle (CPU, ~2 GB free) | Runs on the 4050 | Notes |
|---|---|---|---|---|
| **llama.cpp** | **Yes** — GBNF grammars, JSON Schema auto-converted to a grammar, plus LLGuidance. Invalid tokens masked to −inf before softmax, so output is guaranteed to parse ([grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md), [llguidance.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md)) | Technically, for a tiny model; see the RAM analysis | Yes | Best CPU story. Works in CLI, completion and server. |
| **vLLM** | **Yes** — xgrammar or guidance backends in current stable, with `--guided-decoding-backend` and a native **Choice** option; earlier versions also offered outlines and lm-format-enforcer ([docs](https://docs.vllm.ai/en/stable/features/structured_outputs/)) | **No** — GPU-oriented; its CPU path used 11.4 GiB for Qwen3-1.7B | Tight at 6 GB | The `guided_choice` / Choice primitive is the closest generative analogue to a `choice` question. |
| **ollama** | **Yes** — `format` accepts a full JSON Schema and constrains generation token-by-token server-side, since 0.5 ([docs](https://docs.ollama.com/capabilities/structured-outputs)) | Marginal | Yes, already installed | Lowest friction. Cloud models do not support structured outputs. |
| **TGI** | Yes (guidance/JSON schema) | No | Tight | No advantage here over the above. |
| **LM Studio** | Yes (structured output / schema) | No (GUI-oriented) | Yes | Fine for interactive probing, wrong for a batch harness. |
| **Kev's own `kev.serve`** | **N/A — not needed.** The pointer head emits a distribution over the supplied options; an invalid action is not representable | No | Yes (0.8B) | Type safety by construction, which is strictly better than constraining a decoder. |

**The architectural point:** constrained decoding makes an invalid action *impossible to
emit*, which is necessary but not sufficient — a schema-valid wrong action is still a
misplay, exactly as the Jev reality-check notes about "cannot hallucinate". A typed
decision model gets the same guarantee for free *and* skips generation entirely. If you
go the local-model route, prefer the typed decider to a constrained chat model.

### The owner's four candidate architectures, assessed

| Approach | VRAM | Latency per decision (4050) | Training data needed | Expected quality |
|---|---|---|---|---|
| **Small instruct LLM + GBNF/JSON-schema** | 2–4 GB at Q4 for a 4B | Seconds — it must *generate*, after prefilling the state | None | Mediocre and slow. Strictly dominated by a typed decider on this task shape. |
| **Typed-decision model (Kev-0.8B)** | **~1.8 GB** | **~350–550 ms** (inferred from 798 ms on a GTX 1650) | None zero-shot; ~1,000+ rows to fine-tune usefully | Adequate at depth 0, weak beyond. The pragmatic choice. |
| **Cross-encoder / reranker over (state, action) pairs** | 0.6B reranker ≈ 1.2 GB | One pass **per candidate action** — 14 actions × prefill is the killer unless you cache | Pairwise preferences | **Measured negative**: the controlled study found Qwen3-Reranker and Qwen3-Embedding backbones bring *no* in-domain gain and trail by up to 2.1 points held-out. CLM-8B is the good version of this idea, and it needs an action cache to pay off. |
| **Trained head over hand-engineered state-action features** | **~0** (a few MB; runs on CPU) | **Sub-millisecond** | ~10⁴ labelled decisions, which the gauntlet generates free | **The strongest long-run option.** See Q3(d). The bge-small + logistic regression result (93.3%, beating both Jev and a frontier model, on 10k labelled examples) is the empirical warrant. |

### Confidence

**High** on footprints, licences and the measured latencies — these come from a
reproducible repo with raw logs, plus a controlled academic study, plus HF model cards.
**High** on the constrained-decoding feature matrix (all from primary vendor docs).
**Medium** on my 4050 extrapolation, which scales one measurement from a different GPU.
**Medium-low** on the board-state token count, which nobody has published.
*Deliberately not answered:* a general "best 1B–14B model as of late 2026" leaderboard.
I did not verify one, and for this task shape the typed-decision family is the better
frame than a general-purpose ranking.

---
## Q3 — Non-LLM deciders

The owner asked for extra weight on 3(a). It gets it, because it is the recommendation.

### 3(a) Forge's built-in AI as the default pilot — **the recommendation**

**Verdict: this is the pilot for every bulk gauntlet game. Nothing else is close on the
criteria that matter for a measuring instrument.**

Evidence, from Forge's own documentation
([docs/AI.md](https://github.com/Card-Forge/forge/blob/master/docs/AI.md)):

- The AI is **not trained**. It runs on basic rules and the maintainers say it is easy
  to beat once you know its weaknesses. The logic is mostly heuristic, split between
  effect APIs and other in-game decisions, with occasional hardcoded per-card logic that
  the maintainers themselves describe as usually unhealthy.
- **It is best with aggro and midrange decks**, poor-to-ok in control, pretty bad in most
  combo. For a Standard red-aggro brewing project this is the single luckiest fact
  available: the engine's free policy is strongest precisely in our archetype.
- Headless `sim` mode exists and is documented for this purpose — running AI matches on
  servers with no display, scripting deck tests, bashing out hundreds of games. Flags:
  `-n N` games, `-m M` match length, `-f F` format, `-t` tournament mode (Bracket,
  RoundRobin, Swiss), `-p P` players, `-q` quiet (results only, no log), `-c S` clock in
  seconds before calling a draw (default 120). Invocation: `java -jar forge.jar sim -d
  deck1 deck2 -n 3`.
- The maintainers explicitly invite exactly this project: if you want to train a model
  for the AI, please do.
- Licence **GNU GPL**; Java 17 minimum
  ([wiki](https://github.com/Card-Forge/forge/wiki),
  [User Guide](https://github.com/Card-Forge/forge/wiki/User-Guide)). Java is already
  installed on jarlaxle, so this box needs **no new runtime** — notable given node, npm,
  uv, docker and ollama are all absent.

Why it is the right pilot for a *brewing* tool, stated as the owner framed it:

- **Consistent.** One fixed heuristic policy, identical across every game and every
  candidate decklist. A policy that does not drift cannot introduce drift into your deck
  comparisons.
- **Cheap.** Zero marginal cost per decision; the whole game runs in the engine process.
  This is what makes thousands of games possible at all.
- **Low variance in the policy dimension.** All remaining variance is the card game's
  own (shuffles, matchups), which is what the paired-seed design in Q5 is built to
  cancel.
- **Archetype-aligned.** Vendor-stated aggro competence.

Its weaknesses are real and must be managed rather than ignored: it is beatable, it is
heuristic, and — critically for brewing — **its competence is uneven across cards**. That
is the measurement-bias problem, and it gets its own section below.

### 3(b) Search-based deciders: ISMCTS, PIMCTS, determinization

**Verdict: the academically strongest option and the wrong choice for a solo builder on
this engine. Do not attempt it.**

The literature is real and MTG-specific. The canonical work is Cowling, Ward and Powley,
*Ensemble Determinization in Monte Carlo Tree Search for the Imperfect Information Card
Game Magic: The Gathering*, IEEE Transactions on Computational Intelligence and AI in
Games, 2012
([White Rose eprint](https://eprints.whiterose.ac.uk/id/eprint/75050/1/EnsDetMagic.pdf)),
alongside the same group's *Information Set Monte Carlo Tree Search*
([eprint](https://eprints.whiterose.ac.uk/75048/1/CowlingPowleyWhitehouse2012.pdf)) and
their later work on ISMCTS parallelization
([CEC 2014](http://www.cmap.polytechnique.fr/~nikolaus.hansen/proceedings/2014/WCCI/CEC-2014/PROGRAM/E-14726.pdf)).
**I could not retrieve the numeric results**: the hosting server returns PDF, which my
fetch tool cannot parse. I am citing the existence and topic of the work, not its
figures, and the owner should treat any specific strength claim about ISMCTS-on-MTG as
unverified here.

What the surrounding literature does report, from sources I could read:

- Naive MCTS **performs poorly in large combinatorial action spaces**, which is why one
  group proposed fixed-depth tree search with decoupled Thompson sampling instead
  (arXiv [2012.12186](https://arxiv.org/html/2012.12186v1)). MTG's action space at a
  single priority pass is combinatorial in exactly the bad way (choose a subset of
  attackers, a subset of blockers, an assignment of blockers to attackers).
- Information-gain incentives added to both PIMCTS and ISMCTS improved on the baselines
  and against a cheating-MCTS reference in a hidden-information multi-action game
  ([Springer/ACM](https://dl.acm.org/doi/abs/10.1007/978-3-031-34017-8_6)).
- Combining human-decision prediction with ISMCTS is an active line
  (arXiv [1709.09451](https://arxiv.org/html/1709.09451v1)).
- Supervised prediction models materially improve MCTS strength and efficiency in
  Hearthstone (arXiv [1808.04794](https://arxiv.org/html/1808.04794v1)) — i.e. the
  prior-over-search pattern works in card games.

**The blocking cost is engineering, not algorithmic.** MCTS of any flavour needs to clone
a game state, apply an action, roll out, and discard — thousands of times per decision.
Forge is a GPL Java rules engine built around a single mutable game with a GUI
attached; it does not expose a cheap cloneable state. spike-eval, which is deep inside
Forge, had to build a *puzzle search arm* that **replays the whole game prefix from the
start** for each rollout (`LlmSpikePuzzle.stepSearch` / `REPLAY_HANDOVER`), and even then
bounds the search with `PZL_SEARCH_MAX_DRAWS` and a wall clock. Prefix replay per rollout
is fine for a handful of counterfactuals; it is hopeless as a per-decision policy in a
thousand-game gauntlet.

Expected strength: high. Implementation cost: **very high** (engine surgery). Compute
cost: **very high** (hundreds of rollouts × prefix replay). Realistic for a solo
builder: **no.**

### 3(c) Hand-written heuristic policies

**Verdict: yes, but only as targeted patches over Forge's AI, never as a replacement,
and always behind a flag that the measurement harness records.**

Writing a complete aggro policy from scratch duplicates work Forge already did, in the
archetype Forge is already best at. The useful version is narrow: find a specific spot
where Forge's AI is measurably wrong *for your deck*, encode a rule, and verify the fix
by the Q5 procedure.

Two cautions, both from the harness literature:

- spike-eval classifies its hand-written `greedy:` policy as a **floor**, not a policy:
  preview each cast and non-mana activation, take the largest drop in opponent life,
  else pass; attack with everything; play no land. They keep it to prove that a score
  beats the trivial baseline. Keep your own equivalent, for the same reason.
- Their *"88% lesson"*: a score is meaningless without the trivial baseline it beats.
  Their concrete instance — passing is always legal, so a seat that only ever passes
  scores 1.0 on an all-proposals-legal metric. **Always report a random-legal and a
  greedy baseline next to every gauntlet result.** This is cheap and it catches whole
  classes of harness bug.

Expected strength: moderate on patched spots, zero elsewhere. Implementation cost: low
per rule, unbounded in aggregate. Compute cost: ~0. Realistic: **yes, with discipline
about scope.**

### 3(d) Small learned policy/value networks — **the sleeper pick**

**Verdict: the best long-term decider for this project, and the one the project
uniquely enables. Build it second, after the gauntlet works.**

The argument is empirical and comes from three independent places:

1. **With labels, a small supervised model beats zero-shot decision models and frontier
   LLMs on the same task.** In an independent Banking77 field, bge-small plus logistic
   regression trained on 10,003 examples scored **93.3%**, against Jev's 83.2% and
   GPT-5.6 Terra's 87.5%. The reviewer's conclusion was blunt: if you have labelled data,
   fit a classifier first — decision models earn their place on zero-shot tasks and on
   latency ([jev-usecases](https://github.com/vamsikrishna2421/jev-usecases) §6, citing
   Creative AI News' survey of four independent evaluations).
2. **A trained policy beats frontier LLMs at play, by a wide margin, and is ~1000×
   faster.** AutoTavern's TavernAgent answers **91%** of play tasks against at most 63%
   for frontier LLMs, decides in **0.03 s** against up to 26 s, and within a live turn's
   time budget keeps 90% where no LLM exceeds 26%. On the live ladder its rating went
   from 6,000 to ~15,000, with its last 20 records averaging placement 1.60 and 80%
   firsts, beating the server's ten highest-rated players on every statistic (2.34, 59%)
   (arXiv [2610.33845](https://arxiv.org/abs/2610.33845)).
3. **Small nets generalise surprisingly well in MTG specifically.** DraftFM: a
   **1.6-million-parameter** network fitted on 149 million human picks predicts held-out
   picks in three entirely withheld expansions at 50.8% / 60.4% / 56.7% top-1, where
   chance at the opening pick is about 7% (arXiv
   [2608.19568](https://arxiv.org/html/2608.19568v1)). Different task (drafting, not
   play), but it establishes that tiny models carry real MTG card knowledge.

Why it fits *this* project better than any other option: **a deck-brewing gauntlet is a
labelled-decision factory.** Every game logs (state, legal actions, action taken,
eventual result). Thousands of games produce tens of thousands of rows at zero marginal
cost. That is precisely the regime where the supervised-beats-zero-shot result above
applies.

Expected strength: unknown, plausibly above Forge's AI on the narrow distribution of
your own decks. Implementation cost: **medium** — the real work is feature engineering,
not training. Compute cost: **sub-millisecond, CPU-only**, which means it could run on
jarlaxle, unlike every neural option in Q2. Realistic for a solo builder: **yes**, and it
is the only option that gets better while you sleep.

Two cautions. First, a policy trained on logs of Forge's AI will **imitate Forge's AI,
including its mistakes** — behaviour cloning inherits the demonstrator's ceiling. To
exceed it you need either outcome-weighted training (prefer actions from won games) or
the counterfactual labels from Q6. Second, learned card-game policies can be **highly
exploitable even when they look strong**: ByteRL beat a top-10 Hearthstone player in
China yet its Legends of Code and Magic play was shown to be highly exploitable
(arXiv [2404.16689](https://arxiv.org/html/2404.16689)). For a *measuring instrument*
exploitability matters less than consistency — the gauntlet is fixed and not adversarial
— but it is a reason never to report your agent's strength as if it were general.

### Confidence

**High** on 3(a) — Forge's own documentation states the aggro competence and the `sim`
interface. **High** on the engineering blocker in 3(b), which I verified by reading how
an existing in-Forge project had to implement search. **Medium-high** on 3(d), which
rests on three strong but analogous results rather than a direct MTG-play measurement.
**Low** on any numeric strength claim for ISMCTS-on-MTG; I could not read the paper.

---
## Q4 — Hybrid designs used in practice

### Verdict

Three of the four patterns are real and documented. **Cascade routing** is in production
and has a published cookbook. **LLM-as-prior over search** is real but blocked by Forge's
architecture. **Distillation into a local model is the one to build**, and the data
volumes needed are now published. The LLM-per-move pattern is the one to avoid, and that
is a measured result.

### Cascade / speculative routing: real, in production

OpenRouter ships a Jev cookbook titled *Cut LLM Cost with a Jev-Verified Cascade*: draft
with a cheap model, verify the draft against retrieved context with the decision model,
and escalate to a stronger model only when the check fails
([OpenRouter Jev guide](https://openrouter.ai/docs/guides/community/jev)). The same page
lists a tool-call gate (safe calls run, unsupported refused, ambiguous pause for a human)
and an auto-approve recipe for coding-agent permission prompts using a reversibility
check. LangChain exposes the same thing as middleware — `ModelRouterMiddleware` with
named choices and criteria, and `AutoModeMiddleware` for gating risky tool calls
([LangChain](https://www.langchain.com/blog/building-a-harness-with-jev)).

The economics, with the honest version stated by the source itself: on a million-ticket
cascade using the vendor's own figures the bill was ~$6,480 instead of ~$30,400 — a
**4.7× saving on the whole system**, not the 400× headline, because the cascade only
removes the easy slice ([jev-usecases](https://github.com/vamsikrishna2421/jev-usecases)
§5). The source calls the 1:1 replacement comparison "the wrong-shaped comparison for
most real migrations". That 4.7× is the number to plan against.

**The warning, again, and it is specific to our game:** the one team that built a
cheap-tier cascade *inside an MTG harness* retired it (Q1, `ONE_TIER=0`). Cascades work
well when the easy slice is genuinely easy and independently verifiable. In MTG the
"easy" slice is mostly already handled by the deterministic rules, and what is left is
mostly not easy.

### LLM-as-prior over search (the AlphaZero pattern)

Real, published, and blocked here by engineering rather than by theory.

- **Supervised priors improve card-game MCTS**: demonstrated in Hearthstone (arXiv
  [1808.04794](https://arxiv.org/html/1808.04794v1)).
- **Code World Models** (arXiv [2510.04542](https://arxiv.org/pdf/2510.04542)) is the
  most interesting variant: rather than prompting for moves, use the LLM to translate
  rules and trajectories into an executable Python world model — state transition, legal
  move enumeration, termination — then run MCTS against it, with LLM-generated heuristic
  value functions to make the search efficient and inference functions to estimate hidden
  state. Their stated motivation is that direct move generation relies on fragile pattern
  matching and yields frequent illegal moves and shallow play.
- **PIANIST** (arXiv [2411.15998](https://arxiv.org/html/2411.15998)) decomposes a
  partially-observable world model into seven components an LLM can generate zero-shot
  from a natural-language game description, for fast MCTS.
- **PriorZero** (arXiv [2605.12289](https://arxiv.org/pdf/2605.12289)) names the failure
  modes directly: a fixed LLM prior limits exploration because it is blind to
  environment-specific dynamics, while end-to-end fine-tuning suffers optimization
  instability and credit-assignment problems.

For this project the Code World Models route is a trap of a particular kind: we already
*have* a rules-complete engine, so generating a second, approximate one is a step
backwards — and an approximate simulator would silently bias deck comparisons, which is
the one thing this project cannot tolerate. The MCTS-over-Forge route is blocked as
described in Q3(b).

### Distilling frontier decisions into a local model: realistic, and sized

**This is the hybrid worth building, and the data volumes are published rather than
guessed.** Kev's own documentation reports fine-tuning results that answer the owner's
question directly ([kev README](https://github.com/jaredpalmer/kev)):

| Fine-tune data | Result |
|---|---|
| **400 records** | Gain was **inside the noise** |
| **1,050 generated records**, 3 questions, 15 min on one H100 | Kev-4B 67.7% → **73.6%** accuracy; decisions automated at a 5% error budget 34% → **48%** |
| **5,219 labelled real records**, one epoch | Kev-4B 0.804 → **0.904** on unseen items |

So the answer to "what data volume?" is: **~400 rows is wasted effort, ~1,000 rows buys a
measurable gain, ~5,000 rows buys a large one.** A deck-brewing gauntlet at ~150–250
decisions per game reaches 5,000 logged decisions in roughly **20–35 games**. The data is
not the constraint; labelling quality is.

Three further details that materially change how you would do it:

- **Always use `--init_from`, never train from the base.** Measured on 836 support-tool
  decisions: a fine-tune from the base model scored **0.33** on Kev's own eval set
  against 0.84 for the released model; the same data with `--init_from` kept **0.83**
  there and reached **0.88** on the new domain. Use a smaller learning rate (2e-5) than
  the from-scratch recipe.
- **A 0.8B fine-tune fits the laptop.** `--batch 1 --accum 8` in bf16 fits the 0.8B model
  on a **4 GB** GPU, so the 6 GB 4050 has headroom. Kev-4B training needs an H100 — about
  **$1 per run** on Modal, and the repo ships a skill that runs the whole loop and tears
  the infrastructure down afterwards. A frugal hybrid: train 4B in the cloud for a dollar,
  but you still cannot *serve* it on 6 GB.
- **Fine-tuning fixes the calibration complaint.** Each checkpoint stores a fitted
  temperature. On new sources, refitting took Kev-9B's calibration error from 0.103 to
  **0.041** and its confident errors (wrong at p ≥ 0.9) from 8.2% to **2.4%** — below
  Jev's 3.7%. Temperature never changes which answer wins, only the probability you
  threshold on. Since the whole escalation design depends on thresholding a confidence,
  **refit the temperature on your own gauntlet labels** and treat the shipped one as a
  placeholder.
- **Kev's benchmark already reports the metric you need**: the share of decisions you
  could automate at a 5% error budget. That is exactly the triage question from Q1,
  expressed as a number you can optimise. Adopt the metric.

QLoRA's feasibility on consumer hardware is well established generally — the original
paper finetuned a 65B model on a single 48 GB GPU and matched 16-bit performance (arXiv
[2305.14314](https://arxiv.org/html/2305.14314)); 4-bit QLoRA on a 7B needs roughly 6 GB
([lora-qlora-101](https://github.com/Cyr-Ch/lora-qlora-101)). So a 7–8B QLoRA is right at
the edge of the 4050 and comfortable in the cloud, but the per-decision *serving* problem
from Q2 remains: a 7B at ~1 s per decision is unusable in a thousand-game gauntlet
regardless of how it was trained.

### The pattern to avoid, with the measurement

**Frontier model per priority pass.** spike-eval publishes the real numbers: a game costs
about **$0.09** on average (median $0.07) with their default frontier model, takes about
**18 minutes** on average (range 5–90), and the model may think for minutes on one hard
decision. Their puzzle eval put 20 models on 5 hard puzzles for one game each: 5 models
solved all five, 3 solved none, 58 of 100 games solved — and they caution against reading
it as a ranking, since one game per puzzle cannot separate close models and some failures
were harness losses or early stops.

At 18 minutes per game a thousand-game gauntlet is **12.5 days of wall clock**, and
10,000 games is four months. Against Forge-vs-Forge in seconds, this settles it: the
frontier model cannot be in the per-decision loop of a brewing tool. It belongs where
AutoTavern put it — **building**.

### Confidence

**High** on the cascade pattern and its honest 4.7× figure (vendor cookbook plus a
source that explicitly debunks its own headline). **High** on the fine-tuning data
volumes and the `--init_from` and temperature findings — these are specific measured
numbers in the project's own documentation with run directories cited. **High** on the
frontier-per-move cost, which is measured in a running harness. **Medium** on the
LLM-prior-over-search papers, which I read as abstracts rather than in full.

---
## Q5 — Measuring whether a change is any good

### Verdict

Use the chess-engine testing playbook, which solved exactly this problem (tiny effects,
huge variance, cheap games): **paired games with shared seeds and swapped seats, the
pair as the unit of analysis, and a sequential test instead of a fixed sample size.**
The maths below is complete enough to implement directly.

### Sample size, worked out

Standard two-proportion test, two-sided α = 0.05, power 80%. The constant is
(z₀.₀₂₅ + z₀.₂₀)² = (1.96 + 0.8416)² = **7.849**.

**Unpaired, two decklists each played against the same gauntlet:**

n per arm = 7.849 × [p₁(1−p₁) + p₂(1−p₂)] / (p₁−p₂)²

| Effect | Per arm | **Total games** |
|---|---|---|
| 50% → 53% (3 pp) | 4,353 | **8,706** |
| 50% → 55% (5 pp) | 1,562 | **3,124** |

**One-sample, comparing a candidate against a control whose win rate you have already
measured to high precision** (e.g. 20,000 games banked on the control list):

n = 7.849 × p(1−p) / δ²

| Effect | **Games needed** |
|---|---|
| 3 pp | **2,180** |
| 5 pp | **785** |

That 4× difference is free. **Bank a very large control run once, then test each
candidate against it as a one-sample problem.** This is the single highest-leverage
statistical decision in the project and it costs nothing but disk.

**Paired design.** Playing both lists against the same gauntlet draw with the same seed
makes the outcomes correlated, and required n scales by (1 − ρ) where ρ is the
correlation between arms on the same seed. ρ = 0.25 saves a quarter of the games, ρ = 0.5
halves them. **ρ must be measured on your own data, not assumed** — estimate it from your
first paired block and then use it to size everything afterwards.

**Mirrored seats.** Play each seed twice with the seats swapped. This is the direct
analogue of chess's practice of playing every opening from both sides, and it cancels the
play/draw advantage, which in Standard is large. The **unit of analysis becomes the pair**,
with outcomes in {0, 1, 2} wins — a trinomial over pairs, which is precisely the role
Fishtest's **pentanomial** model plays over its game pairs. Fishtest states that the
pentanomial model, by accounting for five paired outcomes rather than three unpaired ones,
yields a substantial saving of testing resources over the trinomial
([Fishtest Mathematics](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-Mathematics.html)).
Expect a similar order of saving here, and measure it.

A bonus from the same page: the difference between pentanomial and trinomial predictions
lets Fishtest estimate the RMS bias in its opening book. The analogue is directly useful
— **the gap between your paired and unpaired variance estimates is an estimate of how
much of your signal is shuffle luck rather than deck strength.**

### Elo conversion

Elo = −400 · log₁₀(1/p − 1):

| Win rate | Elo |
|---|---|
| 52% | **+13.9** |
| 53% | **+20.9** |
| 55% | **+34.9** |

Worth internalising: a 3-point win-rate change is ~21 Elo, which in chess-engine terms is
a very large improvement. If a single card swap genuinely moves 5 points, you are looking
for ~35 Elo, and that is detectable in hundreds of games rather than thousands. Changes
smaller than 1 pp (~7 Elo) are, for practical purposes, **not measurable** by a solo
builder and should not be chased.

Fishtest expresses its bounds in **normalized Elo**, which makes the expected duration of
a test depend only on the chosen bounds and not on the draw ratio or the opening book
(same source). The MTG analogue of the draw ratio is the matchup-dependent variance of
your gauntlet; normalizing serves the same purpose and makes test lengths comparable
across gauntlet compositions.

### Sequential testing (SPRT), implementable

Fishtest uses the **Generalized SPRT (GSPRT)**, in which unknown parameters in H₀ and H₁
are replaced by their maximum-likelihood estimates; it behaves asymptotically like SPRT
as error probabilities approach zero, and its guarantees do not depend on the Elo
differences being small. Elo is estimated from completed tests by approximating the GSPRT
as a random walk — an SPRT for the drift of a Brownian motion with variance estimated from
the sample (same source). The background on the plain test is at
[chessprogramming.org/Sequential_Probability_Ratio_Test](https://chessprogramming.org/Sequential_Probability_Ratio_Test);
Fishtest's own implementation is
[`stat_util.py`](https://github.com/glinscott/fishtest/blob/master/server/fishtest/stats/stat_util.py).
SPRT minimizes expected sample size among sequential tests with the same or smaller
Type I and Type II error (arXiv [2410.16076](https://arxiv.org/html/2410.16076v1)).

Plain SPRT is enough to start, and here it is in full. Hypotheses H₀: p = p₀ (no
improvement), H₁: p = p₁. After W wins and L losses:

```
LLR = W·ln(p₁/p₀) + L·ln((1−p₁)/(1−p₀))
```

With α = β = 0.05 the boundaries are:

```
accept H₁ when LLR ≥ ln((1−β)/α) = ln(19) = +2.944
accept H₀ when LLR ≤ ln(β/(1−α)) = ln(0.05/0.95) = −2.944
otherwise keep playing
```

For bounds p₀ = 0.50, p₁ = 0.55, each win adds ln(1.10) = **+0.09531** and each loss adds
ln(0.90) = **−0.10536**. Expected drift per game is +0.00501 if the truth is 0.55 and
−0.00503 if it is 0.50, so the expected stopping point is about **588 games** either way,
against **785** for the fixed-n one-sample design — roughly a **25% saving at the bound**,
and far more when the true effect is larger than the bound, which is the common case for
an obviously good card. For 3 pp bounds (p₀ = 0.50, p₁ = 0.53) the expected stop is about
**1,634 games** against 2,180 fixed — the same ~25%.

Two implementation notes. Run the SPRT **on the paired unit**, not on individual games,
or the independence assumption fails and the error rates are wrong. And pre-register the
bounds: SPRT is safe to check continuously only because its boundaries were computed in
advance, which is exactly what distinguishes it from peeking at a fixed-n test
([Fishtest FAQ](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-FAQ.html)
notes workers report every eight games).

### Elo-style rating of policy versions

For comparing *pilot policies* rather than decklists, run a round-robin and fit ratings.
Forge's `sim` already supports `-t RoundRobin | Swiss | Bracket` with `-p` players, so the
tournament scaffolding is free. Keep the decklists fixed and vary only the policy, and
include the random-legal and greedy floors from Q3(c) as anchors so the scale is tied to
something absolute.

### Seeding: the one thing to verify first

Everything above requires reproducible shuffles. **Stock Forge's documented `sim`
interface has no seed flag** — `AI.md` lists `-d -D -n -m -f -t -p -q -c` and nothing
for RNG. spike-eval clearly has seeded, reproducible games (`--seeds 4101`,
`PZL_SEEDS`, pinned canaries at specific seeds, and the note that both seeds replay to
the same game), which it achieves through its own overlay and `engine-patches/`. That is a
strong argument for **building on spike-eval's seeded path rather than stock `sim`** —
it is GPL-3.0-or-later, like Forge, and compiled into Forge. *Unverified:* whether stock
Forge exposes a seed by any undocumented route, and whether Forge's AI is fully
deterministic given a fixed seed. Both are day-one checks, and both are load-bearing.

### Confidence

**High** on the arithmetic — I computed it and it is reproducible from the formulas
given. **High** on the SPRT and pentanomial methodology, from Fishtest's own
documentation. **Medium** on the transfer of the pentanomial saving to MTG, which is an
argument by analogy; the analogy is good (paired games, high variance, cheap play) but
MTG's variance structure is not chess's. **Medium-low** on the seeding situation, which is
inferred from one project's flags rather than read from Forge's source.

---
## Q6 — "Did it actually misplay?"

### Verdict

Counterfactual replay is not a design proposal — **it has been built, in Forge, for MTG,
and the technique has a name and a script.** Adopt it. The surrounding ideas
(hindsight analysis, regret estimates) are sound but mostly need labelling as design
proposals, which I do below.

### Evidence: step regret, a real implementation

spike-eval implements counterfactual rollout from a decision point in two stages
(ARCHITECTURE.md, `replay:` bridge and `eval/puzzles/step_regret.py`):

**Step 1 — deterministic replay.** A `ReplayBridge` plays a recorded game back exactly:
every recorded model turn is served back with its calls as recorded, so skips, side
effects and RNG draws are the recorded game's. The replay is verified aggressively — each
ask must be the recorded ask (same answer field, same option labels *in order*, same
ranges, same DECISION line, same turn and step), each decision row must equal the
recorded row (type, option count, choice, options), and the game must end with the
recorded status and `log_sha256`. The first mismatch is a **drift**: the run ends
immediately and the row is marked `drift`. Prompt wording differences are counted
separately and are not drifts. This matters because **a counterfactual is worthless if
the replay itself is not faithful**, and they made unfaithfulness loud rather than silent.
Measured: 14 recorded attempts replayed on a later engine epoch to the recorded status,
`log_sha256` and engine log.

**Step 2 — hand over to search at decision K.** With `REPLAY_HANDOVER=K`, the replay seat
plays the first K decisions and then hands the rest of the game to a search arm. The
engineering care here is instructive: the handover deliberately avoids drawing from the
engine RNG (the search arm's own constructor would draw a long and shift the whole rest of
the game against the recording), drops a yield the recording asked for, and verifies that
the first decision after the handover is the recording's row K+1 — same type, same menu
size, same options. Every rollout replays the prefix into a discarded sink so the row
checks still run, then searches the remainder against Forge's AI **on the recorded seed**.
Verdicts per rollout: `proven` (a winning line found and replayed once more),
`unwinnable` (every line played out, none truncated by `PZL_SEARCH_MAX_DRAWS` or the wall
clock), `not_found`, `drift`. `REPLAY_FORCE=o` forces one specific option at K;
`REPLAY_FORCE=all` tries each.

**Step 3 — locate the regret.** `step_regret.py` scans positions before each model
decision **backwards from the end** until one is `proven`, then names the regret decision
as the point where the next position is `unwinnable`, bracketing it when `not_found` lies
between, and reports a floor (options decided over options total, exact only when every
option was decided).

That backwards scan is the clever part and the part worth copying: against a
deterministic opponent, a won position never becomes lost again, so walking back from the
end finds the **last** position that was still winnable, and the decision immediately
after it is the blunder. This cleanly separates a bad decision from a bad outcome, which
is the owner's exact question.

**Two honest limits**, both from the source. First, the whole apparatus runs on
*puzzles* — fixed boards with a "win this turn" goal and a deterministic opponent — not on
full games against a stochastic opponent. Second, the recordings they have verified hold
only `play` and `target` decisions plus harness-auto rows; lookups, yields, keep-untapped,
blocks and multi-picks go through the same path but have **not yet been shown to replay**.
So the technique is proven on a restricted slice, and extending it to blocks (where
combinatorics explode) is unproven work.

### Why puzzles, not win rates, for judging decisions

spike-eval's reasoning for building a puzzle eval is directly applicable and worth
quoting in substance: counting wins makes a poor eval because Magic has a lot of luck in
it and decks beat each other rock-paper-scissors, so a win rate says more about the draw
and the decks than about the player. A puzzle removes the luck — a board, a goal, and
either you find the line or you don't. Their hard suite only admits a board if random
play and all the fixed baseline players fail it.

**For a brewing tool this gives you a second, orthogonal instrument.** Win rate measures
the deck; a puzzle suite measures the pilot. If you suspect the pilot is the problem
rather than the deck (Q3(a)'s bias question), a puzzle suite is how you check — and it is
cheap, because puzzles are deterministic and short.

### Hindsight analysis and regret estimates — design proposals

Labelled as proposals. I found no published MTG-specific work on either, and the owner
should treat these as my suggestions rather than as cited practice.

1. **Hindsight flagging to shortlist candidates for expensive replay.** Counterfactual
   rollout is expensive (prefix replay per rollout), so do not run it everywhere. Use the
   full game log, with the hidden information revealed after the fact, to cheaply flag
   suspicious decisions: a card held in hand until death that was castable for three or
   more turns; removal pointed at a creature when a lethal-relevant one was on board;
   an attack that lost a creature for no damage; mana left unspent in a turn where
   something castable was in hand. Then replay only the flagged decisions. This is a
   recall-oriented filter feeding a precise-but-costly verifier, and it is the standard
   shape for this kind of audit.
2. **Regret as a value delta rather than win/loss.** Where a full rollout to a terminal
   state is too expensive, estimate regret as the difference in a cheap value proxy
   (life totals, board presence, cards in hand) at a fixed horizon of N turns after the
   decision, averaged over several opponent draws. Cheaper and noisier than the proven/
   unwinnable verdict, and suitable for bulk triage. Note this reintroduces exactly the
   heuristic-value-function bias that the proven/unwinnable approach avoids, so use it to
   rank, never to conclude.
3. **The frontier model as the offline reference oracle.** This is where hosted Jev or a
   frontier LLM earns a place despite the local-only constraint: run it over the
   *flagged* decisions only, offline, well outside the production loop, and treat
   disagreement with the pilot as a third flag. Volume is small (dozens per game, not
   hundreds), latency does not matter, and the cost is bounded. Jev's `choice` primitive
   with the recorded legal-action list is a natural fit — and this is exactly the pattern
   Arize recommended for LLM judges: run the cheap decision model over everything for
   coverage, then re-run the failures through the expensive judge for the directional
   signal ([via jev-usecases](https://github.com/vamsikrishna2421/jev-usecases) §6).
4. **Labels for Q3(d).** Every confirmed regret decision is a high-quality training row
   with a *known-correct* alternative action. This is how the learned policy escapes the
   behaviour-cloning ceiling noted in Q3(d): you are not imitating Forge's AI, you are
   training on positions where Forge's AI was proven wrong.

### Confidence

**High** on the step-regret implementation — it is documented in detail with named
scripts, env vars, verdict values, and a cited measurement of 14 replayed attempts.
**High** on the puzzles-beat-win-rates argument for judging a pilot. **Low to none** as
evidence for items 1–4, which are my design proposals and are labelled as such; item 3's
cascade-and-re-judge shape is the only part with a citation behind it.

---

## Q7 — Learning without weight updates

### Verdict

**More marketing than measurement, and the one careful study of the failure mode found
something worse than "it doesn't help much": it found that reflective memory can
entrench false beliefs.** Use external memory for facts you can verify programmatically.
Do not use free-form self-reflection as the learning mechanism.

### Evidence: the failure mode is measured

*Honest Lying: Understanding Memory Confabulation in Reflexive Agents* (arXiv
[2605.29463](https://arxiv.org/abs/2605.29463), ICML 2026 Workshop on Failure Modes in
Agentic AI) is the key source, and its results are stark:

- Reflexion-style agents assume agents can accurately diagnose their own failures. The
  paper shows this assumption **fails systematically**: across ALFWorld and HumanEval,
  agents store confident but incorrect interpretations of the task and keep acting on
  them across trials — **even though the environment resets to the correct task each
  time**.
- They name it **memory confabulation** and introduce the **Reflection Repetition Rate
  (RRR)**, a log-based metric for repeated reliance on incorrect reflective content.
- They identify **16 "frozen" ALFWorld environments in which 0 of 121 reflections mention
  the correct target object**, plus 4 analogous HumanEval cases. Zero out of a hundred and
  twenty-one.
- **The mitigation is the actionable finding**: replace open-ended self-diagnosis with
  **programmatic extraction of trajectory-level failure signals**. That took correct
  object mention from **0% to 86%**, RRR from **0.64 to 0.10**, and solved 3 of the 16
  frozen environments.

Supporting critiques, which triangulate the same conclusion:

- A position paper argues contemporary agentic memory is "a memo, not true memory",
  characterising Reflexion as verbal self-critiques in an episodic buffer and Voyager as
  skills accumulated as code in a vector database (arXiv
  [2604.27707](https://arxiv.org/pdf/2604.27707v1)).
- Voyager-style agents "often struggle with rudimentary tasks, even when fine-tuned on
  domain-specific knowledge" when driven by open LLMs (arXiv
  [2411.12977](https://arxiv.org/html/2411.12977v2)).
- Agents that mutate their own prompts accumulate **silent objective drift** — progress by
  the agent's own lights, divergence from the user's intent
  ([coevolution-kernel](https://github.com/hegu-1/coevolution-kernel), a position paper).

The original works are real and worth reading as design references — Reflexion (verbal
reinforcement learning, textual diagnoses from grounded feedback), Voyager (verified
executable skills retrieved compositionally), and ExpeL (collect successes and failures,
extract cross-task insights, apply them at evaluation time, arXiv
[2308.10144](https://ar5iv.labs.arxiv.org/html/2308.10144)). The pattern that holds up is
the **Voyager** one, and the reason is structural: a skill is *verified executable code*,
so the environment, not the model, decides whether it goes in the library. Reflexion's
textual diagnoses have no such gate, which is exactly the hole the confabulation paper
drove through.

### What this means for the deck brewer

The owner's "harness holds deck strategy and match history, and learns" is the Reflexion
pattern unless it is designed not to be. Three concrete consequences:

1. **Extract failure signals programmatically, not narratively.** Do not ask the model
   "why did you lose?" and store the answer. Compute it: mana curve stumbles, turns with
   unspent mana, cards never cast, the turn the opponent's clock became lethal, which
   gauntlet deck won and in how many turns. This is the confabulation paper's own
   mitigation, with its 0% → 86% result behind it.
2. **Gate every memory entry on verification.** The Voyager analogue here is strong: a
   "deck strategy note" should only enter the library if it is backed by a gauntlet
   result that passed the Q5 test. An unverified note is a confabulation waiting to be
   retrieved.
3. **Measure RRR.** It is a log-based metric; the gauntlet produces logs. If the same
   wrong belief about a card keeps reappearing across iterations, you want a number that
   says so rather than a vibe.

One more structural warning specific to brewing: because the gauntlet is **fixed**, a
memory loop will happily overfit to it. The confabulation paper's agents could not escape
a false belief because nothing contradicted it; a brewing agent optimising against five
frozen decks has the same problem by construction. Hold out gauntlet decks the iteration
loop never sees — spike-eval does exactly this, reserving seed blocks for evaluation and
keeping panel seeds, held-out decks and held-out puzzles out of training data
(`eval/seed_policy.py`, `eval_only.py`).

### Confidence

**High** on the confabulation results and the programmatic-extraction mitigation — a
workshop-accepted paper with specific counts and a measured intervention. **High** that
the original Reflexion/Voyager/ExpeL papers exist and say what I describe. **Medium** on
my three consequences, which are reasoned transfers to a domain nobody has studied this
way. **High** on the overfitting-to-a-fixed-gauntlet risk, which follows from the design
rather than from evidence.

---
## The measurement-bias problem

The owner named the risk precisely: **if the pilot plays a new card badly, the deck
change looks bad for the wrong reason.** This is the central threat to the whole tool, so
it gets its own section. The good news is that Forge makes it unusually detectable.

### Why it happens, mechanically

Forge's AI is heuristic, with per-card logic in the card scripts. The Card scripting API
exposes an `SVar` that is, for our purposes, a gift:

> `RemAIDeck` prevents a card from appearing in random AI decks. It applies to cards the
> AI cannot use at all **and to cards the AI could use but only ineffectively**; the AI
> also will not draft them
> ([Card scripting API](https://github.com/Card-Forge/forge/wiki/Card-scripting-API)).

That is a **machine-readable, maintainer-curated flag for "Forge's AI plays this card
badly."** There is also a per-card `AILogic` mechanism driving play priority and timing
priority, discussed at length by Forge contributors
([slightlymagic thread](https://slightlymagic.net/forum/viewtopic.php?f=52&t=20874)),
and related hint SVars such as `BuffedBy`
([thread](https://slightlymagic.net/forum/viewtopic.php?f=52&t=18792)).

So the bias is not a mystery: it concentrates in cards with no `AILogic` and/or a
`RemAIDeck` flag. Standard makes this worse than Pauper would, because new sets add
complex cards faster than AI hints get written for them — and a brewing tool is, by
definition, pointed at new cards.

### Five detectors, cheapest first

1. **Pre-flight card audit (free, instant, do this always).** Before running any gauntlet
   on a candidate card, grep its Forge card script. If it carries `RemAIDeck`, Forge's own
   maintainers are telling you the AI cannot evaluate it. If it has no `AILogic` and a
   non-trivial activated or triggered ability, treat the result as suspect. **Emit this as
   a warning attached to every deck comparison involving that card.** This single check
   costs minutes to build and catches the most common failure.
2. **Card-level usage instrumentation (cheap).** For every card in the list, log: cast
   rate per game, average turn cast, times drawn but never cast, times held while
   castable, targets chosen. A card the pilot never casts, or casts at implausible times,
   cannot be evaluated by that pilot — and this shows up immediately as a near-zero cast
   rate. Report these alongside the win rate, not in a separate file.
3. **Pilot-sensitivity test (the decisive one).** Run the same A/B under two different
   pilots: Forge's AI, and Forge's AI plus your heuristic overrides (or the greedy floor).
   **If the sign of the win-rate delta flips, the result is a property of the pilot, not
   of the deck**, and must be discarded. If the sign holds and only the magnitude moves,
   the finding is robust. This is the standard robustness check and it is the main reason
   to keep more than one pilot alive even after choosing a default.
4. **Known-answer anchors (calibration).** Keep a small set of swaps whose direction is
   not in dispute — a strictly-better burn spell, an obviously wrong land count, a card
   that is simply unplayable. Run them through the full pipeline periodically. If the
   instrument cannot recover a known answer, it is broken, and no novel result from it
   means anything. This is also the day-one acceptance test (see below).
5. **Flagged-decision audit (expensive, targeted).** For a card whose result you distrust
   after detectors 1–3, run the Q6 counterfactual replay on the decisions where that card
   was in hand or on board. If replay shows the pilot repeatedly took a proven-worse action
   with that card, you have confirmed pilot incompetence rather than card weakness — and
   you have the training rows to fix it.

### The honest limit

Detectors 1–4 tell you **whether** to trust a result. They do not tell you what the card
is actually worth. For a card Forge's AI genuinely cannot pilot, the correct output of
this tool is not a number but a sentence: *"cannot evaluate this card; the pilot does not
use it correctly."* A brewing tool that says so is far more valuable than one that
confidently reports a biased win rate, and this should be a first-class output of the
pipeline rather than an error case.

---

## Recommended decision pipeline

Four layers. Layer 0 does almost all the work.

```
Layer 3  Frontier LLM (Codex / kiro-cli)  — offline, between gauntlet runs
         Picks card changes. Reads programmatically-extracted match reports.
         Proposes the next candidate list. Writes the SPRT bounds. Never plays.
                            │  candidate decklist
                            ▼
Layer 0  Forge built-in AI  — pilot for 100% of bulk gauntlet games
         Runs on jarlaxle, headless `sim`, parallel JVMs, seeded.
         Zero marginal cost. Aggro-competent per vendor docs.
                            │  game logs + win rates
                            ▼
Layer 1  Deterministic auto-resolve  — only in audited games where a model plays
         The four spike-eval owner rules + the floating-mana exception.
                            │  surviving decisions
                            ▼
Layer 2  Local decider (Kev-0.8B on the 4050)  — audited subset only, ~1-5% of games
         Typed `choice` over the enumerated legal actions. No text generation.
         Confidence-gated; temperature refit on your own labels.
```

And an offline branch, outside the loop:

```
Q6 audit:  hindsight flags → counterfactual replay (step regret) → confirmed misplays
                                      │
                                      ├─► warnings attached to deck comparisons
                                      └─► labelled rows → Layer 2 fine-tune, then a
                                          feature-based policy net (Q3(d))
```

### Why this shape

- **Layer 0 carries the bulk** because the pilot is a measuring instrument, and
  consistency and cost dominate strength. Forge's AI is free, fixed, and vendor-stated
  best at our archetype.
- **Layer 2 is deliberately not in the bulk path.** The Q2 arithmetic (~70–110 s of
  decider time per game, 20–30 hours per thousand games) makes it impossible there, and
  the Q1 fast-tier retirement warns that a cheap tier in the bulk path corrupts the
  measurement anyway. Its real job is to be a *second opinion* on a small audited sample,
  so you can quantify how much Layer 0 is costing you.
- **Layer 3 builds rather than plays**, which is the AutoTavern result (91% vs ≤63%,
  0.03 s vs 26 s) and the single clearest finding in this investigation.
- **The offline audit branch is what makes the thing improve**, and it feeds Q3(d), the
  only decider that could eventually run on jarlaxle at sub-millisecond cost.

### Build order

1. **Seeded Forge-vs-Forge gauntlet on jarlaxle.** Fork or vendor spike-eval's seeded
   path rather than stock `sim` (Q5 seeding caveat). Measure Forge's RAM per JVM and
   games/hour, and find where jarlaxle's missing 6 GB of RAM is going.
2. **The known-answer acceptance test.** Below. Do not proceed past this.
3. **Paired/mirrored harness with SPRT**, bounds pre-registered, control run banked
   large, ρ measured from the first block.
4. **Programmatic match-report extraction** (Q7) and the card-usage instrumentation plus
   `RemAIDeck`/`AILogic` pre-flight audit (bias section).
5. **Layer 3 loop**: frontier model proposes candidates, reads reports, iterates.
6. *Only then* **Layer 2**: `kev.serve` with Kev-0.8B on the laptop, on an audited
   subset, with the temperature refit on your own labels and the
   automated-at-5%-error-budget metric as the target.
7. *Only then* **Q6 step regret**, and from its labels, the Q3(d) feature-based policy.

Steps 1–5 need **no GPU, no local model, and no hosted API**. If the project stopped
after step 5 it would already be a working deck-brewing tool. That ordering is
deliberate: every decider option in this report is an optimisation of a loop that must
first exist and must first be trustworthy.

### The cheapest experiment that proves or kills it

**The known-answer A/B.** One day of work, zero dollars, no GPU, no model.

- Build two Standard decklists differing by exactly one swap whose direction nobody
  disputes. Two candidates: 4 Lightning Bolt against 4 Shock (strictly better card,
  expected effect small but positive), and a correct land count against a clearly wrong
  one (expected effect large, several points).
- Run both against a fixed three-to-five-deck gauntlet, paired seeds, seats mirrored,
  pilot = Forge's AI on both sides.
- Apply the Q5 SPRT with bounds p₀ = 0.50, p₁ = 0.55. Expect a verdict in roughly 600
  paired units if the effect is at the bound, far fewer for the land-count test.
- Report the random-legal and greedy floors beside the result (the 88% lesson).

**Pass:** the instrument recovers the known-better list with the right sign, and the
land-count test — where the true effect is large — resolves quickly and decisively.
Then build the rest.

**Fail, and what each failure means:** no significant difference on the land-count test
means the harness or the seeding is broken, not that land counts don't matter. A *wrong
sign* means the pilot is biased in a way that inverts results, and that must be
understood before anything else is built. A verdict that will not stabilise across reruns
with different seed blocks means your variance model is wrong and the sample sizes in Q5
are too small for your gauntlet.

This test is worth more than every model-selection decision in this report, because it
is the only thing that establishes whether the measuring instrument measures anything.

---

## What I could not verify

Stated plainly, separated from the findings above.

**Resolved, contrary to the original brief:** the brief asked me to report that no tool
named 'jev' could be identified. The opposite is true — Jev is real, well documented and
central to this analysis. The original brief's framing is superseded.

**Could not verify:**

- **ISMCTS-on-MTG numbers.** The Cowling/Ward/Powley paper is hosted as PDF, which my
  fetch tool cannot read. I cite its existence and topic only. Any specific strength
  claim about ISMCTS in MTG should be treated as unverified here.
- **Forge's resident memory per JVM and games/hour for Standard.** No published figure
  found. This is load-bearing for the parallel gauntlet plan on an 8 GB box and is a
  day-one measurement.
- **Whether stock Forge `sim` can seed its shuffles.** Not in `AI.md`'s flag list. I infer
  spike-eval adds it via its overlay and `engine-patches/`, but I did not read Forge's
  source.
- **Whether Forge's AI is deterministic given a fixed seed.** Essential for paired
  testing and the Q6 replay. Unconfirmed.
- **Standard board-state token count.** Nobody publishes it. All my per-decision cost and
  latency arithmetic rests on a 2,000–4,000 token estimate and scales linearly with it.
  Measure it first; it moves every number in Q2 and the Jev pricing section.
- **Kev-4B at 4-bit on a 6 GB 4050.** Plausible on paper, but no published or validated
  quantisation. Do not plan on it.
- **My RTX 4050 extrapolation** (~350–550 ms/decision) scales a GTX 1650 measurement by a
  1.5–2.5× guess. Benchmark it directly; it is a 30-minute job and it decides whether
  Layer 2 is viable even for audits.
- **A general "best 1B–14B open model, late 2026" ranking.** I did not verify a current
  leaderboard, and deliberately framed Q2 around the typed-decision family instead, which
  fits the task shape better. If the owner wants a general ranking, that is a separate
  search.
- **jarlaxle's RAM breakdown.** 8 GB total with ~2 GB free means ~6 GB is committed to
  something. Until that is known, the parallelism plan is guesswork.

**Known weak evidence, flagged where used:** the Jev calibration criticism rests on a
survey of public posts plus several small independent fields rather than one large
controlled study; the pentanomial variance saving is transferred to MTG by analogy with
chess; and the Q6 items 1, 2 and 4 are my design proposals with no citations behind them.








