# Spec Delta

## Purpose

Governs persistent real CLI pilot sessions, isolated information access and explicit recovery when a provider or decision fails.

## ADDED Requirements

### Requirement: Persistent declared seats

Each seat SHALL have a distinct persistent CLI conversation and recorded provider, model and profile identity. The system MUST NOT cold-start a new conversation for each move.

#### Scenario: Next decision

- **WHEN** the same seat receives another decision in the game
- **THEN** its existing conversation is continued with the new private observation

### Requirement: Enforced information boundary

A pilot SHALL be unable to inspect sibling memory, referee hidden-state files or unrelated host tools, irrespective of prompt instructions.

#### Scenario: Hidden-file read

- **WHEN** a pilot runtime attempts to read a sibling or referee file
- **THEN** the runtime denies access

#### Scenario: Unexpected tool

- **WHEN** a provider configuration exposes a path to hidden state
- **THEN** live play is refused until the exposure is removed

### Requirement: Structured external answers

A CLI answer SHALL be validated against the current engine-owned choice schema and exact decision identity before relay.

#### Scenario: Malformed answer

- **WHEN** a CLI returns missing, unknown or wrongly typed action fields
- **THEN** the game pauses without a default choice

### Requirement: Quota and transport pause

Provider limits, transport loss and unsupported decisions SHALL preserve the pending state without applying a move, consuming a game-loss clock or crediting a win.

#### Scenario: Quota exhausted

- **WHEN** a provider reports a usage limit
- **THEN** the game and pending decision pause with the seat session identity preserved

### Requirement: Idempotent recovery

On reconnect the system SHALL check whether a pending answer was already applied before resubmitting it, and SHALL resume the recorded seat conversation.

#### Scenario: Response lost

- **WHEN** an accepted action response was lost before the client acknowledged it
- **THEN** recovery retrieves the accepted result without applying it twice
