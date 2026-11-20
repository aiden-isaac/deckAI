# Spec Delta

## Purpose

Governs how a deck is piloted while it is being measured, so that a decklist's score reflects the deck rather than the pilot's inability to execute it — including deck-specific decision logic for strategies the engine's stock heuristics cannot play.

## ADDED Requirements

### Requirement: Declared and recorded pilot

The system SHALL require the pilot policy for each seat to be declared explicitly for every run, and SHALL record it as part of the result identity.

#### Scenario: Pilot recorded per seat

- **WHEN** a run completes
- **THEN** its record names the pilot policy used for the candidate seat and for the opponent seat

#### Scenario: Undeclared pilot is refused

- **WHEN** a run is requested without an explicit pilot policy for each seat
- **THEN** the system refuses the run rather than relying on an engine default

### Requirement: Donation is optional

The pilot SHALL be able to decline an optional donation entirely, choosing no target, whenever no permanent it controls would harm its new controller. Donating a beneficial permanent is never preferable to donating nothing.

#### Scenario: Nothing worth donating

- **WHEN** an optional donation trigger resolves and the pilot controls no permanent with a pending effect that would harm its new controller
- **THEN** the pilot declines the donation, chooses no target, and the game continues legally

#### Scenario: Declining is preferred over donating value

- **WHEN** the only permanents available to donate would benefit the opponent
- **THEN** the pilot declines rather than donating one of them

### Requirement: Donate a permanent whose pending effect harms its controller

The pilot SHALL prefer donating a permanent whose next pending effect harms whoever controls it, and SHALL evaluate the timing so that the harmful effect resolves under the new controller rather than under the pilot.

#### Scenario: Modal permanent with only the harmful mode remaining

- **WHEN** the pilot controls a permanent that triggers on its controller's upkeep, must choose a previously unchosen mode each time, and has only a mode that makes its controller lose the game still unchosen
- **THEN** the pilot donates that permanent before its own next upkeep

#### Scenario: Modal permanent with beneficial modes still available

- **WHEN** the same permanent still has beneficial modes unchosen
- **THEN** the pilot does not donate it, because the opponent would receive the beneficial modes instead

#### Scenario: Saga one chapter short of its harmful chapter

- **WHEN** the pilot controls a chapter-based permanent whose final chapter harms its controller and whose lore counters are one short of that chapter
- **THEN** the pilot donates it, so the harmful chapter resolves under the opponent

#### Scenario: Saga with beneficial chapters still pending

- **WHEN** the same chapter-based permanent has beneficial chapters still to resolve
- **THEN** the pilot does not donate it yet

#### Scenario: Fallback when no harmful permanent exists

- **WHEN** a non-optional donation effect resolves and no permanent has a pending harmful effect
- **THEN** the pilot falls back to donating its least valuable permanent and the game continues legally

### Requirement: Donation timing must favour the pilot

The pilot SHALL donate only when the harmful effect will resolve under the new controller before the pilot would suffer it, and SHALL NOT donate when the donation would leave the pilot exposed to that same effect first.

#### Scenario: Harm would strike the pilot first

- **WHEN** donating a harmful permanent would not cause the opponent to suffer its effect before the pilot's own next upkeep
- **THEN** the pilot does not donate it

#### Scenario: Harm strikes the opponent first

- **WHEN** the opponent's next upkeep precedes the pilot's, so the donated permanent's harmful effect resolves under the opponent
- **THEN** the pilot donates it

### Requirement: Deck-specific pilot logic is opt-in and attributed

The system SHALL apply deck-specific pilot logic only when a run declares it, and SHALL record which deck-specific logic was active so results produced with and without it are never pooled.

#### Scenario: Logic applied only when declared

- **WHEN** a run does not declare deck-specific pilot logic
- **THEN** the pilot behaves as the stock engine AI, and the record states that no deck-specific logic was active

#### Scenario: Results separated by pilot logic

- **WHEN** an aggregate is requested over runs that used different deck-specific pilot logic
- **THEN** the system refuses to pool them and names the differing logic

### Requirement: Measurement of pilot competence on a deck

The system SHALL provide a way to measure whether the pilot can execute a deck's intended strategy, reporting how often the deck's primary win condition is reached, so that a poor win rate caused by pilot failure is distinguishable from one caused by the decklist.

#### Scenario: Combo deck never executes its combo

- **WHEN** a deck whose intended win condition is a specific combo is measured and that win condition is reached in no games
- **THEN** the system reports a pilot-execution failure for that deck rather than reporting its win rate as a property of the decklist

#### Scenario: Execution rate reported alongside win rate

- **WHEN** a deck declares an intended win condition
- **THEN** every result for that deck reports the rate at which the win condition was reached, beside the win rate
