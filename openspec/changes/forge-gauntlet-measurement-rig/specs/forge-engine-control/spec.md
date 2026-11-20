# Spec Delta

## Purpose

Runs a pinned rules referee for external pilots, exposing faithful legal decisions and recording accepted actions without silently choosing strategy.

## ADDED Requirements

### Requirement: Pinned rules and adapter identity

The system SHALL record and verify the engine, adapter, patch, card-data and deck identities before starting or reconstructing a game.

#### Scenario: Drift refused

- **WHEN** a required source or artifact differs from its recorded identity
- **THEN** play is refused with the differing component named

### Requirement: Seat-private observations

The system SHALL expose only public state and information the acting seat is authorized to know, including face visibility and temporary reveals.

#### Scenario: Opponent private state hidden

- **WHEN** a seat receives a decision
- **THEN** opponent hidden hand contents, library order and unrevealed faces are absent

#### Scenario: Authorized reveal visible

- **WHEN** an effect permits a seat to inspect a hidden card
- **THEN** that seat receives its authorized information without exposing it to the other seat

### Requirement: External strategic ownership

Every non-forced strategic choice SHALL come from the declared external pilot. Unowned callbacks and failed answers MUST pause or fail without AI, greedy or first-legal selection.

#### Scenario: Missing response

- **WHEN** a non-forced decision has no valid pilot answer
- **THEN** the pending decision remains unapplied and no fallback move is made

#### Scenario: Forced operation

- **WHEN** exactly one legal mechanical outcome exists
- **THEN** it may execute with a forced or mechanical provenance marker

### Requirement: Validated exactly-once actions

The referee SHALL validate seat, game, decision and state revision plus the complete legal answer before applying an action at most once.

#### Scenario: Stale answer refused

- **WHEN** an answer names an old revision or another seat
- **THEN** state remains unchanged and the mismatch is reported

#### Scenario: Duplicate answer

- **WHEN** an accepted decision is submitted again
- **THEN** the previous result is returned without executing another action

### Requirement: Recorded outcomes and reconstruction

The system SHALL journal accepted decisions and produce a structured game outcome. Reconstruction MUST replay recorded actions and refuse divergent prompts or state.

#### Scenario: Completed game

- **WHEN** a game ends normally
- **THEN** its winner, reason, turns, identities and decision provenance are recorded

#### Scenario: Replay divergence

- **WHEN** reconstruction encounters a different decision or legal state
- **THEN** it stops explicitly rather than inventing an action

### Requirement: External sideboarding

The system SHALL apply legal sideboard exchanges chosen by the pilot between games and record resulting deck identities.

#### Scenario: Postboard game

- **WHEN** both pilots submit valid exchanges
- **THEN** the next game uses the recorded postboard configurations without an AI sideboard plan
