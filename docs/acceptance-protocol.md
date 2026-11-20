# Acceptance protocol, declared before the run

Use the five decks and frozen equal-weight gauntlet described in
`acceptance-fixtures.md`. Use stock Forge AI in both seats, sideboarding off,
Monte Carlo off, a 120-second game clock, and the exported engine identity.
Record actual JVM peak resident memory with `/usr/bin/time -v` before choosing
concurrency; the worker ceiling must cover that measurement and the JVM heap.

1. Run 200 healthy-deck games for calibration, balancing both seat orders and
   play/draw within each opponent pairing. Record actual allocation, game
   duration, draw/clock rate, peak worker RSS and sustainable worker count.
2. Freeze that baseline. Run at most 1,200 games of the 20-land candidate under
   the same identity and gauntlet, with 400 games per opponent. This keeps the
   baseline plus candidate within 1,400 games. The candidate uses shared
   shuffle seeds wherever the baseline contains the same opponent and seat.
3. Analyze candidate records in a declared order independent of outcomes:
   sort by opponent, seed and candidate seat, then shuffle with Python
   `random.Random(20261120)`. Do not use worker-completion order, which groups
   matchups. Use the frozen weighted healthy win rate as SPRT `p0`, `p1 = p0
   + 0.04`, alpha and beta 0.05, and a 1,200-game cap. Report the stopping
   observation count and the total number of games actually collected.
4. Require both SPRT rejection and a negative candidate-minus-healthy
   equal-weight aggregate. Rejection alone says the candidate failed to show
   the declared improvement; it does not prove the land reduction hurt it.
   Report effect and uncertainty alongside the screening decision. The
   frozen 200-game baseline itself has sampling uncertainty; the one-sample
   screening error rates are conditional on that estimate.
5. Check winning turns, candidate mulligans and damage through the first ten
   global turns for variation and plausible values. Require a higher mean
   mulligan count for the 20-land candidate. Report clock draws separately.
6. Reproduce one recorded game alone under its stored identity, requiring
   the same winner and turn count. Require complete runtime card-reveal
   arrays and no stripped or cannot-play-well cards in every scored game.

Record each measured criterion in `acceptance-gate.md`. If any fails, report
the failure and stop before the Donate deck, Donate AI or sideboarding work.
Do not change the decks, weighting, seed order or thresholds after seeing
the results to make the gate pass. Any revised experiment needs a separately
declared protocol and the user's decision.

These results measure Forge's heuristic pilot. They do not establish human
competitive performance, particularly for control or combo decks.
