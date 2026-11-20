# Statistics: what this project claims, and on how many games

Every number in this document is a default in `harness/stats.py`, and
`tests/test_statistics_doc.py` fails if the two drift apart. Everything is
hand-rolled from the standard library (design decision D8): no statistics
framework hides the stopping rule.

## Minimum detectable effect

**5 percentage points of win rate, at 80% power and alpha = 0.05.** That is
the smallest difference this rig calls decision-grade. Anything smaller is
either screened out as "not worth games" or measured for a long time.

Why 5 pp: at the planning throughput of 17,280 games/day, a 5 pp fixed-sample
comparison costs 3,140 games (about 4.4 hours), a 3 pp one costs 8,721 (12
hours), and a 2 pp one costs 19,623 (27 hours). Resolving 2 pp per candidate
change is not affordable, and a 2 pp change is not worth the wait.

## Sample sizes the minimum detectable effect implies

Two-proportion, two-sided, alpha = 0.05, both arms taken at p = 0.5 (the worst
case for variance):

    n_per_arm = (z_{1-alpha/2} + z_power)^2 * [p_A(1-p_A) + p_B(1-p_B)] / delta^2

with `z_{0.975} = 1.959964`, `z_{0.80} = 0.841621`, `z_{0.95} = 1.644854`, so
the constant is `7.84888` at 80% power and `12.99471` at 95%.

| Effect | 80% power, per arm | 80% power, total games | 95% power, total games |
|---|---|---|---|
| 5 pp | 1,570 | **3,140** | 5,198 |
| 3 pp | 4,361 | **8,721** | 14,439 |
| 2 pp | 9,812 | **19,623** | 32,487 |

Every sample size is rounded up. The research report's table shows 9,811 and
19,622 on the 2 pp row because it rounds 9,811.1 and 19,622.2 down; the
difference is one game.

A secondary metric with a lower base rate is cheaper, not dearer: "wins by
turn 5" at p = 0.30 needs 3,663 games per arm for the same 3 pp, because
`p(1-p) = 0.21` rather than 0.25.

## Stopping rules in use

### Screening: one-sample SPRT against a frozen incumbent baseline

| Parameter | Value |
|---|---|
| Bounds | p0 = 0.50 (no improvement) vs p1 = 0.54 (+4 percentage points) |
| Error rates | alpha = 0.05, beta = 0.05 |
| Game cap | 4,000 |
| Accept when | log-likelihood ratio >= log((1-beta)/alpha) = +2.94444 |
| Reject when | log-likelihood ratio <= log(beta/(1-alpha)) = -2.94444 |
| Per win | +log(p1/p0) = +0.07696 |
| Per loss | +log((1-p1)/(1-p0)) = -0.08338 |

The baseline is measured once per generation and frozen; a candidate is a
one-sample test against that constant, which costs half what playing both arms
costs. The baseline must be re-measured whenever any identity field other than
the candidate's own decklist hash changes, and whenever a change is accepted,
because the incumbent has moved. `harness.stats.require_current_baseline`
refuses a stale baseline and names the fields that moved.

Expected cost, from the research simulation (4,000 trials per cell): about 266
games to kill a candidate that is 5 pp worse, about 845 under the null, about
824 to confirm a real +4 pp, and about 1,398 in the indifference zone. Mean
over a realistic mix of proposals: roughly 1,100 games.

**A cap-out is inconclusive, never an acceptance.** Hitting 4,000 games means
the effect, if any, sits inside the indifference zone — exactly the case not
worth more games.

### Confirmation: paired fixed-sample over shared shuffle seeds

Sized for 3 pp at 80% power: **8,721 games**. Candidate and incumbent play the
same seeds; each seed contributes one difference, and the result is the mean
difference with its 95% interval, never a bare win rate.

Pairing is verified, not assumed. Only seeds present for *both* decklists
contribute; every game under a seed present in only one arm is excluded, with
the count and the reason reported.

### Per-matchup figures: diagnostic, never decision-grade

Games are allocated proportional to metagame weight, which minimises the
variance of the weighted aggregate. Under that allocation a 4% matchup gets 44
of a 1,100-game screen: standard error 7.5 pp, 95% interval about ±15 pp.
Resolving 5 pp *inside* one matchup would need 3,140 games in that matchup
alone — 78,500 total games at a 4% share, for one candidate change.

So a matchup whose own game count is below 3,140 is marked diagnostic-only,
and no per-matchup win rate is ever reported without its Wilson interval.
Decisions cite the weighted aggregate `sum(w_i * p_i)`, whose variance is
`sum(w_i^2 * p_i(1-p_i)/n_i)`; per-matchup numbers exist to show where to look.

### Robustness: every accepted decision is re-scored

An aggregate win rate is a property of the gauntlet weighting as much as of the
deck, so every accepted decision is re-scored under at least **two** alternative
weightings. If the direction of the weighted difference reverses under any
declared weighting, the change is reported as **metagame-contingent** rather
than as an improvement, together with the weightings under which it helps and
hurts.

### Pooling: identity equality or refusal

Results may be pooled only when all 9 identity fields match: engine commit,
patch hash, candidate decklist hash, incumbent decklist hash, gauntlet version,
AI profile, sideboarding state, per-game clock and deck-specific pilot logic.
A mismatch is refused with the differing fields named; a missing or placeholder
field is refused as unreproducible.

## Game record shape

`harness.stats` consumes plain mappings — one per completed game, as the runner
appends them to JSONL. It reads three fields:

| Field | Type | Meaning |
|---|---|---|
| `opponent` | str | gauntlet opponent id |
| `seed` | int | shuffle seed; the pairing key for the paired comparison |
| `won` | bool | whether the deck under measurement won |

The candidate's and the incumbent's records are passed as separate sequences,
so no field has to identify the arm. The pairing key defaults to
`("opponent", "seed")` and is overridable.
