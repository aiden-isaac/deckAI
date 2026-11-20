# Proposal

## Why

The project's goal is to decide which cards to buy by testing decklists in simulated play instead of paying for cards that turn out not to work. Every later capability — LLM-proposed card swaps, sideboard construction, deck iteration — is worthless unless the underlying measurement is trustworthy, and five research investigations ([`.agents/tasks/`](../../../.agents/tasks/)) found four Forge defaults that silently corrupt results: unscripted cards are stripped from the deck rather than rejected (a 60-card list with three unimplemented cards plays as a 57-card library), simulation mode never checks deck legality, sideboarding is disabled, and one seed covers a whole run so A/B samples cannot be paired.

This change builds the measuring instrument and proves it works before anything is built on top of it. It also makes the first target deck — a Jeskai Donate combo built on Kobayashi Maru Scenario, The Naked Time and Iroh, Tea Master — actually pilotable, because Forge's stock AI donates junk rather than a lethal enchantment and therefore cannot execute the deck's combo at all.

## What Changes

- **Pin and build Forge locally on `kano`** at a recorded commit, with a git-tracked patch series rather than a fork, so the engine version is part of every result's identity.
- **Patch four engine gaps**: emit per-game results as JSONL instead of parsing stdout text, accept a per-game seed so A/B samples can be paired by shuffle, expose `AISideboardingEnabled` (currently hardcoded off, making the 15-card sideboard goal unreachable), and expose `-mc` so the simulation can run the same AI strength as the desktop game.
- **Add a deck validation gate** that intersects Standard legality (from Forge's own `res/formats/Sanctioned/Standard.txt`), the installed Forge card pool, and the `RemAIDecks`/`complainCardsCantPlayWell` AI-competence flags, and that refuses to score any run where Forge reveals stripped or unpilotable cards.
- **Add a gauntlet runner** that owns a work queue of (candidate, opponent, seed, seat) cells, runs parallel worker JVMs sized to available RAM, and records one row per game under a run identity that includes the engine commit, patch hash, deck hashes, gauntlet version and AI profile.
- **Add the statistics layer**: mirrored play/draw and both-seat allocation, SPRT screening against a frozen incumbent baseline, and paired fixed-*n* confirmation, with every test recording its stopping reason and confidence interval.
- **Make the Jeskai Donate deck pilotable** by extending Forge's `DonateJunk` AI logic so the AI prefers donating a permanent that makes its controller lose, and by shipping a v0 decklist plus a candidate card pool explored beyond the initial suggestions.
- **Gate the whole change behind a known-answer acceptance test**: a deliberately crippled variant (24 lands cut to 20) must be rejected with the correct sign in under ~1,500 games, with non-degenerate fitness fields and a reproducible replay. **If this test fails, the change fails** — no amount of downstream work rescues an instrument that cannot detect a broken mana base.

Out of scope for this change, deliberately: the LLM proposal loop, sideboard plan optimization, the search algorithm over card counts, and migration to `jarlaxle`.

## Capabilities

### New Capabilities

- `forge-engine-control`: Driving a pinned, patched Forge build headlessly — writing deck files, seeding individual games, running batches, and returning one structured record per game. Owns the engine patch series and the version identity that every result is stamped with.
- `deck-validation`: Deciding whether a decklist is testable at all — format legality, construction rules, presence in the installed card pool, and AI pilotability — and refusing to produce a score when it is not.
- `experiment-statistics`: Turning game records into decisions — allocation across a gauntlet with mirrored play/draw and seats, sequential screening, fixed-*n* confirmation, effect sizes with confidence intervals, and the reproducibility identity that says which results may be pooled.
- `pilot-policy`: How a deck gets piloted during measurement, including the AI profile in use and deck-specific AI logic for strategies Forge's stock heuristics cannot execute, such as donating a lethal permanent.

### Modified Capabilities

None — this is the project's first change.

## Impact

- **New code**: a Python harness (`harness/`), a Forge patch series (`forge-patches/`), deck and gauntlet data (`decks/`, `gauntlets/`), and a results store (SQLite plus JSONL).
- **External dependencies**: a pinned clone of [Card-Forge/forge](https://github.com/Card-Forge/forge) (GPL-3.0) at `/home/aiden/Projects/forge`, Maven and a JDK that Forge supports, and Scryfall bulk card data for legality cross-checks.
- **Licensing**: patching and compiling against Forge makes the harness a GPL-3.0 derivative. Accepted for a personal tool; recorded here so the decision is explicit and not discovered later.
- **Hardware**: runs on `kano` (16 GB RAM, RTX 4050, 20 cores). RAM, not cores, caps worker count. Migration to `jarlaxle` is deferred, and its ~2 GB free RAM would cap it at roughly two workers until it is upgraded.
- **Known measurement ceiling, to be printed on every report the tool produces**: results are win rates as piloted by Forge's heuristic AI, which its own authors document as good at aggro and midrange, poor at control, and bad at most combo. The target deck *is* a combo deck, which makes `pilot-policy` load-bearing rather than optional.
