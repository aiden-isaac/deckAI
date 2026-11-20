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

### Requirement: Donation of a lethal permanent

The pilot SHALL be able to execute a donation strategy, choosing to give an opponent a permanent that will cause that opponent to lose, in preference to giving away a permanent of low value.

#### Scenario: Lethal permanent preferred over junk

- **WHEN** the pilot controls both a permanent that will make its controller lose and a low-value permanent, and a donation effect resolves
- **THEN** the pilot donates the permanent that will make its controller lose

#### Scenario: No lethal permanent available

- **WHEN** a donation effect resolves and the pilot controls no permanent that will make its controller lose
- **THEN** the pilot falls back to its prior behaviour of donating a low-value permanent, and the game continues legally

#### Scenario: Donation withheld when it would backfire

- **WHEN** donating the lethal permanent would not cause the opponent to lose before the pilot itself loses to it
- **THEN** the pilot does not donate it

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
