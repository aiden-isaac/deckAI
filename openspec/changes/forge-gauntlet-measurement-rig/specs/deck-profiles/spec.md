# Spec Delta

## Purpose

Creates initial Standard pilot knowledge from actual dated decklists, piloting guides and sideboarding evidence, with explicit provenance and access limits.

## ADDED Requirements

### Requirement: Sourced frozen decklists

Each initial profile SHALL include a real dated 60+15 Standard list, exact card counts, author or event, source URL, retrieval date and validation snapshot.

#### Scenario: List imported

- **WHEN** an online list seeds a profile
- **THEN** its exact original list and any explicitly labelled adaptation are distinguishable and validated

### Requirement: Attributable initial strategy

Profiles SHALL cover objectives, mulligans, sequencing, interaction, combat and sideboarding. Strategic claims MUST identify a source or be labelled as inference.

#### Scenario: Strategy claim

- **WHEN** an initial profile recommends a line or matchup plan
- **THEN** its supporting URL/date or inference label is available

### Requirement: Honest video and article use

The system SHALL distinguish actually inspected article/transcript/video content from descriptions, inaccessible pages and paywalled material. Timestamps MUST refer to inspected evidence.

#### Scenario: Description only

- **WHEN** only a video description is accessible
- **THEN** the profile does not claim the gameplay was watched or invent timestamped advice

### Requirement: Exact sideboard plans

Sideboard plans SHALL refer to the frozen list and distinguish directly sourced exchanges from inferred matchup adaptations.

#### Scenario: Plan validated

- **WHEN** a sideboard plan is loaded
- **THEN** every in/out card and count is checked against that profile and its source status is shown

### Requirement: Independent profile versions

Each seat SHALL use its own identified profile version, fixed throughout a match, with no shared writable strategic memory.

#### Scenario: Match begins

- **WHEN** two pilots load their profiles
- **THEN** their separate versions are recorded and remain fixed for that match
