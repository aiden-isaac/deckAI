# Spec Delta

## Purpose

Decides whether a decklist can be measured at all — format legality, construction rules, presence in the installed card pool, and whether the pilot can actually play its cards — and withholds a score rather than returning a misleading one.

## ADDED Requirements

### Requirement: Format legality validation

The system SHALL validate a decklist against the target format's legal set list and ban list as published by the installed engine, and SHALL reject any list containing a card that is not legal.

#### Scenario: Legal list passes

- **WHEN** a decklist contains only cards from legal sets with no banned cards
- **THEN** validation passes and records the format definition version used

#### Scenario: Banned card rejected

- **WHEN** a decklist contains a card on the ban list
- **THEN** validation fails and names the offending card and the reason

### Requirement: Construction rule validation

The system SHALL enforce the format's construction rules — minimum main-deck size, maximum sideboard size, and the per-card copy limit with its documented exceptions — independently of the engine, which does not check them in simulation mode.

#### Scenario: Illegal copy count rejected

- **WHEN** a decklist contains five copies of a card that is limited to four
- **THEN** validation fails and names the card and its count

#### Scenario: Undersized main deck rejected

- **WHEN** a decklist's main deck contains fewer cards than the format minimum
- **THEN** validation fails and reports the actual and required sizes

### Requirement: Card pool availability validation

The system SHALL verify that every card in a decklist exists in the installed engine's card pool before any game is played, because the engine silently removes unimplemented cards from the library and continues the game.

#### Scenario: Unimplemented card rejected before play

- **WHEN** a decklist names a card absent from the installed engine's card pool
- **THEN** validation fails and names the card, and no games are run

#### Scenario: Engine reveals stripped cards at runtime

- **WHEN** the engine reports at game start that cards were unsupported and removed from a deck
- **THEN** the system marks the run unscorable and reports which cards were stripped, even if validation had passed

### Requirement: Pilot competence disclosure

The system SHALL detect cards the pilot is known to play badly — including engine-declared AI-competence flags and the engine's runtime complaint list — and SHALL attach that disclosure to every result produced with those cards in the deck.

#### Scenario: Flagged card disclosed, not silently removed

- **WHEN** a decklist contains a card the engine flags as one its AI cannot play well
- **THEN** validation passes but the result records a pilot-competence warning naming that card

#### Scenario: Warning accompanies the score

- **WHEN** a result is reported for a deck containing flagged cards
- **THEN** the pilot-competence warning appears alongside the win rate rather than in a separate log

### Requirement: Withholding a score

The system SHALL refuse to report a win rate for any run whose decks failed validation or whose runtime reveals indicated stripped cards, and SHALL report the reason in place of the number.

#### Scenario: Invalid run yields no score

- **WHEN** a completed run is found to have been played with a stripped or invalid deck
- **THEN** the system reports the failure reason and does not report a win rate for that run

#### Scenario: Validation result is part of the record

- **WHEN** any run is recorded
- **THEN** its record states which validation checks ran and whether each passed, so an unvalidated run is distinguishable from a validated one
