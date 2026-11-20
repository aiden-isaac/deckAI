# Spec Delta

## Purpose

Drives a pinned, patched Forge build headlessly so that batches of AI-vs-AI games can be run on demand and every game returns one structured record stamped with the exact engine version that produced it.

## ADDED Requirements

### Requirement: Pinned engine identity

The system SHALL record, for every batch of games it runs, the Forge upstream commit, the hash of the applied patch series, and the card-data version in use, and SHALL refuse to run when the working engine tree does not match the recorded pin.

#### Scenario: Engine matches the pin

- **WHEN** a batch is requested and the engine tree's commit and patch hash equal the recorded pin
- **THEN** the batch runs and every resulting game record carries that commit and patch hash

#### Scenario: Engine has drifted from the pin

- **WHEN** a batch is requested and the engine tree's commit or patch hash differs from the recorded pin
- **THEN** the system refuses to run the batch and reports which component drifted

### Requirement: Headless batch execution

The system SHALL run AI-vs-AI games with no graphical interface and no network, accepting a candidate deck, an opponent deck, a game count, an AI profile per seat, and a per-game time limit.

#### Scenario: Batch of games completes

- **WHEN** a batch of N games is requested for two valid decks
- **THEN** the system returns N game records and a non-zero count of games actually played

#### Scenario: A game exceeds its time limit

- **WHEN** a game exceeds the configured per-game time limit
- **THEN** that game is recorded as a draw with a flag marking it as clock-terminated, and the batch continues

### Requirement: Per-game seeding

The system SHALL accept a distinct shuffle seed for each individual game in a batch, so that two different decklists can be played against the same sequence of shuffles.

#### Scenario: Same seed reproduces a game

- **WHEN** a recorded game is re-run alone with its recorded seed, decks, AI profile and engine pin
- **THEN** the replayed game produces the same winner and the same turn count

#### Scenario: Paired samples share seeds

- **WHEN** two candidate decklists are run against the same opponent with the same seed list
- **THEN** each seed appears exactly once per candidate, so the samples can be paired seed-for-seed

### Requirement: Structured per-game records

The system SHALL emit one machine-readable record per game containing at minimum the winner, the losing reason, the turn count, elapsed milliseconds, the seed, the seat assignment, mulligan counts for both players, and the draw flag.

#### Scenario: Record is emitted per game

- **WHEN** a batch of games completes
- **THEN** each game has exactly one record, and no field required above is absent or empty

#### Scenario: Engine output cannot be parsed

- **WHEN** the engine emits output the system cannot parse into a complete record
- **THEN** the system discards the batch rather than recording partial games, and reports the unparsed output

### Requirement: Best-of-three matches with sideboarding

The system SHALL support running best-of-three matches in which the AI sideboards between games, and SHALL report whether sideboarding was active for a given batch.

#### Scenario: Sideboarding enabled

- **WHEN** a best-of-three batch is run with sideboarding enabled
- **THEN** games after the first reflect a sideboarded deck, and each game record identifies its position in the match

#### Scenario: Sideboarding state is always recorded

- **WHEN** any batch completes
- **THEN** its records state whether sideboarding was active, so games played with and without it are never pooled silently

### Requirement: Worker parallelism bounded by memory

The system SHALL run multiple games concurrently in separate engine processes, and SHALL cap the number of concurrent workers by available system memory rather than by processor count.

#### Scenario: Worker count derived from memory

- **WHEN** a batch is requested on a host with a known amount of free memory
- **THEN** the system chooses a worker count whose combined memory ceiling fits within that free memory, and records the count used

#### Scenario: A worker process dies

- **WHEN** a worker process exits abnormally mid-batch
- **THEN** the games it had not yet completed are re-queued or reported as unrun, and no partial game is recorded as a result
