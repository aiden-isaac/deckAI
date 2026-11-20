# Deck validation

Group 3 tasks **3.1–3.7** were verified on 2026-11-20. Implementation commit:
`2af0cd2`. This verifies the validation gate; it does not claim the group 6
measurement acceptance gate has passed.

The gate intersects the installed Forge scripts, Forge's Standard set/ban file,
and Scryfall's paper Standard legality. It also enforces 60 minimum main-deck
cards, 15 maximum sideboard cards, and four copies across both sections, with
basic-land and scripted card exceptions. Unknown, ambiguous, noncanonical and
off-format names fail explicitly. Every successful record contains all five
checks; an empty or partial record cannot authorize scoring.

## Recorded sources

| Source | Verified snapshot |
|---|---|
| Forge upstream | `d16199280919834339c9c17ce477e8e95191f996` |
| Cardsfolder Git tree | `74f929e900b23e7e443193bd8e87e0fdf68532ab` |
| Installed scripts | 34,466, excluding `upcoming/` |
| Standard definition | `Standard@9fedc0d18436`; 21 sets, 13 bans |
| Standard file SHA256 | `9fedc0d18436fb8c5ab4bbcbdc6346ac41cde1549e7d0bc16eb358e7fb4f855f` |
| Scryfall bulk | `oracle-cards-20261120100203.jsonl.gz` |
| Bulk size / raw cards | 25,540,722 bytes / 39,356 objects |
| Bulk SHA256 | `383d271230261563804a98d83ca6a5023dff5e219c1776566f07a0702204d556` |
| Filter | `legalities.standard == "legal"` and `"paper" in games` |
| Filtered count | **5,460 card objects**, counting cards rather than face aliases |

The real bulk download was recovered from the interrupted Kiro session. Both
the bulk and `cache/scryfall/standard-legal.json` are retained locally and ignored
by Git. Offline reuse was tested with network access explicitly disabled.
Downloads and filtered-cache writes use atomic replacement; short downloads
cannot become completed cache files.

All 5,460 filtered cards resolve in the installed pool and pass the three-source
gate using their engine deck names. The reverse comparison finds six Forge
Standard names absent from Scryfall's paper-legal names: `A-Cori-Steel Cutter`,
`A-Geological Appraiser`, `A-Heartfire Hero`, `A-Kona, Rescue Beastie`,
`A-Leyline of Resonance`, and `A-Vivi Ornitier`. These disagreements are reported
and refused. They are not silently reconciled.

Engine patch and jar identity are enforced separately by the runner using
[`forge-patches/identity.json`](../forge-patches/identity.json).

## Core cards and compound names

Each of these passed the installed three-source check: Kobayashi Maru Scenario,
The Naked Time, Iroh, Tea Master; United Battlefront; Harmless Offering;
Shiko, Paragon of the Way; Stiltzkin, Moogle Merchant; Aang's Iceberg;
Solitary Cell; Seam Rip; Skycoach Conductor; and Aang, Swift Savior.

The last two resolve through `skycoach_conductor_all_aboard.txt` and
`aang_swift_savior_aang_and_la_oceans_fury.txt`. Both faces and Scryfall's combined
names resolve in the lookup index. Research shorthand such as `Iroh Tea Master`
also resolves, but deck files must use the actual engine spelling. Obtain it
with `validator.pool.resolve(name).name`; validation reports the required name
instead of accepting shorthand the JVM would strip. Genuine split cards use
their combined Forge name. A prepared creature does not inherit legality from
its separately legal copied spell.

Harmless Offering records `AI:RemoveDeck:Random`; Kobayashi Maru Scenario has no
such flags or `SVar:AI` hints. Script flags and runtime `cannot_play_well` names
are pilot disclosures attached to the score under the current spec. They do
not authorize removing cards. Actual stripping always withholds the score.

## Actual runtime refusal

An intentionally bypassed raw JVM simulation added
`Definitely Not A Card DeckAI Probe` to Forge's Tuktuk 3 deck and played Slayer 3.
Using JDK 17, seed 123, `-n 1 -c 10 -q`, the process exited successfully and
completed turn 7 with Tuktuk 3 winning. Forge nevertheless printed:

```text
An unsupported card was requested: "Definitely Not A Card DeckAI Probe" from "null".
```

The parser deduplicated the repeated warning. Even when supplied with an earlier
successful preflight record and a nominal 100% win rate, `score_run` returned
`scorable=False` and `win_rate=None`, rendering:

```text
No win rate: run is unscorable
  reason: the engine stripped cards from a deck at game start: Definitely Not A Card DeckAI Probe
```

Probe decks, full output and refusal text were retained under
`/tmp/deckai-validation-probe/`. Headless AI reveal callbacks are no-ops, so the
patched engine also emits `stripped` and `cannot_play_well` arrays from the actual
deck-validity and complaint checks. The runner must merge these from every game
with parsed stdout/stderr; quiet output alone cannot establish zero stripping.

## Reproduce validation

From the repository root:

```sh
DECKAI_FORGE_ROOT=/home/aiden/Projects/forge uv run pytest
uv lock --check
```

At implementation commit `2af0cd2`, the full suite passed **153 tests**, including
**58 validation tests**. The installed-data tests require `DECKAI_FORGE_ROOT` and
the real cached bulk; ordinary tests run without Forge or network access. The
checks include a handwritten 60+15 `.dck` round-trip, exact installed bans,
construction failures, missing cards, source disagreements, alias copy counts,
compound cards, prepared-card legality and runtime score refusal.

Runner entry points are `build_validator(..., allow_network=False)`,
`read_dck(path)`, `validator.validate(deck)`, and `result.to_dict()`. A missing or
corrupt offline cache raises `ScryfallDataUnavailable` and blocks the run.
Use `merge_runtime_reveals` to combine text-derived `RuntimeReveal` objects and
`RuntimeReveal(stripped=tuple(names), cannot_play_well=tuple(names))` from each
validated structured game record, then pass the combined reveal to `score_run`.

Legality is a dated snapshot. A later Standard change requires new bulk data
and revalidation. Candidate research and Donate deck work remain behind the
group 6 gate. Any eventual win rate describes the declared Forge AI pilot;
these validation checks do not establish that it can execute a combo.
