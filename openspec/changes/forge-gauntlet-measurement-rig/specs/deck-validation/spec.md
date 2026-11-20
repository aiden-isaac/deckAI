# Spec Delta

## Purpose

Verifies that sourced Standard lists are constructible, legal in the dated paper snapshot and available in the installed rules engine before play.

## ADDED Requirements

### Requirement: Three-source legality

The system SHALL require agreement between the pinned format definition, installed card pool and dated paper-legality source. Disagreements MUST be named rather than resolved silently.

#### Scenario: Legal list

- **WHEN** every card resolves and all legality sources agree
- **THEN** the list passes with the source versions recorded

#### Scenario: Disagreement

- **WHEN** the paper source and installed format disagree
- **THEN** the list is refused and the card and sources are named

### Requirement: Construction rules

The system SHALL enforce the Standard minimum main size, maximum sideboard size and copy limits with documented card exceptions. Initial MVP profiles MUST freeze exactly 60 main and 15 sideboard cards.

#### Scenario: Invalid construction

- **WHEN** a list violates a size or copy rule
- **THEN** it is refused with the actual and allowed values

### Requirement: Runtime integrity

A run with missing validation or stripped/unsupported cards SHALL be invalid and SHALL NOT receive a scored result.

#### Scenario: Stripped card

- **WHEN** the engine removes a named card at runtime despite preflight validation
- **THEN** the run is invalidated and the card is reported

### Requirement: Pilot warning attribution

Stock-engine AI competence flags SHALL be labelled as stock-AI metadata and SHALL NOT be presented as proof about the external LLM pilot.

#### Scenario: External pilot uses flagged card

- **WHEN** a card carries a Forge AI competence flag
- **THEN** the metadata is disclosed without silently removing the card or claiming the LLM cannot play it

### Requirement: Postboard validation

Each proposed sideboard exchange SHALL use available cards, preserve deck totals and pass construction and legality checks before the next game.

#### Scenario: Invalid exchange

- **WHEN** a proposed exchange uses an absent card or inconsistent in/out counts
- **THEN** the exchange is refused without changing the deck
