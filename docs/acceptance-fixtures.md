# Acceptance fixtures

These are fixed, hand-authored Standard decks for testing the measuring
instrument. They are not tournament lists or card-buying recommendations.

`decks/acceptance/healthy.dck` is a red creature-and-burn deck with 24 Mountains,
including four- and five-mana threats. `crippled.dck` replaces exactly four
Mountains with four Kellan, Planar Trailblazer, keeping 60 cards. The hypothesis
is that this land reduction hurts the deck. Its effect must be measured; the
filename does not establish that the hypothesis is true.

`gauntlets/acceptance/manifest.json` freezes three equally weighted opponents:
white lifegain, green elves and black midrange. Their byte hashes and weights
are part of the gauntlet version. Check for drift with:

```sh
python -m harness.gauntlet gauntlets/acceptance/manifest.json
```

All five decks passed the installed-card, construction, Forge Standard and
cached Scryfall Standard checks on 2026-11-20. No AI competence flags were
present. The sources were Forge commit
`d16199280919834339c9c17ce477e8e95191f996`, format hash
`9fedc0d18436`, and Scryfall oracle bulk `20261120100203`.

This is preflight validation. Runtime card-stripping checks, the 200-game
calibration, the statistical rejection and single-game reproduction remain
necessary before the acceptance gate can pass. All later numbers describe
Forge heuristic AI play, including its limitations at control and combo.
