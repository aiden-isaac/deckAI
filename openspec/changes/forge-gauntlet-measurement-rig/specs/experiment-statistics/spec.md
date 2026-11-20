# Spec Delta

## Purpose

Turns individual game records into defensible decisions about decklists — allocating games across a gauntlet, screening candidates sequentially, confirming winners, and reporting effect sizes with the uncertainty attached.

## ADDED Requirements

### Requirement: Balanced allocation across a gauntlet

The system SHALL allocate a candidate's games across the gauntlet's opponents according to a declared weighting, and SHALL balance play/draw and seat assignment within every candidate-opponent pairing.

#### Scenario: Play and draw are balanced

- **WHEN** a candidate is run for an even number of games against one opponent
- **THEN** half those games are on the play and half on the draw

#### Scenario: Allocation follows the declared weighting

- **WHEN** a candidate is screened against a weighted gauntlet
- **THEN** each opponent's share of games matches its declared weight within rounding, and the weighting used is recorded with the result

### Requirement: Sequential screening against a frozen baseline

The system SHALL screen a candidate against a previously measured incumbent baseline using a sequential test with pre-declared bounds and error rates, stopping as soon as the test reaches a decision or hits its game cap.

#### Scenario: Clearly worse candidate stops early

- **WHEN** a candidate is substantially worse than the baseline
- **THEN** the test rejects it well before the game cap and records the stopping reason as a rejection

#### Scenario: Inconclusive candidate hits the cap

- **WHEN** a candidate's true effect lies between the declared bounds
- **THEN** the test runs to its game cap and records the outcome as inconclusive rather than as an acceptance or a rejection

#### Scenario: Baseline must be current

- **WHEN** a screening test is requested and the baseline was measured under a different engine pin, gauntlet version, AI profile or incumbent decklist
- **THEN** the system refuses to screen against that baseline and requires it to be re-measured

### Requirement: Paired confirmation of an accepted change

The system SHALL confirm an accepted candidate with a paired fixed-sample test that compares candidate and incumbent over the same shuffle seeds, and SHALL report the effect size with a confidence interval.

#### Scenario: Confirmation reports an interval

- **WHEN** a confirmation run completes
- **THEN** the result states the point estimate of the win-rate difference and its confidence interval, not a bare win rate

#### Scenario: Pairing is verified, not assumed

- **WHEN** a paired confirmation is assembled from game records
- **THEN** only seeds present for both decklists contribute to the paired comparison, and any unpaired games are reported as excluded

### Requirement: Per-matchup numbers carry their uncertainty

The system SHALL report per-matchup win rates only together with their confidence intervals, and SHALL mark per-matchup figures as diagnostic rather than decision-grade whenever their sample size is below the level needed to resolve the declared minimum effect.

#### Scenario: Small matchup sample is marked diagnostic

- **WHEN** a matchup received too few games to resolve the declared minimum detectable effect
- **THEN** its win rate is reported with its interval and an explicit diagnostic-only marker

#### Scenario: Decisions use the aggregate

- **WHEN** an accept or reject decision is recorded
- **THEN** the decision cites the weighted aggregate, and per-matchup figures appear only as supporting diagnosis

### Requirement: Result identity and poolability

The system SHALL stamp every result with an identity comprising the engine pin, patch hash, decklist hashes, gauntlet version, AI profile, sideboarding state and time limit, and SHALL refuse to pool results whose identities differ.

#### Scenario: Mismatched results are not pooled

- **WHEN** an aggregate is requested over results with differing identity fields
- **THEN** the system refuses to combine them and names the fields that differ

#### Scenario: Identity enables reproduction

- **WHEN** a stored result is selected for reproduction
- **THEN** its identity contains everything needed to re-run it without consulting any other source

### Requirement: Robustness of a decision to the gauntlet weighting

The system SHALL re-score every accepted decision under at least two alternative gauntlet weightings and SHALL report any decision whose direction changes as contingent on the metagame rather than as an improvement.

#### Scenario: Sign flips under an alternative weighting

- **WHEN** an accepted change's measured advantage reverses under an alternative weighting
- **THEN** the result records the change as metagame-contingent and reports the weightings under which it helps and hurts

#### Scenario: Robust change is reported as such

- **WHEN** an accepted change retains its direction under every declared weighting
- **THEN** the result records it as robust to the tested weightings
